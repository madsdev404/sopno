"""
sopno/core/agents/worker.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
AgentWorker — the daemon that claims run / resume jobs and drives the agent loop
(long-running-agents.md, rollout steps 4-6).

The queue is the coordination point: a worker atomically claims a ``run`` or
``resume`` job, loads the session, and runs a bounded ORIENT → DECIDE → ACT →
OBSERVE loop. Everything the agent does is checkpointed after every step (action
log + session state), so a crash mid-job leaves the audit trail intact and the
watchdog reclaims the session on boot.

What a worker run looks like:

    claim job ─▶ load session
      ├─ terminal / deleted / paused session → finish the job, do nothing
      └─ drive the loop (per-agent lock)
           ORIENT   load goal, plan, working memory, alignment, pending input,
                    recent activity into the fresh context window
           DECIDE   LLM picks the next action (session's tool allowlist)
           ACT      dispatch via the registry; an approval gate parks the
                    session in ``waiting_human`` with the pending action saved
           OBSERVE  append the result to the action log; reflect facts into
                    working memory
      └─ job ends at a terminal state, a park, or the per-job turn budget
           (partial progress → session returns to ``ready`` and sleeps until
            its next trigger — event-driven dormancy)

Budgets (``max_turns`` / ``max_wall_minutes`` / ``max_actions_per_day``) are
enforced here, not by the model: an exhausted session goes ``dead``.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional

from sopno.config.settings import settings
from sopno.llm.client import chat as llm_chat, message_as_dict

from sopno.core.agents.queue import AgentQueue
from sopno.core.agents.session import AgentSessionStore
from sopno.core.coding import run_coding_task
from sopno.tools.builtins.files import files as _files
from sopno.tools.registry import execute_tool, get_registered_names
from sopno.tools.schema import get_schema

# ── Constants ─────────────────────────────────────────────────────────────────

# Agent management tools are never given to a background agent (no self-hosting
# / self-termination surprises); a default allowlist is everything else.
MANAGEMENT_TOOLS = frozenset({
    "agent_create", "agent_list", "agent_status", "agent_send",
    "agent_pause", "agent_resume", "agent_kill", "agent_log", "agent_align",
    "coding_run", "coding_status",
})

# A job drives at most this many turns before handing the session back to
# dormancy (partial progress is checkpointed; the next trigger continues it).
_DEFAULT_JOB_MAX_TURNS = 20

# Context-selection caps for the ORIENT phase (token budget).
_ORIENT_MEMORY = 10
_ORIENT_ACTIVITY = 8
_ORIENT_ALIGNMENT = 5

_YES = re.compile(r"^\s*(?:yes|yep|yeah|y|approve|approved|ok|okay|sure|হ্যাঁ|হয়)\b",
                  re.IGNORECASE)
LlmStep = Callable[[list[dict], Optional[list]], dict]

# Serializes tool dispatch across workers so the pending-action singleton in
# files.py is never clobbered by two agents mid-flight.
_DISPATCH_LOCK = threading.RLock()

# One lock per agent so two workers can never drive the same session at once.
_AGENT_LOCKS: dict[int, threading.RLock] = {}
_AGENT_LOCKS_GUARD = threading.Lock()


def _agent_lock(agent_id: int) -> threading.RLock:
    with _AGENT_LOCKS_GUARD:
        lock = _AGENT_LOCKS.get(agent_id)
        if lock is None:
            lock = threading.RLock()
            _AGENT_LOCKS[agent_id] = lock
        return lock


def _parse_iso(raw: Optional[str]) -> Optional[float]:
    """Parse the store's ``%Y-%m-%d %H:%M:%S`` timestamps."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def _is_yes(text: str) -> bool:
    return bool(_YES.match((text or "").strip()))


