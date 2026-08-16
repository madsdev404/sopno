"""
sopno/core/coding/agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
The coding-agent loop (autonomous-coding.md).

``CodingAgent.run(task_spec)`` drives INGEST → PLAN → ACT → OBSERVE → REFLECT →
DECIDE → VERIFY → SUBMIT against a real repository in an isolated worktree,
then leaves the finished branch for human review and merge. It is deliberately
thin: the tool safety gates live in ``tools.py``, the git lifecycle in
``worktree.py``, verification in ``verify.py``, and prompts in ``prompts.py``.

Everything is injectable (``llm_step`` / ``git_runner`` / ``verify_runner``) so
unit tests script the whole loop without a real LLM or shell.

Terminal states: ``success`` · ``no_op`` · ``blocked`` · ``stalled`` ·
``exhausted``. An error is never recorded as a win.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from sopno.config.settings import settings
from sopno.llm.client import chat as llm_chat, message_as_dict
from sopno.tools.builtins.dev import terminal as _term

from sopno.core.coding.prompts import recitation, system_prompt, task_prompt
from sopno.core.coding.tools import (CHANGE_TOOLS, TERMINAL_TOOLS,
                                     ToolDispatcher, tools_schema)
from sopno.core.coding.verify import Verifier
from sopno.core.coding.worktree import WorktreeSession
from sopno.core.coding.util import q

TERMINAL_STATES = ("success", "no_op", "blocked", "stalled", "exhausted")

LlmStep = Callable[[list[dict], Optional[list]], dict]


class CodingAgent:
    """
    Run the autonomous-coding loop on one ticket, in an isolated worktree.

    Constructor args are the injection points for tests (and the future daemon
    runtime): the loop itself never calls the LLM, git, or verification
    machinery directly.
    """

    def __init__(
        self,
        *,
        repo: Optional[Path | str] = None,
        worktree_dir: Optional[Path | str] = None,
        llm_step: Optional[LlmStep] = None,
        git_runner: Optional[Callable[[str, str], dict]] = None,
        verify_runner: Optional[Callable[[str], dict]] = None,
        store=None,
        session_id: Optional[int] = None,
    ) -> None:
        self.repo = Path(repo) if repo else settings.project_root
        self.worktree_dir = Path(worktree_dir) if worktree_dir else settings.coding_worktree_dir
        self.llm_step = llm_step or self._default_llm_step
        self.git_runner = git_runner or self._default_git_runner
        self.verify_runner = verify_runner or self._default_verify_runner
        self.store = store
        self.session_id = session_id

        # Per-run state (fresh for every ``run`` call).
        self.worktrees: Optional[WorktreeSession] = None
        self.dispatcher: Optional[ToolDispatcher] = None
        self.verifier: Optional[Verifier] = None
        self.turns = 0
        self.changes = 0
        self.blocked_reason: Optional[str] = None
        self.final_text: Optional[str] = None
        self.started_at = 0.0

    # ── Injection points (defaults) ──────────────────────────────────────────

    def _default_llm_step(self, messages: list[dict], tools: Optional[list]) -> dict:
        response = llm_chat(messages, tools=tools or None)
        return message_as_dict(response["message"])

    def _default_git_runner(self, args: str, cwd: str) -> dict:
        return _term._run_command_raw(f"git -C {q(cwd)} {args}")

    def _default_verify_runner(self, command: str) -> dict:
        return _term._run_command_raw(command, timeout=120)

    # ── Budgets ───────────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        return sum(len(str(m.get("content", ""))) for m in messages) // 4

    def _over_budget(self, messages: list[dict]) -> Optional[str]:
        if self.turns >= int(settings.coding_max_turns):
            return f"turn budget ({settings.coding_max_turns}) exceeded"
        if time.time() - self.started_at > int(settings.coding_max_wall_minutes) * 60:
            return f"wall-clock budget ({settings.coding_max_wall_minutes} min) exceeded"
        if self._estimate_tokens(messages) >= int(settings.coding_max_tokens):
            return f"token budget ({settings.coding_max_tokens}) exceeded"
        assert self.worktrees is not None
        if self.worktrees.diff_lines() >= int(settings.coding_max_diff_lines):
            return f"diff-size budget ({settings.coding_max_diff_lines} lines) exceeded"
        return None

    # ── Session/audit hook ────────────────────────────────────────────────────

    # Working-memory marker for the durable coding-worktree record, so a
    # background session can crash-resume onto the same branch (step 7).
    _CODING_MARKER = "[coding-worktree]"

    def _log_action(self, kind: str, detail: str) -> None:
        if self.store is not None and self.session_id is not None:
            try:
                self.store.log_action(self.session_id, kind, detail)
            except Exception:  # noqa: BLE001
                pass

    def _finish_session(self, state: str) -> None:
        if self.store is not None and self.session_id is not None:
            # ``blocked`` / ``stalled`` stay resumable (the work is on the
            # branch); only real exhaustion is terminal.
            target = {
                "success": "done", "no_op": "done", "blocked": "blocked",
                "stalled": "blocked", "exhausted": "dead",
            }.get(state, "dead")
            try:
                self.store.transition(self.session_id, target)
            except Exception:  # noqa: BLE001
                pass

    def _load_coding_record(self) -> Optional[dict]:
        """The stored ``{branch, base}`` of a previous run, if any."""
        if self.store is None or self.session_id is None:
            return None
        try:
            agent = self.store.get(self.session_id)
        except Exception:  # noqa: BLE001
            return None
        for entry in reversed(agent.get("working_memory") or []):
            text = entry.get("text", "")
            if text.startswith(self._CODING_MARKER):
                try:
                    return json.loads(text[len(self._CODING_MARKER):].strip())
                except ValueError:
                    return None
        return None

    def _save_coding_record(self, branch: str, base_sha: str) -> None:
        if self.store is not None and self.session_id is not None:
            try:
                self.store.append_memory(
                    self.session_id,
                    f"{self._CODING_MARKER} "
                    f"{json.dumps({'branch': branch, 'base': base_sha})}",
                )
            except Exception:  # noqa: BLE001
                pass

    # ── Result helpers ────────────────────────────────────────────────────────

    def _result(self, state: str, reason: str, diff_lines: int) -> dict[str, Any]:
        return {
            "state": state,
            "reason": reason,
            "branch": self.worktrees.branch if self.worktrees else "",
            "worktree": str(self.worktrees.worktree or "") if self.worktrees else "",
            "commits": self.worktrees.commits if self.worktrees else [],
            "turns": self.turns,
            "changes": self.changes,
            "diff_lines": diff_lines,
            "summary": self.final_text or "",
        }

    # ── The loop ──────────────────────────────────────────────────────────────

    def run(self, task_spec: str | dict) -> dict[str, Any]:
        """
        Run one ticket to a terminal state.

        Args:
            task_spec: A dict with ``goal`` (required), ``acceptance_criteria``
                (list), ``paths_allowed`` (list of repo-relative paths, empty =
                whole worktree), ``verify_recipe`` (list of ``{command, kind}``).
                A plain string is treated as just the goal.

        Returns:
            dict with keys: state, branch, worktree, commits, turns, changes,
            diff_lines, summary, reason.
        """
        spec = task_spec if isinstance(task_spec, dict) else {"goal": task_spec}
        spec = dict(spec or {})
        goal = (spec.get("goal") or "").strip()
        if not goal:
            return {"state": "blocked", "reason": "A ticket needs a goal.",
                    "branch": "", "worktree": "", "commits": [],
                    "turns": 0, "changes": 0, "diff_lines": 0, "summary": ""}

        paths_allowed = [str(p) for p in (spec.get("paths_allowed") or [])]
        recipe = Verifier.resolve_recipe(spec)
        self.started_at = time.time()

        try:
            # ── Setup: worktree + branch on an isolated checkout ────────
            wt = WorktreeSession(self.repo, self.worktree_dir, self.git_runner)
            record = self._load_coding_record()
            resumed = False
            branch = ""
            if record and record.get("branch"):
                branch = str(record["branch"])
                if wt.attach(branch, record.get("base")) == "":
                    resumed = True
            if not resumed:
                branch = wt.make_branch(goal)
                err = wt.setup(branch)
                if err:
                    return {"state": "blocked", "reason": err, "branch": branch,
                            "worktree": str(wt.worktree or ""), "commits": [],
                            "turns": 0, "changes": 0, "diff_lines": 0, "summary": ""}
            assert wt.worktree is not None

            self.worktrees = wt
            self.dispatcher = ToolDispatcher(self.repo, wt.worktree, paths_allowed)
            self.verifier = Verifier(wt.worktree, self.verify_runner, recipe)
            self._save_coding_record(wt.branch, wt.base_sha)

            self._write_plan(goal, spec)
            messages: list[dict] = [
                {"role": "system", "content": system_prompt(branch, self.repo)},
                {"role": "user", "content": task_prompt(goal, spec, paths_allowed, recipe)},
            ]
            if resumed:
                messages.append({
                    "role": "user",
                    "content": "This run resumes an existing branch. Read "
                               "PLAN.md and progress.md first, then continue "
                               "the work from the last checkpoint commit.",
                })
            self._log_action("transition", f"started run on branch {branch}"
                             + (" (resumed)" if resumed else ""))

            # ── ReAct loop ──────────────────────────────────────────────
            state, reason, turns_without_progress = "blocked", "", 0
            while True:
                if turns_without_progress >= int(settings.coding_stall_rounds):
                    state, reason = "stalled", (
                        f"no progress for {settings.coding_stall_rounds} "
                        "rounds (stagnation detector)")
                    break
                budget = self._over_budget(messages)
                if budget:
                    state, reason = "exhausted", budget
                    break
                if self.blocked_reason:
                    state, reason = "blocked", self.blocked_reason
                    break

                self.turns += 1
                messages.append({"role": "user",
                                 "content": self._recite() + "\n\nContinue."})
                try:
                    msg = self.llm_step(messages, tools_schema())
                except Exception as e:  # noqa: BLE001
                    state, reason = "blocked", f"LLM step failed: {e}"
                    break
                messages.append(msg)
                self._log_action("llm", f"turn {self.turns}")

                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    self.final_text = (msg.get("content") or "").strip()
                    break

                made_progress = False
                for call in tool_calls:
                    fn = call["function"] if isinstance(call, dict) else call.function
                    name = fn["name"] if isinstance(fn, dict) else fn.name
                    args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
                    if not isinstance(args, dict):
                        args = {}
                    result = self.dispatcher.dispatch(name, args)
                    messages.append({"role": "tool", "content": result})
                    self._log_action(
                        "action",
                        f"{name}({json.dumps(args)[:500]}) -> {result[:200]}",
                    )
                    if result.startswith("Blocked by safety policy"):
                        self.blocked_reason = result
                        continue
                    if name in CHANGE_TOOLS and result.startswith("Done"):
                        made_progress = True
                        self._after_change(name, result)

                turns_without_progress = 0 if made_progress else turns_without_progress + 1

            # ── Finalize ────────────────────────────────────────────────
            if self.final_text is not None:
                if self.blocked_reason:
                    state, reason = "blocked", self.blocked_reason
                elif self.changes == 0:
                    state, reason = "no_op", "nothing was changed"
                elif not self.verifier.green():
                    state, reason = "blocked", (
                        "the verification recipe did not pass; the work is on the "
                        "branch for review")
                else:
                    state, reason = "success", "goal met and verification green"

            diff_lines = wt.diff_lines()
            self._write_summary(goal, state, reason, diff_lines)
            if state == "success" and not wt.commits:
                wt.checkpoint("final state")
            self._log_action("transition", f"finished in state {state}: {reason}")
            self._finish_session(state)
            return self._result(state, reason, diff_lines)

        except Exception as e:  # noqa: BLE001
            diff = self.worktrees.diff_lines() if self.worktrees else 0
            return self._result("blocked", f"coding agent crashed: {e}", diff)

    # ── Loop helpers ──────────────────────────────────────────────────────────

    def _write_plan(self, goal: str, spec: dict) -> None:
        assert self.worktrees is not None
        steps = spec.get("steps") or []
        lines = [f"# Plan — {goal}", "", "## Steps"]
        if steps:
            lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        else:
            lines += [
                "1. Inspect the code (read/search).",
                "2. Make minimal changes in scope.",
                "3. Verify with the recipe; iterate until green.",
            ]
        self.worktrees.write_doc("PLAN.md", "\n".join(lines) + "\n")

    def _recite(self) -> str:
        assert self.worktrees is not None and self.worktrees.worktree is not None
        return recitation(self.worktrees.worktree, self.verifier.recipe,
                          self.verifier.last_results)

    def _after_change(self, name: str, result: str) -> None:
        assert self.worktrees is not None and self.verifier is not None
        self.changes += 1
        self.worktrees.append_doc(
            "progress.md", f"- T{self.turns}: {name} applied ({result[:120]})",
        )
        # Verification cadence: run the recipe after every change.
        self.verifier.run()
        for r in self.verifier.last_results:
            self.worktrees.append_doc(
                "progress.md",
                f"  - verify {r['kind']}: {'PASS' if r['ok'] else 'FAIL'}",
            )
        self._log_action("verify", json.dumps(self.verifier.last_results)[:500])
        sha = self.worktrees.checkpoint(
            f"after {name} (verify {'green' if self.verifier.green() else 'red'})"
        )
        if sha:
            self.worktrees.append_doc("progress.md", f"  - checkpoint commit {sha[:8]}")

    def _write_summary(self, goal: str, state: str, reason: str,
                       diff_lines: int) -> None:
        assert self.worktrees is not None
        summary = (
            f"# SUMMARY — {state}\n\n"
            f"Goal: {goal}\n"
            f"State: {state}\nReason: {reason}\n\n"
            f"- Branch: {self.worktrees.branch}\n"
            f"- Commits: {len(self.worktrees.commits)}\n"
            f"- Changes applied: {self.changes}\n"
            f"- Diff (added+removed lines): {diff_lines}\n"
            f"- Turns: {self.turns}\n\n"
        )
        if self.final_text:
            summary += f"## Agent summary\n\n{self.final_text}\n"
        summary += "\nReview and merge this branch at your convenience.\n"
        self.worktrees.write_doc("SUMMARY.md", summary)
