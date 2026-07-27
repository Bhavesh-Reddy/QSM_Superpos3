# QuMail — Usage & Troubleshooting Guide

How to connect, send, and read mail with QuMail — and how to fix the common
"SMTP authentication failed" error. For build/packaging see the
[README](../README.md); for internals see [architecture.md](architecture.md).

---

## 1. Commands to run the application

All commands run from the `qumail/` project root.

### 1.1 First-time setup (once)

```powershell
cd qumail

# Python backend + KM simulator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest

# Config: copy the template and set a keystore password
copy .env.example .env
#   then edit .env and set KEYSTORE_MASTER_PASSWORD to any non-empty value

# Frontend
cd frontend
npm install
cd ..
```

Bash / Git Bash / WSL equivalents:

```bash
cd qumail
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt pytest   # or .venv/bin/python on Linux/macOS
cp .env.example .env            # then set KEYSTORE_MASTER_PASSWORD
( cd frontend && npm install )
```

### 1.2 Start the three services (three separate terminals)

Use the helper scripts (they pick up the venv and check for `.env`):

```powershell
# Terminal 1 — KM simulator on :8100
scripts\run_simulator.bat

# Terminal 2 — backend API on :8000   (needs .env)
scripts\run_backend.bat

# Terminal 3 — frontend dev server on :5173
scripts\run_frontend.bat
```

Bash: `bash scripts/run_simulator.sh`, `bash scripts/run_backend.sh`,
`bash scripts/run_frontend.sh`.

Prefer the Electron desktop shell instead of the browser tab?
`cd frontend && npm run electron:dev` (in place of terminal 3).

### 1.3 Equivalent raw commands (no scripts)

If you'd rather run the processes directly:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m km_simulator.main         # KM simulator :8100

# Terminal 2
.\.venv\Scripts\python.exe -m backend.main              # backend API :8000

# Terminal 3
cd frontend
npm run dev                                             # frontend :5173
```

### 1.4 Verify it's up (optional smoke checks)

```powershell
curl http://127.0.0.1:8100/api/v1/keys/SAE-ALICE/status   # KM simulator
curl http://127.0.0.1:8000/health                         # backend  -> {"status":"ok",...}
```

Then open **http://localhost:5173** in your browser.

### 1.5 Run the tests (optional)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q                 # full suite
.\.venv\Scripts\python.exe -m pytest tests/integration/ -v     # end-to-end flow
```

---

## 2. Before you start (services checklist)

Confirm all three are running:

| Service | URL | Started by |
|---------|-----|-----------|
| KM simulator (ETSI 014) | http://127.0.0.1:8100 | `scripts/run_simulator.bat` |
| Backend API | http://127.0.0.1:8000 | `scripts/run_backend.bat` (needs `.env`) |
| Frontend (Vite) | http://localhost:5173 | `scripts/run_frontend.bat` |

Open the frontend at **http://localhost:5173**.

---

## 3. Connect the Key Manager and your mailbox

In **Settings**:

1. **Key Manager** — base URL `http://127.0.0.1:8100`, SAE ID `SAE-ALICE`
   (the default). On success you'll see *"Connected to Key Manager · N keys
   available."*
2. **Mailbox** — your email address + **App Password** (see §4). On success you'll
   see *"Mailbox connected."*

> ⚠️ **"Mailbox connected" does not verify your login.** Connecting only stores
> the account and detects the provider — it makes **no** SMTP/IMAP call. Your
> credentials are actually checked on the first **Send** (SMTP) and **Inbox**
> fetch (IMAP). So a green "connected" toast followed by an auth error on Send
> is expected when the password is wrong.

---

## 4. Gmail requires an App Password (fixes "SMTP authentication failed")

Google blocks basic-auth passwords for SMTP/IMAP. Using your normal Google
password produces:

> ⚠️ SMTP authentication failed (use an app password)

**Fix:**

1. Enable **2-Step Verification** on the Google account:
   https://myaccount.google.com/security
2. Create an App Password: **https://myaccount.google.com/apppasswords**
   (name it "QuMail"). You get a 16-character token like `abcd efgh ijkl mnop`.
3. In QuMail **Settings → Mailbox**, enter your address and paste the token
   **with spaces removed** (`abcdefghijklmnop`) — **not** your real password.
4. Enable IMAP so the Inbox can fetch: Gmail → ⚙️ **See all settings** →
   **Forwarding and POP/IMAP** → **Enable IMAP** → **Save Changes**.

Then press **Send** again — the error is gone.

**Other providers:** Yahoo and Outlook also require app passwords. Outlook/
Office365 often disables SMTP AUTH at the organization level, so **Gmail is the
easiest to demo with**. Provider hosts are auto-detected from the address domain
(`backend/app/email_svc/sender.py`).

