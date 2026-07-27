"""SMTP sending for QuMail (M5).

Sends both QuMail ``.qenc`` messages and plain messages via the sender's
provider (Gmail/Yahoo/Outlook auto-detected from the address domain), using
STARTTLS on the submission port. Credentials come from an
:class:`EmailAccount` (populated from ``backend/app/config.py`` in production);
app passwords are recommended since providers block basic auth on real ones.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid

from core.exceptions import EmailError, EmailSendError
from core.models import EmailMessage, EncryptedMessage

from backend.app.email_svc import mime_packer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderPreset:
    """SMTP/IMAP endpoints for a mail provider.

    Attributes:
        smtp_host: SMTP submission host.
        smtp_port: SMTP submission port (587 = STARTTLS).
        imap_host: IMAP host.
        imap_port: IMAP SSL port (993).
    """

    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int


# Provider presets keyed by short name; domains map onto them below.
PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "gmail": ProviderPreset("smtp.gmail.com", 587, "imap.gmail.com", 993),
    "yahoo": ProviderPreset("smtp.mail.yahoo.com", 587, "imap.mail.yahoo.com", 993),
    "outlook": ProviderPreset("smtp.office365.com", 587, "outlook.office365.com", 993),
}

# Domain -> provider name (auto-detection).
_DOMAIN_MAP: dict[str, str] = {
    "gmail.com": "gmail",
    "googlemail.com": "gmail",
    "yahoo.com": "yahoo",
    "ymail.com": "yahoo",
    "outlook.com": "outlook",
    "hotmail.com": "outlook",
    "live.com": "outlook",
    "office365.com": "outlook",
}


def detect_provider(address: str) -> str:
    """Infer the provider short-name from an email address domain.

    Args:
        address: Full email address (e.g. ``alice@gmail.com``).

    Returns:
        A key of :data:`PROVIDER_PRESETS`.

    Raises:
        EmailError: If the domain is not a known provider.
    """
    domain = address.rsplit("@", 1)[-1].lower()
    provider = _DOMAIN_MAP.get(domain)
    if provider is None:
        raise EmailError(f"unknown email provider for domain '{domain}'")
    return provider


@dataclass
class EmailAccount:
    """Credentials + endpoints for one mailbox.

    Attributes:
        address: The mailbox address (also the SMTP/IMAP username).
        password: App password / token (never logged, never sent in mail).
        preset: Resolved provider endpoints.
    """

    address: str
    password: str
    preset: ProviderPreset

    @classmethod
    def from_address(cls, address: str, password: str) -> EmailAccount:
        """Build an account by auto-detecting the provider from the address.

        Args:
            address: The mailbox address.
            password: App password / token.

        Returns:
            A configured :class:`EmailAccount`.

        Raises:
            EmailError: If the provider cannot be detected.
        """
        return cls(address, password, PROVIDER_PRESETS[detect_provider(address)])


class Sender:
    """Submits messages over SMTP for a single account."""

    def __init__(self, account: EmailAccount, timeout: float = 30.0) -> None:
        """Store the account used for all sends.

        Args:
            account: Credentials + endpoints of the sending mailbox.
            timeout: Socket timeout in seconds.
        """
        self._account = account
        self._timeout = timeout

    def _submit(self, mime_message: MimeMessage) -> str:
        """Connect, authenticate, and send one MIME message.

        Args:
            mime_message: The fully built message (headers included).

        Returns:
            The message's ``Message-ID``.

        Raises:
            EmailSendError: On authentication or transport failure.
        """
        if mime_message["Message-ID"] is None:
            mime_message["Message-ID"] = make_msgid()
        message_id = str(mime_message["Message-ID"])
        preset = self._account.preset
        try:
            with smtplib.SMTP(preset.smtp_host, preset.smtp_port, timeout=self._timeout) as smtp:
                smtp.ehlo()
                smtp.starttls()  # upgrade to TLS before authenticating
                smtp.ehlo()
                smtp.login(self._account.address, self._account.password)
                smtp.send_message(mime_message)
        except smtplib.SMTPAuthenticationError as exc:
            # Log Google's actual rejection (contains no password) so the real
            # cause is visible, e.g. "534 5.7.9 Application-specific password
            # required" vs "535 5.7.8 Username and Password not accepted".
            logger.warning(
                "SMTP auth rejected by %s for %s: code=%s detail=%s",
                preset.smtp_host,
                self._account.address,
                getattr(exc, "smtp_code", "?"),
                getattr(exc, "smtp_error", b"").decode("utf-8", "replace"),
            )
            raise EmailSendError("SMTP authentication failed (use an app password)") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"SMTP send failed: {exc}") from exc
        logger.info("sent message %s to %s", message_id, mime_message["To"])
        return message_id

    def send_quantum_email(
        self,
        message: EmailMessage,
        encrypted_body: EncryptedMessage,
        encrypted_attachments: list[tuple[str, EncryptedMessage]] | None = None,
    ) -> str:
        """Pack ciphertext as ``.qenc`` MIME and send it.

        Args:
            message: Plaintext envelope (sender, recipient, subject).
            encrypted_body: Encrypted message body.
            encrypted_attachments: Encrypted attachments as
                ``(original_filename, EncryptedMessage)`` pairs.

        Returns:
            The sent message's ``Message-ID``.

        Raises:
            EmailSendError: On SMTP failure.
            MimeFormatError: If the MIME message cannot be built.
        """
        mime_message = mime_packer.build(
            sender=message.sender,
            recipient=message.recipient,
            subject=message.subject,
            encrypted_body=encrypted_body,
            encrypted_attachments=encrypted_attachments,
        )
        return self._submit(mime_message)

    def send_plain(self, message: EmailMessage) -> str:
        """Send an unencrypted message (Level 4 / compatibility).

        Args:
            message: The plaintext message to send.

        Returns:
            The sent message's ``Message-ID``.

        Raises:
            EmailSendError: On SMTP failure.
        """
        mime_message = MimeMessage()
        mime_message["From"] = message.sender
        mime_message["To"] = message.recipient
        mime_message["Subject"] = message.subject
        mime_message.set_content(message.body)
        for attachment in message.attachments:
            maintype, _, subtype = attachment.content_type.partition("/")
            mime_message.add_attachment(
                attachment.data,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.filename,
            )
        return self._submit(mime_message)
