"""
sopno/ui/hud.py
━━━━━━━━━━━━━━━
Mature floating companion HUD for Sopno.

Layout: header (size presets) → robot → clean chat thread →
Voice|Text segmented dock → status log.
Supports Full / Medium / Small presets plus edge drag-resize.
"""

from __future__ import annotations

import math
import os
import random
import sys
import threading
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsDropShadowEffect,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QLineEdit,
    QFrame,
    QSizePolicy,
    QScrollArea,
    QButtonGroup,
)
from PyQt5.QtCore import (
    Qt,
    pyqtSignal,
    QObject,
    QPoint,
    QRect,
    QFileSystemWatcher,
    QTimer,
    QRectF,
    QPointF,
    QSize,
)
from PyQt5.QtGui import (
    QFont,
    QColor,
    QIcon,
    QPixmap,
    QPainter,
    QPen,
    QBrush,
    QRadialGradient,
    QPainterPath,
)

from sopno.config.settings import settings
from sopno.core.assistant import SopnoAssistant

# Preset panel sizes (width × height). User can also free-drag edges.
SIZE_PRESETS = {
    "small":  (280, 360),
    "medium": (380, 560),
    "full":   (520, 740),
}
MIN_SIZE = (260, 320)
MAX_SIZE = (720, 960)
EDGE = 8  # px hit-zone for drag-resize

STATUS_COPY = {
    "standby":   ("Idle", "#8B9BB4"),
    "listening": ("Listening", "#5EB1F5"),
    "thinking":  ("Thinking", "#9B8CF2"),
    "speaking":  ("Speaking", "#4ADE9A"),
    "error":     ("Error", "#F07178"),
}

STATE_ACCENT = {
    "standby":   QColor(139, 155, 180),
    "listening": QColor(94, 177, 245),
    "thinking":  QColor(155, 140, 242),
    "speaking":  QColor(74, 222, 154),
    "error":     QColor(240, 113, 120),
}

_CHROME = """
    QPushButton {{
        background: transparent;
        color: #5C6B82;
        border: none;
        font-size: {font_size}px;
        font-weight: 500;
        padding: 0px;
    }}
    QPushButton:hover {{ color: {hover}; }}
"""

# VS Code–style toolbar icon button (codicon density: 22px hit, quiet hover)
_TOOL_ICON = """
    QPushButton {{
        background: {bg};
        border: none;
        border-radius: 5px;
        padding: 0px;
    }}
    QPushButton:hover {{
        background: rgba(255, 255, 255, 0.08);
    }}
    QPushButton:pressed {{
        background: rgba(255, 255, 255, 0.12);
    }}
"""

_SEGMENT = """
    QPushButton {{
        background: {bg};
        color: {fg};
        border: none;
        border-radius: {radius};
        padding: {pad_v}px {pad_h}px;
        font-size: {font_size}px;
        font-weight: 600;
        letter-spacing: 0.2px;
    }}
    QPushButton:hover {{
        background: {hover_bg};
        color: {hover_fg};
    }}
"""

_ICON_BTN = """
    QPushButton {{
        background: {bg};
        border: 1px solid {border};
        border-radius: 18px;
        padding: 0px;
    }}
    QPushButton:hover {{
        background: {hover_bg};
        border-color: {hover_border};
    }}
    QPushButton:pressed {{
        background: {pressed_bg};
    }}
"""


# ── Icon painting (crisp vector glyphs, no emoji) ─────────────────────────────

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



