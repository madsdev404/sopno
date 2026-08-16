"""
tests/core/test_agent_scheduler.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the agent scheduler + event sources
(sopno/core/agents/scheduler.py, sopno/core/agents/events.py):
cron / interval / ETA trigger parsing and next-fire computation, the scheduler
tick (fire → run job, last-fired bookkeeping, idempotency), and the event wake
channel (message + atomic state_delta → pending input + resume job).
"""

import sqlite3
import tempfile
import time
import unittest
from datetime import datetime

from sopno.core.agents.events import AgentEvents
from sopno.core.agents.queue import AgentQueue
from sopno.core.agents.scheduler import (
    AgentScheduler,
    next_fire_at,
    parse_schedule,
)
from sopno.core.agents.session import AgentSessionStore


def _temp_db() -> str:
    return tempfile.mkstemp(suffix=".db")[1]


def _ts(*args) -> float:
    """Local-time timestamp helper: _ts(2026, 8, 16, 10, 3) → 10:03."""
    return datetime(*args).timestamp()


def _backdate(store: AgentSessionStore, agent_id: int, ts: float) -> None:
    """Pin a session's created_at so anchors are deterministic in tests."""
    store._conn.execute(
        "UPDATE agents SET created_at = ? WHERE id = ?",
        (datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"), agent_id),
    )
    store._conn.commit()


# ── Schedule parsing ─────────────────────────────────────────────────────────


class ParseScheduleTest(unittest.TestCase):
    def test_interval(self) -> None:
        spec = parse_schedule("interval:3600")
        self.assertEqual(spec, {"type": "interval", "seconds": 3600})

    def test_interval_rejects_non_positive(self) -> None:
        for bad in ("interval:0", "interval:-5", "interval:abc"):
            with self.assertRaises(ValueError):
                parse_schedule(bad)

    def test_cron_wildcards(self) -> None:
        spec = parse_schedule("cron:* * * * *")
        self.assertEqual(spec["type"], "cron")
        self.assertIsNone(spec["min"])
        self.assertIsNone(spec["dow"])

    def test_cron_steps_ranges_names(self) -> None:
        spec = parse_schedule("cron:*/15 9-17 1,15 * mon-fri")
        self.assertEqual(spec["min"], [0, 15, 30, 45])
        self.assertEqual(spec["hour"], list(range(9, 18)))
        self.assertEqual(spec["dom"], [1, 15])
        self.assertIsNone(spec["month"])
        self.assertEqual(spec["dow"], [1, 2, 3, 4, 5])

    def test_cron_rejects_malformed(self) -> None:
        for bad in (
            "cron:* * * *",
            "cron:* * * * * *",
            "cron:* 24 * * *",
            "cron:a * * * *",
            "cron:60 * * * *",
        ):
            with self.assertRaises(ValueError):
                parse_schedule(bad)

    def test_eta(self) -> None:
        spec = parse_schedule("eta:2026-08-20 14:30:00")
        self.assertEqual(spec["type"], "eta")
        self.assertEqual(spec["at"], _ts(2026, 8, 20, 14, 30))

    def test_unknown_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_schedule("bogus:1")


# ── Next-fire computation ────────────────────────────────────────────────────


class NextFireTest(unittest.TestCase):
    def test_interval(self) -> None:
        spec = parse_schedule("interval:60")
        self.assertEqual(next_fire_at(spec, 1000.0), 1060.0)

    def test_eta_future_and_past(self) -> None:
        spec = parse_schedule("eta:2026-08-20 14:30:00")
        self.assertEqual(next_fire_at(spec, _ts(2026, 8, 20, 14, 0)), _ts(2026, 8, 20, 14, 30))
        self.assertIsNone(next_fire_at(spec, _ts(2026, 8, 20, 14, 31)))

    def test_cron_every_minute(self) -> None:
        spec = parse_schedule("cron:* * * * *")
        nxt = next_fire_at(spec, _ts(2026, 8, 16, 10, 3, 45))
        self.assertEqual(nxt, _ts(2026, 8, 16, 10, 4))

    def test_cron_daily_9am_rolls_to_tomorrow(self) -> None:
        spec = parse_schedule("cron:0 9 * * *")
        after_morning = next_fire_at(spec, _ts(2026, 8, 16, 10, 3))
        self.assertEqual(after_morning, _ts(2026, 8, 17, 9, 0))
        before_9am = next_fire_at(spec, _ts(2026, 8, 16, 8, 59))
        self.assertEqual(before_9am, _ts(2026, 8, 16, 9, 0))

    def test_cron_weekday_midnight(self) -> None:
        # Aug 16 2026 is a Sunday; next Monday midnight is Aug 17.
        spec = parse_schedule("cron:0 0 * * mon")
        nxt = next_fire_at(spec, _ts(2026, 8, 16, 23, 30))
        self.assertEqual(nxt, _ts(2026, 8, 17, 0, 0))

    def test_cron_first_of_month(self) -> None:
        spec = parse_schedule("cron:30 14 1 * *")
        nxt = next_fire_at(spec, _ts(2026, 8, 16))
        self.assertEqual(nxt, _ts(2026, 9, 1, 14, 30))

    def test_cron_dom_or_dow(self) -> None:
        # Fires on the 13th OR any Friday. Aug 2026: the 13th is a Thursday;
        # the first Friday after Aug 1 is Aug 7 → that wins.
        spec = parse_schedule("cron:0 12 13 * fri")
        nxt = next_fire_at(spec, _ts(2026, 8, 1))
        self.assertEqual(nxt, _ts(2026, 8, 7, 12, 0))


# ── Scheduler tick ───────────────────────────────────────────────────────────


class SchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AgentSessionStore(_temp_db())
        self.queue = AgentQueue(_temp_db())

    def tearDown(self) -> None:
        self.store.close()
        self.queue.close()

    def test_interval_fires_and_does_not_duplicate(self) -> None:
        scheduler = AgentScheduler(store=self.store, queue=self.queue)
        agent_id = self.store.create(
            "nightly", "Do the thing", schedule="interval:3600"
        )
        fired = scheduler.tick(now=time.time() + 3601)
        self.assertEqual(len(fired), 1)
        job = self.queue.get(fired[0]["job_id"])
        self.assertEqual(job["kind"], "run")
        self.assertEqual(job["status"], "ready")
        agent = self.store.get(agent_id)
        self.assertIsNotNone(agent["last_fired_at"])
        # A second tick within the interval must not fire again.
        self.assertEqual(scheduler.tick(now=time.time() + 3700), [])
        # Once the interval elapses, the next cadence fires a new job.
        fired2 = scheduler.tick(now=time.time() + 7300)
        self.assertEqual(len(fired2), 1)
        self.assertNotEqual(fired2[0]["job_id"], job["id"])

    def test_interval_anchored_on_creation(self) -> None:
        scheduler = AgentScheduler(store=self.store, queue=self.queue)
        created_before = _ts(2026, 8, 16, 0, 0)
        agent_id = self.store.create("worker", "Goal", schedule="interval:60")
        _backdate(self.store, agent_id, created_before)
        # 61s after creation the trigger is due.
        fired = scheduler.tick(now=created_before + 61)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["agent"]["id"], agent_id)

    def test_cron_due_and_undue(self) -> None:
        scheduler = AgentScheduler(store=self.store, queue=self.queue)
        agent_id = self.store.create("digest", "Digest", schedule="cron:0 9 * * *")
        _backdate(self.store, agent_id, _ts(2026, 8, 16, 0, 0))
        # First tick at 09:30 catches up the missed 09:00 fire today.
        fired = scheduler.tick(now=_ts(2026, 8, 16, 9, 30))
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["agent"]["id"], agent_id)
        # Same day, just after the catch-up: next is tomorrow 09:00 → nothing.
        self.assertEqual(scheduler.tick(now=_ts(2026, 8, 16, 9, 45)), [])
        # Next day 10:00 — due again.
        fired2 = scheduler.tick(now=_ts(2026, 8, 17, 10, 0))
        self.assertEqual(len(fired2), 1)
        self.assertNotEqual(fired2[0]["job_id"], fired[0]["job_id"])

    def test_eta_is_one_shot_and_clears_schedule(self) -> None:
        scheduler = AgentScheduler(store=self.store, queue=self.queue)
        agent_id = self.store.create(
            "onetime", "One thing", schedule="eta:2026-08-20 14:30:00"
        )
        _backdate(self.store, agent_id, _ts(2026, 8, 16, 0, 0))
        self.assertEqual(scheduler.tick(now=_ts(2026, 8, 20, 14, 0)), [])
        fired = scheduler.tick(now=_ts(2026, 8, 20, 14, 31))
        self.assertEqual(len(fired), 1)
        agent = self.store.get(agent_id)
        self.assertIsNone(agent["schedule"])
        self.assertEqual(scheduler.tick(now=_ts(2026, 8, 20, 15, 0)), [])

    def test_malformed_schedule_is_skipped(self) -> None:
        scheduler = AgentScheduler(store=self.store, queue=self.queue)
        self.store.create("broken", "Goal", schedule="not:a-spec")
        self.assertEqual(scheduler.tick(now=time.time()), [])

    def test_fire_callback_receives_agent_and_job(self) -> None:
        seen: list = []
        scheduler = AgentScheduler(
            store=self.store,
            queue=self.queue,
            fire_callback=lambda agent, job_id: seen.append((agent["id"], job_id)),
        )
        agent_id = self.store.create("cb", "Goal", schedule="interval:1")
        scheduler.tick(now=time.time() + 1)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], agent_id)
        self.assertEqual(self.queue.get(seen[0][1])["kind"], "run")

    def test_terminal_and_paused_sessions_are_skipped(self) -> None:
        scheduler = AgentScheduler(store=self.store, queue=self.queue)
        done_id = self.store.create("done", "Goal", schedule="interval:1")
        dead_id = self.store.create("dead", "Goal", schedule="interval:1")
        paused_id = self.store.create("paused", "Goal", schedule="interval:1")
        for agent_id in (done_id, dead_id):
            self.store.transition(agent_id, "ready")
            self.store.transition(agent_id, "running")
        self.store.transition(done_id, "done")
        self.store.transition(dead_id, "dead")
        self.store.set_status(paused_id, "paused")
        # All three have a due interval schedule but none may fire.
        self.assertEqual(scheduler.tick(now=time.time() + 2), [])
        self.assertEqual(self.queue.peek(), [])


