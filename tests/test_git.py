"""
tests/test_git.py
━━━━━━━━━━━━━━━━
Automated unit tests for the git repository tools.

Uses a fake ``_run_command_raw`` that executes the real git binary in a
temporary repository, so the full git CLI path is exercised without a
persistent terminal session.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sopno.config.settings import settings
from sopno.tools.builtins import files, git
from sopno.tools.builtins.git import (
    git_add,
    git_branch,
    git_commit,
    git_commit_message,
    git_diff,
    git_log,
    git_status,
    git_stash,
)


def _run(command: str, timeout=None) -> dict:
    try:
        proc = subprocess.run(
            command, shell=True, text=True, capture_output=True, timeout=timeout or 30
        )
        out = proc.stdout
        if not out and proc.stderr:
            out = proc.stderr
        return {
            "stdout": out,
            "exit_code": proc.returncode,
            "completed": True,
            "state": "idle",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "stdout": "",
            "exit_code": None,
            "completed": True,
            "state": "idle",
            "error": f"Terminal error: {e}",
        }


def _blocked(reason: str = "shutdown") -> dict:
    return {"stdout": "", "exit_code": None, "completed": True,
            "state": "idle", "blocked": reason}


def _error(msg: str = "Terminal error: boom") -> dict:
    return {"stdout": "", "exit_code": None, "completed": True,
            "state": "idle", "error": msg}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )


class GitTestCase(unittest.TestCase):
    """A real throwaway git repository (initialized, with one commit)."""

    def setUp(self) -> None:
        self._td = tempfile.mkdtemp(prefix="sopno-git-test-")
        self.repo = Path(self._td)
        self._saved = {
            "enabled": settings.git_enabled,
            "max_chars": settings.git_max_diff_chars,
        }
        settings.git_enabled = True
        settings.git_max_diff_chars = 12000
        files._PENDING_ACTION = None
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "sopno@test.local")
        _git(self.repo, "config", "user.name", "Sopno Test")
        (self.repo / "file.txt").write_text("hello\nworld\n", encoding="utf-8")
        _git(self.repo, "add", "file.txt")
        _git(self.repo, "commit", "-q", "-m", "feat: initial file")
        self._raw = patch.object(git, "_run_command_raw", side_effect=_run)
        self._raw.start()

    def tearDown(self) -> None:
        self._raw.stop()
        files._PENDING_ACTION = None
        settings.git_enabled = self._saved["enabled"]
        settings.git_max_diff_chars = self._saved["max_chars"]
        shutil.rmtree(self._td, ignore_errors=True)


# ── Read-only tools ──────────────────────────────────────────────────────────

class TestReadOnly(GitTestCase):
    def test_status_shows_branch_and_clean(self) -> None:
        out = git_status(str(self.repo))
        self.assertIn("main", out)
        self.assertIn("Recent commits:", out)
        self.assertIn("feat: initial file", out)

    def test_status_shows_changes(self) -> None:
        (self.repo / "file.txt").write_text("changed\n", encoding="utf-8")
        self.assertIn("M file.txt", git_status(str(self.repo)))

    def test_log_lists_commits(self) -> None:
        self.assertIn("feat: initial file", git_log(str(self.repo), limit=5))

    def test_log_clamps_limit(self) -> None:
        with patch.object(git, "_run_git_raw", return_value=_run("git log")) as raw:
            git_log(str(self.repo), limit=999)
        self.assertIn("-n 50", raw.call_args_list[0][0][1])

    def test_diff_unstaged(self) -> None:
        (self.repo / "file.txt").write_text("changed line\n", encoding="utf-8")
        out = git_diff(str(self.repo))
        self.assertIn("-hello", out)
        self.assertIn("+changed line", out)

    def test_diff_staged(self) -> None:
        (self.repo / "file.txt").write_text("staged change\n", encoding="utf-8")
        _git(self.repo, "add", "file.txt")
        self.assertIn("+staged change", git_diff(str(self.repo), staged=True))

    def test_diff_nothing_unstaged(self) -> None:
        self.assertIn("No unstaged changes", git_diff(str(self.repo)))

    def test_diff_nothing_staged(self) -> None:
        self.assertIn("Nothing is staged", git_diff(str(self.repo), staged=True))

    def test_not_a_repo(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="sopno-notrepo-"))
        try:
            out = git_status(str(other)).lower()
            self.assertTrue("failed" in out or "fatal" in out, out)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_relative_repo_rejected(self) -> None:
        self.assertIn("absolute path", git_status("relative/repo"))

    def test_disabled(self) -> None:
        settings.git_enabled = False
        self.assertIn("disabled", git_status(str(self.repo)))
        self.assertIn("disabled", git_log(str(self.repo)))


# ── Branches ─────────────────────────────────────────────────────────────────

class TestBranches(GitTestCase):
    def test_list(self) -> None:
        self.assertIn("main", git_branch(str(self.repo), "list"))

    def test_create_and_switch(self) -> None:
        self.assertIn("Created", git_branch(str(self.repo), "create", "feature-x"))
        self.assertIn("Switched", git_branch(str(self.repo), "switch", "feature-x"))
        out = git_branch(str(self.repo), "list")
        self.assertIn("feature-x", out)
        self.assertIn("*", out)

    def test_create_existing_fails(self) -> None:
        self.assertIn("failed", git_branch(str(self.repo), "create", "main").lower())

    def test_delete_needs_confirmation(self) -> None:
        git_branch(str(self.repo), "create", "temp-branch")
        out = git_branch(str(self.repo), "delete", "temp-branch")
        self.assertIn("permission", out)
        self.assertIsNotNone(files.pending_action())
        files._PENDING_ACTION = None

    def test_delete_after_yes(self) -> None:
        git_branch(str(self.repo), "create", "temp-branch")
        git_branch(str(self.repo), "delete", "temp-branch")
        pid = files.pending_action()["id"]
        self.assertIn("Deleted", files.resolve_pending(pid, "yes") or "")
        self.assertNotIn("temp-branch", git_branch(str(self.repo), "list"))

    def test_invalid_branch_name(self) -> None:
        self.assertIn("Invalid branch name",
                      git_branch(str(self.repo), "create", "bad;name"))
        self.assertIn("Invalid branch name",
                      git_branch(str(self.repo), "create", "has space"))

    def test_unknown_action(self) -> None:
        self.assertIn("Unknown branch action", git_branch(str(self.repo), "explode"))

    def test_switch_missing_fails(self) -> None:
        self.assertIn("failed", git_branch(str(self.repo), "switch", "ghost").lower())


# ── git_add ──────────────────────────────────────────────────────────────────

class TestGitAdd(GitTestCase):
    def test_add_requires_confirmation(self) -> None:
        (self.repo / "new.txt").write_text("x", encoding="utf-8")
        out = git_add(str(self.repo), "new.txt")
        self.assertIn("permission", out)
        self.assertIsNotNone(files.pending_action())

    def test_add_after_yes(self) -> None:
        (self.repo / "new.txt").write_text("x", encoding="utf-8")
        git_add(str(self.repo), "new.txt")
        pid = files.pending_action()["id"]
        self.assertIn("Staged", files.resolve_pending(pid, "yes") or "")
        self.assertIn("new.txt", git_diff(str(self.repo), staged=True))

    def test_add_all(self) -> None:
        (self.repo / "new.txt").write_text("x", encoding="utf-8")
        git_add(str(self.repo), ".")
        pid = files.pending_action()["id"]
        files.resolve_pending(pid, "yes")
        self.assertIn("new.txt", git_diff(str(self.repo), staged=True))

    def test_invalid_path_rejected(self) -> None:
        self.assertIn("Invalid path", git_add(str(self.repo), "x;y"))
        self.assertIsNone(files.pending_action())

    def test_missing_path_fails(self) -> None:
        git_add(str(self.repo), "ghost.txt")
        pid = files.pending_action()["id"]
        self.assertIn("failed", (files.resolve_pending(pid, "yes") or "").lower())


# ── git_commit ───────────────────────────────────────────────────────────────

class TestGitCommit(GitTestCase):
    def test_commit_requires_confirmation(self) -> None:
        (self.repo / "file.txt").write_text("v2\n", encoding="utf-8")
        out = git_commit(str(self.repo), message="fix: tweak file")
        self.assertIn("permission", out)
        self.assertIn("fix: tweak file", out)
        self.assertIsNotNone(files.pending_action())

    def test_commit_after_yes(self) -> None:
        (self.repo / "file.txt").write_text("v2\n", encoding="utf-8")
        _git(self.repo, "add", "file.txt")
        git_commit(str(self.repo), message="fix: tweak file")
        pid = files.pending_action()["id"]
        self.assertIn("fix: tweak file", files.resolve_pending(pid, "yes") or "")
        self.assertIn("fix: tweak file", git_log(str(self.repo), limit=3))

    def test_commit_with_add_all(self) -> None:
        (self.repo / "new.txt").write_text("x", encoding="utf-8")
        git_commit(str(self.repo), message="feat: add new", add_all=True)
        pid = files.pending_action()["id"]
        self.assertIn("feat: add new", files.resolve_pending(pid, "yes") or "")

    def test_commit_nothing_staged(self) -> None:
        git_commit(str(self.repo), message="fix: nothing")
        pid = files.pending_action()["id"]
        self.assertIn("failed", (files.resolve_pending(pid, "yes") or "").lower())

    def test_commit_no_message(self) -> None:
        self.assertIn("needs a message", git_commit(str(self.repo)))

    def test_commit_bad_message(self) -> None:
        self.assertIn("invalid characters", git_commit(str(self.repo), message="bad;msg"))

    def test_commit_confirm_no_cancels(self) -> None:
        (self.repo / "file.txt").write_text("v2\n", encoding="utf-8")
        _git(self.repo, "add", "file.txt")
        git_commit(str(self.repo), message="fix: nope")
        pid = files.pending_action()["id"]
        self.assertIn("Cancelled", files.resolve_pending(pid, "no") or "")
        self.assertNotIn("fix: nope", git_log(str(self.repo), limit=3))


# ── git_stash ────────────────────────────────────────────────────────────────

class TestGitStash(GitTestCase):
    def test_list_empty(self) -> None:
        self.assertIn("No stashes", git_stash(str(self.repo)))

    def test_push_needs_confirmation(self) -> None:
        (self.repo / "file.txt").write_text("dirty\n", encoding="utf-8")
        out = git_stash(str(self.repo), "push", "wip")
        self.assertIn("permission", out)
        self.assertIsNotNone(files.pending_action())

    def test_push_and_list_after_yes(self) -> None:
        (self.repo / "file.txt").write_text("dirty\n", encoding="utf-8")
        git_stash(str(self.repo), "push", "wip changes")
        pid = files.pending_action()["id"]
        self.assertIn("wip changes", files.resolve_pending(pid, "yes") or "")
        self.assertIn("wip changes", git_stash(str(self.repo), "list"))

    def test_pop_restores_after_yes(self) -> None:
        (self.repo / "file.txt").write_text("dirty\n", encoding="utf-8")
        git_stash(str(self.repo), "push")
        pid = files.pending_action()["id"]
        files.resolve_pending(pid, "yes")
        git_stash(str(self.repo), "pop")
        pid = files.pending_action()["id"]
        self.assertIsNotNone(pid)
        files.resolve_pending(pid, "yes")
        self.assertIn("dirty", (self.repo / "file.txt").read_text(encoding="utf-8"))
        self.assertIn("No stashes", git_stash(str(self.repo), "list"))

    def test_pop_without_stash_fails(self) -> None:
        git_stash(str(self.repo), "pop")
        pid = files.pending_action()["id"]
        self.assertIn("failed", (files.resolve_pending(pid, "yes") or "").lower())

    def test_unknown_action(self) -> None:
        self.assertIn("Unknown stash action", git_stash(str(self.repo), "drop"))


# ── git_commit_message ───────────────────────────────────────────────────────

class TestCommitMessage(GitTestCase):
    def test_no_diff_staged(self) -> None:
        self.assertIn("Nothing is staged", git_commit_message(str(self.repo)))

    def test_with_staged_diff(self) -> None:
        (self.repo / "file.txt").write_text("brand new\n", encoding="utf-8")
        _git(self.repo, "add", "file.txt")
        with patch("sopno.llm.client.single_reply",
                   return_value="feat: update file text"):
            self.assertEqual(git_commit_message(str(self.repo)),
                             "feat: update file text")

    def test_llm_error_degrades(self) -> None:
        (self.repo / "file.txt").write_text("brand new\n", encoding="utf-8")
        _git(self.repo, "add", "file.txt")
        with patch("sopno.llm.client.single_reply", side_effect=RuntimeError("down")):
            self.assertIn("Could not generate", git_commit_message(str(self.repo)))


# ── Blocked / error propagation ──────────────────────────────────────────────

class TestBlocked(GitTestCase):
    def test_blocked_propagates(self) -> None:
        with patch.object(git, "_run_command_raw", return_value=_blocked()):
            self.assertIn("Blocked by safety policy", git_status(str(self.repo)))
            self.assertIn("Blocked by safety policy", git_log(str(self.repo)))

    def test_error_propagates(self) -> None:
        with patch.object(git, "_run_command_raw", return_value=_error()):
            self.assertIn("Terminal error", git_status(str(self.repo)))


if __name__ == "__main__":
    unittest.main()
