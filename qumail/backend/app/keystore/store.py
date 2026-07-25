"""Encrypted-at-rest quantum key store with OTP single-use (M7).

Keys are cached in a single JSON file where every record is individually
encrypted with AES-256-GCM under a storage key derived from the user's master
password (PBKDF2-HMAC-SHA256, >= 600k iterations, random salt). Raw key bytes
never touch disk in plaintext.

File format::

    {
      "version": 1,
      "kdf": {"algo": "PBKDF2-HMAC-SHA256", "salt": b64, "iterations": N, "dklen": 32},
      "verifier": {"iv": b64, "tag": b64, "ct": b64},   # detects wrong password
      "records": { "<key_ID>": {"iv": b64, "tag": b64, "ct": b64}, ... }
    }

Each record's ``key_ID`` is bound as GCM associated data so ciphertexts cannot
be relabelled or swapped. The ``consumed`` flag lives *inside* the encrypted
record, so single-use state is tamper-evident.

Design note: the prompt describes "salt+iv+tag+ct per record". We keep a single
file-level KDF salt (deriving the storage key once — 600k PBKDF2 rounds per
record would be prohibitive) and store a fresh iv+tag+ct per record. The salt
is persisted in the file header.

No secrets (key bytes, password) are ever logged.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from Crypto.Cipher import AES

from core.exceptions import (
    KeyAlreadyConsumedError,
    KeyExhaustedError,
    KeyNotFoundError,
    KeyStoreError,
)
from core.interfaces import IKeyStore
from core.models import QKDKey

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 600_000
_SALT_LEN = 16
_IV_LEN = 12
_STORAGE_KEY_LEN = 32
_VERIFIER_PLAINTEXT = b"QUMAIL-KEYSTORE-V1"
_VERIFIER_AAD = b"verifier"
_FILE_VERSION = 1


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(data: str) -> bytes:
    return base64.b64decode(data)


class KeyStore(IKeyStore):
    """AES-256-GCM encrypted key cache enforcing OTP single-use."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        master_password: str,
        iterations: int = PBKDF2_ITERATIONS,
    ) -> None:
        """Open an existing store or create a new one.

        Args:
            path: Path to the encrypted store file.
            master_password: Password used to derive the storage key.
            iterations: PBKDF2 iteration count for a *new* store (must be
                >= 600k for production; lower only for tests). Existing stores
                use the iteration count recorded in their header.

        Raises:
            KeyStoreError: If an existing store cannot be opened (e.g. wrong
                password or corrupt file).
        """
        self._path = Path(path)
        self._keys: dict[str, QKDKey] = {}
        password = master_password.encode("utf-8")
        try:
            if self._path.exists():
                self._load(password)
            else:
                self._init_new(password, iterations)
        finally:
            del password  # drop the plaintext password reference promptly

    # -- key derivation & record crypto ------------------------------------- #

    @staticmethod
    def _derive(password: bytes, salt: bytes, iterations: int) -> bytes:
        """Derive the 32-byte storage key via PBKDF2-HMAC-SHA256."""
        return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, _STORAGE_KEY_LEN)

    def _encrypt(self, plaintext: bytes, aad: bytes) -> dict[str, str]:
        """Encrypt ``plaintext`` under the storage key with a fresh nonce.

        Args:
            plaintext: Bytes to encrypt.
            aad: Associated data to authenticate (not encrypted).

        Returns:
            A ``{iv, tag, ct}`` record with base64 values.
        """
        iv = os.urandom(_IV_LEN)
        cipher = AES.new(self._storage_key, AES.MODE_GCM, nonce=iv)
        cipher.update(aad)
        ct, tag = cipher.encrypt_and_digest(plaintext)
        return {"iv": _b64e(iv), "tag": _b64e(tag), "ct": _b64e(ct)}

    def _decrypt(self, record: dict[str, str], aad: bytes) -> bytes:
        """Decrypt and verify a ``{iv, tag, ct}`` record.

        Args:
            record: The encrypted record.
            aad: Associated data that must match what was used to encrypt.

        Returns:
            The recovered plaintext.

        Raises:
            ValueError: If authentication fails (wrong key or tampering).
        """
        cipher = AES.new(self._storage_key, AES.MODE_GCM, nonce=_b64d(record["iv"]))
        cipher.update(aad)
        return cipher.decrypt_and_verify(_b64d(record["ct"]), _b64d(record["tag"]))

    # -- load / init -------------------------------------------------------- #

    def _init_new(self, password: bytes, iterations: int) -> None:
        """Create a fresh, empty encrypted store on disk."""
        self._salt = os.urandom(_SALT_LEN)
        self._iterations = iterations
        self._storage_key = self._derive(password, self._salt, iterations)
        self._verifier = self._encrypt(_VERIFIER_PLAINTEXT, _VERIFIER_AAD)
        self._persist()
        logger.info("created new key store at %s", self._path)

    def _load(self, password: bytes) -> None:
        """Load and decrypt an existing store, verifying the password.

        Raises:
            KeyStoreError: On malformed file, wrong password, or corrupt record.
        """
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            kdf = data["kdf"]
            self._salt = _b64d(kdf["salt"])
            self._iterations = int(kdf["iterations"])
            self._verifier = data["verifier"]
            records = data["records"]
        except (ValueError, KeyError, TypeError) as exc:
            raise KeyStoreError(f"malformed key store file: {exc}") from exc

        self._storage_key = self._derive(password, self._salt, self._iterations)

        # Verify the password before trusting any record.
        try:
            if self._decrypt(self._verifier, _VERIFIER_AAD) != _VERIFIER_PLAINTEXT:
                raise ValueError("verifier mismatch")
        except ValueError as exc:
            raise KeyStoreError("failed to open key store (wrong password?)") from exc

        for key_id, record in records.items():
            try:
                payload = json.loads(self._decrypt(record, key_id.encode("utf-8")))
            except ValueError as exc:
                raise KeyStoreError(f"corrupt record for {key_id}") from exc
            self._keys[key_id] = self._payload_to_key(payload)
        logger.info("opened key store at %s (%d record(s))", self._path, len(self._keys))

    # -- (de)serialization -------------------------------------------------- #

    @staticmethod
    def _key_to_payload(key: QKDKey) -> dict[str, object]:
        return {
            "key_id": key.key_id,
            "key": _b64e(key.key),
            "size_bits": key.size_bits,
            "consumed": key.consumed,
            "created_at": key.created_at.isoformat(),
        }

    @staticmethod
    def _payload_to_key(payload: dict) -> QKDKey:
        return QKDKey(
            key_id=payload["key_id"],
            key=_b64d(payload["key"]),
            size_bits=int(payload["size_bits"]),
            consumed=bool(payload["consumed"]),
            created_at=datetime.fromisoformat(payload["created_at"]),
        )

    def _persist(self) -> None:
        """Encrypt all records and write the store atomically (temp + rename)."""
        document = {
            "version": _FILE_VERSION,
            "kdf": {
                "algo": "PBKDF2-HMAC-SHA256",
                "salt": _b64e(self._salt),
                "iterations": self._iterations,
                "dklen": _STORAGE_KEY_LEN,
            },
            "verifier": self._verifier,
            "records": {
                key_id: self._encrypt(
                    json.dumps(self._key_to_payload(key)).encode("utf-8"),
                    key_id.encode("utf-8"),
                )
                for key_id, key in self._keys.items()
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._path)  # atomic on Windows and POSIX
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

    def _secure_overwrite(self) -> None:
        """Best-effort overwrite of the current file's bytes before removal.

        Note: on journaling filesystems / SSDs with wear-levelling this cannot
        guarantee erasure; records are encrypted regardless, so this only adds
        defence in depth against recovery of the (already-ciphertext) file.
        """
        if not self._path.exists():
            return
        size = self._path.stat().st_size
        with open(self._path, "r+b") as handle:
            handle.seek(0)
            handle.write(os.urandom(size))
            handle.flush()
            os.fsync(handle.fileno())

    # -- IKeyStore API ------------------------------------------------------ #

    def put(self, key: QKDKey) -> None:
        """Cache a key and persist the store.

        Args:
            key: The key to store; overwrites any existing entry with the same
                ``key_id``.
        """
        self._keys[key.key_id] = key.model_copy()
        self._persist()
        logger.info("stored key %s (%d bits)", key.key_id, key.size_bits)

    def get(self, key_id: str) -> QKDKey:
        """Return a stored key without consuming it.

        Args:
            key_id: The KM-assigned key ID.

        Returns:
            A copy of the stored key.

        Raises:
            KeyNotFoundError: If ``key_id`` is not present.
            KeyExhaustedError: If the key was already consumed (single-use).
        """
        key = self._keys.get(key_id)
        if key is None:
            raise KeyNotFoundError(f"no key with id {key_id}")
        if key.consumed:
            raise KeyExhaustedError(f"key {key_id} already consumed")
        return key.model_copy()

    def consume(self, key_id: str) -> QKDKey:
        """Mark a key consumed and persist the flag (atomic single-use).

        Args:
            key_id: The KM-assigned key ID.

        Returns:
            The key, now flagged consumed (return this copy to use the bytes).

        Raises:
            KeyNotFoundError: If ``key_id`` is not present.
            KeyAlreadyConsumedError: If the key was already consumed.
        """
        key = self._keys.get(key_id)
        if key is None:
            raise KeyNotFoundError(f"no key with id {key_id}")
        if key.consumed:
            raise KeyAlreadyConsumedError(f"key {key_id} already consumed")
        key.consumed = True
        self._persist()
        logger.info("consumed key %s", key_id)
        return key.model_copy()

    def delete(self, key_id: str) -> None:
        """Remove a key, overwriting the old file bytes (best-effort secure erase).

        Args:
            key_id: The KM-assigned key ID.

        Raises:
            KeyNotFoundError: If ``key_id`` is not present.
        """
        if key_id not in self._keys:
            raise KeyNotFoundError(f"no key with id {key_id}")
        del self._keys[key_id]
        self._secure_overwrite()
        self._persist()
        logger.info("deleted key %s", key_id)
