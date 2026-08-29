"""
tests/core/test_plan_mode.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Vagted per-turn reasoning-mode resolution + plan-then-execute flow
(doc/roadmap/thinking-modes.md §5.4/§5.5). Entirely offline: mic, TTS, and
LLM calls are patched.
"""

import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

from sopno.config.settings import settings
from sopno.core.assistant import SopnoAssistant, detect_mode_override, strip_mode_phrase, plan_steps
from sopno.llm import modes
from sopno.tools.builtins.files import files as files_module


def _dummy_llm_response(content: str = "done", tool_calls: Optional = None) -> dict:
    return {"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}


class TestModeOverride(unittest.TestCase):
    def test_english_detection(self) -> None:
        self.assertEqual(detect_mode_override("think about the ocean"), modes.THINKING)
        self.assertEqual(detect_mode_override("deep think about X"), modes.DEEP)
        self.assertEqual(detect_mode_override("make a plan to fix the build"), modes.PLAN)
        self.assertEqual(detect_mode_override("quick answer this"), modes.QUICK)

    def test_bangla_detection(self) -> None:
        self.assertEqual(detect_mode_override("একটা প্ল্যান করো"), modes.PLAN)
        self.assertEqual(detect_mode_override("গভীর ভাবে ভাবো"), modes.DEEP)
        self.assertEqual(detect_mode_override("ভাবো"), modes.THINKING)
        self.assertEqual(detect_mode_override("সংক্ষেপে বলো"), modes.QUICK)

    def test_detection_order_plan_wins(self) -> None:
        self.assertEqual(
            detect_mode_override("make a plan to think about deep reasoning"),
            modes.PLAN,
        )

    def test_no_override(self) -> None:
        self.assertIsNone(detect_mode_override("what is the weather like"))
        self.assertIsNone(detect_mode_override(""))
        self.assertIsNone(detect_mode_override(None))

    def test_strip_removes_only_matched_phrase(self) -> None:
        self.assertEqual(
            strip_mode_phrase("think about the ocean at dusk", modes.THINKING),
            "the ocean at dusk",
        )
        self.assertEqual(
            strip_mode_phrase("make a plan to fix the build", modes.PLAN),
            "to fix the build",
        )
        # Non-matching mode leaves text intact.
        self.assertEqual(
            strip_mode_phrase("think about the ocean", modes.DEEP),
            "think about the ocean",
        )


class TestPlanSteps(unittest.TestCase):
    def test_numbered(self) -> None:
        text = "1. Read the file\n2. Check the tests\n3. Fix failures"
        self.assertEqual(
            plan_steps(text),
            ["Read the file", "Check the tests", "Fix failures"],
        )

    def test_bulleted(self) -> None:
        text = "- measure the loop\n* optimize the core"
        self.assertEqual(plan_steps(text), ["measure the loop", "optimize the core"])

    def test_dedupes_and_skips_non_list(self) -> None:
        text = "Goal: refactor\n- repeat\n- repeat\nplain line"
        self.assertEqual(plan_steps(text), ["repeat"])


class PlanFlowBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="plan_test_")
        self._plan_dir = patch.object(settings, "plan_dir", Path(self.tmp))
        self._plan_dir.start()
        self.addCleanup(self._plan_dir.stop)
        files_module._PENDING_ACTION = None
        self.addCleanup(setattr, files_module, "_PENDING_ACTION", None)

        # Pure rule/LLM seam mocks; the audio-io + persistence get patched away.
        self.stream = MagicMock()
        self.stream.return_value = iter([])
        self.single = MagicMock(return_value="1. Read the file\n2. Check the outputs")
        self.chat = MagicMock(return_value=_dummy_llm_response("step done"))
        self.exec = MagicMock(return_value="tool ok")
        self.sleep = patch.object(time, "sleep", return_value=None)
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

        self.errors: list[str] = []

        self.patchers = [
            patch("sopno.core.assistant.MicStream"),
            patch("sopno.core.assistant.Listener"),
            patch("sopno.core.assistant.MemoryStore"),
            patch("sopno.core.assistant.ReminderStore"),
            patch("sopno.core.assistant.stream_mode", self.stream),
            patch("sopno.core.assistant.single_reply", self.single),
            patch("sopno.core.assistant.llm_chat", self.chat),
            patch("sopno.core.assistant.execute_tool", self.exec),
        ]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)

        self.replies: list[str] = []
        self.thinking: list[str] = []
        self.statuses: list[str] = []

        self.asst = SopnoAssistant(
            status_callback=self.statuses.append,
            reply_callback=self.replies.append,
            log_callback=lambda m: None,
            thinking_callback=self.thinking.append,
        )
        self.asst.interaction_mode = "text"
        self.asst._stopped_mid_turn = lambda: False
        self.asst._speech_lock = threading.Lock()

    def tearDown(self) -> None:
        files_module._PENDING_ACTION = None


