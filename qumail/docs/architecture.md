# QuMail Architecture

QuMail is a Windows desktop email client that sends and receives encrypted mail
over ordinary providers (Gmail/Yahoo/Outlook), using quantum keys fetched from a
Key Manager via the ETSI GS QKD 014 REST API, at four user-selectable security
levels. This document describes the system as built.

## 1. Component map

```
 Electron + React GUI (M1, frontend/)
        │  HTTP (localhost:8000)
        ▼
 FastAPI backend (backend/)
   ├─ M2b API surface        backend/app/api/      routers, schemas, exception→HTTP
   ├─ M2a Orchestration      backend/app/services/ SendService / ReceiveService
   ├─ M3 Crypto Engine       backend/app/crypto/   OTP · Quantum-AES · PQC
   ├─ M4 KM Client           backend/app/km/        ETSI 014 REST client
   ├─ M5 Email Service       backend/app/email_svc/ SMTP · IMAP · .qenc MIME
   └─ M7 Key Store           backend/app/keystore/  AES-GCM at rest, OTP single-use
        │  ETSI 014 (HTTP, localhost:8100)
        ▼
 KM Simulator (M6, km_simulator/)  Qiskit QRNG + BB84  [dev only; real QKD hardware later]

 core/ — shared contracts (models, interfaces, exceptions) imported by every module.
```

## 2. Layering and boundaries

- **`core/` is the contract hub.** Every cross-module call goes through the ABCs
  in `core/interfaces.py` (`ICryptoEngine`, `IKMClient`, `IEmailService`,
  `IKeyStore`). Modules exchange typed models from `core/models.py`, never loose
  dicts, and raise typed errors from `core/exceptions.py`.
- **M2 is split.** *M2a services* hold the security-critical orchestration
  (order of key fetch → encrypt → consume → send, and fetch → resolve → decrypt)
  and import **only** `core` — no FastAPI. *M2b API* is a thin HTTP surface that
  maps requests onto services and maps typed exceptions to HTTP status codes in
  one place (`backend/main.py`).
- **Secrets stay server-side.** The GUI never receives key bytes, derived keys,
  or passwords — only `key_id`s, non-secret metadata, ciphertext status, and (on
  read) recovered plaintext (CLAUDE.md constraint #3).

## 3. Send pipeline (SendService)

1. **Key (levels 1–2):** `KMClient.get_key(target_sae_id=recipient)` → ETSI 014
   `enc_keys`. Level 1 requests a key at least as long as the plaintext.
2. **Cache:** `KeyStore.put(key)` (encrypted at rest).
3. **Encrypt:** `CryptoEngine.encrypt(plaintext, level, key=…)`.
4. **Consume (level 1 only):** `KeyStore.consume(key_id)` — OTP keys are
   strictly single-use.
5. **Send:** pack ciphertext + metadata (carrying `key_id`, never key bytes) as
   a `.qenc` MIME message and submit via SMTP.

Levels 3 (PQC) and 4 (plain) make no KM call.

## 4. Receive pipeline (ReceiveService)

1. **Fetch:** `IEmailService.fetch()` (IMAP) → messages with ciphertext held in
   `security_metadata` (never decrypted client-side).
2. **Locate** the requested message; **extract** the `.qenc` envelope.
3. **Resolve key:** local `KeyStore.get(key_id)` first; on a miss, fall back to
   `KMClient.get_key_with_ids(source_sae_id, [key_id])` (ETSI 014 `dec_keys`)
   and cache the result.
4. **Decrypt:** `CryptoEngine.decrypt(...)` → plaintext.

The two-party key handoff is real: the sender consumes its own OTP copy; the
receiver independently redeems the same `key_ID` from the KM via `dec_keys`.

## 5. Security levels

| Level | Scheme | Key source | Notes |
|------|--------|-----------|-------|
| 1 | Quantum OTP | KM `enc_keys` | XOR; key length ≥ plaintext; single-use |
| 2 | Quantum-AES | KM `enc_keys` | AES-256-GCM, key via HKDF-SHA256 |
| 3 | PQC | PQC keypair | ML-KEM-768 + ML-DSA-65 + AES-GCM |
| 4 | None | — | plaintext (compatibility) |

## 6. Simulator ↔ real hardware

The KM Simulator (M6) implements the same ETSI 014 surface the client's KM
Client speaks. **Swapping in real QKD hardware is a `base_url` change only**
(`POST /auth/km` at runtime, or `KM_BASE_URL` in `.env`) — no code change in the
client. See `docs/etsi_qkd_014.md`.

## 7. Testing strategy

- Per-module unit tests in `tests/` (crypto round-trips, keystore single-use,
  KM client error mapping, MIME build/parse, API status codes).
- `tests/integration/` runs a full **send → fetch → read** flow against the real
  KM simulator (started in a uvicorn thread), with only the SMTP/IMAP transport
  replaced by an in-memory loopback. Marked `integration`.

## 8. Ownership (Team Superpos3)

| Member | Folders |
|--------|---------|
| A — Quantum & Keys | `km_simulator/`, `backend/app/km/`, `backend/app/keystore/` |
| B — Security Core | `core/`, `backend/app/crypto/`, `backend/app/services/` |
| C — App & Integration | `frontend/`, `backend/app/email_svc/`, `backend/app/api/`, packaging |
