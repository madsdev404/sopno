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
        self._pre_merge_sha: Optional[str] = None

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

    def attach(self, branch: str, base: Optional[str] = None) -> str:
        """
        Reattach to an existing worktree (crash-resume): the branch keeps its
        checkpoint commits and harness docs, so the loop continues from the last
        commit instead of restarting. Returns an error string or ''.
        """
        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        target = self.worktree_dir / branch.split("/")[-1]
        if not target.is_dir():
            return f"no worktree found for branch {branch}"
        res = self.git_runner("branch --show-current", str(target))
        current = (res.get("stdout") or "").strip()
        if current != branch:
            return f"worktree {target} is on branch {current}, not {branch}"
        self.worktree = target
        self.branch = branch
        self.base_sha = base or self.head()
        log = self.git_runner(
            f"log --format=%H {q(self.base_sha)}..HEAD", str(target)
        )
        self.commits = [sha for sha in (log.get("stdout") or "").split() if sha]
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

    # ── Merge (step 7, auto_merge_guardrailed only) ─────────────────────────

    def merge_back(self) -> tuple[Optional[str], str]:
        """
        Merge the branch into the main checkout (--no-ff). The branch stays
        around so the run can be audited or reverted later. Returns
        ``(merged_sha_or_None, error_string_or_'')``.
        """
        assert self.worktree is not None
        self._pre_merge_sha = self.head()
        res = self.git_runner(f"merge --no-ff --no-edit {q(self.branch)}",
                              str(self.repo))
        if res.get("exit_code") not in (0, None):
            self.abort_merge()
            return None, (f"auto-merge failed: "
                          f"{res.get('error') or (res.get('stdout') or '')[:300]}")
        # The pre-merge head is kept so the caller can roll the committed merge
        # back if its post-merge verification (or push) fails.
        sha = self.git_runner("rev-parse HEAD", str(self.repo))
        merged = (sha.get("stdout") or "").strip()
        return merged, ""

    def abort_merge(self) -> None:
        """
        Undo a merge: an in-progress merge is aborted; an already-committed
        merge is hard-reset to the pre-merge head. The branch is untouched.
        """
        if self._pre_merge_sha:
            self.git_runner(f"reset --hard {q(self._pre_merge_sha)}",
                            str(self.repo))
            self._pre_merge_sha = None
        else:
            self.git_runner("merge --abort", str(self.repo))

    def push(self) -> str:
        """Push the merged main branch to its remote; error string or ''."""
        res = self.git_runner("push", str(self.repo))
        if res.get("exit_code") not in (0, None):
            return (f"push failed: "
                    f"{res.get('error') or (res.get('stdout') or '')[:300]}")
        return ""

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
