"""Tests for M7 KeyStore: encrypted-at-rest cache + OTP single-use.

Uses a low PBKDF2 iteration count for speed (production defaults to 600k); the
iteration count is a construction parameter, not a weakening of the default.
"""

import pytest

from backend.app.keystore.store import KeyStore
from core.exceptions import (
    KeyAlreadyConsumedError,
    KeyExhaustedError,
    KeyNotFoundError,
    KeyStoreError,
)
from core.models import QKDKey

FAST_ITERS = 1_000  # keep the suite quick; real usage uses PBKDF2_ITERATIONS
PASSWORD = "correct horse battery staple"


def _key(key_id: str = "QK-000001", raw: bytes = b"\xa5" * 32) -> QKDKey:
    return QKDKey(key_id=key_id, key=raw, size_bits=len(raw) * 8)


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "keys.enc"


class TestRoundTrip:
    def test_put_then_get(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        original = _key(raw=bytes(range(32)))
        store.put(original)

        fetched = store.get(original.key_id)
        assert fetched.key == original.key
        assert fetched.size_bits == 256
        assert fetched.consumed is False

    def test_get_missing_raises(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        with pytest.raises(KeyNotFoundError):
            store.get("QK-404")

    def test_persists_across_reopen(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        store.put(_key(raw=bytes(range(32))))
        del store

        reopened = KeyStore(store_path, PASSWORD)  # iterations read from header
        assert reopened.get("QK-000001").key == bytes(range(32))


class TestSingleUse:
    def test_consume_then_get_raises_key_exhausted(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        store.put(_key())

        consumed = store.consume("QK-000001")
        assert consumed.consumed is True
        assert consumed.key == b"\xa5" * 32  # material still usable once

        with pytest.raises(KeyExhaustedError):
            store.get("QK-000001")

    def test_double_consume_raises(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        store.put(_key())
        store.consume("QK-000001")
        with pytest.raises(KeyAlreadyConsumedError):
            store.consume("QK-000001")

    def test_consumed_flag_survives_reopen(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        store.put(_key())
        store.consume("QK-000001")
        del store

        reopened = KeyStore(store_path, PASSWORD)
        with pytest.raises(KeyExhaustedError):
            reopened.get("QK-000001")


class TestEncryptionAtRest:
    def test_wrong_password_fails_to_open(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        store.put(_key())
        del store

        with pytest.raises(KeyStoreError):
            KeyStore(store_path, "wrong password")

    def test_raw_key_bytes_never_on_disk(self, store_path) -> None:
        secret = bytes(range(32))
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        store.put(_key(raw=secret))

        blob = store_path.read_bytes()
        assert secret not in blob  # ciphertext only; no plaintext key material

    def test_corrupt_file_raises(self, store_path) -> None:
        store_path.write_text("not json at all")
        with pytest.raises(KeyStoreError):
            KeyStore(store_path, PASSWORD)


class TestDelete:
    def test_delete_removes_key(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        store.put(_key())
        store.delete("QK-000001")
        with pytest.raises(KeyNotFoundError):
            store.get("QK-000001")

    def test_delete_missing_raises(self, store_path) -> None:
        store = KeyStore(store_path, PASSWORD, iterations=FAST_ITERS)
        with pytest.raises(KeyNotFoundError):
            store.delete("QK-404")
