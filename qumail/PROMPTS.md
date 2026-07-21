# QuMail — Per-Module Task Prompts

Use these one at a time in Claude Code **after** the bootstrap (MASTER_PROMPT.md) completes.
Every prompt assumes `CLAUDE.md` is in the repo and already read. Each follows the same shape:
**Persona · Goal · Inputs · Constraints · Output/Format · Tests.**

Recommended order: **core → M6 → M4 → M3 → M7 → M5 → M2 → M1 → integration.**

---

## PROMPT A — core/ contracts (do first)

```
Per CLAUDE.md. Implement core/ fully.

Goal: shared contracts every module depends on.
Files: core/models.py, core/interfaces.py, core/exceptions.py.

Requirements:
- models.py (pydantic v2): SecurityLevel(IntEnum: OTP=1, QUANTUM_AES=2, PQC=3, NONE=4);
  QKDKey(key_id:str, key:bytes, size_bits:int); EncryptedMessage(ciphertext:bytes, metadata:dict, level:SecurityLevel);
  EmailMessage(sender, recipient, subject, body, attachments, timestamp, security_metadata).
- interfaces.py (ABC/Protocol): ICryptoEngine.encrypt/decrypt; IKMClient.get_status/get_key/get_key_with_ids;
  IEmailService.send/fetch; IKeyStore.put/get/consume.
- exceptions.py: base QuMailError + KMConnectionError, KeyExhaustedError, KeyNotFoundError, DecryptionError, EmailError, ConfigError.

Format: type hints + Google docstrings. No logic beyond validation.
Tests: test_core_models.py — construct each model, assert enum values, assert validation errors on bad input.
Then print the pytest command.
```

---

## PROMPT B — M6 KM Simulator (Qiskit, ETSI 014)

```
Per CLAUDE.md. Implement km_simulator/ as a standalone FastAPI service.

Goal: an ETSI GS QKD 014-compliant Key Manager for development, generating keys via Qiskit QRNG.
Files: km_simulator/main.py, qrng.py, bb84.py.

Requirements:
- qrng.py: generate_random_bits(n) using a Qiskit circuit (Hadamard on each qubit, measure) with Aer simulator;
  fall back to secrets.token_bytes if Qiskit unavailable, logging a warning. Expose get_random_key(size_bits)->bytes.
- bb84.py: simulate BB84 between Alice/Bob (prepare in random bases, measure, sift, estimate QBER). Return sifted key + QBER.
  This doubles as an educational module for the demo.
- main.py: FastAPI with exactly these endpoints (match CLAUDE.md §8):
  GET  /api/v1/keys/{sae_id}/status
  POST /api/v1/keys/{sae_id}/enc_keys   -> generate N keys of `size` bits, store in an in-memory dict keyed by key_ID, return {keys:[{key_ID, key(b64)}]}
  POST /api/v1/keys/{sae_id}/dec_keys   -> look up requested key_IDs, return matching {key_ID, key(b64)}
- key_ID format: "QK-XXXXXX" (zero-padded counter). Base64-encode key bytes.
- CORS enabled for localhost. Runs on port 8100.

Constraints: field names must match ETSI 014 exactly (key_ID, key, number, size, key_IDs). No auth in sim, but leave a TODO hook.
Tests: test_km_simulator.py with httpx — request enc_keys, then dec_keys with returned IDs, assert same key bytes; assert status shape.
Print run + test commands.
```

---

## PROMPT C — M4 KM Client (ETSI 014 REST client)

