"""Abstract interfaces (ABCs) for every QuMail module.

Cross-module calls go through these contracts only (CLAUDE.md constraint #4):
define/update the interface here *before* implementing a module. Concrete
implementations live in ``backend/app/<module>/`` and ``km_simulator/``.

Interfaces:
    ICryptoEngine: M3 — all four security levels behind one facade.
    IKMClient:     M4 — ETSI GS QKD 014 REST client.
    IEmailService: M5 — SMTP send / IMAP fetch of ``.qenc`` messages.
    IKeyStore:     M7 — encrypted-at-rest key cache with OTP one-time-use.
"""

from __future__ import annotations

import abc

from core.models import (
    EmailMessage,
    EncryptedMessage,
    ETSIStatus,
    QKDKey,
    SecurityLevel,
)


class ICryptoEngine(abc.ABC):
    """Encrypts/decrypts payloads at any of the four security levels (M3)."""

    @abc.abstractmethod
    def encrypt(
        self,
        plaintext: bytes,
        level: SecurityLevel,
        key: QKDKey | None = None,
        recipient_public_key: bytes | None = None,
    ) -> EncryptedMessage:
        """Encrypt ``plaintext`` at the requested security level.

        Args:
            plaintext: Raw payload bytes (body or attachment).
            level: Security level to apply.
            key: Quantum key from the key store (required for levels 1–2).
            recipient_public_key: ML-KEM-768 public key (required for level 3).

        Returns:
            The ciphertext plus metadata needed for decryption.

        Raises:
            EncryptionError: If inputs are invalid for the level
                (e.g., OTP key shorter than the plaintext).
            UnsupportedSecurityLevelError: If ``level`` is unknown.
        """

    @abc.abstractmethod
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
            sender_public_key: Sender's ML-DSA-65 public key for signature
                verification (level 3).

        Returns:
            The recovered plaintext bytes.

        Raises:
            DecryptionError: On bad key, corrupted ciphertext, or GCM tag failure.
            SignatureVerificationError: If the level-3 signature is invalid.
        """


class IKMClient(abc.ABC):
    """ETSI GS QKD 014 REST client toward the Key Manager (M4)."""

    @abc.abstractmethod
    def get_status(self, slave_sae_id: str) -> ETSIStatus:
        """Query key availability for a peer SAE.

        Maps to ``GET /api/v1/keys/{slave_SAE_ID}/status``.

        Args:
            slave_sae_id: SAE ID of the communication peer.

        Returns:
            The KM's status document.

        Raises:
            KMConnectionError: If the KM is unreachable.
            KMResponseError: If the response is not valid ETSI 014 JSON.
        """

    @abc.abstractmethod
    def get_key(
        self, slave_sae_id: str, number: int = 1, size: int = 256
    ) -> list[QKDKey]:
        """Request fresh keys for encrypting toward a peer.

        Maps to ``POST /api/v1/keys/{slave_SAE_ID}/enc_keys``.

        Args:
            slave_sae_id: SAE ID of the communication peer.
            number: How many keys to request.
            size: Key size in bits.

        Returns:
            Keys with KM-assigned ``key_id``s (base64 already decoded).

        Raises:
            KMConnectionError: If the KM is unreachable.
            KeyExhaustedError: If the KM has insufficient key material.
        """

    @abc.abstractmethod
    def get_key_with_ids(
        self, master_sae_id: str, key_ids: list[str]
    ) -> list[QKDKey]:
        """Fetch the keys matching IDs received from a peer.

        Maps to ``POST /api/v1/keys/{master_SAE_ID}/dec_keys``.

        Args:
            master_sae_id: SAE ID of the sender who requested the keys.
            key_ids: ``key_ID`` values from the message metadata.

        Returns:
            The matching keys.

        Raises:
            KMConnectionError: If the KM is unreachable.
            KMResponseError: If any requested ID is unknown to the KM.
        """


class IEmailService(abc.ABC):
    """SMTP send / IMAP fetch of QuMail messages (M5)."""

    @abc.abstractmethod
    def send(self, message: EmailMessage, encrypted: EncryptedMessage) -> str:
        """Pack an encrypted message as ``.qenc`` MIME and submit via SMTP.

        Args:
            message: Plaintext envelope (sender, recipient, subject).
            encrypted: Payload produced by the crypto engine.

        Returns:
            The provider-assigned Message-ID.

        Raises:
            EmailSendError: On SMTP failure.
            MimeFormatError: If the MIME message cannot be built.
        """

    @abc.abstractmethod
    def fetch(self, folder: str = "INBOX", limit: int = 20) -> list[EmailMessage]:
        """List recent messages from an IMAP folder (headers + parsed payloads).

        Args:
            folder: IMAP folder name.
            limit: Maximum number of messages to return, newest first.

        Returns:
            Parsed messages; encrypted ones still carry ciphertext until
            the caller decrypts them via the crypto engine.

        Raises:
            EmailFetchError: On IMAP failure.
        """


class IKeyStore(abc.ABC):
    """Encrypted-at-rest cache of quantum keys with OTP single-use rules (M7)."""

    @abc.abstractmethod
    def put(self, key: QKDKey) -> None:
        """Cache a key fetched from the KM.

        Args:
            key: The key to store; must have a unique ``key_id``.
        """

    @abc.abstractmethod
    def get(self, key_id: str) -> QKDKey:
        """Return a stored key without consuming it.

        Args:
            key_id: The KM-assigned key ID.

        Returns:
            The stored key.

        Raises:
            KeyNotFoundError: If ``key_id`` is not in the store.
        """

    @abc.abstractmethod
    def consume(self, key_id: str) -> QKDKey:
        """Atomically fetch a key and mark it consumed (OTP single-use).

        Args:
            key_id: The KM-assigned key ID.

        Returns:
            The key, now flagged as consumed.

        Raises:
            KeyNotFoundError: If ``key_id`` is not in the store.
            KeyAlreadyConsumedError: If the key was consumed before
                (CLAUDE.md constraint #2 — never reuse OTP keys).
        """