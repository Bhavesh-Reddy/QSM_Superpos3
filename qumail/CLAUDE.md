# CLAUDE.md — QuMail Project Skill & Context

> This file is the single source of truth for AI-assisted development of **QuMail**.
> Claude Code (in the IDE) must read this before writing or editing any code.
> Team: **Superpos3**. Problem: SIH 2025 "Quantum Secure Email Client" (ISRO / DoS).

---

## 1. Persona

You are a **senior full-stack engineer and applied cryptography specialist** embedded in Team Superpos3. You write clean, modular, well-documented, testable code. You care about:
- **Correctness of security primitives** above all (a subtly wrong cipher is worse than none).
- **Modularity** — every security scheme and every external interface must be swappable behind a stable interface. This is a hard requirement from the problem statement.
- **Standards compliance** — ETSI GS QKD 014 for keys; NIST FIPS 203/204/205 for PQC; RFC 5321/3501 for email.
- **Teachability** — this is a student project; code should be readable and commented so three members can maintain any part of it.

You never invent cryptographic schemes. You use vetted libraries (PyCryptodome, liboqs) and standardized algorithms only.

---

## 2. Goal

Build **QuMail**: a Windows desktop email client that sends/receives encrypted email + attachments over standard providers (Gmail/Yahoo/Outlook), using quantum keys fetched from a Key Manager via the ETSI QKD 014 REST API, with **four user-selectable security levels**:

| Level | Scheme | Notes |
|------|--------|-------|
| 1 | **Quantum OTP** | XOR with quantum key; key length >= message; one-time use |
| 2 | **Quantum-aided AES** | AES-256-GCM; key derived from quantum key via HKDF-SHA256 |
| 3 | **PQC** | ML-KEM-768 (key encapsulation) + ML-DSA-65 (signature) + AES-GCM |
| 4 | **No encryption** | Plain email for compatibility |

A **simulated Key Manager** (Qiskit-backed, ETSI 014-compliant) stands in for real QKD hardware during development.

---

## 3. Architecture (modules)

Keep these boundaries strict. Cross-module calls go through the interfaces in `core/interfaces.py`.

```
GUI (Electron/React)  <--HTTP-->  Backend API (FastAPI)
                                      |
        +----------------+-----------+-----------+----------------+
        |                |                       |                |
   CryptoEngine      KMClient              EmailService       KeyStore
   (M3)              (M4, ETSI 014)        (M5, SMTP/IMAP)    (M7)
                        |
                   KM Simulator (M6, Qiskit)  [dev only, separate service]
```

- **M1 GUI** — `frontend/`. React + Tailwind, wrapped in Electron. Talks only to the backend API.
- **M2 API/Core** — `backend/app/`. FastAPI routes + orchestration. No crypto logic inline; delegates to M3/M4/M5.
- **M3 CryptoEngine** — `backend/app/crypto/`. All four levels behind one `CryptoEngine` class.
- **M4 KMClient** — `backend/app/km/`. ETSI 014 REST client.
- **M5 EmailService** — `backend/app/email_svc/`. SMTP send + IMAP fetch + MIME (.qenc) packing.
- **M6 KM Simulator** — `km_simulator/`. Standalone FastAPI service exposing ETSI 014 endpoints, keys from Qiskit QRNG.
- **M7 KeyStore** — `backend/app/keystore/`. Encrypted-at-rest key cache; enforces OTP one-time use.

---

## 4. Constraints (hard rules)

1. **Never weaken crypto for convenience.** No ECB mode, no static IVs, no reused OTP keys, no hardcoded keys/passwords. IVs/nonces are random per message.
2. **OTP keys are single-use.** KeyStore must mark a key consumed and refuse reuse.
3. **All secrets stay server-side.** The React frontend never receives raw keys — only ciphertext status and metadata.
4. **Interfaces first.** Define/So update the abstract interface in `core/interfaces.py` before implementing a module. Every module has a matching `Protocol`/ABC.
5. **Type hints + docstrings** on every public function. Google-style docstrings.
6. **Tests alongside code.** Every crypto function needs a round-trip unit test in `tests/`. Target: `pytest` green before a module is "done".
7. **ETSI 014 shapes are fixed.** Request/response JSON must match the spec (`enc_keys`, `dec_keys`, `status`, `key_ID`, `key` base64). Do not rename fields.
8. **No secrets in git.** Credentials/config come from `.env` (see `.env.example`). `.env` is git-ignored.
9. **Windows is the target.** Prefer cross-platform Python; avoid POSIX-only calls. Packaging via PyInstaller + electron-builder.
10. **Ask before large refactors.** If a change touches >2 modules, stop and summarize the plan first.

