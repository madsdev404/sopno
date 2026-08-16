"""
sopno/core/agents/scheduler.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AgentScheduler — cron / interval / ETA triggers for long-running agents
(long-running-agents.md, rollout step 3).

Sessions carry an optional ``schedule`` trigger spec on their durable row. This
module parses that spec, computes when it fires next, and — on the poll tick —
enqueues a ``run`` job for the agent through the shared ``AgentQueue``. The
queue is the coordination point: the future worker claims the job and drives
the agent's loop, so a fire never depends on this thread's lifetime and never
double-runs (an idempotency key tied to the fire timestamp dedupes a crash
between enqueue and last-fired bookkeeping).

Trigger grammar (``agents.schedule``):

    interval:<seconds>   every N seconds (first fire N seconds after creation)
    cron:<min> <hour> <dom> <month> <dow>
                         standard 5-field cron; fields support ``*``, ``*/n``,
                         ``a-b``, ``a,b,c`` and 3-letter month/day names.
                         dom/dow combine as: both restricted → OR; one
                         restricted → that one; both ``*`` → every day.
    eta:<YYYY-MM-DD HH:MM:SS>
                         one-shot at an absolute time; clears after firing.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sopno.config.settings import settings

from sopno.core.agents.queue import AgentQueue, get_queue
from sopno.core.agents.session import AgentSessionStore, get_store

# ── Schedule parsing ──────────────────────────────────────────────────────────

_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DOW_NAMES = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}


def _field_value(text: str, lo: int, hi: int, names: Optional[dict] = None) -> int:
    """One cron field value (number or 3-letter name) within [lo, hi]."""
    text = text.strip().lower()
    if names and text in names:
        value = names[text]
    else:
        try:
            value = int(text)
        except ValueError:
            raise ValueError(f"Bad cron value '{text}'.") from None
    if not (lo <= value <= hi):
        raise ValueError(f"Cron value {value} out of range {lo}-{hi}.")
    return value


def _cron_field(field: str, lo: int, hi: int, names: Optional[dict] = None) -> Optional[list[int]]:
    """
    Parse one cron field into a sorted list of allowed values. ``None`` means
    ``*`` (all values) — the callers treat that specially for dom/dow.
    """
    field = (field or "").strip()
    if not field:
        raise ValueError("Empty cron field.")
    if field == "*":
        return None
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            base, _, step_text = part.partition("/")
            step = int(step_text)
            if step < 1:
                raise ValueError(f"Bad cron step in '{part}'.")
        else:
            base = part
        if base == "*":
            values.update(range(lo, hi + 1, step))
        elif "-" in base:
            a, _, b = base.partition("-")
            va = _field_value(a, lo, hi, names)
            vb = _field_value(b, lo, hi, names)
            if va > vb:
                raise ValueError(f"Inverted cron range '{base}'.")
            values.update(range(va, vb + 1, step))
        else:
            values.add(_field_value(base, lo, hi, names))
    if not values:
        raise ValueError(f"Empty cron field '{field}'.")
    return sorted(values)


def parse_schedule(spec: str) -> dict[str, Any]:
    """
    Parse a trigger spec into a normalized dict. Raises ValueError on any
    malformed spec.

    Returns one of::

        {"type": "interval", "seconds": N}
        {"type": "cron", "min": [...], "hour": [...], "dom": [...|None],
         "month": [...|None], "dow": [...|None]}
        {"type": "eta", "at": float}
    """
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("Empty schedule spec.")
    kind, _, body = spec.partition(":")

    if kind == "interval":
        try:
            seconds = int(body.strip())
        except ValueError:
            raise ValueError("interval needs a whole number: 'interval:3600'.") from None
        if seconds < 1:
            raise ValueError("interval must be at least 1 second.")
        return {"type": "interval", "seconds": seconds}

    if kind == "cron":
        parts = body.split()
        if len(parts) != 5:
            raise ValueError("cron needs 5 fields: minute hour dom month dow.")
        minute, hour, dom, month, dow = parts
        return {
            "type": "cron",
            "min": _cron_field(minute, 0, 59),
            "hour": _cron_field(hour, 0, 23),
            "dom": _cron_field(dom, 1, 31),
            "month": _cron_field(month, 1, 12, _MONTH_NAMES),
            "dow": _cron_field(dow, 0, 6, _DOW_NAMES),
        }

    if kind == "eta":
        try:
            at = datetime.strptime(body.strip(), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            raise ValueError(
                "eta needs an ISO timestamp: 'eta:2026-08-20 14:30:00'."
            ) from None
        return {"type": "eta", "at": at}

    raise ValueError("Schedule must start with interval:, cron: or eta:.")


def _cron_next(spec: dict[str, Any], after_ts: float) -> Optional[float]:
    """The next datetime strictly after ``after_ts`` matching the cron spec."""
    minutes = spec["min"] if spec["min"] is not None else list(range(0, 60))
    hours = spec["hour"] if spec["hour"] is not None else list(range(0, 24))
    dom, month, dow = spec["dom"], spec["month"], spec["dow"]
    now = datetime.fromtimestamp(after_ts)
    for day_offset in range(366):
        day = now + timedelta(days=day_offset)
        if month is not None and day.month not in month:
            continue
        dom_ok = day.day in dom if dom is not None else True
        dow_ok = (day.weekday() + 1) % 7 in dow if dow is not None else True
        if dom is not None and dow is not None:
            day_ok = dom_ok or dow_ok
        elif dom is not None:
            day_ok = dom_ok
        elif dow is not None:
            day_ok = dow_ok
        else:
            day_ok = True
        if not day_ok:
            continue
        start_hour = now.hour if day_offset == 0 else 0
        for hour in hours:
            if hour < start_hour:
                continue
            if hour == now.hour and day_offset == 0:
                mins = [m for m in minutes if m > now.minute]
            else:
                mins = minutes
            if mins:
                return day.replace(
                    hour=hour, minute=mins[0], second=0, microsecond=0
                ).timestamp()
    return None


def next_fire_at(spec: dict[str, Any], after_ts: float) -> Optional[float]:
    """
    When this trigger fires next, strictly after ``after_ts``. ``None`` means
    it never fires again (a one-shot ETA already in the past).
    """
    after_ts = float(after_ts)
    if spec["type"] == "interval":
        return after_ts + float(spec["seconds"])
    if spec["type"] == "eta":
        at = float(spec["at"])
        return at if at > after_ts else None
    return _cron_next(spec, after_ts)


def _parse_iso(raw: Optional[str]) -> Optional[float]:
    """Parse the store's ``%Y-%m-%d %H:%M:%S`` timestamps."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


