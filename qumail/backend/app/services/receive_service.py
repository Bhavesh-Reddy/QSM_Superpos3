"""Receive-side orchestration (M2a): fetch -> key -> decrypt.

Depends exclusively on ``core`` contracts (``core/interfaces.py``,
``core/models.py``, ``core/exceptions.py``). No FastAPI imports allowed here
— HTTP concerns live in ``backend/app/api/`` (M2b).
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from core.exceptions import EmailFetchError, KeyNotFoundError
from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient
from core.models import EmailMessage, EncryptedMessage, QKDKey, SecurityLevel

logger = logging.getLogger(__name__)


class ReceiveService:
    """Orchestrates inbound mail: locate, resolve keys, decrypt.

    Pipeline:
        1. Fetch recent messages via IMAP and locate the requested one.
        2. Read the ``key_id`` out of its security metadata (if any).
        3. Resolve the key: the local key store first, falling back to the
           KM's ``dec_keys`` endpoint (and caching what comes back).
        4. Decrypt via the crypto engine and return plaintext + metadata.
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
            crypto: Decrypts payloads per their metadata.
            km: ETSI 014 client used to fetch decryption keys by ID.
            mail: Fetches and parses inbound messages.
            store: Local key cache consulted before calling the KM.
        """
        self._crypto = crypto
        self._km = km
        self._mail = mail
        self._store = store

    def read(
        self,
        message_id: str,
        folder: str = "INBOX",
        limit: int = 50,
        private_key: bytes | None = None,
        sender_public_key: bytes | None = None,
    ) -> dict[str, Any]:
        """Locate one message, resolve its key, and decrypt it.

        Args:
            message_id: Identifier of the message to read (see
                :meth:`_locate` for how this is matched against
                ``mail.fetch()`` results).
            folder: IMAP folder to search.
            limit: How many recent messages to scan for ``message_id``.
            private_key: Recipient's ML-KEM-768 secret key (level 3 only).
            sender_public_key: Sender's ML-DSA-65 public key, for signature
                verification (level 3 only).

        Returns:
            ``{"plaintext": bytes, "metadata": dict, "level": SecurityLevel}``.

        Raises:
            EmailFetchError: If the IMAP fetch fails or no message matches
                ``message_id``.
            KMConnectionError: If the key isn't cached and the KM is
                unreachable.
            KeyNotFoundError: If neither the store nor the KM has the key.
            DecryptionError: On bad key, corrupted ciphertext, or bad tag.
            SignatureVerificationError: If the level-3 signature is invalid.
        """
        message = self._locate(message_id, folder, limit)
        encrypted = self._extract_encrypted(message)

        key: QKDKey | None = None
        key_id = encrypted.metadata.get("key_id")
        if key_id is not None:
            key = self._resolve_key(key_id, source_sae_id=message.sender)

        plaintext = self._crypto.decrypt(
            encrypted,
            key=key,
            private_key=private_key,
            sender_public_key=sender_public_key,
        )
        logger.info(
            "decrypted message_id=%s level=%s key_id=%s",
            message_id,
            int(encrypted.level),
            key_id,
        )
        return {
            "plaintext": plaintext,
            "metadata": encrypted.metadata,
            "level": encrypted.level,
        }

    def _locate(self, message_id: str, folder: str, limit: int) -> EmailMessage:
        """Find the fetched message matching ``message_id``.

        Assumption (IEmailService.fetch() returns EmailMessage objects with
        no dedicated ID field today): the email layer is expected to stash
        its transport message ID under ``security_metadata["message_id"]``.
        M5's current ``Receiver`` doesn't populate that key yet — this is a
        forward-looking contract for a follow-up patch there, kept out of
        scope here since this module only touches ``services/``.

        Args:
            message_id: The ID to match.
            folder: IMAP folder to search.
            limit: How many recent messages to scan.

        Returns:
            The matching message.

        Raises:
            EmailFetchError: If the fetch fails or no message matches.
        """
        for message in self._mail.fetch(folder=folder, limit=limit):
            metadata = message.security_metadata or {}
            if metadata.get("message_id") == message_id:
                return message
        raise EmailFetchError(f"message '{message_id}' not found in '{folder}'")

    @staticmethod
    def _extract_encrypted(message: EmailMessage) -> EncryptedMessage:
        """Rebuild the :class:`EncryptedMessage` carried in a fetched message.

        Mirrors the envelope ``backend/app/email_svc/receiver.py`` writes
        into ``security_metadata["body"]``: ``{level, metadata,
        ciphertext_b64}``. Plain (non-QuMail) mail has no such envelope; its
        already-plaintext body is wrapped as a level-4 message so callers
        have one uniform return shape.

        Args:
            message: The fetched message.

        Returns:
            The encrypted body payload.

        Raises:
            EmailFetchError: If a QuMail envelope is present but malformed.
        """
        metadata = message.security_metadata or {}
        body = metadata.get("body")
        if body is None:
            return EncryptedMessage(
                ciphertext=message.body.encode("utf-8"),
                metadata={},
                level=SecurityLevel.NONE,
            )
        try:
            return EncryptedMessage(
                ciphertext=base64.b64decode(body["ciphertext_b64"]),
                metadata=dict(body.get("metadata") or {}),
                level=SecurityLevel(body["level"]),
            )
        except (KeyError, ValueError) as exc:
            raise EmailFetchError(f"malformed QuMail envelope: {exc}") from exc

    def _resolve_key(self, key_id: str, source_sae_id: str) -> QKDKey:
        """Resolve a key by ID: local store first, then the KM.

        Args:
            key_id: The KM-assigned key ID from the message metadata.
            source_sae_id: SAE ID of the sender, for the KM ``dec_keys``
                fallback.

        Returns:
            The resolved key.

        Raises:
            KMConnectionError: If the store misses and the KM is unreachable.
            KeyNotFoundError: If neither the store nor the KM has the key.
        """
        try:
            return self._store.get(key_id)
        except KeyNotFoundError:
            keys = self._km.get_key_with_ids(source_sae_id, [key_id])
            if not keys:
                raise KeyNotFoundError(f"KM has no key for key_id={key_id}") from None
            key = keys[0]
            self._store.put(key)  # cache for any re-read of this message
            return key