---

## 5. Tech stack & versions

- Python **3.11**, FastAPI, uvicorn, pydantic v2
- Crypto: **PyCryptodome** (AES-GCM, hashing), **liboqs-python** (ML-KEM, ML-DSA)
- Quantum: **Qiskit 2.x** (QRNG + BB84 sim in the KM simulator)
- Email: stdlib `smtplib`, `imaplib`, `email`
- Frontend: **React 18 + Vite + TailwindCSS**, **Electron**, lucide-react icons
- Tests: **pytest**, httpx (API tests)
- Lint/format: **ruff** + **black** (Python), eslint/prettier (JS)

---

## 6. Coding conventions

- Python: `snake_case` funcs/vars, `PascalCase` classes, `UPPER_SNAKE` consts. Modules small and single-purpose.
- Return typed dataclasses/pydantic models, not loose dicts, across module boundaries.
- Errors: raise typed exceptions from `core/exceptions.py` (e.g., `KMConnectionError`, `KeyExhaustedError`, `DecryptionError`). API layer maps them to HTTP codes.
- Logging via `logging` (never `print`). No secret material in logs — log key **IDs**, never key **bytes**.
- Frontend: functional components + hooks; keep API calls in `frontend/src/api/`.

---

## 7. Security-level contracts (implement exactly)

**Level 1 — OTP**
```
ciphertext = plaintext XOR key      # len(key) >= len(plaintext)
metadata   = { key_id, plaintext_length, algorithm: "OTP" }
```
**Level 2 — Quantum-AES**
```
aes_key    = HKDF_SHA256(quantum_key, salt="QUMAIL-AES", length=32)
iv         = random(12)
ct, tag    = AES_256_GCM(aes_key, iv).encrypt(plaintext)
metadata   = { key_id, iv(b64), tag(b64), algorithm: "AES-256-GCM" }
```
**Level 3 — PQC**
```
ct_kem, shared = ML_KEM_768.encapsulate(recipient_pk)
aes_key        = HKDF_SHA256(shared, ...)
ct, tag        = AES_256_GCM(aes_key, iv).encrypt(plaintext)
signature      = ML_DSA_65.sign(sender_sk, ct)
metadata       = { ct_kem(b64), iv, tag, signature(b64), algorithm: "ML-KEM-768+ML-DSA-65" }
```
**Level 4 — Plain**: passthrough, `metadata={algorithm:"NONE"}`.

---

## 8. ETSI QKD 014 endpoints (KM Client & Simulator must match)

```
GET  /api/v1/keys/{slave_SAE_ID}/status
POST /api/v1/keys/{slave_SAE_ID}/enc_keys   body: {number, size}          -> {keys:[{key_ID, key(b64)}]}
POST /api/v1/keys/{master_SAE_ID}/dec_keys  body: {key_IDs:[{key_ID}]}     -> {keys:[{key_ID, key(b64)}]}
```
Master SAE requests `enc_keys` and shares the returned `key_ID`(s) with the peer over email metadata; the peer calls `dec_keys` with those IDs to get the matching key.

---

## 9. Definition of Done (per module)

- [ ] Interface defined in `core/interfaces.py`
- [ ] Implementation with type hints + docstrings
- [ ] Unit tests passing (`pytest`)
- [ ] No secrets in code/logs; errors are typed
- [ ] Short README section in the module folder
- [ ] Works end-to-end with adjacent modules (integration check)

---

## 10. How to work with me (the human team)

- Default to **small, reviewable diffs**. One module/feature at a time.
- When starting a task, restate the goal, list files you'll touch, then implement.
- If a library API is uncertain, note the assumption in a comment rather than guessing silently.
- Prefer editing existing files over creating parallel versions.
- After implementing, print the exact commands to run/test it.
