"""Tests for Level 2 — Quantum-aided AES-256-GCM.

Covers:
- Round-trip encrypt → decrypt produces original plaintext.
- Each encryption produces a different IV (non-deterministic).
- Tampered GCM tag → DecryptionError.
- Tampered ciphertext → DecryptionError.
- Round-trip through the CryptoEngine facade.
"""

from __future__ import annotations

import base64
import os

import pytest

from backend.app.crypto import quantum_aes
from backend.app.crypto.engine import CryptoEngine
from core.exceptions import DecryptionError, EncryptionError
from core.models import EncryptedMessage, QKDKey, SecurityLevel


class TestQuantumAESDirect:
    """Direct tests against the quantum_aes module."""

    @pytest.fixture()
    def quantum_key(self) -> bytes:
        """A 256-bit (32-byte) quantum key."""
        return os.urandom(32)

    def test_roundtrip(self, quantum_key: bytes) -> None:
        """Basic encrypt → decrypt round-trip."""
        plaintext = b"AES-256-GCM encrypted with a quantum-derived key"
        enc_msg = quantum_aes.encrypt(plaintext, quantum_key, "key-aes-001")

        assert enc_msg.level == SecurityLevel.QUANTUM_AES
        assert enc_msg.metadata["algorithm"] == "AES-256-GCM"
        assert enc_msg.metadata["key_id"] == "key-aes-001"
        assert "iv" in enc_msg.metadata
        assert "tag" in enc_msg.metadata

        recovered = quantum_aes.decrypt(enc_msg, quantum_key)
        assert recovered == plaintext

    def test_unique_iv_per_call(self, quantum_key: bytes) -> None:
        """Two encryptions of the same plaintext must produce different IVs."""
        plaintext = b"same message twice"
        msg1 = quantum_aes.encrypt(plaintext, quantum_key, "k1")
        msg2 = quantum_aes.encrypt(plaintext, quantum_key, "k2")

        assert msg1.metadata["iv"] != msg2.metadata["iv"]

    def test_tampered_tag_raises(self, quantum_key: bytes) -> None:
        """Flipping a bit in the GCM tag must cause DecryptionError."""
        plaintext = b"tamper-test payload"
        enc_msg = quantum_aes.encrypt(plaintext, quantum_key, "k-tamper")

        # Decode tag, flip a bit, re-encode
        tag_bytes = bytearray(base64.b64decode(enc_msg.metadata["tag"]))
        tag_bytes[0] ^= 0x01
        tampered_meta = dict(enc_msg.metadata)
        tampered_meta["tag"] = base64.b64encode(bytes(tag_bytes)).decode()

        tampered_msg = EncryptedMessage(
            ciphertext=enc_msg.ciphertext,
            metadata=tampered_meta,
            level=enc_msg.level,
        )

        with pytest.raises(DecryptionError, match="tag verification failed"):
            quantum_aes.decrypt(tampered_msg, quantum_key)

    def test_tampered_ciphertext_raises(self, quantum_key: bytes) -> None:
        """Modifying the ciphertext bytes must cause DecryptionError."""
        plaintext = b"integrity check"
        enc_msg = quantum_aes.encrypt(plaintext, quantum_key, "k-ct-tamper")

        bad_ct = bytearray(enc_msg.ciphertext)
        bad_ct[0] ^= 0xFF
        tampered_msg = EncryptedMessage(
            ciphertext=bytes(bad_ct),
            metadata=enc_msg.metadata,
            level=enc_msg.level,
        )

        with pytest.raises(DecryptionError):
            quantum_aes.decrypt(tampered_msg, quantum_key)

    def test_wrong_key_raises(self) -> None:
        """Decrypting with a different key must fail."""
        plaintext = b"wrong key test"
        key1 = os.urandom(32)
        key2 = os.urandom(32)

        enc_msg = quantum_aes.encrypt(plaintext, key1, "k-wrong")

        with pytest.raises(DecryptionError):
            quantum_aes.decrypt(enc_msg, key2)

    def test_empty_plaintext(self, quantum_key: bytes) -> None:
        """Empty plaintext should round-trip correctly."""
        enc_msg = quantum_aes.encrypt(b"", quantum_key, "k-empty")
        assert quantum_aes.decrypt(enc_msg, quantum_key) == b""


class TestQuantumAESViaEngine:
    """Round-trip via the CryptoEngine facade at SecurityLevel.QUANTUM_AES."""

    def test_engine_roundtrip(self) -> None:
        plaintext = b"Engine-level AES test"
        qkd_key = QKDKey(
            key_id="engine-aes-001",
            key=os.urandom(32),
            size_bits=256,
        )

        engine = CryptoEngine()
        enc_msg = engine.encrypt(
            plaintext, SecurityLevel.QUANTUM_AES, key=qkd_key
        )

        assert enc_msg.level == SecurityLevel.QUANTUM_AES
        assert enc_msg.metadata["algorithm"] == "AES-256-GCM"
        assert enc_msg.metadata["key_id"] == "engine-aes-001"
        # No raw key in metadata
        assert "key" not in enc_msg.metadata

        recovered = engine.decrypt(enc_msg, key=qkd_key)
        assert recovered == plaintext

    def test_engine_rejects_missing_key(self) -> None:
        engine = CryptoEngine()
        with pytest.raises(EncryptionError, match="requires a quantum key"):
            engine.encrypt(b"test", SecurityLevel.QUANTUM_AES, key=None)
