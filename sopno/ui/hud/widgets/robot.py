"""
sopno/ui/hud/widgets/robot.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Animated robot face — blinks, glances, speaks, reacts to state.
"""

import math
import random

from PyQt5.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt5.QtWidgets import QWidget

from sopno.ui.hud.visuals.theme import STATE_ACCENT


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