# ── Event sources ────────────────────────────────────────────────────────────


class EventsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AgentSessionStore(_temp_db())
        self.queue = AgentQueue(_temp_db())
        self.events = AgentEvents(store=self.store, queue=self.queue)

    def tearDown(self) -> None:
        self.store.close()
        self.queue.close()

    def _park(self) -> int:
        agent_id = self.store.create("parked", "Wait for input")
        self.store.transition(agent_id, "ready")
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "waiting_human")
        return agent_id

    def test_wake_queues_input_and_resume_job(self) -> None:
        agent_id = self._park()
        result = self.events.wake(agent_id, "yes, go ahead", source="human")
        self.assertEqual(result["pending"], 1)
        job = self.queue.get(result["job_id"])
        self.assertEqual(job["kind"], "resume")
        self.assertEqual(job["agent_id"], agent_id)
        agent = self.store.get(agent_id)
        self.assertEqual(agent["pending_input"][0]["text"], "yes, go ahead")
        kinds = [entry["kind"] for entry in self.store.action_log(agent_id)]
        self.assertIn("event", kinds)

    def test_wake_applies_state_delta(self) -> None:
        agent_id = self._park()
        self.events.wake(
            agent_id,
            "resume",
            state_delta={"plan": ["step 1", "step 2"], "status": "resuming"},
        )
        agent = self.store.get(agent_id)
        self.assertEqual(agent["plan"], ["step 1", "step 2"])
        self.assertEqual(agent["status"], "resuming")

    def test_wake_rejects_bad_delta_field(self) -> None:
        agent_id = self._park()
        with self.assertRaises(ValueError):
            self.events.wake(agent_id, "hi", state_delta={"nonsense": 1})

    def test_wake_unknown_agent(self) -> None:
        with self.assertRaises(ValueError):
            self.events.wake(9999, "hi")

    def test_wake_after_terminal_state_is_durable_not_poisoned(self) -> None:
        # A wake on a done session must not raise; the resume job is queued and
        # the worker decides what to do with a terminal session.
        agent_id = self.store.create("finished", "Done work")
        self.store.transition(agent_id, "ready")
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "done")
        result = self.events.wake(agent_id, "revive?")
        self.assertEqual(self.queue.get(result["job_id"])["kind"], "resume")


