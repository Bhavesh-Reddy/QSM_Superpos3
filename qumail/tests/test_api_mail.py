"""Smoke tests for POST /mail/send, GET /mail/fetch, POST /mail/read
(M2b routes_mail), with SendService/ReceiveService/IEmailService mocked via
FastAPI dependency overrides — no real crypto/KM/email happens here.
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi.testclient import TestClient

from backend.app.api.deps import get_mail_service, get_receive_service, get_send_service
from backend.main import create_app
from core.models import EmailMessage, SecurityLevel


class FakeSendService:
    """Records the call it received and returns a canned result."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def send(self, to, subject, body, level, attachments=None):
        self.calls.append(
            {"to": to, "subject": subject, "body": body, "level": level, "attachments": attachments}
        )
        return self.result


class FakeReceiveService:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.last_message_id: str | None = None

    def read(self, message_id, **kwargs):
        self.last_message_id = message_id
        return self.result


class FakeMailService:
    def __init__(self, messages: list[EmailMessage]) -> None:
        self._messages = messages

    def send(self, message, encrypted):
        raise NotImplementedError

    def fetch(self, folder: str = "INBOX", limit: int = 20) -> list[EmailMessage]:
        return self._messages


def _client(app=None) -> TestClient:
    return TestClient(app or create_app())


def test_send_mail_success() -> None:
    app = create_app()
    fake = FakeSendService({"message_id": "<abc@qumail.local>", "key_id": "QK-1", "level": SecurityLevel.OTP})
    app.dependency_overrides[get_send_service] = lambda: fake
    client = _client(app)

    resp = client.post(
        "/mail/send", json={"to": "bob@example.com", "subject": "hi", "body": "hello", "level": 1}
    )

    assert resp.status_code == 200
    assert resp.json() == {"message_id": "<abc@qumail.local>", "key_id": "QK-1", "level": 1}
    assert fake.calls[0]["to"] == "bob@example.com"
    assert fake.calls[0]["level"] == SecurityLevel.OTP


def test_send_mail_decodes_base64_attachment() -> None:
    app = create_app()
    fake = FakeSendService({"message_id": "<abc@qumail.local>", "key_id": None, "level": SecurityLevel.NONE})
    app.dependency_overrides[get_send_service] = lambda: fake
    client = _client(app)

    data_b64 = base64.b64encode(b"file bytes").decode("ascii")
    resp = client.post(
        "/mail/send",
        json={
            "to": "bob@example.com",
            "subject": "hi",
            "body": "hello",
            "level": 4,
            "attachments": [{"filename": "a.txt", "data": data_b64}],
        },
    )

    assert resp.status_code == 200
    attachments = fake.calls[0]["attachments"]
    assert attachments[0].filename == "a.txt"
    assert attachments[0].data == b"file bytes"


def test_fetch_mail_returns_summaries_never_ciphertext() -> None:
    app = create_app()
    message = EmailMessage(
        sender="alice@example.com",
        recipient="bob@example.com",
        subject="hi",
        body="",
        security_metadata={
            "message_id": "1",
            "body": {
                "level": 2,
                "metadata": {"algorithm": "AES-256-GCM", "key_id": "QK-1"},
                "ciphertext_b64": base64.b64encode(b"secret-ciphertext").decode("ascii"),
            },
        },
    )
    app.dependency_overrides[get_mail_service] = lambda: FakeMailService([message])
    client = _client(app)

    resp = client.get("/mail/fetch")

    assert resp.status_code == 200
    raw_text = resp.text
    assert "secret-ciphertext" not in raw_text
    assert "QK-1" not in raw_text  # summaries never expose key_id, only algorithm/level
    summary = resp.json()["messages"][0]
    assert summary["is_encrypted"] is True
    assert summary["level"] == 2
    assert summary["algorithm"] == "AES-256-GCM"


def test_read_mail_success() -> None:
    app = create_app()
    fake = FakeReceiveService(
        {
            "plaintext": b"hello world",
            "level": SecurityLevel.QUANTUM_AES,
            "metadata": {"key_id": "QK-1", "algorithm": "AES-256-GCM"},
        }
    )
    app.dependency_overrides[get_receive_service] = lambda: fake
    client = _client(app)

    resp = client.post("/mail/read", json={"message_id": "msg-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["body"] == "hello world"
    assert body["level"] == 2
    assert body["metadata"] == {"key_id": "QK-1", "algorithm": "AES-256-GCM"}
    assert fake.last_message_id == "msg-1"
