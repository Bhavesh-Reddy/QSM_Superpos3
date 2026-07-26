"""Smoke tests for GET /keys/status (M2b routes_keys) and the
not-connected guards in ``backend/app/api/deps.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import AppState, get_km_client, get_mail_service
from backend.main import create_app
from core.exceptions import ConfigError, KMConnectionError
from core.models import ETSIStatus


class FakeKMClient:
    def __init__(self, status: ETSIStatus | None = None, exc: Exception | None = None) -> None:
        self._status = status
        self._exc = exc

    def get_status(self) -> ETSIStatus:
        if self._exc is not None:
            raise self._exc
        assert self._status is not None
        return self._status


def test_keys_status_success() -> None:
    app = create_app()
    status = ETSIStatus(
        source_KME_ID="KME-1",
        target_KME_ID="KME-2",
        master_SAE_ID="SAE-ALICE",
        slave_SAE_ID="SAE-BOB",
        stored_key_count=3,
    )
    app.dependency_overrides[get_km_client] = lambda: FakeKMClient(status=status)
    client = TestClient(app)

    resp = client.get("/keys/status")

    assert resp.status_code == 200
    assert resp.json()["stored_key_count"] == 3


def test_keys_status_km_connection_error_maps_to_502() -> None:
    app = create_app()
    app.dependency_overrides[get_km_client] = lambda: FakeKMClient(
        exc=KMConnectionError("KM unreachable")
    )
    client = TestClient(app)

    resp = client.get("/keys/status")

    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "KMConnectionError"


def test_get_km_client_raises_config_error_when_not_connected() -> None:
    state = AppState(crypto=object(), store=object())  # type: ignore[arg-type]
    with pytest.raises(ConfigError):
        get_km_client(state)


def test_get_mail_service_raises_config_error_when_not_connected() -> None:
    state = AppState(crypto=object(), store=object())  # type: ignore[arg-type]
    with pytest.raises(ConfigError):
        get_mail_service(state)
