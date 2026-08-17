"""
sopno/core/coding
━━━━━━━━━━━━━━━━
Autonomous coding agent (autonomous-coding.md, rollout step 1).

A ``CodingAgent`` takes a natural-language ticket and drives the ReAct loop
(INGEST → PLAN → ACT → OBSERVE → REFLECT → DECIDE → VERIFY → SUBMIT) against a
real repository **in an isolated git worktree on its own branch**, leaving the
main checkout untouched. Every meaningful change becomes a checkpoint commit, so
each step is one ``git revert`` away, and the finished branch is left for human
review and merge (review-required posture by default).

Safety is defense-in-depth and reuse-first:
  - worktree isolation (``git worktree add``) — the main checkout never changes
  - the existing file ``_authorize`` gate + ``file_blocked_paths`` deny-list
  - coding-specific protected paths (``config.json``, ``sopno/memory``, ``.git``)
  - per-ticket ``paths_allowed`` scope bounds
  - the shared terminal blocklist (commands run via ``_run_command_raw``)
  - hard budgets (turns / tokens / wall-clock / diff size) + a stagnation
    detector; an error is never recorded as a win

Modules (one job each):
  - ``agent.py``    — ``CodingAgent``: the loop itself
  - ``tools.py``    — ``ToolDispatcher``: tool routing + gated file I/O
  - ``worktree.py`` — ``WorktreeSession``: worktree lifecycle + checkpoints
  - ``verify.py``   — ``Verifier``: verification recipe + green check
  - ``prompts.py``  — prompt assembly (incl. the anti-drift recitation)
  - ``util.py``     — slug / shell-quote helpers
"""

from sopno.core.coding.agent import CodingAgent, TERMINAL_STATES  # noqa: F401

__all__ = ["CodingAgent", "TERMINAL_STATES", "run_coding_task", "run_coding_batch"]


def run_coding_task(task_spec: str | dict, **kwargs) -> dict:
    """Run a coding ticket to completion. Returns the result dict."""
    agent = CodingAgent(**kwargs)
    return agent.run(task_spec)


def run_coding_batch(tickets: list, **kwargs) -> list[dict]:
    """
    Run several coding tickets unattended (autonomous-coding.md step 7). Each
    ticket gets a *fresh* CodingAgent, so one run's worktree/session binding can
    never leak into the next. Returns one result dict per ticket.
    """
    results: list[dict] = []
    for ticket in tickets:
        agent = CodingAgent(**kwargs)
        results.append(agent.run(ticket))
    return results
