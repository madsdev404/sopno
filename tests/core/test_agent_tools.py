"""
tests/core/test_agent_tools.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the agent management tools (sopno/tools/builtins/automation/agents.py):
create / list / status / send / pause / resume / kill / log, and their safety
gates (validation + the confirmation gate on kill).
"""

import tempfile
import unittest

from sopno.core.agents.events import AgentEvents, set_events
from sopno.core.agents.queue import AgentQueue, set_queue
from sopno.core.agents.session import AgentSessionStore, set_store
from sopno.tools.builtins.automation.agents import (
    agent_align,
    agent_create,
    agent_kill,
    agent_list,
    agent_log,
    agent_pause,
    agent_resume,
    agent_send,
    agent_status,
)
from sopno.tools.builtins.automation.coding import coding_run, coding_status


def _temp_db() -> str:
    return tempfile.mkstemp(suffix=".db")[1]


class AgentToolsSetup(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AgentSessionStore(_temp_db())
        self.queue = AgentQueue(_temp_db())
        self.events = AgentEvents(store=self.store, queue=self.queue)
        set_store(self.store)
        set_queue(self.queue)
        set_events(self.events)

    def tearDown(self) -> None:
        set_store(None)
        set_queue(None)
        set_events(None)
        self.store.close()
        self.queue.close()


class CreateTest(AgentToolsSetup):
    def test_create_makes_a_ready_session(self) -> None:
        text = agent_create("nightly", "Tidy downloads", task_type="general")
        self.assertIn("Agent 'nightly' created", text)
        agent = self.store.get_by_name("nightly")
        self.assertEqual(agent["state"], "ready")
        self.assertEqual(agent["kind"], "general")

    def test_create_coding_kind_and_schedule(self) -> None:
        text = agent_create(
            "fixer", "Fix the parser bug", task_type="coding",
            schedule="interval:3600", tools=["read_file"],
            budget={"max_turns": 5, "max_wall_minutes": 60},
        )
        self.assertIn("created", text)
        agent = self.store.get_by_name("fixer")
        self.assertEqual(agent["kind"], "coding")
        self.assertEqual(agent["schedule"], "interval:3600")
        self.assertEqual(agent["tools"], ["read_file"])
        self.assertEqual(agent["budget"]["max_turns"], 5)

    def test_create_rejects_bad_inputs(self) -> None:
        self.assertIn("task_type", agent_create("a", "g", task_type="bogus"))
        self.assertIn("Bad schedule",
                      agent_create("a", "g", schedule="nonsense:1"))
        self.assertIn("Unknown tools",
                      agent_create("a", "g", tools=["not_a_tool"]))
        self.assertIn("Unknown budget",
                      agent_create("a", "g", budget={"oops": 1}))
        self.assertIn("non-negative",
                      agent_create("a", "g", budget={"max_turns": -1}))
        self.assertIn("already exists", agent_create("a", "g") and
                      agent_create("a", "g"))

    def test_create_unknown_agent_status(self) -> None:
        self.assertIn("No agent named", agent_status("ghost"))


class LifecycleTest(AgentToolsSetup):
    def _agent(self, name="worker") -> int:
        agent_create(name, "Goal")
        return self.store.get_by_name(name)["id"]

    def test_send_wakes_a_parked_agent(self) -> None:
        agent_id = self._agent()
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "waiting_human")
        text = agent_send("worker", "yes, go ahead")
        self.assertIn("Message queued", text)
        agent = self.store.get(agent_id)
        self.assertEqual(agent["pending_input"][0]["text"], "yes, go ahead")
        jobs = [j for j in self.queue.peek() if j["kind"] == "resume"]
        self.assertEqual(len(jobs), 1)

    def test_send_rejects_terminal(self) -> None:
        agent_id = self._agent()
        self.store.transition(agent_id, "ready")
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "done")
        self.assertIn("already done", agent_send("worker", "hi"))

    def test_pause_cancels_queued_jobs(self) -> None:
        agent_id = self._agent()
        j1 = self.queue.enqueue("run", {"agent_id": agent_id},
                                agent_id=agent_id, idempotency_key="k1")
        j2 = self.queue.enqueue("run", {"agent_id": agent_id},
                                agent_id=agent_id, idempotency_key="k2")
        text = agent_pause("worker")
        self.assertIn("paused", text)
        self.assertEqual(self.store.get(agent_id)["status"], "paused")
        self.assertEqual(self.queue.get(j1)["status"], "cancelled")
        self.assertEqual(self.queue.get(j2)["status"], "cancelled")

    def test_resume_queues_a_job_and_clears_paused(self) -> None:
        agent_id = self._agent()
        agent_pause("worker")
        text = agent_resume("worker")
        self.assertIn("resumed", text)
        self.assertEqual(self.store.get(agent_id)["status"], "idle")
        jobs = [j for j in self.queue.peek() if j["kind"] == "resume"]
        self.assertEqual(len(jobs), 1)

    def test_kill_requires_confirmation_then_terminates(self) -> None:
        from sopno.tools.builtins.files import files

        agent_id = self._agent()
        self.queue.enqueue("run", {"agent_id": agent_id},
                           agent_id=agent_id, idempotency_key="k3")
        text = agent_kill("worker")
        self.assertIn("I need your permission", text)
        # The agent is not dead yet — nothing happened without the 'yes'.
        self.assertNotEqual(self.store.get(agent_id)["state"], "dead")
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("terminated", result)
        agent = self.store.get(agent_id)
        self.assertEqual(agent["state"], "dead")
        self.assertIsNone(agent["schedule"])
        self.assertEqual(self.queue.get(1)["status"], "cancelled")


