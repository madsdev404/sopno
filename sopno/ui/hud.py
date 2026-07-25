"""
sopno/ui/hud.py
━━━━━━━━━━━━━━━
Live glassmorphic PyQt5 HUD overlay for Sopno.

Centerpiece is a painted robot face (not emoji) that blinks, looks around,
and reacts to standby / listening / thinking / speaking.
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
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QPoint, QFileSystemWatcher, QTimer, QRectF, QPointF
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

EXPANDED_SIZE = (360, 540)
COMPACT_SIZE = (220, 180)

STATUS_COPY = {
    "standby":   ("Idle", "#94A3B8"),
    "listening": ("Listening", "#38BDF8"),
    "thinking":  ("Thinking", "#A78BFA"),
    "speaking":  ("Speaking", "#34D399"),
    "error":     ("Error", "#F87171"),
}

STATE_ACCENT = {
    "standby":   QColor(148, 163, 184),
    "listening": QColor(56, 189, 248),
    "thinking":  QColor(167, 139, 250),
    "speaking":  QColor(52, 211, 153),
    "error":     QColor(248, 113, 113),
}

# Flat window chrome — no fill, no border
_CHROME_BTN = """
    QPushButton {{
        background: transparent;
        color: #64748B;
        border: none;
        font-size: 13px;
        font-weight: 500;
        padding: 0px;
    }}
    QPushButton:hover {{
        color: {hover_fg};
    }}
"""

_MODE_BTN = """
    QPushButton {
        background: rgba(255, 255, 255, 0.03);
        color: #94A3B8;
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 12px;
        padding: 8px 14px;
        font-size: 11px;
        font-weight: 600;
        text-align: center;
    }
    QPushButton:hover {
        color: #E2E8F0;
        border-color: rgba(56, 189, 248, 0.35);
        background: rgba(56, 189, 248, 0.08);
    }
    QPushButton:pressed {
        background: rgba(56, 189, 248, 0.16);
    }
