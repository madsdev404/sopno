"""
tests/test_reminders.py
━━━━━━━━━━━━━━━━━━━━━━
Tests for the reminder store, natural-language time parser, tools, and poller.
"""

import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from sopno.config.settings import settings
from sopno.core import reminders
from sopno.tools.builtins import reminders as tools


NOW = datetime(2026, 8, 16, 12, 0, 0).timestamp()  # a Sunday, noon


def _temp_db() -> str:
    return tempfile.mkstemp(suffix=".db")[1]


class ParseWhenTest(unittest.TestCase):
    def parse(self, when: str):
        return reminders.parse_when(when, now=NOW)

    def test_now(self) -> None:
        due, err = self.parse("now")
        self.assertEqual(err, "")
        self.assertEqual(due, NOW + 5)

    def test_in_units(self) -> None:
        for text, delta in (
            ("in 10 minutes", 600),
            ("in 2 hours", 7200),
            ("in 3 days", 259200),
            ("in 30 seconds", 30),
            ("in 1 hour", 3600),
        ):
            due, err = self.parse(text)
            self.assertEqual(err, "", text)
            self.assertAlmostEqual(due, NOW + delta, places=1, msg=text)

    def test_short_units(self) -> None:
        for text, delta in (
            ("in 5m", 300),
            ("in 2h", 7200),
            ("10 minutes", 600),
            ("5min", 300),
            ("2h", 7200),
            ("90 seconds", 90),
        ):
            due, err = self.parse(text)
            self.assertEqual(err, "", text)
            self.assertAlmostEqual(due, NOW + delta, places=1, msg=text)

    def test_time_only_later_today(self) -> None:
        due, err = self.parse("2:30pm")  # 14:30 > noon today
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 16, 14, 30).timestamp(), places=1)

    def test_time_only_rolls_to_tomorrow(self) -> None:
        due, err = self.parse("9am")  # already past 9am today
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 17, 9, 0).timestamp(), places=1)

    def test_24h_time(self) -> None:
        due, err = self.parse("17:45")
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 16, 17, 45).timestamp(), places=1)

    def test_tomorrow_with_time(self) -> None:
        due, err = self.parse("tomorrow 9am")
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 17, 9, 0).timestamp(), places=1)

    def test_tomorrow_alone(self) -> None:
        due, err = self.parse("tomorrow")
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 17, 9, 0).timestamp(), places=1)

    def test_tonight(self) -> None:
        due, err = self.parse("tonight 8pm")
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 16, 20, 0).timestamp(), places=1)

    def test_full_datetime(self) -> None:
        due, err = self.parse("2026-08-20 14:30")
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 20, 14, 30).timestamp(), places=1)

    def test_date_only_midmorning(self) -> None:
        due, err = self.parse("2026-08-20")
        self.assertEqual(err, "")
        self.assertAlmostEqual(due, datetime(2026, 8, 20, 9, 0).timestamp(), places=1)

    def test_bad_input(self) -> None:
        for bad in ("", "sometime", "next tuesday", "banana", "9:99pm"):
            due, err = self.parse(bad)
            self.assertIsNone(due, bad)
            self.assertTrue(err, bad)


class ReminderStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = _temp_db()
        self.store = reminders.ReminderStore(db_path=self.path)

    def tearDown(self) -> None:
        self.store.close()

    def test_set_and_list(self) -> None:
        rid = self.store.set("water the plants", time.time() + 600)
        self.assertGreater(rid, 0)
        rows = self.store.list()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "water the plants")
        self.assertEqual(rows[0]["status"], "pending")

    def test_due_fires_once(self) -> None:
        rid = self.store.set("call the bank", time.time() - 10)
        fired = self.store.due(now=time.time())
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["id"], rid)
        self.assertEqual(fired[0]["text"], "call the bank")
        # Second poll must not re-fire (at-least-once).
        self.assertEqual(self.store.due(now=time.time()), [])

    def test_future_not_due(self) -> None:
        self.store.set("later", time.time() + 3600)
        self.assertEqual(self.store.due(now=time.time()), [])

    def test_cancel(self) -> None:
        rid = self.store.set("do something", time.time() + 600)
        self.assertTrue(self.store.cancel(rid))
        self.assertFalse(self.store.cancel(rid))  # already cancelled
        rows = [r for r in self.store.list() if r["id"] == rid]
        self.assertEqual(rows[0]["status"], "cancelled")

    def test_cancel_unknown_id(self) -> None:
        self.assertFalse(self.store.cancel(999))

    def test_persistence_across_reopen(self) -> None:
        rid = self.store.set("survive restart", time.time() + 3600)
        self.store.close()
        reopened = reminders.ReminderStore(db_path=self.path)
        try:
            rows = reopened.list()
            self.assertTrue(any(r["id"] == rid for r in rows))
        finally:
            reopened.close()

    def test_count_pending(self) -> None:
        self.store.set("a", time.time() + 3600)
        self.store.set("b", time.time() + 7200)
        self.assertEqual(self.store.count_pending(), 2)


class ReminderToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = _temp_db()
        self._old = reminders.get_store()
        reminders.set_store(reminders.ReminderStore(db_path=self.path))
        self._saved_enabled = settings.reminders_enabled
        self._saved_max = settings.reminders_max
        self._saved_horizon = settings.reminders_max_horizon_days
        settings.reminders_enabled = True
        settings.reminders_max = 50
        settings.reminders_max_horizon_days = 365

    def tearDown(self) -> None:
        reminders.set_store(self._old)
        settings.reminders_enabled = self._saved_enabled
        settings.reminders_max = self._saved_max
        settings.reminders_max_horizon_days = self._saved_horizon

    def test_set_reminder(self) -> None:
        out = tools.set_reminder("in 10 minutes", "water the plants")
        self.assertIn("Done", out)
        self.assertIn("water the plants", out)
        self.assertRegex(out, r"reminder \d+ set")
        self.assertTrue(reminders.get_store().count_pending() >= 1)

    def test_set_reminder_malformed_when(self) -> None:
        out = tools.set_reminder("sometime next week", "x")
        self.assertIn("couldn't understand", out)
        self.assertEqual(reminders.get_store().count_pending(), 0)

    def test_set_reminder_empty_text(self) -> None:
        out = tools.set_reminder("9pm", "")
        self.assertIn("what to remind", out)

    def test_set_reminder_horizon_cap(self) -> None:
        settings.reminders_max_horizon_days = 1
        out = tools.set_reminder("2026-12-01 12:00", "x")
        self.assertIn("days away", out)

    def test_set_reminder_max_pending(self) -> None:
        settings.reminders_max = 2
        tools.set_reminder("9pm", "a")
        tools.set_reminder("10pm", "b")
        out = tools.set_reminder("11pm", "c")
        self.assertIn("cancel one first", out)

    def test_list_reminders(self) -> None:
        tools.set_reminder("in 1 hour", "stretch")
        out = tools.list_reminders()
        self.assertIn("stretch", out)
        self.assertIn("#1", out)
        self.assertIn("in ", out)

    def test_cancel_reminder(self) -> None:
        tools.set_reminder("in 1 hour", "stretch")
        rows = reminders.get_store().list()
        rid = str(rows[0]["id"])
        out = tools.cancel_reminder(rid)
        self.assertIn("Done", out)
        self.assertIn("cancelled", tools.list_reminders())

    def test_cancel_reminder_unknown(self) -> None:
        out = tools.cancel_reminder("9999")
        self.assertIn("No reminder with id", out)

    def test_cancel_reminder_bad_id(self) -> None:
        self.assertIn("isn't a reminder id", tools.cancel_reminder("abc"))

    def test_disabled(self) -> None:
        settings.reminders_enabled = False
        self.assertIn("disabled", tools.set_reminder("9pm", "x"))
        self.assertIn("disabled", tools.list_reminders())


class ReminderPollerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = _temp_db()
        self._old = reminders.get_store()
        self.store = reminders.ReminderStore(db_path=self.path)
        reminders.set_store(self.store)

    def tearDown(self) -> None:
        reminders.set_store(self._old)
        self.store.close()

    def test_poller_delivers_due_reminders(self) -> None:
        self.store.set("drink water", time.time() - 5)
        self.store.set("future task", time.time() + 3600)
        delivered: list[str] = []
        checks = [True]

        def run_once() -> bool:
            keep = checks[0]
            checks[0] = False
            return keep

        poller = reminders.ReminderPoller(
            deliver=delivered.append,
            poll_seconds=1,
            run_check=run_once,
            store=self.store,
        )
        poller.run()
        self.assertEqual(delivered, ["Reminder: drink water"])
        # Delivered status persisted.
        self.assertEqual(self.store.due(now=time.time()), [])


if __name__ == "__main__":
    unittest.main()
