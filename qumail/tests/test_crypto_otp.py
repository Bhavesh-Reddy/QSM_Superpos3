"""Tests for Level 1 — Quantum OTP (XOR cipher).

Covers:
- Round-trip encrypt → decrypt with equal-length key.
- Round-trip with key longer than plaintext.
- EncryptionError when key is too short.
- DecryptionError when key is too short for ciphertext.
- Round-trip through the CryptoEngine facade.
"""

from __future__ import annotations

import os

import pytest

from backend.app.crypto import otp
from backend.app.crypto.engine import CryptoEngine
from core.exceptions import DecryptionError, EncryptionError
from core.models import QKDKey, SecurityLevel


class TestOTPDirect:
    """Direct tests against the otp module (no facade)."""

    def test_roundtrip_equal_length(self) -> None:
        """Encrypt then decrypt with a key the same length as plaintext."""
        plaintext = b"hello quantum world!"
        key = os.urandom(len(plaintext))

        ct = otp.encrypt(plaintext, key)
        assert ct != plaintext, "ciphertext should differ from plaintext"
        assert len(ct) == len(plaintext)

        recovered = otp.decrypt(ct, key)
        assert recovered == plaintext

    def test_roundtrip_longer_key(self) -> None:
        """Key may be longer than plaintext — extra bytes are unused."""
        plaintext = b"short"
        key = os.urandom(len(plaintext) + 100)

        ct = otp.encrypt(plaintext, key)
        recovered = otp.decrypt(ct, key)
        assert recovered == plaintext

    def test_encrypt_rejects_short_key(self) -> None:
        """OTP must raise EncryptionError if key < plaintext."""
        plaintext = b"this is too long for the key"
        key = os.urandom(5)

        with pytest.raises(EncryptionError, match="OTP key too short"):
            otp.encrypt(plaintext, key)

    def test_decrypt_rejects_short_key(self) -> None:
        """Decrypt must raise DecryptionError if key < ciphertext."""
        ciphertext = b"some ciphertext bytes"
        key = os.urandom(3)

        with pytest.raises(DecryptionError, match="OTP key too short"):
            otp.decrypt(ciphertext, key)

    def test_empty_plaintext(self) -> None:
        """Empty plaintext should encrypt / decrypt to empty bytes."""
        key = os.urandom(32)
        ct = otp.encrypt(b"", key)
        assert ct == b""
        assert otp.decrypt(ct, key) == b""

    def test_xor_correctness(self) -> None:
        """Verify that encryption is truly XOR."""
        plaintext = bytes([0x00, 0xFF, 0xAA, 0x55])
        key = bytes([0xFF, 0x00, 0x55, 0xAA])
        expected = bytes([0xFF, 0xFF, 0xFF, 0xFF])

        ct = otp.encrypt(plaintext, key)
        assert ct == expected


class TestOTPViaEngine:
    """Round-trip via the CryptoEngine facade at SecurityLevel.OTP."""

    def test_engine_roundtrip(self) -> None:
        plaintext = b"Quantum-secured one-time pad message"
        qkd_key = QKDKey(
            key_id="test-otp-key-001",
            key=os.urandom(len(plaintext)),
            size_bits=len(plaintext) * 8,
        )

        engine = CryptoEngine()
        enc_msg = engine.encrypt(plaintext, SecurityLevel.OTP, key=qkd_key)

        assert enc_msg.level == SecurityLevel.OTP
        assert enc_msg.metadata["algorithm"] == "OTP"
        assert enc_msg.metadata["key_id"] == "test-otp-key-001"
        assert enc_msg.metadata["plaintext_length"] == len(plaintext)
        # Metadata must NOT contain the key itself
        assert "key" not in enc_msg.metadata

        recovered = engine.decrypt(enc_msg, key=qkd_key)
        assert recovered == plaintext

    def test_engine_rejects_missing_key(self) -> None:
        engine = CryptoEngine()
        with pytest.raises(EncryptionError, match="requires a quantum key"):
            engine.encrypt(b"test", SecurityLevel.OTP, key=None)
