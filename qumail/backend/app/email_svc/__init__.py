"""M5 — Email Service.

SMTP send + IMAP fetch + ``.qenc`` MIME packing for QuMail. The
:class:`EmailService` facade implements ``core.interfaces.IEmailService`` by
delegating to :class:`~backend.app.email_svc.sender.Sender` and
:class:`~backend.app.email_svc.receiver.Receiver`.

Import order note: ``mime_packer`` has no intra-package deps; ``sender``
imports it; ``receiver`` imports both. This module imports all three, so it
must be imported as a package (not via ``from . import sender`` cycles).
"""

from __future__ import annotations

from core.interfaces import IEmailService
from core.models import EmailMessage, EncryptedMessage

from backend.app.email_svc.receiver import Receiver
from backend.app.email_svc.sender import EmailAccount, Sender

__all__ = ["EmailAccount", "EmailService", "Receiver", "Sender"]


class EmailService(IEmailService):
    """Facade wiring the SMTP sender and IMAP receiver behind IEmailService."""

    def __init__(self, account: EmailAccount) -> None:
        """Build sender/receiver for a single mailbox.

        Args:
            account: Credentials + endpoints for the mailbox.
        """
        self._account = account
        self._sender = Sender(account)
        self._receiver = Receiver(account)

    @classmethod
    def from_address(cls, address: str, password: str) -> EmailService:
        """Construct a service, auto-detecting the provider from the address.

        Args:
            address: The mailbox address.
            password: App password / token.

        Returns:
            A ready :class:`EmailService`.
        """
        return cls(EmailAccount.from_address(address, password))

    def send(self, message: EmailMessage, encrypted: EncryptedMessage) -> str:
        """Send an encrypted message body (IEmailService contract).

        Per-attachment encryption is orchestrated by M2a SendService; this
        facade sends the encrypted body. Use
        :meth:`Sender.send_quantum_email` directly to attach encrypted files.

        Args:
            message: Plaintext envelope.
            encrypted: The encrypted body payload.

        Returns:
            The sent message's ``Message-ID``.

        Raises:
            EmailSendError: On SMTP failure.
            MimeFormatError: If the MIME message cannot be built.
        """
        return self._sender.send_quantum_email(message, encrypted)

    def fetch(self, folder: str = "INBOX", limit: int = 50) -> list[EmailMessage]:
        """Fetch recent messages (IEmailService contract).

        Args:
            folder: IMAP folder name.
            limit: Maximum number of messages, newest first.

        Returns:
            Parsed messages; encrypted ones carry ciphertext in
            ``security_metadata`` until decrypted.

        Raises:
            EmailError: On IMAP authentication failure.
            EmailFetchError: On any other IMAP failure.
        """
        return self._receiver.fetch(folder=folder, limit=limit)