class TestPlanFlowImmediate(PlanFlowBase):
    def test_plan_confirm_off_routes_and_executes_immediately(self) -> None:
        with patch.object(settings, "plan_confirm", False):
            self.assertEqual(self.asst._turn_mode, modes.QUICK)
            self.assertTrue(self.asst._process_command("make a plan to fix the build"))

        # Planner asked once; two steps executed via the executor (llm_chat).
        self.single.assert_called_once()
        self.assertEqual(self.chat.call_count, 2)
        self.assertEqual(self.exec.call_count, 0)  # pure replies, no tools

        # Artifact written as a reviewable .md under the temp plan_dir.
        artifacts = list(Path(self.tmp).glob("*.md"))
        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0].read_text(encoding="utf-8")
        self.assertIn("Read the file", artifact)
        self.assertIn("Check the outputs", artifact)

    def test_step_outputs_are_delivered_as_they_finish(self) -> None:
        self.chat.side_effect = [
            _dummy_llm_response("step one done"),
            _dummy_llm_response("step two done"),
        ]
        with patch.object(settings, "plan_confirm", False):
            self.asst._process_command("make a plan to fix the build")
        self.assertIn("step one done", self.replies)
        self.assertIn("step two done", self.replies)


class TestPlanConfirmationGate(PlanFlowBase):
    def test_execution_holds_until_yes(self) -> None:
        with patch.object(settings, "plan_confirm", True):
            self.assertTrue(self.asst._process_command("make a plan to fix the build"))

        # Nothing executed yet — the pending gate is armed.
        self.assertEqual(self.chat.call_count, 0)
        pending = files_module.pending_action()
        self.assertIsNotNone(pending)

        # Approve → executor runs the plan.
        result = files_module.resolve_pending(pending["id"], "yes")
        self.assertTrue(result)
        self.assertEqual(self.chat.call_count, 2)
        artifacts = list(Path(self.tmp).glob("*.md"))
        self.assertEqual(len(artifacts), 1)

    def test_no_decision_cancels_without_executing(self) -> None:
        with patch.object(settings, "plan_confirm", True):
            self.assertTrue(self.asst._process_command("make a plan to fix the build"))

        pending = files_module.pending_action()
        result = files_module.resolve_pending(pending["id"], "no")
        self.assertIn("Cancelled", result)
        self.assertEqual(self.chat.call_count, 0)
        self.assertIsNone(files_module.pending_action())


class TestPlanReplan(PlanFlowBase):
    def test_failed_step_triggers_exactly_one_bounded_replan(self) -> None:
        self.chat.side_effect = [
            _dummy_llm_response("Error: permission denied"),
            _dummy_llm_response("revised done"),
            _dummy_llm_response("step two done"),
        ]
        # First single_reply call = the initial plan; second = the one replan.
        self.single.side_effect = [
            "1. Read the file\n2. Check the outputs",
            "1. Retry with elevated access",
        ]
        with patch.object(settings, "plan_confirm", False):
            self.asst._process_command("make a plan to fix the build")

        # Planner invoked twice: initial plan + one replan. Bounded.
        self.assertEqual(self.single.call_count, 2)
        self.assertEqual(self.chat.call_count, 2)


