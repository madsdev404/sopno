"""
sopno/tools/builtins/knowledge/notes.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Notes / knowledge base — markdown files under ``notes_dir``.

``note_write`` saves a note, ``note_list`` lists them, and ``note_search``
grep's them (read-only). The notes folder lives inside the project (an allowed
root by default) and can later feed the semantic index from feature #2.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from sopno.config.settings import settings
from sopno.tools.builtins.files import files as files

_MAX_CHARS = 20000
_TITLE_SAFE = re.compile(r"[^A-Za-z0-9 _\-()]+")


def _dir() -> tuple[Optional[Path], str]:
    root = getattr(settings, "notes_dir", "") or "sopno/memory/notes"
    p = Path(root)
    if not p.is_absolute():
        p = settings.project_root / p
    return p, ""


def note_write(title: str, content: str) -> str:
    """
    Save a note as a markdown file (confirmed).

    Args:
        title: Note title (becomes the file name).
        content: Note body (markdown ok).

    Returns:
        Confirmation, or a failure reason.
    """
    title = (title or "").strip()
    content = (content or "").strip()
    if not title:
        return "The note needs a title."
    if not content:
        return "The note is empty — write something first."
    if len(content) > _MAX_CHARS:
        return f"That note is too long (max {_MAX_CHARS} characters)."
    safe = _TITLE_SAFE.sub("", title).strip() or "note"
    safe = safe[:80].rstrip(" .")
    cdir, _ = _dir()
    cdir.mkdir(parents=True, exist_ok=True)
    reason = files._authorize(cdir, "write")
    if reason:
        return reason
    target = cdir / f"{safe}.md"

    def _do() -> str:
        header = f"# {title}\n\n"
        target.write_text(header + content + "\n", encoding="utf-8")
        return f"Note saved as {target.name}."

    if target.is_file() and getattr(settings, "file_confirm_writes", True):
        return files._awaiting_confirmation(f"overwrite '{target.name}'", _do)
    return files._awaiting_confirmation(f"save the note '{title}'", _do)


def note_list() -> str:
    """
    List the saved notes with their sizes and last-modified dates.

    Returns:
        One note per line, or a reason none exist.
    """
    cdir, _ = _dir()
    if not cdir.is_dir():
        return f"No notes folder yet ({cdir})."
    notes = sorted(cdir.glob("*.md"))
    if not notes:
        return "No notes yet."
    from datetime import datetime
    parts = []
    for n in notes:
        mtime = datetime.fromtimestamp(n.stat().st_mtime).strftime("%b %d %H:%M")
        size = n.stat().st_size
        parts.append(f"{n.stem} ({size} bytes, {mtime})")
    return "Notes:\n" + "\n".join(parts)


def note_search(query: str) -> str:
    """
    Search the notes for a phrase (case-insensitive).

    Args:
        query: The text to look for.

    Returns:
        Matching notes with line snippets, or a reason nothing matched.
    """
    query = (query or "").strip()
    if not query:
        return "What should I search for?"
    if len(query) > 200:
        return "That search is too long."
    cdir, _ = _dir()
    if not cdir.is_dir():
        return f"No notes folder yet ({cdir})."
    q = query.lower()
    hits = []
    for n in sorted(cdir.glob("*.md")):
        try:
            lines = n.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        matches = [ln for ln in lines if q in ln.lower()]
        if matches:
            snippets = " / ".join(ln.strip()[:120] for ln in matches[:3])
            hits.append(f"{n.stem}: {snippets}")
    if not hits:
        return f"No notes match '{query}'."
    return "Matches:\n" + "\n".join(hits)
