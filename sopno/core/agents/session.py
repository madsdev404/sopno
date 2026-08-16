"""
sopno/core/agents/session.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Durable agent sessions — the state machine + store behind long-running
background agents (long-running-agents.md, rollout step 1).

An agent session is the durable *identity* of a background agent: its name,
goal, current state, plan, working memory, alignment record, and budget — all
outside the LLM context window, checkpointed to SQLite after every transition.
The append-only action log is the audit trail: if you can't reconstruct what an
agent did in the last 24 hours from durable storage, what you have is a
long-running shell script that happens to call an LLM.

Lifecycle (every transition is a row write — a checkpoint):

    created → ready → running → waiting_human ─┐
               ↑        │                      │ (approval / reply event)
               └────────┴─ resumed → running → done | blocked | dead

  - ``waiting_human`` sessions don't poll — they sleep in the DB; a human
    reply, webhook, file event, or schedule resumes them (event-driven
    dormancy).
  - ``done`` and ``dead`` are terminal: no further transitions.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sopno.config.settings import settings

# ── State machine ─────────────────────────────────────────────────────────────

_STATES = frozenset({
    "created", "ready", "running", "waiting_human",
    "done", "blocked", "dead",
})

# Allowed transitions; every other pair raises ValueError.
_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"ready", "dead"}),
    "ready": frozenset({"running", "dead"}),
    # ``running -> ready`` is how a worker parks a session that has made
    # progress on a job but is now dormant until its next trigger (schedule /
    # event / manual resume). It is NOT a failure — it is event-driven dormancy.
    "running": frozenset({"running", "ready", "waiting_human", "done", "blocked", "dead"}),
    "waiting_human": frozenset({"running", "done", "dead"}),
    "blocked": frozenset({"running", "done", "dead"}),
    "done": frozenset(),
    "dead": frozenset(),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    goal TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'created',
    status TEXT NOT NULL DEFAULT 'idle',
    kind TEXT NOT NULL DEFAULT 'general',      -- 'general' | 'coding' (task driver)
    plan TEXT NOT NULL DEFAULT '[]',              -- JSON task graph / step list
    working_memory TEXT NOT NULL DEFAULT '[]',    -- JSON list of entries
    alignment TEXT NOT NULL DEFAULT '[]',         -- JSON list of corrections
    pending_input TEXT NOT NULL DEFAULT '[]',     -- JSON messages queued by agent_send
    pending_action TEXT,                          -- JSON {id, description} approval gate
    tools TEXT NOT NULL DEFAULT '[]',             -- per-agent tool allowlist (JSON)
    schedule TEXT,                                -- cron / interval trigger spec
    budget TEXT NOT NULL DEFAULT '{}',            -- JSON budget: turns/tokens/wall/actions
    budget_used INTEGER NOT NULL DEFAULT 0,
    last_fired_at TEXT,                           -- last schedule fire (scheduler bookkeeping)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_state ON agents (state, updated_at);

CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    kind TEXT NOT NULL,                           -- action | message | transition | error
    detail TEXT NOT NULL,                         -- JSON or free text
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_actions_agent ON agent_actions (agent_id, id);
"""

# Per-agent working-memory cap (entries kept after truncation).
_MAX_MEMORY = 200
_MAX_INPUT = 100


def _iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time()).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(raw: Optional[str], fallback: Any) -> Any:
    try:
        return json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback


def valid_transition(current: str, target: str) -> bool:
    """Whether ``current -> target`` is allowed by the state machine."""
    return target in _TRANSITIONS.get(current, frozenset())


