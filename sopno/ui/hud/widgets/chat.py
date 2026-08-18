"""
sopno/ui/hud/widgets/chat.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Clean scrolling conversation — one bubble per turn, no stacked mess.
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


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

        QTimer.singleShot(50, self._scroll_bottom)

    def _scroll_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
