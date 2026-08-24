"""
sopno/ui/hud/widgets/text_hero.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Empty-state content for text mode: bilingual greeting + starter chips.
Chips fill the composer (they never auto-send). Collapses with a
220ms OutCubic fade the moment the conversation starts.

The robot face itself lives above the transcript (permanent presence);
the hero deliberately carries no second face.
"""

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sopno.ui.hud.visuals.theme import motion_enabled

_DEFAULT_CHIPS = (
    "What can you do?",
    "System status",
    "কী কী পারো বলো?",
)

_CHIP_QSS = """
    QPushButton {{
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 14px;
        padding: {pv}px {ph}px;
        color: #9AAABF;
        font-size: {pt}px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background: rgba(94, 177, 245, 0.14);
        border-color: rgba(94, 177, 245, 0.30);
        color: #D7E6F5;
    }}
"""


class TextHero(QWidget):
    """Greeting + starter chips shown while the transcript is empty."""

    compose_requested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        col = QVBoxLayout(self)
        col.setContentsMargins(12, 4, 12, 4)
        col.setSpacing(10)
        col.addStretch(1)

        self.greeting = QLabel("Ask me anything — English or Bangla.")
        self.greeting.setAlignment(Qt.AlignHCenter)
        self.greeting.setWordWrap(True)
        self.greeting.setFont(QFont("IBM Plex Sans", 10))
        self.greeting.setStyleSheet(
            "color: #9AAABF; background: transparent;"
        )
        col.addWidget(self.greeting, 0, Qt.AlignHCenter)

        self._chip_row = QWidget()
        self._chip_row.setStyleSheet("background: transparent;")
        self._chip_flow = QHBoxLayout(self._chip_row)
        self._chip_flow.setContentsMargins(0, 2, 0, 2)
        self._chip_flow.setSpacing(6)
        self._chips: list[QPushButton] = []
        self._chip_pt = 8
        self._chip_pv = 3
        self._chip_ph = 10
        self.set_chips(_DEFAULT_CHIPS)
        col.addWidget(self._chip_row, 0, Qt.AlignHCenter)

        col.addStretch(1)

        self._anim: QPropertyAnimation | None = None

    # ── Public API ────────────────────────────────────────────────────────
    def set_chips(self, labels) -> None:
        """Replace starter chips (labels of 1–3 strings look best)."""
        for chip in self._chips:
            self._chip_flow.removeWidget(chip)
            chip.deleteLater()
        self._chips.clear()
        for label in labels:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.StrongFocus)   # Tab-reachable; Space/Enter activates
            btn.clicked.connect(lambda _=False, t=label: self.compose_requested.emit(t))
            self._style_chip(btn)
            self._chip_flow.addWidget(btn)
            self._chips.append(btn)
        self._chip_flow.addStretch(1)

    def apply_scale(self, *, pt: int, pv: int, ph: int) -> None:
        self.greeting.setFont(QFont("IBM Plex Sans", pt))
        self._chip_pt = max(7, pt - 2)
        self._chip_pv = max(2, pv)
        self._chip_ph = ph
        for chip in self._chips:
            self._style_chip(chip)

    def collapse(self) -> None:
        """Fade away once the conversation starts."""
        if not self.isVisible():
            return
        if not motion_enabled():
            self.hide()
            return
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._anim = QPropertyAnimation(effect, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(lambda: (self.hide(), self.setGraphicsEffect(None)))
        self._anim.start()

    def reset(self) -> None:
        """Reappear when the thread empties again."""
        self.setGraphicsEffect(None)
        self.show()

    def enter(self) -> None:
        """Soft fade-in when first revealed."""
        if not self.isVisible() or not motion_enabled():
            return
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._anim = QPropertyAnimation(effect, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(lambda: self.setGraphicsEffect(None))
        self._anim.start()

    # ── Internals ────────────────────────────────────────────────────────
    def _style_chip(self, chip: QPushButton) -> None:
        chip.setStyleSheet(_CHIP_QSS.format(
            pv=self._chip_pv,
            ph=self._chip_ph,
            pt=self._chip_pt,
        ))
