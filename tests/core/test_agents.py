"""
tests/core/test_agents.py
━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the long-running agent machinery: the durable session store / state
machine (sopno/core/agents/session.py) and the durable job queue with atomic
claims, leases, retries and a dead-letter state (sopno/core/agents/queue.py).
"""

import tempfile
import time
import unittest

from sopno.core.agents.queue import AgentQueue, _backoff_seconds
from sopno.core.agents.session import AgentSessionStore, valid_transition


def _temp_db() -> str:
    return tempfile.mkstemp(suffix=".db")[1]


# ── Session store / state machine ────────────────────────────────────────────


class ValidTransitionTest(unittest.TestCase):
    def test_legal_transitions(self) -> None:
        for current, target in (
            ("created", "ready"),
            ("created", "dead"),
            ("ready", "running"),
            ("ready", "dead"),
            ("running", "running"),
            ("running", "waiting_human"),
            ("running", "done"),
            ("running", "blocked"),
            ("running", "dead"),
            ("running", "ready"),  # job turn budget → dormancy, still resumable
            ("waiting_human", "running"),
            ("waiting_human", "done"),
            ("blocked", "running"),
            ("blocked", "done"),
            ("blocked", "dead"),
        ):
            self.assertTrue(valid_transition(current, target),
                            f"{current} -> {target} should be allowed")

    def test_illegal_transitions(self) -> None:
        for current, target in (
            ("created", "running"),
            ("done", "ready"),
            ("done", "running"),
            ("dead", "ready"),
            ("waiting_human", "waiting_human"),
            ("running", "created"),
        ):
            self.assertFalse(valid_transition(current, target),
                             f"{current} -> {target} should be blocked")


class SessionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = AgentSessionStore(_temp_db())

    def tearDown(self) -> None:
        self.store.close()

    def test_create_and_get(self) -> None:
        agent_id = self.store.create("researcher", "Find the latest paper.")
        session = self.store.get(agent_id)
        self.assertEqual(session["name"], "researcher")
        self.assertEqual(session["goal"], "Find the latest paper.")
        self.assertEqual(session["state"], "created")
        self.assertEqual(session["plan"], [])

    def test_create_requires_name_and_goal(self) -> None:
        with self.assertRaises(ValueError):
            self.store.create("", "goal")
        with self.assertRaises(ValueError):
            self.store.create("name", "")

    def test_duplicate_name_rejected(self) -> None:
        self.store.create("dupe", "first")
        with self.assertRaises(ValueError):
            self.store.create("dupe", "second")

    def test_get_by_name_and_list(self) -> None:
        a = self.store.create("one", "g1")
        b = self.store.create("two", "g2")
        self.assertEqual(self.store.get_by_name("two")["id"], b)
        names = {s["name"] for s in self.store.list()}
        self.assertEqual(names, {"one", "two"})
        self.assertEqual(self.store.count(), 2)
        self.assertIsNone(self.store.get(a + 100))

    def test_delete(self) -> None:
        agent_id = self.store.create("gone", "x")
        self.assertTrue(self.store.delete(agent_id))
        self.assertIsNone(self.store.get(agent_id))
        self.assertFalse(self.store.delete(agent_id))

    def test_transition_lifecycle(self) -> None:
        agent_id = self.store.create("life", "g")
        self.store.transition(agent_id, "ready")
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "blocked")
        self.store.transition(agent_id, "done")
        self.assertEqual(self.store.get(agent_id)["state"], "done")
        with self.assertRaises(ValueError):
            self.store.transition(agent_id, "running")  # done is terminal

    def test_unknown_transition_rejected(self) -> None:
        agent_id = self.store.create("x", "g")
        with self.assertRaises(ValueError):
            self.store.transition(agent_id, "bogus")
        self.store.transition(agent_id, "ready")
        with self.assertRaises(ValueError):
            self.store.transition(agent_id, "waiting_human")  # ready can't skip running

    def test_waiting_human_roundtrip(self) -> None:
        agent_id = self.store.create("chat", "g")
        self.store.transition(agent_id, "ready")
        self.store.transition(agent_id, "running")
        self.store.transition(agent_id, "waiting_human")
        self.store.enqueue_input(agent_id, "approved")
        self.store.enqueue_input(agent_id, "and one more")
        self.assertEqual(self.store.get(agent_id)["state"], "waiting_human")
        pending = self.store.drain_input(agent_id)
        self.assertEqual([p["text"] for p in pending], ["approved", "and one more"])
        self.assertEqual(self.store.get(agent_id)["pending_input"], [])
        self.store.transition(agent_id, "running")

    def test_heartbeat_only_for_running(self) -> None:
        agent_id = self.store.create("hb", "g")
        self.store.transition(agent_id, "ready")
        self.assertFalse(self.store.heartbeat(agent_id))
        self.store.transition(agent_id, "running")
        self.assertTrue(self.store.heartbeat(agent_id))

    def test_plan_memory_alignment_budget(self) -> None:
        agent_id = self.store.create("mem", "g")
        self.store.set_plan(agent_id, [{"step": "research"}])
        self.store.append_memory(agent_id, "use hybrid retrieval")
        self.store.append_memory(agent_id, "cap at 6 pages")
        self.store.add_alignment(agent_id, "prefer citations")
        self.store.set_budget(agent_id, {"max_turns": 50})
        self.store.bump_budget_used(agent_id, 3)
        session = self.store.get(agent_id)
        self.assertEqual(session["plan"], [{"step": "research"}])
        self.assertEqual(len(session["working_memory"]), 2)
        self.assertEqual(session["working_memory"][1]["text"], "cap at 6 pages")
        self.assertEqual(session["alignment"][0]["text"], "prefer citations")
        self.assertEqual(session["budget"], {"max_turns": 50})
        self.assertEqual(session["budget_used"], 3)

    def test_kind_and_pending_action_roundtrip(self) -> None:
        coding = self.store.create("coder", "g", kind="coding")
        general = self.store.create("plain", "g")
        self.assertEqual(self.store.get(coding)["kind"], "coding")
        self.assertEqual(self.store.get(general)["kind"], "general")
        self.store.set_kind(coding, "general")
        self.assertEqual(self.store.get(coding)["kind"], "general")
        self.store.set_pending_action(coding, {"id": "p", "description": "X"})
        self.assertEqual(self.store.get(coding)["pending_action"]["id"], "p")
        self.store.set_pending_action(coding, None)
        self.assertIsNone(self.store.get(coding)["pending_action"])

    def test_action_log_is_append_only(self) -> None:
        agent_id = self.store.create("audit", "g")
        self.store.transition(agent_id, "ready")
        self.store.log_action(agent_id, "action", "wrote a file")
        self.store.log_action(agent_id, "error", "boom")
        log = self.store.action_log(agent_id)
        kinds = [entry["kind"] for entry in log]
        self.assertIn("action", kinds)
        self.assertIn("error", kinds)
        self.assertEqual(log[0]["detail"], "boom")  # newest first

    def test_persistence_across_reopen(self) -> None:
        path = _temp_db()
        store1 = AgentSessionStore(path)
        agent_id = store1.create("persist", "g")
        store1.transition(agent_id, "ready")
        store1.close()
        store2 = AgentSessionStore(path)
        session = store2.get(agent_id)
        self.assertEqual(session["state"], "ready")
        store2.close()