class AliveRobotFace(QWidget):
    """Parametric robot face — blinks, glances, speaks, reacts to state."""

    def __init__(self, parent=None, size: int = 120) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.state = "standby"
        self._t = 0.0
        self._blink = 0.0
        self._blink_closing = False
        self._next_blink = 2.4
        self._gaze = QPointF(0.0, 0.0)
        self._gaze_target = QPointF(0.0, 0.0)
        self._next_gaze = 1.6
        self._mouth = 0.12
        self._breath = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_state(self, state: str) -> None:
        state = (state or "standby").lower().strip()
        if state not in STATE_ACCENT:
            state = "standby"
        if state != self.state:
            self.state = state
            if state in ("listening", "speaking"):
                self._gaze_target = QPointF(0.0, 0.05)
            elif state == "thinking":
                self._gaze_target = QPointF(0.35, -0.15)

    def set_face_size(self, size: int) -> None:
        self.setFixedSize(size, size)
        self.update()

    def _tick(self) -> None:
        dt = 0.033
        self._t += dt
        self._breath = 0.5 + 0.5 * math.sin(self._t * 1.4)

        self._next_blink -= dt
        if self._next_blink <= 0 and self._blink <= 0:
            self._blink_closing = True
            self._next_blink = random.uniform(2.2, 5.5)

        if self._blink_closing:
            self._blink = min(1.0, self._blink + dt * 10)
            if self._blink >= 1.0:
                self._blink_closing = False
        elif self._blink > 0:
            self._blink = max(0.0, self._blink - dt * 8)

        self._next_gaze -= dt
        if self._next_gaze <= 0 and self.state == "standby":
            self._gaze_target = QPointF(
                random.uniform(-0.45, 0.45),
                random.uniform(-0.25, 0.3),
            )
            self._next_gaze = random.uniform(1.4, 3.2)
        elif self.state == "listening":
            self._gaze_target = QPointF(
                0.08 * math.sin(self._t * 2.1),
                0.06 + 0.04 * math.sin(self._t * 1.3),
            )
        elif self.state == "thinking":
            self._gaze_target = QPointF(
                0.4 * math.sin(self._t * 0.9),
                -0.2 + 0.08 * math.sin(self._t * 1.7),
            )

        self._gaze.setX(self._gaze.x() + (self._gaze_target.x() - self._gaze.x()) * 0.12)
        self._gaze.setY(self._gaze.y() + (self._gaze_target.y() - self._gaze.y()) * 0.12)

        if self.state == "speaking":
            target = 0.25 + 0.55 * abs(math.sin(self._t * 11.0)) * abs(math.sin(self._t * 4.3))
        elif self.state == "listening":
            target = 0.08 + 0.04 * self._breath
        elif self.state == "thinking":
            target = 0.05
        elif self.state == "error":
            target = 0.02
        else:
            target = 0.1 + 0.04 * self._breath

        self._mouth += (target - self._mouth) * 0.28
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        accent = STATE_ACCENT[self.state]
        a = accent

        aura_r = min(w, h) * (0.48 + 0.04 * self._breath)
        if self.state == "listening":
            aura_r *= 1.0 + 0.06 * abs(math.sin(self._t * 5))
        glow = QRadialGradient(cx, cy, aura_r)
        glow.setColorAt(0.0, QColor(a.red(), a.green(), a.blue(), 48 if self.state != "standby" else 22))
        glow.setColorAt(0.55, QColor(a.red(), a.green(), a.blue(), 10))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), aura_r, aura_r)

        head_w = w * 0.62
        head_h = h * 0.68
        head = QRectF(cx - head_w / 2, cy - head_h / 2 + h * 0.02, head_w, head_h)
        radius = head_w * 0.28

        head_grad = QRadialGradient(cx, cy - head_h * 0.15, head_w * 0.75)
        head_grad.setColorAt(0.0, QColor(28, 36, 52))
        head_grad.setColorAt(1.0, QColor(14, 20, 32))
        p.setBrush(QBrush(head_grad))
        p.setPen(QPen(QColor(148, 163, 184, 32), 1.0))
        p.drawRoundedRect(head, radius, radius)

        panel = head.adjusted(head_w * 0.1, head_h * 0.14, -head_w * 0.1, -head_h * 0.12)
        p.setBrush(QColor(7, 10, 18, 230))
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 40), 1.0))
        p.drawRoundedRect(panel, radius * 0.55, radius * 0.55)

        ant_y = head.top() - h * 0.02
        p.setPen(QPen(QColor(60, 72, 90), 1.8))
        p.drawLine(QPointF(cx, head.top() + 2), QPointF(cx, ant_y))
        pulse = 0.55 + 0.45 * self._breath
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(a.red(), a.green(), a.blue(), int(170 * pulse)))
        p.drawEllipse(QPointF(cx, ant_y - 3), 3.2, 3.2)

        ear_pulse = 1.0 + (0.12 * abs(math.sin(self._t * 6)) if self.state == "listening" else 0)
        ear_h = head_h * 0.22 * ear_pulse
        ear_w = head_w * 0.08
        p.setBrush(QColor(28, 36, 52))
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 70 if self.state == "listening" else 28), 1))
        p.drawRoundedRect(QRectF(head.left() - ear_w * 0.7, cy - ear_h / 2, ear_w, ear_h), 3, 3)
        p.drawRoundedRect(QRectF(head.right() - ear_w * 0.3, cy - ear_h / 2, ear_w, ear_h), 3, 3)

        eye_y = panel.center().y() - panel.height() * 0.12
        eye_dx = panel.width() * 0.22
        eye_w = panel.width() * 0.18
        eye_h = panel.height() * 0.22 * (1.0 - 0.92 * self._blink)
        eye_h = max(1.5, eye_h)

        for side in (-1, 1):
            self._draw_eye(p, panel.center().x() + side * eye_dx, eye_y, eye_w, eye_h, accent)

        if self.state == "thinking":
            scan_y = panel.top() + panel.height() * ((math.sin(self._t * 2.2) + 1) / 2)
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 80), 1.2))
            p.drawLine(QPointF(panel.left() + 6, scan_y), QPointF(panel.right() - 6, scan_y))

        mouth_cx = panel.center().x()
        mouth_cy = panel.bottom() - panel.height() * 0.28
        mouth_w = panel.width() * (0.28 + 0.12 * self._mouth)
        mouth_h = panel.height() * (0.06 + 0.22 * self._mouth)

        if self.state == "error":
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 190), 1.8, Qt.SolidLine, Qt.RoundCap))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w * 0.55, mouth_cy + 3)
            path.quadTo(mouth_cx, mouth_cy - 4, mouth_cx + mouth_w * 0.55, mouth_cy + 3)
            p.drawPath(path)
        elif self._mouth < 0.18:
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 160), 1.8, Qt.SolidLine, Qt.RoundCap))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w * 0.5, mouth_cy)
            path.quadTo(mouth_cx, mouth_cy + 5, mouth_cx + mouth_w * 0.5, mouth_cy)
            p.drawPath(path)
        else:
            mouth = QRectF(mouth_cx - mouth_w / 2, mouth_cy - mouth_h / 2, mouth_w, mouth_h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(2, 6, 14))
            p.drawRoundedRect(mouth, mouth_h * 0.45, mouth_h * 0.45)
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 140), 1.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(mouth, mouth_h * 0.45, mouth_h * 0.45)

        if self.state == "listening":
            for i in range(2):
                rr = min(w, h) * (0.38 + 0.08 * i) + 4 * abs(math.sin(self._t * 4 + i))
                p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), int(42 - i * 14)), 1.0))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), rr, rr)

        p.end()

    def _draw_eye(self, p: QPainter, cx: float, cy: float, ew: float, eh: float, accent: QColor) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(2, 6, 14))
        p.drawRoundedRect(QRectF(cx - ew / 2, cy - eh / 2, ew, eh), eh * 0.45, eh * 0.45)

        if self._blink > 0.85:
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 150), 1.5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - ew * 0.35, cy), QPointF(cx + ew * 0.35, cy))
            return

        iris_r = min(ew, eh) * 0.38
        ix = cx + self._gaze.x() * ew * 0.22
        iy = cy + self._gaze.y() * eh * 0.22

        iris = QRadialGradient(ix, iy, iris_r)
        iris.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 220))
        iris.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(), 120))
        iris.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setBrush(QBrush(iris))
        p.drawEllipse(QPointF(ix, iy), iris_r, iris_r)

        p.setBrush(QColor(8, 12, 22))
        p.drawEllipse(QPointF(ix, iy), iris_r * 0.42, iris_r * 0.42)
        p.setBrush(QColor(255, 255, 255, 170))
        p.drawEllipse(QPointF(ix - iris_r * 0.28, iy - iris_r * 0.28), iris_r * 0.18, iris_r * 0.18)




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
        self.voice_btn.setToolTip("Voice mode — speak to Sopno")

        self.text_btn = QPushButton(" Text")
        self.text_btn.setCheckable(True)
        self.text_btn.setCursor(Qt.PointingHandCursor)
        self.text_btn.setFocusPolicy(Qt.NoFocus)
        self.text_btn.setToolTip("Text mode — type to Sopno")

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


