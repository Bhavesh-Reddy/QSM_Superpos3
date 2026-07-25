"""CryptoEngine — unified facade for all four QuMail security levels.

Implements :class:`core.interfaces.ICryptoEngine` by dispatching to the
level-specific submodules (``otp``, ``quantum_aes``, ``pqc``).

Usage::

    engine = CryptoEngine(sender_signing_key=my_dsa_sk)

    # Encrypt at Level 2 (Quantum-AES)
    enc_msg = engine.encrypt(payload, SecurityLevel.QUANTUM_AES, key=qkd_key)

    # Decrypt
    plaintext = engine.decrypt(enc_msg, key=qkd_key)
"""

from __future__ import annotations

import logging
from typing import Any

from backend.app.crypto import otp, pqc, quantum_aes
from core.exceptions import (
    DecryptionError,
    EncryptionError,
    UnsupportedSecurityLevelError,
)
from core.interfaces import ICryptoEngine
from core.models import (
    CryptoMetadata,
    EncryptedMessage,
    QKDKey,
    SecurityLevel,
)

logger = logging.getLogger(__name__)


class CryptoEngine(ICryptoEngine):
    """Facade dispatching encrypt / decrypt to the correct sub-module.

    For PQC (Level 3), the sender's ML-DSA signing key is needed on
    ``encrypt`` and the sender's ML-DSA public key is needed on
    ``decrypt``.  Since the :class:`ICryptoEngine` ABC does not carry
    those parameters, they are stored as instance attributes set at
    construction time.

    Args:
        sender_signing_key: ML-DSA-65 secret key for signing ciphertext
            during Level 3 encryption.  May be ``None`` if Level 3 is
            not used.
    """

    def __init__(
        self,
        sender_signing_key: bytes | None = None,
    ) -> None:
        self._sender_signing_key = sender_signing_key

    # ------------------------------------------------------------------ #
    # Encrypt
    # ------------------------------------------------------------------ #

    def encrypt(
        self,
        plaintext: bytes,
        level: SecurityLevel,
        key: QKDKey | None = None,
        recipient_public_key: bytes | None = None,
    ) -> EncryptedMessage:
        """Encrypt *plaintext* at the requested security level.

        Args:
            plaintext: Raw payload bytes (body or attachment).
            level: Security level to apply.
            key: Quantum key from the key store (required for levels 1–2).
            recipient_public_key: ML-KEM-768 public key (required for
                level 3).

        Returns:
            The ciphertext plus metadata needed for decryption.

        Raises:
            EncryptionError: If inputs are invalid for the level.
            UnsupportedSecurityLevelError: If *level* is unknown.
        """
        if level == SecurityLevel.OTP:
            return self._encrypt_otp(plaintext, key)
        elif level == SecurityLevel.QUANTUM_AES:
            return self._encrypt_aes(plaintext, key)
        elif level == SecurityLevel.PQC:
            return self._encrypt_pqc(plaintext, recipient_public_key)
        elif level == SecurityLevel.NONE:
            return self._encrypt_none(plaintext)
        else:
            raise UnsupportedSecurityLevelError(
                f"Unknown security level: {level}"
            )

    # ------------------------------------------------------------------ #
    # Decrypt
    # ------------------------------------------------------------------ #

    def decrypt(
        self,
        message: EncryptedMessage,
        key: QKDKey | None = None,
        private_key: bytes | None = None,
        sender_public_key: bytes | None = None,
    ) -> bytes:
        """Decrypt an :class:`EncryptedMessage` back to plaintext.

        Args:
            message: Ciphertext and metadata as received.
            key: Quantum key matching ``metadata.key_id`` (levels 1–2).
            private_key: Recipient's ML-KEM-768 secret key (level 3).
            sender_public_key: Sender's ML-DSA-65 public key for
                signature verification (level 3).

        Returns:
            The recovered plaintext bytes.

        Raises:
            DecryptionError: On bad key, corrupted ciphertext, or GCM tag
                failure.
            SignatureVerificationError: If the level 3 signature is
                invalid.
        """
        level = message.level

        if level == SecurityLevel.OTP:
            return self._decrypt_otp(message, key)
        elif level == SecurityLevel.QUANTUM_AES:
            return self._decrypt_aes(message, key)
        elif level == SecurityLevel.PQC:
            return self._decrypt_pqc(message, private_key, sender_public_key)
        elif level == SecurityLevel.NONE:
            return message.ciphertext
        else:
            raise UnsupportedSecurityLevelError(
                f"Unknown security level in message: {level}"
            )

    # ------------------------------------------------------------------ #
    # Level 1 — OTP
    # ------------------------------------------------------------------ #

    @staticmethod
    def _encrypt_otp(
        plaintext: bytes, key: QKDKey | None
    ) -> EncryptedMessage:
        if key is None:
            raise EncryptionError(
                "OTP (Level 1) requires a quantum key."
            )
        ct = otp.encrypt(plaintext, key.key)
        metadata = CryptoMetadata(
            algorithm="OTP",
            key_id=key.key_id,
            plaintext_length=len(plaintext),
        )
        logger.info("OTP encrypt: key_id=%s, len=%d", key.key_id, len(plaintext))
        return EncryptedMessage(
            ciphertext=ct,
            metadata=metadata.model_dump(exclude_none=True),
            level=SecurityLevel.OTP,
        )

    @staticmethod
    def _decrypt_otp(message: EncryptedMessage, key: QKDKey | None) -> bytes:
        if key is None:
            raise DecryptionError(
                "OTP (Level 1) requires a quantum key for decryption."
            )
        logger.info("OTP decrypt: key_id=%s", key.key_id)
        return otp.decrypt(message.ciphertext, key.key)

    # ------------------------------------------------------------------ #
    # Level 2 — Quantum-AES
    # ------------------------------------------------------------------ #

    @staticmethod
    def _encrypt_aes(
        plaintext: bytes, key: QKDKey | None
    ) -> EncryptedMessage:
        if key is None:
            raise EncryptionError(
                "Quantum-AES (Level 2) requires a quantum key."
            )
        logger.info(
            "AES-256-GCM encrypt: key_id=%s, len=%d",
            key.key_id,
            len(plaintext),
        )
        return quantum_aes.encrypt(plaintext, key.key, key.key_id)

    @staticmethod
    def _decrypt_aes(
        message: EncryptedMessage, key: QKDKey | None
    ) -> bytes:
        if key is None:
            raise DecryptionError(
                "Quantum-AES (Level 2) requires a quantum key for decryption."
            )
        logger.info("AES-256-GCM decrypt: key_id=%s", key.key_id)
        return quantum_aes.decrypt(message, key.key)

    # ------------------------------------------------------------------ #
    # Level 3 — PQC
    # ------------------------------------------------------------------ #

    def _encrypt_pqc(
        self, plaintext: bytes, recipient_pk: bytes | None
    ) -> EncryptedMessage:
        if recipient_pk is None:
            raise EncryptionError(
                "PQC (Level 3) requires the recipient's ML-KEM-768 public key."
            )
        if self._sender_signing_key is None:
            raise EncryptionError(
                "PQC (Level 3) requires a sender signing key.  "
                "Pass sender_signing_key= to CryptoEngine()."
            )
        logger.info("PQC encrypt: len=%d", len(plaintext))
        return pqc.encrypt(plaintext, recipient_pk, self._sender_signing_key)

    @staticmethod
    def _decrypt_pqc(
        message: EncryptedMessage,
        private_key: bytes | None,
        sender_public_key: bytes | None,
    ) -> bytes:
        if private_key is None:
            raise DecryptionError(
                "PQC (Level 3) requires the recipient's ML-KEM-768 secret key."
            )
        if sender_public_key is None:
            raise DecryptionError(
                "PQC (Level 3) requires the sender's ML-DSA-65 public key "
                "for signature verification."
            )
        logger.info("PQC decrypt")
        return pqc.decrypt(message, private_key, sender_public_key)

    # ------------------------------------------------------------------ #
    # Level 4 — None (passthrough)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _encrypt_none(plaintext: bytes) -> EncryptedMessage:
        metadata = CryptoMetadata(algorithm="NONE")
        return EncryptedMessage(
            ciphertext=plaintext,
            metadata=metadata.model_dump(exclude_none=True),
            level=SecurityLevel.NONE,
        )
