"""
tests/llm/test_client.py
━━━━━━━━━━━━━━━━━━━━━━━━
LLM-client wrapper: per-mode chat options, think flag, streaming phases, and
message normalization. Ollama is fully patched — no network.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.llm import client as llm_client
from sopno.llm import modes


def _fake_message(**overrides):
    msg = {"role": "assistant", "content": "hi", "thinking": "hmm"}
    msg.update(overrides)
    return msg


class TestChatOptions(unittest.TestCase):
    def test_quick_keeps_todays_budget(self) -> None:
        opts = llm_client._chat_options(modes.QUICK)
        self.assertEqual(opts["num_predict"], 120)
        self.assertEqual(opts["num_ctx"], 2048)
        self.assertEqual(opts["temperature"], 0.6)

    def test_thinking_uses_settings_override(self) -> None:
        with patch.object(llm_client.settings, "llm_think_num_predict", 555):
            self.assertEqual(
                llm_client._chat_options(modes.THINKING)["num_predict"], 555
            )

    def test_deep_uses_settings_overrides(self) -> None:
        with patch.object(llm_client.settings, "llm_deep_num_predict", 900):
            with patch.object(llm_client.settings, "llm_deep_num_ctx", 9999):
                opts = llm_client._chat_options(modes.DEEP)
        self.assertEqual(opts["num_predict"], 900)
        self.assertEqual(opts["num_ctx"], 9999)

    def test_plan_uses_its_own_tier(self) -> None:
        opts = llm_client._chat_options(modes.PLAN)
        self.assertEqual(opts["num_predict"], 400)
        self.assertEqual(opts["num_ctx"], 4096)


class TestChat(unittest.TestCase):
    def _patched_chat(self):
        patcher = patch("sopno.llm.client._get_client")
        client = patcher.start()
        self.addCleanup(patcher.stop)
        return client.return_value.chat

    def test_think_flag_follows_mode(self) -> None:
        chat = self._patched_chat()
        llm_client.chat([], mode=modes.QUICK)
        llm_client.chat([], mode=modes.THINKING)
        llm_client.chat([], mode=modes.DEEP)
        self.assertEqual(chat.call_args_list[0].kwargs["think"], False)
        self.assertEqual(chat.call_args_list[1].kwargs["think"], True)
        self.assertEqual(chat.call_args_list[2].kwargs["think"], True)

    def test_mode_defaults_to_settings_llm_mode(self) -> None:
        chat = self._patched_chat()
        with patch.object(llm_client.settings, "llm_mode", modes.THINKING):
            llm_client.chat([])
        chat.assert_called_once()
        self.assertEqual(chat.call_args.kwargs["think"], True)

    def test_explicit_mode_wins_over_default(self) -> None:
        chat = self._patched_chat()
        with patch.object(llm_client.settings, "llm_mode", modes.DEEP):
            llm_client.chat([], mode=modes.QUICK)
        self.assertEqual(chat.call_args.kwargs["think"], False)

    def test_auto_falls_back_to_quick_budget_not_setting(self) -> None:
        chat = self._patched_chat()
        with patch.object(llm_client.settings, "llm_mode", modes.DEEP):
            llm_client.chat([], mode=modes.AUTO)
        self.assertEqual(chat.call_args.kwargs["options"]["num_predict"], 120)


class TestStreamMode(unittest.TestCase):
    def test_yields_thinking_then_answer(self) -> None:
        patcher = patch("sopno.llm.client._get_client")
        client = patcher.start()
        self.addCleanup(patcher.stop)
        fake = MagicMock()
        fake.chat.return_value = [
            {"message": {"thinking": "step one"}},
            {"message": {"content": "answer start"}},
            {"message": {"thinking": ""}, "message2": {}},
            {"message": {"content": "answer end"}},
        ]
        client.return_value = fake

        chunks = list(llm_client.stream_mode([], mode=modes.QUICK))
        self.assertEqual(chunks, [
            ("thinking", "step one"),
            ("answer", "answer start"),
            ("answer", "answer end"),
        ])

    def test_passes_through_to_chat_options(self) -> None:
        patcher = patch("sopno.llm.client._get_client")
        client = patcher.start()
        self.addCleanup(patcher.stop)
        client.return_value.chat.return_value = []

        with patch("sopno.llm.client._chat_options") as options:
            listed = list(llm_client.stream_mode([], mode=modes.DEEP))

        options.assert_called_once_with(modes.DEEP)
        self.assertEqual(listed, [])
        self.assertTrue(client.return_value.chat.call_args.kwargs["stream"])


class TestSingleReply(unittest.TestCase):
    def test_returns_content_and_strips(self) -> None:
        patcher = patch("sopno.llm.client._get_client")
        client = patcher.start()
        self.addCleanup(patcher.stop)
        client.return_value.chat.return_value = {
            "message": {"content": "  hello world  "}
        }
        reply = llm_client.single_reply([], mode=modes.AUTO)
        self.assertEqual(reply, "hello world")
        # auto resolves to the quick budget (see test_auto_falls_back_to_quick)
        self.assertEqual(client.return_value.chat.call_args.kwargs["think"], False)


class TestMessageAsDict(unittest.TestCase):
    def test_passthrough_for_dict(self) -> None:
        src = _fake_message()
        self.assertIs(llm_client.message_as_dict(src), src)

    def test_normalizes_object_preserving_thinking(self) -> None:
        class _Obj:
            role = "assistant"
            content = "say this"
            thinking = "trace"
            tool_calls = [{"function": {"name": "read_file"}}]

        data = llm_client.message_as_dict(_Obj())
        self.assertEqual(data["role"], "assistant")
        self.assertEqual(data["content"], "say this")
        self.assertEqual(data["thinking"], "trace")
        self.assertEqual(data["tool_calls"], [{"function": {"name": "read_file"}}])


if __name__ == "__main__":
    unittest.main()