class AgentWorker(threading.Thread):
    """
    A daemon thread that claims ready jobs from the queue and drives each one
    through the agent loop. Multiple workers may run concurrently
    (``agents_concurrency``); the per-agent lock keeps one session to one
    driver, and a shared dispatch lock serializes the pending-action gate.
    """

    def __init__(
        self,
        store: Optional[AgentSessionStore] = None,
        queue: Optional[AgentQueue] = None,
        *,
        worker_id: Optional[str] = None,
        poll_seconds: Optional[float] = None,
        run_check: Optional[Callable[[], bool]] = None,
        llm_step: Optional[LlmStep] = None,
        coding_runner: Optional[Callable[..., dict]] = None,
        reflect_fn: Optional[Callable[[dict], str]] = None,
    ) -> None:
        super().__init__(name=f"agent-worker-{worker_id or 'x'}", daemon=True)
        self._store = store or AgentSessionStore(settings.agents_path)
        self._queue = queue or AgentQueue(settings.agents_path)
        self._worker_id = worker_id or f"worker-{id(self):x}"
        self._poll = max(
            1.0, poll_seconds if poll_seconds is not None
            else getattr(settings, "agents_worker_poll_seconds", 2.0)
        )
        self._run_check = run_check or (lambda: True)
        self.llm_step = llm_step or self._default_llm_step
        self.coding_runner = coding_runner or run_coding_task
        # Step 7 (long-running-agents.md): distill a finished run into durable
        # alignment notes. None (the default) skips reflection entirely — the
        # runtime opts in by passing ``default_reflect``.
        self.reflect_fn = reflect_fn

    # ── Injection point (default) ─────────────────────────────────────────────

    def _default_llm_step(self, messages: list[dict], tools: Optional[list]) -> dict:
        response = llm_chat(messages, tools=tools or None)
        return message_as_dict(response["message"])

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self) -> None:
        while self._run_check():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 — never kill the worker
                pass
            time.sleep(self._poll)

    def tick(self) -> list[dict[str, Any]]:
        """Claim and process every job currently available (bounded loop)."""
        processed: list[dict[str, Any]] = []
        for _ in range(32):
            claimed = self._queue.claim(self._worker_id, limit=1)
            if not claimed:
                break
            job = claimed[0]
            try:
                self._process_job(job)
            except Exception as e:  # noqa: BLE001
                self._queue.fail(
                    job["id"], self._worker_id, f"worker crashed: {e}", retryable=True
                )
            processed.append(job)
        return processed

    # ── Job handling ──────────────────────────────────────────────────────────

    def _process_job(self, job: dict[str, Any]) -> None:
        agent_id = job.get("agent_id")
        if agent_id is None:
            self._queue.finish(job["id"], self._worker_id, "job has no agent")
            return
        with _agent_lock(int(agent_id)):
            self._run_with_lock(job)

    def _run_with_lock(self, job: dict[str, Any]) -> None:
        agent = self._store.get(job["agent_id"])
        if agent is None:
            self._queue.finish(job["id"], self._worker_id, "session was deleted")
            return
        state = agent["state"]
        if state in ("done", "dead"):
            self._queue.finish(job["id"], self._worker_id, f"session already {state}")
            return
        if (agent.get("status") or "") == "paused":
            self._queue.finish(job["id"], self._worker_id, "session is paused")
            return

        if state != "running":
            try:
                self._store.transition(agent["id"], "running")
            except ValueError:
                self._queue.fail(
                    job["id"], self._worker_id,
                    f"cannot start session in state '{state}'", retryable=False,
                )
                return

        if (agent.get("kind") or "general") == "coding":
            outcome = self._drive_coding(agent["id"])
        else:
            outcome = self._drive_agent(agent["id"], job)
            self._reflect(agent["id"])
        self._queue.finish(
            job["id"], self._worker_id,
            f"{outcome['state']}: {outcome['reason']}",
        )

    def _drive_coding(self, agent_id: int) -> dict[str, Any]:
        """
        Drive a ``kind='coding'`` session through the autonomous CodingAgent
        (isolated git worktree, checkpoint commits, verification). The coding
        agent transitions the session itself; we reconcile early returns.
        """
        agent = self._store.get(agent_id)
        assert agent is not None
        self._store.set_status(agent_id, "running coding task")
        spec: dict[str, Any] = {
            "goal": agent.get("goal") or "",
            "steps": agent.get("plan") or [],
        }
        try:
            result = self.coding_runner(spec, store=self._store, session_id=agent_id)
        except Exception as e:  # noqa: BLE001
            self._store.log_action(agent_id, "error", f"coding task crashed: {e}")
            self._store.transition(agent_id, "blocked")
            return {"state": "blocked", "reason": f"coding task crashed: {e}"}

        self._store.log_action(
            agent_id, "transition",
            f"coding finished: {result.get('state', '?')}: "
            f"{(result.get('reason') or '')[:400]}",
        )
        state = result.get("state") or "blocked"
        if (self._store.get(agent_id) or {}).get("state") == "running":
            target = {
                "success": "done", "no_op": "done", "blocked": "blocked",
                "stalled": "blocked", "exhausted": "dead",
            }.get(state, "dead")
            try:
                self._store.transition(agent_id, target)
            except ValueError:
                pass
        return {"state": state, "reason": result.get("reason") or ""}

    # ── The loop ──────────────────────────────────────────────────────────────

    def _drive_agent(self, agent_id: int, job: dict[str, Any]) -> dict[str, Any]:
        """One bounded run of the agent loop. Returns an outcome dict."""
        agent = self._store.get(agent_id)
        assert agent is not None
        messages = self._orient(agent)
        tools = self._tools_for(agent)
        job_max = int((agent.get("budget") or {}).get("max_turns", 0)) or int(
            getattr(settings, "agents_job_max_turns", _DEFAULT_JOB_MAX_TURNS)
        )
        max_turns = max(1, job_max)

        # On a resume, apply any queued human input first (approvals, replies).
        messages.extend(self._drain_input(agent_id))

        for _ in range(max_turns):
            if not self._run_check():
                return {"state": "ready", "reason": "worker stopping"}
            budget_hit = self._budget_exceeded(agent_id)
            if budget_hit:
                self._store.log_action(agent_id, "error", f"budget: {budget_hit}")
                self._store.transition(agent_id, "dead")
                return {"state": "dead", "reason": budget_hit}

            self._store.heartbeat(agent_id)
            self._queue.renew(job["id"], self._worker_id)

            try:
                msg = self.llm_step(messages, tools or None)
            except Exception as e:  # noqa: BLE001
                self._store.transition(agent_id, "blocked")
                return {"state": "blocked", "reason": f"LLM step failed: {e}"}
            messages.append(msg)
            self._store.bump_budget_used(agent_id)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                content = (msg.get("content") or "").strip()
                self._store.append_memory(
                    agent_id, f"Result: {content[:500]}" if content else "No result."
                )
                self._store.transition(agent_id, "done")
                return {"state": "done", "reason": content or "goal met"}

            park = self._execute_calls(agent_id, messages, tool_calls, tools)
            if park is not None:
                # An approval gate: save it and sleep until a human decides.
                self._store.set_pending_action(agent_id, park)
                desc = park.get("description") or "a mutating action"
                self._store.transition(agent_id, "waiting_human")
                return {"state": "waiting_human",
                        "reason": f"waiting for approval: {desc}"}

        # Job turn budget reached with the goal unfinished: checkpoint and sleep.
        self._store.transition(agent_id, "ready")
        return {"state": "ready", "reason": "job turn budget reached (dormant)"}

    # ── Tool execution ────────────────────────────────────────────────────────

    def _execute_calls(
        self,
        agent_id: int,
        messages: list[dict],
        tool_calls: list,
        allowed: frozenset[str],
    ) -> Optional[dict]:
        """Run every tool call in one assistant message; return a park, if any."""
        for call in tool_calls:
            fn = call["function"] if isinstance(call, dict) else call.function
            name = fn["name"] if isinstance(fn, dict) else fn.name
            args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
            if not isinstance(args, dict):
                args = {}
            if name not in allowed:
                result = f"Tool '{name}' is not in this agent's allowlist."
            else:
                result, park = self._dispatch(name, args)
                if park is not None:
                    messages.append({"role": "tool", "content": result})
                    self._store.log_action(agent_id, "action",
                                           f"{name}({json.dumps(args)[:500]})")
                    return park
            messages.append({"role": "tool", "content": result})
            self._store.log_action(
                agent_id, "action",
                f"{name}({json.dumps(args)[:500]}) -> {result[:200]}",
            )
        return None

    @staticmethod
    def _dispatch(name: str, args: dict) -> tuple[str, Optional[dict]]:
        """
        Execute one tool, serialized against the pending-action singleton.
        A result that parks a confirmation gate is returned alongside the
        parked action so the caller can sleep in ``waiting_human``.
        """
        with _DISPATCH_LOCK:
            stale = _files.pending_action()
            if stale is not None:
                _files.resolve_pending(stale["id"], "no")  # refuse leftovers
            result = execute_tool(name, args)
            parked = _files.pending_action()
            if parked is not None:
                _files.resolve_pending(parked["id"], "no")  # detach from globals
                return result, parked
        return result, None

    # ── ORIENT: durable state → fresh context window ─────────────────────────

    def _orient(self, agent: dict[str, Any]) -> list[dict]:
        goal = agent.get("goal") or ""
        alignment = agent.get("alignment") or []
        memory = agent.get("working_memory") or []
        activity = self._store.action_log(agent["id"], limit=_ORIENT_ACTIVITY + 4)
        activity = [a for a in activity if a.get("kind") in ("action", "message", "event")]

        lines = [
            "You are a persistent background agent running inside Sopno. Your "
            "context window resets between runs — write every important fact or "
            "decision to working memory and read it back on the next run.",
            "",
            f"## Goal",
            goal,
        ]
        if alignment:
            lines += ["", "## Alignment (corrections from the user — follow these)"]
            for entry in alignment[-_ORIENT_ALIGNMENT:]:
                lines.append(f"- {entry.get('text', '')}")
        if memory:
            lines += ["", "## Working memory"]
            for entry in memory[-_ORIENT_MEMORY:]:
                lines.append(f"- {entry.get('text', '')}")
        if activity:
            lines += ["", "## Recent activity (newest last)"]
            for entry in reversed(activity):
                lines.append(f"- {entry.get('detail', '')[:400]}")
        lines += [
            "",
            "## Instructions",
            "Drive the goal forward with a single tool call per step. When the "
            "goal is met, answer with a concise final summary (no tool call). "
            "If you need a human decision, answer directly and explain what you "
            "need — that parks the session for a human reply.",
        ]
        return [
            {"role": "system",
             "content": self._system_prompt(agent)},
            {"role": "user", "content": "\n".join(lines)},
        ]

    @staticmethod
    def _system_prompt(agent: dict[str, Any]) -> str:
        name = agent.get("name") or "agent"
        kind = agent.get("kind") or "general"
        prompt = (
            f"You are the background agent '{name}'. You work in short, "
            "autonomous runs and must checkpoint your progress durably."
        )
        if kind == "coding":
            prompt += (
                " Your task is a coding ticket: plan in PLAN.md, keep "
                "progress.md updated, write production code and tests, verify, "
                "and finish with a summary."
            )
        return prompt

    # ── REFLECT: distill a finished run into durable alignment notes ──────────

    def _reflect(self, agent_id: int) -> int:
        """
        After a general-agent run, ask the model (if ``reflect_fn`` is wired)
        to extract durable corrections/preferences from the run and store them
        in the alignment record, so the next context window follows them.
        Returns the number of notes stored. Failures are silent — reflection
        is a bonus, never a hard dependency.
        """
        if self.reflect_fn is None:
            return 0
        try:
            agent = self._store.get(agent_id)
            if agent is None or (agent.get("kind") or "general") == "coding":
                return 0
            text = (self.reflect_fn(agent) or "").strip()
        except Exception:  # noqa: BLE001
            return 0
        count = 0
        for line in text.splitlines():
            line = line.strip().lstrip("-*• ").strip()
            if line and self._store.add_alignment(agent_id, line) > 0:
                count += 1
        if count:
            self._store.log_action(agent_id, "message",
                                   f"reflected {count} alignment note(s)")
        return count

    # ── Resume: apply queued human input / approval decisions ────────────────

    def _drain_input(self, agent_id: int) -> list[dict]:
        """Turn queued human input into messages; resolve a parked approval."""
        agent = self._store.get(agent_id)
        assert agent is not None
        pending = self._store.drain_input(agent_id)
        if not pending:
            return []

        messages: list[dict] = []
        parked = agent.get("pending_action")
        if parked and pending:
            decision = pending[0]["text"]
            messages.append(self._decide(parked, decision))
            self._store.set_pending_action(agent_id, None)
            pending = pending[1:]
        for entry in pending:
            messages.append({
                "role": "user",
                "content": f"[message from the user] {entry.get('text', '')}",
            })
        return messages

    @staticmethod
    def _decide(parked: dict, decision: str) -> dict:
        result = _files.resolve_pending(
            parked.get("id"), "yes" if _is_yes(decision) else "no"
        )
        resolved = result or ("Approved." if _is_yes(decision) else "Declined.")
        return {"role": "tool", "content": f"[approval] {resolved}"}

    # ── Capability profile + budgets ──────────────────────────────────────────

    @staticmethod
    def _tools_for(agent: dict[str, Any]) -> frozenset[str]:
        allowlist = [str(t) for t in (agent.get("tools") or [])]
        if allowlist:
            return frozenset(allowlist)
        return frozenset(
            n for n in get_registered_names() if n not in MANAGEMENT_TOOLS
        )

    def _budget_exceeded(self, agent_id: int) -> Optional[str]:
        agent = self._store.get(agent_id)
        assert agent is not None
        budget = agent.get("budget") or {}
        used = int(agent.get("budget_used") or 0)

        max_turns = budget.get("max_turns")
        if max_turns and used >= int(max_turns):
            return f"turn budget ({max_turns}) exhausted"

        max_wall = budget.get("max_wall_minutes")
        if max_wall:
            started = _parse_iso(agent.get("created_at"))
            if started is not None and time.time() - started > int(max_wall) * 60:
                return f"wall-clock budget ({max_wall} min) exhausted"

        max_daily = budget.get("max_actions_per_day")
        if max_daily:
            cutoff = time.time() - 24 * 3600
            recent = 0
            for entry in self._store.action_log(agent_id, limit=1000):
                at = _parse_iso(entry.get("created_at"))
                if entry.get("kind") == "action" and at is not None and at >= cutoff:
                    recent += 1
            if recent >= int(max_daily):
                return f"actions-per-day budget ({max_daily}) exhausted"
        return None


