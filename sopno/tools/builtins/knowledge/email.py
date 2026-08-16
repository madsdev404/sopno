"""
sopno/tools/builtins/knowledge/email.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Email tools — read via IMAP, send via SMTP.

Opt-in only: ``email_enabled`` must be true and the servers/account configured.
Passwords are never stored in config.json — they come from an environment
variable named by ``email_password_env``. Reading is read-only; sending parks
a pending-action Yes/No gate.
"""

from __future__ import annotations

import email as email_lib
import imaplib
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Optional

from sopno.config.settings import settings
from sopno.tools.builtins.files.files import _awaiting_confirmation

_TO_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@._+-"
_SNIPPET = 400


def _enabled() -> str:
    if not getattr(settings, "email_enabled", False):
        return (
            "Email is off. To use it, set email_enabled = true and the "
            "email_imap_server / email_smtp_server / email_user keys in config.json."
        )
    return ""


def _password() -> tuple[str, str]:
    var = (getattr(settings, "email_password_env", "") or "").strip() or "SOPNO_EMAIL_PASSWORD"
    pw = os.environ.get(var, "") or ""
    if not pw:
        return "", f"Set the {var} environment variable to your email password."
    return pw, ""


def _config() -> tuple[dict, str]:
    err = _enabled()
    if err:
        return {}, err
    cfg = {
        "imap": getattr(settings, "email_imap_server", "") or "",
        "smtp": getattr(settings, "email_smtp_server", "") or "",
        "user": getattr(settings, "email_user", "") or "",
        "from": (getattr(settings, "email_from", "") or "").strip() or
                (getattr(settings, "email_user", "") or ""),
        "imap_port": int(getattr(settings, "email_imap_port", 993)),
        "smtp_port": int(getattr(settings, "email_smtp_port", 587)),
    }
    if not cfg["imap"] or not cfg["smtp"] or not cfg["user"]:
        return {}, "Email isn't fully configured — email_imap_server, email_smtp_server and email_user are all required."
    pw, err = _password()
    if err:
        return {}, err
    cfg["password"] = pw
    return cfg, ""


def _snippet(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    return text if len(text) <= _SNIPPET else text[:_SNIPPET] + "…"


def email_read(limit: int = 10, mailbox: str = "INBOX") -> str:
    """
    Read the most recent messages in a mailbox (read-only, IMAP).

    Args:
        limit: How many messages to list (1-20, default 10).
        mailbox: IMAP mailbox folder (default INBOX).

    Returns:
        The subjects/senders/snippets, or a failure reason.
    """
    cfg, err = _config()
    if err:
        return err
    limit = max(1, min(int(limit or 10), 20))
    try:
        conn = imaplib.IMAP4_SSL(cfg["imap"], cfg["imap_port"], timeout=30)
        try:
            conn.login(cfg["user"], cfg["password"])
            conn.select(mailbox or "INBOX")
            typ, data = conn.search(None, "ALL")
            if typ != "OK":
                return f"Could not search {mailbox}."
            ids = (data[0] or b"").split()
            if not ids:
                return f"No messages in {mailbox}."
            parts = []
            for msg_id in ids[-limit:]:
                typ, msg_data = conn.fetch(msg_id, "(RFC822)")
                if typ != "OK" or not msg_data or msg_data[0] is None:
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                subject = str(msg.get("Subject", "(no subject)"))
                frm = str(msg.get("From", "(unknown sender)"))
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True) or b""
                            try:
                                body = body.decode(errors="replace")
                            except Exception:  # noqa: BLE001
                                body = ""
                            break
                else:
                    payload = msg.get_payload(decode=True)
                    body = (payload or b"").decode(errors="replace") if payload else ""
                parts.append(f"{subject}\n  from {frm}\n  {_snippet(body)}")
            return "\n\n".join(parts) or f"No readable messages in {mailbox}."
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
    except imaplib.IMAP4.error as e:
        return f"IMAP error: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Could not read email: {e}"


def email_send(to: str, subject: str, body: str) -> str:
    """
    Send an email via SMTP (confirmed).

    Args:
        to: Recipient address.
        subject: Email subject.
        body: Email body text.

    Returns:
        Confirmation, or a failure reason.
    """
    cfg, err = _config()
    if err:
        return err
    to = (to or "").strip()
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not to or not subject or not body:
        return "Sending needs a recipient, a subject, and a body."
    if len(to) > 254 or any(c not in _TO_SAFE for c in to):
        return "That recipient address looks unsafe."
    if "\n" in subject or len(subject) > 300:
        return "The subject must be a single line."
    if len(body) > 20000:
        return "That message is too long (max 20000 chars)."

    def _do() -> str:
        try:
            msg = EmailMessage()
            msg["From"] = cfg["from"]
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
            server = smtplib.SMTP(cfg["smtp"], cfg["smtp_port"], timeout=30)
            try:
                server.starttls()
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
            finally:
                server.quit()
            return f"Email sent to {to}."
        except Exception as e:  # noqa: BLE001
            return f"Could not send the email: {e}"

    return _awaiting_confirmation(
        f"send an email to {to} with subject '{subject}'", _do
    )
