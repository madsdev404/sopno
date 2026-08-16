"""
sopno/tools/builtins/automation/reminders.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
One-shot reminder tools (voice-invokable via the LLM).

  set_reminder(when, text)   → parse a natural-language time, store it
  list_reminders()           → upcoming + recent reminders
  cancel_reminder(id)        → cancel a pending reminder

Setting a reminder is non-destructive (no confirmation). Cancelling only
applies to an existing pending id. Delivery happens in the background poller
(``sopno/core/reminders.ReminderPoller``) driven by ``SopnoAssistant.run``.
"""

from __future__ import annotations

import time

from sopno.config.settings import settings
from sopno.core import reminders


def _store() -> reminders.ReminderStore:
    return reminders.get_store()


def set_reminder(when: str, text: str) -> str:
    """
    Set a one-shot reminder.

    Args:
        when: Natural-language time, e.g. "in 10 minutes", "9:30pm",
            "tomorrow 9am", "2026-08-20 14:30".
        text: What to remind about.

    Returns:
        Confirmation with the scheduled time and reminder id, or a reason.
    """
    if not settings.reminders_enabled:
        return "Reminders are disabled (reminders_enabled = false in config.json)."
    text = (text or "").strip()
    if not text:
        return "Tell me what to remind you about."

    due_ts, err = reminders.parse_when(when)
    if err:
        return err

    now = time.time()
    horizon = settings.reminders_max_horizon_days * 86400
    if due_ts - now > horizon:
        return (f"That's more than {settings.reminders_max_horizon_days} days away — "
                f"I only plan that far ahead.")
    if _store().count_pending() >= settings.reminders_max:
        return f"You already have {settings.reminders_max} reminders pending — cancel one first."

    rid = _store().set(text, due_ts)
    return (f"Done — reminder {rid} set for {reminders.format_due(due_ts)}: '{text}'.")


def list_reminders() -> str:
    """
    List upcoming and recent reminders.

    Returns:
        Formatted lines, or a message when there are none.
    """
    if not settings.reminders_enabled:
        return "Reminders are disabled (reminders_enabled = false in config.json)."
    rows = _store().list()
    if not rows:
        return "You have no reminders right now."

    lines = []
    for r in rows:
        state = {
            "pending": "in",
            "delivered": "done",
            "cancelled": "cancelled",
            "missed": "missed",
        }.get(r["status"], r["status"])
        if r["status"] == "pending":
            lines.append(f"#{r['id']} {state} {r['due_at']} — {r['text']}")
        else:
            lines.append(f"#{r['id']} ({state}) {r['due_at']} — {r['text']}")
    return "\n".join(lines)


def cancel_reminder(id: str) -> str:
    """
    Cancel a pending reminder by id.

    Args:
        id: The reminder id (from list_reminders).

    Returns:
        Confirmation, or a reason it cannot be cancelled.
    """
    if not settings.reminders_enabled:
        return "Reminders are disabled (reminders_enabled = false in config.json)."
    try:
        rid = int(str(id).strip())
    except (TypeError, ValueError):
        return f"'{id}' isn't a reminder id — use list_reminders to see them."
    if not _store().cancel(rid):
        pending = _store().list()
        if not any(r["id"] == rid for r in pending):
            return f"No reminder with id {rid}."
        return f"Reminder {rid} is already done or cancelled."
    return f"Done — cancelled reminder {rid}."
