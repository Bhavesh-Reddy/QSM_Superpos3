"""M2b — auth/connection routes.

Configures the per-session KM and email connections. No crypto, no KM
protocol details, no SMTP/IMAP calls beyond constructing the concrete
clients — everything else is delegated. Passwords are accepted here (there
is nowhere else for them to enter the system) but are never logged or
echoed back in a response.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.exceptions import ConfigError
from core.models import ETSIStatus

from backend.app.api.deps import AppState, get_app_state
from backend.app.email_svc import EmailAccount, EmailService
from backend.app.email_svc.sender import PROVIDER_PRESETS, detect_provider
from backend.app.km.client import KMClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class KMConnectRequest(BaseModel):
    """Body of ``POST /auth/km``."""

    base_url: str
    sae_id: str
    verify_tls: bool = True


class EmailConnectRequest(BaseModel):
    """Body of ``POST /auth/email``."""

    email: str
    password: str
    provider: str | None = None


class EmailConnectResponse(BaseModel):
    """Response of ``POST /auth/email`` — no password, ever."""

    connected: bool
    address: str
    provider: str


@router.post("/km", response_model=ETSIStatus)
def connect_km(payload: KMConnectRequest, state: AppState = Depends(get_app_state)) -> ETSIStatus:
    """Connect to an ETSI 014 Key Manager and return its status.

    Args:
        payload: KM base URL and this client's SAE ID.
        state: Shared app state, updated with the new client on success.

    Returns:
        The KM's status document.

    Raises:
        KMConnectionError: If the KM is unreachable.
        KMResponseError: If the KM's response is malformed.
    """
    km = KMClient(
        base_url=payload.base_url, sae_id=payload.sae_id, verify_tls=payload.verify_tls
    )
    status = km.get_status()
    state.km = km
    logger.info("KM connected: sae_id=%s base_url=%s", payload.sae_id, payload.base_url)
    return status


@router.post("/email", response_model=EmailConnectResponse)
def connect_email(
    payload: EmailConnectRequest, state: AppState = Depends(get_app_state)
) -> EmailConnectResponse:
    """Connect an SMTP/IMAP mailbox for sending and fetching.

    Args:
        payload: Mailbox address, app password, and optional explicit
            provider (skips domain auto-detection when given).
        state: Shared app state, updated with the new email service on
            success.

    Returns:
        Confirmation with the resolved address and provider — never the
        password.

    Raises:
        ConfigError: If an explicit ``provider`` is not one QuMail knows.
        EmailError: If the provider cannot be auto-detected from the domain.
    """
    # Gmail/Yahoo/Outlook app passwords are shown to users in spaced groups
    # ("abcd efgh ijkl mnop"); those spaces are display-only and must be
    # stripped or SMTP/IMAP login fails. App passwords never contain spaces.
    email_address = payload.email.strip()
    app_password = "".join(payload.password.split())

    if payload.provider is not None:
        preset = PROVIDER_PRESETS.get(payload.provider)
        if preset is None:
            raise ConfigError(f"unknown email provider '{payload.provider}'")
        account = EmailAccount(email_address, app_password, preset)
        provider_name = payload.provider
    else:
        account = EmailAccount.from_address(email_address, app_password)
        provider_name = detect_provider(email_address)

    state.mail = EmailService(account)
    logger.info("email connected: address=%s provider=%s", account.address, provider_name)
    return EmailConnectResponse(connected=True, address=account.address, provider=provider_name)
