"""M7 — Secure Key Store.

Encrypted-at-rest cache of quantum keys that enforces OTP single-use. Public
class: :class:`~backend.app.keystore.store.KeyStore`.
"""

from backend.app.keystore.store import KeyStore

__all__ = ["KeyStore"]
