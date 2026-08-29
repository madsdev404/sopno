"""
tests/ui/test_reasoning_selector.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the HUD reasoning-mode selector: a dedicated control distinct from
the Voice|Text HoloToggle (design §5.6). Offscreen — Qt core + widgets only.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from sopno.llm import modes
from sopno.ui.hud.widgets import ReasoningModeSelector

_APP = None


def _get_app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


class ReasoningSelectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _get_app()

    def test_defaults_to_auto(self) -> None:
        sel = ReasoningModeSelector()
        self.assertEqual(sel.current_mode(), modes.AUTO)

    def test_set_mode_selects_segment(self) -> None:
        sel = ReasoningModeSelector()
        sel.set_mode(modes.DEEP)
        self.assertEqual(sel.current_mode(), modes.DEEP)

    def test_unknown_mode_normalizes_to_auto(self) -> None:
        sel = ReasoningModeSelector()
        sel.set_mode("bogus-mode")
        self.assertEqual(sel.current_mode(), modes.AUTO)

    def test_click_emits_mode_selected(self) -> None:
        sel = ReasoningModeSelector()
        emitted: list[str] = []
        sel.mode_selected.connect(emitted.append)
        sel.set_mode(modes.THINKING, emit=True)
        self.assertEqual(emitted, [modes.THINKING])

    def test_set_mode_without_emit_stays_quiet(self) -> None:
        sel = ReasoningModeSelector()
        emitted: list[str] = []
        sel.mode_selected.connect(emitted.append)
        sel.set_mode(modes.QUICK)
        self.assertEqual(emitted, [])

    def test_apply_scale_survives(self) -> None:
        sel = ReasoningModeSelector()
        sel.apply_scale(pad_v=3, pad_h=8, font=9, radius=12)
        self.assertEqual(sel.current_mode(), modes.AUTO)


class WorkerBridgeTest(unittest.TestCase):
    def test_worker_exposes_set_reasoning_mode(self) -> None:
        from sopno.ui.hud.worker import AssistantWorker

        self.assertTrue(hasattr(AssistantWorker, "set_reasoning_mode"))


if __name__ == "__main__":
    unittest.main()