"""


class AliveRobotFace(QWidget):
    """
    Parametric robot face — blinks, glances, speaks, and reacts to state.
    Inspired by canvas robot-face runtimes (blink / lookAt / speak layers).
    """

    def __init__(self, parent=None, size: int = 128) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.state = "standby"
        self._t = 0.0
        self._blink = 0.0          # 0 open → 1 closed
        self._blink_closing = False
        self._next_blink = 2.4
        self._gaze = QPointF(0.0, 0.0)
        self._gaze_target = QPointF(0.0, 0.0)
        self._next_gaze = 1.6
        self._mouth = 0.12         # openness 0..1
        self._breath = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 fps

    def set_state(self, state: str) -> None:
        state = (state or "standby").lower().strip()
        if state not in STATE_ACCENT:
            state = "standby"
        if state != self.state:
            self.state = state
            # Snap gaze inward when engaging
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

        # Blink schedule
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

        # Idle gaze wander
        self._next_gaze -= dt
        if self._next_gaze <= 0 and self.state == "standby":
            self._gaze_target = QPointF(
                random.uniform(-0.45, 0.45),
                random.uniform(-0.25, 0.3),
            )
            self._next_gaze = random.uniform(1.4, 3.2)
        elif self.state == "listening":
            # Slight attentive micro-movement
            self._gaze_target = QPointF(
                0.08 * math.sin(self._t * 2.1),
                0.06 + 0.04 * math.sin(self._t * 1.3),
            )
        elif self.state == "thinking":
            self._gaze_target = QPointF(
                0.4 * math.sin(self._t * 0.9),
                -0.2 + 0.08 * math.sin(self._t * 1.7),
            )

        # Smooth gaze lerp
        self._gaze.setX(self._gaze.x() + (self._gaze_target.x() - self._gaze.x()) * 0.12)
        self._gaze.setY(self._gaze.y() + (self._gaze_target.y() - self._gaze.y()) * 0.12)

        # Mouth by state
        if self.state == "speaking":
            # Talking cadence
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

        # Soft aura
        aura_r = min(w, h) * (0.48 + 0.04 * self._breath)
        if self.state == "listening":
            aura_r *= 1.0 + 0.06 * abs(math.sin(self._t * 5))
        glow = QRadialGradient(cx, cy, aura_r)
        a = accent
        glow.setColorAt(0.0, QColor(a.red(), a.green(), a.blue(), 55 if self.state != "standby" else 28))
        glow.setColorAt(0.55, QColor(a.red(), a.green(), a.blue(), 14))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), aura_r, aura_r)

        # Head plate
        head_w = w * 0.62
        head_h = h * 0.68
        head = QRectF(cx - head_w / 2, cy - head_h / 2 + h * 0.02, head_w, head_h)
        radius = head_w * 0.28

        head_grad = QRadialGradient(cx, cy - head_h * 0.15, head_w * 0.75)
        head_grad.setColorAt(0.0, QColor(30, 41, 59))
        head_grad.setColorAt(1.0, QColor(15, 23, 42))
        p.setBrush(QBrush(head_grad))
        p.setPen(QPen(QColor(148, 163, 184, 40), 1.2))
        p.drawRoundedRect(head, radius, radius)

        # Inner face panel
        panel = head.adjusted(head_w * 0.1, head_h * 0.14, -head_w * 0.1, -head_h * 0.12)
        p.setBrush(QColor(8, 12, 22, 220))
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 50), 1.0))
        p.drawRoundedRect(panel, radius * 0.55, radius * 0.55)

        # Antenna node
        ant_y = head.top() - h * 0.02
        p.setPen(QPen(QColor(71, 85, 105), 2))
        p.drawLine(QPointF(cx, head.top() + 2), QPointF(cx, ant_y))
        pulse = 0.55 + 0.45 * self._breath
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(a.red(), a.green(), a.blue(), int(180 * pulse)))
        p.drawEllipse(QPointF(cx, ant_y - 3), 3.5, 3.5)

        # Side ears / sensors — pulse when listening
        ear_pulse = 1.0 + (0.12 * abs(math.sin(self._t * 6)) if self.state == "listening" else 0)
        ear_h = head_h * 0.22 * ear_pulse
        ear_w = head_w * 0.08
        p.setBrush(QColor(30, 41, 59))
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 80 if self.state == "listening" else 35), 1))
        p.drawRoundedRect(
            QRectF(head.left() - ear_w * 0.7, cy - ear_h / 2, ear_w, ear_h),
            3, 3,
        )
        p.drawRoundedRect(
            QRectF(head.right() - ear_w * 0.3, cy - ear_h / 2, ear_w, ear_h),
            3, 3,
        )

        # Eyes
        eye_y = panel.center().y() - panel.height() * 0.12
        eye_dx = panel.width() * 0.22
        eye_w = panel.width() * 0.18
        eye_h = panel.height() * 0.22 * (1.0 - 0.92 * self._blink)
        if eye_h < 1.5:
            eye_h = 1.5

        for side in (-1, 1):
            ex = panel.center().x() + side * eye_dx
            self._draw_eye(p, ex, eye_y, eye_w, eye_h, accent)

        # Thinking scan line
        if self.state == "thinking":
            scan_y = panel.top() + panel.height() * ((math.sin(self._t * 2.2) + 1) / 2)
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 90), 1.5))
            p.drawLine(QPointF(panel.left() + 6, scan_y), QPointF(panel.right() - 6, scan_y))

        # Mouth
        mouth_cx = panel.center().x()
        mouth_cy = panel.bottom() - panel.height() * 0.28
        mouth_w = panel.width() * (0.28 + 0.12 * self._mouth)
        mouth_h = panel.height() * (0.06 + 0.22 * self._mouth)

        if self.state == "error":
            # Flat frown
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 200), 2.0, Qt.SolidLine, Qt.RoundCap))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w * 0.55, mouth_cy + 3)
            path.quadTo(mouth_cx, mouth_cy - 4, mouth_cx + mouth_w * 0.55, mouth_cy + 3)
            p.drawPath(path)
        elif self._mouth < 0.18:
            # Soft closed smile
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 170), 2.0, Qt.SolidLine, Qt.RoundCap))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w * 0.5, mouth_cy)
            path.quadTo(mouth_cx, mouth_cy + 5, mouth_cx + mouth_w * 0.5, mouth_cy)
            p.drawPath(path)
        else:
            # Open speaking mouth
            mouth = QRectF(mouth_cx - mouth_w / 2, mouth_cy - mouth_h / 2, mouth_w, mouth_h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(2, 6, 14))
            p.drawRoundedRect(mouth, mouth_h * 0.45, mouth_h * 0.45)
            p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 160), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(mouth, mouth_h * 0.45, mouth_h * 0.45)

        # Listening rings
        if self.state == "listening":
            for i in range(2):
                rr = min(w, h) * (0.38 + 0.08 * i) + 4 * abs(math.sin(self._t * 4 + i))
                alpha = int(50 - i * 18)
                p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), alpha), 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), rr, rr)

        p.end()

    def _draw_eye(self, p: QPainter, cx: float, cy: float, ew: float, eh: float, accent: QColor) -> None:
        # Eye socket
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(2, 6, 14))
        p.drawRoundedRect(QRectF(cx - ew / 2, cy - eh / 2, ew, eh), eh * 0.45, eh * 0.45)

        if self._blink > 0.85:
            # Closed lid line
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 160), 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - ew * 0.35, cy), QPointF(cx + ew * 0.35, cy))
            return

        # Iris glow
        iris_r = min(ew, eh) * 0.38
        pupil_ox = self._gaze.x() * ew * 0.22
        pupil_oy = self._gaze.y() * eh * 0.22
        ix, iy = cx + pupil_ox, cy + pupil_oy

        iris = QRadialGradient(ix, iy, iris_r)
        iris.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 230))
        iris.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(), 140))
        iris.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setBrush(QBrush(iris))
        p.drawEllipse(QPointF(ix, iy), iris_r, iris_r)

        # Pupil
        p.setBrush(QColor(8, 12, 22))
        p.drawEllipse(QPointF(ix, iy), iris_r * 0.42, iris_r * 0.42)

        # Specular highlight
        p.setBrush(QColor(255, 255, 255, 180))
        p.drawEllipse(QPointF(ix - iris_r * 0.28, iy - iris_r * 0.28), iris_r * 0.18, iris_r * 0.18)


class AssistantWorker(QObject):
    """Bridges SopnoAssistant callbacks to Qt thread-safe signals."""

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
    """Live translucent HUD with reactive robot face and voice/text modes."""

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
        return f'Say “{primary.title()}” to wake'

    def init_ui(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setStyleSheet(f"""
            QWidget#CentralWidget {{
                background-color: rgba(10, 16, 28, {settings.hud_opacity});
                border: 1px solid rgba(148, 163, 184, 0.14);
                border-radius: 22px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(56, 189, 248, 70))
        shadow.setOffset(0, 4)
        self.central_widget.setGraphicsEffect(shadow)

        root = QVBoxLayout(self.central_widget)
        root.setContentsMargins(14, 10, 10, 14)
        root.setSpacing(10)

        # ── Top chrome ────────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setContentsMargins(4, 0, 0, 0)
        top.setSpacing(6)

        self.context_label = QLabel(self._wake_hint)
        self.context_label.setFont(QFont("IBM Plex Sans", 9))
        self.context_label.setStyleSheet("color: #64748B; background: transparent;")
        self.context_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        chrome = QHBoxLayout()
        chrome.setContentsMargins(0, 0, 0, 0)
        chrome.setSpacing(2)
        chrome.setAlignment(Qt.AlignRight | Qt.AlignTop)

        self.hide_btn = self._chrome_btn("-", "#F472B6", "Hide to system tray")
        self.hide_btn.clicked.connect(self.hide_hud)

        self.min_btn = self._chrome_btn("□", "#38BDF8", "Minimize — shrink to compact view")
        self.min_btn.clicked.connect(self.toggle_compact)

        self.close_btn = self._chrome_btn("×", "#F87171", "Close Sopno")
        self.close_btn.clicked.connect(self.close_app)

        chrome.addWidget(self.hide_btn)
        chrome.addWidget(self.min_btn)
        chrome.addWidget(self.close_btn)

        top.addWidget(self.context_label, stretch=1)
        top.addLayout(chrome)
        root.addLayout(top)

        # ── Alive robot stage ─────────────────────────────────────────────────
        self.avatar_stage = QFrame()
        self.avatar_stage.setObjectName("AvatarStage")
        self.avatar_stage.setStyleSheet("""
            QFrame#AvatarStage {
                background: transparent;
                border: none;
            }
        """)
        stage_layout = QVBoxLayout(self.avatar_stage)
        stage_layout.setContentsMargins(4, 4, 4, 2)
        stage_layout.setSpacing(6)
        stage_layout.setAlignment(Qt.AlignCenter)

        self.robot = AliveRobotFace(size=132)
        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("IBM Plex Sans", 10, QFont.Medium))
        self.status_label.setStyleSheet(
            "color: #94A3B8; background: transparent; letter-spacing: 1px;"
        )

        stage_layout.addWidget(self.robot, 0, Qt.AlignCenter)
        stage_layout.addWidget(self.status_label)
        root.addWidget(self.avatar_stage)

        # ── Conversation ──────────────────────────────────────────────────────
        self.speech_display = QLabel("Waiting…")
        self.speech_display.setWordWrap(True)
        self.speech_display.setFont(QFont("IBM Plex Sans", 9))
        self.speech_display.setStyleSheet("""
            color: #94A3B8;
            background: rgba(255, 255, 255, 0.03);
            padding: 10px 12px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.04);
        """)
        self.speech_display.setMinimumHeight(44)
        root.addWidget(self.speech_display)

        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setFont(QFont("IBM Plex Sans", 10))
        self.reply_display.setPlaceholderText("Replies appear here…")
        self.reply_display.setStyleSheet("""
            QTextEdit {
                color: #E2E8F0;
                background: rgba(0, 0, 0, 0.22);
                border: 1px solid rgba(52, 211, 153, 0.12);
                padding: 10px 12px;
                border-radius: 12px;
            }
        """)
        self.reply_display.setMinimumHeight(88)
        self.reply_display.setMaximumHeight(130)
        root.addWidget(self.reply_display)

        # ── Single mode toggle ────────────────────────────────────────────────
        self.mode_btn = QPushButton("Voice mode")
        self.mode_btn.setCursor(Qt.PointingHandCursor)
        self.mode_btn.setStyleSheet(_MODE_BTN)
        self.mode_btn.setToolTip("Switch to Text mode — type instead of speaking")
        self.mode_btn.clicked.connect(self.toggle_interaction_mode)
        root.addWidget(self.mode_btn)

        # ── Text composer ─────────────────────────────────────────────────────
        self.composer = QWidget()
        composer_row = QHBoxLayout(self.composer)
        composer_row.setContentsMargins(0, 0, 0, 0)
        composer_row.setSpacing(6)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a message…")
        self.text_input.setToolTip("Type your message and press Enter to send")
        self.text_input.setFont(QFont("IBM Plex Sans", 10))
        self.text_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.04);
                color: #E2E8F0;
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 10px;
                padding: 8px 12px;
            }
            QLineEdit:focus {
                border-color: rgba(56, 189, 248, 0.45);
            }
        """)
        self.text_input.returnPressed.connect(self.send_text_message)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedHeight(34)
        self.send_btn.setMinimumWidth(52)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setToolTip("Send message")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.16);
                color: #7DD3FC;
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 10px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.28);
            }
        """)
        self.send_btn.clicked.connect(self.send_text_message)

        composer_row.addWidget(self.text_input)
        composer_row.addWidget(self.send_btn)
        self.composer.setVisible(False)
        root.addWidget(self.composer)

        self.log_display = QLabel("Booting…")
        self.log_display.setFont(QFont("IBM Plex Mono", 8))
        self.log_display.setStyleSheet("color: #475569; background: transparent;")
        self.log_display.setWordWrap(True)
        root.addWidget(self.log_display)

        self.setCentralWidget(self.central_widget)
        self.setFixedSize(*EXPANDED_SIZE)
        self.position_hud()

    def _chrome_btn(self, text: str, hover_fg: str, tip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(22, 20)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(tip)
        btn.setStyleSheet(_CHROME_BTN.format(hover_fg=hover_fg))
        return btn

    def toggle_interaction_mode(self) -> None:
        next_mode = "text" if self.interaction_mode == "voice" else "voice"
        self.set_interaction_mode(next_mode)

    def set_interaction_mode(self, mode: str) -> None:
        mode = mode.lower().strip()
        if mode not in ("voice", "text"):
            return

        self.interaction_mode = mode
        self.composer.setVisible(mode == "text" and not self.is_compact)

        if mode == "voice":
            self.mode_btn.setText("Voice mode")
            self.mode_btn.setToolTip("Switch to Text mode — type instead of speaking")
            self.context_label.setText(self._wake_hint)
        else:
            self.mode_btn.setText("Text mode")
            self.mode_btn.setToolTip("Switch to Voice mode — wake word + mic")
            self.context_label.setText("Type below · replies stay silent")

        if hasattr(self, "worker") and self.worker:
            self.worker.set_mode(mode)
            if mode == "text":
                self.text_input.setFocus()

    def send_text_message(self) -> None:
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self.speech_display.setText(f"You · {text}")
        if hasattr(self, "worker") and self.worker:
            self.worker.submit_text(text)

    def toggle_compact(self) -> None:
        self.is_compact = not self.is_compact
        old_geo = self.geometry()
        right, top = old_geo.right(), old_geo.top()

        for w in (self.speech_display, self.reply_display, self.mode_btn, self.log_display):
            w.setVisible(not self.is_compact)
        self.composer.setVisible(
            (not self.is_compact) and self.interaction_mode == "text"
        )

        if self.is_compact:
            self.setFixedSize(*COMPACT_SIZE)
            self.min_btn.setText("❐")
            self.min_btn.setToolTip("Expand — restore full HUD")
            self.robot.set_face_size(96)
        else:
            self.setFixedSize(*EXPANDED_SIZE)
            self.min_btn.setText("□")
            self.min_btn.setToolTip("Minimize — shrink to compact view")
            self.robot.set_face_size(132)

        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left() + 8, min(right - self.width() + 1, screen.right() - self.width() - 8))
        y = max(screen.top() + 8, min(top, screen.bottom() - self.height() - 8))
        self.move(x, y)

    def position_hud(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + screen.width() - self.width() - 40
        y = screen.y() + 60
        self.move(x, y)

    def init_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)

        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QRadialGradient(16, 16, 14)
        gradient.setColorAt(0.0, QColor(56, 189, 248))
        gradient.setColorAt(0.7, QColor(10, 16, 28))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()

        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("Sopno")

        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet("""
            QMenu {
                background-color: #0A101C;
                color: #E2E8F0;
                border: 1px solid rgba(148, 163, 184, 0.16);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item { padding: 6px 18px; border-radius: 4px; }
            QMenu::item:selected {
                background-color: rgba(56, 189, 248, 0.14);
                color: #7DD3FC;
            }
        """)

        restore = QAction("Show HUD", self)
        restore.triggered.connect(self.restore_hud)
        self.tray_menu.addAction(restore)

        hide = QAction("Hide HUD", self)
        hide.triggered.connect(self.hide_hud)
        self.tray_menu.addAction(hide)
        self.tray_menu.addSeparator()

        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close_app)
        self.tray_menu.addAction(exit_act)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide_hud()
            else:
                self.restore_hud()

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

        label, color = STATUS_COPY.get(self.current_status, STATUS_COPY["standby"])
        self.status_label.setText(label)
        self.status_label.setStyleSheet(
            f"color: {color}; background: transparent; letter-spacing: 1px;"
        )

        shadow = self.central_widget.graphicsEffect()
        if shadow:
            c = QColor(color)
            c.setAlpha(140 if self.current_status != "standby" else 60)
            shadow.setColor(c)

        if self.interaction_mode == "text":
            return
        if self.current_status == "standby":
            self.context_label.setText(self._wake_hint)
        elif self.current_status == "listening":
            self.context_label.setText("Go ahead — I'm listening")
        elif self.current_status == "thinking":
            self.context_label.setText("Working on your request…")
        elif self.current_status == "speaking":
            self.context_label.setText("Replying out loud")
        elif self.current_status == "error":
            self.context_label.setText("Something went wrong")

    def update_user_speech(self, text: str) -> None:
        self.speech_display.setText(f"You · {text}")

    def update_sopno_reply(self, text: str) -> None:
        self.reply_display.setText(text)

    def update_log(self, log: str) -> None:
        short = log if len(log) < 72 else log[:69] + "…"
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
    paths = [
        str(root / "hud.py"),
        str(root.parent / "config" / "settings.py"),
        str(root.parent / "core" / "assistant.py"),
    ]
    return [p for p in paths if Path(p).exists()]


def _restart_process() -> None:
    print("\n[HUD] File change detected — restarting…\n", flush=True)
    python = sys.executable
    os.execv(python, [python, *sys.argv])


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

    if reload:
        _install_hot_reload(app)
        print("[HUD] Hot reload enabled.")

    window = SopnoHUDWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_hud(reload="--reload" in sys.argv)