---

## 5. Send a message

In **Compose**:

1. **To** — recipient address (also used as the KM `target_sae_id` for levels 1–2).
2. **Subject** / **Body**.
3. **Security level:**

   | Level | Scheme | Uses a KM key? |
   |------|--------|----------------|
   | 1 | Quantum OTP | Yes — key length ≥ message; single-use |
   | 2 | Quantum-aided AES | Yes — AES-256-GCM via HKDF |
   | 3 | PQC (ML-KEM + ML-DSA) | No (PQC keypair) — needs `liboqs` |
   | 4 | No encryption | No — plaintext |

4. **Send.** Levels 1–2 fetch a quantum key from the KM, encrypt, and send a
   `.qenc` message. On success you get a message ID (and `key_id` for levels 1–2).

---

## 6. Read a message

Open **Inbox** → click a message. QuMail calls `POST /mail/read`, which resolves
the key (local key store first, then the KM's `dec_keys`) and decrypts
server-side, then shows the plaintext. Raw keys never reach the browser.

---

## 7. Demo tips (important)

An encrypted QuMail message can **only be decrypted by a QuMail client pointed
at the same Key Manager**. In a normal Gmail web view it looks like an
attachment plus a "sent with QuMail" notice — that's expected.

- **Easiest self-contained demo:** send an encrypted message **to your own
  address**, then open **Inbox** in QuMail and read it back. This exercises the
  full encrypt → send → fetch → decrypt loop on one machine.
- **Plain delivery check:** use **Level 4** to confirm ordinary SMTP delivery to
  any external address.
- **Two-party encrypted demo:** the other side must also run QuMail against the
  **same** KM simulator, so `dec_keys` can return the matching key by `key_ID`.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| *SMTP authentication failed (use an app password)* | Normal password used for Gmail/Yahoo/Outlook | Use an **App Password** (§4) |
| Inbox is empty / IMAP error | IMAP disabled on the account | Enable IMAP in provider settings (§4 step 4) |
| *unknown email provider for domain '…'* | Address domain isn't gmail/yahoo/outlook | Use a supported provider, or pass an explicit `provider` |
| *KM not connected; call POST /auth/km first* | KM step skipped | Connect the Key Manager in Settings (§3) |
| KM shows 0 keys / connection refused | Simulator not running | Start `scripts/run_simulator.bat` (port 8100) |
| Backend won't start: missing `KEYSTORE_MASTER_PASSWORD` | No `.env` | `copy .env.example .env` and set the password |
| *KM did not return key_ID* on read | Reading on a different machine/KM than the sender used | Point both sides at the **same** KM (§7) |

---

## 9. Sharing one Key Manager between two machines

Encrypted mail (levels 1–3) can only be decrypted by a QuMail whose KM holds
the key the sender used. Two people each running their own local simulator do
**not** share keys — the receiver gets `KeyNotFoundError` / *"KM did not return
key_ID"*. Both must point at **one** KM.

**Host the shared KM** (one person), from `qumail/`:

```powershell
$env:QUMAIL_KM_HOST = "0.0.0.0"        # bind on the network (default is 127.0.0.1)
.\.venv\Scripts\python.exe -m km_simulator.main
ipconfig                               # note the host's IPv4 address, e.g. 192.168.1.42
```

Allow the port through Windows Firewall (once, as admin) if prompted:

```powershell
netsh advfirewall firewall add rule name="QuMail KM" dir=in action=allow protocol=TCP localport=8100
```

**Both people** set, in QuMail → Settings → Key Manager:

- Base URL: `http://<host-ip>:8100` (e.g. `http://192.168.1.42:8100`)
- SAE ID: any (the simulator ignores it for key storage)

On different networks / firewall trouble? Tunnel instead — no IP or firewall
setup: run `ngrok http 8100` on the host and both use the printed `https://…`
URL as the base URL (leave verify-TLS on).

Env vars: `QUMAIL_KM_HOST` (default `127.0.0.1`), `QUMAIL_KM_PORT` (default
`8100`).

> Keys live *in* the KM instance that issued them. A message already sent
> against a different KM can't be decrypted retroactively — set up the shared
> KM first, then send a **fresh** message.

---

## 10. Where credentials live

- The **email App Password** is held only in the running backend process (in the
  connected `EmailService`); it is never written to disk, logged, or returned in
  any API response.
- The **key store master password** comes from `.env`
  (`KEYSTORE_MASTER_PASSWORD`) and encrypts the at-rest key cache.
- `.env`, `*.enc`, and `keystore.json` are git-ignored — never commit them.
