"""
sopno/ui/hud.py
━━━━━━━━━━━━━━━
Mature floating companion HUD for Sopno.

Layout inspired by premium assistant panels (ChatGPT composer controls,
Gemini Live floating pill, companion-orb hierarchy):
  header → living robot → transcript → compact icon composer dock.
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
    QTextEdit,
    QPushButton,
    QGraphicsDropShadowEffect,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QLineEdit,
    QFrame,
    QSizePolicy,
    QSpacerItem,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QPoint, QFileSystemWatcher, QTimer, QRectF, QPointF, QSize
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

# Compact companion panel proportions
EXPANDED_SIZE = (340, 500)
COMPACT_SIZE = (200, 168)

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
    """Draw mic / keyboard / send glyphs into a QIcon."""
    color = color or QColor("#A8B4C8")
    if active:
        color = QColor("#E8EEF7")

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(color, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)

    s = size
    cx, cy = s / 2, s / 2

    if kind == "mic":
        # Capsule mic
        mic = QRectF(cx - 4, cy - 9, 8, 12)
        p.drawRoundedRect(mic, 4, 4)
        # Stand arc
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
    """Premium floating companion panel."""

    def __init__(self) -> None:
        super().__init__()
        self.old_pos = None
        self.is_compact = False
        self.interaction_mode = "voice"
        self.current_status = "standby"
        self._wake_hint = self._build_wake_hint()

        self.init_ui()
        self.init_tray()

        self.worker = AssistantWorker()
        self.thread = threading.Thread(target=self.worker.start_loop, daemon=True)
        self.worker.status_changed.connect(self.update_status)
        self.worker.speech_detected.connect(self.update_user_speech)
        self.worker.reply_generated.connect(self.update_sopno_reply)
        self.worker.log_message.connect(self.update_log)
        self.thread.start()

    @staticmethod
    def _build_wake_hint() -> str:
        words = [w for w in settings.wake_words if w and not w.startswith("স")]
        primary = words[0] if words else "sopno"
        return f'Say “{primary.title()}”'

    def init_ui(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysShowToolTips, True)

        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
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
        root.setContentsMargins(16, 12, 12, 14)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 0, 0)
        header.setSpacing(8)

        self.context_label = QLabel(self._wake_hint)
        self.context_label.setFont(QFont("IBM Plex Sans", 9))
        self.context_label.setStyleSheet("color: #6B7C94; background: transparent;")
        self.context_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        chrome = QHBoxLayout()
        chrome.setSpacing(2)
        chrome.setContentsMargins(0, 0, 0, 0)
        chrome.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Primary: hide + close (larger). Minimize stays quiet/small.
        self.hide_btn = self._chrome_btn(
            "−", "#E8A0BF", "Hide to system tray", size=28, font_size=16,
        )
        self.hide_btn.clicked.connect(self.hide_hud)

        self.min_btn = self._chrome_btn(
            "□", "#8EC8F0", "Minimize — shrink to compact view", size=16, font_size=9,
        )
        self.min_btn.clicked.connect(self.toggle_compact)

        self.close_btn = self._chrome_btn(
            "×", "#F07178", "Close Sopno", size=28, font_size=16,
        )
        self.close_btn.clicked.connect(self.close_app)

        chrome.addWidget(self.min_btn, 0, Qt.AlignVCenter)
        chrome.addSpacing(6)
        chrome.addWidget(self.hide_btn, 0, Qt.AlignVCenter)
        chrome.addWidget(self.close_btn, 0, Qt.AlignVCenter)

        header.addWidget(self.context_label, 1)
        header.addLayout(chrome)
        root.addLayout(header)
        root.addSpacing(8)

        # ── Robot stage ───────────────────────────────────────────────────────
        stage = QVBoxLayout()
        stage.setSpacing(4)
        stage.setAlignment(Qt.AlignCenter)

        self.robot = AliveRobotFace(size=118)
        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("IBM Plex Sans", 9, QFont.Medium))
        self.status_label.setStyleSheet(
            "color: #8B9BB4; background: transparent; letter-spacing: 0.5px;"
        )

        stage.addWidget(self.robot, 0, Qt.AlignCenter)
        stage.addWidget(self.status_label)
        root.addLayout(stage)
        root.addSpacing(12)

        # ── Transcript surface (single conversation card) ─────────────────────
        self.transcript = QFrame()
        self.transcript.setObjectName("Transcript")
        self.transcript.setStyleSheet("""
            QFrame#Transcript {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
            }
        """)
        t_layout = QVBoxLayout(self.transcript)
        t_layout.setContentsMargins(12, 10, 12, 10)
        t_layout.setSpacing(8)

        you_tag = QLabel("You")
        you_tag.setFont(QFont("IBM Plex Sans", 8, QFont.Medium))
        you_tag.setStyleSheet("color: #5C6B82; background: transparent;")
        t_layout.addWidget(you_tag)

        self.speech_display = QLabel("Waiting for input…")
        self.speech_display.setWordWrap(True)
        self.speech_display.setFont(QFont("IBM Plex Sans", 9))
        self.speech_display.setStyleSheet("color: #9AA8BC; background: transparent;")
        self.speech_display.setMinimumHeight(28)
        t_layout.addWidget(self.speech_display)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,0.05); border: none;")
        t_layout.addWidget(divider)

        sopno_tag = QLabel("Sopno")
        sopno_tag.setFont(QFont("IBM Plex Sans", 8, QFont.Medium))
        sopno_tag.setStyleSheet("color: #5C6B82; background: transparent;")
        t_layout.addWidget(sopno_tag)

        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setFont(QFont("IBM Plex Sans", 10))
        self.reply_display.setPlaceholderText("Response will appear here")
        self.reply_display.setStyleSheet("""
            QTextEdit {
                color: #D7DEE9;
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self.reply_display.setMinimumHeight(72)
        self.reply_display.setMaximumHeight(110)
        t_layout.addWidget(self.reply_display)

        root.addWidget(self.transcript, 1)
        root.addSpacing(12)

        # ── Composer dock (ChatGPT-style circular controls) ───────────────────
        self.dock = QFrame()
        self.dock.setObjectName("Dock")
        self.dock.setStyleSheet("""
            QFrame#Dock {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 22px;
            }
        """)
        dock_row = QHBoxLayout(self.dock)
        dock_row.setContentsMargins(8, 6, 6, 6)
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
                padding: 6px 8px;
                selection-background-color: rgba(94, 177, 245, 0.35);
            }
        """)
        self.text_input.returnPressed.connect(self.send_text_message)
        self.text_input.setVisible(False)

        self.send_btn = self._circle_btn(
            "send",
            tip="Send message",
            active=False,
            accent=False,
        )
        self.send_btn.clicked.connect(self.send_text_message)
        self.send_btn.setVisible(False)

        # Mode: small circular icon — mic (voice) / keyboard (text)
        self.mode_btn = self._circle_btn(
            "mic",
            tip="Voice mode — click to switch to text",
            active=True,
            accent=True,
        )
        self.mode_btn.clicked.connect(self.toggle_interaction_mode)

        dock_row.addWidget(self.text_input, 1)
        dock_row.addWidget(self.send_btn, 0, Qt.AlignVCenter)
        dock_row.addWidget(self.mode_btn, 0, Qt.AlignVCenter)

        # Voice mode: center the mic button in the dock
        self._dock_spacer_l = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._dock_spacer_r = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
        dock_row.insertItem(0, self._dock_spacer_l)
        dock_row.addItem(self._dock_spacer_r)

        root.addWidget(self.dock)
        root.addSpacing(8)

        self.log_display = QLabel("Starting…")
        self.log_display.setAlignment(Qt.AlignCenter)
        self.log_display.setFont(QFont("IBM Plex Mono", 7))
        self.log_display.setStyleSheet("color: #3F4D63; background: transparent;")
        self.log_display.setWordWrap(True)
        root.addWidget(self.log_display)

        self.setCentralWidget(self.central_widget)
        self.setFixedSize(*EXPANDED_SIZE)
        self._apply_mode_layout()
        self.position_hud()

    def _chrome_btn(
        self,
        text: str,
        hover: str,
        tip: str,
        *,
        size: int = 28,
        font_size: int = 16,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(size, size)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(tip)
        btn.setStyleSheet(_CHROME.format(hover=hover, font_size=font_size))
        return btn

    def _circle_btn(self, kind: str, *, tip: str, active: bool, accent: bool) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(36, 36)
        btn.setIconSize(QSize(18, 18))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(tip)
        btn.setIcon(_paint_icon(kind, 36, active=active))

        if accent and active:
            bg, border = "rgba(94, 177, 245, 0.18)", "rgba(94, 177, 245, 0.35)"
            hbg, hb = "rgba(94, 177, 245, 0.28)", "rgba(94, 177, 245, 0.5)"
            pbg = "rgba(94, 177, 245, 0.38)"
        else:
            bg, border = "rgba(255, 255, 255, 0.04)", "rgba(255, 255, 255, 0.08)"
            hbg, hb = "rgba(255, 255, 255, 0.08)", "rgba(255, 255, 255, 0.14)"
            pbg = "rgba(255, 255, 255, 0.12)"

        btn.setStyleSheet(_ICON_BTN.format(
            bg=bg, border=border, hover_bg=hbg, hover_border=hb, pressed_bg=pbg,
        ))
        btn.setProperty("icon_kind", kind)
        return btn

    def _refresh_mode_btn(self) -> None:
        is_voice = self.interaction_mode == "voice"
        kind = "mic" if is_voice else "keyboard"
        self.mode_btn.setIcon(_paint_icon(kind, 36, active=True))
        self.mode_btn.setToolTip(
            "Voice mode — click to switch to text"
            if is_voice
            else "Text mode — click to switch to voice"
        )
        # Accent when voice (active listening surface), quieter when text
        if is_voice:
            self.mode_btn.setStyleSheet(_ICON_BTN.format(
                bg="rgba(94, 177, 245, 0.18)",
                border="rgba(94, 177, 245, 0.35)",
                hover_bg="rgba(94, 177, 245, 0.28)",
                hover_border="rgba(94, 177, 245, 0.5)",
                pressed_bg="rgba(94, 177, 245, 0.38)",
            ))
        else:
            self.mode_btn.setStyleSheet(_ICON_BTN.format(
                bg="rgba(255, 255, 255, 0.06)",
                border="rgba(255, 255, 255, 0.10)",
                hover_bg="rgba(255, 255, 255, 0.10)",
                hover_border="rgba(255, 255, 255, 0.16)",
                pressed_bg="rgba(255, 255, 255, 0.14)",
            ))

    def _apply_mode_layout(self) -> None:
        """Voice: centered mic. Text: input + send + keyboard icon."""
        is_text = self.interaction_mode == "text"
        self.text_input.setVisible(is_text and not self.is_compact)
        self.send_btn.setVisible(is_text and not self.is_compact)

        # Spacers expand only in voice mode to center the mic
        stretch = 1 if (not is_text and not self.is_compact) else 0
        self._dock_spacer_l.changeSize(0, 0, QSizePolicy.Expanding if stretch else QSizePolicy.Fixed, QSizePolicy.Minimum)
        self._dock_spacer_r.changeSize(0, 0, QSizePolicy.Expanding if stretch else QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.dock.layout().invalidate()

        self._refresh_mode_btn()

        if is_text:
            self.context_label.setText("Type a message")
            self.text_input.setFocus()
        else:
            if self.current_status == "standby":
                self.context_label.setText(self._wake_hint)

    def toggle_interaction_mode(self) -> None:
        next_mode = "text" if self.interaction_mode == "voice" else "voice"
        self.set_interaction_mode(next_mode)

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
        self.speech_display.setText(text)
        if hasattr(self, "worker") and self.worker:
            self.worker.submit_text(text)

    def toggle_compact(self) -> None:
        self.is_compact = not self.is_compact
        old = self.geometry()
        right, top = old.right(), old.top()

        show = not self.is_compact
        self.transcript.setVisible(show)
        self.dock.setVisible(show)
        self.log_display.setVisible(show)

        if self.is_compact:
            self.setFixedSize(*COMPACT_SIZE)
            self.min_btn.setText("❐")
            self.min_btn.setToolTip("Expand — restore full HUD")
            self.robot.set_face_size(92)
        else:
            self.setFixedSize(*EXPANDED_SIZE)
            self.min_btn.setText("□")
            self.min_btn.setToolTip("Minimize — shrink to compact view")
            self.robot.set_face_size(118)
            self._apply_mode_layout()

        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left() + 8, min(right - self.width() + 1, screen.right() - self.width() - 8))
        y = max(screen.top() + 8, min(top, screen.bottom() - self.height() - 8))
        self.move(x, y)

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
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event) -> None:
        if self.old_pos is not None:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event) -> None:
        self.old_pos = None

    def update_status(self, status: str) -> None:
        status_clean = status.lower().strip()
        self.current_status = status_clean if status_clean in STATUS_COPY else "standby"
        self.robot.set_state(self.current_status)

        label, color = STATUS_COPY[self.current_status]
        self.status_label.setText(label)
        self.status_label.setStyleSheet(
            f"color: {color}; background: transparent; letter-spacing: 0.5px;"
        )

        if self.interaction_mode == "text":
            return
        hints = {
            "standby": self._wake_hint,
            "listening": "Listening…",
            "thinking": "Thinking…",
            "speaking": "Speaking…",
            "error": "Something went wrong",
        }
        self.context_label.setText(hints.get(self.current_status, self._wake_hint))

    def update_user_speech(self, text: str) -> None:
        self.speech_display.setText(text)

    def update_sopno_reply(self, text: str) -> None:
        self.reply_display.setText(text)

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
