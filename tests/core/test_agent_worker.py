"""
tests/core/test_agent_worker.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the AgentWorker loop (sopno/core/agents/worker.py): claiming jobs,
driving the ORIENT → DECIDE → ACT → OBSERVE loop to a terminal or parked state,
budgets, per-agent serialization, and the coding-task bridge.
"""

import tempfile
import time
import unittest

from sopno.config.settings import settings

from sopno.core.agents.queue import AgentQueue
from sopno.core.agents.session import AgentSessionStore
from sopno.core.agents.worker import AgentWorker, MANAGEMENT_TOOLS


def _temp_db() -> str:
    return tempfile.mkstemp(suffix=".db")[1]


def _tool_call(name: str = "get_current_time", args: dict | None = None) -> list:
    return [{
        "id": "call-1",
        "function": {"name": name, "arguments": args or {}},
    }]


def _tool_llm(tool_calls: list):
    """llm_step that always issues the given tool calls (for loop tests)."""
    def step(messages, tools):
        return {"content": "", "tool_calls": tool_calls}
    return step


def _done_llm():
    """llm_step that immediately answers without a tool call."""
    def step(messages, tools):
        return {"content": "goal met", "tool_calls": []}
    return step


def _parking_worker(store, queue, **kwargs) -> AgentWorker:
    """Worker whose _dispatch parks an approval gate instead of executing."""
    class _ParkingWorker(AgentWorker):
        @staticmethod
        def _dispatch(name, args):
            return "I need your permission to X.", {
                "id": "p1", "description": "mutate something",
            }
    return _ParkingWorker(
        store, queue, worker_id="w", poll_seconds=1.0,
        llm_step=_tool_llm(_tool_call()), **kwargs)


class WorkerSetup(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AgentSessionStore(_temp_db())
        self.queue = AgentQueue(_temp_db())
        # Make per-job turn budgets small and deterministic without editing
        # the global config; restore afterwards.
        self._orig_job_turns = getattr(settings, "agents_job_max_turns", 20)
        settings.agents_job_max_turns = 2

    def tearDown(self) -> None:
        settings.agents_job_max_turns = self._orig_job_turns
        self.store.close()
        self.queue.close()

    def _ready(self, **create) -> int:
        agent_id = self.store.create(**create)
        self.store.transition(agent_id, "ready")
        return agent_id

    def _run_job(self, agent_id: int) -> int:
        return self.queue.enqueue(
            "run", {"agent_id": agent_id}, agent_id=agent_id,
            idempotency_key=f"run-{agent_id}-{time.time_ns()}",
        )

    def _worker(self, **kwargs) -> AgentWorker:
        return AgentWorker(self.store, self.queue, worker_id="w",
                           poll_seconds=1.0, **kwargs)


# ── The loop ─────────────────────────────────────────────────────────────────


class WorkerLoopTest(WorkerSetup):
    def test_done_when_llm_answers(self) -> None:
        agent_id = self._ready(name="a", goal="g")
        job_id = self._run_job(agent_id)
        self._worker(llm_step=_done_llm()).tick()
        self.assertEqual(self.store.get(agent_id)["state"], "done")
        self.assertEqual(self.queue.get(job_id)["status"], "done")
        details = [e["detail"] for e in self.store.action_log(agent_id)]
        self.assertIn("running -> done", details)

    def test_job_turn_budget_parks_back_to_ready(self) -> None:
        # A job that keeps acting without finishing returns the session to
        # dormancy (ready) when its per-job turn budget runs out.
        agent_id = self._ready(name="worker", goal="g")
        job_id = self._run_job(agent_id)
        worker = self._worker(llm_step=_tool_llm(_tool_call()))
        outcome = worker._drive_agent(agent_id, self.queue.get(job_id))
        self.assertEqual(outcome["state"], "ready")
        self.assertEqual(self.store.get(agent_id)["state"], "ready")
        self.assertEqual(self.store.get(agent_id)["budget_used"], 2)

    def test_lifetime_turn_budget_kills_session(self) -> None:
        # With usage already at the lifetime cap, the next loop check goes dead.
        agent_id = self._ready(name="b", goal="g", budget={"max_turns": 1})
        self.store.bump_budget_used(agent_id)
        job_id = self._run_job(agent_id)
        worker = self._worker(llm_step=_tool_llm(_tool_call()))
        worker.tick()
        self.assertEqual(self.store.get(agent_id)["state"], "dead")
        self.assertEqual(self.queue.get(job_id)["status"], "done")

    def test_approval_gate_parks_waiting_human(self) -> None:
        agent_id = self._ready(name="c", goal="g")
        job_id = self._run_job(agent_id)
        worker = _parking_worker(self.store, self.queue)
        worker.tick()
        agent = self.store.get(agent_id)
        self.assertEqual(agent["state"], "waiting_human")
        self.assertEqual(agent["pending_action"]["description"], "mutate something")
        self.assertEqual(self.queue.get(job_id)["status"], "done")

    def test_resume_applies_queued_approval_decision(self) -> None:
        from sopno.core.agents.events import AgentEvents

        agent_id = self._ready(name="d", goal="g")
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "waiting_human")
        self.store.set_pending_action(agent_id, {"id": "abc", "description": "X"})
        events = AgentEvents(store=self.store, queue=self.queue)
        events.wake(agent_id, "yes, go ahead", source="human")

        seen: list[str] = []

        def llm(messages, tools):
            text = "\n".join(str(m.get("content", "")) for m in messages)
            seen.append(text)
            if "[approval]" in text:
                return {"content": "done now", "tool_calls": []}
            return {"content": "", "tool_calls": _tool_call()}

        self._worker(llm_step=llm).tick()
        self.assertEqual(self.store.get(agent_id)["state"], "done")
        self.assertEqual(self.store.get(agent_id)["pending_action"], None)
        self.assertIn("[approval]", seen[0])

    def test_paused_session_skipped(self) -> None:
        agent_id = self._ready(name="e", goal="g")
        self.store.set_status(agent_id, "paused")
        job_id = self._run_job(agent_id)
        self._worker(llm_step=_done_llm()).tick()
        self.assertEqual(self.store.get(agent_id)["state"], "ready")
        self.assertEqual(self.queue.get(job_id)["status"], "done")

    def test_terminal_session_skipped(self) -> None:
        agent_id = self._ready(name="f", goal="g")
        self.store.transition(agent_id, "ready")
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "done")
        job_id = self._run_job(agent_id)
        self._worker(llm_step=_done_llm()).tick()
        self.assertEqual(self.queue.get(job_id)["status"], "done")

    def test_llm_step_failure_blocks_session(self) -> None:
        agent_id = self._ready(name="g", goal="g")
        job_id = self._run_job(agent_id)

        def boom(messages, tools):
            raise RuntimeError("model down")

        self._worker(llm_step=boom).tick()
        self.assertEqual(self.store.get(agent_id)["state"], "blocked")
        self.assertEqual(self.queue.get(job_id)["status"], "done")

    def test_tool_not_in_allowlist_gets_reason(self) -> None:
        agent_id = self._ready(name="h", goal="g", tools=["read_file"])
        self._run_job(agent_id)

        def llm(messages, tools):
            return {"content": "", "tool_calls": _tool_call("edit_file")}

        self._worker(llm_step=llm).tick()
        agent = self.store.get(agent_id)
        # The tool was refused, the loop continued and parked back to ready.
        self.assertEqual(agent["state"], "ready")
        log = " ".join(e["detail"] for e in self.store.action_log(agent_id))
        self.assertIn("not in this agent's allowlist", log)

    def test_two_jobs_for_same_agent_run_serially(self) -> None:
        agent_id = self._ready(name="i", goal="g")
        for i in range(2):
            self._run_job(agent_id)
        worker = self._worker(llm_step=_tool_llm(_tool_call()))
        processed = worker.tick()
        self.assertEqual(len(processed), 2)
        self.assertEqual(self.store.get(agent_id)["state"], "ready")
        self.assertEqual(self.store.get(agent_id)["budget_used"], 4)