```
Per CLAUDE.md. Implement backend/app/km/client.py implementing IKMClient.

Goal: talk to a KM (the simulator now, real hardware later) over ETSI 014.
Requirements:
- KMClient(base_url, sae_id, verify_tls=True). Methods:
  get_status() -> dict
  get_key(target_sae_id, number=1, size=256) -> list[QKDKey]   (POST enc_keys)
  get_key_with_ids(source_sae_id, key_ids) -> list[QKDKey]      (POST dec_keys)
- Use httpx with timeouts. Decode base64 `key` into bytes; wrap in core.models.QKDKey.
- Raise KMConnectionError on network/HTTP errors, KeyNotFoundError when a requested ID is missing.
- No key bytes in logs — log key_IDs and sizes only.

Constraints: depend only on core interfaces/models. Config (base_url, sae_id) comes from app.config.
Tests: test_km_client.py — spin the simulator or mock httpx; assert round-trip enc->dec returns identical bytes; assert errors map correctly.
Print test command.
```

---

## PROMPT D — M3 Crypto Engine (all 4 levels)

```
Per CLAUDE.md §7. Implement backend/app/crypto/ implementing ICryptoEngine.

Goal: correct, tested encryption for all four levels behind one facade.
Files: engine.py (facade), otp.py, quantum_aes.py, pqc.py, kdf.py.

Requirements:
- kdf.py: hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes (use PyCryptodome HKDF).
- otp.py: encrypt(plaintext, key) XOR with strict length check (raise if key shorter); decrypt symmetric.
- quantum_aes.py: derive AES-256 key via HKDF from quantum key; AES-256-GCM with random 12-byte IV; return ct + store iv/tag(b64) in metadata; verify tag on decrypt.
- pqc.py: use liboqs-python. ML-KEM-768 encapsulate/decapsulate for the AES key; ML-DSA-65 sign(ct)/verify. If liboqs missing, raise a clear ConfigError with install hint (do NOT fake it).
- engine.py: CryptoEngine.encrypt(plaintext, level, quantum_key=None, key_id=None, recipient_pk=None, sender_sk=None) and decrypt(enc_msg, quantum_key=None, ...). Dispatch on SecurityLevel. Return core.models.EncryptedMessage.

Constraints: random IV/nonce every call; never log key bytes; typed exceptions; no plaintext in metadata.
Tests: test_crypto_otp/aes/pqc.py — round-trip each level; OTP rejects short key; AES rejects tampered tag; PQC verify fails on modified ciphertext.
Print test command.
```

---

## PROMPT E — M7 KeyStore (encrypted at rest, OTP one-time use)

```
Per CLAUDE.md. Implement backend/app/keystore/store.py implementing IKeyStore.

Goal: cache quantum keys encrypted at rest and enforce OTP single-use.
Requirements:
- KeyStore(path, master_password): derive a storage key via PBKDF2-HMAC-SHA256 (>=600k iterations, random salt).
- put(qkd_key), get(key_id) -> QKDKey, consume(key_id) marks a key used (persist a 'consumed' flag).
- On get for an already-consumed OTP key, raise KeyExhaustedError.
- Persist to an encrypted file (AES-256-GCM); never store raw keys in plaintext. Store salt+iv+tag+ct per record.
- Secure-delete: overwrite record bytes before removal where feasible.

Constraints: no secrets in logs; atomic writes (temp file + rename).
Tests: test_keystore.py — put/get round-trip; consume then get raises KeyExhaustedError; wrong password fails to open.
Print test command.
```

---

## PROMPT F — M5 Email Service (SMTP/IMAP + .qenc MIME)

```
Per CLAUDE.md. Implement backend/app/email_svc/ implementing IEmailService.

Goal: send/receive mail via Gmail/Yahoo/Outlook, carrying QuMail ciphertext as MIME parts.
Files: sender.py (SMTP), receiver.py (IMAP), mime_packer.py.

Requirements:
- Provider presets (smtp/imap host+port) for gmail/yahoo/outlook; auto-detect from address domain.
- mime_packer.build(...): multipart with (a) a plain-text notice for non-QuMail clients, (b) an application/octet-stream part 'qumail_body.qenc' holding ciphertext, with headers X-QuMail-Type and X-QuMail-Metadata (JSON). Attachments similarly as '<name>.qenc'.
- mime_packer.parse(raw): detect [QuMail] messages, extract ciphertext + metadata + attachments.
- sender.send_quantum_email(...) and send_plain(...); receiver.fetch(folder='INBOX', limit=50) -> list[EmailMessage].
- Use STARTTLS/SSL; creds from config; app-password friendly.

Constraints: never send raw keys in mail — only key_IDs live in metadata. Handle auth errors -> EmailError.
Tests: test_email_mime.py — build then parse round-trip preserves ciphertext + metadata (no live network needed).
Print test command.
```

