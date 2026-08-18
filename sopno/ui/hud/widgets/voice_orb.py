"""
sopno/ui/hud/widgets/voice_orb.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Audio-reactive voice mode orb — layered visualization around the robot face.
Inspired by ChatGPT / Gemini Live voice mode.
"""

import math
import random

from PyQt5.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt5.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PyQt5.QtWidgets import QSizePolicy, QWidget

from sopno.ui.hud.widgets.robot import AliveRobotFace

TICK_MS = 33
PARTICLE_COUNT = 20
WAVE_POINTS = 60
BARS_COUNT = 28
RING_SEGMENTS = 10

COLORS = {
    "idle": {
        "primary": QColor(100, 130, 180),
        "secondary": QColor(60, 80, 120),
        "glow": QColor(80, 120, 170, 30),
        "particle": QColor(140, 180, 220),
    },
    "listening": {
        "primary": QColor(94, 177, 245),
        "secondary": QColor(50, 130, 220),
        "glow": QColor(94, 177, 245, 45),
        "particle": QColor(160, 210, 255),
    },
    "thinking": {
        "primary": QColor(155, 140, 242),
        "secondary": QColor(120, 100, 200),
        "glow": QColor(155, 140, 242, 40),
        "particle": QColor(190, 175, 255),
    },
    "speaking": {
        "primary": QColor(74, 222, 154),
        "secondary": QColor(40, 180, 120),
        "glow": QColor(74, 222, 154, 40),
        "particle": QColor(130, 240, 190),
    },
    "error": {
        "primary": QColor(240, 113, 120),
        "secondary": QColor(200, 80, 90),
        "glow": QColor(240, 113, 120, 35),
        "particle": QColor(255, 160, 165),
    },
}

STATE_RING_SPEED = {
    "idle": 0.5,
    "listening": 2.0,
    "thinking": 1.5,
    "speaking": 3.5,
}


def _create_particles(count: int = PARTICLE_COUNT) -> list[dict]:
    particles = []
    for _ in range(count):
        particles.append({
            "angle": random.uniform(0, 2 * math.pi),
            "dist": random.uniform(0.2, 0.7),
            "size": random.uniform(1.0, 2.8),
            "speed": random.uniform(0.1, 0.4),
            "brightness": random.uniform(0.3, 1.0),
            "phase": random.uniform(0, 2 * math.pi),
            "wobble_freq": random.uniform(0.8, 2.5),
        })
    return particles