class AgentSessionStore:
    """
    SQLite-backed store for durable agent sessions.

    Each agent row is a checkpoint; every state transition is a row write plus
    an append-only entry in the action log. Safe to use from multiple threads
    (RLock + WAL) and to reopen across process restarts (crash-resume).
    """

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.agents_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            # Migrations for columns added after the first release: the
            # scheduler's last_fired_at (step 3) and the worker's kind /
            # pending_action (steps 4-6). Each is a no-op when already present.
            for column, definition in (
                ("last_fired_at", "TEXT"),
                ("kind", "TEXT NOT NULL DEFAULT 'general'"),
                ("pending_action", "TEXT"),
            ):
                try:
                    self._conn.execute(
                        f"ALTER TABLE agents ADD COLUMN {column} {definition}"
                    )
                    self._conn.commit()
                except sqlite3.OperationalError:
                    pass  # column already present
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass

    # ── Row helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        out["plan"] = _loads(out.get("plan"), [])
        out["working_memory"] = _loads(out.get("working_memory"), [])
        out["alignment"] = _loads(out.get("alignment"), [])
        out["pending_input"] = _loads(out.get("pending_input"), [])
        out["tools"] = _loads(out.get("tools"), [])
        out["budget"] = _loads(out.get("budget"), {})
        out["pending_action"] = _loads(out.get("pending_action"), None)
        return out

    def _log(self, agent_id: int, kind: str, detail: str) -> None:
        self._conn.execute(
            "INSERT INTO agent_actions (agent_id, kind, detail, created_at)"
            " VALUES (?, ?, ?, ?)",
            (agent_id, kind, detail, _iso()),
        )

    def _touch(self, agent_id: int) -> None:
        self._conn.execute(
            "UPDATE agents SET updated_at = ? WHERE id = ?",
            (_iso(), agent_id),
        )

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        goal: str,
        *,
        schedule: Optional[str] = None,
        tools: Optional[list[str]] = None,
        budget: Optional[dict] = None,
        kind: str = "general",
    ) -> int:
        """
        Create a session in the ``created`` state. Returns its id.

        Args:
            name: Unique agent name (the identity that outlives any run).
            goal: The durable objective, written down so a fresh context
                  window can pick it up.
            schedule: Optional trigger spec (cron / interval / ETA) for the
                      future scheduler.
            tools: Per-agent tool allowlist (least authority). Empty = default.
            budget: Dict of ceilings, e.g. ``{"max_turns": 50,
                    "max_wall_minutes": 120, "max_actions_per_day": 100}``.
            kind: The task driver — ``"general"`` (LLM loop) or ``"coding"``
                  (the CodingAgent in a git worktree).
        """
        name = (name or "").strip()
        goal = (goal or "").strip()
        if not name:
            raise ValueError("An agent needs a name.")
        if not goal:
            raise ValueError("An agent needs a goal.")
        if len(name) > 100:
            raise ValueError("Agent name is too long (max 100 characters).")
        if len(goal) > 8000:
            raise ValueError("Agent goal is too long (max 8000 characters).")
        kind = (kind or "general").strip()[:20] or "general"
        now = _iso()
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO agents (name, goal, state, status, kind, schedule,"
                    " tools, budget, created_at, updated_at)"
                    " VALUES (?, ?, 'created', 'idle', ?, ?, ?, ?, ?, ?)",
                    (name, goal, kind, schedule,
                     _dumps(list(tools) if tools else []),
                     _dumps(dict(budget) if budget else {}),
                     now, now),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"An agent named '{name}' already exists.") from None
            agent_id = int(cur.lastrowid)
            self._log(agent_id, "transition", "created")
            self._conn.commit()
            return agent_id

    def delete(self, agent_id: int) -> bool:
        """Remove a session and its action log. False if it didn't exist."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            self._conn.execute("DELETE FROM agent_actions WHERE agent_id = ?", (agent_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def get(self, agent_id: int) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agents WHERE id = ?", (agent_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_name(self, name: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agents WHERE name = ?", (name or "",)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        """All sessions, newest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM agents ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM agents").fetchone()
            return int(row["n"])

    # ── State machine ─────────────────────────────────────────────────────────

    def _require(self, agent_id: int) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"No agent session with id {agent_id}.")
        return row

    def transition(self, agent_id: int, target: str) -> dict[str, Any]:
        """
        Move a session to ``target``. Validates against the state machine and
        checkpoints the row (every transition is a write). Raises ValueError
        for unknown ids or illegal transitions.
        """
        target = (target or "").strip()
        if target not in _STATES:
            raise ValueError(
                f"Unknown agent state '{target}'. Allowed: {sorted(_STATES)}."
            )
        with self._lock:
            row = self._require(agent_id)
            current = row["state"]
            if current == target:
                self._touch(agent_id)
                self._conn.commit()
                return self._row_to_dict(
                    self._conn.execute(
                        "SELECT * FROM agents WHERE id = ?", (agent_id,)
                    ).fetchone()
                )
            if not valid_transition(current, target):
                raise ValueError(f"Cannot transition agent {agent_id} from "
                                 f"'{current}' to '{target}'.")
            self._conn.execute(
                "UPDATE agents SET state = ?, updated_at = ? WHERE id = ?",
                (target, _iso(), agent_id),
            )
            self._log(agent_id, "transition", f"{current} -> {target}")
            self._conn.commit()
            return self._row_to_dict(
                self._conn.execute(
                    "SELECT * FROM agents WHERE id = ?", (agent_id,)
                ).fetchone()
            )

    def heartbeat(self, agent_id: int) -> bool:
        """
        Refresh ``updated_at`` for a running session (the worker's watchdog
        signal). False if the session no longer exists.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE agents SET updated_at = ? WHERE id = ? AND state = 'running'",
                (_iso(), agent_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ── Fields (each is a checkpoint) ─────────────────────────────────────────

    def _update_fields(self, agent_id: int, **fields) -> None:
        self._require(agent_id)
        columns = list(fields.keys())
        for col in columns:
            if col not in (
                "plan", "working_memory", "alignment", "pending_input",
                "tools", "schedule", "budget", "status", "goal", "last_fired_at",
                "pending_action", "kind",
            ):
                raise ValueError(f"Unknown agent field '{col}'.")
        assignments = ", ".join(f"{c} = ?" for c in columns)
        values = [fields[c] for c in columns]
        self._conn.execute(
            f"UPDATE agents SET {assignments}, updated_at = ? WHERE id = ?",
            (*values, _iso(), agent_id),
        )
        self._conn.commit()

    def set_plan(self, agent_id: int, plan: list) -> None:
        """Store the task graph / ordered step list (JSON)."""
        self._update_fields(agent_id, plan=_dumps(list(plan)))

    def set_status(self, agent_id: int, status: str) -> None:
        self._update_fields(agent_id, status=(status or "idle")[:50])

    def set_schedule(self, agent_id: int, schedule: Optional[str]) -> None:
        self._update_fields(agent_id, schedule=schedule)

    def set_budget(self, agent_id: int, budget: dict) -> None:
        self._update_fields(agent_id, budget=_dumps(dict(budget)))

    def set_last_fired(self, agent_id: int, ts: Optional[float]) -> None:
        """Record when the scheduler last fired this session's trigger."""
        self._update_fields(agent_id, last_fired_at=_iso(ts) if ts is not None else None)

    def set_kind(self, agent_id: int, kind: str) -> None:
        """Set the task driver: 'general' (LLM loop) or 'coding' (CodingAgent)."""
        self._update_fields(agent_id, kind=(kind or "general").strip()[:20] or "general")

    def set_pending_action(self, agent_id: int, action: Optional[dict]) -> None:
        """
        Checkpoint an approval gate the agent parked on (``{id, description}``).
        Persisted so a crash can't lose the question the human is being asked.
        """
        self._update_fields(
            agent_id,
            pending_action=_dumps(dict(action)) if action else None,
        )

    def bump_budget_used(self, agent_id: int, amount: int = 1) -> int:
        """Add to the budget-usage counter; returns the new total."""
        with self._lock:
            self._require(agent_id)
            self._conn.execute(
                "UPDATE agents SET budget_used = budget_used + ?, updated_at = ?"
                " WHERE id = ?",
                (int(amount), _iso(), agent_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT budget_used FROM agents WHERE id = ?", (agent_id,)
            ).fetchone()
            return int(row["budget_used"])

    _DELTA_FIELDS = frozenset({
        "plan", "working_memory", "alignment", "tools", "budget",
        "schedule", "status", "goal", "kind",
    })

    def apply_state_delta(self, agent_id: int, delta: dict) -> None:
        """
        Apply an event's ``state_delta`` atomically before a resume: a dict of
        session fields to checkpoint. List/dict values are JSON-encoded; unknown
        fields are rejected; ``None`` values are ignored.
        """
        delta = dict(delta or {})
        bad = [k for k in delta if k not in self._DELTA_FIELDS]
        if bad:
            raise ValueError(f"Unknown state_delta fields: {sorted(bad)}")
        encoded: dict[str, Any] = {}
        for key, value in delta.items():
            if value is None:
                continue
            if isinstance(value, (list, dict)):
                encoded[key] = _dumps(value)
            else:
                encoded[key] = str(value)
        if encoded:
            self._update_fields(agent_id, **encoded)
    # ── Working memory & alignment (the durable stores) ───────────────────────

    def append_memory(self, agent_id: int, entry: str) -> int:
        """
        Add a key fact/decision to working memory (capped). Returns the new
        number of entries.
        """
        entry = (entry or "").strip()
        if not entry:
            return -1
        with self._lock:
            row = self._require(agent_id)
            memory = _loads(row["working_memory"], [])
            memory.append({"text": entry, "at": _iso()})
            memory = memory[-_MAX_MEMORY:]
            self._update_fields(agent_id, working_memory=_dumps(memory))
            return len(memory)

    def add_alignment(self, agent_id: int, correction: str) -> int:
        """
        Append a correction / preference to the alignment record (capped).
        These are injected into the ORIENT phase of a resume.
        """
        correction = (correction or "").strip()
        if not correction:
            return -1
        with self._lock:
            row = self._require(agent_id)
            alignment = _loads(row["alignment"], [])
            alignment.append({"text": correction, "at": _iso()})
            alignment = alignment[-_MAX_MEMORY:]
            self._update_fields(agent_id, alignment=_dumps(alignment))
            return len(alignment)

    # ── Pending input (event-driven wake) ─────────────────────────────────────

    def enqueue_input(self, agent_id: int, message: str) -> int:
        """
        Queue an incoming message (a human approval, a webhook, a file event).
        Returns the number of pending messages.
        """
        message = (message or "").strip()
        if not message:
            return -1
        with self._lock:
            row = self._require(agent_id)
            pending = _loads(row["pending_input"], [])
            pending.append({"text": message, "at": _iso()})
            pending = pending[-_MAX_INPUT:]
            self._update_fields(agent_id, pending_input=_dumps(pending))
            return len(pending)

    def drain_input(self, agent_id: int) -> list[dict]:
        """Fetch and clear all pending input messages (returns them)."""
        with self._lock:
            row = self._require(agent_id)
            pending = _loads(row["pending_input"], [])
            self._update_fields(agent_id, pending_input=_dumps([]))
            return pending

    # ── Audit log ─────────────────────────────────────────────────────────────

    def log_action(self, agent_id: int, kind: str, detail: str) -> int:
        """Append an entry to the agent's action log (kind: action/message/error)."""
        kind = (kind or "action").strip()[:30]
        detail = str(detail or "")
        with self._lock:
            self._require(agent_id)
            self._log(agent_id, kind, detail[:4000])
            self._conn.commit()
            row = self._conn.execute(
                "SELECT id FROM agent_actions WHERE agent_id = ? ORDER BY id DESC"
                " LIMIT 1",
                (agent_id,),
            ).fetchone()
            return int(row["id"])

    def action_log(self, agent_id: int, limit: int = 100) -> list[dict[str, Any]]:
        """The append-only audit trail, newest first."""
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, agent_id, kind, detail, created_at FROM agent_actions"
                " WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Singleton access (shared by tools / runtime / tests) ─────────────────────

_STORE: Optional[AgentSessionStore] = None


def get_store() -> AgentSessionStore:
    """The shared agent-session store (lazily created)."""
    global _STORE
    if _STORE is None:
        _STORE = AgentSessionStore()
    return _STORE


def set_store(store: Optional[AgentSessionStore]) -> Optional[AgentSessionStore]:
    """Swap in a custom store (used by the assistant runtime and tests)."""
    global _STORE
    _STORE = store
    return _STORE
