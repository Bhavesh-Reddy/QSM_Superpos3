"""Tests for core/ — models, interfaces, exceptions.

Covers: construction of every shared model, enum values, validation errors
on bad input, ABC instantiation guards, and the exception hierarchy.
"""

import pytest
from pydantic import ValidationError

from core import exceptions, interfaces
from core.models import (
    CryptoMetadata,
    EmailAttachment,
    EmailMessage,
    EncryptedMessage,
    ETSIKey,
    ETSIKeyContainer,
    ETSIKeyIDsRequest,
    ETSIKeyRequest,
    ETSIStatus,
    QKDKey,
    SecurityLevel,
)


class TestSecurityLevel:
    def test_levels_match_problem_statement(self) -> None:
        assert SecurityLevel.OTP == 1
        assert SecurityLevel.QUANTUM_AES == 2
        assert SecurityLevel.PQC == 3
        assert SecurityLevel.NONE == 4

    def test_exactly_four_levels(self) -> None:
        assert len(SecurityLevel) == 4


class TestQKDKey:
    def test_construct(self) -> None:
        key = QKDKey(key_id="uuid-1", key=b"\x00" * 32, size_bits=256)
        assert key.key_id == "uuid-1"
        assert key.key == b"\x00" * 32
        assert key.size_bits == 256
        assert key.consumed is False
        assert key.created_at.tzinfo is not None

    def test_rejects_empty_key_id(self) -> None:
        with pytest.raises(ValidationError):
            QKDKey(key_id="", key=b"\x00", size_bits=8)

    def test_rejects_non_positive_size(self) -> None:
        with pytest.raises(ValidationError):
            QKDKey(key_id="uuid-1", key=b"\x00", size_bits=0)

    def test_rejects_missing_key(self) -> None:
        with pytest.raises(ValidationError):
            QKDKey(key_id="uuid-1", size_bits=8)  # type: ignore[call-arg]


class TestEncryptedMessage:
    def test_construct(self) -> None:
        msg = EncryptedMessage(
            ciphertext=b"\x01\x02",
            metadata={"algorithm": "OTP", "key_id": "uuid-1", "plaintext_length": 2},
            level=SecurityLevel.OTP,
        )
        assert msg.level is SecurityLevel.OTP
        assert msg.metadata["algorithm"] == "OTP"

    def test_metadata_defaults_to_empty_dict(self) -> None:
        msg = EncryptedMessage(ciphertext=b"", level=SecurityLevel.NONE)
        assert msg.metadata == {}

    def test_rejects_invalid_level(self) -> None:
        with pytest.raises(ValidationError):
            EncryptedMessage(ciphertext=b"", level=99)

    def test_round_trips_through_json(self) -> None:
        msg = EncryptedMessage(
            ciphertext=b"\x01\x02",
            metadata=CryptoMetadata(
                algorithm="AES-256-GCM", key_id="uuid-1", iv="aXY=", tag="dGFn"
            ).model_dump(exclude_none=True),
            level=SecurityLevel.QUANTUM_AES,
        )
        restored = EncryptedMessage.model_validate_json(msg.model_dump_json())
        assert restored == msg


class TestEmailMessage:
    def test_construct(self) -> None:
        msg = EmailMessage(
            sender="alice@example.com",
            recipient="bob@example.com",
            subject="hello",
            body="hi",
            attachments=[EmailAttachment(filename="a.txt", data=b"abc")],
            security_metadata={"algorithm": "OTP", "key_id": "uuid-1"},
        )
        assert msg.recipient == "bob@example.com"
        assert msg.timestamp.tzinfo is not None
        assert msg.attachments[0].filename == "a.txt"

    def test_defaults(self) -> None:
        msg = EmailMessage(sender="a@x.com", recipient="b@x.com")
        assert msg.subject == ""
        assert msg.body == ""
        assert msg.attachments == []
        assert msg.security_metadata is None

    def test_rejects_empty_sender_or_recipient(self) -> None:
        with pytest.raises(ValidationError):
            EmailMessage(sender="", recipient="b@x.com")
        with pytest.raises(ValidationError):
            EmailMessage(sender="a@x.com", recipient="")

    def test_rejects_bad_timestamp(self) -> None:
        with pytest.raises(ValidationError):
            EmailMessage(
                sender="a@x.com", recipient="b@x.com", timestamp="not-a-date"
            )


class TestETSIWireModels:
    def test_key_container_preserves_etsi_field_names(self) -> None:
        """ETSI 014 field names (key_ID, key) are fixed — must survive serialization."""
        container = ETSIKeyContainer(keys=[ETSIKey(key_ID="uuid-1", key="AAAA")])
        assert container.model_dump() == {"keys": [{"key_ID": "uuid-1", "key": "AAAA"}]}

    def test_key_request_defaults(self) -> None:
        req = ETSIKeyRequest()
        assert req.number == 1
        assert req.size == 256

    def test_key_ids_request_shape(self) -> None:
        req = ETSIKeyIDsRequest.model_validate({"key_IDs": [{"key_ID": "uuid-1"}]})
        assert req.key_IDs[0].key_ID == "uuid-1"

    def test_status_construct(self) -> None:
        status = ETSIStatus(
            source_KME_ID="KME-1",
            target_KME_ID="KME-2",
            master_SAE_ID="SAE-A",
            slave_SAE_ID="SAE-B",
            stored_key_count=10,
        )
        assert status.stored_key_count == 10


class TestInterfaces:
    @pytest.mark.parametrize(
        "iface",
        [
            interfaces.ICryptoEngine,
            interfaces.IKMClient,
            interfaces.IEmailService,
            interfaces.IKeyStore,
        ],
    )
    def test_abcs_cannot_be_instantiated(self, iface: type) -> None:
        with pytest.raises(TypeError):
            iface()  # type: ignore[abstract]

    def test_km_client_contract_method_names(self) -> None:
        for name in ("get_status", "get_key", "get_key_with_ids"):
            assert name in interfaces.IKMClient.__abstractmethods__

    def test_keystore_contract_method_names(self) -> None:
        assert interfaces.IKeyStore.__abstractmethods__ == frozenset(
            {"put", "get", "consume"}
        )


class TestExceptions:
    def test_required_exceptions_exist_and_inherit_base(self) -> None:
        for exc in (
            exceptions.KMConnectionError,
            exceptions.KeyExhaustedError,
            exceptions.KeyNotFoundError,
            exceptions.DecryptionError,
            exceptions.EmailError,
            exceptions.ConfigError,
        ):
            assert issubclass(exc, exceptions.QuMailError)

    def test_all_module_exceptions_inherit_qumail_error(self) -> None:
        for name in dir(exceptions):
            obj = getattr(exceptions, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Exception)
                and obj.__module__ == "core.exceptions"
                and name != "QuMailError"
            ):
                assert issubclass(obj, exceptions.QuMailError), name

    def test_key_reuse_error_is_a_keystore_error(self) -> None:
        assert issubclass(
            exceptions.KeyAlreadyConsumedError, exceptions.KeyStoreError
        )
