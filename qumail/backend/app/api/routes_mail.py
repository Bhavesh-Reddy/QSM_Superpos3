"""M2b — mail routes: send, list (summaries only), read (decrypt).

Thin delegation to :class:`SendService` / :class:`ReceiveService` (M2a) and
the raw :class:`IEmailService` for listing. No crypto/KM/email calls happen
here directly — only request validation, delegation, and response shaping.
Ciphertext and key material never appear in a response.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Base64Bytes, BaseModel

from core.interfaces import IEmailService
from core.models import EmailAttachment, EmailMessage, SecurityLevel

from backend.app.api.deps import get_mail_service, get_receive_service, get_send_service
from backend.app.services import ReceiveService, SendService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mail", tags=["mail"])


class AttachmentIn(BaseModel):
    """One plaintext attachment on ``POST /mail/send``."""

    filename: str
    content_type: str = "application/octet-stream"
    data: Base64Bytes


class SendRequest(BaseModel):
    """Body of ``POST /mail/send``."""

    to: str
    subject: str = ""
    body: str = ""
    level: SecurityLevel
    attachments: list[AttachmentIn] | None = None


class SendResponse(BaseModel):
    """Response of ``POST /mail/send``."""

    message_id: str
    key_id: str | None
    level: SecurityLevel


class MessageSummary(BaseModel):
    """One entry of ``GET /mail/fetch`` — never ciphertext or key bytes."""

    sender: str
    recipient: str
    subject: str
    timestamp: datetime
    is_encrypted: bool
    level: SecurityLevel | None = None
    algorithm: str | None = None


class FetchResponse(BaseModel):
    """Response of ``GET /mail/fetch``."""

    messages: list[MessageSummary]


class ReadRequest(BaseModel):
    """Body of ``POST /mail/read``."""

    message_id: str


class ReadResponse(BaseModel):
    """Response of ``POST /mail/read`` — decrypted body + safe metadata."""

    body: str
    level: SecurityLevel
    metadata: dict[str, Any]


@router.post("/send", response_model=SendResponse)
def send_mail(
    payload: SendRequest, send_service: SendService = Depends(get_send_service)
) -> SendResponse:
    """Encrypt (per ``level``) and send one email.

    Raises:
        EncryptionError: If a level-1 key is shorter than the plaintext, or
            the crypto engine rejects its inputs.
        UnsupportedSecurityLevelError: If ``level`` is unknown.
        KMConnectionError: If a key is needed but the KM is unreachable.
        KeyExhaustedError: If the KM cannot supply enough key material.
        EmailSendError: If SMTP submission fails.
    """
    attachments = [
        EmailAttachment(filename=a.filename, content_type=a.content_type, data=a.data)
        for a in payload.attachments or []
    ]
    result = send_service.send(
        payload.to,
        payload.subject,
        payload.body,
        payload.level,
        attachments=attachments or None,
    )
    logger.info(
        "POST /mail/send to=%s level=%s message_id=%s key_id=%s",
        payload.to,
        int(payload.level),
        result["message_id"],
        result["key_id"],
    )
    return SendResponse(**result)


@router.get("/fetch", response_model=FetchResponse)
def fetch_mail(
    folder: str = "INBOX",
    limit: int = 50,
    mail: IEmailService = Depends(get_mail_service),
) -> FetchResponse:
    """List recent messages as summaries — ciphertext stays server-side.

    Raises:
        EmailError: On IMAP authentication failure.
        EmailFetchError: On any other IMAP failure.
    """
    messages = mail.fetch(folder=folder, limit=limit)
    return FetchResponse(messages=[_summarize(message) for message in messages])


@router.post("/read", response_model=ReadResponse)
def read_mail(
    payload: ReadRequest, receive_service: ReceiveService = Depends(get_receive_service)
) -> ReadResponse:
    """Locate, resolve the key for, and decrypt one message.

    Raises:
        EmailFetchError: If the message can't be found.
        KMConnectionError: If the key isn't cached and the KM is unreachable.
        KeyNotFoundError: If neither the store nor the KM has the key.
        DecryptionError: On bad key, corrupted ciphertext, or bad tag.
        SignatureVerificationError: If the level-3 signature is invalid.
    """
    result = receive_service.read(payload.message_id)
    logger.info(
        "POST /mail/read message_id=%s level=%s", payload.message_id, int(result["level"])
    )
    return ReadResponse(
        body=result["plaintext"].decode("utf-8", errors="replace"),
        level=result["level"],
        metadata=result["metadata"],
    )


def _summarize(message: EmailMessage) -> MessageSummary:
    """Project a fetched :class:`EmailMessage` to a client-safe summary.

    Reads only the level/algorithm out of the QuMail body envelope (see
    ``backend/app/email_svc/receiver.py``); never touches ciphertext or
    ``key_id`` — those stay server-side until an explicit ``/mail/read``.
    """
    body_envelope = (message.security_metadata or {}).get("body")
    level = SecurityLevel(body_envelope["level"]) if body_envelope else None
    algorithm = (
        (body_envelope.get("metadata") or {}).get("algorithm") if body_envelope else None
    )
    return MessageSummary(
        sender=message.sender,
        recipient=message.recipient,
        subject=message.subject,
        timestamp=message.timestamp,
        is_encrypted=body_envelope is not None,
        level=level,
        algorithm=algorithm,
    )
