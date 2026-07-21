# QuMail — End-to-End Directory Structure

This is the canonical layout. Claude Code must create exactly this during bootstrap.

```
qumail/
├── CLAUDE.md                     # Project skill (source of truth)
├── MASTER_PROMPT.md              # Kickoff prompt
├── PROMPTS.md                    # Per-module task prompts
├── DIRECTORY_STRUCTURE.md        # This file
├── README.md                     # Setup + run instructions
├── pyproject.toml                # ruff + black + pytest config
├── requirements.txt              # Python deps
├── .env.example                  # Config template (copy to .env)
├── .gitignore
│
├── core/                         # Shared contracts — imported everywhere
│   ├── __init__.py
│   ├── models.py                 # Pydantic/dataclasses: QKDKey, EmailMessage, EncryptedMessage, SecurityLevel enum
│   ├── interfaces.py             # ABCs/Protocols: ICryptoEngine, IKMClient, IEmailService, IKeyStore
│   └── exceptions.py             # KMConnectionError, KeyExhaustedError, DecryptionError, ...
│
├── backend/                      # M2 + M3 + M4 + M5 + M7  (the QuMail client backend)
│   ├── __init__.py
│   ├── main.py                   # uvicorn entrypoint
│   └── app/
│       ├── __init__.py
│       ├── config.py             # loads .env via pydantic-settings
│       ├── api/                  # M2 — FastAPI routers (thin; delegate to modules)
│       │   ├── __init__.py
│       │   ├── routes_auth.py    # KM login, email login
│       │   ├── routes_mail.py    # send, fetch, read
│       │   └── routes_keys.py    # key status/debug
│       ├── crypto/               # M3 — Crypto Engine
│       │   ├── __init__.py
│       │   ├── engine.py         # CryptoEngine facade (dispatch by SecurityLevel)
│       │   ├── otp.py            # Level 1
│       │   ├── quantum_aes.py    # Level 2
│       │   ├── pqc.py            # Level 3 (ML-KEM + ML-DSA via liboqs)
│       │   └── kdf.py            # HKDF-SHA256 helpers
│       ├── km/                   # M4 — KM Client (ETSI QKD 014)
│       │   ├── __init__.py
│       │   └── client.py         # get_status/get_key/get_key_with_ids
│       ├── email_svc/            # M5 — Email Service
│       │   ├── __init__.py
│       │   ├── sender.py         # SMTP
│       │   ├── receiver.py       # IMAP
│       │   └── mime_packer.py    # .qenc MIME build/parse + metadata headers
│       └── keystore/             # M7 — Secure Key Store
│           ├── __init__.py
│           └── store.py          # encrypted-at-rest cache; OTP one-time-use enforcement
│
├── km_simulator/                 # M6 — standalone ETSI 014 KM (dev only)
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, ETSI 014 endpoints
│   ├── qrng.py                   # Qiskit-based quantum random number generation
│   └── bb84.py                   # BB84 protocol simulation (educational + key gen)
│
├── frontend/                     # M1 — Electron + React GUI
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── electron/
│   │   ├── main.js               # Electron main process (spawns/looks up backend)
│   │   └── preload.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   └── client.ts         # typed fetch wrapper to backend API
│       ├── components/
│       │   ├── ConnectionStatus.tsx
│       │   ├── Sidebar.tsx
│       │   ├── SecurityBadge.tsx
│       │   └── AlertList.tsx
│       └── views/
│           ├── Inbox.tsx
│           ├── Compose.tsx
│           └── Settings.tsx
│
├── tests/                        # pytest (backend + simulator + core)
│   ├── __init__.py
│   ├── test_core_models.py
│   ├── test_crypto_otp.py
│   ├── test_crypto_aes.py
│   ├── test_crypto_pqc.py
│   ├── test_km_client.py
│   ├── test_keystore.py
│   ├── test_email_mime.py
│   └── test_km_simulator.py
│
├── scripts/
│   ├── run_backend.sh / .bat
│   ├── run_simulator.sh / .bat
│   └── run_frontend.sh / .bat
│
└── docs/
    ├── architecture.md
    ├── api_contract.md           # backend REST endpoints
    └── etsi_qkd_014.md           # notes on the standard as implemented
```

## Ownership map (Team Superpos3)

| Member | Folders |
|--------|---------|
| **A — Quantum & Keys** | `km_simulator/`, `backend/app/km/`, `backend/app/keystore/` |
| **B — Security Core**  | `backend/app/crypto/`, `core/` (shared), most of `tests/` |
| **C — App & Integration** | `frontend/`, `backend/app/email_svc/`, `backend/app/api/`, packaging |

Shared: `core/interfaces.py`, `docs/api_contract.md`, integration tests.

## Run order (dev)

```
# 1. KM simulator (terminal 1)
python -m km_simulator.main            # serves ETSI 014 on :8100

# 2. Backend (terminal 2)
python -m backend.main                 # serves QuMail API on :8000

# 3. Frontend (terminal 3)
cd frontend && npm run dev             # Vite dev server / Electron
```
