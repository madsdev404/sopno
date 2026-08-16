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
  - ``scheduler.py`` / ``events.py`` / ``worker.py`` / ``runtime.py`` —
    planned in later rollout steps.
"""

from sopno.core.agents.session import AgentSessionStore  # noqa: F401
from sopno.core.agents.queue import AgentQueue  # noqa: F401
