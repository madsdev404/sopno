"""
sopno/tools/builtins/git.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Git repository tools.

Every git command runs through the shared persistent terminal session
(``terminal._run_command_raw``), so the terminal blocklist and Sopno's own
privileges apply to everything and no new shell surface is created. Repos are
addressed explicitly with ``git -C <repo>`` so Sopno can work in any repository
the user points at — not just the session's current directory.

  git_status()                 → working-tree status + recent history
  git_log(limit)               → recent commits, one line each
  git_diff(staged)             → unstaged or staged diff (capped)
  git_branch(action, name)     → list / create / switch / delete branches
  git_add(paths)               → stage files (confirmed)
  git_commit(message, add_all) → create a commit (confirmed)
  git_stash(action, message)   → list / push / pop stashes
  git_commit_message()         → LLM-suggested commit message from the diff

Safety: staging, committing, branch deletion, and stash push/pop park a
pending action and need the user's Yes/No — the same gate the file tools use.
"""

from __future__ import annotations

import re
import shlex

from sopno.config.settings import settings
from sopno.tools.builtins.files import _awaiting_confirmation
from sopno.tools.builtins.terminal import _run_command_raw

_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9_.\/@-]+$")
# Shell metacharacters / control bytes rejected in interpolated values.
_UNSAFE = re.compile(r"[;&|`$<>()\"'\\\r\x00]")

# Strip ANSI colors / OSC control marks cleat or the shell inject into output.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[=>@]|\x1b.")


def _q(text: str) -> str:
    return shlex.quote(text)


def _clean(text: str) -> str:
    return _ANSI.sub("", text or "").replace("\x00", "").strip()


def _git_enabled() -> str:
    if not getattr(settings, "git_enabled", True):
        return "Git tools are disabled (git_enabled = false in config.json)."
    return ""


def _check_repo(repo: str) -> tuple[str, str]:
    """Normalize/validate the repo path. Returns (repo, error)."""
    repo = (repo or "").strip() or str(settings.project_root)
    if not repo.startswith("/"):
        return "", f"Invalid repo path '{repo}' — use an absolute path."
    if _UNSAFE.search(repo):
        return "", f"Invalid repo path '{repo}'."
    return repo, ""


def _run_git_raw(repo: str, args: str) -> dict:
    return _run_command_raw(f"git -C {_q(repo)} -c color.ui=false {args}")


def _git_text(res: dict, what: str = "git") -> str:
    """Render a git result dict; '' on success with no output."""
    if res.get("blocked"):
        return f"Blocked by safety policy — {res['blocked']}."
    if res.get("error"):
        return res["error"]
    out = (res.get("stdout") or "").strip()
    if res.get("exit_code") not in (0, None):
        return f"{what} failed (exit {res.get('exit_code')})." + (f"\n{out}" if out else "")
    return out


def _cap(text: str) -> str:
    """Cap output to the LLM-friendly diff budget, keeping the tail."""
    limit = max(1, int(getattr(settings, "git_max_diff_chars", 12000)))
    if len(text) <= limit:
        return text
    return "…(output truncated)…\n" + text[-limit:]


def _ok(res: dict) -> bool:
    return res.get("exit_code") == 0


# ── Read-only tools ──────────────────────────────────────────────────────────

def git_status(repo: str = "") -> str:
    """
    Show the working-tree status and recent commit history of a repo.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).

    Returns:
        The short status (branch, staged/unstaged/untracked files) plus the
        last 10 commits, or a reason it could not be read.
    """
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err
    res = _run_git_raw(repo, "--no-pager status --short --branch")
    status = _clean(_git_text(res, "git status"))
    if not _ok(res):
        return status
    res = _run_git_raw(repo, "--no-pager log --oneline -n 10")
    log = _clean(_git_text(res, "git log"))
    parts = [status or "(clean working tree)"]
    if log:
        parts.append("Recent commits:\n" + log)
    return _cap("\n\n".join(parts))


