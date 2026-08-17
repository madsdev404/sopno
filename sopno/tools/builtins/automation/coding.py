"""
sopno/tools/builtins/automation/coding.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User-facing tools for the autonomous coding pipeline
(autonomous-coding.md, rollout steps 4 & 7):

  - ``coding_run``: kick a coding ticket off in the background. It creates a
    durable coding session (kind="coding") and enqueues a ``run`` job the agent
    worker picks up on its next tick. A batch of tickets (``tickets=``) queues
    several runs unattended.
  - ``coding_status``: watch coding sessions — state, budget usage, and the
    worktree branch each one is on (parsed from the durable coding record).

These are the user's handle on the harness: create a ticket, watch it work in
its isolated worktree, then review or merge the finished branch.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from sopno.config.settings import settings
from sopno.core.agents.queue import get_queue
from sopno.core.agents.scheduler import parse_schedule
from sopno.core.agents.session import get_store

_ALLOWED_BUDGET_KEYS = ("max_turns", "max_wall_minutes", "max_actions_per_day")
_CODING_MARKER = "[coding-worktree]"


def _enabled() -> bool:
    return bool(getattr(settings, "coding_enabled", True))


def _find(name: str) -> Optional[dict]:
    return get_store().get_by_name((name or "").strip())


def _coding_record(agent: dict) -> Optional[dict]:
    for entry in reversed(agent.get("working_memory") or []):
        text = entry.get("text", "")
        if text.startswith(_CODING_MARKER):
            try:
                return json.loads(text[len(_CODING_MARKER):].strip())
            except ValueError:
                return None
    return None


def _format_coding(agent: dict) -> str:
    record = _coding_record(agent)
    branch = record.get("branch", "") if record else ""
    lines = [
        f"#{agent['id']} {agent['name']} [coding]",
        f"  state: {agent['state']} (status: {agent['status']})",
        f"  goal: {agent['goal']}",
    ]
    if branch:
        lines.append(f"  branch: {branch}")
    lines.append(f"  budget: {agent['budget_used']} turns used")
    return "\n".join(lines)


def _validate(goal, schedule, tools, budget) -> Optional[str]:
    if not (goal or "").strip():
        return "A coding ticket needs a goal."
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
    return None


def _make_session(name, goal, schedule, tools, budget) -> tuple[int, str]:
    """Create the coding session + queue its run job. (agent_id, ok|error)."""
    from sopno.core.coding.util import slugify

    name = (name or "").strip() or f"coding-{slugify(goal)}"
    try:
        agent_id = get_store().create(
            name, goal, schedule=schedule, tools=list(tools) if tools else None,
            budget=dict(budget) if budget else None, kind="coding",
        )
    except ValueError as e:
        return 0, str(e)
    get_store().transition(agent_id, "ready")
    queue = get_queue()
    job_id = queue.enqueue(
        "run", {"agent_id": agent_id}, agent_id=agent_id,
        idempotency_key=f"coding-{agent_id}-{time.time_ns()}",
    )
    return agent_id, (
        f"Agent '{name}' created (id {agent_id}) — coding job {job_id} queued. "
        "Watch it with coding_status; the finished branch is on the worktree."
    )


def coding_run(
    goal: Optional[str] = None,
    name: Optional[str] = None,
    schedule: Optional[str] = None,
    tools: Optional[list] = None,
    budget: Optional[dict] = None,
    tickets: Optional[list] = None,
) -> str:
    """
    Kick off an autonomous coding ticket in the background (or a whole batch).

    Args:
        goal: The ticket — what to implement / fix, in natural language.
        name: Optional session name (auto-generated from the goal otherwise).
        schedule: Optional trigger — 'interval:<seconds>', 'cron:<5 fields>'
            or a one-shot 'eta:YYYY-MM-DD HH:MM:SS'.
        tools: Optional tool allowlist for the session.
        budget: Optional ceilings dict (max_turns, max_wall_minutes,
            max_actions_per_day).
        tickets: Optional list of ticket dicts ({goal, name?, schedule?,
            tools?, budget?}) for an unattended batch — each gets its own
            fresh session and run.

    Returns:
        Confirmation with the session id + queued job id, or a reason.
    """
    if not _enabled():
        return "Autonomous coding is disabled in config.json (coding_enabled)."
    if tickets:
        if goal or name or schedule or tools or budget:
            return "When using tickets, pass per-ticket fields inside the list."
        if not isinstance(tickets, list) or not tickets:
            return "tickets must be a non-empty list of dicts."
        lines = []
        for t in tickets:
            if not isinstance(t, dict):
                return "Each ticket must be a dict with at least a goal."
            err = _validate(t.get("goal"), t.get("schedule"),
                            t.get("tools"), t.get("budget"))
            if err:
                return f"Ticket '{t.get('goal')}': {err}"
            agent_id, msg = _make_session(
                t.get("name"), t.get("goal"), t.get("schedule"),
                t.get("tools"), t.get("budget"),
            )
            if not agent_id:
                return f"Ticket '{t.get('goal')}': {msg}"
            lines.append(f"- {msg}")
        return "Queued coding batch:\n" + "\n".join(lines)
    err = _validate(goal, schedule, tools, budget)
    if err:
        return err
    agent_id, msg = _make_session(name, goal, schedule, tools, budget)
    return msg if agent_id else f"coding_run: {msg}"


def coding_status(name: Optional[str] = None, limit: int = 20) -> str:
    """
    Show coding sessions and the branch each one is working on.

    Args:
        name: A specific session name (default: all coding sessions).
        limit: How many sessions to show (default 20).

    Returns:
        One entry per session (state, goal, branch), or a reason none exist.
    """
    if not _enabled():
        return "Autonomous coding is disabled in config.json (coding_enabled)."
    store = get_store()
    if name:
        agent = _find(name)
        if agent is None:
            return f"No agent named '{name}'."
        if agent.get("kind") != "coding":
            return f"'{name}' is a {agent.get('kind')} agent, not a coding session."
        return _format_coding(agent)
    sessions = [a for a in store.list() if a.get("kind") == "coding"]
    if not sessions:
        return "No coding sessions yet. Try coding_run."
    limit = max(1, min(int(limit), 100))
    lines = [f"Coding sessions ({len(sessions)}):"]
    for agent in sessions[:limit]:
        lines.append(_format_coding(agent))
    return "\n\n".join(lines)
