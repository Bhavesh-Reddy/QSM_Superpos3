"""Level 1 — Quantum One-Time Pad (XOR cipher).

The OTP is information-theoretically secure *if and only if* the key is
at least as long as the plaintext and is never reused.  Key-reuse
enforcement lives in the KeyStore (M7); this module enforces the length
invariant.

No key material is ever logged.
"""

from __future__ import annotations

from core.exceptions import DecryptionError, EncryptionError


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """XOR *plaintext* with *key* to produce ciphertext.

    Args:
        plaintext: Raw message bytes.
        key: Quantum key bytes.  Must be ``>= len(plaintext)``.

    Returns:
        Ciphertext of the same length as *plaintext*.

    Raises:
        EncryptionError: If the key is shorter than the plaintext.
    """
    if len(key) < len(plaintext):
        raise EncryptionError(
            f"OTP key too short: key has {len(key)} bytes but plaintext "
            f"has {len(plaintext)} bytes.  Key must be >= plaintext length."
        )

    return bytes(p ^ k for p, k in zip(plaintext, key))


def decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """XOR *ciphertext* with *key* to recover the plaintext.

    Args:
        ciphertext: Previously encrypted bytes.
        key: The same quantum key used for encryption.  Must be
            ``>= len(ciphertext)``.

    Returns:
        Recovered plaintext bytes.

    Raises:
        DecryptionError: If the key is shorter than the ciphertext.
    """
    if len(key) < len(ciphertext):
        raise DecryptionError(
            f"OTP key too short for decryption: key has {len(key)} bytes "
            f"but ciphertext has {len(ciphertext)} bytes."
        )

    return bytes(c ^ k for c, k in zip(ciphertext, key))
