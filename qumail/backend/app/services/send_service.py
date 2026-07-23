"""Send-side orchestration (M2a): key -> encrypt -> send.

Typed stub — signatures and contracts only; logic lands in a later task.
Depends exclusively on ``core`` contracts. No FastAPI imports allowed here.
"""

from __future__ import annotations

from core.interfaces import ICryptoEngine, IEmailService, IKeyStore, IKMClient
from core.models import EmailMessage, SecurityLevel


class SendService:
    """Orchestrates outbound mail at a chosen security level.

    Pipeline (to be implemented):
        1. Request key(s) from the KM for the recipient's SAE
           (levels 1–2 only; level 3 uses PQC keypairs, level 4 skips keys).
        2. Cache the key in the key store; consume it if OTP.
        3. Encrypt the body + attachments via the crypto engine.
        4. Pack ciphertext + metadata as ``.qenc`` MIME and send via SMTP.
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
            km_client: ETSI 014 client used to fetch encryption keys.
            crypto_engine: Encrypts payloads at the requested level.
            email_service: Packs and submits the outbound message.
            key_store: Caches keys and enforces OTP single-use.
        """
        self._km_client = km_client
        self._crypto_engine = crypto_engine
        self._email_service = email_service
        self._key_store = key_store

    def send_encrypted_email(
        self,
        message: EmailMessage,
        level: SecurityLevel,
        slave_sae_id: str,
    ) -> str:
        """Encrypt and send one email end to end.

        Args:
            message: Plaintext message composed by the user.
            level: Security level selected in the UI.
            slave_sae_id: SAE ID of the recipient (for KM ``enc_keys``).

        Returns:
            The provider-assigned Message-ID of the sent mail.

        Raises:
            KMConnectionError: If keys are needed but the KM is unreachable.
            KeyExhaustedError: If the KM cannot supply enough key material.
            EncryptionError: If encryption fails for the chosen level.
            EmailSendError: If SMTP submission fails.
        """
        raise NotImplementedError
