"""Typed exception hierarchy for QuMail.

Every module raises exceptions defined here instead of ad-hoc ones so the
API layer (backend/app/api/) can map them to HTTP status codes in a single
place. All exceptions inherit from :class:`QuMailError`.

Never include secret material (key bytes, passwords) in exception messages —
reference key IDs only.
"""

from __future__ import annotations


class QuMailError(Exception):
    """Base class for all QuMail-specific errors."""


# --------------------------------------------------------------------------- #
# Key Manager (M4 client / M6 simulator)
# --------------------------------------------------------------------------- #


class KMError(QuMailError):
    """Base class for Key Manager related errors."""


class KMConnectionError(KMError):
    """Raised when the ETSI 014 Key Manager cannot be reached.

    Typically wraps a transport-level error (timeout, refused connection).
    """


class KMResponseError(KMError):
    """Raised when the KM responds with an error or a malformed ETSI 014 body."""


# --------------------------------------------------------------------------- #
# Key Store (M7)
# --------------------------------------------------------------------------- #


class KeyStoreError(QuMailError):
    """Base class for local key store errors."""


class KeyNotFoundError(KeyStoreError):
    """Raised when a requested ``key_ID`` is not present in the key store."""


class KeyExhaustedError(KeyStoreError):
    """Raised when the KM has no more key material to serve."""


class KeyAlreadyConsumedError(KeyStoreError):
    """Raised on any attempt to reuse an OTP key that was already consumed.

    OTP keys are strictly single-use (CLAUDE.md constraint #2); the key store
    enforces this and callers must treat the error as fatal for the operation.
    """


# --------------------------------------------------------------------------- #
# Crypto Engine (M3)
# --------------------------------------------------------------------------- #


class CryptoError(QuMailError):
    """Base class for encryption/decryption errors."""


class EncryptionError(CryptoError):
    """Raised when encryption fails (e.g., OTP key shorter than plaintext)."""


class DecryptionError(CryptoError):
    """Raised when decryption fails (bad key, corrupted ciphertext, bad tag)."""


class SignatureVerificationError(CryptoError):
    """Raised when an ML-DSA signature does not verify (Level 3 only)."""


class UnsupportedSecurityLevelError(CryptoError):
    """Raised when a message specifies a security level the engine cannot handle."""


# --------------------------------------------------------------------------- #
# Email Service (M5)
# --------------------------------------------------------------------------- #


class EmailError(QuMailError):
    """Base class for SMTP/IMAP/MIME errors."""


class EmailSendError(EmailError):
    """Raised when SMTP submission fails."""


class EmailFetchError(EmailError):
    """Raised when IMAP fetch/list fails."""


class MimeFormatError(EmailError):
    """Raised when a ``.qenc`` MIME message cannot be built or parsed."""


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


class ConfigError(QuMailError):
    """Raised when required configuration (.env) is missing or invalid."""
