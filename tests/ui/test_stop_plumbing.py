"""
tests/ui/test_stop_plumbing.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the text-mode Stop contract: request_stop arms a cooperative
cancel flag, checkpoints consume it without corrupting context, and the
flag never leaks into the next turn.
"""

import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sopno.core.assistant import SopnoAssistant
from sopno.ui.hud.worker import AssistantWorker


def _bare_assistant() -> tuple[SopnoAssistant, list[str]]:
    """SopnoAssistant without mic/TTS/LLM side effects."""
    assistant = SopnoAssistant.__new__(SopnoAssistant)
    assistant._turn_stop = threading.Event()
    assistant.context = type(
        "Ctx", (), {"raw_messages": [{"role": "user", "content": "hi"}]}
    )()
    statuses: list[str] = []
    assistant.on_log_message = lambda msg: None
    assistant.on_status_changed = statuses.append
    return assistant, statuses


class RequestStopTest(unittest.TestCase):
    def test_request_stop_arms_flag_once(self) -> None:
        assistant, _ = _bare_assistant()
        self.assertTrue(assistant.request_stop())
        self.assertFalse(assistant.request_stop())   # idempotent

    def test_checkpoint_consumes_stop_and_pops_user_message(self) -> None:
        assistant, statuses = _bare_assistant()
        assistant.request_stop()
        self.assertTrue(assistant._stopped_mid_turn())
        self.assertEqual(statuses, ["standby"])
        self.assertEqual(assistant.context.raw_messages, [])

    def test_checkpoint_without_stop_is_noop(self) -> None:
        assistant, statuses = _bare_assistant()
        self.assertFalse(assistant._stopped_mid_turn())
        self.assertEqual(statuses, [])
        self.assertEqual(len(assistant.context.raw_messages), 1)

    def test_stop_does_not_leak_into_next_turn(self) -> None:
        assistant, _ = _bare_assistant()
        assistant.request_stop()
        # Simulate the finally-block cleanup at the end of _process_command.
        assistant._turn_stop.clear()
        self.assertFalse(assistant._stopped_mid_turn())


class WorkerBridgeTest(unittest.TestCase):
    def test_worker_exposes_stop_generation(self) -> None:
        self.assertTrue(hasattr(AssistantWorker, "stop_generation"))


if __name__ == "__main__":
    unittest.main()
