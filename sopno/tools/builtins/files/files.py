"""
sopno/tools/builtins/files/files.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Permission-gated file & folder access for Sopno.

Reads are allowed anywhere inside the configured read roots; writes, edits,
renames and deletes additionally require a Yes/No confirmation (spoken in
voice mode, typed in text mode) unless ``file_confirm_writes`` is disabled.

Every operation passes through the ``_authorize`` gate, applied in order:

  1. master switch (``file_enabled``)
  2. absolute, resolved (symlink-safe) path
  3. secret / foot-gun deny-list (``file_blocked_paths``)
  4. allowed roots (``file_allowed_read`` / ``file_allowed_write``)

Writes that need confirmation are parked in a pending-action slot; the
assistant asks the user, then calls ``resolve_pending`` on the next reply.

  read_file(path, lines)     → file contents (optionally head/tail), binary docs
  write_file(path, content)  → create or overwrite a file (confirmed)
  edit_file(path, old, new)  → exact-string replace (confirmed)
  list_directory(path)       → entries of a folder
  delete_file(path)          → remove a single file (confirmed)
  rename_file(path, new)     → move / rename a file (confirmed)
  copy_file(path, new)       → duplicate a file or folder (confirmed)
  move_file(path, new)       → alias of rename_file (confirmed)
  search_files(query, ...)   → find files by name or content
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import uuid
from pathlib import Path
from typing import Callable, Optional

from sopno.config.settings import settings
from . import readers

_MAX_ENTRIES = 200


def _fmt_size(n: int) -> str:
    """Human-friendly size (B / KB / MB / GB)."""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _max_size() -> int:
    return max(1, int(getattr(settings, "file_max_size_bytes", 2_000_000)))


def _max_chars() -> int:
    return max(1, int(getattr(settings, "file_output_chars", 6000)))


# ── Path gate ────────────────────────────────────────────────────────────────

def _normalize_root(root: str) -> Optional[Path]:
    """Resolve a configured allowed root; '.' / '<project_root>' = project root."""
    if not root or str(root).strip() in (".", "<project_root>"):
        return settings.project_root
    try:
        return Path(root).expanduser().resolve(strict=False)
    except OSError:
        return None


def _resolve_target(path: str) -> tuple[Optional[Path], str]:
    """Expand ~ and resolve (symlink-safe) a path. Returns (path, error)."""
    raw = (path or "").strip()
    if not raw:
        return None, "Please provide a path."
    if not raw.startswith(("~", "/")):
        return None, f"Use an absolute path, got '{raw}'."
    try:
        p = Path(raw).expanduser().resolve(strict=False)
    except OSError:
        return None, f"Invalid path '{raw}'."
    return p, ""


def _blocked_reason(path: Path) -> str:
    """Why a resolved path is off-limits, or '' if it is allowed."""
    parts = {p.lower() for p in path.parts}
    for entry in settings.file_blocked_paths:
        e = (entry or "").strip()
        if not e:
            continue
        low_e = e.lower()
        if any(ch in low_e for ch in "*?"):
            if any(fnmatch.fnmatch(part, low_e) for part in parts):
                return f"matches blocked pattern '{entry}'"
        elif "/" in e or "\\" in e:
            bp = Path(e).expanduser()
            if not bp.is_absolute():
                bp = Path(settings.project_root) / bp
            try:
                bp = bp.resolve(strict=False)
            except OSError:
                pass
            if path == bp or bp in path.parents:
                return f"matches blocked path '{entry}'"
        elif low_e in parts:
            return f"matches blocked name '{entry}'"
    return ""


def _authorize(path: Path, mode: str) -> str:
    """Return a refusal reason, or '' if `path` may be used for `mode` (read/write)."""
    if not settings.file_enabled:
        return "File access is disabled (file_enabled = false in config.json)."
    if not path.is_absolute():
        return "Only absolute paths are supported."
    reason = _blocked_reason(path)
    if reason:
        return f"{path} is off-limits — it {reason}."
    roots = settings.file_allowed_read if mode == "read" else settings.file_allowed_write
    if not roots:
        key = "file_allowed_read" if mode == "read" else "file_allowed_write"
        return f"No {mode} roots are configured ({key} in config.json)."
    for root in roots:
        root_path = _normalize_root(root)
        if root_path is not None and (path == root_path or root_path in path.parents):
            return ""
    shown = ", ".join(str(_normalize_root(r) or r) for r in roots)
    return f"{path} is outside the allowed {mode} roots ({shown})."


# ── Pending-action confirmation ──────────────────────────────────────────────

_PENDING_ACTION: Optional[dict] = None


def _awaiting_confirmation(description: str, fn: Callable[[], str]) -> str:
    """Register a pending mutating action and ask the user to approve it."""
    global _PENDING_ACTION
    _PENDING_ACTION = {
        "id": uuid.uuid4().hex[:8],
        "description": description,
        "fn": fn,
    }
    return (
        f"I need your permission to {description}. "
        f"Say 'yes' to allow it, or 'no' to cancel. "
        f"(pending action {_PENDING_ACTION['id']})"
    )


def pending_action() -> Optional[dict]:
    """Info about the write/delete awaiting confirmation, or None."""
    if _PENDING_ACTION is None:
        return None
    return {"id": _PENDING_ACTION["id"], "description": _PENDING_ACTION["description"]}


def resolve_pending(action_id: str, decision: str) -> Optional[str]:
    """Resolve a pending action with 'yes' or 'no'. Returns the result text."""
    global _PENDING_ACTION
    if _PENDING_ACTION is None or _PENDING_ACTION["id"] != action_id:
        return None
    action = _PENDING_ACTION
    _PENDING_ACTION = None
    if decision == "no":
        return f"Cancelled: {action['description']}."
    return action["fn"]()


# ── Read tools ───────────────────────────────────────────────────────────────

def read_file(path: str, lines: Optional[int] = None) -> str:
    """
    Read the contents of a file.

    Args:
        path: Absolute path of the file to read.
        lines: Optional — positive = first N lines, negative = last N lines.

    Returns:
        The file contents (capped), or a reason it cannot be read.
    """
    target, err = _resolve_target(path)
    if err:
        return err
    assert target is not None
    reason = _authorize(target, "read")
    if reason:
        return reason
    if target.is_dir():
        return f"{target} is a folder. Use list_directory to see its contents."
    if not target.is_file():
        return f"No file at {target}."

    # Binary documents (PDF, images, Office) are routed to the readers, which
    # have their own page/image and output caps (they can exceed the text
    # file_max_size_bytes limit, e.g. scanned PDFs).
    if readers.is_binary_like(target):
        text, method = readers.extract_text(target)
        if method:
            return f"[{method}] {text}"

    size = target.stat().st_size
    if size > _max_size():
        return (f"{target} is {_fmt_size(size)} — larger than the "
                f"{_fmt_size(_max_size())} limit (file_max_size_bytes in config.json).")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Could not read {target}: {e}"

    if lines is not None:
        try:
            n = int(lines)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            text = "\n".join(text.splitlines()[:n])
        elif n < 0:
            text = "\n".join(text.splitlines()[n:])
    if len(text) > _max_chars():
        text = text[:_max_chars()] + "\n…(content truncated)…"
    return text or "(empty file)"


def list_directory(path: str = "") -> str:
    """
    List the entries of a folder.

    Args:
        path: Absolute path of the folder (defaults to the project root).

    Returns:
        Sorted entries with type and size, or a reason it cannot be listed.
    """
    if path:
        target, err = _resolve_target(path)
        if err:
            return err
    else:
        target = settings.project_root
    assert target is not None
    reason = _authorize(target, "read")
    if reason:
        return reason
    if target.is_file():
        return f"{target} is a file. Use read_file to view its contents."
    if not target.is_dir():
        return f"No folder at {target}."
    try:
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError as e:
        return f"Could not list {target}: {e}"

    lines = []
    for p in entries[: _MAX_ENTRIES]:
        marker = "dir " if p.is_dir() else "file"
        if p.is_file():
            try:
                size = _fmt_size(p.stat().st_size)
            except OSError:
                size = "?"
        else:
            size = "—"
        lines.append(f"{marker:<5} {size:>8}  {p.name}")
    if not lines:
        return f"{target} is empty."

    head = f"{target} — {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"
    if len(entries) > _MAX_ENTRIES:
        head += f", showing first {_MAX_ENTRIES}"
    return head + "\n" + "\n".join(lines)


# ── Mutating tools (confirmed) ───────────────────────────────────────────────

def write_file(path: str, content: str) -> str:
    """
    Create a new file or overwrite an existing one.

    Args:
        path: Absolute path of the target file.
        content: The full text to write.

    Returns:
        Confirmation, or a reason the write cannot happen.
    """
    target, err = _resolve_target(path)
    if err:
        return err
    assert target is not None
    reason = _authorize(target, "write")
    if reason:
        return reason
    data = (content or "").encode("utf-8")
    if len(data) > _max_size():
        return (f"Content is {_fmt_size(len(data))} — larger than the "
                f"{_fmt_size(_max_size())} limit (file_max_size_bytes in config.json).")

    existing = None
    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = None
        if existing == content:
            return f"{target} already contains that exact content."

    description = f"overwrite '{target}'" if existing is not None else f"create '{target}'"

    def _do() -> str:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as e:
            return f"Could not write {target}: {e}"
        return f"Done — wrote {_fmt_size(len(data))} to {target}."

    if not settings.file_confirm_writes:
        return _do()
    return _awaiting_confirmation(description, _do)


def edit_file(path: str, old_string: str, new_string: str) -> str:
    """
    Replace one exact string in a file (read-before-edit invariant).

    Args:
        path: Absolute path of the file to edit.
        old_string: The exact text to replace (must appear exactly once).
        new_string: The replacement text.

    Returns:
        Confirmation, or a reason the edit cannot happen.
    """
    target, err = _resolve_target(path)
    if err:
        return err
    assert target is not None
    reason = _authorize(target, "write")
    if reason:
        return reason
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

    description = f"replace text in '{target}'"

    def _do() -> str:
        try:
            now = target.read_text(encoding="utf-8")
        except OSError as e:
            return f"Could not re-read {target}: {e}"
        n = now.count(old_string)
        if n == 0:
            return f"'{old_string}' is no longer in {target} — edit cancelled."
        if n > 1:
            return f"'{old_string}' now appears {n} times — edit cancelled, be more specific."
        try:
            target.write_text(now.replace(old_string, new_string, 1), encoding="utf-8")
        except OSError as e:
            return f"Could not write {target}: {e}"
        return f"Done — replaced one occurrence in {target}."

    if not settings.file_confirm_writes:
        return _do()
    return _awaiting_confirmation(description, _do)


def delete_file(path: str) -> str:
    """
    Delete a single file (folders are never deleted).

    Args:
        path: Absolute path of the file to remove.

    Returns:
        Confirmation, or a reason the file cannot be deleted.
    """
    target, err = _resolve_target(path)
    if err:
        return err
    assert target is not None
    reason = _authorize(target, "write")
    if reason:
        return reason
    if not target.exists():
        return f"No file at {target}."
    if target.is_dir():
        return f"{target} is a folder. I only delete individual files."

    description = f"delete '{target}'"

    def _do() -> str:
        try:
            target.unlink()
        except OSError as e:
            return f"Could not delete {target}: {e}"
        return f"Done — deleted {target}."

    if not settings.file_confirm_writes:
        return _do()
    return _awaiting_confirmation(description, _do)


def rename_file(path: str, new_path: str) -> str:
    """
    Rename or move a single file.

    Args:
        path: Absolute path of the file to move.
        new_path: Absolute destination path.

    Returns:
        Confirmation, or a reason the rename cannot happen.
    """
    src, err = _resolve_target(path)
    if err:
        return err
    dst, err2 = _resolve_target(new_path)
    if err2:
        return err2
    assert src is not None and dst is not None
    reason = _authorize(src, "write")
    if reason:
        return reason
    reason = _authorize(dst, "write")
    if reason:
        return reason
    if not src.exists():
        return f"No file at {src}."
    if src.is_dir():
        return f"{src} is a folder. I only rename individual files."
    if dst.exists():
        return f"{dst} already exists — I won't overwrite it."

    description = f"rename '{src}' to '{dst}'"

    def _do() -> str:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        except OSError as e:
            return f"Could not rename {src}: {e}"
        return f"Done — moved {src.name} to {dst}."

    if not settings.file_confirm_writes:
        return _do()
    return _awaiting_confirmation(description, _do)


# ── Search ───────────────────────────────────────────────────────────────────

def _search_max_results() -> int:
    return max(1, int(getattr(settings, "file_search_max_results", 50)))


def search_files(query: str, path: str = "", mode: str = "content") -> str:
    """
    Find files by file name or by content.

    Args:
        query: Filename pattern (mode="name", fnmatch glob or plain substring)
            or text to search for inside files (mode="content", regex).
        path: Folder to search, absolute (defaults to the project root).
        mode: "name" searches file names; "content" greps file contents.

    Returns:
        A capped list of hits, or a reason the search cannot run.
    """
    query = (query or "").strip()
    if not query:
        return "Please provide something to search for."
    mode = (mode or "content").strip().lower()
    if mode not in ("name", "content"):
        return f"Unknown mode '{mode}' — use 'name' or 'content'."

    if path:
        target, err = _resolve_target(path)
        if err:
            return err
    else:
        target = settings.project_root
    assert target is not None
    reason = _authorize(target, "read")
    if reason:
        return reason
    if target.is_file():
        return f"{target} is a file. Point search_files at a folder."
    if not target.is_dir():
        return f"No folder at {target}."

    cap = _search_max_results()
    hits: list[str] = []
    scanned = 0
    try:
        for p in target.rglob("*"):
            scanned += 1
            if scanned > 5000:
                hits.append("…(searched 5000 files, stopping)…")
                break
            if _blocked_reason(p):
                continue
            if mode == "name":
                if not p.is_file():
                    continue
                name = p.name
                if fnmatch.fnmatch(name, query) or query.lower() in name.lower():
                    hits.append(str(p))
            else:
                if not p.is_file():
                    continue
                if readers.is_binary_like(p):
                    continue
                line = _grep_line(p, query)
                if line is not None:
                    hits.append(line)
            if len(hits) >= cap:
                break
    except OSError as e:
        return f"Could not search {target}: {e}"

    if not hits:
        return f"No matches for {query!r} under {target}."

    head = f"{len(hits)} match{'es' if len(hits) != 1 else ''}"
    if len(hits) >= cap:
        head += f" (capped at {cap})"
    return head + "\n" + "\n".join(hits)


def _grep_line(path: Path, pattern: str) -> Optional[str]:
    """First 'path:line' for a regex/substring in a file, or None."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if _pattern_matches(pattern, raw):
                    line = raw.rstrip("\n")
                    if len(line) > 200:
                        line = line[:200] + "…"
                    return f"{path}:{lineno}: {line}"
    except OSError:
        return None
    return None


