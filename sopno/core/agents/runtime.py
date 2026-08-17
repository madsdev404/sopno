"""
sopno/core/agents/runtime.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
AgentRuntime — the lifecycle owner for long-running background agents
(long-running-agents.md, rollout step 6).

The runtime is the piece Sopno starts at boot: it spawns the worker pool
(``agents_concurrency`` threads), starts the scheduler (schedule triggers →
``run`` jobs) and a watchdog, and owns the shared store + queue singletons. On
stop it shuts everything down cleanly.

Watchdog responsibilities (on boot and periodically):
  - ``queue.recover_orphans()`` — reclaim jobs whose lease expired (crash
    mid-job) with backoff, or dead-letter them when attempts run out.
  - reclaim sessions stuck in ``running`` with a stale heartbeat and no live
    job — a crash left them mid-flight; they go back to ``ready`` so the next
    trigger resumes them instead of leaving them stuck forever.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Optional

from sopno.config.settings import settings

from sopno.core.agents.queue import AgentQueue, get_queue
from sopno.core.agents.scheduler import AgentScheduler
from sopno.core.agents.session import AgentSessionStore, get_store
from sopno.core.agents.sources import (FileWatcher, WebhookServer,
                                       set_watcher, set_webhook)
from sopno.core.agents.worker import AgentWorker, default_reflect, set_workers


def _parse_iso(raw: Optional[str]) -> Optional[float]:
    """Parse the store's ``%Y-%m-%d %H:%M:%S`` timestamps."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


class AgentRuntime:
    """
    Starts and owns the workers, the scheduler and the watchdog for the shared
    store + queue. Safe to start once per process.
    """

    def __init__(
        self,
        store: Optional[AgentSessionStore] = None,
        queue: Optional[AgentQueue] = None,
        *,
        run_check: Optional[Callable[[], bool]] = None,
        concurrency: Optional[int] = None,
    ) -> None:
        self.store = store or get_store()
        self.queue = queue or get_queue()
        self.run_check = run_check or (lambda: True)
        self.concurrency = max(
            1, int(concurrency if concurrency is not None
                   else getattr(settings, "agents_concurrency", 2))
        )
        self._workers: list[AgentWorker] = []
        self._scheduler: Optional[AgentScheduler] = None
        self._watchdog: Optional[threading.Thread] = None
        self._watcher: Optional[FileWatcher] = None
        self._webhook: Optional[WebhookServer] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Boot the runtime: orphan recovery, workers, scheduler, watchdog."""
        with self._lock:
            if self._workers:
                return  # already running
            self._stop.clear()
            # Crash-resume on boot: reclaim any job left running by a prior
            # process before any worker can claim new work.
            try:
                self.queue.recover_orphans()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._reclaim_stale_sessions()
            except Exception:  # noqa: BLE001
                pass

            self._workers = [
                AgentWorker(self.store, self.queue,
                            worker_id=f"w{i}",
                            run_check=lambda: self._alive(),
                            reflect_fn=default_reflect)
                for i in range(self.concurrency)
            ]
            for worker in self._workers:
                worker.start()
            set_workers(self._workers)

            self._scheduler = AgentScheduler(
                self.store, self.queue,
                run_check=lambda: self._alive(),
            )
            self._scheduler.start()

            self._watchdog = threading.Thread(
                target=self._watchdog_loop, name="agent-watchdog", daemon=True
            )
            self._watchdog.start()

            # Step 7: event sources — the file watcher and the webhook receiver
            # are optional, enabled by their config values.
            self._start_sources()

    def _start_sources(self) -> None:
        try:
            if settings.agents_file_watches:
                self._watcher = FileWatcher(self.store, self.queue)
                self._watcher.start()
                set_watcher(self._watcher)
        except Exception:  # noqa: BLE001
            pass
        try:
            if int(settings.agents_webhook_port):
                self._webhook = WebhookServer(self.store, self.queue)
                self._webhook.start()
                set_webhook(self._webhook)
        except Exception:  # noqa: BLE001
            pass

    def stop(self) -> None:
        """Stop workers, scheduler and watchdog; the store stays open for tools."""
        with self._lock:
            self._stop.set()
            for worker in self._workers:
                if worker.is_alive():
                    worker.join(timeout=5)
            self._workers = []
            set_workers([])
            if self._scheduler is not None:
                self._scheduler = None
            if self._watchdog is not None:
                wd = self._watchdog
                self._watchdog = None
                if wd.is_alive():
                    wd.join(timeout=5)
            if self._watcher is not None:
                self._watcher.stop()
                self._watcher = None
                set_watcher(None)
            if self._webhook is not None:
                self._webhook.stop()
                self._webhook = None
                set_webhook(None)

    def _alive(self) -> bool:
        return not self._stop.is_set() and self.run_check()

    # ── Watchdog ──────────────────────────────────────────────────────────────

    def _watchdog_loop(self) -> None:
        interval = max(5.0, float(getattr(settings, "agents_watchdog_seconds", 60)))
        while self._alive():
            time.sleep(interval)
            try:
                self.queue.recover_orphans()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._reclaim_stale_sessions()
            except Exception:  # noqa: BLE001
                pass

    def _reclaim_stale_sessions(self) -> int:
        """
        Sessions stuck in ``running`` with a heartbeat older than the lease
        window — and no live job driving them — are reclaimed to ``ready`` so a
        future trigger resumes them. Returns the number reclaimed.
        """
        lease = max(10.0, float(getattr(settings, "agents_lease_seconds", 300)))
        live_jobs: set[int] = set()
        for job in self.queue.peek(limit=500):
            if job.get("status") == "running":
                agent_id = job.get("agent_id")
                if agent_id is not None:
                    live_jobs.add(int(agent_id))
        reclaimed = 0
        now = time.time()
        for agent in self.store.list():
            if agent.get("state") != "running" or agent.get("id") in live_jobs:
                continue
            updated = _parse_iso(agent.get("updated_at"))
            if updated is None:
                continue
            if now - updated > lease:
                try:
                    self.store.transition(agent["id"], "ready")
                    self.store.log_action(
                        agent["id"], "error",
                        "stale running session reclaimed by watchdog",
                    )
                    reclaimed += 1
                except Exception:  # noqa: BLE001
                    pass
        return reclaimed


# ── Singleton access (shared by the assistant runtime / tests) ───────────────

_RUNTIME: Optional[AgentRuntime] = None


def get_runtime() -> AgentRuntime:
    """The shared runtime instance (lazily created)."""
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = AgentRuntime()
    return _RUNTIME


def set_runtime(runtime: Optional[AgentRuntime]) -> Optional[AgentRuntime]:
    """Swap in a custom runtime (used by the assistant and tests)."""
    global _RUNTIME
    _RUNTIME = runtime
    return _RUNTIME
