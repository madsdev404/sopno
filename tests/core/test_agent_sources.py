"""
tests/core/test_agent_sources.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the event sources (sopno/core/agents/sources.py): the poll-based
FileWatcher and the HTTP WebhookServer both turn an external event into the
same durable wake (pending input + resume job) as a human reply.
"""

import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from sopno.core.agents.queue import AgentQueue
from sopno.core.agents.session import AgentSessionStore
from sopno.core.agents.sources import (FileWatcher, WebhookServer,
                                       get_webhook, set_webhook)


def _temp_db() -> str:
    return tempfile.mkstemp(suffix=".db")[1]


class SourceSetup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = AgentSessionStore(_temp_db())
        self.queue = AgentQueue(_temp_db())

    def tearDown(self) -> None:
        self.store.close()
        self.queue.close()
        self._tmp.cleanup()


class FileWatcherTest(SourceSetup):
    def _agent(self, name="watch") -> int:
        agent_id = self.store.create(name, "Goal")
        self.store.transition(agent_id, "ready")
        return agent_id

    def _resume_jobs(self, agent_id: int) -> list[dict]:
        return [j for j in self.queue.peek()
                if j["kind"] == "resume" and j["agent_id"] == agent_id]

    def test_file_change_wakes_the_agent(self) -> None:
        agent_id = self._agent("watch")
        watched = self.root / "inbox"
        watched.mkdir()
        (watched / "seed.txt").write_text("x", encoding="utf-8")
        watcher = FileWatcher(
            self.store, self.queue,
            watches=[{"path": str(watched), "agent": "watch",
                      "message": "inbox changed: {path}"}],
            poll_seconds=0.5,
        )
        try:
            watcher._tick()  # initial snapshot (no wake)
            self.assertEqual(self._resume_jobs(agent_id), [])
            (watched / "new.txt").write_text("hello", encoding="utf-8")
            watcher._tick()
            jobs = self._resume_jobs(agent_id)
            self.assertEqual(len(jobs), 1)
            agent = self.store.get(agent_id)
            self.assertEqual(agent["pending_input"][0]["text"],
                             "inbox changed: new.txt")
            # The snapshot advanced — the same change never fires twice.
            watcher._tick()
            self.assertEqual(len(self._resume_jobs(agent_id)), 1)
        finally:
            watcher.stop()

    def test_unknown_agent_is_ignored(self) -> None:
        watched = self.root / "inbox"
        watched.mkdir()
        watcher = FileWatcher(
            self.store, self.queue,
            watches=[{"path": str(watched), "agent": "ghost"}],
            poll_seconds=0.5,
        )
        try:
            (watched / "a.txt").write_text("x", encoding="utf-8")
            watcher._tick()
            self.assertEqual(len(self.queue.peek(limit=100)), 0)
        finally:
            watcher.stop()


class WebhookServerTest(SourceSetup):
    def _server(self) -> WebhookServer:
        server = WebhookServer(self.store, self.queue, port=0)
        server.start()
        self.addCleanup(server.stop)
        return server

    def test_webhook_wakes_an_agent(self) -> None:
        agent_id = self.store.create("webby", "Goal")
        self.store.transition(agent_id, "ready")
        server = self._server()
        body = json.dumps({"agent": "webby", "message": "deploy finished"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/webhook", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(json.loads(resp.read())["ok"], True)
        agent = self.store.get(agent_id)
        self.assertEqual(agent["pending_input"][0]["text"], "deploy finished")
        resumes = [j for j in self.queue.peek()
                   if j["kind"] == "resume" and j["agent_id"] == agent_id]
        self.assertEqual(len(resumes), 1)

    def test_webhook_applies_state_delta(self) -> None:
        agent_id = self.store.create("delta", "Goal")
        self.store.transition(agent_id, "ready")
        server = self._server()
        body = json.dumps({"agent": agent_id,
                           "message": "paused externally",
                           "state_delta": {"status": "paused"}}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/webhook", data=body,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
        self.assertEqual(self.store.get(agent_id)["status"], "paused")

    def test_health_endpoint(self) -> None:
        server = self._server()
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/health", timeout=5
        ) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(json.loads(resp.read())["ok"], True)

    def test_unknown_agent_returns_404(self) -> None:
        server = self._server()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/webhook",
            data=json.dumps({"agent": "ghost"}).encode(), method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
