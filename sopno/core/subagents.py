"""
sopno/core/subagents.py
━━━━━━━━━━━━━━━━━━━━━━━
Multi-agent runners.

A subagent is a focused, single-turn worker with its own system prompt and a
restricted tool schema, running the same Ollama tool-calling loop as the main
assistant but returning plain text instead of speaking. Agents:

  - researcher:  find facts / verify claims (search, fetch, read)
  - coder:       inspect and modify code (files, git, terminal)
  - reviewer:    read-only code / text review (files, git)
"""

from __future__ import annotations

from typing import Optional

from sopno.config.prompts import SYSTEM_PROMPT
from sopno.config.settings import settings
from sopno.llm.client import chat as llm_chat, message_as_dict
from sopno.tools.registry import execute_tool, get_registered_names
from sopno.tools.schema import get_schema

_MAX_TASK = 8000
_MAX_TURNS = 4

_AGENT_PROMPTS = {
    "researcher": (
        "You are a researcher subagent. Find accurate, source-backed answers.\n"
        "Gather information first with search_web / fetch_url / read_file, then "
        "write a concise factual answer with sources. Never invent URLs or facts."
    ),
    "coder": (
        "You are a coder subagent. Inspect the codebase with read_file / "
        "search_files / git_status, then write or modify code with edit_file. "
        "Run tests via run_terminal when useful. Return a short summary of what "
        "you changed and how you verified it."
    ),
    "reviewer": (
        "You are a reviewer subagent. Review code or documents read-only: point "
        "out bugs, security issues, and style problems with file:line references. "
        "Never modify files."
    ),
}

_ALLOWED_TOOLS = {
    "researcher": ("search_web", "fetch_url", "read_file", "list_directory",
                   "search_files", "read_logs", "get_current_time"),
    "coder": ("read_file", "write_file", "edit_file", "list_directory",
              "delete_file", "rename_file", "copy_file", "move_file",
              "search_files", "git_status", "git_log", "git_diff", "git_branch",
              "git_add", "git_commit", "git_stash", "git_commit_message",
              "run_terminal", "terminal_status"),
    "reviewer": ("read_file", "list_directory", "search_files", "git_status",
                 "git_log", "git_diff", "read_logs"),
}

_NAMES = frozenset(get_registered_names())


def list_agents() -> list[str]:
    return list(_AGENT_PROMPTS.keys())


def _schema_for(agent: str) -> list:
    allowed = _ALLOWED_TOOLS.get(agent, ())
    if not allowed:
        return []
    return [t for t in get_schema() if t["function"]["name"] in allowed]


def run_subagent(agent: str, task: str) -> str:
    """
    Run a focused subagent (researcher / coder / reviewer) on a task.

    Args:
        agent: Which subagent to run.
        task: What to do — be specific.

    Returns:
        The subagent's text answer, or a reason it failed.
    """
    agent = (agent or "").strip().lower()
    task = (task or "").strip()
    if agent not in _AGENT_PROMPTS:
        return f"Unknown subagent '{agent}'. Available: {', '.join(list_agents())}."
    if not task:
        return "The task is empty — tell the subagent what to do."
    if len(task) > _MAX_TASK:
        return f"That task is too long (max {_MAX_TASK} characters)."
    if not getattr(settings, "subagents_enabled", True):
        return "Subagents are disabled in config.json (subagents_enabled)."

    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT + "\n\n" + _AGENT_PROMPTS[agent]},
        {"role": "user", "content": task},
    ]
    tools = _schema_for(agent)
    max_turns = int(getattr(settings, "subagents_max_turns", _MAX_TURNS))

    try:
        for _ in range(max_turns):
            response = llm_chat(messages, tools=tools or None)
            response_msg = message_as_dict(response["message"])
            tool_calls = response_msg.get("tool_calls") or []
            if not tool_calls:
                content = response_msg.get("content", "").strip()
                return content or "The subagent finished without a response."
            messages.append(response_msg)
            for tool in tool_calls:
                fn = tool["function"] if isinstance(tool, dict) else tool.function
                name = fn["name"] if isinstance(fn, dict) else fn.name
                args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
                if not isinstance(args, dict):
                    args = {}
                if name not in _NAMES:
                    result = f"Tool '{name}' is not registered."
                else:
                    try:
                        result = execute_tool(name, args)
                    except Exception as err:  # noqa: BLE001
                        result = f"Tool error: {err}"
                messages.append({"role": "tool", "content": result})
        return ("The subagent hit its turn limit. "
                "It may need the main assistant to continue.")
    except Exception as err:  # noqa: BLE001
        return f"Subagent error: {err}"
