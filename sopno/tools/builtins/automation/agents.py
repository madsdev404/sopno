"""
sopno/tools/builtins/automation/agents.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Long-running background agent tools — create, manage, talk to, and inspect
durable agent sessions (sopno/core/agents). These are the user's handle on the
machinery: define an agent with a goal (+ optional schedule / tool allowlist /
budget / task type), watch it work, feed it decisions when it parks on an
approval, and pause or kill it.

Safety:
  - ``agent_create`` is non-destructive (defining an agent acts nothing yet).
  - ``agent_kill`` is destructive → the pending-action Yes/No gate.
  - ``agent_send`` wakes a parked session with a message (human approval).
  - Every mutating capability is gated behind the shared ``agents_enabled``
    switch; sessions carry a least-authority tool allowlist.
"""

from __future__ import annotations

import time
from typing import Optional

from sopno.config.settings import settings
from sopno.core.agents.events import get_events, set_events as _set_events
from sopno.core.agents.queue import get_queue
from sopno.core.agents.scheduler import parse_schedule
from sopno.core.agents.session import get_store, set_store as _set_store

_ALLOWED_KINDS = ("general", "coding")
_ALLOWED_BUDGET_KEYS = ("max_turns", "max_wall_minutes", "max_actions_per_day")
_MAX_LOG = 100


def _store():
    store = get_store()
    if store is None:
        store = _set_store_impl()
    return store


def _set_store_impl():
    from sopno.core.agents.session import AgentSessionStore

    store = AgentSessionStore()
    _set_store(store)
    return store


def _events():
    events = get_events()
    if events is None:
        from sopno.core.agents.events import AgentEvents

        events = AgentEvents()
        _set_events(events)
    return events


def _enabled() -> bool:
    return bool(getattr(settings, "agents_enabled", True))


def _find(name: str) -> Optional[dict]:
    return _store().get_by_name((name or "").strip())


def _format_agent(agent: dict) -> str:
    budget = agent.get("budget") or {}
    budget_txt = ", ".join(f"{k}={v}" for k, v in budget.items()) or "default"
    schedule = agent.get("schedule") or "none"
    pending = len(agent.get("pending_input") or [])
    return (
        f"#{agent['id']} {agent['name']} [{agent.get('kind', 'general')}]\n"
        f"  state: {agent['state']} (status: {agent['status']})\n"
        f"  goal: {agent['goal']}\n"
        f"  schedule: {schedule}\n"
        f"  budget: {budget_txt} (used {agent['budget_used']} turns)\n"
        f"  tools: {', '.join(agent.get('tools') or []) or 'all (default)'}\n"
        f"  pending input: {pending}"
    )


def agent_create(
    name: str,
    goal: str,
    schedule: Optional[str] = None,
    tools: Optional[list] = None,
    budget: Optional[dict] = None,
    task_type: str = "general",
) -> str:
    """
    Create a durable background agent with a goal it keeps making progress on.

    Args:
        name: Unique agent name (its identity across runs and restarts).
        goal: The objective, written down so a fresh context window can resume it.
        schedule: Optional trigger — 'interval:<seconds>', 'cron:<5 fields>'
            (min hour dom month dow, '*'/'*/n'/'a-b'/'a,b,c', 3-letter month/day
            names), or a one-shot 'eta:YYYY-MM-DD HH:MM:SS'.
        tools: Optional tool allowlist (least authority); empty = all safe tools.
        budget: Optional ceilings dict — max_turns, max_wall_minutes,
            max_actions_per_day.
        task_type: 'general' (LLM loop) or 'coding' (CodingAgent in a worktree).

    Returns:
        Confirmation with the new agent id, or a validation reason.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    name = (name or "").strip()
    goal = (goal or "").strip()
    task_type = (task_type or "general").strip().lower()
    if task_type not in _ALLOWED_KINDS:
        return f"task_type must be one of {', '.join(_ALLOWED_KINDS)}."
    if schedule:
        try:
            parse_schedule(schedule)
        except ValueError as e:
            return f"Bad schedule: {e}"
    if tools:
        from sopno.tools.registry import get_registered_names  # noqa: PLC0415
        known = set(get_registered_names())
        unknown = [t for t in tools if t not in known]
        if unknown:
            return f"Unknown tools: {', '.join(map(str, unknown))}."
    if budget:
        bad = [k for k in budget if k not in _ALLOWED_BUDGET_KEYS]
        if bad:
            return f"Unknown budget keys: {', '.join(map(str, bad))}."
        for key, value in budget.items():
            if not isinstance(value, int) or value < 0:
                return f"Budget '{key}' must be a non-negative integer."
    try:
        agent_id = _store().create(
            name, goal, schedule=schedule, tools=list(tools) if tools else None,
            budget=dict(budget) if budget else None, kind=task_type,
        )
    except ValueError as e:
        return str(e)
    _store().transition(agent_id, "ready")
    return (
        f"Agent '{name}' created (id {agent_id}) and ready. "
        "It runs as a background session — use agent_status to watch it and "
        "agent_send to talk to it."
    )


def agent_list() -> str:
    """
    List all background agents with their state and schedule.

    Returns:
        One entry per agent, or a reason none exist.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agents = _store().list()
    if not agents:
        return "No background agents yet. Try agent_create."
    return "Agents:\n" + "\n\n".join(_format_agent(a) for a in agents)


