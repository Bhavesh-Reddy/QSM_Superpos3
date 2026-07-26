"""Tests for M2a SendService: key -> encrypt -> send sequencing.

Uses hand-written fakes of all four ``core.interfaces`` contracts (rather
than mocks) so we can assert real call order and real state changes (OTP
consumption, store contents) without over-specifying implementation detail.
"""

from __future__ import annotations

import inspect

import pytest

from backend.app.services import send_service
from backend.app.services.send_service import SendService
from core.exceptions import EncryptionError, KeyAlreadyConsumedError, KeyNotFoundError
from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient
from core.models import (
    EncryptedMessage,
    EmailMessage,
    ETSIStatus,
    QKDKey,
    SecurityLevel,
)

SENDER_SAE = "SAE-ALICE"
RECIPIENT = "bob@example.com"


class FakeKMClient(IKMClient):
    """Hands out keys of a caller-controlled size; records every call."""

    def __init__(self, call_log: list[str], *, fixed_size_bits: int | None = None) -> None:
        self.call_log = call_log
        self._fixed_size_bits = fixed_size_bits
        self._counter = 0

    def get_status(self) -> ETSIStatus:
        raise NotImplementedError("not exercised by SendService")

    def get_key(self, target_sae_id: str, number: int = 1, size: int = 256) -> list[QKDKey]:
        self.call_log.append("km.get_key")
        self._counter += 1
        size_bits = self._fixed_size_bits if self._fixed_size_bits is not None else size
        return [
            QKDKey(
                key_id=f"QK-{self._counter:06d}",
                key=b"\x00" * (size_bits // 8 or 1),
                size_bits=size_bits,
            )
            for _ in range(number)
        ]

    def get_key_with_ids(self, source_sae_id: str, key_ids: list[str]) -> list[QKDKey]:
        raise NotImplementedError("not exercised by SendService")


class FakeKeyStore(IKeyStore):
    """In-memory key store; records puts/consumes and enforces single-use."""

    def __init__(self, call_log: list[str]) -> None:
        self.call_log = call_log
        self._keys: dict[str, QKDKey] = {}
        self.consumed: list[str] = []

    def put(self, key: QKDKey) -> None:
        self.call_log.append("store.put")
        self._keys[key.key_id] = key

    def get(self, key_id: str) -> QKDKey:
        try:
            return self._keys[key_id]
        except KeyError:
            raise KeyNotFoundError(key_id) from None

    def consume(self, key_id: str) -> QKDKey:
        self.call_log.append("store.consume")
        key = self.get(key_id)
        if key.key_id in self.consumed:
            raise KeyAlreadyConsumedError(key_id)
        self.consumed.append(key.key_id)
        return key


class FakeCryptoEngine(ICryptoEngine):
    """Pass-through 'encryption'; records calls and echoes the key_id."""

    def __init__(self, call_log: list[str]) -> None:
        self.call_log = call_log

    def encrypt(
        self,
        plaintext: bytes,
        level: SecurityLevel,
        key: QKDKey | None = None,
        recipient_public_key: bytes | None = None,
    ) -> EncryptedMessage:
        self.call_log.append("crypto.encrypt")
        metadata = {"algorithm": level.name}
        if key is not None:
            metadata["key_id"] = key.key_id
        return EncryptedMessage(ciphertext=plaintext, metadata=metadata, level=level)

    def decrypt(
        self,
        message: EncryptedMessage,
        key: QKDKey | None = None,
        private_key: bytes | None = None,
        sender_public_key: bytes | None = None,
    ) -> bytes:
        raise NotImplementedError("not exercised by SendService")


class FakeEmailService(IEmailService):
    """Records the send call and returns a canned Message-ID."""

    def __init__(self, call_log: list[str]) -> None:
        self.call_log = call_log
        self.sent: list[tuple[EmailMessage, EncryptedMessage]] = []

    def send(self, message: EmailMessage, encrypted: EncryptedMessage) -> str:
        self.call_log.append("mail.send")
        self.sent.append((message, encrypted))
        return "<msg-1@qumail.local>"

    def fetch(self, folder: str = "INBOX", limit: int = 20) -> list[EmailMessage]:
        raise NotImplementedError("not exercised by SendService")


def _build_service(
    call_log: list[str], *, fixed_key_size_bits: int | None = None
) -> tuple[SendService, FakeKMClient, FakeKeyStore, FakeCryptoEngine, FakeEmailService]:
    km = FakeKMClient(call_log, fixed_size_bits=fixed_key_size_bits)
    store = FakeKeyStore(call_log)
    crypto = FakeCryptoEngine(call_log)
    mail = FakeEmailService(call_log)
    return SendService(crypto=crypto, km=km, mail=mail, store=store), km, store, crypto, mail


def test_services_layer_has_no_fastapi_imports() -> None:
    """M2a rule: orchestration must stay free of HTTP-framework concerns."""
    assert "fastapi" not in inspect.getsource(send_service)


def test_otp_call_order_is_key_then_encrypt_then_consume_then_send() -> None:
    call_log: list[str] = []
    svc, _km, store, _crypto, mail = _build_service(call_log)

    result = svc.send(RECIPIENT, "hi", "hello world", SecurityLevel.OTP)

    assert call_log == ["km.get_key", "store.put", "crypto.encrypt", "store.consume", "mail.send"]
    assert result["key_id"] in store.consumed
    assert result["level"] == SecurityLevel.OTP
    assert mail.sent[0][0].security_metadata["key_id"] == result["key_id"]


def test_aes_call_order_has_no_consume() -> None:
    call_log: list[str] = []
    svc, *_ = _build_service(call_log)

    svc.send(RECIPIENT, "hi", "hello world", SecurityLevel.QUANTUM_AES)

    assert call_log == ["km.get_key", "store.put", "crypto.encrypt", "mail.send"]


def test_otp_consumes_its_key_exactly_once() -> None:
    call_log: list[str] = []
    svc, _km, store, _crypto, _mail = _build_service(call_log)

    result = svc.send(RECIPIENT, "hi", "secret", SecurityLevel.OTP)

    assert store.consumed.count(result["key_id"]) == 1
    assert call_log.count("store.consume") == 1


@pytest.mark.parametrize("level", [SecurityLevel.PQC, SecurityLevel.NONE])
def test_l3_and_l4_make_no_km_call(level: SecurityLevel) -> None:
    call_log: list[str] = []
    svc, *_ = _build_service(call_log)

    result = svc.send(RECIPIENT, "hi", "hello world", level)

    assert "km.get_key" not in call_log
    assert "store.put" not in call_log
    assert "store.consume" not in call_log
    assert result["key_id"] is None
    assert call_log == ["crypto.encrypt", "mail.send"]


def test_short_otp_key_raises_before_persisting() -> None:
    call_log: list[str] = []
    # Recipient KM always hands back a 8-bit key, far short of any real body.
    svc, _km, store, _crypto, mail = _build_service(call_log, fixed_key_size_bits=8)

    with pytest.raises(EncryptionError):
        svc.send(RECIPIENT, "hi", "a plaintext body longer than one byte", SecurityLevel.OTP)

    # The undersized key must never be cached or sent.
    assert "store.put" not in call_log
    assert "mail.send" not in call_log
    assert mail.sent == []