# ── Coding bridge ────────────────────────────────────────────────────────────


class CodingBridgeTest(WorkerSetup):
    def test_coding_kind_routes_to_coding_runner(self) -> None:
        calls: list[tuple] = []

        def coding_runner(spec, **kwargs):
            calls.append((spec, kwargs))
            return {"state": "success", "reason": "done", "branch": "b",
                    "worktree": "w", "commits": ["c"], "turns": 1,
                    "changes": 1, "diff_lines": 10, "summary": "built"}

        agent_id = self._ready(name="coder", goal="Fix the bug", kind="coding")
        job_id = self._run_job(agent_id)
        worker = self._worker(coding_runner=coding_runner)
        worker.tick()
        spec, kwargs = calls[0]
        self.assertEqual(spec["goal"], "Fix the bug")
        self.assertEqual(kwargs["store"], self.store)
        self.assertEqual(kwargs["session_id"], agent_id)
        self.assertEqual(self.store.get(agent_id)["state"], "done")
        self.assertEqual(self.queue.get(job_id)["status"], "done")

    def test_coding_runner_crash_blocks_session(self) -> None:
        def coding_runner(spec, **kwargs):
            raise RuntimeError("worktree exploded")

        agent_id = self._ready(name="coder2", goal="g", kind="coding")
        self._run_job(agent_id)
        self._worker(coding_runner=coding_runner).tick()
        self.assertEqual(self.store.get(agent_id)["state"], "blocked")


# ── Capability profile ───────────────────────────────────────────────────────


class CapabilityTest(WorkerSetup):
    def test_default_allowlist_excludes_management_tools(self) -> None:
        worker = self._worker()
        agent = {"tools": []}
        allowed = worker._tools_for(agent)
        self.assertFalse(MANAGEMENT_TOOLS & allowed)

    def test_explicit_allowlist_wins(self) -> None:
        worker = self._worker()
        allowed = worker._tools_for({"tools": ["read_file"]})
        self.assertEqual(allowed, frozenset({"read_file"}))


if __name__ == "__main__":
    unittest.main()
