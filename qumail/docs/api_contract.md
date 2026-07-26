# QuMail Backend API Contract

> **Status:** implemented (G2). This document describes the API exactly as
> built in `backend/app/api/` + `backend/main.py`, over the M2a services
> from G1 (`SendService.send`, `ReceiveService.read`). It supersedes an
> earlier draft that was written against a pre-G1 stub (`send_encrypted_email`
> / `fetch_and_decrypt`, an `/api` prefix, UID-based decrypt) — those shapes
> were never implemented. Changes require agreement between the owners of
> `services/` and `api/` (see `DIRECTORY_STRUCTURE.md`).

---

## 1. Conventions

- **Base URL:** `http://127.0.0.1:8000` (backend; the KM sim runs on `:8100`).
- **No path prefix.** Routes are mounted at their literal paths (`/auth/km`,
  `/mail/send`, ...) — there is no `/api` prefix.
- **Encoding:** JSON bodies (`Content-Type: application/json`), UTF-8.
  Attachment bytes are base64 strings (`data` on send; `data_b64`-style
  fields are not used elsewhere — reads return a decoded UTF-8 `body`).
- **Method semantics:** `GET` = read, no side effects; `POST` = action.
- **Security levels:** integer enum, matching `core.models.SecurityLevel`:

  | value | name | scheme |
  |------|------|--------|
  | 1 | OTP | Quantum one-time pad |
  | 2 | QUANTUM_AES | AES-256-GCM (HKDF from quantum key) |
  | 3 | PQC | ML-KEM-768 + ML-DSA-65 + AES-GCM |
  | 4 | NONE | plain (compatibility) |

### 1.1 Hard invariant — no secrets to the client

