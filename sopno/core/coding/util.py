"""
sopno/core/coding/util.py
━━━━━━━━━━━━━━━━━━━━━━━━
Small shared helpers for the autonomous-coding package.
"""

from __future__ import annotations

import re
import shlex

# Git branch names may only contain a safe character set (matches the git tools).
_SAFE_BRANCH = re.compile(r"[A-Za-z0-9_.\/@-]+")


def slugify(text: str, max_len: int = 60) -> str:
    """Turn free text into a safe, short slug for branch names."""
    slug = re.sub(r"[^a-z0-9_.\-/]+", "-", (text or "").lower()).strip("-.")
    if not slug:
        slug = "task"
    return slug[:max_len].strip("-.")


def q(text) -> str:
    """Shell-quote a value for interpolation into a command string."""
    return shlex.quote(str(text))


def safe_branch(branch: str) -> bool:
    return _SAFE_BRANCH.fullmatch(branch) is not None
