"""
tests/test_email.py
━━━━━━━━━━━━━━━━━━
Email tools with stubbed IMAP/SMTP: the opt-in gate, the env-password rule,
read-only listing, and the confirmed send (recipient validation included).
"""

import os
import unittest
from email.message import EmailMessage
from unittest.mock import patch

from sopno.config.settings import settings
from sopno.tools.builtins import email as mod
from sopno.tools.builtins import files


class EmailTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "enabled": settings.email_enabled,
            "user": settings.email_user,
            "imap": settings.email_imap_server,
            "smtp": settings.email_smtp_server,
            "env": getattr(settings, "email_password_env", "SOPNO_EMAIL_PASSWORD"),
        }
        settings.email_enabled = True
        settings.email_user = "me@example.com"
        settings.email_imap_server = "imap.example.com"
        settings.email_smtp_server = "smtp.example.com"
        self._env_pw = "SOPNO_TEST_PASSWORD"
        self._old_env = os.environ.get(self._env_pw)
        os.environ[self._env_pw] = "sekrit"
        settings.email_password_env = self._env_pw

    def tearDown(self) -> None:
        settings.email_enabled = self._saved["enabled"]
        settings.email_user = self._saved["user"]
        settings.email_imap_server = self._saved["imap"]
        settings.email_smtp_server = self._saved["smtp"]
        settings.email_password_env = self._saved["env"]
        if self._old_env is None:
            os.environ.pop(self._env_pw, None)
        else:
            os.environ[self._env_pw] = self._old_env


class EmailReadTest(EmailTest):
    def test_disabled(self) -> None:
        settings.email_enabled = False
        out = mod.email_read()
        self.assertIn("Email is off", out)
        self.assertIn("email_enabled", out)

    def test_missing_password_env(self) -> None:
        os.environ.pop(self._env_pw, None)
        out = mod.email_read()
        self.assertIn("environment variable", out)
        self.assertIn(self._env_pw, out)

    def test_incomplete_config(self) -> None:
        settings.email_smtp_server = ""
        out = mod.email_read()
        self.assertIn("email_imap_server, email_smtp_server and email_user", out)

    def test_read_lists_messages(self) -> None:
        msg = EmailMessage()
        msg["Subject"] = "Hello"
        msg["From"] = "boss@example.com"
        msg.set_content("See you tomorrow")
        raw = msg.as_bytes()

        class FakeConn:
            def __init__(self, *a, **k):
                pass

            def login(self, *a):
                return ("OK",)

            def select(self, *a):
                return ("OK", b"1")

            def search(self, *a):
                return ("OK", [b"1 2"])

            def fetch(self, msg_id, *a):
                return ("OK", [(msg_id, raw)])

            def logout(self):
                return ("BYE",)

        with patch("imaplib.IMAP4_SSL", FakeConn):
            out = mod.email_read()
        self.assertIn("Hello", out)
        self.assertIn("boss@example.com", out)
        self.assertIn("See you tomorrow", out)

    def test_read_empty_mailbox(self) -> None:
        class FakeConn:
            def __init__(self, *a, **k):
                pass

            def login(self, *a):
                return ("OK",)

            def select(self, *a):
                return ("OK", b"1")

            def search(self, *a):
                return ("OK", [b""])

            def logout(self):
                return ("BYE",)

        with patch("imaplib.IMAP4_SSL", FakeConn):
            out = mod.email_read()
        self.assertIn("No messages", out)


class EmailSendTest(EmailTest):
    def test_requires_all_fields(self) -> None:
        out = mod.email_send("x@y.com", "", "")
        self.assertIn("recipient, a subject, and a body", out)

    def test_unsafe_recipient(self) -> None:
        out = mod.email_send("x@y.com;rm -rf /", "Hi", "Body")
        self.assertIn("looks unsafe", out)

    def test_send_confirmed_and_sent(self) -> None:
        sent = {}

        class FakeServer:
            def __init__(self, host, port, timeout=None):
                sent["host"] = host

            def starttls(self):
                return ()

            def login(self, user, pw):
                sent["user"] = user
                sent["pw"] = pw

            def send_message(self, m):
                sent["to"] = m["To"]
                sent["subject"] = m["Subject"]

            def quit(self):
                return ()

        with patch("smtplib.SMTP", FakeServer):
            out = mod.email_send("friend@example.com", "Reunion", "Saturday?")
            self.assertIn("permission to send an email", out)
            pending = files.pending_action()
            self.assertIsNotNone(pending)
            result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Email sent to friend@example.com", result)
        self.assertEqual(sent["host"], "smtp.example.com")
        self.assertEqual(sent["user"], "me@example.com")
        self.assertEqual(sent["pw"], "sekrit")
        self.assertEqual(sent["subject"], "Reunion")

    def test_send_denied(self) -> None:
        with patch("smtplib.SMTP"):
            mod.email_send("friend@example.com", "Hi", "Body")
        pending = files.pending_action()
        result = files.resolve_pending(pending["id"], "no")
        self.assertIn("Cancelled", result)


if __name__ == "__main__":
    unittest.main()
