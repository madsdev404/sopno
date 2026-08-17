"""
tests/core/test_agent_runtime.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the runtime lifecycle owner (sopno/core/agents/runtime.py):
orphan recovery on boot, the watchdog reclaim of stale running sessions, and a
clean start/stop of workers + scheduler.
"""

import tempfile
import time
import unittest
from datetime import datetime

from sopno.core.agents.queue import AgentQueue
from sopno.core.agents.runtime import AgentRuntime
from sopno.core.agents.session import AgentSessionStore


def _temp_db() -> str:
    return tempfile.mkstemp(suffix=".db")[1]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _backdate_updated(store: AgentSessionStore, agent_id: int, ts: float) -> None:
    store._conn.execute(
        "UPDATE agents SET updated_at = ? WHERE id = ?", (_iso(ts), agent_id)
    )
    store._conn.commit()


class RuntimeSetup(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AgentSessionStore(_temp_db())
        self.queue = AgentQueue(_temp_db())

    def tearDown(self) -> None:
        self.store.close()
        self.queue.close()

    def _runtime(self, **kwargs) -> AgentRuntime:
        return AgentRuntime(self.store, self.queue, run_check=lambda: True,
                            **kwargs)

    def _park_running(self, name: str) -> int:
        agent_id = self.store.create(name, "Goal")
        self.store.transition(agent_id, "ready")
        self.store.transition(agent_id, "running")
        return agent_id


class ReclaimTest(RuntimeSetup):
    def test_stale_running_session_reclaimed_to_ready(self) -> None:
        agent_id = self._park_running("stale")
        _backdate_updated(self.store, agent_id, time.time() - 3600)
        runtime = self._runtime()
        reclaimed = runtime._reclaim_stale_sessions()
        self.assertEqual(reclaimed, 1)
        agent = self.store.get(agent_id)
        self.assertEqual(agent["state"], "ready")
        log = "\n".join(e["detail"] for e in self.store.action_log(agent_id))
        self.assertIn("stale running session", log)

    def test_fresh_session_is_not_reclaimed(self) -> None:
        agent_id = self._park_running("fresh")
        runtime = self._runtime()
        self.assertEqual(runtime._reclaim_stale_sessions(), 0)
        self.assertEqual(self.store.get(agent_id)["state"], "running")

    def test_live_job_protects_running_session(self) -> None:
        agent_id = self._park_running("busy")
        job_id = self.queue.enqueue(
            "run", {"agent_id": agent_id}, agent_id=agent_id,
            idempotency_key=f"r-{agent_id}",
        )
        self.assertEqual(len(self.queue.claim("w1", limit=1)), 1)
        _backdate_updated(self.store, agent_id, time.time() - 3600)
        runtime = self._runtime()
        self.assertEqual(runtime._reclaim_stale_sessions(), 0)
        self.assertEqual(self.store.get(agent_id)["state"], "running")
        self.assertIsNotNone(self.queue.get(job_id))

    def test_only_running_sessions_are_candidates(self) -> None:
        ready_id = self.store.create("r", "Goal")
        self.store.transition(ready_id, "ready")
        _backdate_updated(self.store, ready_id, time.time() - 3600)
        runtime = self._runtime()
        self.assertEqual(runtime._reclaim_stale_sessions(), 0)
        self.assertEqual(self.store.get(ready_id)["state"], "ready")


class BootRecoveryTest(RuntimeSetup):
    def test_orphaned_jobs_recovered_on_start(self) -> None:
        # A job left 'running' by a dead process gets reclaimed by the boot
        # orphan recovery (its lease expired long ago).
        agent_id = self.store.create("orphan", "Goal")
        job_id = self.queue.enqueue(
            "run", {"agent_id": agent_id}, agent_id=agent_id,
            idempotency_key="orphan-1",
        )
        self.queue.claim("dead-worker", limit=1)
        # Simulate an expired lease: backdate the lease_until.
        self.queue._conn.execute(
            "UPDATE agent_jobs SET lease_until = ? WHERE id = ?",
            (_iso(time.time() - 1000), job_id),
        )
        self.queue._conn.commit()
        runtime = self._runtime(concurrency=1)
        runtime.start()
        self.assertEqual(self.queue.get(job_id)["status"], "ready")
        runtime.stop()
        self.assertEqual(self.queue.get(job_id)["status"], "ready")

    def test_start_stop_is_idempotent_and_clean(self) -> None:
        runtime = self._runtime(concurrency=2)
        runtime.start()
        runtime.start()  # no-op while already running
        runtime.stop()
        runtime.stop()  # no-op once stopped
        self.assertEqual(runtime._workers, [])


class EventSourcesTest(RuntimeSetup):
    def test_runtime_starts_and_stops_configured_sources(self) -> None:
        import socket

        import tempfile
        from pathlib import Path

        from sopno.config.settings import settings
        from sopno.core.agents.sources import get_watcher, get_webhook

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        watch_dir = Path(tempfile.mkdtemp())
        old_watches = settings.agents_file_watches
        old_host = settings.agents_webhook_host
        old_port = settings.agents_webhook_port
        settings.agents_file_watches = [{"path": str(watch_dir), "agent": 1}]
        settings.agents_webhook_host = "127.0.0.1"
        settings.agents_webhook_port = port
        try:
            runtime = self._runtime(concurrency=1)
            runtime.start()
            self.assertIsNotNone(runtime._watcher)
            self.assertIsNotNone(runtime._webhook)
            self.assertEqual(get_watcher(), runtime._watcher)
            self.assertEqual(get_webhook(), runtime._webhook)
            runtime.stop()
            self.assertIsNone(runtime._watcher)
            self.assertIsNone(runtime._webhook)
            self.assertIsNone(get_watcher())
            self.assertIsNone(get_webhook())
        finally:
            settings.agents_file_watches = old_watches
            settings.agents_webhook_host = old_host
            settings.agents_webhook_port = old_port

    def test_runtime_without_sources_starts_none(self) -> None:
        from sopno.config.settings import settings
        from sopno.core.agents.sources import get_watcher, get_webhook

        old_watches = settings.agents_file_watches
        old_port = settings.agents_webhook_port
        settings.agents_file_watches = []
        settings.agents_webhook_port = 0
        try:
            runtime = self._runtime(concurrency=1)
            runtime.start()
            self.assertIsNone(runtime._watcher)
            self.assertIsNone(runtime._webhook)
            runtime.stop()
        finally:
            settings.agents_file_watches = old_watches
            settings.agents_webhook_port = old_port


class WatchdogTest(RuntimeSetup):
    def test_watchdog_thread_starts_and_runs(self) -> None:
        from sopno.config.settings import settings
        runtime = self._runtime(concurrency=1)
        old_interval = getattr(settings, "agents_watchdog_seconds", 60)
        settings.agents_watchdog_seconds = 0.1
        try:
            runtime.start()
            self.assertIsNotNone(runtime._watchdog)
            self.assertTrue(runtime._watchdog.is_alive())
            runtime.stop()
            self.assertIsNone(runtime._watchdog)
        finally:
            settings.agents_watchdog_seconds = old_interval

    def test_watchdog_reclaims_stale_sessions_on_tick(self) -> None:
        from sopno.config.settings import settings
        agent_id = self._park_running("watchdog-stale")
        _backdate_updated(self.store, agent_id, time.time() - 3600)
        runtime = self._runtime(concurrency=1)
        old_interval = getattr(settings, "agents_watchdog_seconds", 60)
        settings.agents_watchdog_seconds = 0.05
        try:
            runtime.start()
            # Give the watchdog a moment to fire at least once.
            time.sleep(0.3)
            agent = self.store.get(agent_id)
            self.assertEqual(agent["state"], "ready")
        finally:
            settings.agents_watchdog_seconds = old_interval
            runtime.stop()

    def test_runtime_starts_workers_and_scheduler(self) -> None:
        from sopno.config.settings import settings
        runtime = self._runtime(concurrency=2)
        old_interval = getattr(settings, "agents_watchdog_seconds", 60)
        settings.agents_watchdog_seconds = 60
        try:
            runtime.start()
            self.assertEqual(len(runtime._workers), 2)
            self.assertTrue(all(w.is_alive() for w in runtime._workers))
            self.assertIsNotNone(runtime._watchdog)
            self.assertTrue(runtime._watchdog.is_alive())
            self.assertIsNotNone(runtime._scheduler)
            runtime.stop()
            self.assertEqual(runtime._workers, [])
        finally:
            settings.agents_watchdog_seconds = old_interval


if __name__ == "__main__":
    unittest.main()
