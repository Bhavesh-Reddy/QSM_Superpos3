"""Exception -> HTTP status mapping matrix (M2b, registered once in
``backend/main.py``). Exercised through POST /mail/read with a
ReceiveService double that raises the exception under test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import get_receive_service
from backend.main import create_app
from core.exceptions import (
    ConfigError,
    DecryptionError,
    EmailFetchError,
    EncryptionError,
    KeyAlreadyConsumedError,
    KeyExhaustedError,
    KeyNotFoundError,
    KMConnectionError,
    KMResponseError,
    SignatureVerificationError,
    UnsupportedSecurityLevelError,
)


class RaisingReceiveService:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def read(self, message_id, **kwargs):
        raise self._exc


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (KMConnectionError("KM unreachable"), 502),
        (KMResponseError("malformed ETSI 014 body"), 502),
        (KeyExhaustedError("no key material"), 409),
        (KeyNotFoundError("QK-1"), 404),
        (KeyAlreadyConsumedError("QK-1"), 409),
        (DecryptionError("bad GCM tag"), 400),
        (SignatureVerificationError("bad ML-DSA signature"), 400),
        (EncryptionError("OTP key too short"), 422),
        (UnsupportedSecurityLevelError("level 9"), 422),
        (EmailFetchError("IMAP fetch failed"), 502),
        (ConfigError("KM not connected"), 500),
    ],
)
def test_exception_maps_to_expected_status(exc: Exception, expected_status: int) -> None:
    app = create_app()
    app.dependency_overrides[get_receive_service] = lambda: RaisingReceiveService(exc)
    client = TestClient(app)

    resp = client.post("/mail/read", json={"message_id": "msg-1"})

    assert resp.status_code == expected_status
    body = resp.json()
    assert body["error"]["type"] == type(exc).__name__
    assert body["error"]["message"] == str(exc)
