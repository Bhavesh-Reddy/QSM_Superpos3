"""Standalone Gmail IMAP+SMTP credential check (diagnostic, not part of the app).

Tests an email address + app password directly against Gmail, printing Google's
raw response so authentication failures are explained. Bypasses QuMail entirely
to isolate whether a problem is the credential/account or the app.

Usage (from the qumail/ root):
    .\.venv\Scripts\python.exe scripts\check_gmail.py

The password is read via a hidden prompt — it is never echoed, logged, or
stored. Run this in a terminal you trust.
"""

from __future__ import annotations

import getpass
import imaplib
import smtplib


def main() -> None:
    email = input("Gmail address: ").strip()
    raw = getpass.getpass("App password (input hidden): ")
    # Same normalization the backend does — Gmail app passwords have no spaces.
    password = "".join(raw.split())
    print(f"(using a {len(password)}-character password with spaces removed)\n")

    print("── IMAP (imap.gmail.com:993) ──")
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20) as imap:
            imap.login(email, password)
            imap.select("INBOX", readonly=True)
            status, data = imap.uid("search", "ALL")
            count = len(data[0].split()) if status == "OK" and data and data[0] else 0
            print(f"  ✅ IMAP login OK — {count} message(s) visible in INBOX")
    except imaplib.IMAP4.error as exc:
        print(f"  ❌ IMAP rejected: {exc}")
    except OSError as exc:
        print(f"  ❌ IMAP connection error: {exc}")

    print("\n── SMTP (smtp.gmail.com:587, STARTTLS) ──")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(email, password)
            print("  ✅ SMTP login OK")
    except smtplib.SMTPAuthenticationError as exc:
        detail = getattr(exc, "smtp_error", b"").decode("utf-8", "replace")
        print(f"  ❌ SMTP rejected: code={getattr(exc, 'smtp_code', '?')} {detail}")
    except (smtplib.SMTPException, OSError) as exc:
        print(f"  ❌ SMTP error: {exc}")

    print(
        "\nIf both say ✅ here but QuMail still fails, it's a QuMail bug — tell me.\n"
        "If they fail here too, the credential/account is the problem (see the reason above)."
    )


if __name__ == "__main__":
    main()
