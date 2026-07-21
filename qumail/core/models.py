"""Shared data models for QuMail (pydantic v2).

These models are the typed contracts passed across module boundaries
(CLAUDE.md convention: "return typed dataclasses/pydantic models, not loose
dicts"). ETSI GS QKD 014 wire models keep the exact field names from the
standard (``key_ID``, ``key``, ...) — do not rename them.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SecurityLevel(enum.IntEnum):
    """The four user-selectable security levels of QuMail.

    Attributes:
        OTP: Level 1 — Quantum One-Time Pad (XOR with quantum key).
        QUANTUM_AES: Level 2 — AES-256-GCM with HKDF-derived quantum key.
        PQC: Level 3 — ML-KEM-768 + ML-DSA-65 + AES-256-GCM.
        NONE: Level 4 — no encryption (compatibility mode).
    """

    OTP = 1
    QUANTUM_AES = 2
    PQC = 3
    NONE = 4


# --------------------------------------------------------------------------- #
# ETSI GS QKD 014 wire models (field names are fixed by the standard)
# --------------------------------------------------------------------------- #


class ETSIKey(BaseModel):
    """A single key entry as returned by an ETSI 014 Key Manager.

    Attributes:
        key_ID: UUID identifying the key on both KM endpoints.
        key: Base64-encoded key material.
    """

    key_ID: str
    key: str


class ETSIKeyContainer(BaseModel):
    """Response body of ``enc_keys`` / ``dec_keys`` (ETSI 014 "key container")."""

    keys: list[ETSIKey] = Field(default_factory=list)


class ETSIKeyRequest(BaseModel):
    """Request body of ``POST .../enc_keys``.

    Attributes:
        number: How many keys to return.
        size: Size of each key in bits.
    """

    number: int = 1
    size: int = 256


class ETSIKeyID(BaseModel):
    """A single ``{"key_ID": ...}`` entry inside a ``dec_keys`` request."""

    key_ID: str


class ETSIKeyIDsRequest(BaseModel):
    """Request body of ``POST .../dec_keys``."""

    key_IDs: list[ETSIKeyID] = Field(default_factory=list)


class ETSIStatus(BaseModel):
    """Response body of ``GET .../status`` (subset of the ETSI 014 status model).

    Attributes:
        source_KME_ID: ID of the KME serving this SAE.
        target_KME_ID: ID of the peer KME.
        master_SAE_ID: SAE that requests ``enc_keys``.
        slave_SAE_ID: SAE that requests ``dec_keys``.
        key_size: Default key size in bits.
        stored_key_count: Keys currently available.
        max_key_count: Maximum keys the KME can store.
        max_key_per_request: Maximum keys returned per request.
        max_key_size: Largest requestable key size in bits.
        min_key_size: Smallest requestable key size in bits.
    """

    source_KME_ID: str
    target_KME_ID: str
    master_SAE_ID: str
    slave_SAE_ID: str
    key_size: int = 256
    stored_key_count: int = 0
    max_key_count: int = 1024
    max_key_per_request: int = 8
    max_key_size: int = 65536
    min_key_size: int = 64


# --------------------------------------------------------------------------- #
# Internal models (backend-side; never sent to the frontend with key bytes)
# --------------------------------------------------------------------------- #


class QKDKey(BaseModel):
    """A quantum key held in the local key store.

    The raw ``key`` bytes never leave the backend process boundary
    (CLAUDE.md constraint #3). Frontend-facing responses carry only
    ``key_id`` and status metadata.

    Attributes:
        key_id: UUID matching the KM's ``key_ID``.
        key: Raw key material (decoded from base64).
        size_bits: Key length in bits.
        consumed: True once the key has been used for OTP (single-use).
        created_at: UTC timestamp when the key was cached locally.
    """

    key_id: str
    key: bytes
    size_bits: int
    consumed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EmailAttachment(BaseModel):
    """A file attached to an email message.

    Attributes:
        filename: Original file name.
        content_type: MIME type (e.g., ``application/pdf``).
        data: Raw file bytes (plaintext before encryption / after decryption).
    """

    filename: str
    content_type: str = "application/octet-stream"
    data: bytes = b""


class EmailMessage(BaseModel):
    """A plaintext email as composed by / shown to the user.

    Attributes:
        sender: RFC 5321 ``From`` address.
        recipients: RFC 5321 ``To`` addresses.
        subject: Subject line (never encrypted; keep it non-sensitive).
        body: Plaintext body.
        attachments: Plaintext attachments.
    """

    sender: str
    recipients: list[str]
    subject: str = ""
    body: str = ""
    attachments: list[EmailAttachment] = Field(default_factory=list)


class CryptoMetadata(BaseModel):
    """Algorithm parameters shipped alongside ciphertext in the ``.qenc`` MIME part.

    Only the fields relevant to the chosen algorithm are populated; all
    binary values are base64-encoded strings so the model serializes to
    JSON cleanly.

    Attributes:
        algorithm: One of ``"OTP"``, ``"AES-256-GCM"``,
            ``"ML-KEM-768+ML-DSA-65"``, ``"NONE"``.
        key_id: KM ``key_ID`` used (levels 1–2).
        plaintext_length: Original length in bytes (level 1).
        iv: Base64 GCM nonce (levels 2–3).
        tag: Base64 GCM auth tag (levels 2–3).
        ct_kem: Base64 ML-KEM ciphertext (level 3).
        signature: Base64 ML-DSA signature over the ciphertext (level 3).
    """

    algorithm: str
    key_id: str | None = None
    plaintext_length: int | None = None
    iv: str | None = None
    tag: str | None = None
    ct_kem: str | None = None
    signature: str | None = None


class EncryptedMessage(BaseModel):
    """Ciphertext plus everything the recipient needs to decrypt it.

    Attributes:
        security_level: Level the message was encrypted at.
        ciphertext: Encrypted payload bytes.
        metadata: Algorithm parameters (IVs, tags, key IDs — no key bytes).
    """

    security_level: SecurityLevel
    ciphertext: bytes
    metadata: CryptoMetadata
