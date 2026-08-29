"""
tests/ui/test_reasoning_dropdown.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the HUD reasoning-mode dropdown: a holographic pill (HoloToggle
family) with a menu, distinct from the Voice|Text HoloToggle (design §5.6).
Offscreen — Qt core + widgets only.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from sopno.llm import modes
from sopno.ui.hud.widgets import ReasoningModeDropdown

_APP = None


def _get_app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


class ReasoningDropdownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _get_app()

    def test_defaults_to_auto(self) -> None:
        dd = ReasoningModeDropdown()
        self.assertEqual(dd.current_mode(), modes.AUTO)
        self.assertEqual(dd.checked_mode, modes.AUTO)

    def test_set_mode_selects(self) -> None:
        dd = ReasoningModeDropdown()
        dd.set_mode(modes.DEEP)
        self.assertEqual(dd.current_mode(), modes.DEEP)

    def test_menu_has_all_five_modes(self) -> None:
        dd = ReasoningModeDropdown()
        labels = [a.text() for a in dd.menu().actions()]
        self.assertEqual(
            labels,
            ["Auto", "Quick", "Thinking", "Deep", "Plan"],
        )

    def test_selecting_via_menu_action_sets_mode(self) -> None:
        dd = ReasoningModeDropdown()
        dd.set_mode(modes.AUTO)
        dd.menu().actions()[3].trigger()  # Deep
        self.assertEqual(dd.current_mode(), modes.DEEP)

    def test_unknown_mode_normalizes_to_auto(self) -> None:
        dd = ReasoningModeDropdown()
        dd.set_mode("bogus-mode")
        self.assertEqual(dd.current_mode(), modes.AUTO)

    def test_click_emits_mode_selected(self) -> None:
        dd = ReasoningModeDropdown()
        emitted: list[str] = []
        dd.mode_selected.connect(emitted.append)
        dd.set_mode(modes.THINKING, emit=True)
        self.assertEqual(emitted, [modes.THINKING])

    def test_set_mode_without_emit_stays_quiet(self) -> None:
        dd = ReasoningModeDropdown()
        emitted: list[str] = []
        dd.mode_selected.connect(emitted.append)
        dd.set_mode(modes.QUICK)
        self.assertEqual(emitted, [])

    def test_apply_scale_survives_compact(self) -> None:
        dd = ReasoningModeDropdown()
        dd.apply_scale(pad_v=3, pad_h=8, font=9, compact=True)
        self.assertEqual(dd.width(), 56)
        self.assertEqual(dd.current_mode(), modes.AUTO)

    def test_apply_scale_expand_label(self) -> None:
        dd = ReasoningModeDropdown()
        dd.apply_scale(pad_v=3, pad_h=8, font=10, compact=False)
        self.assertEqual(dd.width(), 96)


class WorkerBridgeTest(unittest.TestCase):
    def test_worker_exposes_set_reasoning_mode(self) -> None:
        from sopno.ui.hud.worker import AssistantWorker

        self.assertTrue(hasattr(AssistantWorker, "set_reasoning_mode"))


if __name__ == "__main__":
    unittest.main()