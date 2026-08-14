"""
sopno/ui/hud/widgets/mode_toggle.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Segmented Voice | Text control for switching how you talk to Sopno.
"""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton

from sopno.ui.hud.visuals.icons import _paint_icon
from sopno.ui.hud.visuals.theme import _SEGMENT


class ModeToggle(QFrame):
    """Segmented Voice | Text control (ChatGPT / Hub Talk style)."""

    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ModeToggle")
        self._pad_v = 4
        self._pad_h = 10
        self._font = 10
        self._icon = 12
        self._radius = 14
        self.setStyleSheet("""
            QFrame#ModeToggle {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(1)
        self._row = row

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self.voice_btn = QPushButton(" Voice")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.setFocusPolicy(Qt.NoFocus)
        self.voice_btn.setToolTip("Voice mode — speak to assistant")

        self.text_btn = QPushButton(" Text")
        self.text_btn.setCheckable(True)
        self.text_btn.setCursor(Qt.PointingHandCursor)
        self.text_btn.setFocusPolicy(Qt.NoFocus)
        self.text_btn.setToolTip("Text mode — type to assistant")

        self._group.addButton(self.voice_btn)
        self._group.addButton(self.text_btn)
        self.voice_btn.setChecked(True)

        row.addWidget(self.voice_btn)
        row.addWidget(self.text_btn)
        self._paint()

        self.voice_btn.clicked.connect(lambda: self._emit("voice"))
        self.text_btn.clicked.connect(lambda: self._emit("text"))

    def apply_scale(self, *, pad_v: int, pad_h: int, font: int, icon: int, radius: int) -> None:
        self._pad_v = pad_v
        self._pad_h = pad_h
        self._font = font
        self._icon = icon
        self._radius = radius
        self.setStyleSheet(f"""
            QFrame#ModeToggle {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {radius}px;
            }}
        """)
        self._paint()

    def _emit(self, mode: str) -> None:
        self.set_mode(mode, emit=True)

    def set_mode(self, mode: str, *, emit: bool = False) -> None:
        mode = "text" if mode == "text" else "voice"
        self.voice_btn.setChecked(mode == "voice")
        self.text_btn.setChecked(mode == "text")
        self._paint()
        if emit:
            self.mode_changed.emit(mode)

    def _paint(self) -> None:
        voice_on = self.voice_btn.isChecked()
        ics = max(20, self._icon + 8)
        self.voice_btn.setIcon(_paint_icon("mic", ics, active=voice_on))
        self.text_btn.setIcon(_paint_icon("keyboard", ics, active=not voice_on))
        self.voice_btn.setIconSize(QSize(self._icon, self._icon))
        self.text_btn.setIconSize(QSize(self._icon, self._icon))

        def style(active: bool, left: bool) -> str:
            # Capsule ends match frame radius
            r = max(6, self._radius - 2)
            radius = f"{r}px 5px 5px {r}px" if left else f"5px {r}px {r}px 5px"
            if active:
                return _SEGMENT.format(
                    bg="rgba(94, 177, 245, 0.22)",
                    fg="#E8F3FC",
                    hover_bg="rgba(94, 177, 245, 0.30)",
                    hover_fg="#FFFFFF",
                    radius=radius,
                    pad_v=self._pad_v,
                    pad_h=self._pad_h,
                    font_size=self._font,
                )
            return _SEGMENT.format(
                bg="transparent",
                fg="#7A8AA3",
                hover_bg="rgba(255, 255, 255, 0.05)",
                hover_fg="#C5D0E0",
                radius=radius,
                pad_v=self._pad_v,
                pad_h=self._pad_h,
                font_size=self._font,
            )

        self.voice_btn.setStyleSheet(style(voice_on, True))
        self.text_btn.setStyleSheet(style(not voice_on, False))