---

## PROMPT G — M2 API wiring (FastAPI)

```
Per CLAUDE.md. Implement backend/app/api/ routers and wire modules in backend/main.py.

Goal: thin REST layer the frontend calls; orchestrates encrypt-then-send and fetch-then-decrypt.
Endpoints (see docs/api_contract.md — create it):
- POST /auth/km {base_url, sae_id}        -> connect KMClient, return status
- POST /auth/email {email, password, provider} -> connect EmailService
- POST /mail/send {to, subject, body, level, attachments?} -> get key (if L1/L2), encrypt, send; return {message_id, key_id, level}
- GET  /mail/fetch?folder=INBOX&limit=50  -> list summaries (never include key bytes)
- POST /mail/read {message_id}            -> fetch, pull key via dec_keys, decrypt, return plaintext + metadata
- GET  /keys/status                       -> KM status

Constraints: routers stay thin; all logic via M3/M4/M5/M7. Map typed exceptions to HTTP codes (KMConnectionError->502, KeyExhaustedError->409, DecryptionError->400, EmailError->502). Secrets from config, not query params in logs.
Tests: httpx TestClient smoke tests for each route with modules mocked.
Print run + test commands.
```

---

## PROMPT H — M1 Frontend (Electron + React)

```
Per CLAUDE.md. Implement frontend/ (React + Tailwind + Electron) calling the backend API.

Goal: a clean desktop GUI — inbox, compose (with security-level selector), settings (KM + email login), connection status, alerts.
Requirements:
- src/api/client.ts: typed wrappers for the M2 endpoints.
- views/Settings.tsx: KM config (url, sae_id) + email login (email, app-password, provider) + default security level. Connect buttons reflect status.
- views/Compose.tsx: to/subject/body + Level dropdown (1-4); warns if L1/L2 chosen while KM disconnected; Send calls /mail/send.
- views/Inbox.tsx: list from /mail/fetch with SecurityBadge; clicking calls /mail/read and shows plaintext + 'verified with key <id>' when encrypted.
- components: ConnectionStatus, Sidebar, SecurityBadge (green/blue/purple/grey for L1-4), AlertList.
- Electron main.js loads the Vite dev server in dev, built files in prod.

Constraints: NEVER request or display raw key bytes — only key IDs/status. Keep API calls in api/. Tailwind for styling; lucide-react for icons. No localStorage for secrets.
Format: functional components + hooks; small files.
Then print the dev-run commands.
```

---

## PROMPT I — Integration & packaging

```
Per CLAUDE.md. Wire everything end-to-end and package for Windows.

Tasks:
1. End-to-end test: with km_simulator + backend running, script a full flow (send L1 and L2 mail to a test account, fetch, read, assert plaintext matches). Put under tests/integration/.
2. scripts/: run_backend, run_simulator, run_frontend for both .sh and .bat.
3. Packaging: PyInstaller spec for backend + simulator; electron-builder config for the app; document the build in README.
4. docs/: finalize architecture.md, api_contract.md, etsi_qkd_014.md.

Constraints: keep the simulator and real-KM paths interchangeable via config. Note in README that real QKD hardware swaps in by changing KM base_url only.
Print the full build + run sequence.
```

---

## Tips for steering Claude Code

- If output drifts, reply: **"Re-read CLAUDE.md §4 constraints and revise."**
- For a focused change: name the file and the function, not the whole module.
- Ask for **tests first** on anything security-critical if you want extra safety.
- Keep sessions per-module; long sessions lose focus. Commit between modules.
