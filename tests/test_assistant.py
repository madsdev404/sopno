"""
tests/test_assistant.py
━━━━━━━━━━━━━━━━━━━━━━━━
Automated unit tests for Sopno context, dispatcher, and pipeline states.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.core.context import ConversationContext
from sopno.core.dispatcher import CommandDispatcher


class TestSopnoAssistantCore(unittest.TestCase):
    """Verifies core conversation history preservation, summarization triggering, and dispatcher routing."""

    def test_conversation_context_lifecycle(self) -> None:
        """Verify adding messages, language constraint generation, and resetting."""
        ctx = ConversationContext()
        self.assertEqual(len(ctx.raw_messages), 1)  # Initially just system prompt
        self.assertEqual(ctx.raw_messages[0]["role"], "system")

        # Add some messages
        ctx.add_user_message("Hello Sopno")
        ctx.add_assistant_message("Hello User")

        self.assertEqual(len(ctx.raw_messages), 3)
        self.assertEqual(ctx.raw_messages[1]["role"], "user")
        self.assertEqual(ctx.raw_messages[2]["role"], "assistant")

        # Language constraint test
        ctx.current_language = "bn"
        llm_msgs = ctx.get_messages_for_llm()
        self.assertEqual(len(llm_msgs), 4)
        self.assertEqual(llm_msgs[-1]["role"], "system")
        self.assertIn("Bangla", llm_msgs[-1]["content"])

        ctx.current_language = "en"
        llm_msgs = ctx.get_messages_for_llm()
        self.assertIn("English", llm_msgs[-1]["content"])

        # Reset
        ctx.reset()
        self.assertEqual(len(ctx.raw_messages), 1)

    def test_dispatcher_routing_patterns(self) -> None:
        """Verify that rule patterns map accurately to system tools."""
        dispatcher = CommandDispatcher()

        # 1. Date/Time query
        with patch("sopno.core.dispatcher.execute_tool") as mock_execute:
            dispatcher.dispatch("what is the current time?")
            mock_execute.assert_called_with("get_current_time", {})

        # 2. Open Application query
        with patch("sopno.core.dispatcher.execute_tool") as mock_execute:
            dispatcher.dispatch("open chrome")
            mock_execute.assert_called_with("open_application", {"app_name": "chrome"})

        # 3. Search query
        with patch("sopno.core.dispatcher.execute_tool") as mock_execute:
            dispatcher.dispatch("search for python list comprehension")
            mock_execute.assert_called_with("search_web", {"query": "python list comprehension"})

        # 4. Unknown query goes to LLM (returns None)
        res = dispatcher.dispatch("why is the sky blue?")
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
