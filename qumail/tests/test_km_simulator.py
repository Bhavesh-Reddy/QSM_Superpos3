"""Tests for M6 KM simulator: ETSI 014 endpoints, QRNG, and BB84.

Uses FastAPI's httpx-backed TestClient to exercise the ASGI app in-process
(no live server needed).
"""

import base64

import pytest
from fastapi.testclient import TestClient

from km_simulator import bb84, qrng
from km_simulator.main import app

client = TestClient(app)

SAE_ID = "SAE-BOB"


class TestStatusEndpoint:
    def test_status_shape(self) -> None:
        resp = client.get(f"/api/v1/keys/{SAE_ID}/status")
        assert resp.status_code == 200
        body = resp.json()
        # ETSI 014 status fields (exact names).
        for field in (
            "source_KME_ID",
            "target_KME_ID",
            "master_SAE_ID",
            "slave_SAE_ID",
            "key_size",
            "stored_key_count",
            "max_key_per_request",
        ):
            assert field in body, field
        assert body["slave_SAE_ID"] == SAE_ID


class TestEncDecRoundTrip:
    def test_enc_then_dec_returns_same_key_bytes(self) -> None:
        # enc_keys: request 3 keys of 256 bits.
        enc = client.post(
            f"/api/v1/keys/{SAE_ID}/enc_keys", json={"number": 3, "size": 256}
        )
        assert enc.status_code == 200
        enc_keys = enc.json()["keys"]
        assert len(enc_keys) == 3
        for entry in enc_keys:
            assert entry["key_ID"].startswith("QK-")
            assert len(entry["key_ID"]) == len("QK-") + 6  # zero-padded counter
            # 256-bit key -> 32 bytes -> base64 decodes cleanly.
            assert len(base64.b64decode(entry["key"])) == 32

        # dec_keys: redeem the returned IDs, expect identical key material.
        key_ids = [{"key_ID": e["key_ID"]} for e in enc_keys]
        dec = client.post(
            f"/api/v1/keys/{SAE_ID}/dec_keys", json={"key_IDs": key_ids}
        )
        assert dec.status_code == 200
        dec_keys = {e["key_ID"]: e["key"] for e in dec.json()["keys"]}
        for entry in enc_keys:
            assert dec_keys[entry["key_ID"]] == entry["key"]

    def test_dec_unknown_key_id_returns_404(self) -> None:
        resp = client.post(
            f"/api/v1/keys/{SAE_ID}/dec_keys",
            json={"key_IDs": [{"key_ID": "QK-999999"}]},
        )
        assert resp.status_code == 404

    def test_enc_rejects_bad_size(self) -> None:
        resp = client.post(
            f"/api/v1/keys/{SAE_ID}/enc_keys", json={"number": 1, "size": 100}
        )
        assert resp.status_code == 400


class TestQRNG:
    def test_get_random_key_length(self) -> None:
        key = qrng.get_random_key(256)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_generate_random_bits_values(self) -> None:
        bits = qrng.generate_random_bits(64)
        assert len(bits) == 64
        assert set(bits) <= {0, 1}

    def test_rejects_non_multiple_of_8(self) -> None:
        with pytest.raises(ValueError):
            qrng.get_random_key(100)


class TestBB84:
    def test_noiseless_run_has_low_qber(self) -> None:
        result = bb84.simulate_bb84(n_qubits=512, eavesdropper=False)
        # Without an eavesdropper, sifted bits agree -> QBER ~ 0.
        assert result.qber == 0.0
        assert result.raw_length == 512
        assert 0 < result.sifted_length <= 512

    def test_eavesdropper_raises_qber(self) -> None:
        result = bb84.simulate_bb84(n_qubits=1024, eavesdropper=True)
        # Intercept-resend injects errors; QBER should be clearly non-zero.
        assert result.qber > 0.1
