# QuMail Backend API Contract

> **Status:** proposed for agreement between **Member B** (G1 / M2a services) and
> **Member C** (G2 / M2b HTTP surface + M1 frontend). This is the single source
> of truth for the REST boundary between the React GUI and the FastAPI backend.
> G2 implements exactly these shapes; H (frontend `src/api/client.ts`) consumes them.
>
> Once B and C sign off, changes require agreement from both (it is a shared
> contract, per the ownership map in `DIRECTORY_STRUCTURE.md`).

---

## 1. Conventions

- **Base URL:** `http://127.0.0.1:8000` (backend runs on `:8000`; KM sim on `:8100`).
- **Prefix:** all endpoints live under `/api`.
- **Encoding:** JSON request/response bodies (`Content-Type: application/json`),
  UTF-8. Binary blobs (attachment bytes, ciphertext the client must not decrypt)
  are **base64 strings**.
- **Method semantics:** `GET` = read, no side effects; `POST` = action / mutation.
- **Time:** ISO-8601 UTC strings (e.g. `2026-07-25T10:30:00+00:00`).
- **Security levels:** integer enum, matching `core.models.SecurityLevel`:

  | value | name | scheme |
  |------|------|--------|
  | 1 | OTP | Quantum one-time pad |
  | 2 | QUANTUM_AES | AES-256-GCM (HKDF from quantum key) |
  | 3 | PQC | ML-KEM-768 + ML-DSA-65 + AES-GCM |
  | 4 | NONE | plain (compatibility) |

### 1.1 Hard invariant — no secrets to the client

