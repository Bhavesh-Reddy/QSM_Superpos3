"""HKDF-SHA256 key derivation helper.

Wraps PyCryptodome's HKDF so every crypto submodule uses the same
derivation logic with consistent parameter validation.

Never logs or stores intermediate key material.
"""

from __future__ import annotations

from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF


def hkdf_sha256(
    ikm: bytes,
    salt: bytes,
    info: bytes,
    length: int,
) -> bytes:
    """Derive a key from *ikm* using HKDF-SHA256 (RFC 5869).

    Args:
        ikm: Input keying material (e.g. a quantum key or KEM shared secret).
        salt: Non-secret salt.  May be empty but should not be for production.
        info: Context / application-specific info string.
        length: Desired output length in bytes (1–255 × hash-len).

    Returns:
        Derived key of the requested *length*.

    Raises:
        ValueError: If *ikm* is empty or *length* is not positive.
    """
    if not ikm:
        raise ValueError("ikm must be non-empty")
    if length <= 0:
        raise ValueError("length must be positive")

    # PyCryptodome HKDF signature (all positional):
    #   HKDF(master, key_len, salt, hashmod, num_keys=1, context=None)
    # With num_keys=1 it returns a single bytes object.
    derived = HKDF(
        ikm,                                    # master
        length,                                 # key_len
        salt if salt else b"\x00" * 32,         # salt (empty → 32 zero bytes)
        SHA256,                                 # hashmod
        1,                                      # num_keys
        info,                                   # context
    )
    if isinstance(derived, tuple):
        return derived[0]
    return derived
