"""Placeholder tests for M2a ReceiveService (stub only — logic tests come later)."""

import inspect
from unittest.mock import create_autospec

import pytest

from backend.app.services import receive_service
from backend.app.services.receive_service import ReceiveService
from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient


def _make_service() -> ReceiveService:
    return ReceiveService(
        km_client=create_autospec(IKMClient, instance=True),
        crypto_engine=create_autospec(ICryptoEngine, instance=True),
        email_service=create_autospec(IEmailService, instance=True),
        key_store=create_autospec(IKeyStore, instance=True),
    )


def test_stub_constructs_and_fetch_is_not_implemented_yet() -> None:
    svc = _make_service()
    with pytest.raises(NotImplementedError):
        svc.fetch_and_decrypt(master_sae_id="SAE-A")


def test_services_layer_has_no_fastapi_imports() -> None:
    """M2a rule: orchestration must stay free of HTTP-framework concerns."""
    assert "fastapi" not in inspect.getsource(receive_service)
