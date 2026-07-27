"""M6 — ETSI GS QKD 014 Key Manager simulator (FastAPI, dev only).

Exposes the three ETSI 014 endpoints from CLAUDE.md section 8. Keys are
generated from the QRNG (:mod:`km_simulator.qrng`) and held in an in-memory
store keyed by ``key_ID``; a master SAE requests ``enc_keys`` and shares the
returned IDs with the peer, who redeems them via ``dec_keys``.

Wire field names are fixed by the standard (``key_ID``, ``key``, ``number``,
``size``, ``key_IDs``) and reused from ``core.models`` so client and simulator
never drift. Base64 is used to carry raw key bytes as JSON strings.

Run: ``python -m km_simulator.main``  (serves on http://127.0.0.1:8100)
"""

from __future__ import annotations

import base64
import itertools
import logging
import os
import threading

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from core.models import (
    ETSIKey,
    ETSIKeyContainer,
    ETSIKeyIDsRequest,
    ETSIKeyRequest,
    ETSIStatus,
)
from km_simulator import qrng

logger = logging.getLogger(__name__)

# Simulator identity (would be provisioned per-KME in a real deployment).
SOURCE_KME_ID = "KME-SIM-001"
TARGET_KME_ID = "KME-SIM-002"
MASTER_SAE_ID = "SAE-MASTER"
DEFAULT_KEY_SIZE_BITS = 256
MAX_KEYS_PER_REQUEST = 128
PORT = 8100

app = FastAPI(
    title="QuMail KM Simulator",
    description="ETSI GS QKD 014-compliant Key Manager simulator (development only).",
    version="0.1.0",
)

# CORS: allow the Electron/Vite frontend and local backend to call the sim.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:8000",  # QuMail backend
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _KeyVault:
    """Thread-safe in-memory key store keyed by ``key_ID``.

    Not persistent and not encrypted — this is a development stand-in for real
    QKD hardware. The client-side KeyStore (M7) is the component responsible
    for encrypted-at-rest caching and OTP one-time-use enforcement.
    """

    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def create_keys(self, number: int, size_bits: int) -> list[ETSIKey]:
        """Generate and store ``number`` keys of ``size_bits`` bits each.

        Args:
            number: How many keys to generate.
            size_bits: Size of each key in bits.

        Returns:
            The new keys as ETSI entries with base64-encoded material.
        """
        created: list[ETSIKey] = []
        with self._lock:
            for _ in range(number):
                key_id = f"QK-{next(self._counter):06d}"
                key_bytes = qrng.get_random_key(size_bits)
                self._keys[key_id] = key_bytes
                created.append(
                    ETSIKey(
                        key_ID=key_id,
                        key=base64.b64encode(key_bytes).decode("ascii"),
                    )
                )
        return created

    def lookup(self, key_ids: list[str]) -> list[ETSIKey]:
        """Return stored keys matching ``key_ids`` (base64-encoded).

        Args:
            key_ids: The ``key_ID`` values to look up.

        Returns:
            Matching keys, one per requested ID.

        Raises:
            KeyError: If any requested ``key_ID`` is unknown.
        """
        found: list[ETSIKey] = []
        with self._lock:
            for key_id in key_ids:
                if key_id not in self._keys:
                    raise KeyError(key_id)
                found.append(
                    ETSIKey(
                        key_ID=key_id,
                        key=base64.b64encode(self._keys[key_id]).decode("ascii"),
                    )
                )
        return found

    @property
    def stored_count(self) -> int:
        """Number of keys currently held."""
        with self._lock:
            return len(self._keys)


vault = _KeyVault()


# TODO(auth): ETSI 014 secures endpoints with mutual TLS + SAE certificates.
# The simulator runs open for dev; add an auth dependency here before any
# non-local deployment (e.g. verify a client cert / bearer token per SAE).
def _authorize(sae_id: str) -> None:
    """Authorization hook (no-op in the simulator).

    Args:
        sae_id: The calling SAE's ID.
    """
    return None


@app.get("/api/v1/keys/{sae_id}/status", response_model=ETSIStatus)
def get_status(sae_id: str) -> ETSIStatus:
    """Report key availability for a peer SAE (ETSI 014 ``status``).

    Args:
        sae_id: The peer (slave) SAE ID.

    Returns:
        The KM status document.
    """
    _authorize(sae_id)
    return ETSIStatus(
        source_KME_ID=SOURCE_KME_ID,
        target_KME_ID=TARGET_KME_ID,
        master_SAE_ID=MASTER_SAE_ID,
        slave_SAE_ID=sae_id,
        key_size=DEFAULT_KEY_SIZE_BITS,
        stored_key_count=vault.stored_count,
        max_key_per_request=MAX_KEYS_PER_REQUEST,
    )


@app.post("/api/v1/keys/{sae_id}/enc_keys", response_model=ETSIKeyContainer)
def post_enc_keys(sae_id: str, request: ETSIKeyRequest) -> ETSIKeyContainer:
    """Generate fresh keys for encrypting toward a peer (ETSI 014 ``enc_keys``).

    Args:
        sae_id: The peer (slave) SAE ID the keys are destined for.
        request: ``{number, size}`` — count and per-key bit size.

    Returns:
        A key container with the generated keys (base64-encoded).

    Raises:
        HTTPException: 400 if ``number``/``size`` are out of range.
    """
    _authorize(sae_id)
    if request.number < 1 or request.number > MAX_KEYS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"number must be between 1 and {MAX_KEYS_PER_REQUEST}",
        )
    if request.size <= 0 or request.size % 8 != 0:
        raise HTTPException(
            status_code=400, detail="size must be a positive multiple of 8"
        )
    keys = vault.create_keys(number=request.number, size_bits=request.size)
    logger.info("enc_keys: issued %d key(s) of %d bits to %s", request.number, request.size, sae_id)
    return ETSIKeyContainer(keys=keys)


@app.post("/api/v1/keys/{sae_id}/dec_keys", response_model=ETSIKeyContainer)
def post_dec_keys(sae_id: str, request: ETSIKeyIDsRequest) -> ETSIKeyContainer:
    """Return keys matching the supplied IDs (ETSI 014 ``dec_keys``).

    Args:
        sae_id: The master SAE ID that originally requested the keys.
        request: ``{key_IDs:[{key_ID}]}`` — the IDs shared over email metadata.

    Returns:
        A key container with the matching keys (base64-encoded).

    Raises:
        HTTPException: 404 if any requested ``key_ID`` is unknown.
    """
    _authorize(sae_id)
    requested = [entry.key_ID for entry in request.key_IDs]
    try:
        keys = vault.lookup(requested)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown key_ID: {exc.args[0]}"
        ) from exc
    logger.info("dec_keys: served %d key(s) to %s", len(keys), sae_id)
    return ETSIKeyContainer(keys=keys)


def main() -> None:
    """Run the simulator with uvicorn.

    Host/port come from the environment so one teammate can host a *shared*
    KM that others reach over the network:

        QUMAIL_KM_HOST  bind address (default 127.0.0.1; set 0.0.0.0 to share)
        QUMAIL_KM_PORT  port (default 8100)
    """
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("QUMAIL_KM_HOST", "127.0.0.1")
    port = int(os.environ.get("QUMAIL_KM_PORT", PORT))
    logger.info("KM simulator binding on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
