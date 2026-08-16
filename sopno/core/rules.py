"""
sopno/core/rules.py
━━━━━━━━━━━━━━━━━━
Automation rules — "if {condition} then {action}", persisted in SQLite and
checked by a background poller.

Security model:
  - Conditions are restricted to an allowlist of read-only numeric metrics and
    comparison operators — never ``eval``-ed.
  - Actions are existing registered tools invoked via the registry. The user
    approves a rule once at creation; when it fires, any pending-action gate
    the tool raises is auto-approved (the rule itself was the confirmation).
"""

from __future__ import annotations

import re
import shlex
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import psutil

from sopno.config.settings import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    condition TEXT NOT NULL,
    action TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_fired TEXT,
    fire_count INTEGER NOT NULL DEFAULT 0
);
"""

_CONDITION = re.compile(
    r"^\s*(?P<metric>[a-z_0-9]+)\s*(?P<op><=|>=|<|>|==)\s*(?P<value>\d+(?:\.\d+)?)\s*$"
)

_METRICS = (
    "battery_percent",   # 0-100
    "cpu_percent",       # 0-100
    "ram_percent",       # 0-100
    "disk_free_gb",      # gigabytes free on /
    "hour_of_day",       # 0-23
    "day_of_week",       # 0=Monday .. 6=Sunday
)


def _read_metric(name: str) -> float:
    """Read a metric; raises ValueError for unknown names or unreadable data."""
    if name == "battery_percent":
        bat = psutil.sensors_battery()
        if not bat:
            raise ValueError("no battery present")
        return float(bat.percent)
    if name == "cpu_percent":
        return float(psutil.cpu_percent(interval=0.1))
    if name == "ram_percent":
        return float(psutil.virtual_memory().percent)
    if name == "disk_free_gb":
        return float(psutil.disk_usage("/").free) / (1024 ** 3)
    if name == "hour_of_day":
        return float(datetime.now().hour)
    if name == "day_of_week":
        return float(datetime.now().weekday())
    raise ValueError(f"unknown metric '{name}'")


def _evaluate(condition: str) -> bool:
    m = _CONDITION.match(condition or "")
    if not m:
        raise ValueError(
            "Condition must look like 'battery_percent < 20' — metric, operator "
            "(< <= > >= ==), then a number."
        )
    metric, op, value = m.group("metric"), m.group("op"), float(m.group("value"))
    if metric not in _METRICS:
        raise ValueError(
            f"Unknown metric '{metric}'. Allowed: {', '.join(_METRICS)}."
        )
    current = _read_metric(metric)
    if op == "<":
        return current < value
    if op == "<=":
        return current <= value
    if op == ">":
        return current > value
    if op == ">=":
        return current >= value
    return current == value


def _parse_action(action: str) -> tuple[str, dict]:
    from sopno.tools.registry import get_registered_names

    parts = shlex.split(action or "")
    if not parts:
        raise ValueError("The action is empty.")
    tool = parts[0]
    args: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            raise ValueError(f"Action argument '{part}' must be key=value.")
        key, _, val = part.partition("=")
        args[key.strip()] = val
    if tool not in get_registered_names():
        raise ValueError(f"Tool '{tool}' is not registered.")
    return tool, args


class RuleStore:
    """SQLite persistence + condition evaluation for automation rules."""

    def __init__(self, path=None):
        self.db_path = Path(path) if path else settings.rules_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(self.db_path)
        self._prev_true: set[int] = set()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass

    def add(self, name: str, condition: str, action: str) -> int:
        """Validate then insert a rule; returns its id."""
        _evaluate(condition)  # raises on invalid condition
        _parse_action(action)  # raises on invalid action
        name = (name or "").strip()[:100]
        if not name:
            raise ValueError("The rule needs a name.")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO rules (name, condition, action, created_at) VALUES (?,?,?,?)",
                (name, condition.strip(), action.strip(),
                 datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_rules(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM rules ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def remove(self, rule_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def set_enabled(self, rule_id: int, enabled: bool) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE rules SET enabled=? WHERE id=?", (1 if enabled else 0, rule_id)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def _mark_fired(self, rule_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE rules SET last_fired=?, fire_count=fire_count+1 WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), rule_id),
            )
            self._conn.commit()

    def run(self) -> list[str]:
        """Check every enabled rule; fire (once per true-period) and return results."""
        results: list[str] = []
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM rules WHERE enabled=1"
            ).fetchall()
        for row in rows:
            rule_id = int(row["id"])
            try:
                matched = _evaluate(row["condition"])
            except Exception:  # noqa: BLE001
                matched = False
            was_true = rule_id in self._prev_true
            if matched and not was_true:
                self._prev_true.add(rule_id)
                out = self._fire(row)
                if out:
                    results.append(f"{row['name']}: {out}")
            elif not matched:
                self._prev_true.discard(rule_id)
        return results

    def _fire(self, row) -> str:
        from sopno.tools.builtins import files
        from sopno.tools.registry import execute_tool

        try:
            tool, args = _parse_action(row["action"])
            out = execute_tool(tool, args)
            if files.pending_action() is not None:
                pending = files.pending_action()
                assert pending is not None
                approved = files.resolve_pending(pending["id"], "yes") or "Done."
                out = f"{out} {approved}".strip()
            self._mark_fired(int(row["id"]))
            return out
        except Exception as e:  # noqa: BLE001
            return f"action failed: {e}"


class RulePoller(threading.Thread):
    """Daemon thread that periodically checks enabled rules and fires them."""

    def __init__(self, store: RuleStore, deliver: Callable[[str], None],
                 run_check: Callable[[], bool]):
        super().__init__(daemon=True, name="sopno-rules")
        self._store = store
        self._deliver = deliver
        self._run_check = run_check
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        interval = float(getattr(settings, "rules_poll_seconds", 60))
        while not self._stop.wait(interval):
            if not self._run_check():
                break
            try:
                for result in self._store.run():
                    self._deliver(result)
            except Exception as e:  # noqa: BLE001
                pass


# module-level instance for tools/tests to share
_store: Optional[RuleStore] = None


def get_store() -> Optional[RuleStore]:
    return _store


def set_store(store: Optional[RuleStore]) -> None:
    global _store
    _store = store
