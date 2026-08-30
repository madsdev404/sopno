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
from sopno.ui.hud.widgets import ModelDropdown, ReasoningModeDropdown

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


class ModelDropdownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _get_app()

    def test_defaults_to_config_model_name(self) -> None:
        from sopno.config.settings import settings

        dd = ModelDropdown()
        self.assertEqual(dd.current_model(), settings.model_name)

    def test_set_model_selects(self) -> None:
        from sopno.config.settings import settings

        dd = ModelDropdown()
        dd.set_model("qwen3:14b")
        self.assertEqual(dd.current_model(), "qwen3:14b")

    def test_unknown_model_falls_back_to_default(self) -> None:
        from sopno.config.settings import settings

        dd = ModelDropdown()
        dd.set_model("bogus-model")
        self.assertEqual(dd.current_model(), settings.model_name)

    def test_menu_lists_selectable_models(self) -> None:
        from sopno.config.settings import settings

        dd = ModelDropdown()
        labels = [a.text() for a in dd.menu().actions()]
        self.assertIn(settings.model_name, labels)
        self.assertEqual(labels[0], settings.model_name)

    def test_click_emits_model_selected(self) -> None:
        dd = ModelDropdown()
        emitted: list[str] = []
        dd.model_selected.connect(emitted.append)
        dd.set_model("qwen3:32b", emit=True)
        self.assertEqual(emitted, ["qwen3:32b"])

    def test_differs_from_mode_dropdown_signal(self) -> None:
        self.assertNotEqual(
            ModelDropdown().model_selected,
            ReasoningModeDropdown().mode_selected,
        )

    def test_compact_and_expand_sizes(self) -> None:
        dd = ModelDropdown()
        dd.apply_scale(pad_v=3, pad_h=8, font=9, compact=True)
        self.assertEqual(dd.width(), 56)
        dd.apply_scale(pad_v=3, pad_h=8, font=10, compact=False)
        self.assertEqual(dd.width(), 108)


class WorkerBridgeTest(unittest.TestCase):
    def test_worker_exposes_set_reasoning_mode(self) -> None:
        from sopno.ui.hud.worker import AssistantWorker

        self.assertTrue(hasattr(AssistantWorker, "set_reasoning_mode"))


if __name__ == "__main__":
    unittest.main()