# ── Schema migration (scheduler added last_fired_at) ─────────────────────────


class MigrationTest(unittest.TestCase):
    def test_old_db_gains_last_fired_at(self) -> None:
        db = _temp_db()
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                goal TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'created',
                status TEXT NOT NULL DEFAULT 'idle',
                plan TEXT NOT NULL DEFAULT '[]',
                working_memory TEXT NOT NULL DEFAULT '[]',
                alignment TEXT NOT NULL DEFAULT '[]',
                pending_input TEXT NOT NULL DEFAULT '[]',
                tools TEXT NOT NULL DEFAULT '[]',
                schedule TEXT,
                budget TEXT NOT NULL DEFAULT '{}',
                budget_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()
        store = AgentSessionStore(db)
        agent_id = store.create("legacy", "Goal", schedule="interval:10")
        store.set_last_fired(agent_id, 123.0)
        expected = datetime.fromtimestamp(123.0).strftime("%Y-%m-%d %H:%M:%S")
        self.assertEqual(store.get(agent_id)["last_fired_at"], expected)
        store.close()

    def test_old_db_gains_kind_and_pending_action(self) -> None:
        db = _temp_db()
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                goal TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'created',
                status TEXT NOT NULL DEFAULT 'idle',
                plan TEXT NOT NULL DEFAULT '[]',
                working_memory TEXT NOT NULL DEFAULT '[]',
                alignment TEXT NOT NULL DEFAULT '[]',
                pending_input TEXT NOT NULL DEFAULT '[]',
                tools TEXT NOT NULL DEFAULT '[]',
                schedule TEXT,
                budget TEXT NOT NULL DEFAULT '{}',
                budget_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()
        store = AgentSessionStore(db)
        agent_id = store.create("legacy2", "Goal", kind="coding")
        store.set_pending_action(agent_id, {"id": "abc", "description": "X"})
        agent = store.get(agent_id)
        self.assertEqual(agent["kind"], "coding")
        self.assertEqual(agent["pending_action"]["id"], "abc")
        store.close()


if __name__ == "__main__":
    unittest.main()
