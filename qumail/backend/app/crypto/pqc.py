"""Level 3 — Post-Quantum Cryptography (ML-KEM-768 + ML-DSA-65).

Uses liboqs-python for NIST FIPS 203 (ML-KEM) key encapsulation and
FIPS 204 (ML-DSA) digital signatures.  The shared secret from ML-KEM is
fed through HKDF-SHA256 to derive an AES-256-GCM key.

If liboqs-python is not installed, all functions raise ``ConfigError``
with an install hint rather than silently degrading.

No key material is ever logged.
"""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING

from core.exceptions import (
    ConfigError,
    DecryptionError,
    EncryptionError,
    SignatureVerificationError,
)
from core.models import CryptoMetadata, EncryptedMessage, SecurityLevel

from backend.app.crypto.kdf import hkdf_sha256

if TYPE_CHECKING:
    import oqs  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# liboqs availability check
# ---------------------------------------------------------------------------

_OQS_AVAILABLE = False

try:
    import oqs  # type: ignore[import-untyped]

    _OQS_AVAILABLE = True
except ImportError:
    pass

_INSTALL_HINT = (
    "liboqs-python is required for PQC (Level 3). "
    "Install via: pip install liboqs-python"
)

# Derivation parameters for the AES key from the KEM shared secret.
_SALT = b"QUMAIL-PQC"
_INFO = b"ml-kem-768-aes-256-gcm"
_KEY_LEN = 32
_IV_LEN = 12


def _require_oqs() -> None:
    """Raise ``ConfigError`` if liboqs is not importable."""
    if not _OQS_AVAILABLE:
        raise ConfigError(_INSTALL_HINT)


# ---------------------------------------------------------------------------
# Key generation helpers
# ---------------------------------------------------------------------------


def generate_kem_keypair() -> tuple[bytes, bytes]:
    """Generate an ML-KEM-768 key pair.

    Returns:
        A ``(public_key, secret_key)`` tuple of raw bytes.

    Raises:
        ConfigError: If liboqs-python is not installed.
    """
    _require_oqs()
    kem = oqs.KeyEncapsulation("ML-KEM-768")
    public_key = kem.generate_keypair()
    secret_key = kem.export_secret_key()
    return public_key, secret_key


def generate_sig_keypair() -> tuple[bytes, bytes]:
    """Generate an ML-DSA-65 signing key pair.

    Returns:
        A ``(public_key, secret_key)`` tuple of raw bytes.

    Raises:
        ConfigError: If liboqs-python is not installed.
    """
    _require_oqs()
    sig = oqs.Signature("ML-DSA-65")
    public_key = sig.generate_keypair()
    secret_key = sig.export_secret_key()
    return public_key, secret_key


# ---------------------------------------------------------------------------
# Encrypt / Decrypt
# ---------------------------------------------------------------------------


def encrypt(
    plaintext: bytes,
    recipient_kem_pk: bytes,
    sender_sig_sk: bytes,
) -> EncryptedMessage:
    """Encrypt *plaintext* using ML-KEM-768 encapsulation + AES-256-GCM, then
    sign the ciphertext with ML-DSA-65.

    Args:
        plaintext: Raw payload bytes.
        recipient_kem_pk: Recipient's ML-KEM-768 public key.
        sender_sig_sk: Sender's ML-DSA-65 secret key for signing.

    Returns:
        An :class:`EncryptedMessage` with ciphertext and metadata containing
        the KEM ciphertext, IV, GCM tag, and signature (all base64).

    Raises:
        ConfigError: If liboqs-python is not installed.
        EncryptionError: If the PQC encryption pipeline fails.
    """
    _require_oqs()

    try:
        # 1) ML-KEM-768 encapsulation → (ct_kem, shared_secret)
        kem = oqs.KeyEncapsulation("ML-KEM-768")
        ct_kem, shared_secret = kem.encap_secret(recipient_kem_pk)

        # 2) Derive AES-256 key from the shared secret
        aes_key = hkdf_sha256(
            ikm=shared_secret, salt=_SALT, info=_INFO, length=_KEY_LEN
        )

        # 3) AES-256-GCM encrypt with a fresh random IV
        iv = os.urandom(_IV_LEN)
        from Crypto.Cipher import AES

        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        # 4) ML-DSA-65 sign the AES ciphertext
        sig = oqs.Signature("ML-DSA-65", secret_key=sender_sig_sk)
        signature = sig.sign(ciphertext)

        # 5) Build metadata (all binary values base64-encoded)
        metadata = CryptoMetadata(
            algorithm="ML-KEM-768+ML-DSA-65",
            ct_kem=base64.b64encode(ct_kem).decode("ascii"),
            iv=base64.b64encode(iv).decode("ascii"),
            tag=base64.b64encode(tag).decode("ascii"),
            signature=base64.b64encode(signature).decode("ascii"),
        )

        return EncryptedMessage(
            ciphertext=ciphertext,
            metadata=metadata.model_dump(exclude_none=True),
            level=SecurityLevel.PQC,
        )
    except (ConfigError, EncryptionError):
        raise
    except Exception as exc:
        raise EncryptionError(f"PQC encryption failed: {exc}") from exc


def decrypt(
    message: EncryptedMessage,
    recipient_kem_sk: bytes,
    sender_sig_pk: bytes,
) -> bytes:
    """Decrypt a PQC :class:`EncryptedMessage` and verify its signature.

    Args:
        message: The encrypted message with PQC metadata.
        recipient_kem_sk: Recipient's ML-KEM-768 secret key.
        sender_sig_pk: Sender's ML-DSA-65 public key.

    Returns:
        Recovered plaintext bytes.

    Raises:
        ConfigError: If liboqs-python is not installed.
        SignatureVerificationError: If the ML-DSA-65 signature is invalid.
        DecryptionError: On KEM decapsulation failure, missing metadata,
            or GCM tag verification failure.
    """
    _require_oqs()

    meta = message.metadata

    # --- Decode metadata fields ---
    try:
        ct_kem = base64.b64decode(meta["ct_kem"])
        iv = base64.b64decode(meta["iv"])
        tag = base64.b64decode(meta["tag"])
        signature = base64.b64decode(meta["signature"])
    except (KeyError, ValueError) as exc:
        raise DecryptionError(
            f"Missing or invalid PQC metadata field: {exc}"
        ) from exc

    try:
        # 1) Verify signature FIRST (fail fast on tampering)
        sig = oqs.Signature("ML-DSA-65")
        is_valid = sig.verify(message.ciphertext, signature, sender_sig_pk)
        if not is_valid:
            raise SignatureVerificationError(
                "ML-DSA-65 signature verification failed: "
                "ciphertext may have been tampered with."
            )

        # 2) ML-KEM-768 decapsulation → shared_secret
        kem = oqs.KeyEncapsulation("ML-KEM-768", secret_key=recipient_kem_sk)
        shared_secret = kem.decap_secret(ct_kem)

        # 3) Derive AES key
        aes_key = hkdf_sha256(
            ikm=shared_secret, salt=_SALT, info=_INFO, length=_KEY_LEN
        )

        # 4) AES-256-GCM decrypt + verify tag
        from Crypto.Cipher import AES

        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        plaintext = cipher.decrypt_and_verify(message.ciphertext, tag)

    except (SignatureVerificationError, DecryptionError, ConfigError):
        raise
    except ValueError as exc:
        raise DecryptionError(
            f"PQC decryption / GCM tag verification failed: {exc}"
        ) from exc
    except Exception as exc:
        raise DecryptionError(f"PQC decryption failed: {exc}") from exc

    return plaintext
