"""
sopno/core/reminders.py
━━━━━━━━━━━━━━━━━━━━━━
One-shot reminders: SQLite-persisted, polled in the background.

Design (from the implementation plan):
- The LLM (or a direct tool call) parses intent into ``(when, text)``;
  ``parse_when`` normalizes natural-language times deterministically.
- Reminders live in their own SQLite DB so a restart never loses them.
  States: ``pending → delivered | cancelled`` (``missed`` reserved).
- A daemon poller thread fires anything ``due_at <= now AND status = pending``
  exactly once (marked delivered in the same transaction — at-least-once, no
  explosion) by pushing it into the reply flow as "Reminder: …".
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from sopno.config.settings import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    due_at TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (status, due_at);
"""

# ── Time parsing ─────────────────────────────────────────────────────────────

_UNIT_SECONDS = {
    "s": 1, "m": 60, "h": 3600, "d": 86400,
    "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
}

_AMPM_REF = "I couldn't understand that time. Try 'in 10 minutes', 'at 9:30pm', or 'tomorrow 9am'."


def _at_hhmm(now: float, base_date, hour: int, minute: int, meridiem: str) -> Optional[float]:
    """Absolute timestamp for a wall-clock time on a date; rolls to tomorrow if past."""
    if not (0 <= minute <= 59) or not (0 <= hour <= 23):
        return None
    h = hour % 24
    if meridiem:
        if meridiem == "pm" and h < 12:
            h += 12
        if meridiem == "am" and h == 12:
            h = 0
    due = datetime(base_date.year, base_date.month, base_date.day, h, minute)
    ts = due.timestamp()
    if ts <= now:
        ts += 86400
    return ts


def parse_when(when: str, now: Optional[float] = None) -> tuple[Optional[float], str]:
    """
    Parse a natural-language time into an absolute epoch timestamp.

    Returns ``(due_ts, error)`` — exactly one is set. Understands:
    "now", "in 10 minutes", "in 2h", "10 minutes", "5min", "2h",
    "9:30pm", "9am", "17:45", "today 9am", "tonight 8pm", "tomorrow 9am",
    "tomorrow", "2026-08-20 14:30", "2026-08-20".
    """
    now = now if now is not None else time.time()
    raw = (when or "").strip().lower()
    if not raw:
        return None, "Tell me when — for example 'in 10 minutes' or 'tomorrow 9am'."

    today = datetime.fromtimestamp(now).date()
    tomorrow = today + timedelta(days=1)

    if raw == "now":
        return now + 5, ""

    m = re.fullmatch(r"in (\d+)\s*([a-z]+)", raw)
    if m and m.group(2) in _UNIT_SECONDS:
        return now + int(m.group(1)) * _UNIT_SECONDS[m.group(2)], ""
    m = re.fullmatch(r"in (\d+)\s*([smhd])", raw)
    if m:
        return now + int(m.group(1)) * _UNIT_SECONDS[m.group(2)], ""
    m = re.fullmatch(r"(\d+)\s*([a-z]+)", raw)
    if m and m.group(2) in _UNIT_SECONDS:
        return now + int(m.group(1)) * _UNIT_SECONDS[m.group(2)], ""
    m = re.fullmatch(r"(\d+)\s*([smhd])", raw)
    if m:
        return now + int(m.group(1)) * _UNIT_SECONDS[m.group(2)], ""

    m = re.fullmatch(
        r"(today|tonight|tomorrow)(?: at)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw
    )
    if m:
        base = today if m.group(1) in ("today", "tonight") else tomorrow
        due = _at_hhmm(now, base, int(m.group(2)), int(m.group(3) or 0), m.group(4) or "")
        if due is None:
            return None, _AMPM_REF
        return due, ""

    m = re.fullmatch(r"(?:at )?(\d{1,2}):(\d{2})\s*(am|pm)?", raw)
    if m:
        due = _at_hhmm(now, today, int(m.group(1)), int(m.group(2)), m.group(3) or "")
        if due is None:
            return None, _AMPM_REF
        return due, ""
    m = re.fullmatch(r"(?:at )?(\d{1,2})\s*(am|pm)", raw)
    if m:
        due = _at_hhmm(now, today, int(m.group(1)), 0, m.group(2))
        if due is None:
            return None, _AMPM_REF
        return due, ""

    if raw in ("tomorrow", "tmr", "next day"):
        return _at_hhmm(now, tomorrow, 9, 0, "am"), ""

    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?: at)?\s*(\d{1,2}):(\d{2})", raw)
    if m:
        try:
            y, mo, d, h, mi = (int(g) for g in m.groups())
            return datetime(y, mo, d, h, mi).timestamp(), ""
        except ValueError:
            return None, _AMPM_REF
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            y, mo, d = (int(g) for g in m.groups())
            return datetime(y, mo, d, 9, 0).timestamp(), ""
        except ValueError:
            return None, _AMPM_REF

    return None, _AMPM_REF


