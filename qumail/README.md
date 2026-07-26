# QuMail — Quantum Secure Email Client

Team **Superpos3** · SIH 2025 "Quantum Secure Email Client" (ISRO / DoS).

QuMail is a Windows desktop email client that sends and receives encrypted mail
over ordinary providers (Gmail/Yahoo/Outlook), using quantum keys fetched from a
Key Manager via the **ETSI GS QKD 014** REST API, at four user-selectable
security levels. A **simulated Key Manager** (Qiskit-backed, ETSI 014-compliant)
stands in for real QKD hardware during development.

| Level | Scheme | Notes |
|------|--------|-------|
| 1 | Quantum OTP | XOR with a quantum key ≥ message length; single-use |
| 2 | Quantum-AES | AES-256-GCM; key via HKDF-SHA256 from a quantum key |
| 3 | PQC | ML-KEM-768 + ML-DSA-65 + AES-GCM |
| 4 | None | plaintext (compatibility) |

**New here? Start with [`docs/usage.md`](docs/usage.md)** — how to connect, send,
and read mail, plus the Gmail App Password fix for "SMTP authentication failed."

See also [`docs/architecture.md`](docs/architecture.md),
[`docs/api_contract.md`](docs/api_contract.md), and
[`docs/etsi_qkd_014.md`](docs/etsi_qkd_014.md).

---

## Prerequisites

- **Python 3.11+** (developed/tested on 3.12)
- **Node.js 18+** (for the frontend)
- Windows 10/11 (cross-platform Python; Bash scripts also provided)

## 1. Backend + simulator setup

```powershell
cd qumail
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest          # dev/test

copy .env.example .env
# edit .env and set KEYSTORE_MASTER_PASSWORD (required, no default)
```

Optional extras: `pip install qiskit qiskit-aer` (real QRNG in the simulator —
otherwise it uses the OS CSPRNG), `pip install liboqs-python` (level-3 PQC).

## 2. Frontend setup

```powershell
cd frontend
npm install
```

## 3. Run (three terminals)

```powershell
# Terminal 1 — KM simulator (ETSI 014) on :8100
scripts\run_simulator.bat

# Terminal 2 — backend API on :8000   (needs .env)
scripts\run_backend.bat

# Terminal 3 — frontend (Vite dev server on :5173)
scripts\run_frontend.bat
```

Bash equivalents (`scripts/run_*.sh`) are provided for Git Bash / WSL. To launch
the Electron desktop shell instead of the browser dev server:
`cd frontend && npm run electron:dev`.

## 4. Tests

```powershell
cd qumail
.\.venv\Scripts\python.exe -m pytest tests/ -q                    # everything
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q      # unit only
.\.venv\Scripts\python.exe -m pytest tests/integration/ -v        # end-to-end
```

The integration suite starts the KM simulator in-process and runs a full
**send → fetch → read** round trip for levels 1, 2, and 4 (only the SMTP/IMAP
transport is stubbed — everything else is real).

## 5. Build (Windows packaging)

**Backend + simulator (PyInstaller):**

```powershell
cd qumail
.\.venv\Scripts\python.exe -m pip install pyinstaller
pyinstaller packaging\backend.spec       # -> dist\qumail-backend\
pyinstaller packaging\simulator.spec     # -> dist\qumail-simulator\
```

Ship a `.env` next to `qumail-backend.exe` (config is read from the working
directory, never bundled — no secrets in the build).

**Desktop app (electron-builder):**

```powershell
cd frontend
npm run electron:build                   # -> frontend\release\
```

## 6. Real QKD hardware

The client speaks only the ETSI 014 REST surface, so **switching from the
simulator to real QKD hardware is a `base_url` change — nothing else**:

- set `KM_BASE_URL` (and the real `SAE_ID`) in `.env`, **or**
- call `POST /auth/km` at runtime with the hardware KME's URL.

Leave `verify_tls` on for real hardware; it is only disabled for the local
plain-HTTP simulator. No client code changes are required.

## Project layout

```
core/           shared contracts (models, interfaces, exceptions)
backend/        FastAPI app: api (M2b), services (M2a), crypto, km, email_svc, keystore
km_simulator/   ETSI 014 KM simulator (Qiskit QRNG + BB84) — dev only
frontend/       Electron + React + Tailwind GUI
tests/          pytest (unit + tests/integration/ end-to-end)
scripts/        run_{simulator,backend,frontend}.{bat,sh}
packaging/      PyInstaller specs + frozen entrypoints
docs/           architecture, API contract, ETSI 014 notes
```
