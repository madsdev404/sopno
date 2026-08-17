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
        delegate_fn: Optional[Callable[[str, str], str]] = None,
        review_runner: Optional[Callable[[str], dict]] = None,
        store=None,
        session_id: Optional[int] = None,
    ) -> None:
        self.repo = Path(repo) if repo else settings.project_root
        self.worktree_dir = Path(worktree_dir) if worktree_dir else settings.coding_worktree_dir
        self.llm_step = llm_step or self._default_llm_step
        self.git_runner = git_runner or self._default_git_runner
        self.verify_runner = verify_runner or self._default_verify_runner
        self.delegate_fn = delegate_fn or self._default_delegate_fn
        self.review_runner = review_runner or self._default_review_runner
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
        # Step 4: escalation record (populated in auto_merge_guardrailed /
        # unattended modes) and step 7: merge outcome.
        self.escalations: list[dict] = []
        self.review_result: Optional[dict] = None
        self.review_used = False
        self.merged = False
        self.merged_sha: Optional[str] = None
        self.baseline_green: Optional[bool] = None

    # ── Injection points (defaults) ──────────────────────────────────────────

    def _default_llm_step(self, messages: list[dict], tools: Optional[list]) -> dict:
        response = llm_chat(messages, tools=tools or None)
        return message_as_dict(response["message"])

    def _default_git_runner(self, args: str, cwd: str) -> dict:
        return _term._run_command_raw(f"git -C {q(cwd)} {args}")

    def _default_verify_runner(self, command: str) -> dict:
        return _term._run_command_raw(command, timeout=120)

    def _default_delegate_fn(self, agent: str, task: str) -> str:
        """Step 5: run a focused sub-agent and return only its digest."""
        from sopno.core.subagents import run_subagent
        out = run_subagent(agent, task)
        return (out or "")[:2000]

    def _default_review_runner(self, diff_summary: str) -> dict:
        """Step 5: ask the reviewer sub-agent (a different role) for a verdict."""
        from sopno.core.subagents import run_subagent
        prompt = (
            "Review this diff. Judge correctness, security, and scope. Reply "
            "with exactly one line starting APPROVED or BLOCKED, then a short "
            "reason.\n\nDIFF:\n"
            + (diff_summary or "(empty diff)")[:4000]
        )
        text = (run_subagent("reviewer", prompt) or "").strip()
        ok = not text.upper().startswith("BLOCKED")
        return {"ok": ok, "issues": text[:1000]}

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
            "escalations": list(self.escalations),
            "merged": self.merged,
            "merged_sha": self.merged_sha,
            "baseline_green": self.baseline_green,
            "review": dict(self.review_result) if self.review_result else None,
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
            self.dispatcher = ToolDispatcher(
                self.repo, wt.worktree, paths_allowed,
                delegate_fn=self.delegate_fn,
            )
            self.verifier = Verifier(wt.worktree, self.verify_runner, recipe)
            self._save_coding_record(wt.branch, wt.base_sha)

            # Step 4: red/green baseline — establish whether a failing test
            # already exists before any change. When the baseline is green the
            # agent gets an advisory RED-FIRST note (never a hard block).
            if settings.coding_require_red_test:
                self.verifier.run()
                self.baseline_green = self.verifier.green()
                self._log_action(
                    "verify",
                    "baseline: " + ("green" if self.baseline_green else "red"),
                )

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
            if self.baseline_green:
                messages.append({
                    "role": "user",
                    "content": ("RED-FIRST note: the verification recipe is "
                                "green on the base commit. If this ticket "
                                "implies a fix, write a failing test (red) "
                                "first, then make it pass."),
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
                    if name == "escalate":
                        result = self._escalate(args)
                        messages.append({"role": "tool", "content": result})
                        self._log_action(
                            "action",
                            f"escalate({json.dumps(args)[:500]}) -> {result[:200]}",
                        )
                        if self.blocked_reason:
                            break
                        continue
                    if name == "run_review":
                        result = self._run_review()
                        messages.append({"role": "tool", "content": result})
                        self._log_action("action", f"run_review() -> {result[:200]}")
                        continue
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
                        "the verification recipe did not pass; the work is on "
                        "the branch for review")
                else:
                    # Step 5/7: optional review step, then the approval gate.
                    mode = settings.coding_approval_mode
                    review_needed = (
                        mode == "auto_merge_guardrailed"
                        or any(step.get("kind") == "review" for step in recipe)
                    )
                    if review_needed and not self.review_used:
                        self._run_review()
                    if self.review_result is not None and not self.review_result.get("ok"):
                        state, reason = "blocked", (
                            "reviewer BLOCKED the diff: "
                            f"{self.review_result.get('issues', '')[:300]}")
                    elif mode == "auto_merge_guardrailed":
                        merged, err = self._auto_merge()
                        if err:
                            state, reason = "blocked", err
                        else:
                            state, reason = "success", (
                                f"goal met, verification green, and branch "
                                f"auto-merged as {merged[:12]}")
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
            f"- Turns: {self.turns}\n"
        )
        if self.merged and self.merged_sha:
            summary += f"- Auto-merged into main as {self.merged_sha[:12]}\n"
        summary += "\n"
        if self.escalations:
            summary += "## Escalations\n"
            summary += "\n".join(
                f"- Q: {e['question']}" + (f" (reason: {e['reason']})" if e["reason"] else "")
                for e in self.escalations
            ) + "\n\n"
        if self.review_result is not None:
            verdict = "APPROVED" if self.review_result.get("ok") else "BLOCKED"
            summary += f"## Review: {verdict}\n{self.review_result.get('issues', '')}\n\n"
        if self.final_text:
            summary += f"## Agent summary\n\n{self.final_text}\n"
        if not self.merged:
            summary += "\nReview and merge this branch at your convenience.\n"
        self.worktrees.write_doc("SUMMARY.md", summary)

    # ── Step 4: escalation ───────────────────────────────────────────────────

    def _escalate(self, args: dict) -> str:
        """Route an escalate() call per the approval mode."""
        reason = (args.get("reason") or "").strip()
        question = (args.get("question") or "").strip()
        if not question:
            return "escalate needs a 'question' to ask a human."
        mode = settings.coding_approval_mode
        if mode == "review_required":
            self.blocked_reason = f"escalated to human: {question[:300]}"
            return f"[Escalated to a human — run paused] {question}"
        self.escalations.append({
            "reason": reason[:300], "question": question[:500],
            "turn": self.turns,
        })
        self._log_action("message", f"escalation: {question[:200]}")
        return f"[Escalation recorded for later review] {question}"

    # ── Step 5: sub-agent review ─────────────────────────────────────────────

    def _diff_summary(self) -> str:
        assert self.worktrees is not None and self.worktrees.worktree is not None
        if not self.worktrees.commits:
            return "(no commits yet)"
        res = self.git_runner(
            f"--no-pager diff {q(self.worktrees.base_sha)}...HEAD --stat",
            str(self.worktrees.worktree),
        )
        return (res.get("stdout") or "").strip() or "(no changes)"

    def _run_review(self) -> str:
        """Ask the reviewer sub-agent to judge the current diff."""
        try:
            result = dict(self.review_runner(self._diff_summary()) or {})
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "issues": f"review failed: {e}"}
        self.review_used = True
        self.review_result = result
        verdict = "APPROVED" if result.get("ok") else "BLOCKED"
        return f"Review: {verdict} — {str(result.get('issues', ''))[:500]}"

    # ── Step 7: guardrailed auto-merge ───────────────────────────────────────

    def _auto_merge(self) -> tuple[Optional[str], str]:
        """
        Merge the branch into the main checkout with three guardrails: the
        branch must be green, the merge must be clean, and the merged main
        tree must re-verify green (otherwise the merge is aborted). Git push /
        remote actions stay off unless ``coding_push_enabled``.
        """
        assert self.worktrees is not None and self.verifier is not None
        if not self.worktrees.commits:
            return None, "nothing to merge — the run made no commits"
        # Guardrail 1: the branch itself must be green.
        self.verifier.run()
        if not self.verifier.green():
            return None, "auto-merge aborted: verification is not green"
        # Guardrail 2: clean merge; abort and report on any conflict/error.
        merged, err = self.worktrees.merge_back()
        if err:
            return None, err
        # Guardrail 3: re-verify the merged main tree; abort on red.
        merged_verifier = Verifier(self.repo, self.verify_runner,
                                   self.verifier.recipe)
        merged_verifier.run()
        if not merged_verifier.green():
            self.worktrees.abort_merge()
            return None, ("auto-merge aborted: the merged main tree failed "
                          "verification; the branch is intact")
        if settings.coding_push_enabled:
            push_err = self.worktrees.push()
            if push_err:
                self.worktrees.abort_merge()
                return None, push_err
        self.merged = True
        self.merged_sha = merged
        return merged, ""
