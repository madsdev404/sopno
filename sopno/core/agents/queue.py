"""
sopno/core/agents/queue.py
━━━━━━━━━━━━━━━━━━━━━━━━━
AgentQueue — a SQLite durable job queue for long-running agents
(long-running-agents.md, rollout step 2).

This is what makes an agent *recoverable and auditable*: every unit of work is
a job row that survives restarts. A worker atomically **claims** a ready job
(one job → exactly one worker), renews a **lease** (heartbeat) while working,
and either **finishes**, **fails** (retry with exponential backoff + jitter,
then a dead-letter state), or is reclaimed by **orphan recovery** when its
lease expires without a heartbeat. **Idempotency keys** deduplicate re-delivered
events/actions.

Job lifecycle:

    ready → running → done
      │        │      └ (lease expiry, no heartbeat) ──▶ ready | dead
      │        └→ failed ──▶ ready (backoff) | dead   (attempts exhausted)
      └→ cancelled
"""

from __future__ import annotations

import random
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from sopno.config.settings import settings

_JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER,
    kind TEXT NOT NULL,                           -- e.g. 'run' | 'message' | 'event'
    payload TEXT NOT NULL DEFAULT '{}',           -- JSON arguments
    status TEXT NOT NULL DEFAULT 'ready',         -- ready|running|done|failed|dead|cancelled
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    idempotency_key TEXT,
    next_attempt_at TEXT,                         -- backoff gate; NULL = claimable
    lease_owner TEXT,
    lease_until TEXT,                             -- ISO; NULL while ready
    heartbeat_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_jobs_idem
    ON agent_jobs (idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_jobs_ready ON agent_jobs (status, next_attempt_at, id);
"""

_STATUSES = frozenset({"ready", "running", "done", "failed", "dead", "cancelled"})


def _iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time()).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _backoff_seconds(
    attempt: int,
    base: float,
    cap: float,
    jitter: Callable[[], float] = random.random,
) -> float:
    """
    Exponential backoff with jitter: ``base * 2**(attempt-1)`` capped, then
    scaled by ``1 + jitter()`` (0.5 scale). Deterministic tests can inject a
    jitter function.
    """
    if attempt <= 0:
        return 0.0
    raw = min(cap, base * (2 ** (attempt - 1)))
    return raw * (1.0 + max(0.0, jitter()))


class AgentQueue:
    """
    SQLite-backed job queue with atomic claim, leases, retries and a
    dead-letter state. Safe across threads and process restarts.
    """

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        *,
        lease_seconds: Optional[float] = None,
        backoff_base: Optional[float] = None,
        backoff_cap: Optional[float] = None,
        default_max_attempts: Optional[int] = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else settings.agents_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = float(
            lease_seconds if lease_seconds is not None
            else getattr(settings, "agents_lease_seconds", 300)
        )
        self.backoff_base = float(
            backoff_base if backoff_base is not None
            else getattr(settings, "agents_backoff_base", 5)
        )
        self.backoff_cap = float(
            backoff_cap if backoff_cap is not None
            else getattr(settings, "agents_backoff_cap", 3600)
        )
        self.default_max_attempts = int(
            default_max_attempts if default_max_attempts is not None
            else getattr(settings, "agents_max_attempts", 3)
        )
        # isolation_level=None → explicit BEGIN IMMEDIATE transactions.
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_JOBS_SCHEMA)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass

    # ── Enqueue ───────────────────────────────────────────────────────────────

    def enqueue(
        self,
        kind: str,
        payload: Optional[dict] = None,
        *,
        agent_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        max_attempts: Optional[int] = None,
        delay_seconds: float = 0.0,
    ) -> int:
        """
        Add a job in the ``ready`` state. Returns its id.

        Idempotency: re-enqueuing with the same ``idempotency_key`` returns the
        existing job's id instead of creating a duplicate (dedupe of re-delivered
        events/actions). ``delay_seconds`` gates when ``claim`` will pick it up
        (the backoff gate). ``max_attempts`` caps retries before dead-letter.
        """
        kind = (kind or "").strip()[:40]
        if not kind:
            raise ValueError("A job needs a kind (e.g. 'run', 'message', 'event').")
        now = _iso()
        max_attempts = int(
            max_attempts if max_attempts is not None else self.default_max_attempts
        )
        max_attempts = max(1, min(max_attempts, 20))
        delay = max(0.0, float(delay_seconds or 0.0))
        next_at = None
        if delay > 0:
            next_at = _iso(time.time() + delay)
        with self._lock:
            if idempotency_key is not None:
                existing = self._conn.execute(
                    "SELECT id FROM agent_jobs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])
            try:
                cur = self._conn.execute(
                    "INSERT INTO agent_jobs (agent_id, kind, payload, status,"
                    " attempts, max_attempts, idempotency_key, next_attempt_at,"
                    " created_at, updated_at)"
                    " VALUES (?, ?, ?, 'ready', 0, ?, ?, ?, ?, ?)",
                    (agent_id, kind,
                     __import__("json").dumps(payload or {}, ensure_ascii=False),
                     max_attempts, idempotency_key, next_at, now, now),
                )
            except sqlite3.IntegrityError:
                # Raced with another enqueue of the same key — dedupe.
                existing = self._conn.execute(
                    "SELECT id FROM agent_jobs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])
                raise
            return int(cur.lastrowid)

    # ── Atomic claim ──────────────────────────────────────────────────────────

    def claim(self, worker_id: str, limit: int = 1, now: Optional[float] = None) -> list[dict]:
        """
        Atomically claim up to ``limit`` ready jobs for ``worker_id``.

        ``BEGIN IMMEDIATE`` … ``UPDATE … WHERE status='ready'`` inside the same
        transaction guarantees each job goes to exactly one worker. Claimed jobs
        get a lease (``lease_owner`` / ``lease_until`` / ``heartbeat_at``).
        """
        now = now if now is not None else time.time()
        limit = max(1, int(limit))
        claimed: list[dict] = []
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self._conn.execute(
                    "SELECT * FROM agent_jobs"
                    " WHERE status = 'ready' AND (next_attempt_at IS NULL"
                    "   OR next_attempt_at <= ?)"
                    " ORDER BY id ASC LIMIT ?",
                    (_iso(now), limit),
                ).fetchall()
                for row in rows:
                    self._conn.execute(
                        "UPDATE agent_jobs SET status = 'running', lease_owner = ?,"
                        " lease_until = ?, heartbeat_at = ?, updated_at = ?"
                        " WHERE id = ? AND status = 'ready'",
                        (worker_id, _iso(now + self.lease_seconds), _iso(now),
                         _iso(now), row["id"]),
                    )
                    fresh = self._conn.execute(
                        "SELECT * FROM agent_jobs WHERE id = ?", (row["id"],)
                    ).fetchone()
                    claimed.append(dict(fresh))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return claimed

    # ── Leases & heartbeats ───────────────────────────────────────────────────

    def renew(self, job_id: int, worker_id: str, now: Optional[float] = None,
              seconds: Optional[float] = None) -> bool:
        """Renew a claimed job's lease (heartbeat). False if not owned/running."""
        now = now if now is not None else time.time()
        seconds = seconds if seconds is not None else self.lease_seconds
        with self._lock:
            cur = self._conn.execute(
                "UPDATE agent_jobs SET lease_until = ?, heartbeat_at = ?,"
                " updated_at = ? WHERE id = ? AND status = 'running'"
                " AND lease_owner = ?",
                (_iso(now + seconds), _iso(now), _iso(now), job_id, worker_id),
            )
            return cur.rowcount > 0

    def finish(self, job_id: int, worker_id: str, result: Optional[str] = None) -> bool:
        """Mark a claimed job done. False if not owned/running."""
        result = (result or "")[:4000]
        with self._lock:
            cur = self._conn.execute(
                "UPDATE agent_jobs SET status = 'done', lease_owner = NULL,"
                " lease_until = NULL, heartbeat_at = NULL,"
                " last_error = NULL, updated_at = ?"
                " WHERE id = ? AND status = 'running' AND lease_owner = ?",
                (_iso(), job_id, worker_id),
            )
            if cur.rowcount:
                if result:
                    self._conn.execute(
                        "UPDATE agent_jobs SET payload = ? WHERE id = ?",
                        (result, job_id),
                    )
            return cur.rowcount > 0

    def fail(
        self,
        job_id: int,
        worker_id: str,
        error: str,
        *,
        retryable: bool = True,
        now: Optional[float] = None,
    ) -> bool:
        """
        Record a failure. Retryable failures re-enter ``ready`` after exponential
        backoff; non-retryable (or attempts exhausted) go straight to ``dead``
        (the dead-letter queue, kept for inspection/retry). False if the caller
        no longer owns a running job.
        """
        now = now if now is not None else time.time()
        error = (error or "Job failed.")[:1000]
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agent_jobs WHERE id = ? AND status = 'running'"
                " AND lease_owner = ?",
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                return False
            attempts = int(row["attempts"]) + 1
            if not retryable or attempts >= int(row["max_attempts"]):
                self._conn.execute(
                    "UPDATE agent_jobs SET status = 'dead', attempts = ?,"
                    " lease_owner = NULL, lease_until = NULL, heartbeat_at = NULL,"
                    " last_error = ?, updated_at = ? WHERE id = ?",
                    (attempts, error, _iso(), job_id),
                )
            else:
                next_at = _iso(
                    now + _backoff_seconds(attempts, self.backoff_base, self.backoff_cap)
                )
                self._conn.execute(
                    "UPDATE agent_jobs SET status = 'ready', attempts = ?,"
                    " lease_owner = NULL, lease_until = NULL, heartbeat_at = NULL,"
                    " last_error = ?, next_attempt_at = ?, updated_at = ?"
                    " WHERE id = ?",
                    (attempts, error, next_at, _iso(), job_id),
                )
            return True

    def release(self, job_id: int, worker_id: str) -> bool:
        """
        Return a claimed job to ``ready`` (no attempt counted) — used when a
        worker gracefully hands a job back. False if not owned/running.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE agent_jobs SET status = 'ready', lease_owner = NULL,"
                " lease_until = NULL, heartbeat_at = NULL, next_attempt_at = NULL,"
                " updated_at = ? WHERE id = ? AND status = 'running'"
                " AND lease_owner = ?",
                (_iso(), job_id, worker_id),
            )
            return cur.rowcount > 0

    # ── Orphan recovery (crash-resume) ────────────────────────────────────────

    def recover_orphans(self, now: Optional[float] = None) -> int:
        """
        Reclaim ``running`` jobs whose lease has expired without a heartbeat:
        re-queue them (attempts + 1, backoff) or dead-letter them when attempts
        are exhausted. Returns the number of jobs reclaimed. Call on boot and
        periodically while running.
        """
        now = now if now is not None else time.time()
        reclaimed = 0
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self._conn.execute(
                    "SELECT * FROM agent_jobs"
                    " WHERE status = 'running' AND lease_until IS NOT NULL"
                    " AND lease_until <= ?",
                    (_iso(now),),
                ).fetchall()
                for row in rows:
                    attempts = int(row["attempts"]) + 1
                    error = f"orphaned: lease expired at {row['lease_until']}"
                    if attempts >= int(row["max_attempts"]):
                        self._conn.execute(
                            "UPDATE agent_jobs SET status = 'dead', attempts = ?,"
                            " lease_owner = NULL, lease_until = NULL,"
                            " heartbeat_at = NULL, last_error = ?, updated_at = ?"
                            " WHERE id = ?",
                            (attempts, error, _iso(), row["id"]),
                        )
                    else:
                        next_at = _iso(
                            now + _backoff_seconds(attempts, self.backoff_base,
                                                   self.backoff_cap)
                        )
                        self._conn.execute(
                            "UPDATE agent_jobs SET status = 'ready', attempts = ?,"
                            " lease_owner = NULL, lease_until = NULL,"
                            " heartbeat_at = NULL, last_error = ?,"
                            " next_attempt_at = ?, updated_at = ? WHERE id = ?",
                            (attempts, error, next_at, _iso(), row["id"]),
                        )
                    reclaimed += 1
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return reclaimed

    # ── Administration / inspection ───────────────────────────────────────────

    def cancel(self, job_id: int) -> bool:
        """Cancel a ready or running job. False if already terminal."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE agent_jobs SET status = 'cancelled', updated_at = ?"
                " WHERE id = ? AND status IN ('ready', 'running')",
                (_iso(), job_id),
            )
            return cur.rowcount > 0

    def get(self, job_id: int) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agent_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def peek(self, limit: int = 50) -> list[dict[str, Any]]:
        """Recent jobs, newest first (inspection)."""
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM agent_jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM agent_jobs GROUP BY status"
            ).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}


# ── Singleton access (shared by tools / runtime / tests) ─────────────────────

_QUEUE: Optional[AgentQueue] = None


def get_queue() -> AgentQueue:
    """The shared job queue (lazily created)."""
    global _QUEUE
    if _QUEUE is None:
        _QUEUE = AgentQueue()
    return _QUEUE


def set_queue(queue: Optional[AgentQueue]) -> Optional[AgentQueue]:
    """Swap in a custom queue (used by the runtime and tests)."""
    global _QUEUE
    _QUEUE = queue
    return _QUEUE
