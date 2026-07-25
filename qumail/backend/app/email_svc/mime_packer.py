"""Build and parse QuMail ``.qenc`` MIME messages (M5).

A QuMail message is a ``multipart/mixed`` with:

1. A plain-text notice so ordinary mail clients show something readable.
2. An ``application/octet-stream`` part named ``qumail_body.qenc`` holding the
   ciphertext, tagged with ``X-QuMail-Type: body`` and ``X-QuMail-Metadata``
   (a JSON envelope with the security level and crypto metadata).
3. Zero or more attachment parts named ``<name>.qenc`` tagged
   ``X-QuMail-Type: attachment``.

Only ``key_ID``s ever appear in metadata — never raw key bytes (CLAUDE.md
constraint #3). The subject is prefixed ``[QuMail]`` and a top-level
``X-QuMail-Version`` header makes detection reliable regardless of subject.

Note: crypto metadata for Level 3 (PQC) contains large base64 blobs
(``ct_kem``, ``signature``). They are carried in the ``X-QuMail-Metadata``
header as spec'd; a single unbroken base64 token can exceed the RFC 5322
998-char line recommendation. Fine for the dev simulator path; a production
transport may prefer a sidecar MIME part for those fields.
"""

from __future__ import annotations

import email
import json
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.policy import default as default_policy

from core.exceptions import MimeFormatError
from core.models import EncryptedMessage, SecurityLevel

TYPE_HEADER = "X-QuMail-Type"
META_HEADER = "X-QuMail-Metadata"
VERSION_HEADER = "X-QuMail-Version"
FILENAME_HEADER = "X-QuMail-Filename"
SUBJECT_PREFIX = "[QuMail] "
BODY_FILENAME = "qumail_body.qenc"
QENC_SUFFIX = ".qenc"

_NOTICE = (
    "This message was sent with QuMail and is quantum-secured.\n"
    "The content is encrypted; open it with a QuMail client to read it.\n"
)


@dataclass
class ParsedQuMail:
    """Result of parsing an inbound message.

    Attributes:
        is_qumail: True if the message carries QuMail encrypted parts.
        sender: ``From`` address.
        recipient: ``To`` address.
        subject: Subject with the ``[QuMail]`` prefix stripped.
        body: The encrypted body, or None for a non-QuMail message.
        attachments: ``(original_filename, EncryptedMessage)`` pairs.
    """

    is_qumail: bool
    sender: str = ""
    recipient: str = ""
    subject: str = ""
    body: EncryptedMessage | None = None
    attachments: list[tuple[str, EncryptedMessage]] = field(default_factory=list)


def _metadata_envelope(encrypted: EncryptedMessage, filename: str | None = None) -> str:
    """Serialize an encrypted part's level + metadata to a JSON header value.

    Args:
        encrypted: The encrypted body or attachment.
        filename: Original filename (attachments only).

    Returns:
        A JSON string for the ``X-QuMail-Metadata`` header.
    """
    envelope: dict[str, object] = {
        "level": int(encrypted.level),
        "metadata": encrypted.metadata,
    }
    if filename is not None:
        envelope["filename"] = filename
    return json.dumps(envelope)


def _add_qenc_part(
    root: MimeMessage,
    encrypted: EncryptedMessage,
    part_type: str,
    filename: str,
    original_name: str | None = None,
) -> None:
    """Attach one ``.qenc`` octet-stream part with QuMail headers.

    Args:
        root: The multipart root to append to.
        encrypted: Ciphertext + metadata to embed.
        part_type: ``"body"`` or ``"attachment"``.
        filename: The ``.qenc`` filename for the MIME part.
        original_name: Original attachment filename (attachments only).
    """
    root.add_attachment(
        encrypted.ciphertext,
        maintype="application",
        subtype="octet-stream",
        filename=filename,
    )
    part = root.get_payload()[-1]  # the just-added part
    part[TYPE_HEADER] = part_type
    part[META_HEADER] = _metadata_envelope(encrypted, original_name)
    if original_name is not None:
        part[FILENAME_HEADER] = original_name