def format_due(due_ts: float) -> str:
    """Human-friendly due time, e.g. 'Sunday, August 16 at 09:00 PM'."""
    return datetime.fromtimestamp(due_ts).strftime("%A, %B %d at %I:%M %p")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ── Store ────────────────────────────────────────────────────────────────────

class ReminderStore:
    """SQLite-backed reminder persistence."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.reminders_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def set(self, text: str, due_at: float) -> int:
        """Store a pending reminder. Returns its id."""
        text = (text or "").strip()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO reminders (due_at, text, status, created_at)"
                " VALUES (?, ?, 'pending', ?)",
                (_iso(due_at), text, _iso(time.time())),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def cancel(self, reminder_id: int) -> bool:
        """Cancel a pending reminder. False if it doesn't exist or is done."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE reminders SET status = 'cancelled'"
                " WHERE id = ? AND status = 'pending'",
                (reminder_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def count_pending(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM reminders WHERE status = 'pending'"
            ).fetchone()
            return int(row["n"])

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        """Upcoming pending reminders + the most recent finished ones."""
        with self._lock:
            now = _iso(time.time())
            upcoming = self._conn.execute(
                "SELECT id, due_at, text, status FROM reminders"
                " WHERE status = 'pending' AND due_at >= ?"
                " ORDER BY due_at ASC LIMIT ?",
                (now, limit),
            ).fetchall()
            recent = self._conn.execute(
                "SELECT id, due_at, text, status FROM reminders"
                " WHERE status != 'pending'"
                " ORDER BY id DESC LIMIT 10",
            ).fetchall()
        return [dict(r) for r in upcoming] + [dict(r) for r in recent]

    def due(self, now: Optional[float] = None) -> list[dict[str, Any]]:
        """
        Fetch and deliver all reminders due at/before ``now``.

        Atomic: they are marked ``delivered`` in the same transaction, so each
        reminder fires exactly once (at-least-once semantics, no explosion).
        """
        now = now if now is not None else time.time()
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, due_at, text FROM reminders"
                " WHERE status = 'pending' AND due_at <= ?"
                " ORDER BY due_at ASC",
                (_iso(now),),
            ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                placeholders = ",".join("?" for _ in ids)
                self._conn.execute(
                    f"UPDATE reminders SET status = 'delivered'"
                    f" WHERE id IN ({placeholders})",
                    ids,
                )
                self._conn.commit()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ── Singleton access (shared by tools and the poller) ────────────────────────

_STORE: Optional[ReminderStore] = None


def get_store() -> ReminderStore:
    """The shared reminder store (lazily created)."""
    global _STORE
    if _STORE is None:
        _STORE = ReminderStore()
    return _STORE


def set_store(store: ReminderStore) -> ReminderStore:
    """Swap in a custom store (used by the assistant and tests)."""
    global _STORE
    _STORE = store
    return _STORE


# ── Poller ───────────────────────────────────────────────────────────────────

class ReminderPoller(threading.Thread):
    """
    Background daemon thread: every ``poll_seconds`` it delivers any due
    reminders through ``deliver(text)`` (e.g. the assistant's reply flow).
    """

    def __init__(
        self,
        deliver: Callable[[str], None],
        poll_seconds: Optional[float] = None,
        run_check: Optional[Callable[[], bool]] = None,
        store: Optional[ReminderStore] = None,
    ) -> None:
        super().__init__(name="reminder-poller", daemon=True)
        self._deliver = deliver
        self._poll = max(1.0, poll_seconds or getattr(settings, "reminders_poll_seconds", 30))
        self._run_check = run_check or (lambda: True)
        self._store = store or get_store()

    def run(self) -> None:
        while self._run_check():
            try:
                for reminder in self._store.due():
                    self._deliver(f"Reminder: {reminder['text']}")
            except Exception:  # noqa: BLE001 — never kill the poller
                pass
            time.sleep(self._poll)
