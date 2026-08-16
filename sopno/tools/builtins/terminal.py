"""
sopno/tools/builtins/terminal.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Terminal tools — real, persistent shell access for Sopno.

Backed by ``cleat``: a persistent PTY shell whose byte stream is parsed for
OSC 133 marks, giving Sopno structured stdout + real exit codes, plus a
virtual screen for interactive programs (REPLs, TUIs, installers).

All three tools share ONE shell session per Sopno process, so ``cd`` /
``export`` / background jobs persist between calls:

    run_terminal(command, timeout)  → run a command, wait, return output
    terminal_send(keys, enter)      → send keys/stdin to the running program
    terminal_status()               → poll what the session is doing now

Safety: every command passes through a blocklist of destructive/irreversible
patterns (configurable via ``terminal_blocklist`` in config.json). Commands
run with the same privileges as Sopno itself.
"""

from __future__ import annotations

import re
import threading
from typing import Optional

from cleat.engine import Engine

from sopno.config.settings import settings

_ENGINE_LOCK = threading.Lock()
_ENGINE: Optional[Engine] = None

# Control-key tokens the LLM can send instead of raw control characters.
_CTRL = {"ctrl-c": "\x03", "ctrl-d": "\x04", "ctrl-z": "\x1a"}

_PIPE_TO_SHELL = re.compile(
    r"\b(curl|wget)\s+[^\n|;]*\|\s*(sudo\s+)?(ba)?sh\b", re.IGNORECASE
)


def _default_blocklist() -> list[str]:
    return [
        "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
        "rm -rf /", "rm -fr /", "rm -rf /*", "rm -fr /*",
        "rm -rf ~", "rm -fr ~", "sudo rm -rf /",
        "mkfs", "fdisk", "parted", "mkpart", "mkswap",
        "fork bomb", ":(){",
        "chmod -R 777 /", "chmod 777 /",
        "> /dev/sda", "> /dev/sdb", "> /dev/sdc", "> /dev/sdd",
        "of=/dev/sda", "of=/dev/sdb", "of=/dev/sdc",
    ]


def _blocked_reason(command: str) -> str:
    """Return a human reason the command is blocked, or '' if it is allowed."""
    if not settings.terminal_enabled:
        return "terminal access is disabled (terminal_enabled = false in config.json)"
    low = command.lower()
    for pattern in settings.terminal_blocklist:
        if pattern in low:
            return f"matches blocked pattern '{pattern}'"
    if _PIPE_TO_SHELL.search(command):
        return "piping a downloaded script directly into a shell"
    return ""


def _format_output(result: dict, truncate: bool = True) -> str:
    """Render a cleat result dict as a compact, capped string."""
    state = result.get("state")
    lines: list[str] = []
    if result.get("completed"):
        lines.append(f"exit code: {result.get('exit_code')}")
    else:
        lines.append(f"not finished — session state: {state or 'unknown'}")

    if "output" in result:
        out = result["output"]
    else:
        out = result.get("stdout") or result.get("screen") or ""
    if truncate and len(out) > settings.terminal_output_chars:
        out = "…(output truncated)…\n" + out[-settings.terminal_output_chars:]
    if out:
        lines.append(out.rstrip())

    if state == "awaiting-input":
        lines.append("The program is waiting for input. Use terminal_send(keys=..., enter=true) to respond.")
    elif state == "password":
        lines.append("A password prompt is showing. Use terminal_send(keys='<password>', enter=true).")
    elif state == "tui":
        lines.append("A full-screen program is open. Use terminal_send to send keys (e.g. 'ctrl-c', 'q').")
    elif state == "running":
        lines.append("Still running. Use terminal_status() to check later.")
    return "\n".join(lines)


def _engine() -> Engine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = Engine(shell=settings.terminal_shell).start()
        return _ENGINE


def _close() -> None:
    """Close the shared shell session and drop the reference."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            try:
                _ENGINE.close()
            except Exception:
                pass
            _ENGINE = None


# ── Tools ────────────────────────────────────────────────────────────────────

def run_terminal(command: str, timeout: Optional[float] = None) -> str:
    """
    Run a shell command in the persistent terminal session and return its output.

    Args:
        command: The shell command to run.
        timeout: Max seconds to wait for completion (default from settings,
                 1-300). Long-running commands return partial output + state.

    Returns:
        The command output (capped), the exit code, and/or the session state.
    """
    command = (command or "").strip()
    if not command:
        return "Please provide a command to run."

    reason = _blocked_reason(command)
    if reason:
        return (
            f"Blocked by safety policy — {reason}. "
            "If this command is actually safe, allow it in terminal_blocklist "
            "in config.json."
        )

    timeout = max(1.0, min(float(timeout or settings.terminal_timeout),
                           float(settings.terminal_max_timeout)))
    try:
        result = _engine().run_command(command, timeout=timeout)
    except RuntimeError as e:
        return f"Terminal error: {e}"
    except Exception as e:
        return f"Terminal error: {e}"

    return _format_output(result)


def terminal_send(keys: str, enter: bool = False) -> str:
    """
    Send keys/stdin to the running program in the terminal session.

    Args:
        keys: Text to type. Use 'ctrl-c', 'ctrl-d', or 'ctrl-z' for control
              characters; '' sends only the Enter key when enter=true.
        enter: Whether to press Enter after the keys.

    Returns:
        The updated session screen/output and state.
    """
    keys = (keys or "").strip()
    if keys.lower() in ("ctrl-c", "ctrl-d", "ctrl-z"):
        keys = _CTRL[keys.lower()]
    try:
        result = _engine().send_keys(keys, enter=enter)
    except Exception as e:
        return f"Terminal error: {e}"

    return _format_output({"completed": result.get("completed"),
                           "exit_code": result.get("exit_code"),
                           "state": result.get("state"),
                           "output": result.get("screen") or ""})


def terminal_status() -> str:
    """
    Check what the terminal session is doing right now (no input sent).

    Returns:
        Current output so far, whether the command finished (and its exit
        code), and the session state.
    """
    try:
        result = _engine().read_output(timeout=0.5, idle=0.2)
    except Exception as e:
        return f"Terminal error: {e}"
    return _format_output({"completed": result.get("completed"),
                           "exit_code": result.get("exit_code"),
                           "state": result.get("state"),
                           "output": result.get("output") or ""})
