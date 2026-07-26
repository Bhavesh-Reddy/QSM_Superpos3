# QuMail — Usage & Troubleshooting Guide

How to connect, send, and read mail with QuMail — and how to fix the common
"SMTP authentication failed" error. For install/build steps see the
[README](../README.md); for internals see [architecture.md](architecture.md).

---

## 1. Before you start

Make sure all three services are running (see the README "Run" section):

| Service | URL | Started by |
|---------|-----|-----------|
| KM simulator (ETSI 014) | http://127.0.0.1:8100 | `scripts/run_simulator.bat` |
| Backend API | http://127.0.0.1:8000 | `scripts/run_backend.bat` (needs `.env`) |
| Frontend (Vite) | http://localhost:5173 | `scripts/run_frontend.bat` |

Open the frontend at **http://localhost:5173**.

---

## 2. Connect the Key Manager and your mailbox

In **Settings**:

1. **Key Manager** — base URL `http://127.0.0.1:8100`, SAE ID `SAE-ALICE`
   (the default). On success you'll see *"Connected to Key Manager · N keys
   available."*
2. **Mailbox** — your email address + **App Password** (see §3). On success you'll
   see *"Mailbox connected."*

> ⚠️ **"Mailbox connected" does not verify your login.** Connecting only stores
> the account and detects the provider — it makes **no** SMTP/IMAP call. Your
> credentials are actually checked on the first **Send** (SMTP) and **Inbox**
> fetch (IMAP). So a green "connected" toast followed by an auth error on Send
> is expected when the password is wrong.

---

## 3. Gmail requires an App Password (fixes "SMTP authentication failed")

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

## 4. Send a message

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

## 5. Read a message

Open **Inbox** → click a message. QuMail calls `POST /mail/read`, which resolves
the key (local key store first, then the KM's `dec_keys`) and decrypts
server-side, then shows the plaintext. Raw keys never reach the browser.

---

## 6. Demo tips (important)

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

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| *SMTP authentication failed (use an app password)* | Normal password used for Gmail/Yahoo/Outlook | Use an **App Password** (§3) |
| Inbox is empty / IMAP error | IMAP disabled on the account | Enable IMAP in provider settings (§3 step 4) |
| *unknown email provider for domain '…'* | Address domain isn't gmail/yahoo/outlook | Use a supported provider, or pass an explicit `provider` |
| *KM not connected; call POST /auth/km first* | KM step skipped | Connect the Key Manager in Settings (§2) |
| KM shows 0 keys / connection refused | Simulator not running | Start `scripts/run_simulator.bat` (port 8100) |
| Backend won't start: missing `KEYSTORE_MASTER_PASSWORD` | No `.env` | `copy .env.example .env` and set the password |
| *KM did not return key_ID* on read | Reading on a different machine/KM than the sender used | Point both sides at the **same** KM (§6) |

---

## 8. Where credentials live

- The **email App Password** is held only in the running backend process (in the
  connected `EmailService`); it is never written to disk, logged, or returned in
  any API response.
- The **key store master password** comes from `.env`
  (`KEYSTORE_MASTER_PASSWORD`) and encrypts the at-rest key cache.
- `.env`, `*.enc`, and `keystore.json` are git-ignored — never commit them.
