"""
sopno/ui/hud/widgets/status_dot.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8px state dot with breathing halo — pulses only in thinking/speaking.
Replaces the old full-width status label row (§7 of the text-mode spec).
"""

import math

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QPainter, QRadialGradient
from PyQt5.QtWidgets import QWidget

from sopno.ui.hud.visuals.theme import STATE_ACCENT, motion_enabled


class StatusDot(QWidget):
    """Compact assistant-state indicator: solid dot + soft halo."""

    _PULSE_STATES = ("thinking", "speaking")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.state = "standby"
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state: str) -> None:
        state = (state or "standby").lower().strip()
        if state not in STATE_ACCENT:
            state = "standby"
        if state == self.state:
            return
        self.state = state
        if motion_enabled() and state in self._PULSE_STATES:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
            self.update()

    def _tick(self) -> None:
        self._phase += 0.033
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        accent = QColor(STATE_ACCENT[self.state])
        pulsing = self.state in self._PULSE_STATES and self._timer.isActive()

        halo_r = cx - 0.5
        alpha = 55
        scale = 1.0
        if pulsing:
            wave = 0.5 + 0.5 * math.sin(self._phase * math.pi * 2 / 1.6)
            halo_r *= 1.0 + 0.35 * wave
            alpha = int(30 + 45 * wave)

        glow = QRadialGradient(cx, cy, max(halo_r, 1))
        gcol = QColor(accent)
        gcol.setAlpha(alpha)
        glow.setColorAt(0.0, gcol)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        core_r = (self.width() / 2 - 2) * scale
        p.setBrush(accent)
        p.drawEllipse(QPointF(cx, cy), max(core_r, 1.5), max(core_r, 1.5))

        p.end()
