"""Placeholder tests for M2a SendService (stub only — logic tests come later)."""

import inspect
from unittest.mock import create_autospec

import pytest

from backend.app.services import send_service
from backend.app.services.send_service import SendService
from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient
from core.models import EmailMessage, SecurityLevel


def _make_service() -> SendService:
    return SendService(
        km_client=create_autospec(IKMClient, instance=True),
        crypto_engine=create_autospec(ICryptoEngine, instance=True),
        email_service=create_autospec(IEmailService, instance=True),
        key_store=create_autospec(IKeyStore, instance=True),
    )


def test_stub_constructs_and_send_is_not_implemented_yet() -> None:
    svc = _make_service()
    msg = EmailMessage(sender="a@x.com", recipient="b@x.com", body="hi")
    with pytest.raises(NotImplementedError):
        svc.send_encrypted_email(msg, SecurityLevel.OTP, slave_sae_id="SAE-B")


def test_services_layer_has_no_fastapi_imports() -> None:
    """M2a rule: orchestration must stay free of HTTP-framework concerns."""
    assert "fastapi" not in inspect.getsource(send_service)
