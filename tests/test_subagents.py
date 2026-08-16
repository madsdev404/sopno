"""
tests/test_subagents.py
━━━━━━━━━━━━━━━━━━━━━━━
Subagent runners: agent inventory, restricted schemas, input validation, and
the mocked tool-calling loop.
"""

import unittest
from unittest.mock import patch

from sopno.config.settings import settings
from sopno.core import subagents as core
from sopno.tools.builtins import subagents as tool


class SubagentCoreTest(unittest.TestCase):
    def test_agent_inventory(self) -> None:
        agents = core.list_agents()
        self.assertEqual(set(agents), {"researcher", "coder", "reviewer"})

    def test_schema_restricted_per_agent(self) -> None:
        researcher = [t["function"]["name"] for t in core._schema_for("researcher")]
        coder = [t["function"]["name"] for t in core._schema_for("coder")]
        reviewer = [t["function"]["name"] for t in core._schema_for("reviewer")]
        self.assertIn("search_web", researcher)
        self.assertIn("fetch_url", researcher)
        self.assertNotIn("edit_file", researcher)
        self.assertIn("edit_file", coder)
        self.assertIn("run_terminal", coder)
        self.assertNotIn("write_file", reviewer)
        self.assertNotIn("run_terminal", reviewer)
        self.assertIn("git_diff", reviewer)
        self.assertNotIn("search_web", reviewer)

    def test_unknown_agent(self) -> None:
        self.assertIn("Unknown subagent", core.run_subagent("pirate", "go"))

    def test_empty_task(self) -> None:
        self.assertIn("task is empty", core.run_subagent("researcher", "  "))

    def test_oversized_task(self) -> None:
        self.assertIn("too long", core.run_subagent("researcher", "x" * 10000))

    def test_disabled(self) -> None:
        saved = settings.subagents_enabled
        settings.subagents_enabled = False
        try:
            self.assertIn("disabled", core.run_subagent("researcher", "hi"))
        finally:
            settings.subagents_enabled = saved


class SubagentLoopTest(unittest.TestCase):
    @patch("sopno.core.subagents.llm_chat")
    def test_plain_reply(self, mock_chat) -> None:
        mock_chat.return_value = {"message": {"role": "assistant",
                                              "content": "42 is the answer"}}
        out = core.run_subagent("researcher", "what is 6x7?")
        self.assertEqual(out, "42 is the answer")

    @patch("sopno.core.subagents.llm_chat")
    def test_tool_call_then_reply(self, mock_chat) -> None:
        first = {"message": {"role": "assistant",
                             "content": "",
                             "tool_calls": [{"function": {
                                 "name": "get_current_time", "arguments": {}}}]}}
        second = {"message": {"role": "assistant",
                              "content": "Done: the time was checked."}}
        mock_chat.side_effect = [first, second]

        out = core.run_subagent("reviewer", "check time")
        self.assertEqual(out, "Done: the time was checked.")
        # A tool message was fed back into the loop.
        sent = [call.args[0] for call in mock_chat.call_args_list]
        roles = [m["role"] for m in sent[1]]
        self.assertIn("tool", roles)
        tool_msgs = [m for m in sent[1] if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 1)

    @patch("sopno.core.subagents.llm_chat")
    def test_turn_limit(self, mock_chat) -> None:
        tool_call = {"message": {"role": "assistant",
                                 "content": "",
                                 "tool_calls": [{"function": {
                                     "name": "get_current_time",
                                     "arguments": {}}}]}}
        mock_chat.return_value = tool_call
        out = core.run_subagent("coder", "keep looping")
        self.assertIn("turn limit", out)

    @patch("sopno.core.subagents.llm_chat")
    def test_unknown_tool_from_llm_is_safe(self, mock_chat) -> None:
        first = {"message": {"role": "assistant",
                             "content": "",
                             "tool_calls": [{"function": {
                                 "name": "sudo_rm_rf", "arguments": {}}}]}}
        second = {"message": {"role": "assistant", "content": "not a real tool"}}
        mock_chat.side_effect = [first, second]
        out = core.run_subagent("coder", "try it")
        self.assertEqual(out, "not a real tool")
        tool_msgs = [m for m in mock_chat.call_args_list[1].args[0]
                     if m["role"] == "tool"]
        self.assertIn("not registered", tool_msgs[0]["content"])


class SubagentToolTest(unittest.TestCase):
    def test_tool_list(self) -> None:
        out = tool.subagent_list()
        self.assertIn("researcher", out)
        self.assertIn("reviewer", out)

    def test_tool_run_validation(self) -> None:
        self.assertIn("Unknown subagent", tool.run_subagent("x", "hi"))
        self.assertIn("task is empty", tool.run_subagent("coder", ""))


if __name__ == "__main__":
    unittest.main()
