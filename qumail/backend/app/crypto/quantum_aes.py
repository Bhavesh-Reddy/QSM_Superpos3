"""Level 2 — Quantum-aided AES-256-GCM.

The quantum key from the Key Manager is not used directly.  Instead an
AES-256 key is derived via HKDF-SHA256, giving key-separation even when
the same quantum key were (hypothetically) used for two messages — though
the KeyStore should prevent that.

A fresh random 12-byte IV is generated for every call.  IV, GCM tag, and
key ID are stored in metadata (base64); ciphertext is returned raw.

No key material is ever logged.
"""

from __future__ import annotations

import base64
import os

from Crypto.Cipher import AES

from backend.app.crypto.kdf import hkdf_sha256
from core.exceptions import DecryptionError, EncryptionError
from core.models import CryptoMetadata, EncryptedMessage, SecurityLevel

# Fixed derivation parameters (must match on encrypt and decrypt).
_SALT = b"QUMAIL-AES"
_INFO = b"aes-256-gcm"
_KEY_LEN = 32  # 256 bits
_IV_LEN = 12   # GCM recommended nonce size


def _derive_aes_key(quantum_key: bytes) -> bytes:
    """Derive a 256-bit AES key from a quantum key via HKDF-SHA256."""
    return hkdf_sha256(ikm=quantum_key, salt=_SALT, info=_INFO, length=_KEY_LEN)


def encrypt(plaintext: bytes, quantum_key: bytes, key_id: str) -> EncryptedMessage:
    """Encrypt *plaintext* with AES-256-GCM using a quantum-derived key.

    Args:
        plaintext: Raw payload bytes.
        quantum_key: Raw quantum key bytes from the Key Manager.
        key_id: KM-assigned key ID (stored in metadata, never the key itself).

    Returns:
        An :class:`EncryptedMessage` with ciphertext and metadata containing
        the IV, GCM tag, key ID, and algorithm identifier (all base64 where
        binary).

    Raises:
        EncryptionError: If AES encryption fails for any reason.
    """
    try:
        aes_key = _derive_aes_key(quantum_key)
        iv = os.urandom(_IV_LEN)

        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        metadata = CryptoMetadata(
            algorithm="AES-256-GCM",
            key_id=key_id,
            iv=base64.b64encode(iv).decode("ascii"),
            tag=base64.b64encode(tag).decode("ascii"),
        )

        return EncryptedMessage(
            ciphertext=ciphertext,
            metadata=metadata.model_dump(exclude_none=True),
            level=SecurityLevel.QUANTUM_AES,
        )
    except EncryptionError:
        raise
    except Exception as exc:
        raise EncryptionError(f"AES-256-GCM encryption failed: {exc}") from exc


def decrypt(message: EncryptedMessage, quantum_key: bytes) -> bytes:
    """Decrypt an AES-256-GCM :class:`EncryptedMessage`.

    Args:
        message: The encrypted message (ciphertext + metadata with IV/tag).
        quantum_key: Raw quantum key bytes matching the one used to encrypt.

    Returns:
        Recovered plaintext bytes.

    Raises:
        DecryptionError: On missing metadata fields, GCM tag verification
            failure, or any other decryption error.
    """
    meta = message.metadata

    try:
        iv = base64.b64decode(meta["iv"])
        tag = base64.b64decode(meta["tag"])
    except (KeyError, ValueError) as exc:
        raise DecryptionError(
            f"Missing or invalid AES-GCM metadata (iv/tag): {exc}"
        ) from exc

    try:
        aes_key = _derive_aes_key(quantum_key)
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        plaintext = cipher.decrypt_and_verify(message.ciphertext, tag)
    except ValueError as exc:
        # PyCryptodome raises ValueError on GCM tag mismatch.
        raise DecryptionError(
            f"AES-256-GCM decryption/tag verification failed: {exc}"
        ) from exc
    except Exception as exc:
        raise DecryptionError(
            f"AES-256-GCM decryption failed: {exc}"
        ) from exc

    return plaintext