def build(
    sender: str,
    recipient: str,
    subject: str,
    encrypted_body: EncryptedMessage,
    encrypted_attachments: list[tuple[str, EncryptedMessage]] | None = None,
) -> MimeMessage:
    """Assemble a QuMail ``.qenc`` MIME message.

    Args:
        sender: ``From`` address.
        recipient: ``To`` address.
        subject: Subject line (``[QuMail]`` prefix is added automatically).
        encrypted_body: Ciphertext + metadata for the message body.
        encrypted_attachments: ``(original_filename, EncryptedMessage)`` pairs.

    Returns:
        A :class:`email.message.EmailMessage` ready for ``.as_bytes()``/SMTP.

    Raises:
        MimeFormatError: If the message cannot be assembled.
    """
    try:
        root = MimeMessage(policy=default_policy)
        root["From"] = sender
        root["To"] = recipient
        root["Subject"] = SUBJECT_PREFIX + subject
        root[VERSION_HEADER] = "1"
        root.set_content(_NOTICE)  # plain-text notice for non-QuMail clients

        _add_qenc_part(root, encrypted_body, "body", BODY_FILENAME)
        for original_name, enc in encrypted_attachments or []:
            _add_qenc_part(
                root,
                enc,
                "attachment",
                f"{original_name}{QENC_SUFFIX}",
                original_name=original_name,
            )
        return root
    except Exception as exc:  # noqa: BLE001 - normalize to a typed error
        raise MimeFormatError(f"failed to build QuMail message: {exc}") from exc


def _decode_part(part: MimeMessage) -> EncryptedMessage:
    """Reconstruct an :class:`EncryptedMessage` from a ``.qenc`` MIME part.

    Args:
        part: A part tagged with ``X-QuMail-Type`` and ``X-QuMail-Metadata``.

    Returns:
        The decoded encrypted message.

    Raises:
        MimeFormatError: If the metadata header is missing or malformed.
    """
    raw_meta = part[META_HEADER]
    if raw_meta is None:
        raise MimeFormatError(f"part missing {META_HEADER} header")
    try:
        envelope = json.loads(raw_meta)
        level = SecurityLevel(int(envelope["level"]))
        metadata = dict(envelope.get("metadata") or {})
    except (ValueError, KeyError, TypeError) as exc:
        raise MimeFormatError(f"malformed {META_HEADER}: {exc}") from exc
    ciphertext = part.get_payload(decode=True) or b""
    return EncryptedMessage(ciphertext=ciphertext, metadata=metadata, level=level)


def parse(raw: bytes) -> ParsedQuMail:
    """Parse a raw RFC 5322 message, extracting QuMail ciphertext if present.

    Args:
        raw: The raw message bytes (as fetched over IMAP).

    Returns:
        A :class:`ParsedQuMail`; ``is_qumail`` is False for ordinary mail.

    Raises:
        MimeFormatError: If the bytes cannot be parsed as a message at all.
    """
    try:
        msg = email.message_from_bytes(raw, policy=default_policy)
    except Exception as exc:  # noqa: BLE001 - normalize to a typed error
        raise MimeFormatError(f"failed to parse message: {exc}") from exc

    raw_subject = str(msg["Subject"] or "")
    subject = (
        raw_subject[len(SUBJECT_PREFIX) :]
        if raw_subject.startswith(SUBJECT_PREFIX)
        else raw_subject
    )
    result = ParsedQuMail(
        is_qumail=False,
        sender=str(msg["From"] or ""),
        recipient=str(msg["To"] or ""),
        subject=subject,
    )

    is_qumail = msg[VERSION_HEADER] is not None
    for part in msg.walk():
        part_type = part[TYPE_HEADER]
        if part_type == "body":
            is_qumail = True
            result.body = _decode_part(part)
        elif part_type == "attachment":
            is_qumail = True
            original = part[FILENAME_HEADER] or (
                (part.get_filename() or "attachment").removesuffix(QENC_SUFFIX)
            )
            result.attachments.append((str(original), _decode_part(part)))

    result.is_qumail = is_qumail
    return result
