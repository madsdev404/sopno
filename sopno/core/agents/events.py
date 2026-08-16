"""
sopno/core/agents/events.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Event sources for long-running agents (long-running-agents.md, rollout step 3).

Sessions that are parked — ``waiting_human``, ``blocked``, or just dormant
``ready`` — resume on *events*, not polling: a human reply, a webhook, a file
change, a schedule tick, or a manual ``agent_send``. This module turns such an
event into the durable wake: it checkpoints any ``state_delta`` (atomic, so a
crash can't leave a half-applied event), queues the input message on the
session's pending-input pile, and enqueues a ``resume`` job the future worker
claims. The event channel never talks to the LLM — it only makes the state
resumable.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from sopno.core.agents.queue import AgentQueue, get_queue
from sopno.core.agents.session import AgentSessionStore, get_store


class AgentEvents:
    """Wakes parked sessions with a message and an optional state delta."""

    def __init__(
        self,
        store: Optional[AgentSessionStore] = None,
        queue: Optional[AgentQueue] = None,
    ) -> None:
        self._store = store or get_store()
        self._queue = queue or get_queue()
        self._lock = threading.RLock()

    def wake(
        self,
        agent_id: int,
        message: str,
        state_delta: Optional[dict] = None,
        source: str = "message",
    ) -> dict[str, Any]:
        """
        Deliver an event to a session:

        1. checkpoints ``state_delta`` (validated by the store),
        2. queues ``message`` on the session's pending input,
        3. enqueues a ``resume`` job for the worker to claim.

        Returns ``{"agent_id", "pending", "job_id", "state"}``. Raises
        ValueError if the session doesn't exist.
        """
        agent = self._store.get(agent_id)
        if agent is None:
            raise ValueError(f"No agent session with id {agent_id}.")
        source = (source or "message").strip()[:20] or "message"
        message = (message or "").strip()
        with self._lock:
            if state_delta:
                self._store.apply_state_delta(agent_id, state_delta)
            pending = self._store.enqueue_input(agent_id, message) \
                if message else len(agent.get("pending_input") or [])
            job_id = self._queue.enqueue(
                "resume",
                {"agent_id": agent_id, "source": source},
                agent_id=agent_id,
                idempotency_key=f"resume-{agent_id}-{time.time():.6f}",
            )
            self._store.log_action(
                agent_id, "event", f"{source}: {message[:200]}" if message else source
            )
        return {
            "agent_id": agent_id,
            "pending": pending,
            "job_id": job_id,
            "state": self._store.get(agent_id),
        }


# ── Singleton access (shared by tools / runtime / tests) ─────────────────────

_EVENTS: Optional[AgentEvents] = None


def get_events() -> AgentEvents:
    """The shared event channel (lazily created)."""
    global _EVENTS
    if _EVENTS is None:
        _EVENTS = AgentEvents()
    return _EVENTS


def set_events(events: Optional[AgentEvents]) -> Optional[AgentEvents]:
    """Swap in a custom channel (used by the runtime and tests)."""
    global _EVENTS
    _EVENTS = events
    return _EVENTS
