"""
sopno/tools/builtins/knowledge/calendar.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Calendar tools — file-based ICS first (no external service needed).

``calendar_list`` parses ``.ics`` files under ``calendar_dir`` and lists the
upcoming events (read-only). ``calendar_create_event`` appends a VEVENT to
``calendar_dir/calendar.ics`` — write-root gated and confirmed.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sopno.config.settings import settings
from sopno.tools.builtins.files import files as files

# DTSTART/DTEND: 20260816T140000 (local), ...Z (UTC), or date-only 20260816.
_DT = re.compile(r"(\d{8})(?:T(\d{6})(Z)?)?")
_MAX = 20


def _dir() -> tuple[Optional[Path], str]:
    root = getattr(settings, "calendar_dir", "") or "sopno/memory/calendar"
    p = Path(root)
    if not p.is_absolute():
        p = settings.project_root / p
    return p, ""


def _parse_dt(value: str) -> Optional[datetime]:
    m = _DT.fullmatch((value or "").strip().rstrip(";"))
    if not m:
        return None
    date = m.group(1)
    time = m.group(2) or "000000"
    dt = datetime(int(date[:4]), int(date[4:6]), int(date[6:8]),
                  int(time[:2]), int(time[2:4]), int(time[4:6]))
    return dt


def _events(p: Path) -> list[dict]:
    """Parse VEVENT blocks from a single .ics file."""
    events = []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return events
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        def field(name: str) -> str:
            m = re.search(rf"{name}(?:;[^:]*)?:(.*?)(?:\r?\n|$)", block)
            return m.group(1).strip() if m else ""

        summary = field("SUMMARY") or "(untitled event)"
        start = _parse_dt(field("DTSTART"))
        end = _parse_dt(field("DTEND"))
        location = field("LOCATION")
        events.append({
            "summary": summary,
            "start": start,
            "end": end,
            "location": location,
            "file": p.name,
        })
    return events


def calendar_list(limit: int = 10) -> str:
    """
    List upcoming events from the .ics files in the calendar directory.

    Args:
        limit: How many upcoming events to show (1-20, default 10).

    Returns:
        The events, or a reason none can be listed.
    """
    cdir, _ = _dir()
    if not cdir.is_dir():
        return f"No calendar folder yet ({cdir}) — add .ics files or create events."
    limit = max(1, min(int(limit or 10), _MAX))
    now = datetime.now()
    upcoming = []
    for p in sorted(cdir.glob("*.ics")):
        upcoming.extend(_events(p))
    upcoming = [e for e in upcoming if e["start"] is not None and e["start"] >= now - timedelta(hours=1)]
    upcoming.sort(key=lambda e: e["start"] or now)
    if not upcoming:
        return "No upcoming events found in the calendar."
    parts = []
    for e in upcoming[:limit]:
        when = e["start"].strftime("%A, %b %d at %H:%M")
        loc = f" at {e['location']}" if e.get("location") else ""
        parts.append(f"{when} — {e['summary']}{loc}")
    return "Upcoming events:\n" + "\n".join(parts)


def calendar_create_event(summary: str, start: str, end: str,
                          description: str = "") -> str:
    """
    Add an event to the local calendar file (confirmed).

    Args:
        summary: Event title.
        start: Start as 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM'.
        end: End as 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM'.
        description: Optional note.

    Returns:
        Confirmation, or a failure reason.
    """
    if not summary.strip():
        return "The event needs a summary."
    starts, err = _parse_input_dt(start, "start")
    if err:
        return err
    ends, err = _parse_input_dt(end, "end")
    if err:
        return err
    if ends <= starts:
        return "The event must end after it starts."
    cdir, _ = _dir()
    cdir.mkdir(parents=True, exist_ok=True)
    reason = files._authorize(cdir, "write")
    if reason:
        return reason
    target = cdir / "calendar.ics"
    dt_start = starts.strftime("%Y%m%dT%H%M%S")
    dt_end = ends.strftime("%Y%m%dT%H%M%S")
    uid = f"{starts.strftime('%Y%m%d%H%M%S')}@{summary.strip().lower()[:16]}"

    def _do() -> str:
        esc = lambda s: (s or "").replace("\\", "\\\\").replace(",", "\\,").replace("\n", "\\n")  # noqa: E731
        block = (
            "BEGIN:VEVENT\n"
            f"UID:{uid}\n"
            f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%S')}\n"
            f"DTSTART:{dt_start}\n"
            f"DTEND:{dt_end}\n"
            f"SUMMARY:{esc(summary)}\n"
        )
        if description:
            block += f"DESCRIPTION:{esc(description)}\n"
        block += "END:VEVENT\n"
        if target.is_file():
            body = target.read_text(encoding="utf-8", errors="replace")
            if body.rstrip().endswith("END:VCALENDAR"):
                body = body.rstrip()[: -len("END:VCALENDAR")].rstrip() + "\n"
            else:
                body = body.rstrip() + "\n"
            target.write_text(body + block + "END:VCALENDAR\n", encoding="utf-8")
        else:
            target.write_text(
                "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Sopno//Calendar//EN\n"
                + block + "END:VCALENDAR\n",
                encoding="utf-8",
            )
        return f"Event '{summary}' added."

    return files._awaiting_confirmation(f"add the event '{summary}' to the calendar", _do)


def _parse_input_dt(value: str, label: str) -> tuple[Optional[datetime], str]:
    value = (value or "").strip().replace("T", " ").replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt), ""
        except ValueError:
            continue
    return None, f"The {label} time should look like '2026-08-16 14:00'."
