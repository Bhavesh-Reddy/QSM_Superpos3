"""Dependency-injection plumbing for the M2b HTTP surface.

Holds the process-wide :class:`AppState` (built once at startup by
``backend/main.py``'s lifespan) and the small ``Depends`` provider chain
routers use to reach it. No routing, no request/response schemas, no
business logic — just wiring, per CLAUDE.md's "routers delegate only" rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from core.exceptions import ConfigError
from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient

from backend.app.services import ReceiveService, SendService


@dataclass
class AppState:
    """Session-scoped backend state, held on ``app.state.qumail``.

    ``crypto`` and ``store`` are built once at startup. ``km`` and ``mail``
    start unset and are populated by ``POST /auth/km`` / ``POST /auth/email``
    — this is a single-user desktop app talking to a backend it spawns
    locally, so one implicit server-side session is enough (no auth tokens).

    Attributes:
        crypto: The crypto engine singleton.
        store: The encrypted key store singleton.
        km: The connected KM client, once ``/auth/km`` succeeds.
        mail: The connected email service, once ``/auth/email`` succeeds.
    """

    crypto: ICryptoEngine
    store: IKeyStore
    km: IKMClient | None = None
    mail: IEmailService | None = None


def get_app_state(request: Request) -> AppState:
    """Fetch the :class:`AppState` set up in ``backend/main.py``'s lifespan."""
    return request.app.state.qumail


def get_crypto_engine(state: AppState = Depends(get_app_state)) -> ICryptoEngine:
    """Provide the shared crypto engine."""
    return state.crypto


def get_key_store(state: AppState = Depends(get_app_state)) -> IKeyStore:
    """Provide the shared key store."""
    return state.store


def get_km_client(state: AppState = Depends(get_app_state)) -> IKMClient:
    """Provide the connected KM client.

    Raises:
        ConfigError: If ``POST /auth/km`` has not been called yet.
    """
    if state.km is None:
        raise ConfigError("KM not connected; call POST /auth/km first")
    return state.km


def get_mail_service(state: AppState = Depends(get_app_state)) -> IEmailService:
    """Provide the connected email service.

    Raises:
        ConfigError: If ``POST /auth/email`` has not been called yet.
    """
    if state.mail is None:
        raise ConfigError("Email not connected; call POST /auth/email first")
    return state.mail


def get_send_service(
    crypto: ICryptoEngine = Depends(get_crypto_engine),
    km: IKMClient = Depends(get_km_client),
    mail: IEmailService = Depends(get_mail_service),
    store: IKeyStore = Depends(get_key_store),
) -> SendService:
    """Build a request-scoped :class:`SendService` over the current session."""
    return SendService(crypto=crypto, km=km, mail=mail, store=store)


def get_receive_service(
    crypto: ICryptoEngine = Depends(get_crypto_engine),
    km: IKMClient = Depends(get_km_client),
    mail: IEmailService = Depends(get_mail_service),
    store: IKeyStore = Depends(get_key_store),
) -> ReceiveService:
    """Build a request-scoped :class:`ReceiveService` over the current session."""
    return ReceiveService(crypto=crypto, km=km, mail=mail, store=store)
