"""Tests for core/ — models, interfaces, exceptions (scaffold sanity checks)."""

import pytest

from core import exceptions, interfaces
from core.models import (
    CryptoMetadata,
    EncryptedMessage,
    ETSIKey,
    ETSIKeyContainer,
    QKDKey,
    SecurityLevel,
)


class TestSecurityLevel:
    def test_levels_match_problem_statement(self) -> None:
        assert SecurityLevel.OTP == 1
        assert SecurityLevel.QUANTUM_AES == 2
        assert SecurityLevel.PQC == 3
        assert SecurityLevel.NONE == 4


class TestETSIWireModels:
    def test_key_container_preserves_etsi_field_names(self) -> None:
        """ETSI 014 field names (key_ID, key) are fixed — must survive serialization."""
        container = ETSIKeyContainer(keys=[ETSIKey(key_ID="uuid-1", key="AAAA")])
        dumped = container.model_dump()
        assert dumped == {"keys": [{"key_ID": "uuid-1", "key": "AAAA"}]}


class TestQKDKey:
    def test_new_key_is_not_consumed(self) -> None:
        key = QKDKey(key_id="uuid-1", key=b"\x00" * 32, size_bits=256)
        assert key.consumed is False
        assert key.created_at.tzinfo is not None


class TestEncryptedMessage:
    def test_round_trips_through_json(self) -> None:
        msg = EncryptedMessage(
            security_level=SecurityLevel.QUANTUM_AES,
            ciphertext=b"\x01\x02",
            metadata=CryptoMetadata(algorithm="AES-256-GCM", key_id="uuid-1"),
        )
        restored = EncryptedMessage.model_validate_json(msg.model_dump_json())
        assert restored == msg


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


class TestExceptions:
    def test_all_exceptions_inherit_qumail_error(self) -> None:
        for name in dir(exceptions):
            obj = getattr(exceptions, name)
            if isinstance(obj, type) and issubclass(obj, Exception) and name != "QuMailError":
                if obj.__module__ == "core.exceptions":
                    assert issubclass(obj, exceptions.QuMailError), name

    def test_key_reuse_error_is_a_keystore_error(self) -> None:
        assert issubclass(
            exceptions.KeyAlreadyConsumedError, exceptions.KeyStoreError
        )