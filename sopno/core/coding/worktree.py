"""
sopno/core/coding/worktree.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Worktree lifecycle for a coding run.

Isolation is non-negotiable: every run gets a fresh ``git worktree`` on its own
branch, so the main checkout is never touched. A *checkpoint* is a commit after
each meaningful unit of work — every step is one ``git revert`` away. The run's
docs (PLAN.md / progress.md / SUMMARY.md) live in the worktree root, written by
the harness (the agent's own tools treat them as protected).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Optional

from sopno.core.coding.util import q, safe_branch, slugify

GitRunner = Callable[[str, str], dict]


class WorktreeSession:
    """Owns the worktree: creation, base commit, checkpoints, diff budget."""

    def __init__(self, repo: Path, worktree_dir: Path, git_runner: GitRunner) -> None:
        self.repo = Path(repo)
        self.worktree_dir = Path(worktree_dir)
        self.git_runner = git_runner
        self.worktree: Optional[Path] = None
        self.branch = ""
        self.base_sha = ""
        self.commits: list[str] = []

    # ── Branch naming ─────────────────────────────────────────────────────────

    def make_branch(self, goal: str) -> str:
        slug = slugify(goal or "task")
        branch = f"sopno/{slug}-{time.strftime('%Y%m%d-%H%M%S')}"
        return branch if safe_branch(branch) else "sopno/task"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def head(self) -> str:
        """The repo's current commit (the run's diff base)."""
        res = self.git_runner("rev-parse HEAD", str(self.repo))
        return (res.get("stdout") or "").strip()

    def setup(self, branch: str) -> str:
        """Create the worktree + branch; returns an error string or ''."""
        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        target = self.worktree_dir / branch.split("/")[-1]
        res = self.git_runner(
            f"worktree add -b {q(branch)} {q(target)} HEAD", str(self.repo)
        )
        if res.get("blocked") or res.get("error") or res.get("exit_code") not in (0, None):
            return (f"Could not create worktree: "
                    f"{res.get('error') or res.get('blocked') or res}")
        self.base_sha = self.head()
        self.worktree = target
        self.branch = branch
        return ""

    def checkpoint(self, note: str) -> Optional[str]:
        """Commit all current changes; returns the commit sha or None."""
        assert self.worktree is not None
        wt = str(self.worktree)
        res = self.git_runner("add -A", wt)
        if res.get("exit_code") not in (0, None):
            return None
        message = f"feat({self.branch.split('/')[-1]}): {note}"
        res = self.git_runner(f"commit -m {q(message)}", wt)
        out = (res.get("stdout") or "").strip()
        if res.get("exit_code") in (0, None) and "nothing to commit" not in out:
            sha = self.git_runner("rev-parse HEAD", wt)
            sha_val = (sha.get("stdout") or "").strip()
            if sha_val:
                self.commits.append(sha_val)
                return sha_val
        return None

    def diff_lines(self) -> int:
        """Lines added+removed on the branch vs. the base commit."""
        assert self.worktree is not None
        if not self.commits:
            return 0
        res = self.git_runner(
            f"--no-pager diff --numstat {q(self.base_sha)}...HEAD", str(self.worktree)
        )
        out = (res.get("stdout") or "").strip()
        total = 0
        for line in out.splitlines():
            parts = line.split("\t")
            for token in parts[:2]:
                if token.isdigit():
                    total += int(token)
        return total

    # ── Harness-owned docs (the agent cannot touch these) ────────────────────

    def write_doc(self, rel: str, content: str) -> None:
        assert self.worktree is not None
        target = (self.worktree / rel).resolve(strict=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def append_doc(self, rel: str, line: str) -> None:
        assert self.worktree is not None
        target = self.worktree / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")
