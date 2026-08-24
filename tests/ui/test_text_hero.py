"""
tests/ui/test_text_hero.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests for the empty-state hero: starter chips emit compose_requested,
collapse/reset lifecycle, and keyboard reachability.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from sopno.config.settings import settings
from sopno.ui.hud.widgets.text_hero import TextHero

_APP = None


def _get_app() -> QApplication:
    global _APP
    if QApplication.instance() is None:
        _APP = QApplication([])
    return _APP


class TextHeroTest(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        settings.hud_reduced_motion = True  # deterministic collapse (no tween)
        self.hero = TextHero()
        self.hero.resize(380, 400)
        self.hero.show()

    def tearDown(self) -> None:
        self.hero.deleteLater()

    def test_default_chips_built(self) -> None:
        self.assertGreaterEqual(len(self.hero._chips), 3)

    def test_chip_click_emits_compose_requested(self) -> None:
        self.hero.set_chips(["What can you do?", "System status"])
        received: list[str] = []
        self.hero.compose_requested.connect(received.append)
        self.hero._chips[1].click()
        self.assertEqual(received, ["System status"])

    def test_chips_are_keyboard_reachable(self) -> None:
        for chip in self.hero._chips:
            self.assertEqual(chip.focusPolicy(), Qt.StrongFocus)

    def test_collapse_hides(self) -> None:
        self.assertTrue(self.hero.isVisible())
        self.hero.collapse()
        self.assertFalse(self.hero.isVisible())

    def test_reset_restores_after_collapse(self) -> None:
        self.hero.collapse()
        self.assertFalse(self.hero.isVisible())
        self.hero.reset()
        self.assertTrue(self.hero.isVisible())

    def test_apply_scale_restyles_chips(self) -> None:
        self.hero.apply_scale(pt=12, pv=5, ph=14)
        # Greeting font grows with the scale request.
        self.assertEqual(self.hero.greeting.font().pointSize(), 12)
        # Chips restyled without changing their labels.
        labels = [c.text() for c in self.hero._chips]
        self.assertGreaterEqual(len(labels), 3)
        self.assertTrue(all(c.styleSheet() for c in self.hero._chips))

    def test_hero_has_no_face(self) -> None:
        # The robot face lives above the transcript; hero must not carry one.
        self.assertFalse(hasattr(self.hero, "face"))


if __name__ == "__main__":
    unittest.main()