# ── The scheduler thread ──────────────────────────────────────────────────────

class AgentScheduler(threading.Thread):
    """
    Background daemon thread: every ``poll_seconds`` it checks every session
    that carries a schedule and fires any trigger that is due.

    A fire enqueues a ``run`` job (idempotency key tied to the fire timestamp,
    so a crash between enqueue and bookkeeping cannot double-run) and records
    ``last_fired_at``. ``fire_callback(agent, job_id)`` lets a runtime hook the
    fire (e.g. wake a worker); the default just enqueues through the queue.
    """

    def __init__(
        self,
        store: Optional[AgentSessionStore] = None,
        queue: Optional[AgentQueue] = None,
        poll_seconds: Optional[float] = None,
        run_check: Optional[Callable[[], bool]] = None,
        fire_callback: Optional[Callable[[dict[str, Any], int], None]] = None,
    ) -> None:
        super().__init__(name="agent-scheduler", daemon=True)
        self._store = store or get_store()
        self._queue = queue or get_queue()
        self._poll = max(
            1.0, poll_seconds if poll_seconds is not None
            else getattr(settings, "agents_poll_seconds", 30)
        )
        self._run_check = run_check or (lambda: True)
        self._fire_callback = fire_callback

    def run(self) -> None:
        while self._run_check():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 — never kill the scheduler
                pass
            time.sleep(self._poll)

    def tick(self, now: Optional[float] = None) -> list[dict[str, Any]]:
        """
        Fire every due trigger. Returns a list of ``{"agent": dict, "job_id": int}``.
        """
        now = now if now is not None else time.time()
        fired: list[dict[str, Any]] = []
        for agent in self._store.list():
            spec_text = agent.get("schedule")
            if not spec_text:
                continue
            # Terminal or paused sessions don't keep firing their schedule.
            if agent.get("state") in ("done", "dead") or \
                    (agent.get("status") or "") == "paused":
                continue
            try:
                spec = parse_schedule(spec_text)
            except ValueError:
                continue  # malformed schedule — leave for the owner to fix
            last = _parse_iso(agent.get("last_fired_at"))
            anchor = last if last is not None else _parse_iso(agent.get("created_at"))
            if anchor is None:
                anchor = now
            nxt = next_fire_at(spec, anchor)
            if nxt is None or nxt > now:
                continue
            # A fire is a unit of work: one job per fire timestamp. The key is
            # stable across a crash between enqueue and bookkeeping (dedupe),
            # and unique per cadence so consecutive fires each produce a job.
            stamp = f"{int(anchor)}"
            idem = f"run-{agent['id']}-{stamp}"
            job_id = self._queue.enqueue(
                "run",
                {"agent_id": agent["id"]},
                agent_id=agent["id"],
                idempotency_key=idem,
            )
            if spec["type"] == "eta":
                self._store.set_schedule(agent["id"], None)  # one-shot
            self._store.set_last_fired(agent["id"], now)
            if self._fire_callback:
                try:
                    self._fire_callback(agent, job_id)
                except Exception:  # noqa: BLE001
                    pass
            fired.append({"agent": agent, "job_id": job_id})
        return fired


# ── Singleton access (shared by tools / runtime / tests) ─────────────────────

_SCHEDULER: Optional[AgentScheduler] = None


def get_scheduler() -> AgentScheduler:
    """The shared scheduler instance (lazily created)."""
    global _SCHEDULER
    if _SCHEDULER is None:
        _SCHEDULER = AgentScheduler()
    return _SCHEDULER


def set_scheduler(scheduler: Optional[AgentScheduler]) -> Optional[AgentScheduler]:
    """Swap in a custom scheduler (used by the runtime and tests)."""
    global _SCHEDULER
    _SCHEDULER = scheduler
    return _SCHEDULER
