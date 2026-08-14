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
    elif kind in ("size-small", "size-medium", "size-full"):
        # Same outer frame for equal optical weight (VS Code toolbar density)
        box = QRectF(cx - s * 0.32, cy - s * 0.28, s * 0.64, s * 0.56)
        r = s * 0.08
        p.drawRoundedRect(box, r, r)
        if kind == "size-medium":
            # Mid divider — denser content, same footprint
            mid = box.center().y()
            p.drawLine(
                QPointF(box.left() + s * 0.10, mid),
                QPointF(box.right() - s * 0.10, mid),
            )
        elif kind == "size-full":
            # Title-bar hairline (maximize)
            y = box.top() + s * 0.15
            p.drawLine(
                QPointF(box.left() + s * 0.08, y),
                QPointF(box.right() - s * 0.08, y),
            )

    p.end()
    return QIcon(pm)
