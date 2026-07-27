"""Tests for M5 Receiver parsing + M2b app-password normalization.

Covers the two fixes that make Inbox -> open -> decrypt work end to end:
  * every fetched message carries a stable ``security_metadata["message_id"]``
    (QuMail and plain), so ``POST /mail/read`` can locate it;
  * app passwords pasted with display spaces are stripped on connect.
"""

from __future__ import annotations

from backend.app.api.deps import AppState
from backend.app.api.routes_auth import EmailConnectRequest, connect_email
from backend.app.email_svc import mime_packer
from backend.app.email_svc.receiver import Receiver
from core.models import EncryptedMessage, SecurityLevel


class _StubCrypto:
    pass


class _StubStore:
    pass


def _qumail_raw() -> bytes:
    built = mime_packer.build(
        sender="alice@gmail.com",
        recipient="bob@gmail.com",
        subject="ops",
        encrypted_body=EncryptedMessage(
            ciphertext=b"\x01\x02ciphertext",
            metadata={"algorithm": "AES-256-GCM", "key_id": "QK-000001"},
            level=SecurityLevel.QUANTUM_AES,
        ),
    )
    return built.as_bytes()


def test_qumail_message_carries_message_id_and_envelope() -> None:
    msg = Receiver._to_email_message(_qumail_raw(), message_id="42")
    assert msg.security_metadata["message_id"] == "42"
    body = msg.security_metadata["body"]
    assert body["level"] == int(SecurityLevel.QUANTUM_AES)
    assert body["metadata"]["key_id"] == "QK-000001"


def test_plain_message_still_gets_a_message_id() -> None:
    raw = (
        b"From: someone@example.com\r\n"
        b"To: me@gmail.com\r\n"
        b"Subject: plain hello\r\n"
        b"Content-Type: text/plain\r\n\r\n"
        b"just text\r\n"
    )
    msg = Receiver._to_email_message(raw, message_id="7")
    assert msg.security_metadata["message_id"] == "7"
    assert msg.security_metadata.get("body") is None  # not a QuMail message
    assert msg.body.strip() == "just text"


def test_connect_email_strips_app_password_spaces() -> None:
    # A Gmail app password pasted with its display spaces must be stored
    # without them, or SMTP/IMAP login fails.
    state = AppState(crypto=_StubCrypto(), store=_StubStore())
    resp = connect_email(
        EmailConnectRequest(email=" alice@gmail.com ", password="abcd efgh ijkl mnop"),
        state=state,
    )

    assert resp.connected is True
    assert resp.address == "alice@gmail.com"
    assert resp.provider == "gmail"
    # The stored credential has no spaces (and the address is trimmed).
    assert state.mail._account.password == "abcdefghijklmnop"
    assert state.mail._account.address == "alice@gmail.com"
