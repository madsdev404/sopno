"""
sopno/tools/registry.py
━━━━━━━━━━━━━━━━━━━━━━━
Central tools registry.

Maps the tool names declared in TOOLS_SCHEMA to their actual Python function
implementations, providing a clean execution interface.
"""

from typing import Callable, Any

from sopno.tools.builtins.system import open_application, control_volume, get_system_stats, lock_screen
from sopno.tools.builtins.search import search_web, fetch_url
from sopno.tools.builtins.datetime_tool import get_current_time
from sopno.tools.builtins.media import play_media_control
from sopno.tools.builtins.terminal import run_terminal, terminal_send, terminal_status
from sopno.tools.builtins.manage import (
    list_processes,
    kill_process,
    manage_service,
    read_logs,
    manage_cron,
)
from sopno.tools.builtins.files import (
    read_file,
    write_file,
    edit_file,
    list_directory,
    delete_file,
    rename_file,
)
from sopno.tools.builtins.git import (
    git_status,
    git_log,
    git_diff,
    git_branch,
    git_add,
    git_commit,
    git_stash,
    git_commit_message,
)
from sopno.llm.researcher import research


# Map schema tool names to Python functions
_REGISTRY: dict[str, Callable[..., str]] = {
    "get_current_time": get_current_time,
    "open_application": open_application,
    "search_web": search_web,
    "fetch_url": fetch_url,
    "control_volume": control_volume,
    "get_system_stats": get_system_stats,
    "lock_screen": lock_screen,
    "play_media_control": play_media_control,
    "research": research,
    "run_terminal": run_terminal,
    "terminal_send": terminal_send,
    "terminal_status": terminal_status,
    "list_processes": list_processes,
    "kill_process": kill_process,
    "manage_service": manage_service,
    "read_logs": read_logs,
    "manage_cron": manage_cron,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_directory": list_directory,
    "delete_file": delete_file,
    "rename_file": rename_file,
    "git_status": git_status,
    "git_log": git_log,
    "git_diff": git_diff,
    "git_branch": git_branch,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_stash": git_stash,
    "git_commit_message": git_commit_message,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """
    Look up and run a registered tool function.

    Args:
        name: The tool's schema name (e.g., 'get_current_time')
        arguments: Parameters parsed from the LLM tool-call output

    Returns:
        Spoken response/string output from the tool
    """
    func = _REGISTRY.get(name)
    if not func:
        return f"Error: Tool '{name}' is not registered."

    try:
        # Call the tool function spreading the arguments dict
        return func(**arguments)
    except TypeError as te:
        # Handle mismatched argument signatures gracefully
        return f"Error: Invalid arguments for tool '{name}' — {te}"
    except Exception as e:
        return f"Error executing tool '{name}': {e}"


def get_registered_names() -> list[str]:
    """Returns a list of all registered tool names."""
    return list(_REGISTRY.keys())
