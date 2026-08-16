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

    def tearDown(self) -> None:
        settings.file_allowed_write = self._old_roots
        settings.coding_stall_rounds = self._old_stall
        settings.coding_max_turns = self._old_max_turns
        self._tmp.cleanup()

    def agent(self, responses: list[dict], verify=0) -> CodingAgent:
        return CodingAgent(
            repo=self.repo,
            worktree_dir=self.root / "worktrees",
            llm_step=scripted(responses),
            git_runner=git_runner(),
            verify_runner=verify_runner(verify),
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


if __name__ == "__main__":
    unittest.main()
