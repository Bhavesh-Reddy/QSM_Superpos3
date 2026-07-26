"""QuMail backend entrypoint (M2b) — FastAPI app factory + uvicorn runner.

Wires the M2b routers over the M2a services, builds the process-wide
:class:`~backend.app.api.deps.AppState` (crypto engine + key store) at
startup, and registers the one typed-exception -> HTTP-status mapping used
across the whole API. Routers themselves stay free of this mapping logic.

Run: ``python -m backend.main`` (serves on http://127.0.0.1:8000 by default)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.exceptions import (
    ConfigError,
    CryptoError,
    DecryptionError,
    EmailError,
    EncryptionError,
    KeyAlreadyConsumedError,
    KeyExhaustedError,
    KeyNotFoundError,
    KeyStoreError,
    KMConnectionError,
    KMError,
    KMResponseError,
    QuMailError,
    SignatureVerificationError,
    UnsupportedSecurityLevelError,
)

from backend.app.api import routes_auth, routes_keys, routes_mail
from backend.app.api.deps import AppState
from backend.app.config import get_settings
from backend.app.crypto.engine import CryptoEngine
from backend.app.keystore.store import KeyStore

logger = logging.getLogger(__name__)

# Dev-tooling CORS origins (Vite dev server + Electron renderer), same
# convention as km_simulator/main.py. Not secret, so no need to route this
# through Settings — keeping it here lets the app be constructed (and
# imported for tests) without requiring any environment configuration.
_CORS_ORIGINS = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Ordered most-specific-first: the first matching (isinstance) entry wins,
# so subclasses must be listed before their base class.
_EXCEPTION_STATUS: list[tuple[type[QuMailError], int]] = [
    (KeyNotFoundError, 404),
    (KeyExhaustedError, 409),
    (KeyAlreadyConsumedError, 409),
    (KeyStoreError, 409),
    (DecryptionError, 400),
    (SignatureVerificationError, 400),
    (EncryptionError, 422),
    (UnsupportedSecurityLevelError, 422),
    (CryptoError, 422),
    (KMConnectionError, 502),
    (KMResponseError, 502),
    (KMError, 502),
    (EmailError, 502),
    (ConfigError, 500),
    (QuMailError, 500),
]


def _status_for(exc: QuMailError) -> int:
    """Map a typed QuMail exception to its HTTP status code."""
    for exc_type, status_code in _EXCEPTION_STATUS:
        if isinstance(exc, exc_type):
            return status_code
    return 500  # pragma: no cover - unreachable, QuMailError is the catch-all


def _qumail_error_handler(request: Request, exc: QuMailError) -> JSONResponse:
    """Render any :class:`QuMailError` as ``{"error": {type, message}}``.

    Registered once for the whole app instead of per-router, per CLAUDE.md's
    "routers delegate only" rule. Never includes secret material — exception
    messages are already written to exclude key bytes/passwords.
    """
    status_code = _status_for(exc)
    logger.warning("%s -> %d: %s", type(exc).__name__, status_code, exc)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"type": type(exc).__name__, "message": str(exc)}},
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the crypto engine + key store once and stash them on app.state.

    ``km`` and ``mail`` start unset; ``POST /auth/km`` / ``POST /auth/email``
    populate them per session (see ``backend/app/api/deps.py``).
    """
    settings = get_settings()
    crypto = CryptoEngine()
    store = KeyStore(settings.keystore_path, settings.keystore_master_password)
    app.state.qumail = AppState(crypto=crypto, store=store)
    logger.info(
        "QuMail backend ready: default sae_id=%s default km_base_url=%s",
        settings.sae_id,
        settings.km_base_url,
    )
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application (routers + CORS + exception mapping)."""
    app = FastAPI(
        title="QuMail Backend",
        description="Quantum-secure email client backend — M2b HTTP surface.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_auth.router)
    app.include_router(routes_mail.router)
    app.include_router(routes_keys.router)

    app.add_exception_handler(QuMailError, _qumail_error_handler)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok", "version": app.version}

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
