"""
sopno/ui/hud/widgets.py
━━━━━━━━━━━━━━━━━━━━━━
Reusable HUD widgets: the Voice|Text segmented toggle and the chat thread.
"""

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sopno.ui.hud.icons import _paint_icon
from sopno.ui.hud.theme import _SEGMENT


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


class ChatThread(QScrollArea):
    """Clean scrolling conversation — one bubble per turn, no stacked mess."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.12);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._col = QVBoxLayout(self._inner)
        self._col.setContentsMargins(2, 2, 2, 2)
        self._col.setSpacing(8)
        self._col.addStretch(1)
        self.setWidget(self._inner)
        self._count = 0
        self._max_bubbles = 40
        self._tag_pt = 7
        self._body_pt = 9
        self._pad = 8
        self._radius = 12

    def apply_scale(self, *, tag_pt: int, body_pt: int, pad: int, radius: int, gap: int) -> None:
        self._tag_pt = tag_pt
        self._body_pt = body_pt
        self._pad = pad
        self._radius = radius
        self._col.setSpacing(gap)
        # Restyle existing bubbles
        for i in range(self._col.count() - 1):
            item = self._col.itemAt(i)
            bubble = item.widget() if item else None
            if not bubble:
                continue
            lay = bubble.layout()
            if lay:
                lay.setContentsMargins(pad, pad - 1, pad, pad - 1)
            for j in range(lay.count() if lay else 0):
                w = lay.itemAt(j).widget()
                if not isinstance(w, QLabel):
                    continue
                if j == 0:
                    w.setFont(QFont("IBM Plex Sans", tag_pt, QFont.Medium))
                else:
                    w.setFont(QFont("IBM Plex Sans", body_pt))
            is_user = "94, 177, 245" in bubble.styleSheet()
            bubble.setStyleSheet(self._bubble_css(is_user))

    def _bubble_css(self, is_user: bool) -> str:
        r = self._radius
        if is_user:
            return f"""
                QFrame#Bubble {{
                    background: rgba(94, 177, 245, 0.12);
                    border: 1px solid rgba(94, 177, 245, 0.18);
                    border-radius: {r}px;
                }}
            """
        return f"""
            QFrame#Bubble {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: {r}px;
            }}
        """

    def clear(self) -> None:
        while self._col.count() > 1:
            item = self._col.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._count = 0

    def add_message(self, role: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        bubble = QFrame()
        bubble.setObjectName("Bubble")
        is_user = role == "user"
        bubble.setStyleSheet(self._bubble_css(is_user))

        lay = QVBoxLayout(bubble)
        lay.setContentsMargins(self._pad, self._pad - 1, self._pad, self._pad - 1)
        lay.setSpacing(2)

        tag = QLabel("You" if is_user else "Sopno")
        tag.setFont(QFont("IBM Plex Sans", self._tag_pt, QFont.Medium))
        tag.setStyleSheet(
            "color: #6EA8D8; background: transparent;"
            if is_user else
            "color: #7A8AA3; background: transparent;"
        )
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setFont(QFont("IBM Plex Sans", self._body_pt))
        body.setStyleSheet("color: #D7DEE9; background: transparent;")

        lay.addWidget(tag)
        lay.addWidget(body)

        self._col.insertWidget(self._col.count() - 1, bubble)
        self._count += 1

        while self._count > self._max_bubbles and self._col.count() > 1:
            item = self._col.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
                self._count -= 1

        QTimer.singleShot(30, self._scroll_bottom)

    def _scroll_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