def _pattern_matches(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text, re.IGNORECASE) is not None
    except re.error:
        return pattern.lower() in text.lower()


# ── Copy / move ──────────────────────────────────────────────────────────────

def copy_file(path: str, new_path: str, overwrite: bool = False) -> str:
    """
    Duplicate a file or folder (files and folders both copy).

    Args:
        path: Absolute path of the file or folder to copy.
        new_path: Absolute destination path.
        overwrite: Allow replacing an existing destination (default False).

    Returns:
        Confirmation, or a reason the copy cannot happen.
    """
    src, err = _resolve_target(path)
    if err:
        return err
    dst, err2 = _resolve_target(new_path)
    if err2:
        return err2
    assert src is not None and dst is not None
    reason = _authorize(src, "read")
    if reason:
        return reason
    reason = _authorize(dst, "write")
    if reason:
        return reason
    if not src.exists():
        return f"No file or folder at {src}."
    if dst == src:
        return "Source and destination are the same path."
    if dst.exists() and not overwrite:
        return f"{dst} already exists — pass overwrite=true to replace it."

    description = f"copy '{src}' to '{dst}'"

    def _do() -> str:
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

    if not settings.file_confirm_writes:
        return _do()
    return _awaiting_confirmation(description, _do)


def move_file(path: str, new_path: str) -> str:
    """Move/rename a single file. Alias of rename_file (confirmed)."""
    return rename_file(path, new_path)