The frontend **never** receives raw key bytes, derived keys, passwords, or app
passwords (CLAUDE.md constraint #3). Responses expose only: `key_id`s, security
metadata (algorithm, IV/tag as opaque base64), ciphertext *status*, and — after
server-side decryption — the recovered plaintext. Requests carrying secrets
(email app-password, keystore master password) are accepted **only** over the
auth endpoints and are held server-side; they are never echoed back.

---

## 2. Shared data types

### `SecurityInfo`
Per-message security descriptor (safe to send to the client — no key material):
```json
{
  "level": 2,
  "algorithm": "AES-256-GCM",
  "key_ids": ["QK-000123"],
  "verified": true
}
```
- `algorithm`: `"OTP" | "AES-256-GCM" | "ML-KEM-768+ML-DSA-65" | "NONE"`.
- `key_ids`: KM key IDs referenced by the message (empty for level 3/4).
- `verified`: level-3 signature check result; `null` when not applicable.

### `Attachment`
```json
{ "filename": "report.pdf", "content_type": "application/pdf", "size_bytes": 20480 }
```
On **send**, the client includes `data_b64` (base64 plaintext bytes). On **read**,
the decrypted response includes `data_b64`; on **list**, only metadata is returned.

### `MessageSummary` (list view — not decrypted)
```json
{
  "uid": "1029",
  "sender": "alice@gmail.com",
  "recipient": "bob@outlook.com",
  "subject": "Quarterly report",
  "timestamp": "2026-07-25T10:30:00+00:00",
  "is_qumail": true,
  "security": { "level": 2, "algorithm": "AES-256-GCM", "key_ids": ["QK-000123"], "verified": null },
  "decrypted": false
}
```

### `DecryptedMessage` (read view — plaintext after server-side decryption)
```json
{
  "uid": "1029",
  "sender": "alice@gmail.com",
  "recipient": "bob@outlook.com",
  "subject": "Quarterly report",
  "timestamp": "2026-07-25T10:30:00+00:00",
  "body": "the recovered plaintext body",
  "attachments": [{ "filename": "report.pdf", "content_type": "application/pdf", "size_bytes": 20480, "data_b64": "..." }],
  "security": { "level": 2, "algorithm": "AES-256-GCM", "key_ids": ["QK-000123"], "verified": null }
}
```

---

## 3. Endpoints

### 3.1 Health

#### `GET /api/health`
Liveness probe. → `200`
```json
{ "status": "ok", "version": "0.1.0" }
```

---

### 3.2 Auth & connections — `routes_auth.py`

Credentials are stored server-side for the session; none are returned.

#### `POST /api/auth/km`
Configure the KM (ETSI 014) connection used for key fetch.
```json
{ "base_url": "http://127.0.0.1:8100", "sae_id": "SAE-ALICE", "verify_tls": true }
```
→ `200` `{ "connected": true, "sae_id": "SAE-ALICE" }`
Errors: `KMConnectionError` → `502`.

#### `POST /api/auth/email`
Log in to the mail provider (SMTP/IMAP). Provider auto-detected from the address.
```json
{ "address": "alice@gmail.com", "app_password": "····", "display_name": "Alice" }
```
→ `200` `{ "connected": true, "address": "alice@gmail.com", "provider": "gmail" }`
Errors: bad domain → `400 ConfigError`; auth failure → `401 EmailError`.

#### `POST /api/auth/keystore`
Unlock (or create) the encrypted key store with the master password.
```json
{ "master_password": "····" }
```
→ `200` `{ "unlocked": true }`
Errors: wrong password / corrupt store → `401 KeyStoreError`.

#### `GET /api/auth/status`
Current connection state (no secrets). → `200`
```json
{ "km": true, "email": true, "keystore": true, "sae_id": "SAE-ALICE", "address": "alice@gmail.com" }
```

---

### 3.3 Mail — `routes_mail.py`

#### `POST /api/mail/send`
Encrypt (per level) and send. Delegates to `SendService.send_encrypted_email`.
```json
{
  "recipient": "bob@outlook.com",
  "subject": "Quarterly report",
  "body": "hello bob",
  "attachments": [{ "filename": "report.pdf", "content_type": "application/pdf", "data_b64": "..." }],
  "security_level": 2,
  "slave_sae_id": "SAE-BOB"
}
```
Notes:
- `sender` is taken from the authenticated email session (not client-supplied).
- `slave_sae_id` is **required for levels 1–2** (KM key fetch), ignored for 4,
  and (level 3) replaced by recipient PQC public-key resolution — see §6 Q3.

→ `200`
```json
{ "message_id": "<abc@gmail.com>", "security": { "level": 2, "algorithm": "AES-256-GCM", "key_ids": ["QK-000123"], "verified": null } }
```
Errors: `KMConnectionError` → `502`; `KeyExhaustedError` → `409`;
`EncryptionError` → `422`; `EmailSendError` → `502`.

#### `GET /api/mail/messages?folder=INBOX&limit=50`
List recent messages (headers + security descriptor; **not decrypted**).
Delegates to `IEmailService.fetch`; ciphertext stays server-side.
→ `200` `{ "messages": [ MessageSummary, ... ] }`
Errors: email auth → `401`; IMAP failure → `502 EmailError`.

#### `POST /api/mail/messages/{uid}/decrypt`
Fetch one message, resolve its key(s) (key store → KM `dec_keys`), decrypt, and
return plaintext. Delegates to `ReceiveService.fetch_and_decrypt` (single-UID).
Body (optional): `{ "master_sae_id": "SAE-ALICE" }` (defaults to the peer stored
in the message metadata).
→ `200` `DecryptedMessage`
Errors: `KeyNotFoundError` → `404`; `KeyExhaustedError` → `409`;
`DecryptionError` → `422`; `SignatureVerificationError` → `422`.

---

### 3.4 Keys (status / debug) — `routes_keys.py`

#### `GET /api/keys/status?target_sae_id=SAE-BOB`
KM key availability toward a peer (proxies ETSI 014 `status`).
→ `200`
```json
{ "source_KME_ID": "KME-SIM-001", "target_KME_ID": "KME-SIM-002",
  "master_SAE_ID": "SAE-ALICE", "slave_SAE_ID": "SAE-BOB",
  "stored_key_count": 42, "key_size": 256, "max_key_per_request": 128 }
```
Errors: `KMConnectionError` → `502`.

#### `GET /api/keys/cache`
Debug view of the local key store — **IDs and flags only, never key bytes**.
→ `200`
```json
{ "keys": [ { "key_id": "QK-000123", "size_bits": 256, "consumed": false, "created_at": "2026-07-25T10:00:00+00:00" } ] }
```

---

## 4. Error model

All non-2xx responses share one shape:
```json
{ "error": { "type": "KeyExhaustedError", "message": "human-readable, no secrets" } }
```
`type` is the `core.exceptions` class name. `message` never contains key bytes,
passwords, or plaintext.

### Exception → HTTP status mapping (implemented once in the API layer)

| `core.exceptions`            | HTTP | Meaning |
|------------------------------|------|---------|
| `ConfigError`                | 400  | Missing/invalid configuration or unknown provider |
| `EmailError` (auth)          | 401  | SMTP/IMAP or keystore authentication failed |
| `KeyStoreError`              | 401  | Store locked / wrong master password |
| `KeyNotFoundError`           | 404  | Unknown `key_ID` / message UID |
| `KeyExhaustedError`          | 409  | Key material spent / OTP already consumed |
| `KeyAlreadyConsumedError`    | 409  | Attempt to reuse a consumed OTP key |
| `EncryptionError`            | 422  | Bad inputs for the chosen level |
| `DecryptionError`            | 422  | Bad key / corrupt ciphertext / GCM tag failure |
| `SignatureVerificationError` | 422  | Level-3 ML-DSA signature invalid |
| `KMConnectionError`          | 502  | KM unreachable / HTTP error |
| `KMResponseError`            | 502  | Malformed ETSI 014 response |
| `EmailSendError` / `EmailFetchError` | 502 | SMTP/IMAP transport failure |
| (pydantic validation)        | 422  | Malformed request body (FastAPI default) |
| (uncaught)                   | 500  | Unexpected server error |

---

## 5. Request lifecycle (informative)

**Send (level 1–2):** `POST /api/mail/send` → SendService: `KMClient.get_key` →
`KeyStore.put` (+ `consume` for OTP) → `CryptoEngine.encrypt` →
`mime_packer.build` → `Sender.send_quantum_email` → returns `message_id` + `key_ids`.

**Receive:** `GET /api/mail/messages` (list, ciphertext server-side) →
`POST /api/mail/messages/{uid}/decrypt` → ReceiveService: read `key_ID`s from
metadata → `KeyStore.get` else `KMClient.get_key_with_ids` → `CryptoEngine.decrypt`
→ returns `DecryptedMessage`.

---

## 6. Open questions for B + C to confirm

1. **Session model.** Single-user desktop app → one implicit server-side session
   (no auth token in requests), or an explicit session id? *Proposed: implicit,
   since Electron talks to a localhost backend it spawns.*
2. **Message identity.** Use IMAP `UID` (string) as the message handle for
   `/decrypt`? *Proposed: yes.*
3. **Level-3 key exchange.** How does the sender obtain the recipient's ML-KEM
   public key, and where do PQC keypairs live (keystore vs. a new `pqc_identity`)?
   This is unresolved in CLAUDE.md §7 and blocks the level-3 send path. *Needs a
   decision before G1 implements level 3.*
4. **Decrypt granularity.** Per-UID decrypt (proposed) vs. a batch
   `fetch_and_decrypt` that decrypts a page at once. *Proposed: per-UID on demand,
   to avoid consuming OTP keys for messages the user never opens.*
5. **Attachment size cap / streaming.** Base64 in JSON is fine for small files;
   set a max (e.g. 10 MB) and return `413` above it? *Proposed: 25 MB cap.*

---

## 7. Validation

This contract is verified by: (a) G2 implementing FastAPI routers whose
`response_model`s match §2–§3; (b) a contract test (`tests/test_api_contract.py`,
added with G2) asserting each endpoint's status codes and JSON shape via
`httpx`/`TestClient`; (c) the frontend `client.ts` typed against these shapes.
```
