"""Tests for M5 mime_packer: build -> parse round-trip (no network).

Also covers provider auto-detection and the EmailService facade shape.
"""

import pytest

from backend.app.email_svc import EmailService, mime_packer, sender
from core.exceptions import EmailError, MimeFormatError
from core.models import EncryptedMessage, SecurityLevel


def _enc(ciphertext: bytes, metadata: dict, level: SecurityLevel) -> EncryptedMessage:
    return EncryptedMessage(ciphertext=ciphertext, metadata=metadata, level=level)


class TestBuildParseRoundTrip:
    def test_body_ciphertext_and_metadata_preserved(self) -> None:
        body = _enc(
            ciphertext=b"\x00\x01\x02\xff\xfe secret bytes \x10",
            metadata={"algorithm": "AES-256-GCM", "key_id": "QK-000001", "iv": "aXY=", "tag": "dGFn"},
            level=SecurityLevel.QUANTUM_AES,
        )
        built = mime_packer.build(
            sender="alice@gmail.com",
            recipient="bob@yahoo.com",
            subject="Hello Bob",
            encrypted_body=body,
        )
        parsed = mime_packer.parse(built.as_bytes())

        assert parsed.is_qumail is True
        assert parsed.sender == "alice@gmail.com"
        assert parsed.recipient == "bob@yahoo.com"
        assert parsed.subject == "Hello Bob"  # [QuMail] prefix stripped
        assert parsed.body is not None
        assert parsed.body.ciphertext == body.ciphertext
        assert parsed.body.metadata == body.metadata
        assert parsed.body.level is SecurityLevel.QUANTUM_AES

    def test_attachments_round_trip(self) -> None:
        body = _enc(b"body-ct", {"algorithm": "OTP", "key_id": "QK-000009"}, SecurityLevel.OTP)
        att1 = _enc(b"\x89PNG-ciphertext", {"algorithm": "OTP", "key_id": "QK-000010"}, SecurityLevel.OTP)
        att2 = _enc(b"pdf-ciphertext-bytes", {"algorithm": "OTP", "key_id": "QK-000011"}, SecurityLevel.OTP)

        built = mime_packer.build(
            sender="alice@gmail.com",
            recipient="bob@outlook.com",
            subject="Files",
            encrypted_body=body,
            encrypted_attachments=[("photo.png", att1), ("report.pdf", att2)],
        )
        parsed = mime_packer.parse(built.as_bytes())

        assert parsed.body.ciphertext == body.ciphertext
        assert len(parsed.attachments) == 2
        names = [name for name, _ in parsed.attachments]
        assert names == ["photo.png", "report.pdf"]
        recovered = {name: enc for name, enc in parsed.attachments}
        assert recovered["photo.png"].ciphertext == att1.ciphertext
        assert recovered["report.pdf"].ciphertext == att2.ciphertext
        assert recovered["report.pdf"].metadata == att2.metadata

    def test_pqc_large_metadata_round_trip(self) -> None:
        # Level 3 metadata carries large base64 blobs (ct_kem, signature).
        body = _enc(
            ciphertext=b"pqc-ciphertext",
            metadata={
                "algorithm": "ML-KEM-768+ML-DSA-65",
                "ct_kem": "A" * 1400,
                "iv": "aXY=",
                "tag": "dGFn",
                "signature": "B" * 4400,
            },
            level=SecurityLevel.PQC,
        )
        built = mime_packer.build("a@gmail.com", "b@gmail.com", "pqc", body)
        parsed = mime_packer.parse(built.as_bytes())
        assert parsed.body.metadata == body.metadata
        assert parsed.body.level is SecurityLevel.PQC


class TestDetection:
    def test_non_qumail_message_is_flagged(self) -> None:
        raw = (
            b"From: someone@example.com\r\n"
            b"To: me@example.com\r\n"
            b"Subject: ordinary mail\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"just a normal email\r\n"
        )
        parsed = mime_packer.parse(raw)
        assert parsed.is_qumail is False
        assert parsed.body is None
        assert parsed.subject == "ordinary mail"

    def test_malformed_metadata_raises(self) -> None:
        built = mime_packer.build(
            "a@gmail.com",
            "b@gmail.com",
            "x",
            _enc(b"ct", {"algorithm": "OTP"}, SecurityLevel.OTP),
        )
        # Corrupt the metadata header.
        for part in built.walk():
            if part[mime_packer.META_HEADER] is not None:
                del part[mime_packer.META_HEADER]
                part[mime_packer.META_HEADER] = "{not-json"
        with pytest.raises(MimeFormatError):
            mime_packer.parse(built.as_bytes())


class TestProviderDetection:
    @pytest.mark.parametrize(
        "address,expected",
        [
            ("alice@gmail.com", "gmail"),
            ("bob@yahoo.com", "yahoo"),
            ("carol@outlook.com", "outlook"),
            ("dave@hotmail.com", "outlook"),
        ],
    )
    def test_detect_provider(self, address: str, expected: str) -> None:
        assert sender.detect_provider(address) == expected

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(EmailError):
            sender.detect_provider("eve@self-hosted.example")

    def test_account_from_address_resolves_preset(self) -> None:
        account = sender.EmailAccount.from_address("alice@gmail.com", "app-password")
        assert account.preset.smtp_host == "smtp.gmail.com"
        assert account.preset.smtp_port == 587
        assert account.preset.imap_host == "imap.gmail.com"


class TestEmailServiceFacade:
    def test_facade_implements_interface(self) -> None:
        from core.interfaces import IEmailService

        svc = EmailService.from_address("alice@gmail.com", "app-password")
        assert isinstance(svc, IEmailService)
