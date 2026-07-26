"""Runtime configuration for the QuMail backend (M2b support).

Loaded from the process environment / a ``.env`` file via
``pydantic-settings``. Nothing here talks to FastAPI, the KM, or email —
it is pure configuration, read once and cached.

Never log a ``Settings`` instance directly: ``keystore_master_password`` is
a secret (CLAUDE.md constraint #8, #3).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration.

    Attributes:
        km_base_url: Default ETSI 014 KM URL; overridable per-session via
            ``POST /auth/km``.
        sae_id: This client's own default SAE ID; overridable via
            ``POST /auth/km``.
        keystore_path: Path to the encrypted-at-rest key store file.
        keystore_master_password: Password used to derive the key store's
            storage key. Required — never given a hardcoded default.
        host: Bind host for uvicorn.
        port: Bind port for uvicorn.
    """

    km_base_url: str = "http://127.0.0.1:8100"
    sae_id: str = "SAE-ALICE"
    keystore_path: str = "keystore.json"
    keystore_master_password: str
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton (cached).

    Raises:
        pydantic_core.ValidationError: If a required setting (e.g.
            ``KEYSTORE_MASTER_PASSWORD``) is missing from the environment.
    """
    return Settings()
