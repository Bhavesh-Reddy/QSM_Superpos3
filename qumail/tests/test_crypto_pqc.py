"""Tests for Level 3 — Post-Quantum Cryptography (ML-KEM-768 + ML-DSA-65).

All tests are skipped if ``liboqs-python`` is not installed.

Covers:
- Key pair generation for KEM and DSA.
- Round-trip encrypt → decrypt with fresh key pairs.
- SignatureVerificationError on tampered ciphertext.
- DecryptionError on wrong recipient key.
- Round-trip through the CryptoEngine facade.
"""

from __future__ import annotations

import pytest

# Skip the entire module if liboqs is not available.
oqs = pytest.importorskip("oqs", reason="liboqs-python not installed")

from backend.app.crypto import pqc  # noqa: E402
from backend.app.crypto.engine import CryptoEngine  # noqa: E402
from core.exceptions import (  # noqa: E402
    DecryptionError,
    EncryptionError,
    SignatureVerificationError,
)
from core.models import EncryptedMessage, SecurityLevel  # noqa: E402


@pytest.fixture()
def kem_keypair() -> tuple[bytes, bytes]:
    """Fresh ML-KEM-768 key pair."""
    return pqc.generate_kem_keypair()


@pytest.fixture()
def sig_keypair() -> tuple[bytes, bytes]:
    """Fresh ML-DSA-65 key pair."""
    return pqc.generate_sig_keypair()


class TestPQCDirect:
    """Direct tests against the pqc module."""

    def test_roundtrip(
        self,
        kem_keypair: tuple[bytes, bytes],
        sig_keypair: tuple[bytes, bytes],
    ) -> None:
        """Encrypt → decrypt should recover the original plaintext."""
        recipient_pk, recipient_sk = kem_keypair
        sender_sig_pk, sender_sig_sk = sig_keypair

        plaintext = b"Post-quantum encrypted message via ML-KEM-768"
        enc_msg = pqc.encrypt(plaintext, recipient_pk, sender_sig_sk)

        assert enc_msg.level == SecurityLevel.PQC
        assert enc_msg.metadata["algorithm"] == "ML-KEM-768+ML-DSA-65"
        assert "ct_kem" in enc_msg.metadata
        assert "iv" in enc_msg.metadata
        assert "tag" in enc_msg.metadata
        assert "signature" in enc_msg.metadata

        recovered = pqc.decrypt(enc_msg, recipient_sk, sender_sig_pk)
        assert recovered == plaintext

    def test_tampered_ciphertext_fails_signature(
        self,
        kem_keypair: tuple[bytes, bytes],
        sig_keypair: tuple[bytes, bytes],
    ) -> None:
        """Modified ciphertext must trigger SignatureVerificationError."""
        recipient_pk, recipient_sk = kem_keypair
        sender_sig_pk, sender_sig_sk = sig_keypair

        plaintext = b"signature integrity test"
        enc_msg = pqc.encrypt(plaintext, recipient_pk, sender_sig_sk)

        # Tamper with ciphertext
        bad_ct = bytearray(enc_msg.ciphertext)
        bad_ct[0] ^= 0xFF
        tampered_msg = EncryptedMessage(
            ciphertext=bytes(bad_ct),
            metadata=enc_msg.metadata,
            level=enc_msg.level,
        )

        with pytest.raises(SignatureVerificationError):
            pqc.decrypt(tampered_msg, recipient_sk, sender_sig_pk)

    def test_wrong_recipient_key_fails(
        self,
        sig_keypair: tuple[bytes, bytes],
    ) -> None:
        """Decrypting with a different recipient's KEM key must fail."""
        sender_sig_pk, sender_sig_sk = sig_keypair

        # Two distinct recipients
        recipient_pk_1, _ = pqc.generate_kem_keypair()
        _, recipient_sk_2 = pqc.generate_kem_keypair()

        plaintext = b"wrong-key test"
        enc_msg = pqc.encrypt(plaintext, recipient_pk_1, sender_sig_sk)

        # Decrypt with wrong secret key — signature might still verify
        # (signature is over ciphertext, independent of KEM), but
        # KEM decapsulation will produce a different shared secret
        # leading to GCM tag failure.
        with pytest.raises((DecryptionError, SignatureVerificationError)):
            pqc.decrypt(enc_msg, recipient_sk_2, sender_sig_pk)

    def test_empty_plaintext(
        self,
        kem_keypair: tuple[bytes, bytes],
        sig_keypair: tuple[bytes, bytes],
    ) -> None:
        """Empty plaintext should round-trip correctly."""
        recipient_pk, recipient_sk = kem_keypair
        sender_sig_pk, sender_sig_sk = sig_keypair

        enc_msg = pqc.encrypt(b"", recipient_pk, sender_sig_sk)
        recovered = pqc.decrypt(enc_msg, recipient_sk, sender_sig_pk)
        assert recovered == b""


class TestPQCViaEngine:
    """Round-trip via the CryptoEngine facade at SecurityLevel.PQC."""

    def test_engine_roundtrip(
        self,
        kem_keypair: tuple[bytes, bytes],
        sig_keypair: tuple[bytes, bytes],
    ) -> None:
        recipient_pk, recipient_sk = kem_keypair
        sender_sig_pk, sender_sig_sk = sig_keypair

        engine = CryptoEngine(sender_signing_key=sender_sig_sk)
        plaintext = b"Engine-level PQC test"
        enc_msg = engine.encrypt(
            plaintext,
            SecurityLevel.PQC,
            recipient_public_key=recipient_pk,
        )

        assert enc_msg.level == SecurityLevel.PQC
        assert enc_msg.metadata["algorithm"] == "ML-KEM-768+ML-DSA-65"

        recovered = engine.decrypt(
            enc_msg,
            private_key=recipient_sk,
            sender_public_key=sender_sig_pk,
        )
        assert recovered == plaintext

    def test_engine_rejects_missing_recipient_pk(
        self,
        sig_keypair: tuple[bytes, bytes],
    ) -> None:
        _, sender_sig_sk = sig_keypair
        engine = CryptoEngine(sender_signing_key=sender_sig_sk)
        with pytest.raises(EncryptionError, match="recipient.*public key"):
            engine.encrypt(b"test", SecurityLevel.PQC)

    def test_engine_rejects_missing_signing_key(
        self,
        kem_keypair: tuple[bytes, bytes],
    ) -> None:
        recipient_pk, _ = kem_keypair
        engine = CryptoEngine()  # no signing key
        with pytest.raises(EncryptionError, match="sender signing key"):
            engine.encrypt(
                b"test",
                SecurityLevel.PQC,
                recipient_public_key=recipient_pk,
            )
