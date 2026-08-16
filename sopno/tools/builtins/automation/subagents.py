"""
sopno/tools/builtins/automation/subagents.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool that delegates a focused task to a researcher / coder / reviewer subagent.
"""

from __future__ import annotations


def run_subagent(agent: str, task: str) -> str:
    """
    Delegate a focused task to a subagent (researcher / coder / reviewer).

    Args:
        agent: Which subagent to run — 'researcher', 'coder', or 'reviewer'.
        task: What to do, described precisely.

    Returns:
        The subagent's text answer.
    """
    from sopno.core.subagents import run_subagent as _run

    return _run(agent, task)


def subagent_list() -> str:
    """
    List the available subagents.

    Returns:
        The subagent names, one per line.
    """
    from sopno.core.subagents import list_agents

    return "Subagents:\n" + "\n".join(list_agents())
