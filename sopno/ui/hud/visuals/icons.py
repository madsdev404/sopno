"""
sopno/ui/hud/visuals/icons.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Icon rendering — Lucide SVGs for toggle/action icons,
hand-drawn VS Code–style for window controls.
"""

from PyQt5.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtSvg import QSvgRenderer

# ── Lucide SVG sources (toggle + action icons) ─────────────────────────

_SVG: dict[str, str] = {
    "bell": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/></svg>',
    "ear": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8.5a6.5 6.5 0 1 1 13 0c0 6-6 6-6 10a3.5 3.5 0 1 1-7 0"/><path d="M15 8.5a2.5 2.5 0 0 0-5 0v1a2 2 0 1 1 0 4"/></svg>',
    "mic": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19v3"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><rect x="9" y="2" width="6" height="13" rx="3"/></svg>',
    "newspaper": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18h-5"/><path d="M18 14h-8"/><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2"/><rect width="8" height="4" x="10" y="6" rx="1"/></svg>',
    "send": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/></svg>',
}

# ── VS Code–style window controls (hand-drawn) ────────────────────────

_pixmap_cache: dict[tuple[str, int, str], QPixmap] = {}


def _render_svg(kind: str, size: int, color: str) -> QPixmap:
    key = (kind, size, color)
    if key in _pixmap_cache:
        return _pixmap_cache[key]
    src = _SVG.get(kind, _SVG["send"])
    colored = src.replace('stroke="currentColor"', f'stroke="{color}"')
    renderer = QSvgRenderer(QByteArray(colored.encode()))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(p)
    p.end()
    _pixmap_cache[key] = pm
    return pm


def _paint_chrome(kind: str, size: int, color: QColor) -> QIcon:
    """Hand-drawn VS Code–style window control icons."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    stroke = max(1.0, size * 0.07)
    p.setPen(QPen(color, stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    s = float(size)
    cx, cy = s / 2, s / 2

    if kind == "minimize":
        y = cy + 1
        p.drawLine(QPointF(cx - 4, y), QPointF(cx + 4, y))
    elif kind == "maximize":
        box = QRectF(cx - 5, cy - 5, 10, 10)
        p.drawRoundedRect(box, 1.5, 1.5)
    elif kind == "restore":
        box1 = QRectF(cx - 3, cy - 5, 8, 8)
        box2 = QRectF(cx - 5, cy - 3, 8, 8)
        p.drawRoundedRect(box1, 1.5, 1.5)
        p.drawRoundedRect(box2, 1.5, 1.5)
    elif kind == "close":
        p.drawLine(QPointF(cx - 3.5, cy - 3.5), QPointF(cx + 3.5, cy + 3.5))
        p.drawLine(QPointF(cx + 3.5, cy - 3.5), QPointF(cx - 3.5, cy + 3.5))
    elif kind == "hide":
        p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))

    p.end()
    return QIcon(pm)


def _paint_icon(kind: str, size: int = 24, color: QColor | None = None, active: bool = False) -> QIcon:
    """Render icon — Lucide SVG for actions, hand-drawn for window controls."""
    if color is None:
        color = QColor("#FFFFFF") if active else QColor("#8899B0")

    if kind in ("minimize", "maximize", "restore", "close", "hide"):
        return _paint_chrome(kind, size, color)

    return QIcon(_render_svg(kind, size, color.name()))
