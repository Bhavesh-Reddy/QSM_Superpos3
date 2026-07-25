"""IMAP fetching for QuMail (M5).

Retrieves recent messages over IMAP-SSL and parses them into core
:class:`~core.models.EmailMessage` objects. QuMail messages keep their
ciphertext in ``security_metadata`` (base64-encoded) until the orchestration
layer (M2a ReceiveService) decrypts them — the receiver never decrypts and
never touches key material.
"""

from __future__ import annotations

import base64
import email
import imaplib
import logging
from email.policy import default as default_policy
from email.utils import parsedate_to_datetime

from core.exceptions import EmailError, EmailFetchError
from core.models import EmailMessage

from backend.app.email_svc import mime_packer
from backend.app.email_svc.sender import EmailAccount

logger = logging.getLogger(__name__)


class Receiver:
    """Fetches and parses inbound mail for a single account."""

    def __init__(self, account: EmailAccount, timeout: float = 30.0) -> None:
        """Store the account used for all fetches.

        Args:
            account: Credentials + endpoints of the mailbox to read.
            timeout: Socket timeout in seconds.
        """
        self._account = account
        self._timeout = timeout

    def fetch(self, folder: str = "INBOX", limit: int = 50) -> list[EmailMessage]:
        """Fetch the most recent messages from a folder, newest first.

        Args:
            folder: IMAP folder name.
            limit: Maximum number of messages to return.

        Returns:
            Parsed messages; QuMail ones carry ciphertext in
            ``security_metadata`` pending decryption.

        Raises:
            EmailError: On IMAP authentication failure.
            EmailFetchError: On any other IMAP/parse failure.
        """
        preset = self._account.preset
        try:
            with imaplib.IMAP4_SSL(
                preset.imap_host, preset.imap_port, timeout=self._timeout
            ) as imap:
                try:
                    imap.login(self._account.address, self._account.password)
                except imaplib.IMAP4.error as exc:
                    raise EmailError("IMAP authentication failed (use an app password)") from exc

                imap.select(folder, readonly=True)
                status, data = imap.search(None, "ALL")
                if status != "OK":
                    raise EmailFetchError(f"IMAP search failed in '{folder}'")

                ids = data[0].split()
                recent_ids = ids[-limit:] if limit else ids
                messages: list[EmailMessage] = []
                for msg_id in reversed(recent_ids):  # newest first
                    status, raw_data = imap.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not raw_data or raw_data[0] is None:
                        continue
                    raw = raw_data[0][1]
                    messages.append(self._to_email_message(raw))
                return messages
        except EmailError:
            raise
        except (imaplib.IMAP4.error, OSError) as exc:
            raise EmailFetchError(f"IMAP fetch failed: {exc}") from exc

    @staticmethod
    def _to_email_message(raw: bytes) -> EmailMessage:
        """Convert raw RFC822 bytes into a core :class:`EmailMessage`.

        Args:
            raw: The raw message bytes.

        Returns:
            A parsed message. QuMail messages have ``security_metadata`` set
            and an empty body; ordinary mail has its plain-text body.
        """
        headers = email.message_from_bytes(raw, policy=default_policy)
        sender = str(headers["From"] or "")
        recipient = str(headers["To"] or "")
        try:
            timestamp = parsedate_to_datetime(headers["Date"]) if headers["Date"] else None
        except (TypeError, ValueError):
            timestamp = None

        parsed = mime_packer.parse(raw)
        if not parsed.is_qumail:
            body_part = headers.get_body(preferencelist=("plain",))
            body = body_part.get_content() if body_part is not None else ""
            msg = EmailMessage(
                sender=sender or "unknown@unknown",
                recipient=recipient or "unknown@unknown",
                subject=str(headers["Subject"] or ""),
                body=body,
            )
        else:
            # Carry ciphertext (base64) + metadata for the decryptor; no keys.
            security_metadata: dict[str, object] = {
                "qumail": True,
                "body": {
                    "level": int(parsed.body.level),
                    "metadata": parsed.body.metadata,
                    "ciphertext_b64": base64.b64encode(parsed.body.ciphertext).decode("ascii"),
                }
                if parsed.body is not None
                else None,
                "attachments": [
                    {
                        "filename": name,
                        "level": int(enc.level),
                        "metadata": enc.metadata,
                        "ciphertext_b64": base64.b64encode(enc.ciphertext).decode("ascii"),
                    }
                    for name, enc in parsed.attachments
                ],
            }
            msg = EmailMessage(
                sender=sender or "unknown@unknown",
                recipient=recipient or "unknown@unknown",
                subject=parsed.subject,
                body="",
                security_metadata=security_metadata,
            )

        if timestamp is not None:
            msg.timestamp = timestamp
        return msg