The frontend never receives raw key bytes, derived keys, passwords, or app
passwords (CLAUDE.md constraint #3). `POST /mail/send` and `POST /mail/read`
expose only `key_id` and non-secret crypto metadata (algorithm, IV/tag/etc.
as opaque base64 inside `metadata`). `GET /mail/fetch` summaries go further
and omit `key_id` entirely — only `level` + `algorithm` are exposed, since
listing shouldn't require resolving any key. Passwords accepted by
`POST /auth/email` are held only in-process (in the connected
`EmailService`) and are never echoed back or logged.

### 1.2 Session model

Single-user desktop app → **one implicit server-side session**, held on
`app.state.qumail` (see `backend/app/api/deps.py:AppState`). No auth tokens
in requests; the Electron shell talks to a backend it spawns on localhost.
`crypto` and `store` are built once at startup; `km` and `mail` start unset
and are populated by `POST /auth/km` / `POST /auth/email`. Any `/mail/*` or
`/keys/*` call made before the relevant connect endpoint returns
`ConfigError` → `500`.

---

## 2. Endpoints

### 2.1 Health

#### `GET /health`
Liveness probe, no auth required. → `200`
```json
{ "status": "ok", "version": "0.1.0" }
```

---

### 2.2 Auth & connections — `routes_auth.py`

#### `POST /auth/km`
Connect to an ETSI 014 Key Manager and return its status.
```json
{ "base_url": "http://127.0.0.1:8100", "sae_id": "SAE-ALICE", "verify_tls": true }
```
→ `200` — the KM's `ETSIStatus` document:
```json
{
  "source_KME_ID": "KME-SIM-001", "target_KME_ID": "KME-SIM-002",
  "master_SAE_ID": "SAE-ALICE", "slave_SAE_ID": "SAE-BOB",
  "key_size": 256, "stored_key_count": 42, "max_key_count": 1024,
  "max_key_per_request": 8, "max_key_size": 65536, "min_key_size": 64
}
```
Errors: `KMConnectionError` → `502`; `KMResponseError` → `502`.

#### `POST /auth/email`
Connect an SMTP/IMAP mailbox. `provider` is optional — when omitted, the
provider is auto-detected from the address domain (gmail/yahoo/outlook).
```json
{ "email": "alice@gmail.com", "password": "an-app-password", "provider": null }
```
→ `200`
```json
{ "connected": true, "address": "alice@gmail.com", "provider": "gmail" }
```
Errors: unknown explicit `provider` → `ConfigError` → `500`; domain can't be
auto-detected / bad login → `EmailError` → `502`.

---

### 2.3 Mail — `routes_mail.py`

#### `POST /mail/send`
Encrypt (per `level`) and send. Delegates to `SendService.send`.
```json
{
  "to": "bob@example.com",
  "subject": "Quarterly report",
  "body": "hello bob",
  "level": 2,
  "attachments": [{ "filename": "report.pdf", "content_type": "application/pdf", "data": "<base64>" }]
}
```
Notes:
- `to` is also used as the KM `target_sae_id` for levels 1–2 (see
  `SendService`); there is no separate `slave_sae_id` field.
- `sender` (the `From` address) comes from the connected email session, not
  the request body.
- Levels 1–2 fetch a key from the KM; level 1 additionally requires the key
  be at least as long as the plaintext. Levels 3–4 make no KM call.

→ `200`
```json
{ "message_id": "<abc@gmail.com>", "key_id": "QK-000123", "level": 2 }
```
`key_id` is `null` for levels 3 and 4.
Errors: `KMConnectionError` → `502`; `KeyExhaustedError` → `409`;
`EncryptionError` → `422`; `UnsupportedSecurityLevelError` → `422`;
`EmailSendError` → `502`.

#### `GET /mail/fetch?folder=INBOX&limit=50`
List recent messages as summaries — **not decrypted**, no `key_id`.
Delegates directly to the connected `IEmailService.fetch`.
→ `200`
```json
{
  "messages": [
    {
      "sender": "alice@gmail.com",
      "recipient": "bob@outlook.com",
      "subject": "Quarterly report",
      "timestamp": "2026-07-25T10:30:00+00:00",
      "is_encrypted": true,
      "level": 2,
      "algorithm": "AES-256-GCM"
    }
  ]
}
```
`level`/`algorithm` are `null` for plain (non-QuMail) mail.
Errors: `EmailError` → `502`; `EmailFetchError` → `502`.

#### `POST /mail/read`
Locate, resolve the key for, and decrypt one message. Delegates to
`ReceiveService.read`.
```json
{ "message_id": "1" }
```
→ `200`
```json
{
  "body": "hello bob",
  "level": 2,
  "metadata": { "key_id": "QK-000123", "algorithm": "AES-256-GCM", "iv": "...", "tag": "..." }
}
```
Errors: `EmailFetchError` → `502` (message not found); `KMConnectionError`
→ `502`; `KeyNotFoundError` → `404`; `DecryptionError` → `400`;
`SignatureVerificationError` → `400`.

---

### 2.4 Keys — `routes_keys.py`

#### `GET /keys/status`
KM key availability for the connected session (proxies ETSI 014 `status`).
Same shape as `POST /auth/km`'s response.
Errors: `ConfigError` → `500` (not connected); `KMConnectionError` → `502`.

---

## 3. Error model

All non-2xx responses from a typed exception share one shape:
```json
{ "error": { "type": "KeyExhaustedError", "message": "human-readable, no secrets" } }
```
`type` is the `core.exceptions` class name. `message` never contains key
bytes, passwords, or plaintext. Registered once, in `backend/main.py`, over
`QuMailError` (Starlette dispatches subclasses to the same handler) —
routers never catch exceptions themselves.

### Exception → HTTP status mapping (`backend/main.py::_EXCEPTION_STATUS`)

| `core.exceptions`            | HTTP | Meaning |
|------------------------------|------|---------|
| `KeyNotFoundError`            | 404  | Unknown `key_id` |
| `KeyExhaustedError`           | 409  | KM has insufficient key material |
| `KeyAlreadyConsumedError`     | 409  | Attempt to reuse a consumed OTP key |
| `KeyStoreError` (other)       | 409  | Other key-store state conflict |
| `DecryptionError`             | 400  | Bad key / corrupt ciphertext / GCM tag failure |
| `SignatureVerificationError`  | 400  | Level-3 ML-DSA signature invalid |
| `EncryptionError`             | 422  | Bad inputs for the chosen level (e.g. short OTP key) |
| `UnsupportedSecurityLevelError` | 422 | Unknown security level |
| `CryptoError` (other)         | 422  | Other crypto-engine failure |
| `KMConnectionError`           | 502  | KM unreachable / HTTP error |
| `KMResponseError`             | 502  | Malformed ETSI 014 response |
| `KMError` (other)             | 502  | Other KM failure |
| `EmailError` (incl. `EmailSendError`, `EmailFetchError`, `MimeFormatError`) | 502 | SMTP/IMAP/MIME failure |
| `ConfigError`                 | 500  | Missing/invalid configuration, or KM/email not yet connected |
| `QuMailError` (other)         | 500  | Fallback for any other typed error |
| (pydantic validation)         | 422  | Malformed request body (FastAPI default) |
| (uncaught)                    | 500  | Unexpected server error (Starlette default) |

The mapping checks subclasses before their base class (e.g.
`KeyNotFoundError` before the generic `KeyStoreError` fallback), so adding a
new `core.exceptions` subclass without updating the table still lands on a
sane family-level status instead of a bare 500.

---

## 4. Request lifecycle (informative)

**Send:** `POST /mail/send` → `SendService.send`: (levels 1–2)
`KMClient.get_key` → `KeyStore.put` → `CryptoEngine.encrypt` → (level 1 only)
`KeyStore.consume` → `key_id` written into `EmailMessage.security_metadata`
→ `IEmailService.send`. Levels 3–4 skip the KM call entirely.

**Receive:** `GET /mail/fetch` (list, ciphertext stays server-side) →
`POST /mail/read` → `ReceiveService.read`: locate the message via
`IEmailService.fetch`, read `key_id` from its metadata → `KeyStore.get` else
`KMClient.get_key_with_ids` (caching the result) → `CryptoEngine.decrypt`.

---

## 5. Known gaps / follow-ups

1. **Message identity.** `ReceiveService._locate` (M2a) matches
   `message_id` against `EmailMessage.security_metadata["message_id"]`, a
   key the concrete `backend/app/email_svc/receiver.py` does not populate
   yet — it needs a small follow-up patch to stash the real IMAP/RFC 5322
   `Message-ID` there before `/mail/read` works against a live mailbox.
2. **Level-3 key material.** `POST /mail/send` at level 3 calls
   `CryptoEngine.encrypt` with no `recipient_public_key` wired in yet (no
   PQC identity/keystore endpoint exists) — it will raise `EncryptionError`
   until that's added.
3. **CORS origins are hardcoded** in `backend/main.py` (matching
   `km_simulator/main.py`'s convention) rather than sourced from `Settings`,
   so the app object can be constructed for tests without any environment
   configuration. Revisit if the dev origin needs to be configurable.

---

## 6. Validation

Verified by `tests/test_api_auth.py`, `tests/test_api_mail.py`,
`tests/test_api_keys.py` (one `httpx`/`TestClient` smoke test per route,
services mocked via `app.dependency_overrides`), `tests/test_api_errors.py`
(the full exception → status matrix), and `tests/test_api_lifespan.py` (one
real-lifespan startup test, unmocked).