class InspectTest(AgentToolsSetup):
    def test_list_status_and_log(self) -> None:
        agent_create("alpha", "Goal A")
        agent_create("beta", "Goal B", task_type="coding")
        listing = agent_list()
        self.assertIn("alpha", listing)
        self.assertIn("beta", listing)
        status = agent_status("alpha")
        self.assertIn("Goal A", status)
        self.store.log_action(self.store.get_by_name("alpha")["id"],
                              "message", "hello")
        self.assertIn("hello", agent_log("alpha", limit=5))

    def test_agent_align_records_a_correction(self) -> None:
        agent_create("alignme", "Goal")
        text = agent_align("alignme", "always run the tests before committing")
        self.assertIn("Alignment recorded", text)
        agent = self.store.get_by_name("alignme")
        self.assertEqual(agent["alignment"][0]["text"],
                         "always run the tests before committing")
        self.assertIn("correction", agent_align("alignme", ""))
        self.assertIn("No agent named", agent_align("ghost", "x"))


class CodingToolsTest(AgentToolsSetup):
    def test_coding_run_creates_session_and_queues_job(self) -> None:
        text = coding_run("Add a CLI flag", name="fixer")
        self.assertIn("created", text)
        self.assertIn("queued", text)
        agent = self.store.get_by_name("fixer")
        self.assertEqual(agent["kind"], "coding")
        self.assertEqual(agent["state"], "ready")
        runs = [j for j in self.queue.peek() if j["kind"] == "run"
                and j["agent_id"] == agent["id"]]
        self.assertEqual(len(runs), 1)

    def test_coding_run_requires_a_goal(self) -> None:
        self.assertIn("needs a goal", coding_run(""))

    def test_coding_run_batch_queues_each_ticket(self) -> None:
        text = coding_run(tickets=[
            {"goal": "Ticket one"},
            {"goal": "Ticket two", "schedule": "interval:3600"},
        ])
        self.assertIn("Queued coding batch", text)
        self.assertIn("Ticket one", coding_status())
        self.assertEqual(len([a for a in self.store.list()
                              if a.get("kind") == "coding"]), 2)

    def test_coding_run_rejects_bad_tickets(self) -> None:
        self.assertIn("needs a goal", coding_run(tickets=[{"goal": ""}]))
        self.assertIn("per-ticket fields",
                      coding_run(goal="x", tickets=[{"goal": "y"}]))

    def test_coding_status_shows_branch_from_record(self) -> None:
        coding_run("Watch this branch", name="watchdog")
        agent_id = self.store.get_by_name("watchdog")["id"]
        self.store.append_memory(
            agent_id,
            "[coding-worktree] "
            '{"branch": "sopno/watch-20240101-000000", "base": "abc"}',
        )
        text = coding_status("watchdog")
        self.assertIn("sopno/watch-20240101-000000", text)
        self.assertIn("watchdog", coding_status())
        self.assertIn("No agent named", coding_status("ghost"))


if __name__ == "__main__":
    unittest.main()