class TestThinkingStreaming(PlanFlowBase):
    def test_think_about_streams_thinking_then_answer(self) -> None:
        # Text-mode streaming where the reference-mode resolution matters most.
        self.stream.return_value = iter([
            ("thinking", "trace chunk one"),
            ("answer", "final answer"),
        ])
        with patch.object(settings, "llm_mode", modes.AUTO):
            ok = self.asst._process_command("think about the ocean at dusk")

        self.assertTrue(ok)
        self.assertEqual(self.asst._turn_mode, modes.THINKING)
        # "think about" was stripped; the LLM saw the remainder.
        user_msgs = [m for m in self.asst.context.raw_messages if m["role"] == "user"]
        self.assertEqual(user_msgs[-1]["content"], "the ocean at dusk")
        # Thinking trace rendered, answer delivered.
        self.assertIn("trace chunk one", self.thinking)
        self.assertIn("final answer", self.replies)


class TestForcedMode(PlanFlowBase):
    """UI-driven set_reasoning_mode() routing (§5.6 HUD selector)."""

    def test_forced_thinking_wins_over_config_default(self) -> None:
        # config default is quick; HUD forces thinking → thinking wins.
        with patch.object(settings, "llm_mode", modes.QUICK):
            self.asst.set_reasoning_mode(modes.THINKING)
            self.asst._process_command("the ocean at dusk")
        self.assertEqual(self.asst._turn_mode, modes.THINKING)

    def test_phrase_override_still_beats_forced_mode(self) -> None:
        self.asst.set_reasoning_mode(modes.DEEP)
        # "quick answer" is an explicit phrase → it wins per turn.
        self.asst._process_command("quick answer what is the capital of Japan")
        self.assertEqual(self.asst._turn_mode, modes.QUICK)

    def test_auto_clears_force_and_defers_to_config(self) -> None:
        self.asst.set_reasoning_mode(modes.DEEP)
        self.assertIsNotNone(self.asst._forced_mode)
        self.asst.set_reasoning_mode(modes.AUTO)
        self.assertIsNone(self.asst._forced_mode)

    def test_forced_plan_routes_into_plan_flow(self) -> None:
        with patch.object(settings, "plan_confirm", False):
            self.asst.set_reasoning_mode(modes.PLAN)
            ok = self.asst._process_command("refactor the build")  # no phrase hint
        self.assertTrue(ok)
        # Planner invoked once by the plan branch.
        self.assertEqual(self.single.call_count, 1)


class TestLlMEthinkBackCompat(PlanFlowBase):
    def test_thinking_resolved_turn_downgrades_to_quick_when_llm_think_off(self) -> None:
        # llm_mode=auto, >=5 words, no hints → THINKING, but legacy llm_think
        # is off → the compat rule downgrades this turn to QUICK.
        with patch.object(settings, "llm_mode", modes.AUTO):
            with patch.object(settings, "llm_think", False):
                self.asst._process_command(
                    "the northern lights dance vividly tonight"
                )
        self.assertEqual(self.asst._turn_mode, modes.QUICK)
        self.assertFalse(self.asst._turn_think)

    def test_thinking_resolved_turn_stays_thinking_when_llm_think_on(self) -> None:
        with patch.object(settings, "llm_mode", modes.AUTO):
            with patch.object(settings, "llm_think", True):
                self.asst._process_command(
                    "the northern lights dance vividly tonight"
                )
        self.assertEqual(self.asst._turn_mode, modes.THINKING)
        self.assertTrue(self.asst._turn_think)

    def test_explicit_override_is_never_downgraded(self) -> None:
        # A per-turn override beats the legacy toggle entirely.
        with patch.object(settings, "llm_think", False):
            self.asst._process_command("think about the ocean")
        self.assertEqual(self.asst._turn_mode, modes.THINKING)


if __name__ == "__main__":
    unittest.main()