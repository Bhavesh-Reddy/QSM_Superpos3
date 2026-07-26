"""End-to-end startup smoke test — the one test that runs the *real*
lifespan (real Settings, real CryptoEngine, real KeyStore) instead of
mocking it out, to prove the wiring in backend/main.py actually holds
together. Everything else in tests/test_api_*.py mocks the services layer.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.deps import AppState
from backend.app.config import get_settings
from backend.app.crypto.engine import CryptoEngine
from backend.app.keystore.store import KeyStore
from backend.main import create_app


def test_real_lifespan_builds_app_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KEYSTORE_MASTER_PASSWORD", "test-only-password")
    monkeypatch.setenv("KEYSTORE_PATH", str(tmp_path / "keystore.json"))
    get_settings.cache_clear()
    try:
        app = create_app()
        with TestClient(app) as client:
            state: AppState = app.state.qumail
            assert isinstance(state.crypto, CryptoEngine)
            assert isinstance(state.store, KeyStore)
            assert state.km is None
            assert state.mail is None

            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # Neither KM nor email connected yet -> ConfigError -> 500.
            resp = client.get("/keys/status")
            assert resp.status_code == 500
            assert resp.json()["error"]["type"] == "ConfigError"
    finally:
        get_settings.cache_clear()