def git_log(repo: str = "", limit: int = 10) -> str:
    """
    Show recent commits, one line each.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).
        limit: Number of commits to show (1-50, default 10).

    Returns:
        One-line commit history, or a reason it could not be read.
    """
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err
    limit = max(1, min(int(limit or 10), 50))
    res = _run_git_raw(repo, f"--no-pager log --oneline -n {limit}")
    text = _clean(_git_text(res, "git log"))
    if not text and _ok(res):
        return "This repository has no commits yet."
    return _cap(text)


def git_diff(repo: str = "", staged: bool = False) -> str:
    """
    Show the working-tree diff, optionally only the staged changes.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).
        staged: True to show only staged (index) changes.

    Returns:
        The diff (capped), or a short message when there is nothing to show.
    """
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err
    area = "--staged" if staged else ""
    res = _run_git_raw(repo, f"--no-pager diff {area}".strip())
    text = _clean(_git_text(res, "git diff"))
    if not text and _ok(res):
        return "Nothing is staged yet — use git_add to stage changes." if staged \
            else "No unstaged changes to show."
    return _cap(text)


def git_commit_message(repo: str = "", staged: bool = True) -> str:
    """
    Ask the local LLM to draft a conventional commit message from the diff.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).
        staged: True (default) to use the staged diff, else the unstaged one.

    Returns:
        A suggested ``type(scope): subject`` message plus a short body.
        Read-only — nothing is staged or committed.
    """
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err
    area = "--staged" if staged else ""
    res = _run_git_raw(repo, f"--no-pager diff {area}".strip())
    text = _clean(_git_text(res, "git diff"))
    if not text and _ok(res):
        return ("Nothing is staged — run git_add first (or call with "
                "staged=false to use the working-tree diff).") if staged \
            else "There are no unstaged changes to summarize."
    if len(text) > 3500:
        text = text[:3500] + "\n…(diff truncated)…"

    from sopno.llm.client import single_reply

    system = (
        "You are a senior git expert. Given a git diff, produce a concise "
        "conventional commit message: one subject line of the form "
        "type(scope): summary (types: feat, fix, docs, style, refactor, perf, "
        "test, chore), then a short bulleted body explaining what changed and "
        "why. Output ONLY the commit message — no commentary, no code fences."
    )
    try:
        return single_reply([
            {"role": "system", "content": system},
            {"role": "user", "content": f"Git diff:\n\n{text}"},
        ])
    except Exception as e:
        return f"Could not generate a commit message ({e})."


# ── Branch tools ─────────────────────────────────────────────────────────────

def git_branch(repo: str = "", action: str = "list", name: str = "") -> str:
    """
    List, create, switch, or delete branches.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).
        action: 'list' (default), 'create', 'switch', or 'delete'.
        name: Branch name for create / switch / delete.

    Returns:
        The branch list, a confirmation, or a reason the action failed.
        Deleting a branch needs the user's Yes/No confirmation.
    """
    action = (action or "list").strip().lower()
    if action not in ("list", "create", "switch", "delete"):
        return f"Unknown branch action '{action}'. Use list, create, switch, or delete."
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err

    if action == "list":
        res = _run_git_raw(repo, "--no-pager branch -a")
        text = _clean(_git_text(res, "git branch"))
        if not text and _ok(res):
            return "No branches found."
        return _cap(text)

    name = (name or "").strip()
    if not _SAFE_BRANCH.fullmatch(name):
        return f"Invalid branch name '{name}'."

    if action == "create":
        res = _run_git_raw(repo, f"branch {_q(name)}")
        text = _clean(_git_text(res, "git branch"))
        if _ok(res):
            return f"Created branch '{name}'."
        return text

    if action == "switch":
        res = _run_git_raw(repo, f"checkout {_q(name)}")
        text = _clean(_git_text(res, "git checkout"))
        if _ok(res):
            return f"Switched to branch '{name}'."
        return text

    description = f"delete branch '{name}' in '{repo}'"

    def _do() -> str:
        res = _run_git_raw(repo, f"branch -d {_q(name)}")
        text = _clean(_git_text(res, "git branch"))
        if _ok(res):
            return f"Deleted branch '{name}'."
        return text

    return _awaiting_confirmation(description, _do)


