"""
sopno/ui/hud/widgets/mode_toggle.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Glassmorphism segmented Voice | Text toggle.
"""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QPushButton

from sopno.ui.hud.visuals.icons import _paint_icon


class ModeToggle(QFrame):
    """Glassmorphism 2-segment pill toggle: voice | text."""

    mode_changed = pyqtSignal(str)

    _FRAME = """
        QFrame#ModeToggle {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: {r}px;
        }}
    """

    _BTN_ACTIVE = """
        QPushButton {{
            background: rgba(94, 177, 245, 0.30);
            border: 1px solid rgba(94, 177, 245, 0.50);
            border-radius: {r}px;
            padding: {pv}px {ph}px;
        }}
        QPushButton:hover {{
            background: rgba(94, 177, 245, 0.42);
            border-color: rgba(94, 177, 245, 0.65);
        }}
        QPushButton:pressed {{
            background: rgba(94, 177, 245, 0.55);
        }}
    """

    _BTN_IDLE = """
        QPushButton {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: {r}px;
            padding: {pv}px {ph}px;
        }}
        QPushButton:hover {{
            background: rgba(255, 255, 255, 0.10);
            border-color: rgba(255, 255, 255, 0.15);
        }}
        QPushButton:pressed {{
            background: rgba(255, 255, 255, 0.14);
        }}
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ModeToggle")
        self._pv = 4
        self._ph = 10
        self._icon_sz = 14
        self._frame_r = 12

        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(0)

        self.voice_btn = QPushButton()
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(True)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.setFocusPolicy(Qt.NoFocus)
        self.voice_btn.setFixedHeight(24)
        self.voice_btn.setToolTip("Voice mode")
        row.addWidget(self.voice_btn)

        self.text_btn = QPushButton()
        self.text_btn.setCheckable(True)
        self.text_btn.setCursor(Qt.PointingHandCursor)
        self.text_btn.setFocusPolicy(Qt.NoFocus)
        self.text_btn.setFixedHeight(24)
        self.text_btn.setToolTip("Text mode")
        row.addWidget(self.text_btn)

        self.voice_btn.clicked.connect(lambda: self._on_click("voice"))
        self.text_btn.clicked.connect(lambda: self._on_click("text"))
        self._apply_style()

    def apply_scale(self, *, pad_v: int = 4, pad_h: int = 10,
                    font: int = 10, icon: int = 14, radius: int = 12) -> None:
        self._pv = pad_v
        self._ph = pad_h
        self._icon_sz = icon
        self._frame_r = radius
        height = icon + pad_v * 2 + 8
        self.voice_btn.setFixedHeight(height)
        self.text_btn.setFixedHeight(height)
        self._apply_style()

    def set_mode(self, mode: str, *, emit: bool = False) -> None:
        mode = "text" if mode == "text" else "voice"
        self.voice_btn.setChecked(mode == "voice")
        self.text_btn.setChecked(mode == "text")
        self._apply_style()
        if emit:
            self.mode_changed.emit(mode)

    def _on_click(self, mode: str) -> None:
        self.set_mode(mode, emit=True)

    def _apply_style(self) -> None:
        r = self._frame_r
        self.setStyleSheet(self._FRAME.format(r=r))
        btn_r = max(6, r - 2)
        for btn, key, icon in (
            (self.voice_btn, "voice", "mic"),
            (self.text_btn, "text", "keyboard"),
        ):
            active = btn.isChecked()
            tpl = self._BTN_ACTIVE if active else self._BTN_IDLE
            btn.setIcon(_paint_icon(icon, self._icon_sz, active=active))
            btn.setIconSize(QSize(self._icon_sz, self._icon_sz))
            btn.setStyleSheet(tpl.format(r=btn_r, pv=self._pv, ph=self._ph))
