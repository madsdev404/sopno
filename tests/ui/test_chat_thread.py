"""
tests/ui/test_chat_thread.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the selectable rich-text ChatThread: native selection flags,
turn ordering/merging, typing-dots lifecycle, streaming caret contract,
trimming, and the no-timestamp / no-chrome guarantees.
"""

import os
import re
import unittest
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from sopno.config.settings import settings
from sopno.ui.hud.widgets.chat import ChatThread, _MAX_BLOCKS

_APP = None


def _get_app() -> QApplication:
    global _APP
    if QApplication.instance() is None:
        _APP = QApplication([])
    return _APP


class ChatThreadTestBase(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        settings.hud_reduced_motion = True  # deterministic rendering
        self.thread = ChatThread()
        self.thread.resize(380, 560)

    def tearDown(self) -> None:
        self.thread.deleteLater()


class NativeSelectionTest(ChatThreadTestBase):
    def test_selectable_by_mouse_and_keyboard(self) -> None:
        flags = self.thread.textInteractionFlags()
        self.assertTrue(flags & Qt.TextSelectableByMouse)
        self.assertTrue(flags & Qt.TextSelectableByKeyboard)

    def test_select_all_then_copy_puts_text_in_clipboard(self) -> None:
        from PyQt5.QtWidgets import QApplication as QA
        self.thread.add_message("user", "copy me please")
        self.thread.selectAll()
        self.thread.copy()
        self.assertIn("copy me please", QA.clipboard().text())


class TranscriptTest(ChatThreadTestBase):
    def test_transcript_empty_thread(self) -> None:
        self.assertEqual(self.thread.transcript_text(), "")

    def test_transcript_order_and_attribution(self) -> None:
        self.thread.add_message("user", "hello")
        self.thread.add_message("assistant", "hi there")
        text = self.thread.transcript_text()
        lines = text.split("\n\n")
        self.assertEqual(lines[0], "You: hello")
        self.assertEqual(lines[1], "Sopno: hi there")

    def test_consecutive_same_role_are_separate_blocks(self) -> None:
        self.thread.add_message("user", "first part")
        self.thread.add_message("user", "second part")
        self.assertEqual(len(self.thread._blocks), 2)
        self.assertEqual(self.thread._blocks[0]["text"], "first part")
        self.assertEqual(self.thread._blocks[1]["text"], "second part")

    def test_error_rows_attributed(self) -> None:
        self.thread.add_message("error", "boom")
        self.assertIn("Error: boom", self.thread.transcript_text())

    def test_interrupted_marker_in_transcript(self) -> None:
        self.thread.add_message("assistant", "partial ans", streaming=True)
        self.thread.finalize_streaming(interrupted=True)
        self.assertIn("(interrupted)", self.thread.transcript_text())

    def test_empty_text_ignored_unless_streaming(self) -> None:
        self.assertIsNone(self.thread.add_message("user", "   "))
        self.assertTrue(self.thread.is_empty)
        self.thread.add_message("assistant", "", streaming=True)
        self.assertFalse(self.thread.is_empty)


class NoChromeTest(ChatThreadTestBase):
    """The page belongs to the text: zero chrome inside the transcript."""

    def test_no_timestamps_rendered_even_when_ts_given(self) -> None:
        self.thread.add_message("user", "stamped?", ts=datetime(2026, 8, 25, 14, 30))
        self.thread.add_message("assistant", "no stamps anymore")
        plain = self.thread.toPlainText()
        self.assertIsNone(re.search(r"\d{2}:\d{2}", plain))

    def test_plain_text_contains_message(self) -> None:
        self.thread.add_message("assistant", "plain text only")
        self.assertIn("plain text only", self.thread.toPlainText())


class TypingDotsTest(ChatThreadTestBase):
    def test_begin_typing_shows_dots(self) -> None:
        self.thread.begin_typing()
        self.assertTrue(self.thread._typing)
        self.assertGreater(len(self.thread.toPlainText().strip()), 0)

    def test_end_typing_clears_dots(self) -> None:
        self.thread.begin_typing()
        self.thread.end_typing()
        self.assertFalse(self.thread._typing)

    def test_add_message_closes_typing_state(self) -> None:
        self.thread.begin_typing()
        self.thread.add_message("assistant", "answer arrived")
        self.assertFalse(self.thread._typing)


class StreamingTest(ChatThreadTestBase):
    def test_streaming_block_shows_text(self) -> None:
        self.thread.add_message("assistant", "partial", streaming=True)
        self.assertIn("partial", self.thread.toPlainText())

    def test_finalize_keeps_text(self) -> None:
        self.thread.add_message("assistant", "partial", streaming=True)
        self.thread.finalize_streaming(interrupted=False)
        self.assertIn("partial", self.thread.toPlainText())

    def test_append_stream_text_grows_open_block(self) -> None:
        self.thread.add_message("assistant", "he", streaming=True)
        self.thread.append_stream_text("llo")
        self.assertEqual(self.thread._blocks[-1]["text"], "hello")

    def test_append_creates_assistant_block_if_missing(self) -> None:
        self.thread.append_stream_text("orphan chunk")
        self.assertEqual(self.thread._blocks[-1]["role"], "assistant")


class TrimAndClearTest(ChatThreadTestBase):
    def test_cap_trims_oldest_blocks(self) -> None:
        for i in range(_MAX_BLOCKS + 10):
            self.thread.add_message("user" if i % 2 == 0 else "assistant", f"m{i}")
        self.assertLessEqual(len(self.thread._blocks), _MAX_BLOCKS)
        self.assertNotIn("m0", self.thread.transcript_text())
        self.assertIn(f"m{_MAX_BLOCKS + 9}", self.thread.transcript_text())

    def test_clear_chat_resets_everything(self) -> None:
        self.thread.begin_typing()
        self.thread.clear_chat()
        self.assertTrue(self.thread.is_empty)
        self.assertFalse(self.thread._typing)
        self.assertEqual(self.thread.transcript_text(), "")


if __name__ == "__main__":
    unittest.main()
