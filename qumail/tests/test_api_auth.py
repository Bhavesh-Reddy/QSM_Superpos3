"""Smoke tests for POST /auth/km and POST /auth/email (M2b routes_auth).

``KMClient`` performs real network I/O in its constructor's later calls, so
it is monkeypatched at the point ``routes_auth`` imports it. ``EmailAccount``
/``EmailService`` do no I/O at construction time, so the real classes are
exercised against a genuinely known domain (gmail) without needing fakes.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api import routes_auth
from backend.app.api.deps import AppState, get_app_state
from backend.main import create_app
from core.exceptions import KMConnectionError
from core.models import ETSIStatus


class FakeKMClient:
    """Stands in for ``backend.app.km.client.KMClient`` — no network calls."""

    def __init__(self, base_url: str, sae_id: str, verify_tls: bool = True) -> None:
        self.base_url = base_url
        self.sae_id = sae_id

    def get_status(self) -> ETSIStatus:
        return ETSIStatus(
            source_KME_ID="KME-1",
            target_KME_ID="KME-2",
            master_SAE_ID=self.sae_id,
            slave_SAE_ID="SAE-BOB",
            stored_key_count=5,
        )


class FailingKMClient(FakeKMClient):
    def get_status(self) -> ETSIStatus:
        raise KMConnectionError("KM unreachable")


def _client() -> TestClient:
    app = create_app()
    # No real lifespan/Settings/KeyStore for these route-wiring smoke tests —
    # stand in a bare AppState so get_app_state() doesn't need real startup.
    app.dependency_overrides[get_app_state] = lambda: AppState(
        crypto=object(), store=object()  # type: ignore[arg-type]
    )
    return TestClient(app)


def test_connect_km_success(monkeypatch) -> None:
    monkeypatch.setattr(routes_auth, "KMClient", FakeKMClient)
    client = _client()

    resp = client.post("/auth/km", json={"base_url": "http://km.test", "sae_id": "SAE-ALICE"})

    assert resp.status_code == 200
    assert resp.json()["master_SAE_ID"] == "SAE-ALICE"


def test_connect_km_unreachable_maps_to_502(monkeypatch) -> None:
    monkeypatch.setattr(routes_auth, "KMClient", FailingKMClient)
    client = _client()

    resp = client.post("/auth/km", json={"base_url": "http://km.test", "sae_id": "SAE-ALICE"})

    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "KMConnectionError"


def test_connect_email_auto_detected_provider() -> None:
    client = _client()

    resp = client.post(
        "/auth/email", json={"email": "alice@gmail.com", "password": "app-password"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"connected": True, "address": "alice@gmail.com", "provider": "gmail"}
    assert "password" not in resp.text


def test_connect_email_explicit_provider() -> None:
    client = _client()

    resp = client.post(
        "/auth/email",
        json={"email": "alice@custom.example", "password": "x", "provider": "yahoo"},
    )

    assert resp.status_code == 200
    assert resp.json()["provider"] == "yahoo"


def test_connect_email_unknown_explicit_provider_maps_to_500() -> None:
    client = _client()

    resp = client.post(
        "/auth/email",
        json={"email": "alice@custom.example", "password": "x", "provider": "not-a-provider"},
    )

    assert resp.status_code == 500
    assert resp.json()["error"]["type"] == "ConfigError"


def test_connect_email_unknown_domain_maps_to_502() -> None:
    client = _client()

    resp = client.post(
        "/auth/email", json={"email": "alice@totally-unknown-domain.zzz", "password": "x"}
    )

    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "EmailError"
