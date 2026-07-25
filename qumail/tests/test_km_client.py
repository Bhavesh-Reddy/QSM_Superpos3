"""Tests for M4 KMClient against a stateful httpx mock of an ETSI 014 KM.

The mock stores raw key bytes on ``enc_keys`` and returns the same bytes on
``dec_keys``, so the enc->dec round-trip exercises the client's real base64
decoding and asserts byte-for-byte identity — no live server needed.
"""

import base64
import itertools
import json
import logging
import os

import httpx
import pytest

from backend.app.km.client import KMClient
from core.exceptions import KeyExhaustedError, KeyNotFoundError, KMConnectionError
from core.models import ETSIStatus, QKDKey

BASE_URL = "http://km.test"
SAE_ID = "SAE-ALICE"
PEER_SAE_ID = "SAE-BOB"


class FakeKM:
    """Minimal stateful ETSI 014 KM backing an httpx.MockTransport."""

    def __init__(self, *, empty_enc: bool = False) -> None:
        self.store: dict[str, bytes] = {}
        self._counter = itertools.count(1)
        self._empty_enc = empty_enc

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/status"):
            return httpx.Response(200, json=self._status())
        if path.endswith("/enc_keys"):
            return httpx.Response(200, json=self._enc(json.loads(request.content)))
        if path.endswith("/dec_keys"):
            return self._dec(json.loads(request.content))
        return httpx.Response(404, json={"detail": "not found"})

    def _status(self) -> dict:
        return ETSIStatus(
            source_KME_ID="KME-1",
            target_KME_ID="KME-2",
            master_SAE_ID=SAE_ID,
            slave_SAE_ID=PEER_SAE_ID,
            stored_key_count=len(self.store),
        ).model_dump()

    def _enc(self, body: dict) -> dict:
        if self._empty_enc:
            return {"keys": []}
        keys = []
        for _ in range(body["number"]):
            key_id = f"QK-{next(self._counter):06d}"
            raw = os.urandom(body["size"] // 8)
            self.store[key_id] = raw
            keys.append({"key_ID": key_id, "key": base64.b64encode(raw).decode("ascii")})
        return {"keys": keys}

    def _dec(self, body: dict) -> httpx.Response:
        keys = []
        for entry in body["key_IDs"]:
            key_id = entry["key_ID"]
            if key_id not in self.store:
                return httpx.Response(404, json={"detail": f"unknown key_ID: {key_id}"})
            keys.append(
                {"key_ID": key_id, "key": base64.b64encode(self.store[key_id]).decode("ascii")}
            )
        return httpx.Response(200, json={"keys": keys})


@pytest.fixture
def patch_transport(monkeypatch):
    """Return a factory that binds KMClient's httpx.Client to a mock transport."""

    def _install(transport: httpx.MockTransport) -> KMClient:
        original = httpx.Client

        def factory(*args, **kwargs):
            kwargs.pop("verify", None)
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", factory)
        return KMClient(BASE_URL, SAE_ID, verify_tls=False)

    return _install


class TestRoundTrip:
    def test_enc_then_dec_returns_identical_bytes(self, patch_transport) -> None:
        km = FakeKM()
        client = patch_transport(httpx.MockTransport(km.handler))

        enc_keys = client.get_key(PEER_SAE_ID, number=3, size=256)
        assert len(enc_keys) == 3
        assert all(isinstance(k, QKDKey) for k in enc_keys)
        assert all(len(k.key) == 32 and k.size_bits == 256 for k in enc_keys)

        ids = [k.key_id for k in enc_keys]
        dec_keys = client.get_key_with_ids(SAE_ID, ids)
        dec_by_id = {k.key_id: k.key for k in dec_keys}
        for enc in enc_keys:
            assert dec_by_id[enc.key_id] == enc.key  # identical raw bytes

    def test_get_status_returns_typed_model(self, patch_transport) -> None:
        km = FakeKM()
        client = patch_transport(httpx.MockTransport(km.handler))
        status = client.get_status()
        assert isinstance(status, ETSIStatus)
        assert status.master_SAE_ID == SAE_ID


class TestErrorMapping:
    def test_unknown_key_id_raises_key_not_found(self, patch_transport) -> None:
        km = FakeKM()
        client = patch_transport(httpx.MockTransport(km.handler))
        with pytest.raises(KeyNotFoundError):
            client.get_key_with_ids(SAE_ID, ["QK-999999"])

    def test_empty_enc_response_raises_key_exhausted(self, patch_transport) -> None:
        km = FakeKM(empty_enc=True)
        client = patch_transport(httpx.MockTransport(km.handler))
        with pytest.raises(KeyExhaustedError):
            client.get_key(PEER_SAE_ID, number=1, size=256)

    def test_network_error_maps_to_km_connection_error(self, patch_transport) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = patch_transport(httpx.MockTransport(boom))
        with pytest.raises(KMConnectionError):
            client.get_key(PEER_SAE_ID)

    def test_server_error_maps_to_km_connection_error(self, patch_transport) -> None:
        def server_error(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "boom"})

        client = patch_transport(httpx.MockTransport(server_error))
        with pytest.raises(KMConnectionError):
            client.get_status()


class TestNoKeyBytesInLogs:
    def test_logs_key_ids_not_key_bytes(self, patch_transport, caplog) -> None:
        km = FakeKM()
        client = patch_transport(httpx.MockTransport(km.handler))
        with caplog.at_level(logging.INFO, logger="backend.app.km.client"):
            keys = client.get_key(PEER_SAE_ID, number=1, size=256)
        logged = "\n".join(r.getMessage() for r in caplog.records)
        assert keys[0].key_id in logged  # key_ID is logged
        # Raw/base64 key material must never appear in logs.
        assert base64.b64encode(keys[0].key).decode("ascii") not in logged
