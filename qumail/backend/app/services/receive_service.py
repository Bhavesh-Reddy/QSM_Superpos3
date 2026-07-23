"""Receive-side orchestration (M2a): fetch -> key -> decrypt.

Typed stub — signatures and contracts only; logic lands in a later task.
Depends exclusively on ``core`` contracts. No FastAPI imports allowed here.
"""

from __future__ import annotations

from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient
from core.models import EmailMessage


class ReceiveService:
    """Orchestrates inbound mail: fetch, resolve keys, decrypt.

    Pipeline (to be implemented):
        1. Fetch recent messages via IMAP.
        2. For encrypted ones, read ``key_ID``(s) from the metadata and
           resolve the matching key: key store first, then KM ``dec_keys``.
        3. Decrypt via the crypto engine and return plaintext messages;
           surface per-message decryption failures without aborting the batch.
    """

    def __init__(
        self,
        km_client: IKMClient,
        crypto_engine: ICryptoEngine,
        email_service: IEmailService,
        key_store: IKeyStore,
    ) -> None:
        """Inject module dependencies (constructor does wiring only).

        Args:
            km_client: ETSI 014 client used to fetch decryption keys by ID.
            crypto_engine: Decrypts payloads per their metadata.
            email_service: Fetches and parses inbound messages.
            key_store: Local key cache consulted before calling the KM.
        """
        self._km_client = km_client
        self._crypto_engine = crypto_engine
        self._email_service = email_service
        self._key_store = key_store

    def fetch_and_decrypt(
        self,
        master_sae_id: str,
        folder: str = "INBOX",
        limit: int = 20,
    ) -> list[EmailMessage]:
        """Fetch recent mail and decrypt anything encrypted.

        Args:
            master_sae_id: SAE ID of the sender side (for KM ``dec_keys``).
            folder: IMAP folder to read.
            limit: Maximum number of messages, newest first.

        Returns:
            Messages with plaintext bodies/attachments where decryption
            succeeded; ``security_metadata`` reports each message's status.

        Raises:
            EmailFetchError: If the IMAP fetch itself fails.
            KMConnectionError: If a needed key must come from the KM and it
                is unreachable.
        """
        raise NotImplementedError
