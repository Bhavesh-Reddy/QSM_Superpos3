"""M3 Crypto Engine — encryption/decryption for all four QuMail security levels.

Submodules:
    kdf:          HKDF-SHA256 key derivation.
    otp:          Level 1 — quantum one-time pad (XOR).
    quantum_aes:  Level 2 — AES-256-GCM with HKDF-derived quantum key.
    pqc:          Level 3 — ML-KEM-768 + ML-DSA-65 + AES-256-GCM.
    engine:       Facade dispatching to the above based on SecurityLevel.
"""

from backend.app.crypto.engine import CryptoEngine

__all__ = ["CryptoEngine"]
