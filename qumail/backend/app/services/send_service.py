"""Send-side orchestration (M2a): key -> encrypt -> send.

Depends exclusively on ``core`` contracts (``core/interfaces.py``,
``core/models.py``, ``core/exceptions.py``). No FastAPI imports allowed here
— HTTP concerns live in ``backend/app/api/`` (M2b).
"""

from __future__ import annotations

import logging
from typing import Any

from core.exceptions import EncryptionError, UnsupportedSecurityLevelError
from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient
from core.models import EmailAttachment, EmailMessage, QKDKey, SecurityLevel

logger = logging.getLogger(__name__)

# AES-256-GCM only needs a well-mixed 256-bit input to HKDF; unlike OTP it
# does not need to scale with the plaintext length.
_QUANTUM_AES_KEY_BITS = 256

# Placeholder "From" identity: the real authenticated mailbox address is not
# yet wired in (that lands with M2b's config/auth layer). Overridable per
# call via send(..., sender=...) so callers aren't stuck with this default.
_DEFAULT_SENDER = "me@qumail.local"


class SendService:
    """Orchestrates outbound mail at a chosen security level.

    Pipeline:
        1. Levels 1-2: request a key from the KM (keyed by the recipient's
           SAE ID), cache it in the key store, encrypt, then — OTP only —
           mark the key consumed.
        2. Level 3: no KM call; the crypto engine runs the PQC path.
        3. Level 4: no KM call; the crypto engine passes the plaintext
           through unchanged.
        4. Pack the resulting ``key_id`` (never key bytes) into the
           message's security metadata and submit via the email service.
    """

    def __init__(
        self,
        crypto: ICryptoEngine,
        km: IKMClient,
        mail: IEmailService,
        store: IKeyStore,
    ) -> None:
        """Inject module dependencies (constructor does wiring only).

        Args:
            crypto: Encrypts payloads at the requested level.
            km: ETSI 014 client used to fetch encryption keys.
            mail: Packs and submits the outbound message.
            store: Caches keys and enforces OTP single-use.
        """
        self._crypto = crypto
        self._km = km
        self._mail = mail
        self._store = store

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        level: SecurityLevel,
        attachments: list[EmailAttachment] | None = None,
        sender: str = _DEFAULT_SENDER,
        recipient_public_key: bytes | None = None,
    ) -> dict[str, Any]:
        """Encrypt and send one email end to end.

        Args:
            to: Recipient address (also used as the KM ``target_sae_id``).
            subject: Subject line.
            body: Plaintext body.
            level: Security level selected by the user.
            attachments: Plaintext attachments, if any.
            sender: ``From`` address (see module note on the placeholder
                default).
            recipient_public_key: ML-KEM-768 public key (level 3 only).

        Returns:
            ``{"message_id": str, "key_id": str | None, "level": SecurityLevel}``.

        Raises:
            EncryptionError: If a level-1 key is shorter than the plaintext,
                or the crypto engine rejects its inputs.
            UnsupportedSecurityLevelError: If ``level`` is unknown.
            KMConnectionError: If a key is needed but the KM is unreachable.
            KeyExhaustedError: If the KM cannot supply enough key material.
            EmailSendError: If SMTP submission fails.
        """
        plaintext = body.encode("utf-8")
        key = self._acquire_key(level, to, plaintext)
        encrypted = self._crypto.encrypt(
            plaintext, level, key=key, recipient_public_key=recipient_public_key
        )

        if level == SecurityLevel.OTP:
            # OTP keys are strictly single-use (CLAUDE.md constraint #2).
            self._store.consume(key.key_id)  # type: ignore[union-attr]

        metadata = dict(encrypted.metadata or {})
        if key is not None and "key_id" not in metadata:
            metadata["key_id"] = key.key_id  # never the key bytes

        message = EmailMessage(
            sender=sender,
            recipient=to,
            subject=subject,
            body=body,
            attachments=attachments or [],
            security_metadata=metadata or None,
        )
        message_id = self._mail.send(message, encrypted)

        key_id = metadata.get("key_id")
        logger.info(
            "sent message_id=%s level=%s key_id=%s", message_id, int(level), key_id
        )
        return {"message_id": message_id, "key_id": key_id, "level": level}

    def _acquire_key(
        self, level: SecurityLevel, to: str, plaintext: bytes
    ) -> QKDKey | None:
        """Fetch, validate, and cache a quantum key for levels 1-2 only.

        Args:
            level: Security level driving whether/how a key is needed.
            to: Recipient address, used as the KM ``target_sae_id``.
            plaintext: The body bytes to be encrypted (sizes the OTP key).

        Returns:
            The acquired key, or ``None`` for levels 3-4 (no KM call).

        Raises:
            EncryptionError: If an OTP key is shorter than the plaintext.
            UnsupportedSecurityLevelError: If ``level`` is unknown.
        """
        if level == SecurityLevel.OTP:
            needed_bits = len(plaintext) * 8
        elif level == SecurityLevel.QUANTUM_AES:
            needed_bits = _QUANTUM_AES_KEY_BITS
        elif level in (SecurityLevel.PQC, SecurityLevel.NONE):
            return None
        else:
            raise UnsupportedSecurityLevelError(f"Unknown security level: {level}")

        keys = self._km.get_key(target_sae_id=to, number=1, size=needed_bits)
        key = keys[0]

        if level == SecurityLevel.OTP and key.size_bits < needed_bits:
            raise EncryptionError(
                f"OTP key {key.key_id} is {key.size_bits} bits, "
                f"need >= {needed_bits} bits for a {len(plaintext)}-byte plaintext"
            )

        self._store.put(key)
        logger.info(
            "acquired key key_id=%s level=%s size_bits=%d",
            key.key_id,
            int(level),
            key.size_bits,
        )
        return key
