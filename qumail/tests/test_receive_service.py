"""Tests for M2a ReceiveService: locate -> resolve key -> decrypt.

Uses hand-written fakes of all four ``core.interfaces`` contracts (rather
than mocks) so we can assert real call order and real state changes without
over-specifying implementation detail.
"""

from __future__ import annotations

import base64
import inspect

import pytest

from backend.app.services import receive_service
from backend.app.services.receive_service import ReceiveService
from core.exceptions import EmailFetchError, KeyNotFoundError
from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient
from core.models import (
    EmailMessage,
    EncryptedMessage,
    ETSIStatus,
    QKDKey,
    SecurityLevel,
)

SENDER = "alice@example.com"
KEY_ID = "QK-000001"
KEY_BYTES = b"\x11" * 16


def _qumail_message(
    message_id: str,
    ciphertext: bytes,
    level: SecurityLevel = SecurityLevel.QUANTUM_AES,
    key_id: str | None = KEY_ID,
) -> EmailMessage:
    body_metadata = {"key_id": key_id} if key_id is not None else {}
    return EmailMessage(
        sender=SENDER,
        recipient="bob@example.com",
        subject="hi",
        body="",
        security_metadata={
            "message_id": message_id,
            "body": {
                "level": int(level),
                "metadata": body_metadata,
                "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            },
        },
    )


class FakeKMClient(IKMClient):
    def __init__(self, call_log: list[str], keys_by_id: dict[str, QKDKey]) -> None:
        self.call_log = call_log
        self._keys_by_id = keys_by_id

    def get_status(self) -> ETSIStatus:
        raise NotImplementedError("not exercised by ReceiveService")

    def get_key(self, target_sae_id: str, number: int = 1, size: int = 256) -> list[QKDKey]:
        raise NotImplementedError("not exercised by ReceiveService")

    def get_key_with_ids(self, source_sae_id: str, key_ids: list[str]) -> list[QKDKey]:
        self.call_log.append("km.get_key_with_ids")
        return [self._keys_by_id[key_id] for key_id in key_ids if key_id in self._keys_by_id]


class FakeKeyStore(IKeyStore):
    def __init__(self, call_log: list[str], seed: dict[str, QKDKey] | None = None) -> None:
        self.call_log = call_log
        self._keys: dict[str, QKDKey] = dict(seed or {})

    def put(self, key: QKDKey) -> None:
        self.call_log.append("store.put")
        self._keys[key.key_id] = key

    def get(self, key_id: str) -> QKDKey:
        self.call_log.append("store.get")
        try:
            return self._keys[key_id]
        except KeyError:
            raise KeyNotFoundError(key_id) from None

    def consume(self, key_id: str) -> QKDKey:
        raise NotImplementedError("not exercised by ReceiveService")


class FakeCryptoEngine(ICryptoEngine):
    """Pass-through 'decryption'; records calls and echoes the ciphertext."""

    def __init__(self, call_log: list[str]) -> None:
        self.call_log = call_log
        self.last_key: QKDKey | None = None

    def encrypt(
        self,
        plaintext: bytes,
        level: SecurityLevel,
        key: QKDKey | None = None,
        recipient_public_key: bytes | None = None,
    ) -> EncryptedMessage:
        raise NotImplementedError("not exercised by ReceiveService")

    def decrypt(
        self,
        message: EncryptedMessage,
        key: QKDKey | None = None,
        private_key: bytes | None = None,
        sender_public_key: bytes | None = None,
    ) -> bytes:
        self.call_log.append("crypto.decrypt")
        self.last_key = key
        return message.ciphertext


class FakeEmailService(IEmailService):
    def __init__(self, call_log: list[str], messages: list[EmailMessage]) -> None:
        self.call_log = call_log
        self._messages = messages

    def send(self, message: EmailMessage, encrypted: EncryptedMessage) -> str:
        raise NotImplementedError("not exercised by ReceiveService")

    def fetch(self, folder: str = "INBOX", limit: int = 20) -> list[EmailMessage]:
        self.call_log.append("mail.fetch")
        return self._messages


def test_services_layer_has_no_fastapi_imports() -> None:
    """M2a rule: orchestration must stay free of HTTP-framework concerns."""
    assert "fastapi" not in inspect.getsource(receive_service)


def test_resolves_key_from_store_without_calling_km() -> None:
    call_log: list[str] = []
    key = QKDKey(key_id=KEY_ID, key=KEY_BYTES, size_bits=128)
    message = _qumail_message("msg-1", b"ciphertext-bytes")

    km = FakeKMClient(call_log, keys_by_id={})
    store = FakeKeyStore(call_log, seed={KEY_ID: key})
    crypto = FakeCryptoEngine(call_log)
    mail = FakeEmailService(call_log, [message])
    svc = ReceiveService(crypto=crypto, km=km, mail=mail, store=store)

    result = svc.read("msg-1")

    assert call_log == ["mail.fetch", "store.get", "crypto.decrypt"]
    assert result["plaintext"] == b"ciphertext-bytes"
    assert result["level"] == SecurityLevel.QUANTUM_AES
    assert crypto.last_key == key


def test_falls_back_to_km_and_caches_key_on_store_miss() -> None:
    call_log: list[str] = []
    key = QKDKey(key_id=KEY_ID, key=KEY_BYTES, size_bits=128)
    message = _qumail_message("msg-2", b"other-ciphertext")

    km = FakeKMClient(call_log, keys_by_id={KEY_ID: key})
    store = FakeKeyStore(call_log)  # empty: forces the KM fallback
    crypto = FakeCryptoEngine(call_log)
    mail = FakeEmailService(call_log, [message])
    svc = ReceiveService(crypto=crypto, km=km, mail=mail, store=store)

    result = svc.read("msg-2")

    assert call_log == ["mail.fetch", "store.get", "km.get_key_with_ids", "store.put", "crypto.decrypt"]
    assert result["plaintext"] == b"other-ciphertext"
    assert crypto.last_key == key


def test_plain_non_qumail_message_skips_key_resolution() -> None:
    call_log: list[str] = []
    message = EmailMessage(
        sender=SENDER,
        recipient="bob@example.com",
        subject="hi",
        body="plain text",
        security_metadata={"message_id": "anything"},
    )

    km = FakeKMClient(call_log, keys_by_id={})
    store = FakeKeyStore(call_log)
    crypto = FakeCryptoEngine(call_log)
    mail = FakeEmailService(call_log, [message])
    svc = ReceiveService(crypto=crypto, km=km, mail=mail, store=store)

    result = svc.read("anything")

    assert call_log == ["mail.fetch", "crypto.decrypt"]
    assert result["plaintext"] == b"plain text"
    assert result["level"] == SecurityLevel.NONE
    assert crypto.last_key is None


def test_unknown_message_id_raises_email_fetch_error() -> None:
    call_log: list[str] = []
    km = FakeKMClient(call_log, keys_by_id={})
    store = FakeKeyStore(call_log)
    crypto = FakeCryptoEngine(call_log)
    mail = FakeEmailService(call_log, [_qumail_message("msg-1", b"x")])
    svc = ReceiveService(crypto=crypto, km=km, mail=mail, store=store)

    with pytest.raises(EmailFetchError):
        svc.read("does-not-exist")