# ── Staging / commit / stash (confirmed) ─────────────────────────────────────

def git_add(repo: str = "", paths: str = "") -> str:
    """
    Stage files for the next commit.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).
        paths: One or more space-separated paths (default '.', everything).

    Returns:
        A confirmation, or a reason the files could not be staged.
        Needs the user's Yes/No confirmation.
    """
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err
    paths = (paths or "").strip() or "."
    tokens = paths.split()
    for tok in tokens:
        if tok.startswith("-") or _UNSAFE.search(tok):
            return f"Invalid path '{tok}' in paths."
    safe = " ".join(_q(t) for t in tokens)

    description = f"stage {paths} in '{repo}'"

    def _do() -> str:
        res = _run_git_raw(repo, f"add -- {safe}")
        text = _clean(_git_text(res, "git add"))
        if _ok(res):
            return f"Staged {len(tokens)} path(s) in {repo}."
        return text

    return _awaiting_confirmation(description, _do)


def git_commit(repo: str = "", message: str = "", add_all: bool = False) -> str:
    """
    Create a commit with the given message.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).
        message: The commit message (use git_commit_message to draft one).
        add_all: Also stage all changes (git add -A) before committing.

    Returns:
        The commit output, or a reason the commit failed.
        Needs the user's Yes/No confirmation.
    """
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err
    message = (message or "").strip()
    if not message:
        return "A commit needs a message — use git_commit_message to draft one."
    if len(message) > 2000:
        return "Commit message is too long (max 2000 characters)."
    if _UNSAFE.search(message):
        return "Commit message contains invalid characters."
    first = message.splitlines()[0]
    if len(first) > 60:
        first = first[:60] + "…"

    description = f"create a commit in '{repo}' — '{first}'"
    if add_all:
        description += " (staging all changes first)"

    def _do() -> str:
        if add_all:
            res = _run_git_raw(repo, "add -A")
            if not _ok(res):
                return _clean(_git_text(res, "git add"))
        res = _run_git_raw(repo, f"commit -m {_q(message)}")
        text = _clean(_git_text(res, "git commit"))
        if _ok(res):
            return text or f"Committed to {repo}."
        return text

    return _awaiting_confirmation(description, _do)


def git_stash(repo: str = "", action: str = "list", message: str = "") -> str:
    """
    List, push, or pop stashes.

    Args:
        repo: Optional absolute path of the git repository (defaults to the
              project root).
        action: 'list' (default), 'push', or 'pop'.
        message: Optional note for a stash push.

    Returns:
        The stash list, a confirmation, or a reason the action failed.
        Push and pop need the user's Yes/No confirmation.
    """
    action = (action or "list").strip().lower()
    if action not in ("list", "push", "pop"):
        return f"Unknown stash action '{action}'. Use list, push, or pop."
    reason = _git_enabled()
    if reason:
        return reason
    repo, err = _check_repo(repo)
    if err:
        return err

    if action == "list":
        res = _run_git_raw(repo, "--no-pager stash list")
        text = _clean(_git_text(res, "git stash"))
        if not text and _ok(res):
            return "No stashes."
        return _cap(text)

    if action == "push":
        msg = (message or "").strip()
        if msg:
            if _UNSAFE.search(msg) or len(msg) > 500:
                return "Invalid stash message."
            args = f"push -m {_q(msg)}"
        else:
            args = "push"
        description = f"stash changes in '{repo}'"

        def _do() -> str:
            res = _run_git_raw(repo, f"stash {args}")
            text = _clean(_git_text(res, "git stash"))
            if _ok(res):
                return text or f"Changes stashed in {repo}."
            return text

        return _awaiting_confirmation(description, _do)

    description = f"restore the most recent stash in '{repo}'"

    def _do() -> str:
        res = _run_git_raw(repo, "stash pop")
        text = _clean(_git_text(res, "git stash"))
        if _ok(res):
            return text or f"Restored the stash in {repo}."
        return text

    return _awaiting_confirmation(description, _do)