def agent_status(name: str) -> str:
    """
    Show a background agent's state, goal, budget usage, and recent activity.

    Args:
        name: The agent's name.

    Returns:
        The agent's status, or a reason it doesn't exist.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agent = _find(name)
    if agent is None:
        return f"No agent named '{name}'."
    lines = [_format_agent(agent), "", "Recent activity (newest first):"]
    log = _store().action_log(agent["id"], limit=8)
    if not log:
        lines.append("- (nothing yet)")
    for entry in log:
        lines.append(f"- {entry['created_at']} {entry['kind']}: "
                     f"{entry['detail'][:200]}")
    return "\n".join(lines)


def agent_send(name: str, message: str) -> str:
    """
    Send a message to a background agent (wakes it from waiting_human /
    dormant). A parked approval is answered: 'yes' approves, anything else
    declines.

    Args:
        name: The agent's name.
        message: What to tell it — e.g. 'yes, go ahead'.

    Returns:
        Confirmation that the agent was woken, or a reason it can't be.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agent = _find(name)
    if agent is None:
        return f"No agent named '{name}'."
    if agent["state"] in ("done", "dead"):
        return f"Agent '{name}' is already {agent['state']}."
    message = (message or "").strip()
    if not message:
        return "Give the agent a message."
    result = _events().wake(agent["id"], message, source="human")
    return (
        f"Message queued for '{name}' (job {result['job_id']}). "
        f"It will resume on the next worker tick."
    )


def agent_pause(name: str) -> str:
    """
    Pause a background agent: it stops being scheduled / resumed until
    agent_resume. Already-queued jobs are cancelled.

    Args:
        name: The agent's name.

    Returns:
        Confirmation, or a reason it doesn't exist.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agent = _find(name)
    if agent is None:
        return f"No agent named '{name}'."
    if agent["state"] in ("done", "dead"):
        return f"Agent '{name}' is already {agent['state']}."
    queue = get_queue()
    cancelled = 0
    for job in queue.peek(limit=500):
        if job.get("agent_id") == agent["id"] and \
                job.get("status") in ("ready", "running"):
            if queue.cancel(job["id"]):
                cancelled += 1
    _store().set_status(agent["id"], "paused")
    _store().log_action(agent["id"], "message", "paused by user")
    return f"Agent '{name}' paused ({cancelled} queued job(s) cancelled)."


def agent_resume(name: str) -> str:
    """
    Resume a paused or parked background agent (queues a resume job).

    Args:
        name: The agent's name.

    Returns:
        Confirmation, or a reason it doesn't exist.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agent = _find(name)
    if agent is None:
        return f"No agent named '{name}'."
    if agent["state"] in ("done", "dead"):
        return f"Agent '{name}' is already {agent['state']}."
    _store().set_status(agent["id"], "idle")
    _store().log_action(agent["id"], "message", "resumed by user")
    queue = get_queue()
    job_id = queue.enqueue(
        "resume",
        {"agent_id": agent["id"], "source": "user"},
        agent_id=agent["id"],
        idempotency_key=f"resume-{agent['id']}-{time.time():.6f}",
    )
    return f"Agent '{name}' resumed (job {job_id})."


def agent_kill(name: str) -> str:
    """
    Terminate a background agent permanently (confirmed). Its queued jobs are
    cancelled and its schedule cleared; the session is marked dead.

    Args:
        name: The agent's name.

    Returns:
        Confirmation, or a reason it doesn't exist.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agent = _find(name)
    if agent is None:
        return f"No agent named '{name}'."
    if agent["state"] in ("done", "dead"):
        return f"Agent '{name}' is already {agent['state']}."

    def _do() -> str:
        queue = get_queue()
        cancelled = 0
        for job in queue.peek(limit=500):
            if job.get("agent_id") == agent["id"] and \
                    job.get("status") in ("ready", "running"):
                if queue.cancel(job["id"]):
                    cancelled += 1
        _store().set_schedule(agent["id"], None)
        _store().transition(agent["id"], "dead")
        _store().log_action(agent["id"], "message", "killed by user")
        return f"Agent '{name}' terminated ({cancelled} job(s) cancelled)."

    from sopno.tools.builtins import files

    return files._awaiting_confirmation(f"terminate agent '{name}' permanently",
                                        _do)


def agent_log(name: str, limit: int = 50) -> str:
    """
    Show a background agent's append-only audit trail (actions, messages,
    transitions, errors).

    Args:
        name: The agent's name.
        limit: How many entries to show (max 100).

    Returns:
        The audit trail, or a reason the agent doesn't exist.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agent = _find(name)
    if agent is None:
        return f"No agent named '{name}'."
    limit = max(1, min(int(limit), _MAX_LOG))
    entries = _store().action_log(agent["id"], limit=limit)
    if not entries:
        return f"No activity logged for '{name}' yet."
    lines = [f"Audit log for '{name}' (newest first):"]
    for entry in entries:
        lines.append(f"- {entry['created_at']} {entry['kind']}: "
                     f"{entry['detail']}")
    return "\n".join(lines)


def agent_align(name: str, correction: str) -> str:
    """
    Give a background agent a durable correction / preference. It is recorded in
    the agent's alignment store and injected into its ORIENT phase on resume.

    Args:
        name: The agent's name.
        correction: The instruction to keep going forward, e.g. 'always run the
            tests before committing'.

    Returns:
        Confirmation, or a reason the agent doesn't exist.
    """
    if not _enabled():
        return "Background agents are disabled in config.json (agents_enabled)."
    agent = _find(name)
    if agent is None:
        return f"No agent named '{name}'."
    correction = (correction or "").strip()
    if not correction:
        return "Give the agent a correction to record."
    count = _store().add_alignment(agent["id"], correction)
    _store().log_action(agent["id"], "message",
                        f"alignment: {correction[:200]}")
    return (f"Alignment recorded for '{name}' "
            f"({count} note(s) on file). It applies from the next resume.")