class VoiceModeOrb(QWidget):
    """Complete voice mode visualization with robot face at center."""

    def __init__(self, parent=None, size: int = 400) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(120, 120)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._state = "idle"
        self._target_state = "idle"
        self._transition = 1.0
        self._audio_level = 0.0
        self._smoothed_audio = 0.0
        self._t = 0.0
        self._breath = 0.0
        self._particles = _create_particles()
        self._bars = [0.0] * BARS_COUNT

        face_size = int(size * 0.45)
        self.face = AliveRobotFace(self, size=face_size)
        self.face.setVisible(False)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    def showEvent(self, _event) -> None:
        self.face.setVisible(True)

    def hideEvent(self, _event) -> None:
        self.face.setVisible(False)

    def set_state(self, state: str) -> None:
        state = (state or "idle").lower().strip()
        if state not in COLORS:
            state = "idle"
        if state != self._target_state:
            self._target_state = state
            self._transition = 0.0
        self.face.set_state(state)

    def set_audio_level(self, rms: float) -> None:
        self._audio_level = min(1.0, rms / 3000.0)

    def set_face_size(self, size: int) -> None:
        self.face.set_face_size(size)

    def _tick(self) -> None:
        dt = TICK_MS / 1000.0
        self._t += dt
        self._breath = 0.5 + 0.5 * math.sin(self._t * 1.4)

        self._smoothed_audio += (self._audio_level - self._smoothed_audio) * 0.15

        if self._transition < 1.0:
            self._transition = min(1.0, self._transition + dt * 3.6)
            if self._transition >= 1.0:
                self._state = self._target_state

        for i in range(BARS_COUNT):
            target = self._smoothed_audio * (0.5 + 0.5 * math.sin(self._t * 3 + i * 0.3))
            self._bars[i] += (target - self._bars[i]) * 0.2

        self.update()

    def paintEvent(self, _event) -> None:
        if not self.isVisible() or self.width() < 10:
            return
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.35
        state = self._target_state
        colors = COLORS[state]
        audio = self._smoothed_audio
        t = self._t
        breath = self._breath

        self._draw_glow_rings(p, cx, cy, r, colors, t, audio)
        self._draw_orb(p, cx, cy, r, colors, t, state, audio)
        self._draw_particles(p, cx, cy, r, colors, t, state)
        self._draw_wave_lines(p, cx, cy, r, colors, t, state, audio)
        self._draw_bars(p, cx, cy, r, colors, t, state)
        self._draw_core(p, cx, cy, r, colors, t, breath)
        self._draw_ring(p, cx, cy, r, colors, t, state)

        face_size = self.face.width()
        self.face.move(int(cx - face_size / 2), int(cy - face_size / 2))

        p.end()

    def _draw_glow_rings(self, p, cx, cy, r, colors, t, audio):
        glow = colors["glow"]
        for i in range(3):
            ring_r = r * (1.15 + 0.08 * i) + 4 * abs(math.sin(t * (2.0 + i * 0.7)))
            alpha = int(glow.alpha() * (0.8 - i * 0.2) * (1.0 + 0.3 * audio))
            pen = QPen(QColor(glow.red(), glow.green(), glow.blue(), max(10, min(255, alpha))), 1.2 - i * 0.3)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

    def _draw_orb(self, p, cx, cy, r, colors, t, state, audio):
        primary = colors["primary"]
        secondary = colors["secondary"]
        effective_r = r * (1.0 + audio * 0.15)

        grad = QRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 1.1)
        grad.setColorAt(0.0, QColor(min(255, primary.red() + 40), min(255, primary.green() + 40), min(255, primary.blue() + 40), 255))
        grad.setColorAt(0.4, QColor(secondary.red(), secondary.green(), secondary.blue(), 255))
        grad.setColorAt(1.0, QColor(max(0, secondary.red() - 30), max(0, secondary.green() - 30), max(0, secondary.blue() - 30), 255))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))

        if state == "speaking":
            sx = 1.0 + 0.05 * audio
            sy = 1.0 - 0.03 * audio
        elif state == "listening":
            sx = 1.0 - 0.02 * audio
            sy = 1.0 + 0.04 * audio
        else:
            sx = 1.0 + 0.01 * math.sin(t * 1.2)
            sy = 1.0 - 0.01 * math.sin(t * 1.2)

        p.drawEllipse(QPointF(cx, cy), effective_r * sx, effective_r * sy)

    def _draw_particles(self, p, cx, cy, r, colors, t, state):
        pc = colors["particle"]
        boost = {"idle": 0.5, "listening": 0.8, "speaking": 1.0, "thinking": 0.7}.get(state, 0.5)

        for pt in self._particles:
            angle = pt["angle"] + t * pt["speed"]
            dist = r * pt["dist"] * (0.6 + 0.4 * math.sin(t * pt["wobble_freq"] + pt["phase"]))
            px = cx + math.cos(angle) * dist
            py = cy + math.sin(angle) * dist * 0.85

            if (px - cx) ** 2 + (py - cy) ** 2 > (r * 0.75) ** 2:
                continue

            twinkle = 0.5 + 0.5 * math.sin(t * 2.3 + pt["phase"] * 5)
            alpha = int((40 + 180 * pt["brightness"] * twinkle) * boost)
            size = pt["size"] * (0.8 + 0.4 * twinkle)

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pc.red(), pc.green(), pc.blue(), max(15, min(220, alpha))))
            p.drawEllipse(QPointF(px, py), size, size)

    def _draw_wave_lines(self, p, cx, cy, r, colors, t, state, audio):
        primary = colors["primary"]
        n_lines = 5
        wave_amp = (0.04 + 0.18 * audio) * r if state == "speaking" else (0.01 + 0.03 * audio) * r

        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), r, r)
        p.setClipPath(clip)

        for i in range(n_lines):
            frac = (i + 1) / (n_lines + 1)
            line_y = cy - r + frac * r * 2
            dy = line_y - cy
            half_w = math.sqrt(max(0, r * r - dy * dy))
            if half_w < 3:
                continue

            path = QPainterPath()
            for s in range(WAVE_POINTS + 1):
                fx = (s / WAVE_POINTS) * 2 * half_w - half_w
                angle_along = (s / WAVE_POINTS) * 2 * math.pi
                wy = line_y + wave_amp * math.sin(angle_along * 3 + t * 2.5 + i * 0.8) * (1 - abs(dy) / r)
                if s == 0:
                    path.moveTo(cx + fx, wy)
                else:
                    path.lineTo(cx + fx, wy)

            alpha = int(35 + 50 * (1 - abs(frac - 0.5) * 2) + 30 * audio)
            pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), alpha), 0.8)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        p.setClipping(False)

    def _draw_bars(self, p, cx, cy, r, colors, t, state):
        primary = colors["primary"]
        bar_max = r * 0.25

        for i, val in enumerate(self._bars):
            angle = (i / BARS_COUNT) * 2 * math.pi - math.pi / 2
            bar_h = val * bar_max
            x0 = cx + r * math.cos(angle)
            y0 = cy + r * math.sin(angle)
            x1 = cx + (r + bar_h) * math.cos(angle)
            y1 = cy + (r + bar_h) * math.sin(angle)

            alpha = int(70 + 170 * val)
            color = QColor(primary.red(), primary.green(), primary.blue(), max(20, min(240, alpha)))
            pen = QPen(color, 1.5)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    def _draw_core(self, p, cx, cy, r, colors, t, breath):
        primary = colors["primary"]
        core_r = r * (0.20 + 0.08 * breath)

        grad = QRadialGradient(cx, cy, core_r)
        grad.setColorAt(0.0, QColor(min(255, primary.red() + 100), min(255, primary.green() + 100), min(255, primary.blue() + 100), 220))
        grad.setColorAt(0.4, QColor(primary.red(), primary.green(), primary.blue(), 140))
        grad.setColorAt(1.0, QColor(primary.red(), primary.green(), primary.blue(), 0))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

    def _draw_ring(self, p, cx, cy, r, colors, t, state):
        primary = colors["primary"]
        speed = STATE_RING_SPEED.get(state, 0.5)
        angle = t * speed * 15

        p.save()
        p.translate(cx, cy)
        p.rotate(angle)

        dash_r = r + 4
        pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), 80), 1.2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)

        for i in range(RING_SEGMENTS):
            seg_angle = i * (360 / RING_SEGMENTS)
            p.drawArc(QRectF(-dash_r, -dash_r, dash_r * 2, dash_r * 2), int(seg_angle * 16), int(20 * 16))

        p.restore()
