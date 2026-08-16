"""
sopno/core/agents
━━━━━━━━━━━━━━━━
Durable execution machinery for long-running background agents
(doc/roadmap/long-running-agents.md).

The package hosts the pieces that let an agent keep making progress across
many context windows and process restarts:

  - ``session.py`` — ``AgentSessionStore``: the durable per-agent state
    machine (name, goal, state, plan, working memory, alignment, budget) with
    an append-only action log for auditing.
  - ``queue.py``    — ``AgentQueue``: a SQLite job queue with atomic claims,
    leases + heartbeats, retries with backoff, a dead-letter state, and
    idempotency keys.
  - ``scheduler.py`` — ``AgentScheduler``: cron / interval / ETA triggers that
    fire a session's schedule into a ``run`` job on the queue.
  - ``events.py``   — ``AgentEvents``: the wake channel — a message plus an
    atomic ``state_delta`` become pending input + a ``resume`` job.
  - ``worker.py``   — ``AgentWorker``: claims ``run``/``resume`` jobs and drives
    the ORIENT → DECIDE → ACT → OBSERVE loop (checkpointing after every step,
    parking on approval gates, enforcing budgets and tool allowlists).
  - ``runtime.py``  — ``AgentRuntime``: lifecycle owner — workers, scheduler,
    watchdog, and orphan recovery on boot.
"""

from sopno.core.agents.session import AgentSessionStore  # noqa: F401
from sopno.core.agents.queue import AgentQueue  # noqa: F401
from sopno.core.agents.scheduler import (  # noqa: F401
    AgentScheduler,
    parse_schedule,
    next_fire_at,
    get_scheduler,
    set_scheduler,
)
from sopno.core.agents.events import AgentEvents, get_events, set_events  # noqa: F401


def __getattr__(name):
    # ``AgentWorker`` / ``AgentRuntime`` are imported lazily: they pull in the
    # tools registry + coding harness, which in turn import this package —
    # eager imports here would deadlock the import system.
    if name in ("AgentWorker", "get_workers", "set_workers"):
        from sopno.core.agents.worker import (  # noqa: PLC0415
            AgentWorker, get_workers, set_workers)
        return {"AgentWorker": AgentWorker, "get_workers": get_workers,
                "set_workers": set_workers}[name]
    if name in ("AgentRuntime", "get_runtime", "set_runtime"):
        from sopno.core.agents.runtime import (  # noqa: PLC0415
            AgentRuntime, get_runtime, set_runtime)
        return {"AgentRuntime": AgentRuntime, "get_runtime": get_runtime,
                "set_runtime": set_runtime}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
