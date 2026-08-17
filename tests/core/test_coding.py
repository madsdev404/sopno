"""
tests/core/test_coding.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the autonomous coding agent (sopno/core/coding.py): the ReAct loop,
worktree isolation, gated writes, checkpoint commits, verification cadence and
the terminal-state machine. The LLM is scripted and git runs for real in a temp
repo, so the whole harness is exercised without a network or model.
"""

import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.core.coding import CodingAgent

RECIPE = [{"command": "python -c 'pass'", "kind": "smoke"}]


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", "-C", str(cwd)] + args, check=True,
                   capture_output=True)


def init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "agent@test.dev"], repo)
    _git(["config", "user.name", "Sopno Test"], repo)
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)
    return repo


def git_runner():
    def runner(args: str, cwd: str) -> dict:
        proc = subprocess.run(["git", "-C", str(cwd)] + shlex.split(args),
                              capture_output=True, text=True)
        return {
            "stdout": proc.stdout,
            "exit_code": proc.returncode,
            "completed": True,
            "state": "idle",
            "blocked": None,
            "error": None,
        }
    return runner


def verify_runner(exit_code: int = 0, blocked: str | None = None):
    def runner(command: str) -> dict:
        return {
            "stdout": "ok" if exit_code == 0 else "",
            "exit_code": exit_code,
            "completed": True,
            "state": "idle",
            "blocked": blocked,
            "error": None,
        }
    return runner


def verify_main_red(command: str) -> dict:
    """Green inside the worktree, red on the main checkout (for auto-merge)."""
    ok = "worktrees" in command
    return {
        "stdout": "ok" if ok else "",
        "exit_code": 0 if ok else 1,
        "completed": True,
        "state": "idle",
        "blocked": None,
        "error": None,
    }


def scripted(responses: list[dict]):
    it = iter(responses)

    def step(messages: list[dict], tools: list | None) -> dict:
        return next(it)

    return step


def tool_call(name: str, **args) -> dict:
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def final(text: str) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": []}


class CodingAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = init_repo(self.root)
        # The temp repo lives outside the project root; let the file gate see it.
        self._old_roots = list(settings.file_allowed_write)
        settings.file_allowed_write = [str(self.root)]
        self._old_stall = settings.coding_stall_rounds
        self._old_max_turns = settings.coding_max_turns
        self._old_approval = settings.coding_approval_mode
        self._old_red = settings.coding_require_red_test
        self._old_push = settings.coding_push_enabled

    def tearDown(self) -> None:
        settings.file_allowed_write = self._old_roots
        settings.coding_stall_rounds = self._old_stall
        settings.coding_max_turns = self._old_max_turns
        settings.coding_approval_mode = self._old_approval
        settings.coding_require_red_test = self._old_red
        settings.coding_push_enabled = self._old_push
        self._tmp.cleanup()

    def agent(self, responses: list[dict], verify=0, **kwargs) -> CodingAgent:
        if "verify_runner" not in kwargs:
            kwargs["verify_runner"] = verify_runner(verify)
        return CodingAgent(
            repo=self.repo,
            worktree_dir=self.root / "worktrees",
            llm_step=scripted(responses),
            git_runner=git_runner(),
            **kwargs,
        )

    def test_success_loop(self) -> None:
        responses = [
            tool_call("write_file", path="sopno/hello.py",
                      content="def add(a, b):\n    return a + b\n"),
            final("Implemented add() and the recipe is green."),
        ]
        result = self.agent(responses).run({
            "goal": "Add a small helper module.",
            "paths_allowed": ["sopno"],
            "verify_recipe": RECIPE,
        })

        self.assertEqual(result["state"], "success")
        self.assertEqual(result["changes"], 1)
        self.assertEqual(len(result["commits"]), 1)
        self.assertIn("sopno/", result["branch"])
        # The worktree branch holds the change; the main checkout is untouched.
        self.assertFalse((self.repo / "sopno" / "hello.py").exists())
        worktree = Path(result["worktree"])
        self.assertTrue((worktree / "sopno" / "hello.py").is_file())
        self.assertTrue((worktree / "PLAN.md").is_file())
        self.assertTrue((worktree / "progress.md").is_file())
        self.assertTrue((worktree / "SUMMARY.md").is_file())

    def test_no_op(self) -> None:
        result = self.agent([final("Nothing to do — the code is already correct.")]).run({
            "goal": "Confirm the code is fine.",
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "no_op")
        self.assertEqual(result["changes"], 0)
        self.assertEqual(result["commits"], [])

    def test_blocked_by_protected_file(self) -> None:
        responses = [
            tool_call("write_file", path="PLAN.md", content="hax"),
            final("I edited the plan."),
        ]
        result = self.agent(responses).run({
            "goal": "Trick the agent.",
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "blocked")
        self.assertIn("protected", result["reason"])

    def test_blocked_by_scope(self) -> None:
        responses = [tool_call("write_file", path="secret.txt", content="x")]
        result = self.agent(responses).run({
            "goal": "Write outside the allowed scope.",
            "paths_allowed": ["sopno"],
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "blocked")
        self.assertIn("paths_allowed", result["reason"])

    def test_blocked_when_verification_fails(self) -> None:
        responses = [
            tool_call("write_file", path="sopno/a.py", content="x = 1\n"),
            final("Done."),
        ]
        result = self.agent(responses, verify=1).run({
            "goal": "Change something but verification is red.",
            "paths_allowed": ["sopno"],
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "blocked")
        self.assertIn("verification", result["reason"])

    def test_exhausted_turn_budget(self) -> None:
        settings.coding_max_turns = 0
        result = self.agent([final("never reached")]).run({
            "goal": "A task",
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "exhausted")

    def test_stalled_no_progress(self) -> None:
        settings.coding_stall_rounds = 2
        responses = [tool_call("get_current_time")] * 3
        result = self.agent(responses).run({
            "goal": "Spin without changing anything.",
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "stalled")

    def test_llm_step_failure_is_not_success(self) -> None:
        def boom(messages, tools):
            raise RuntimeError("model down")

        agent = CodingAgent(
            repo=self.repo,
            worktree_dir=self.root / "worktrees",
            llm_step=boom,
            git_runner=git_runner(),
            verify_runner=verify_runner(),
        )
        result = agent.run({"goal": "A task", "verify_recipe": RECIPE})
        self.assertEqual(result["state"], "blocked")
        self.assertIn("model down", result["reason"])

    def test_unknown_tool_refused_harmlessly(self) -> None:
        responses = [
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "rm_entire_disk",
                                          "arguments": {}}}]},
            final("done"),
        ]
        result = self.agent(responses).run({"goal": "A task", "verify_recipe": RECIPE})
        # The refusal is an observation (never executed), nothing changed.
        self.assertEqual(result["state"], "no_op")
        self.assertEqual(result["changes"], 0)
        self.assertFalse((self.repo / "sopno" / "hello.py").exists())

    def test_resume_reuses_the_branch(self) -> None:
        from sopno.core.agents.session import AgentSessionStore

        store = AgentSessionStore(tempfile.mkstemp(suffix=".db")[1])
        agent_id = store.create("coder", "Add a helper", kind="coding")
        try:
            first = CodingAgent(
                repo=self.repo, worktree_dir=self.root / "worktrees",
                llm_step=scripted([
                    tool_call("write_file", path="sopno/h.py", content="x = 1\n"),
                    final("First step done."),
                ]),
                git_runner=git_runner(), verify_runner=verify_runner(),
                store=store, session_id=agent_id,
            ).run({"goal": "Add a helper.", "paths_allowed": ["sopno"],
                   "verify_recipe": RECIPE})
            self.assertEqual(first["state"], "success")

            # A later run on the same session reattaches to the branch instead
            # of starting a fresh one — the checkpoint survives.
            second = CodingAgent(
                repo=self.repo, worktree_dir=self.root / "worktrees",
                llm_step=scripted([final("Continuing — now it is done.")]),
                git_runner=git_runner(), verify_runner=verify_runner(),
                store=store, session_id=agent_id,
            ).run({"goal": "Add a helper.", "paths_allowed": ["sopno"],
                   "verify_recipe": RECIPE})
            self.assertEqual(second["branch"], first["branch"])
            self.assertTrue(
                (Path(second["worktree"]) / "sopno" / "h.py").is_file()
            )
        finally:
            store.close()

    def test_crash_resume_picks_up_from_last_checkpoint(self) -> None:
        from sopno.core.agents.session import AgentSessionStore

        store = AgentSessionStore(tempfile.mkstemp(suffix=".db")[1])
        agent_id = store.create("crasher", "Add files", kind="coding")
        try:
            # First run: write one file, then crash on the second LLM step.
            def boom_on_second(messages, tools):
                if not hasattr(boom_on_second, "_calls"):
                    boom_on_second._calls = 0
                boom_on_second._calls += 1
                if boom_on_second._calls == 1:
                    return tool_call("write_file", path="sopno/a.py",
                                     content="a = 1\n")
                raise RuntimeError("mid-run crash")

            crash_result = CodingAgent(
                repo=self.repo, worktree_dir=self.root / "worktrees",
                llm_step=boom_on_second,
                git_runner=git_runner(), verify_runner=verify_runner(),
                store=store, session_id=agent_id,
            ).run({"goal": "Add files.", "paths_allowed": ["sopno"],
                   "verify_recipe": RECIPE})
            # The coding agent catches the exception and reports blocked.
            self.assertEqual(crash_result["state"], "blocked")
            self.assertIn("mid-run crash", crash_result["reason"])
            branch = crash_result["branch"]
            self.assertTrue(branch)
            # The first file was committed before the crash.
            self.assertTrue(len(crash_result["commits"]) >= 1)

            # Resume: a fresh run on the same session reattaches to the branch,
            # sees the existing file from the checkpoint, and continues.
            second = CodingAgent(
                repo=self.repo, worktree_dir=self.root / "worktrees",
                llm_step=scripted([
                    tool_call("write_file", path="sopno/b.py",
                              content="b = 2\n"),
                    final("Continued after crash."),
                ]),
                git_runner=git_runner(), verify_runner=verify_runner(),
                store=store, session_id=agent_id,
            ).run({"goal": "Add files.", "paths_allowed": ["sopno"],
                   "verify_recipe": RECIPE})
            self.assertEqual(second["state"], "success")
            self.assertEqual(second["branch"], branch)
            wt = Path(second["worktree"])
            # Both files survive — the pre-crash checkpoint was preserved.
            self.assertTrue((wt / "sopno" / "a.py").is_file())
            self.assertTrue((wt / "sopno" / "b.py").is_file())
        finally:
            store.close()

    # ── Step 4: escalation + approval modes ──────────────────────────────

    def test_escalate_in_review_required_blocks(self) -> None:
        settings.coding_approval_mode = "review_required"
        responses = [
            tool_call("escalate", reason="ambiguous spec",
                      question="Which approach should I take?"),
            final("I should have asked."),
        ]
        result = self.agent(responses).run({
            "goal": "Implement the feature.",
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "blocked")
        self.assertIn("Which approach", result["reason"])

    def test_escalate_in_auto_merge_mode_records_and_continues(self) -> None:
        settings.coding_approval_mode = "auto_merge_guardrailed"
        settings.coding_require_red_test = False
        responses = [
            tool_call("escalate", reason="missing info",
                      question="Default port or 8080?"),
            tool_call("write_file", path="sopno/hello.py",
                      content="def add(a, b):\n    return a + b\n"),
            final("Done."),
        ]
        result = self.agent(responses, verify=0).run({
            "goal": "Add a small helper module.",
            "paths_allowed": ["sopno"],
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "success")
        self.assertEqual(len(result["escalations"]), 1)
        self.assertEqual(result["escalations"][0]["question"],
                         "Default port or 8080?")
        self.assertTrue(result["merged"])

    def test_require_red_test_baseline_recorded(self) -> None:
        settings.coding_require_red_test = True
        responses = [
            tool_call("write_file", path="sopno/a.py", content="x = 1\n"),
            final("Done."),
        ]
        result = self.agent(responses, verify=0).run({
            "goal": "Change something.",
            "paths_allowed": ["sopno"],
            "verify_recipe": RECIPE,
        })
        self.assertIs(result["baseline_green"], True)

        red = self.agent(
            [tool_call("write_file", path="sopno/b.py", content="y = 1\n"),
             final("Done.")],
            verify=1,
        ).run({"goal": "Change something else.", "paths_allowed": ["sopno"],
               "verify_recipe": RECIPE})
        self.assertIs(red["baseline_green"], False)

    # ── Step 5: sub-agent delegation + review ────────────────────────────

    def test_delegate_returns_digest(self) -> None:
        calls: list[tuple] = []

        def delegate_fn(agent, task):
            calls.append((agent, task))
            return "digest: the search tool lives in sopno/tools/registry.py"

        responses = [
            tool_call("delegate", agent="researcher",
                      task="Where is the tool registry?"),
            final("Delegated."),
        ]
        result = self.agent(responses, delegate_fn=delegate_fn).run({
            "goal": "A task.",
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "no_op")
        self.assertEqual(calls, [("researcher", "Where is the tool registry?")])

    def test_review_step_gates_success_when_blocked(self) -> None:
        review_recipe = RECIPE + [
            {"command": "python -c 'pass'", "kind": "review"},
        ]
        responses = [
            tool_call("write_file", path="sopno/c.py", content="z = 1\n"),
            final("Done."),
        ]
        result = self.agent(
            responses,
            review_runner=lambda diff: {"ok": False, "issues": "shipping is broken"},
        ).run({
            "goal": "Change something with a review gate.",
            "paths_allowed": ["sopno"],
            "verify_recipe": review_recipe,
        })
        self.assertEqual(result["state"], "blocked")
        self.assertIn("BLOCKED", result["reason"])
        self.assertIsNotNone(result["review"])

    def test_review_approves_when_clean(self) -> None:
        review_recipe = RECIPE + [
            {"command": "python -c 'pass'", "kind": "review"},
        ]
        responses = [
            tool_call("write_file", path="sopno/d.py", content="w = 1\n"),
            final("Done."),
        ]
        result = self.agent(
            responses,
            review_runner=lambda diff: {"ok": True, "issues": "looks good"},
        ).run({
            "goal": "Change something with a review gate.",
            "paths_allowed": ["sopno"],
            "verify_recipe": review_recipe,
        })
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["review"]["ok"], True)

    # ── Step 7: guardrailed auto-merge ───────────────────────────────────

    def test_auto_merge_guardrailed_merges_into_main(self) -> None:
        settings.coding_approval_mode = "auto_merge_guardrailed"
        settings.coding_require_red_test = False
        responses = [
            tool_call("write_file", path="sopno/hello.py",
                      content="def add(a, b):\n    return a + b\n"),
            final("Implemented and verified."),
        ]
        result = self.agent(
            responses,
            verify=0,
            review_runner=lambda diff: {"ok": True, "issues": "approved"},
        ).run({
            "goal": "Add a small helper module.",
            "paths_allowed": ["sopno"],
            "verify_recipe": RECIPE,
        })
        self.assertEqual(result["state"], "success")
        self.assertTrue(result["merged"])
        self.assertTrue(result["merged_sha"])
        self.assertIn("auto-merged", result["reason"])
        # The main checkout now holds the change (and the worktree branch does).
        self.assertTrue((self.repo / "sopno" / "hello.py").is_file())

    def test_auto_merge_aborts_when_merged_tree_red(self) -> None:
        settings.coding_approval_mode = "auto_merge_guardrailed"
        settings.coding_require_red_test = False
        responses = [
            tool_call("write_file", path="sopno/boom.py", content="boom = 1\n"),
            final("Done."),
        ]
        result = self.agent(
            responses,
            verify_runner=verify_main_red,
            review_runner=lambda diff: {"ok": True, "issues": "approved"},
        ).run({
            "goal": "Change something.",
            "paths_allowed": ["sopno"],
            "verify_recipe": RECIPE,
        })
        # The branch was green but the merged main tree failed re-verification,
        # so the merge was rolled back and the run reports blocked.
        self.assertEqual(result["state"], "blocked")
        self.assertIn("auto-merge aborted", result["reason"])
        self.assertFalse(result["merged"])
        self.assertFalse((self.repo / "sopno" / "boom.py").exists())

    # ── Step 7: unattended batch ─────────────────────────────────────────

    def test_run_batch_runs_each_ticket_freshly(self) -> None:
        from sopno.core.coding import run_coding_batch

        pool = iter([
            tool_call("write_file", path="sopno/a.py", content="a = 1\n"),
            final("A done."),
            tool_call("write_file", path="sopno/b.py", content="b = 1\n"),
            final("B done."),
        ])
        results = run_coding_batch(
            [
                {"goal": "Ticket A", "paths_allowed": ["sopno"],
                 "verify_recipe": RECIPE},
                {"goal": "Ticket B", "paths_allowed": ["sopno"],
                 "verify_recipe": RECIPE},
            ],
            repo=self.repo,
            worktree_dir=self.root / "worktrees",
            llm_step=lambda messages, tools: next(pool),
            git_runner=git_runner(),
            verify_runner=verify_runner(),
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["state"], "success")
        self.assertEqual(results[1]["state"], "success")
        self.assertNotEqual(results[0]["branch"], results[1]["branch"])


if __name__ == "__main__":
    unittest.main()