class AssistantWorker(QObject):
    status_changed  = pyqtSignal(str)
    speech_detected = pyqtSignal(str)
    reply_generated = pyqtSignal(str)
    log_message     = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.assistant = SopnoAssistant(
            status_callback=lambda status: self.status_changed.emit(status),
            speech_callback=lambda text: self.speech_detected.emit(text),
            reply_callback=lambda reply: self.reply_generated.emit(reply),
            log_callback=lambda msg: self.log_message.emit(msg),
        )

    @property
    def running(self) -> bool:
        return self.assistant.running

    @running.setter
    def running(self, value: bool) -> None:
        self.assistant.running = value

    def start_loop(self) -> None:
        self.assistant.run()

    def stop(self) -> None:
        self.assistant.stop()

    def set_mode(self, mode: str) -> None:
        self.assistant.set_interaction_mode(mode)

    def submit_text(self, text: str) -> None:
        self.assistant.submit_text(text)


class SopnoHUDWindow(QMainWindow):
    """Floating companion panel — preset sizes + drag-resize."""

    def __init__(self) -> None:
        super().__init__()
        self.old_pos = None
        self._resize_edge = None
        self._press_geo = None
        self._press_global = None
        self.size_mode = "medium"
        self.interaction_mode = "voice"
        self.current_status = "listening"
        self._listen_hint = "Listening… say something"

        self.init_ui()
        self.init_tray()

        self.worker = AssistantWorker()
        self.thread = threading.Thread(target=self.worker.start_loop, daemon=True)
        self.worker.status_changed.connect(self.update_status)
        self.worker.speech_detected.connect(self.update_user_speech)
        self.worker.reply_generated.connect(self.update_sopno_reply)
        self.worker.log_message.connect(self.update_log)
        self.thread.start()

    def init_ui(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysShowToolTips, True)
        self.setMinimumSize(*MIN_SIZE)
        self.setMaximumSize(*MAX_SIZE)
        self.setMouseTracking(True)

        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setMouseTracking(True)
        self.central_widget.setStyleSheet(f"""
            QWidget#CentralWidget {{
                background-color: rgba(12, 16, 24, {settings.hud_opacity});
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 24px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 8)
        self.central_widget.setGraphicsEffect(shadow)

        root = QVBoxLayout(self.central_widget)
        root.setContentsMargins(12, 8, 8, 8)
        root.setSpacing(0)
        self._root = root

        # ── Header (compact chrome) ───────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self._header = header

        self.context_label = QLabel(self._listen_hint)
        self.context_label.setFont(QFont("IBM Plex Sans", 8))
        self.context_label.setStyleSheet("color: #6B7C94; background: transparent;")
        self.context_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.context_label.setMaximumHeight(20)

        self._size_btns: dict[str, QPushButton] = {}
        tips = {
            "small": "Small panel",
            "medium": "Medium panel",
            "full": "Full panel",
        }

        chrome = QHBoxLayout()
        chrome.setSpacing(0)
        chrome.setContentsMargins(0, 0, 0, 0)
        chrome.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._chrome = chrome

        for key in ("small", "medium", "full"):
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setIconSize(QSize(14, 14))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setToolTip(tips[key])
            btn.setIcon(_paint_icon(f"size-{key}", 14, active=False))
            btn.clicked.connect(lambda _=False, k=key: self.apply_size_preset(k))
            self._size_btns[key] = btn
            chrome.addWidget(btn, 0, Qt.AlignVCenter)

        self.hide_btn = self._chrome_btn(
            "−", "#E8A0BF", "Hide to system tray", size=22, font_size=14,
        )
        self.hide_btn.clicked.connect(self.hide_hud)

        self.close_btn = self._chrome_btn(
            "×", "#F07178", "Close Sopno", size=22, font_size=14,
        )
        self.close_btn.clicked.connect(self.close_app)

        chrome.addWidget(self.hide_btn, 0, Qt.AlignVCenter)
        chrome.addWidget(self.close_btn, 0, Qt.AlignVCenter)

        header.addWidget(self.context_label, 1)
        header.addLayout(chrome)
        root.addLayout(header)
        root.addSpacing(4)

        # ── Robot stage ───────────────────────────────────────────────────────
        stage = QVBoxLayout()
        stage.setSpacing(2)
        stage.setAlignment(Qt.AlignCenter)

        self.robot = AliveRobotFace(size=100)
        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("IBM Plex Sans", 9, QFont.Medium))
        self.status_label.setStyleSheet(
            "color: #8B9BB4; background: transparent; letter-spacing: 0.5px;"
        )

        stage.addWidget(self.robot, 0, Qt.AlignCenter)
        stage.addWidget(self.status_label)
        root.addLayout(stage)
        root.addSpacing(8)

        # ── Clean conversation thread ─────────────────────────────────────────
        self.chat = ChatThread()
        self.chat.setMinimumHeight(80)
        root.addWidget(self.chat, 1)
        root.addSpacing(10)

        # ── Mode toggle (Voice | Text) ─────────────────────────────────────────
        self.mode_toggle = ModeToggle()
        self.mode_toggle.mode_changed.connect(self.set_interaction_mode)
        root.addWidget(self.mode_toggle, 0, Qt.AlignHCenter)
        root.addSpacing(8)

        # ── Composer (text mode only) ─────────────────────────────────────────
        self.dock = QFrame()
        self.dock.setObjectName("Dock")
        self.dock.setStyleSheet("""
            QFrame#Dock {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 18px;
            }
        """)
        dock_row = QHBoxLayout(self.dock)
        dock_row.setContentsMargins(10, 6, 6, 6)
        dock_row.setSpacing(6)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Message Sopno…")
        self.text_input.setToolTip("Type a message and press Enter to send")
        self.text_input.setFont(QFont("IBM Plex Sans", 10))
        self.text_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #E4EAF2;
                border: none;
                padding: 6px 4px;
                selection-background-color: rgba(94, 177, 245, 0.35);
            }
        """)
        self.text_input.returnPressed.connect(self.send_text_message)

        self.send_btn = self._circle_btn("send", tip="Send message", active=False, accent=False)
        self.send_btn.clicked.connect(self.send_text_message)

        dock_row.addWidget(self.text_input, 1)
        dock_row.addWidget(self.send_btn, 0, Qt.AlignVCenter)
        root.addWidget(self.dock)
        root.addSpacing(6)

        self.log_display = QLabel("Starting…")
        self.log_display.setAlignment(Qt.AlignCenter)
        self.log_display.setFont(QFont("IBM Plex Mono", 7))
        self.log_display.setStyleSheet("color: #3F4D63; background: transparent;")
        self.log_display.setWordWrap(True)
        root.addWidget(self.log_display)

        # Resize grip hint (bottom-right)
        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        self.resize_hint = QLabel("⋰")
        self.resize_hint.setToolTip("Drag edges or corner to resize")
        self.resize_hint.setStyleSheet("color: #3A4658; background: transparent; font-size: 11px;")
        self.resize_hint.setFixedSize(16, 14)
        grip_row.addWidget(self.resize_hint)
        root.addLayout(grip_row)

        self.setCentralWidget(self.central_widget)
        self.apply_size_preset("medium", anchor_top_right=True)
        self._apply_mode_layout()
        self.position_hud()

    def _chrome_btn(
        self,
        text: str,
        hover: str,
        tip: str,
        *,
        size: int = 22,
        font_size: int = 14,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(size, size)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(tip)
        btn.setStyleSheet(_CHROME.format(hover=hover, font_size=font_size))
        btn.setProperty("hover_color", hover)
        return btn

    def _circle_btn(self, kind: str, *, tip: str, active: bool, accent: bool) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(32, 32)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(tip)
        btn.setIcon(_paint_icon(kind, 32, active=active))
        btn.setProperty("icon_kind", kind)
        bg, border = "rgba(255, 255, 255, 0.04)", "rgba(255, 255, 255, 0.08)"
        hbg, hb = "rgba(255, 255, 255, 0.08)", "rgba(255, 255, 255, 0.14)"
        pbg = "rgba(255, 255, 255, 0.12)"
        btn.setStyleSheet(_ICON_BTN.format(
            bg=bg, border=border, hover_bg=hbg, hover_border=hb, pressed_bg=pbg,
        ))
        return btn

    def _metrics_for_width(self, w: int) -> dict:
        """Responsive tokens from panel width (works for presets + drag-resize)."""
        if w < 320:
            return dict(
                margin=8, gap=4, chrome=20, icon=12, chrome_font=12,
                context_pt=8, face=56, status_pt=7, tag_pt=7, body_pt=8,
                bubble_pad=7, bubble_r=10, bubble_gap=6, log_pt=6,
                send=28, send_icon=14, mode_pad_v=3, mode_pad_h=8,
                mode_font=9, mode_icon=11, mode_r=12, show_status=False, show_log=False,
                hint="Listening…",
            )
        if w < 440:
            return dict(
                margin=10, gap=6, chrome=22, icon=14, chrome_font=13,
                context_pt=8, face=78, status_pt=8, tag_pt=7, body_pt=9,
                bubble_pad=8, bubble_r=12, bubble_gap=7, log_pt=6,
                send=30, send_icon=15, mode_pad_v=4, mode_pad_h=10,
                mode_font=10, mode_icon=12, mode_r=14, show_status=True, show_log=True,
                hint="Listening… say something",
            )
        return dict(
            margin=14, gap=8, chrome=24, icon=15, chrome_font=14,
            context_pt=9, face=110, status_pt=9, tag_pt=8, body_pt=10,
            bubble_pad=10, bubble_r=14, bubble_gap=8, log_pt=7,
            send=34, send_icon=17, mode_pad_v=5, mode_pad_h=12,
            mode_font=11, mode_icon=13, mode_r=16, show_status=True, show_log=True,
            hint="Listening… say something",
        )

    def _apply_responsive(self) -> None:
        """Scale header, type, icons, robot, chat to current window size."""
        if not hasattr(self, "context_label"):
            return
        m = self._metrics_for_width(self.width())
        self._metrics = m
        self._listen_hint = m["hint"]

        # Shell margins + softer radius on small panels
        pad = m["margin"]
        self._root.setContentsMargins(pad, pad - 2, pad - 2, pad - 2)
        radius = 16 if self.width() < 320 else (20 if self.width() < 440 else 24)
        self.central_widget.setStyleSheet(f"""
            QWidget#CentralWidget {{
                background-color: rgba(12, 16, 24, {settings.hud_opacity});
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {radius}px;
            }}
        """)

        # Compact header text + chrome
        self.context_label.setFont(QFont("IBM Plex Sans", m["context_pt"]))
        self.context_label.setMaximumHeight(m["chrome"] + 2)
        if self.interaction_mode == "voice" and self.current_status in ("standby", "listening"):
            self.context_label.setText(self._listen_hint)

        c = m["chrome"]
        ic = m["icon"]
        for key, btn in self._size_btns.items():
            btn.setFixedSize(c, c)
            btn.setIconSize(QSize(ic, ic))

        for btn, hover in (
            (self.hide_btn, "#E8A0BF"),
            (self.close_btn, "#F07178"),
        ):
            btn.setFixedSize(c, c)
            btn.setStyleSheet(_CHROME.format(hover=hover, font_size=m["chrome_font"]))

        self._refresh_size_chips()

        # Robot + status
        self.robot.set_face_size(m["face"])
        self.status_label.setVisible(m["show_status"])
        self.status_label.setFont(QFont("IBM Plex Sans", m["status_pt"], QFont.Medium))
        self.log_display.setVisible(m["show_log"])
        self.log_display.setFont(QFont("IBM Plex Mono", m["log_pt"]))

        # Mode toggle + composer
        self.mode_toggle.apply_scale(
            pad_v=m["mode_pad_v"],
            pad_h=m["mode_pad_h"],
            font=m["mode_font"],
            icon=m["mode_icon"],
            radius=m["mode_r"],
        )
        self.chat.apply_scale(
            tag_pt=m["tag_pt"],
            body_pt=m["body_pt"],
            pad=m["bubble_pad"],
            radius=m["bubble_r"],
            gap=m["bubble_gap"],
        )

        kind = self.send_btn.property("icon_kind") or "send"
        self.send_btn.setFixedSize(m["send"], m["send"])
        self.send_btn.setIconSize(QSize(m["send_icon"], m["send_icon"]))
        self.send_btn.setIcon(_paint_icon(kind, m["send"], active=False))
        self.text_input.setFont(QFont("IBM Plex Sans", m["body_pt"]))

        # Stage / dock spacing via root inserts — keep modest
        self.dock.setStyleSheet(f"""
            QFrame#Dock {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: {max(12, m['mode_r'])}px;
            }}
        """)

    def _refresh_size_chips(self) -> None:
        ic = getattr(self, "_metrics", {}).get("icon", 14)
        for key, btn in self._size_btns.items():
            on = key == self.size_mode
            btn.setIcon(_paint_icon(f"size-{key}", ic, active=on))
            btn.setStyleSheet(_TOOL_ICON.format(
                bg="rgba(94, 177, 245, 0.14)" if on else "transparent",
            ))

    def apply_size_preset(self, mode: str, *, anchor_top_right: bool = False) -> None:
        mode = mode if mode in SIZE_PRESETS else "medium"
        self.size_mode = mode
        w, h = SIZE_PRESETS[mode]
        old = self.geometry()

        if anchor_top_right or not old.isValid() or old.width() < 50:
            self.resize(w, h)
        else:
            right, top = old.right(), old.top()
            self.resize(w, h)
            screen = QApplication.primaryScreen().availableGeometry()
            x = max(screen.left() + 8, min(right - w + 1, screen.right() - w - 8))
            y = max(screen.top() + 8, min(top, screen.bottom() - h - 8))
            self.move(x, y)

        self._apply_responsive()
        self._apply_mode_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive()

    def _edge_at(self, pos: QPoint) -> str | None:
        r = self.rect()
        x, y = pos.x(), pos.y()
        left = x <= EDGE
        right = x >= r.width() - EDGE
        top = y <= EDGE
        bottom = y >= r.height() - EDGE
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return None

    def _cursor_for_edge(self, edge: str | None):
        return {
            "l": Qt.SizeHorCursor,
            "r": Qt.SizeHorCursor,
            "t": Qt.SizeVerCursor,
            "b": Qt.SizeVerCursor,
            "tl": Qt.SizeFDiagCursor,
            "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor,
            "bl": Qt.SizeBDiagCursor,
        }.get(edge, Qt.ArrowCursor)

    def _apply_mode_layout(self) -> None:
        is_text = self.interaction_mode == "text"
        self.dock.setVisible(is_text)
        self.mode_toggle.set_mode(self.interaction_mode, emit=False)

        if is_text:
            self.context_label.setText("Type a message")
            self.text_input.setFocus()
        else:
            if self.current_status in ("standby", "listening"):
                self.context_label.setText(self._listen_hint)

    def set_interaction_mode(self, mode: str) -> None:
        mode = mode.lower().strip()
        if mode not in ("voice", "text"):
            return
        self.interaction_mode = mode
        self._apply_mode_layout()
        if hasattr(self, "worker") and self.worker:
            self.worker.set_mode(mode)

    def send_text_message(self) -> None:
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        # Don't add_message here — assistant emits speech_detected once (same as voice)
        if hasattr(self, "worker") and self.worker:
            self.worker.submit_text(text)

    def position_hud(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + screen.width() - self.width() - 36, screen.y() + 56)

    def init_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        g = QRadialGradient(16, 16, 14)
        g.setColorAt(0.0, QColor(94, 177, 245))
        g.setColorAt(0.7, QColor(12, 16, 24))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(g)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()

        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("Sopno")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #0C1018;
                color: #D7DEE9;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item { padding: 6px 16px; border-radius: 4px; }
            QMenu::item:selected { background: rgba(94,177,245,0.14); color: #B8D9F8; }
        """)
        show_a = QAction("Show HUD", self)
        show_a.triggered.connect(self.restore_hud)
        menu.addAction(show_a)
        hide_a = QAction("Hide HUD", self)
        hide_a.triggered.connect(self.hide_hud)
        menu.addAction(hide_a)
        menu.addSeparator()
        for key, label in (("small", "Size: Small"), ("medium", "Size: Medium"), ("full", "Size: Full")):
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, k=key: self.apply_size_preset(k))
            menu.addAction(act)
        menu.addSeparator()
        exit_a = QAction("Exit", self)
        exit_a.triggered.connect(self.close_app)
        menu.addAction(exit_a)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.hide_hud() if self.isVisible() else self.restore_hud()

    def hide_hud(self) -> None:
        self.hide()
        if hasattr(self, "worker") and self.worker:
            self.worker.log_message.emit("Hidden to tray.")

    def restore_hud(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        edge = self._edge_at(event.pos())
        if edge:
            self._resize_edge = edge
            self._press_geo = self.geometry()
            self._press_global = event.globalPos()
            self.old_pos = None
        else:
            self._resize_edge = None
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event) -> None:
        if self._resize_edge and self._press_geo is not None and self._press_global is not None:
            delta = event.globalPos() - self._press_global
            g = QRect(self._press_geo)
            e = self._resize_edge
            if "l" in e:
                g.setLeft(g.left() + delta.x())
            if "r" in e:
                g.setRight(g.right() + delta.x())
            if "t" in e:
                g.setTop(g.top() + delta.y())
            if "b" in e:
                g.setBottom(g.bottom() + delta.y())

            # Enforce min/max
            if g.width() < MIN_SIZE[0]:
                if "l" in e:
                    g.setLeft(g.right() - MIN_SIZE[0])
                else:
                    g.setWidth(MIN_SIZE[0])
            if g.height() < MIN_SIZE[1]:
                if "t" in e:
                    g.setTop(g.bottom() - MIN_SIZE[1])
                else:
                    g.setHeight(MIN_SIZE[1])
            if g.width() > MAX_SIZE[0]:
                if "l" in e:
                    g.setLeft(g.right() - MAX_SIZE[0])
                else:
                    g.setWidth(MAX_SIZE[0])
            if g.height() > MAX_SIZE[1]:
                if "t" in e:
                    g.setTop(g.bottom() - MAX_SIZE[1])
                else:
                    g.setHeight(MAX_SIZE[1])

            self.setGeometry(g)
            self.size_mode = "custom"
            self._apply_responsive()
            return

        if self.old_pos is not None:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()
            return

        # Hover cursor for edges
        self.setCursor(self._cursor_for_edge(self._edge_at(event.pos())))

    def mouseReleaseEvent(self, event) -> None:
        self.old_pos = None
        self._resize_edge = None
        self._press_geo = None
        self._press_global = None
        self.setCursor(Qt.ArrowCursor)

    def update_status(self, status: str) -> None:
        status_clean = status.lower().strip()
        self.current_status = status_clean if status_clean in STATUS_COPY else "standby"
        self.robot.set_state(self.current_status)

        label, color = STATUS_COPY[self.current_status]
        self.status_label.setText(label)
        pt = getattr(self, "_metrics", {}).get("status_pt", 8)
        self.status_label.setFont(QFont("IBM Plex Sans", pt, QFont.Medium))
        self.status_label.setStyleSheet(
            f"color: {color}; background: transparent; letter-spacing: 0.4px;"
        )

        if self.interaction_mode == "text":
            return
        hints = {
            "standby": self._listen_hint,
            "listening": self._listen_hint,
            "thinking": "Thinking…",
            "speaking": "Speaking…",
            "error": "Something went wrong",
        }
        self.context_label.setText(hints.get(self.current_status, self._listen_hint))

    def update_user_speech(self, text: str) -> None:
        self.chat.add_message("user", text)

    def update_sopno_reply(self, text: str) -> None:
        self.chat.add_message("assistant", text)

    def update_log(self, log: str) -> None:
        short = log if len(log) < 64 else log[:61] + "…"
        self.log_display.setText(short)
        print(f"[HUD Log] {log}")

    def close_app(self) -> None:
        if hasattr(self, "worker") and self.worker:
            self.worker.stop()
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.hide()
        self.close()
        QApplication.instance().quit()


def _watch_paths_for_reload() -> list[str]:
    root = Path(__file__).resolve().parent
    return [p for p in [
        str(root / "hud.py"),
        str(root.parent / "config" / "settings.py"),
        str(root.parent / "core" / "assistant.py"),
    ] if Path(p).exists()]


def _restart_process() -> None:
    print("\n[HUD] File change detected — restarting…\n", flush=True)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _install_hot_reload(app: QApplication) -> QFileSystemWatcher:
    watcher = QFileSystemWatcher(app)
    for path in _watch_paths_for_reload():
        watcher.addPath(path)
        print(f"[HUD] Watching for reload: {path}")

    debounce = QTimer(app)
    debounce.setSingleShot(True)
    debounce.setInterval(400)
    debounce.timeout.connect(_restart_process)

    def on_changed(path: str) -> None:
        if path and Path(path).exists() and path not in watcher.files():
            watcher.addPath(path)
        if not debounce.isActive():
            debounce.start()

    watcher.fileChanged.connect(on_changed)
    return watcher


def run_hud(*, reload: bool = False) -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet("""
        QToolTip {
            background-color: #141A24;
            color: #D7DEE9;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 6px;
            padding: 6px 8px;
            font-size: 11px;
        }
    """)

    if reload:
        _install_hot_reload(app)
        print("[HUD] Hot reload enabled.")
    window = SopnoHUDWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_hud(reload="--reload" in sys.argv)
