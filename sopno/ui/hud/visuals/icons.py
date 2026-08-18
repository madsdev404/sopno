"""
sopno/ui/hud/visuals/icons.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Crisp vector icon painting for the HUD (no emoji).
"""

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _paint_icon(kind: str, size: int = 36, color: QColor | None = None, active: bool = False) -> QIcon:
    """Draw crisp vector glyphs (VS Code codicon density — 16px optical)."""
    if color is None:
        if kind.startswith("size-"):
            color = QColor("#5EB1F5") if active else QColor("#8B9BB4")
        else:
            color = QColor("#E8EEF7") if active else QColor("#A8B4C8")

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    # Hairline stroke like codicons — scales with canvas
    stroke = max(1.15, size * 0.085)
    p.setPen(QPen(color, stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)

    s = float(size)
    cx, cy = s / 2, s / 2

    if kind == "mic":
        mic = QRectF(cx - 4, cy - 9, 8, 12)
        p.drawRoundedRect(mic, 4, 4)
        p.drawArc(QRectF(cx - 8, cy - 4, 16, 14), 0 * 16, -180 * 16)
        p.drawLine(QPointF(cx, cy + 10), QPointF(cx, cy + 13))
        p.drawLine(QPointF(cx - 4, cy + 13), QPointF(cx + 4, cy + 13))
    elif kind == "keyboard":
        board = QRectF(cx - 10, cy - 7, 20, 14)
        p.drawRoundedRect(board, 2.5, 2.5)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        for row, cols in enumerate((4, 5, 3)):
            for i in range(cols):
                x = cx - (cols * 3.2) / 2 + i * 3.2 + 0.6
                y = cy - 4 + row * 3.6
                p.drawRoundedRect(QRectF(x, y, 2.2, 2.0), 0.4, 0.4)
    elif kind == "send":
        path = QPainterPath()
        path.moveTo(cx - 6, cy + 5)
        path.lineTo(cx + 7, cy)
        path.lineTo(cx - 6, cy - 5)
        path.lineTo(cx - 6, cy - 1)
        path.lineTo(cx + 1, cy)
        path.lineTo(cx - 6, cy + 1)
        path.closeSubpath()
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
    elif kind == "minimize":
        # Horizontal line (minimize to taskbar)
        y = cy + 1
        p.drawLine(QPointF(cx - 4, y), QPointF(cx + 4, y))
    elif kind == "maximize":
        # Full square (maximize)
        box = QRectF(cx - 5, cy - 5, 10, 10)
        p.drawRoundedRect(box, 1.5, 1.5)
    elif kind == "restore":
        # Overlapping squares (restore from maximize)
        box1 = QRectF(cx - 3, cy - 5, 8, 8)
        box2 = QRectF(cx - 5, cy - 3, 8, 8)
        p.drawRoundedRect(box1, 1.5, 1.5)
        p.drawRoundedRect(box2, 1.5, 1.5)
    elif kind == "half":
        # Vertical split (half view)
        box = QRectF(cx - 6, cy - 5, 12, 10)
        p.drawRoundedRect(box, 1.5, 1.5)
        p.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 5))
    elif kind == "close":
        # X (close)
        p.drawLine(QPointF(cx - 3.5, cy - 3.5), QPointF(cx + 3.5, cy + 3.5))
        p.drawLine(QPointF(cx + 3.5, cy - 3.5), QPointF(cx - 3.5, cy + 3.5))
    elif kind == "hide":
        # Horizontal line with up arrow (hide to tray)
        y = cy + 2
        p.drawLine(QPointF(cx - 3, y), QPointF(cx + 3, y))

    p.end()
    return QIcon(pm)