# ── Queue ────────────────────────────────────────────────────────────────────


class QueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.q = AgentQueue(_temp_db(), backoff_base=1.0, backoff_cap=60.0)

    def tearDown(self) -> None:
        self.q.close()

    def test_enqueue_and_claim(self) -> None:
        job_id = self.q.enqueue("run", {"goal": "x"})
        claimed = self.q.claim("worker-a")
        self.assertEqual(len(claimed), 1)
        job = claimed[0]
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["lease_owner"], "worker-a")
        # A job is never claimed twice.
        self.assertEqual(self.q.claim("worker-b"), [])

    def test_claim_honors_delay(self) -> None:
        self.q.enqueue("run", delay_seconds=3600)
        self.assertEqual(self.q.claim("w", now=time.time()), [])
        self.assertEqual(len(self.q.claim("w", now=time.time() + 3601)), 1)

    def test_claim_limit(self) -> None:
        self.q.enqueue("a")
        self.q.enqueue("b")
        self.q.enqueue("c")
        self.assertEqual(len(self.q.claim("w", limit=2)), 2)
        self.assertEqual(len(self.q.claim("w", limit=2)), 1)

    def test_finish(self) -> None:
        job_id = self.q.enqueue("run")
        self.q.claim("w")
        self.assertTrue(self.q.finish(job_id, "w", result="ok"))
        self.assertEqual(self.q.get(job_id)["status"], "done")
        self.assertFalse(self.q.finish(job_id, "w"))  # already terminal

    def test_renew_extends_lease(self) -> None:
        job_id = self.q.enqueue("run")
        self.q.claim("w")
        now = time.time()
        self.q.renew(job_id, "w", now=now + 100, seconds=600)
        # Claimed lease ran until now+300; the renewal pushed it to now+700,
        # so a recovery scan at now+600 finds a still-live lease.
        self.q.recover_orphans(now=now + 600)
        job = self.q.get(job_id)
        self.assertEqual(job["status"], "running")  # lease still live

    def test_release(self) -> None:
        job_id = self.q.enqueue("run")
        self.q.claim("w")
        self.assertTrue(self.q.release(job_id, "w"))
        self.assertEqual(self.q.get(job_id)["status"], "ready")
        self.assertEqual(len(self.q.claim("w2")), 1)

    def test_orphan_recovery_requeues(self) -> None:
        job_id = self.q.enqueue("run", max_attempts=3)
        self.q.claim("w", now=time.time())
        self.assertEqual(self.q.recover_orphans(now=time.time() + 1000), 1)
        job = self.q.get(job_id)
        self.assertEqual(job["status"], "ready")
        self.assertEqual(job["attempts"], 1)
        self.assertIsNotNone(job["next_attempt_at"])  # backoff gate
        # Not claimable until backoff passes.
        self.assertEqual(self.q.claim("w2", now=time.time()), [])

    def test_orphan_dead_letter_after_max_attempts(self) -> None:
        job_id = self.q.enqueue("run", max_attempts=2)
        now = time.time()
        self.q.claim("w", now=now)
        self.q.recover_orphans(now=now + 1000)  # attempts -> 1, backoff
        self.q.claim("w", now=now + 10000)
        self.q.recover_orphans(now=now + 11000)  # attempts -> 2 >= max
        job = self.q.get(job_id)
        self.assertEqual(job["status"], "dead")
        self.assertEqual(job["attempts"], 2)
        self.assertIn("orphaned", job["last_error"])

    def test_fail_retries_with_backoff(self) -> None:
        job_id = self.q.enqueue("run", max_attempts=3)
        self.q.claim("w")
        self.assertTrue(self.q.fail(job_id, "w", "transient", now=time.time()))
        job = self.q.get(job_id)
        self.assertEqual(job["status"], "ready")
        self.assertEqual(job["attempts"], 1)
        self.assertEqual(job["last_error"], "transient")

    def test_fail_dead_letter_on_attempt_exhaustion(self) -> None:
        job_id = self.q.enqueue("run", max_attempts=1)
        self.q.claim("w")
        self.assertTrue(self.q.fail(job_id, "w", "boom"))
        self.assertEqual(self.q.get(job_id)["status"], "dead")

    def test_fail_non_retryable_goes_dead(self) -> None:
        job_id = self.q.enqueue("run", max_attempts=5)
        self.q.claim("w")
        self.assertTrue(self.q.fail(job_id, "w", "permanent", retryable=False))
        self.assertEqual(self.q.get(job_id)["status"], "dead")

    def test_idempotency_dedupe(self) -> None:
        a = self.q.enqueue("event", {"n": 1}, idempotency_key="evt-1")
        b = self.q.enqueue("event", {"n": 2}, idempotency_key="evt-1")
        self.assertEqual(a, b)
        self.assertEqual(self.q.stats()["ready"], 1)

    def test_cancel(self) -> None:
        job_id = self.q.enqueue("run")
        self.assertTrue(self.q.cancel(job_id))
        self.assertEqual(self.q.get(job_id)["status"], "cancelled")
        self.assertFalse(self.q.cancel(job_id))

    def test_stats(self) -> None:
        self.q.enqueue("a")
        self.q.enqueue("b")
        job = self.q.enqueue("c")
        claimed = self.q.claim("w", limit=3)
        self.q.finish(claimed[0]["id"], "w")
        stats = self.q.stats()
        self.assertEqual(stats.get("ready", 0), 0)
        self.assertEqual(stats.get("running", 0), 2)
        self.assertEqual(stats.get("done", 0), 1)
        self.assertEqual(job, 3)

    def test_backoff_capped_and_jittered(self) -> None:
        self.assertAlmostEqual(_backoff_seconds(1, 5, 3600, jitter=lambda: 0.0), 5.0)
        self.assertAlmostEqual(_backoff_seconds(2, 5, 3600, jitter=lambda: 0.0), 10.0)
        self.assertAlmostEqual(_backoff_seconds(12, 5, 3600, jitter=lambda: 0.0), 3600.0)
        # Jitter scales up but never below the raw value.
        self.assertGreaterEqual(
            _backoff_seconds(3, 5, 3600, jitter=lambda: 0.7), 20.0
        )


if __name__ == "__main__":
    unittest.main()
