"""
sopno/ui/hud/widgets/context_meter.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tiny conversation-context usage bar for the footer strip.
Green → amber → red as the window fills toward max_history_length.
"""

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QWidget


class ContextMeter(QWidget):
    """64×4 rounded bar showing how full the LLM context window is."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 4)
        self._ratio = 0.0

    def set_ratio(self, ratio: float) -> None:
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)

        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 2, 2)
        p.fillPath(track, QColor(255, 255, 255, 18))

        w = self.width() * self._ratio
        if w >= 1:
            if self._ratio < 0.7:
                color = QColor(74, 222, 154)
            elif self._ratio < 0.9:
                color = QColor(232, 200, 94)
            else:
                color = QColor(240, 113, 120)
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(0, 0, w, self.height()), 2, 2)
            color.setAlpha(160)
            p.fillPath(fill, color)

        p.end()
