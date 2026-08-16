"""
sopno/tools/builtins/system/manage.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Process / service / log / cron management tools.

Every command is executed through the shared persistent terminal session
(``terminal._run_command_raw``) so the safety blocklist and Sopno's own
privileges apply to everything.

  list_processes(query, limit) → top processes (optionally filtered)
  kill_process(target, signal) → terminate a process by PID or name
  manage_service(action, name) → systemctl --user start/stop/restart/status…
  read_logs(source, unit, lines)→ recent journalctl / file-tail entries
  manage_cron(action, …)       → list / add / remove crontab jobs
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from sopno.config.settings import settings
from sopno.tools.builtins.dev.terminal import _blocked_reason, _run_command_raw, _shell_pid

# Shell-safe tokens (service/unit names, absolute paths — no metacharacters).
_SAFE_SERVICE = re.compile(r"^[A-Za-z0-9@._-]+$")
_SAFE_PATH = re.compile(r"^/[A-Za-z0-9@._:/+~-]+$")

# Cron schedule: 5 fields of numbers/names/ranges/steps/lists, or @shortcut.
_TIME_FIELD = r"[0-9a-zA-Z*#,/W\-]+"
_CRON_TIME = re.compile(
    rf"^{_TIME_FIELD} {_TIME_FIELD} {_TIME_FIELD} {_TIME_FIELD} {_TIME_FIELD}$"
)
_CRON_SHORTCUT = re.compile(r"^@(reboot|yearly|annually|monthly|weekly|daily|midnight|hourly)$")

_SIGNALS = {"TERM", "INT", "KILL", "HUP", "STOP", "CONT"}

_SERVICE_ACTIONS = {"start", "stop", "restart", "status", "enable", "disable", "reload"}


def _cap(text: str) -> str:
    """Cap output to the LLM-friendly length, keeping the tail."""
    if len(text) <= settings.terminal_output_chars:
        return text
    return "…(output truncated)…\n" + text[-settings.terminal_output_chars:]


def _result(res: dict, fallback: str) -> str:
    """Convert a raw result dict into a friendly string."""
    if res.get("blocked"):
        return (
            f"Blocked by safety policy — {res['blocked']}. "
            "If this command is actually safe, allow it in terminal_blocklist "
            "in config.json."
        )
    if res.get("error"):
        return res["error"]
    return fallback


# ── Processes ────────────────────────────────────────────────────────────────

def list_processes(query: str = "", limit: int = 10) -> str:
    """
    List the top running processes, optionally filtered by a keyword.

    Args:
        query: Optional keyword to filter by (matches user/command line).
        limit: Max rows to show (1-50).

    Returns:
        A compact process table or a short message when nothing matches.
    """
    limit = max(1, min(int(limit or 10), 50))
    query = (query or "").strip()

    res = _run_command_raw("ps aux --sort=-%cpu")
    blocked_or_error = _result(res, "")
    if blocked_or_error:
        return blocked_or_error

    lines = (res.get("stdout") or "").splitlines()
    if not lines:
        return "No process information available."
    header, rows = lines[0], lines[1:]
    if query:
        q = query.lower()
        rows = [ln for ln in rows if q in ln.lower()]
    if not rows:
        return f"No processes match '{query}'."
    rows = rows[:limit]
    return _cap("Running processes:\n" + header + "\n" + "\n".join(rows))


def kill_process(target: str, signal: str = "TERM") -> str:
    """
    Terminate a running process by PID (a number) or by exact process name.

    Args:
        target: PID (e.g. '4321') or process name (e.g. 'firefox').
        signal: TERM (default), INT, KILL, HUP, STOP, or CONT.

    Returns:
        Confirmation or a reason the process could not be killed.
    """
    target = (target or "").strip()
    if not target:
        return "Please provide a PID or a process name to kill."
    sig = (signal or "TERM").strip().upper().lstrip("-")
    if sig not in _SIGNALS:
        return f"Unsupported signal '{signal}'. Use TERM, INT, KILL, HUP, STOP, or CONT."

    if target.isdigit():
        pid = int(target)
        forbidden = _forbidden_kill(target, pid)
        if forbidden:
            return f"I won't kill {target} — {forbidden}."
        res = _run_command_raw(f"kill -{sig} {pid}")
    else:
        if target.startswith("-") or len(target) > 64 or not re.fullmatch(
            r"[A-Za-z0-9._+\[\]()@ -]+", target
        ):
            return f"Invalid process name '{target}'."
        forbidden = _forbidden_kill(target, None)
        if forbidden:
            return f"I won't kill {target} — {forbidden}."
        res = _run_command_raw(f"pkill -{sig} -x {re.escape(target)}")

    if res.get("blocked") or res.get("error"):
        return _result(res, "")

    if res.get("exit_code") == 0:
        return f"Sent SIG{sig} to {target}."
    out = (res.get("stdout") or "").strip()
    if out:
        return f"Could not kill {target}: {out}"
    return f"Could not kill {target}: no matching process (exit {res.get('exit_code')})"


def _forbidden_kill(target: str, pid: Optional[int]) -> str:
    """Return why a kill target is off-limits, or '' if it is allowed."""
    if pid is not None and pid <= 1:
        return "it is the kernel or init (PID <= 1)"
    shell_pid = _shell_pid()
    if pid is not None and shell_pid and pid == shell_pid:
        return "it is Sopno's own terminal session"
    low = target.lower()
    if low == Path(settings.terminal_shell).name:
        return "it is Sopno's own terminal session"
    if low in ("init", "systemd", "sopno"):
        return f"it is a critical process ('{low}')"
    return ""


# ── Services ─────────────────────────────────────────────────────────────────

def manage_service(action: str, service: str) -> str:
    """
    Control a user systemd service via ``systemctl --user`` (no sudo needed).

    Args:
        action: start, stop, restart, status, enable, disable, or reload.
        service: The unit name (e.g. 'sopno.service').

    Returns:
        Confirmation, the status output, or a failure reason.
    """
    action = (action or "").strip().lower()
    service = (service or "").strip()
    if action not in _SERVICE_ACTIONS:
        return (f"Unknown service action '{action}'. "
                "Use start, stop, restart, status, enable, disable, or reload.")
    if not _SAFE_SERVICE.fullmatch(service) or len(service) > 64:
        return f"Invalid service name '{service}'."

    cmd = f"systemctl --user {action} {service}"
    if action == "status":
        cmd += " --no-pager -l | head -n 15"
    res = _run_command_raw(cmd)

    if res.get("blocked") or res.get("error"):
        return _result(res, "")

    out = (res.get("stdout") or "").strip()
    if action == "status":
        return _cap(out) if out else f"Service {service}: no status output."

    if res.get("exit_code") == 0:
        verb = {"start": "started", "stop": "stopped", "restart": "restarted",
                "enable": "enabled", "disable": "disabled", "reload": "reloaded"}[action]
        return f"Service {service} {verb}."
    return (f"Could not {action} service {service} (exit {res.get('exit_code')})."
            + (f"\n{out}" if out else ""))


# ── Logs ─────────────────────────────────────────────────────────────────────

def read_logs(source: str = "user", unit: Optional[str] = None, lines: int = 30) -> str:
    """
    Read recent log entries.

    Args:
        source: 'user' (user journal), 'system', or an absolute log file path.
        unit: Optional systemd unit to filter by (with user/system journal).
        lines: Number of most-recent lines to read (1-300).

    Returns:
        The raw log tail.
    """
    lines = max(1, min(int(lines or 30), 300))
    unit = (unit or "").strip()
    if unit and not _SAFE_SERVICE.fullmatch(unit):
        return f"Invalid unit name '{unit}'."

    src = (source or "user").strip()
    if src.startswith("/"):
        if not _SAFE_PATH.fullmatch(src):
            return f"Invalid log path '{src}'."
        cmd = f"tail -n {lines} {src}"
    elif src in ("user", "system"):
        if unit:
            cmd = f"journalctl --{src} -u {unit} -n {lines} --no-pager -o short"
        else:
            cmd = f"journalctl --{src} -n {lines} --no-pager -o short"
    else:
        return "Unknown log source. Use 'user', 'system', or a log file path."

    res = _run_command_raw(cmd)
    if res.get("blocked") or res.get("error"):
        return _result(res, "")
    out = (res.get("stdout") or "").strip()
    if not out:
        return "No log output."
    return _cap(out)


# ── Cron ─────────────────────────────────────────────────────────────────────

def manage_cron(action: str = "list", schedule: Optional[str] = None,
                command: Optional[str] = None) -> str:
    """
    List, add, or remove the current user's cron jobs.

    Args:
        action: 'list' (default), 'add', or 'remove'.
        schedule: For add — 5 cron fields (e.g. '0 9 * * *') or '@daily'.
        command: For add/remove — the command line to schedule or match.

    Returns:
        The current crontab, a confirmation, or a failure reason.
    """
    action = (action or "list").strip().lower()
    if action not in ("list", "add", "remove"):
        return "Unknown cron action. Use list, add, or remove."

    res = _run_command_raw("crontab -l")
    if res.get("blocked") or res.get("error"):
        return _result(res, "")
    current = (res.get("stdout") or "").strip()
    if "no crontab" in current.lower():
        current = ""

    if action == "list":
        if not current:
            return "No cron jobs for this user."
        return "Cron jobs:\n" + current

    live_lines = [ln.strip() for ln in current.splitlines()
                  if ln.strip() and not ln.strip().startswith("#")]

    if action == "remove":
        command = (command or "").strip()
        if not command:
            return "Removing a cron job needs the command text to match."
        target = command.lower()
        remaining = [ln for ln in current.splitlines()
                     if target not in ln.lower()]
        removed = len(live_lines) - len([ln for ln in remaining
                                         if ln.strip() and not ln.strip().startswith("#")])
        if removed <= 0:
            return f"No cron job matching '{command}' was found."
        body = "\n".join(remaining).strip()
        return _install_crontab(body + ("\n" if body else ""),
                                f"Removed {removed} cron job(s).")

    # action == "add"
    schedule = (schedule or "").strip()
    command = (command or "").strip()
    if not schedule or not command:
        return "Adding a cron job needs both a schedule and a command."
    if not (_CRON_SHORTCUT.fullmatch(schedule) or _CRON_TIME.fullmatch(schedule)):
        return (f"Invalid schedule '{schedule}'. Use 5 cron fields "
                "(e.g. '0 9 * * *') or a shortcut like '@daily'.")
    if "\n" in command or len(command) > 500:
        return "The cron command must be a single line (max 500 chars)."
    blocked = _blocked_reason(command)
    if blocked:
        return f"Refusing to schedule a blocked command — {blocked}."

    new_line = f"{schedule} {command}"
    if new_line in live_lines:
        return "That cron job already exists."
    updated = current + ("\n" if current else "") + new_line + "\n"
    return _install_crontab(updated, f"Added cron job '{new_line}'.")


def _install_crontab(content: str, success_msg: str) -> str:
    """Write a crontab to a temp file and install it non-interactively."""
    fd, tmp = tempfile.mkstemp(prefix="sopno-cron-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        res = _run_command_raw(f"crontab {tmp}")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if res.get("blocked") or res.get("error"):
        return _result(res, "")
    if res.get("exit_code") == 0:
        return success_msg
    out = (res.get("stdout") or "").strip()
    return f"Could not update crontab: {out or res.get('exit_code')}"
