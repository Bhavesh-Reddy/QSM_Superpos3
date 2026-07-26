"""End-to-end flow: KM simulator + full backend pipeline, no external network.

What is *real* here:
    * the KM simulator, run in a uvicorn server thread on an ephemeral port and
      reached over real HTTP by a real ``KMClient`` (ETSI 014);
    * the crypto engine (OTP + Quantum-AES), the encrypted key store, and the
      M2a orchestration services (``SendService`` / ``ReceiveService``).

What is *substituted*: the SMTP/IMAP transport, replaced by an in-memory
``LoopbackMailServer``. There is no test mailbox to send to, and email
plumbing is exercised separately in ``tests/test_email_mime.py``; here we swap
it out so the test stays hermetic while every security-critical step (KM key
fetch, encrypt, single-use consume, KM ``dec_keys`` resolution, decrypt) runs
for real.

Two-party realism: Alice (sender) and Bob (receiver) hold *separate* key
stores, so an OTP key consumed in Alice's store must be re-fetched by Bob from
the KM via ``dec_keys`` — exactly the real single-use handoff.

The KM base_url is the only thing pointing at the simulator; swapping in real
QKD hardware is a base_url change and nothing else (see README).
"""

from __future__ import annotations

import base64
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from backend.app.crypto.engine import CryptoEngine
from backend.app.keystore.store import KeyStore
from backend.app.km.client import KMClient
from backend.app.services import ReceiveService, SendService
from core.exceptions import KeyExhaustedError
from core.interfaces import IEmailService
from core.models import EmailMessage, EncryptedMessage, SecurityLevel
from km_simulator.main import app as km_app

FAST_ITERS = 1_000  # keystore KDF rounds — low for test speed, not production


class LoopbackMailServer(IEmailService):
    """In-memory stand-in for SMTP send + IMAP fetch.

    ``send`` captures the ciphertext exactly as the real ``mime_packer`` would
    carry it (``security_metadata["body"]`` envelope) and assigns a message id;
    ``fetch`` replays those messages so ``ReceiveService`` can locate and
    decrypt them — mirroring the real Sender/Receiver round trip.
    """

    def __init__(self) -> None:
        self._inbox: list[EmailMessage] = []
        self._counter = 0

    def send(self, message: EmailMessage, encrypted: EncryptedMessage) -> str:
        self._counter += 1
        message_id = str(self._counter)
        self._inbox.append(
            EmailMessage(
                sender=message.sender,
                recipient=message.recipient,
                subject=message.subject,
                body="",
                security_metadata={
                    "message_id": message_id,
                    "body": {
                        "level": int(encrypted.level),
                        "metadata": dict(encrypted.metadata or {}),
                        "ciphertext_b64": base64.b64encode(encrypted.ciphertext).decode("ascii"),
                    },
                },
            )
        )
        return message_id

    def fetch(self, folder: str = "INBOX", limit: int = 50) -> list[EmailMessage]:
        return list(self._inbox)[-limit:]


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="module")
def km_base_url() -> str:
    """Start the KM simulator in a background uvicorn thread; yield its URL."""
    port = _free_port()
    config = uvicorn.Config(km_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15.0
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api/v1/keys/SAE-TEST/status", timeout=1.0)
            if resp.status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:  # pragma: no cover - only on a startup failure
        server.should_exit = True
        pytest.fail("KM simulator did not become ready")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5.0)


@pytest.mark.integration
@pytest.mark.parametrize("level", [SecurityLevel.OTP, SecurityLevel.QUANTUM_AES])
def test_send_fetch_read_roundtrip(km_base_url: str, tmp_path, level: SecurityLevel) -> None:
    crypto = CryptoEngine()
    km = KMClient(km_base_url, sae_id="SAE-ALICE", verify_tls=False)
    alice_store = KeyStore(tmp_path / f"alice_{int(level)}.enc", "pw-alice", iterations=FAST_ITERS)
    bob_store = KeyStore(tmp_path / f"bob_{int(level)}.enc", "pw-bob", iterations=FAST_ITERS)
    mail = LoopbackMailServer()

    alice = SendService(crypto=crypto, km=km, mail=mail, store=alice_store)
    bob = ReceiveService(crypto=crypto, km=km, mail=mail, store=bob_store)

    body = "Attack at dawn — quantum secured. ✨"

    # --- send (Alice): real KM key fetch -> encrypt -> loopback deliver ---
    sent = alice.send(to="bob@example.com", subject="ops", body=body, level=level)
    assert sent["level"] == level
    assert sent["key_id"] is not None  # levels 1-2 always reference a KM key

    # OTP single-use: Alice's copy is spent after send.
    if level == SecurityLevel.OTP:
        with pytest.raises(KeyExhaustedError):
            alice_store.get(sent["key_id"])

    # --- read (Bob): fetch -> resolve key via KM dec_keys -> decrypt ---
    got = bob.read(sent["message_id"])
    assert got["level"] == level
    assert got["plaintext"].decode("utf-8") == body

    # Bob had to fetch the key from the KM (his store started empty) and cached it.
    assert bob_store.get(sent["key_id"]).key_id == sent["key_id"]


@pytest.mark.integration
def test_plain_level_needs_no_km(km_base_url: str, tmp_path) -> None:
    crypto = CryptoEngine()
    km = KMClient(km_base_url, sae_id="SAE-ALICE", verify_tls=False)
    store = KeyStore(tmp_path / "plain.enc", "pw", iterations=FAST_ITERS)
    mail = LoopbackMailServer()
    alice = SendService(crypto=crypto, km=km, mail=mail, store=store)
    bob = ReceiveService(crypto=crypto, km=km, mail=mail, store=store)

    body = "unencrypted compatibility message"
    sent = alice.send(to="bob@example.com", subject="plain", body=body, level=SecurityLevel.NONE)
    assert sent["key_id"] is None

    got = bob.read(sent["message_id"])
    assert got["plaintext"].decode("utf-8") == body
    assert got["level"] == SecurityLevel.NONE
