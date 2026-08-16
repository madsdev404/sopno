"""
sopno/core/coding/tools.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Tool dispatch + gated file I/O for the coding agent.

Read-only builtins run through their real implementations (no interactive side
effects). Mutating file tools are re-implemented here to bypass the Yes/No
pending-action prompt while keeping the ``_authorize`` gate — the agent is
*autonomous*, not *unprivileged*.

Every agent write passes four checks (deny-first):
  1. the shared file gate (``files._authorize`` + ``file_blocked_paths``)
  2. the harness-owned docs (PLAN.md / progress.md / SUMMARY.md)
  3. coding-protected paths (``coding_protected_paths``)
  4. the ticket's ``paths_allowed`` scope
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from sopno.config.settings import settings
from sopno.tools.builtins.dev import git as _git
from sopno.tools.builtins.dev import terminal as _term
from sopno.tools.builtins.files import files as _files
from sopno.tools.builtins.system.datetime_tool import get_current_time
from sopno.tools.schema import get_schema

from sopno.core.coding.util import q

# Harness-owned docs: the agent may not write/edit/delete them via its own tools.
HARNESS_DOCS = frozenset({"PLAN.md", "progress.md", "SUMMARY.md"})

# Read-only builtins with their argument mappers.
READ_TOOLS: dict[str, Callable[[dict], str]] = {
    "read_file": lambda a: _files.read_file(a["path"], a.get("lines")),
    "list_directory": lambda a: _files.list_directory(a.get("path", "")),
    "search_files": lambda a: _files.search_files(a["query"], a.get("path", ""),
                                                  a.get("mode", "content")),
    "git_status": lambda a: _git.git_status(a.get("repo", "")),
    "git_log": lambda a: _git.git_log(a.get("repo", ""), int(a.get("limit", 10))),
    "git_diff": lambda a: _git.git_diff(a.get("repo", ""), bool(a.get("staged", False))),
    "git_commit_message": lambda a: _git.git_commit_message(a.get("repo", "")),
    "terminal_status": lambda a: _term.terminal_status(),
    "get_current_time": lambda a: get_current_time(),
}

CHANGE_TOOLS = frozenset({
    "write_file", "edit_file", "delete_file", "rename_file", "move_file", "copy_file",
})

TERMINAL_TOOLS = frozenset({"run_terminal", "terminal_send"})

# Tool schema allowlist (least authority) — same names as the builtin tools.
ALLOWED_TOOLS = tuple(READ_TOOLS) + (
    "write_file", "edit_file", "delete_file", "rename_file", "copy_file",
    "move_file", "run_terminal", "terminal_send",
)


def tools_schema() -> list:
    """The JSON tool schemas the agent may call, filtered to the allowlist."""
    return [t for t in get_schema() if t["function"]["name"] in ALLOWED_TOOLS]


class ToolDispatcher:
    """
    Routes tool calls and owns the safety gates. All mutating operations
    resolve paths against the worktree root and refuse anything that fails the
    four deny-first checks above.
    """

    def __init__(
        self,
        repo: Path,
        worktree: Path,
        paths_allowed: Optional[list[str]] = None,
    ) -> None:
        self.repo = Path(repo)
        self.worktree = Path(worktree)
        self.paths_allowed = [str(p) for p in (paths_allowed or [])]

    # ── Gates ────────────────────────────────────────────────────────────────

    def _protected_paths(self) -> list[Path]:
        paths: list[Path] = []
        for entry in settings.coding_protected_paths:
            p = Path(entry).expanduser()
            if not p.is_absolute():
                p = self.repo / p
            try:
                paths.append(p.resolve(strict=False))
            except OSError:
                paths.append(p)
        return paths

    def _is_protected(self, target: Path) -> bool:
        if target.name in HARNESS_DOCS:
            return True
        try:
            resolved = target.resolve(strict=False)
        except OSError:
            resolved = target
        for protected in self._protected_paths():
            try:
                protected = protected.resolve(strict=False)
            except OSError:
                pass
            if resolved == protected or protected in resolved.parents:
                return True
        return False

    def _within_allowed(self, target: Path) -> bool:
        if not self.paths_allowed:
            return True
        try:
            resolved = target.resolve(strict=False)
        except OSError:
            return False
        for entry in self.paths_allowed:
            p = Path(entry).expanduser()
            if not p.is_absolute():
                p = self.worktree / p
            try:
                p = p.resolve(strict=False)
            except OSError:
                continue
            if resolved == p or p in resolved.parents:
                return True
        return False

    def _gate(self, target: Path, mode: str) -> str:
        """Refusal reason for an agent write to ``target``, or '' if allowed."""
        reason = _files._authorize(target, mode)
        if reason:
            return reason
        if self._is_protected(target):
            return f"{target} is protected — the agent may not {mode} it."
        if not self._within_allowed(target):
            return f"{target} is outside the ticket's paths_allowed scope."
        return ""

    def _resolve_agent_path(self, path: str) -> tuple[Optional[Path], str]:
        """Resolve an agent-supplied path against the worktree root."""
        raw = (path or "").strip()
        if not raw:
            return None, "Please provide a path."
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = self.worktree / p
        try:
            p = p.resolve(strict=False)
        except OSError:
            return None, f"Invalid path '{raw}'."
        return p, ""

    # ── Mutating operations (bypass the interactive confirm, not the gate) ───

    def _write(self, path: str, content: str) -> str:
        target, err = self._resolve_agent_path(path)
        if err:
            return err
        assert target is not None
        reason = self._gate(target, "write")
        if reason:
            return f"Blocked by safety policy — {reason}."
        data = (content or "").encode("utf-8")
        if len(data) > _files._max_size():
            return "Content is too large for one write."
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content or "", encoding="utf-8")
        except OSError as e:
            return f"Could not write {target}: {e}"
        return f"Done — wrote {len(data)} bytes to {target}."

    def _edit(self, path: str, old_string: str, new_string: str) -> str:
        target, err = self._resolve_agent_path(path)
        if err:
            return err
        assert target is not None
        reason = self._gate(target, "write")
        if reason:
            return f"Blocked by safety policy — {reason}."
        if not target.is_file():
            return f"No file at {target}."
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return f"Could not read {target}: {e}"
        count = current.count(old_string)
        if count == 0:
            return f"'{old_string}' was not found in {target}."
        if count > 1:
            return f"'{old_string}' appears {count} times in {target} — be more specific."
        try:
            target.write_text(current.replace(old_string, new_string, 1), encoding="utf-8")
        except OSError as e:
            return f"Could not write {target}: {e}"
        return f"Done — replaced one occurrence in {target}."

    def _delete(self, path: str) -> str:
        target, err = self._resolve_agent_path(path)
        if err:
            return err
        assert target is not None
        reason = self._gate(target, "write")
        if reason:
            return f"Blocked by safety policy — {reason}."
        if not target.exists():
            return f"No file at {target}."
        if target.is_dir():
            return f"{target} is a folder. I only delete individual files."
        try:
            target.unlink()
        except OSError as e:
            return f"Could not delete {target}: {e}"
        return f"Done — deleted {target}."

    def _rename(self, path: str, new_path: str) -> str:
        src, err = self._resolve_agent_path(path)
        if err:
            return err
        dst, err2 = self._resolve_agent_path(new_path)
        if err2:
            return err2
        assert src is not None and dst is not None
        for target in (src, dst):
            reason = self._gate(target, "write")
            if reason:
                return f"Blocked by safety policy — {reason}."
        if not src.exists():
            return f"No file at {src}."
        if src.is_dir():
            return f"{src} is a folder. I only rename individual files."
        if dst.exists():
            return f"{dst} already exists — I won't overwrite it."
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        except OSError as e:
            return f"Could not rename {src}: {e}"
        return f"Done — moved {src.name} to {dst}."

    def _copy(self, path: str, new_path: str, overwrite: bool = False) -> str:
        src, err = self._resolve_agent_path(path)
        if err:
            return err
        dst, err2 = self._resolve_agent_path(new_path)
        if err2:
            return err2
        assert src is not None and dst is not None
        reason = _files._authorize(src, "read")
        if reason:
            return f"Blocked by safety policy — {reason}."
        reason = self._gate(dst, "write")
        if reason:
            return f"Blocked by safety policy — {reason}."
        if not src.exists():
            return f"No file or folder at {src}."
        if dst == src:
            return "Source and destination are the same path."
        if dst.exists() and not overwrite:
            return f"{dst} already exists — pass overwrite=true to replace it."
        try:
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except OSError as e:
            return f"Could not copy {src}: {e}"
        return f"Done — copied {src} to {dst}."

    def _terminal(self, command: str, timeout: Optional[int] = None) -> str:
        """
        Run a shell command scoped to the worktree via the shared terminal.
        The ``cd`` is wrapped in a subshell so the shared session's cwd is
        never mutated by the agent.
        """
        command = (command or "").strip()
        if not command:
            return "Please provide a command to run."
        scoped = f"(cd {q(self.worktree)} && {command})"
        result = _term._run_command_raw(scoped, timeout=timeout)
        if result.get("blocked"):
            return f"Blocked by safety policy — {result['blocked']}."
        if result.get("error"):
            return result["error"]
        return _term._format_output(result)

    # ── Dispatch ─────────────────────────────────────────────────────────────

    def dispatch(self, name: str, args: dict) -> str:
        """Route one tool call, returning the observation text."""
        name = (name or "").strip()
        args = args or {}
        if name in READ_TOOLS:
            try:
                return str(READ_TOOLS[name](args))
            except Exception as e:  # noqa: BLE001
                return f"Tool error ({name}): {e}"
        if name == "write_file":
            return self._write(args.get("path", ""), args.get("content", ""))
        if name == "edit_file":
            return self._edit(args.get("path", ""), args.get("old_string", ""),
                              args.get("new_string", ""))
        if name == "delete_file":
            return self._delete(args.get("path", ""))
        if name == "rename_file":
            return self._rename(args.get("path", ""), args.get("new_path", ""))
        if name == "move_file":
            return self._rename(args.get("path", ""), args.get("new_path", ""))
        if name == "copy_file":
            return self._copy(args.get("path", ""), args.get("new_path", ""),
                              bool(args.get("overwrite", False)))
        if name == "run_terminal":
            return self._terminal(args.get("command", ""), args.get("timeout"))
        if name == "terminal_send":
            return _term.terminal_send(args.get("keys", ""), bool(args.get("enter", False)))
        return f"Tool '{name}' is not in the coding-agent allowlist."