# ── Singleton access (shared by the runtime / tools / tests) ─────────────────

_WORKERS: list[AgentWorker] = []


def default_reflect(agent: dict[str, Any]) -> str:
    """
    The runtime's default REFLECT step: ask the model to extract one-line
    alignment notes (corrections, preferences, lessons) from an agent's run so
    the next fresh context window follows them. Returns raw lines; ``_reflect``
    filters and stores them.
    """
    try:
        alignment = agent.get("alignment") or []
        prior = "\n".join(
            f"- {e.get('text', '')}" for e in alignment[-_ORIENT_ALIGNMENT:]
        ) or "(none)"
        messages = [
            {"role": "system", "content": (
                "You distill durable alignment notes from an agent's run: "
                "corrections the user gave, preferences the agent learned, and "
                "lessons worth repeating. Reply with ONLY short note lines, one "
                "per line, no bullets, no preamble. Omit anything already "
                "covered by the prior alignment.")},
            {"role": "user", "content": (
                f"Agent: {agent.get('name')}\n"
                f"Goal: {agent.get('goal') or ''}\n"
                f"Prior alignment:\n{prior}\n"
                f"Working memory (recent):\n"
                + "\n".join(f"- {e.get('text', '')}"
                            for e in (agent.get('working_memory') or [])[-6:]))},
        ]
        response = llm_chat(messages, tools=None)
        return message_as_dict(response["message"]).get("content", "")
    except Exception:  # noqa: BLE001
        return ""


def get_workers() -> list[AgentWorker]:
    """The currently-started workers (empty when none are running)."""
    return list(_WORKERS)


def set_workers(workers: Optional[list[AgentWorker]]) -> None:
    """Swap the worker list (used by the runtime and tests)."""
    global _WORKERS
    _WORKERS = list(workers) if workers else []
