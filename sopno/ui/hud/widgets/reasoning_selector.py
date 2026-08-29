"""
sopno/ui/hud/widgets/reasoning_selector.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Compact glass segmented reasoning-mode selector (Auto | Quick | Think |
Deep | Plan). A dedicated control — the Voice|Text HoloToggle is *never*
overloaded with a mode label (design §5.6). Emits the chosen mode; the HUD
pushes it into the assistant via `set_reasoning_mode()`.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QPushButton

from sopno.llm import modes

_LABELS = [
    (modes.AUTO, "Auto", "Auto — phrase hints choose the depth per turn"),
    (modes.QUICK, "Quick", "Quick — short, instant answers (fastest)"),
    (modes.THINKING, "Think", "Thinking — visible reasoning before the reply"),
    (modes.DEEP, "Deep", "Deep — large budget, hard analysis"),
    (modes.PLAN, "Plan", "Plan — plan-then-execute multi-step goals"),
]

_FRAME = """
    QFrame#ReasoningSelector {{
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: {r}px;
    }}
"""

_BTN_ACTIVE = """
    QPushButton {{
        background: rgba(155, 140, 242, 0.28);
        border: 1px solid rgba(155, 140, 242, 0.55);
        border-radius: {r}px;
        padding: {pv}px {ph}px;
        color: #E4DDFF;
        font-weight: 600;
        letter-spacing: 0.3px;
    }}
    QPushButton:hover {{ background: rgba(155, 140, 242, 0.40); }}
"""

_BTN_IDLE = """
    QPushButton {{
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: {r}px;
        padding: {pv}px {ph}px;
        color: #8B9BB4;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: rgba(255, 255, 255, 0.10); }}
"""


class ReasoningModeSelector(QFrame):
    """5-segment pill for quick/thinking/deep/plan/auto reasoning depth."""

    mode_selected = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ReasoningSelector")
        self._pv = 2
        self._ph = 6
        self._font = 8
        self._frame_r = 10

        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)

        self._segments: dict[str, QPushButton] = {}
        for mode, label, tip in _LABELS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _checked, m=mode: self._on_click(m))
            self._segments[mode] = btn
            row.addWidget(btn)

        self._current = modes.AUTO
        self._apply_style()

    def apply_scale(self, *, pad_v: int = 2, pad_h: int = 6,
                    font: int = 8, radius: int = 10) -> None:
        self._pv = pad_v
        self._ph = pad_h
        self._font = font
        self._frame_r = radius
        self._apply_style()

    def set_mode(self, mode: str, *, emit: bool = False) -> None:
        """Select a segment. With `emit`, triggers mode_selected."""
        mode = modes.normalize(mode) or modes.AUTO
        if mode == self._current and not emit:
            return
        self._current = mode
        self._apply_style()
        if emit:
            self.mode_selected.emit(mode)

    def current_mode(self) -> str:
        return self._current

    @property
    def checked_mode(self) -> str:
        return self._current

    def _on_click(self, mode: str) -> None:
        self.set_mode(mode, emit=True)

    def _apply_style(self) -> None:
        self.setStyleSheet(_FRAME.format(r=self._frame_r))
        btn_r = max(5, self._frame_r - 2)
        for mode, btn in self._segments.items():
            active = mode == self._current
            btn.setFont(self.font())
            btn.setFixedHeight(22)
            btn.setChecked(active)
            tpl = _BTN_ACTIVE if active else _BTN_IDLE
            btn.setStyleSheet(tpl.format(
                r=btn_r, pv=self._pv, ph=self._ph,
            ))