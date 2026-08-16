"""
tests/test_calendar.py
━━━━━━━━━━━━━━━━━━━━━
Calendar tools: ICS parsing/list of upcoming events, event creation with
confirmation and .ics append, and input-time validation.
"""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sopno.config.settings import settings
from sopno.tools.builtins import calendar as mod
from sopno.tools.builtins import files


class CalendarTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "dir": getattr(settings, "calendar_dir", ""),
            "roots": list(settings.file_allowed_write),
        }
        self.tmp = Path(tempfile.mkdtemp(prefix="sopno-cal-test-"))
        settings.file_allowed_write = [str(self.tmp)]
        settings.calendar_dir = str(self.tmp)
        self.ics = self.tmp / "cal.ics"

    def tearDown(self) -> None:
        settings.calendar_dir = self._saved["dir"]
        settings.file_allowed_write = self._saved["roots"]

    def _write_sample(self) -> None:
        future = ((datetime.now() + timedelta(days=1)).strftime("%Y%m%d") + "T150000")
        self.ics.write_text(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
            f"UID:1\nDTSTART:{future}\nDTEND:20290101T160000\n"
            "SUMMARY:Standup\nLOCATION:Kitchen\nEND:VEVENT\nEND:VCALENDAR\n",
            encoding="utf-8",
        )

    def test_empty_calendar_folder(self) -> None:
        self.assertIn("No upcoming events", mod.calendar_list())

    def test_no_upcoming_events(self) -> None:
        self.ics.write_text(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:1\n"
            "DTSTART:20000101T100000\nDTEND:20000101T110000\n"
            "SUMMARY:Old\nEND:VEVENT\nEND:VCALENDAR\n",
            encoding="utf-8",
        )
        self.assertIn("No upcoming events", mod.calendar_list())

    def test_lists_upcoming(self) -> None:
        self._write_sample()
        out = mod.calendar_list()
        self.assertIn("Standup", out)
        self.assertIn("Kitchen", out)

    def test_bad_start_time(self) -> None:
        out = mod.calendar_create_event("Party", "someday", "2026-08-16 15:00")
        self.assertIn("start time should look like", out)

    def test_end_before_start(self) -> None:
        out = mod.calendar_create_event(
            "Party", "2026-08-16 15:00", "2026-08-16 14:00"
        )
        self.assertIn("must end after it starts", out)

    def test_create_confirmed_appends(self) -> None:
        self._write_sample()
        out = mod.calendar_create_event(
            "Lunch", "2026-09-01 12:00", "2026-09-01 13:00", "Pizza"
        )
        self.assertIn("permission to add the event 'Lunch'", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("added", result)
        text = (self.tmp / "calendar.ics").read_text(encoding="utf-8")
        self.assertIn("SUMMARY:Lunch", text)
        self.assertIn("DESCRIPTION:Pizza", text)
        self.assertIn("DTSTART:20260901T120000", text)
        self.assertIn("DTEND:20260901T130000", text)
        self.assertIn("END:VCALENDAR", text)

    def test_create_into_missing_dir(self) -> None:
        settings.calendar_dir = str(self.tmp / "nested")
        mod.calendar_create_event("One-off", "2026-10-01 09:00", "2026-10-01 10:00")
        pending = files.pending_action()
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("added", result)
        self.assertTrue((self.tmp / "nested" / "calendar.ics").is_file())

    def test_escapes_commas_and_newlines(self) -> None:
        mod.calendar_create_event(
            "Notes, meeting", "2026-10-01 09:00", "2026-10-01 10:00", "line1\nline2"
        )
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        text = (self.tmp / "calendar.ics").read_text(encoding="utf-8")
        self.assertIn("SUMMARY:Notes\\, meeting", text)
        self.assertIn("DESCRIPTION:line1\\nline2", text)


if __name__ == "__main__":
    unittest.main()
