"""
sopno/ui/hud/widgets/holo_toggle.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Holographic sci-fi toggle switch — glassmorphism with energy rings,
scan line, glow, and particle effects. Lucide icon on thumb. Pure QPainter.
"""

import random
from PyQt5.QtCore import (
    QEasingCurve, QPointF, QPropertyAnimation, QRectF,
    Qt, QTimer, pyqtProperty, pyqtSignal,
)
from PyQt5.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QRadialGradient, QPen,
)
from PyQt5.QtWidgets import QWidget

from sopno.ui.hud.visuals.icons import _render_svg


class _EnergyRings:
    def __init__(self) -> None:
        self.angle = 0.0

    def tick(self, dt: float = 16.0) -> None:
        self.angle = (self.angle + dt * 0.12) % 360.0

    def paint(self, p: QPainter, cx: float, cy: float, on: bool, color: QColor) -> None:
        if not on:
            return
        for i, (r, spd, span) in enumerate([(16, 1.0, 200), (12, -1.4, 160), (9, 2.0, 240)]):
            c = QColor(color)
            c.setAlpha(80 - i * 18)
            p.setPen(QPen(c, 1.2, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), int(self.angle * spd * 16), int(span * 16))


class _Particles:
    def __init__(self) -> None:
        self.dots: list[dict] = []
        self._timer = 0.0

    def tick(self, dt: float = 16.0, on: bool = False) -> None:
        self._timer += dt
        if on and self._timer > 250:
            self._timer = 0.0
            if len(self.dots) < 4:
                self.dots.append({
                    "x": random.uniform(-5, 5), "y": 0.0,
                    "vx": random.uniform(-0.2, 0.2), "vy": random.uniform(-0.12, -0.05),
                    "life": 0.0, "max": random.uniform(0.6, 1.3),
                    "sz": random.uniform(0.8, 2.0),
                })
        for d in self.dots[:]:
            d["life"] += dt / 1000.0
            d["x"] += d["vx"] * dt / 16.0
            d["y"] += d["vy"] * dt / 16.0
            if d["life"] > d["max"]:
                self.dots.remove(d)

    def paint(self, p: QPainter, cx: float, cy: float, color: QColor) -> None:
        for d in self.dots:
            prog = d["life"] / d["max"]
            a = max(0, int(160 * (1.0 - prog)))
            if a < 5:
                continue
            c = QColor(color)
            c.setAlpha(a)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            sz = d["sz"] * (1.0 - prog * 0.5)
            p.drawEllipse(QPointF(cx + d["x"], cy + d["y"]), sz, sz)


class HoloToggle(QWidget):
    """Holographic toggle — 76×26, Lucide icon on thumb."""

    toggled = pyqtSignal(bool)

    _OFF = {
        "track_bg": QColor(0, 18, 45),
        "track_border": QColor(0, 90, 180),
        "track_glow": QColor(0, 70, 170),
        "thumb_bg": QColor(8, 35, 80),
        "thumb_border": QColor(0, 130, 210),
        "thumb_core": QColor(0, 140, 210),
        "thumb_inner": QColor(80, 180, 240),
        "scan": QColor(0, 140, 230),
        "indicator": QColor(0, 150, 220),
    }

    _ON = {
        "track_bg": QColor(0, 45, 22),
        "track_border": QColor(0, 200, 110),
        "track_glow": QColor(0, 200, 120),
        "thumb_bg": QColor(8, 60, 30),
        "thumb_border": QColor(0, 220, 130),
        "thumb_core": QColor(0, 210, 120),
        "thumb_inner": QColor(130, 240, 200),
        "scan": QColor(0, 220, 130),
        "indicator": QColor(0, 200, 110),
    }

    def __init__(self, off_icon: str = "close", on_icon: str = "close",
                 *, initial: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._checked = initial
        self._off_icon = off_icon
        self._on_icon = on_icon
        self._pos = 1.0 if initial else 0.0
        self._scan_y = -3.0
        self._rings = _EnergyRings()
        self._particles = _Particles()
        self._anim = None

        self.setFixedSize(76, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

    def apply_scale(self, **kw) -> None:
        pass

    @property
    def checked(self) -> bool:
        return self._checked

    def toggle(self) -> None:
        self.setChecked(not self._checked)

    def setChecked(self, val: bool) -> None:
        if val == self._checked:
            return
        self._checked = val
        self._start_slide()
        self.toggled.emit(val)

    def mousePressEvent(self, _event) -> None:
        self.toggle()

    def _start_slide(self) -> None:
        if self._anim and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"thumb_pos")
        self._anim.setDuration(300)
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if self._checked else 0.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def get_thumb_pos(self) -> float:
        return self._pos

    def set_thumb_pos(self, val: float) -> None:
        self._pos = val
        self.update()

    thumb_pos = pyqtProperty(float, get_thumb_pos, set_thumb_pos)

    def _on_tick(self) -> None:
        self._rings.tick(16.0)
        self._particles.tick(16.0, on=self._checked)
        self._scan_y += 0.3
        if self._scan_y > self.height() + 3:
            self._scan_y = -3.0
        self.update()

    def paintEvent(self, _event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        C = self._ON if self._checked else self._OFF
        track_r = h / 2
        thumb_r = (h - 4) / 2
        travel = w - h

        # ── holo glow ────────────────────────────────────────────────
        g = QRadialGradient(w / 2, h / 2, w / 2)
        gc = QColor(C["track_glow"]); gc.setAlpha(40)
        g.setColorAt(0, gc); g.setColorAt(1, Qt.transparent)
        q.setBrush(g); q.setPen(Qt.NoPen)
        q.drawRoundedRect(QRectF(0, 0, w, h), track_r, track_r)

        # ── track body ───────────────────────────────────────────────
        tb = QRadialGradient(w / 2, h / 2, w / 2)
        tb.setColorAt(0.0, QColor(C["track_bg"]))
        te = QColor(C["track_bg"]); te.setAlpha(35)
        tb.setColorAt(1.0, te)
        q.setBrush(tb)
        bc = QColor(C["track_border"]); bc.setAlpha(70)
        q.setPen(QPen(bc, 1))
        q.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), track_r, track_r)

        # ── glass highlight ──────────────────────────────────────────
        gh_c = QColor(C["track_border"]); gh_c.setAlpha(20)
        gh = QLinearGradient(0, 2, 0, h * 0.3)
        gh.setColorAt(0, gh_c); gh.setColorAt(1, Qt.transparent)
        q.setBrush(gh); q.setPen(Qt.NoPen)
        q.drawRoundedRect(QRectF(2, 2, w - 4, h * 0.3), track_r, track_r)

        # ── thumb position ───────────────────────────────────────────
        tx = 2 + self._pos * travel
        cy = h / 2

        # ── energy rings ─────────────────────────────────────────────
        self._rings.paint(q, tx + thumb_r, cy, self._checked, C["thumb_border"])

        # ── thumb outer glow ─────────────────────────────────────────
        tg = QRadialGradient(tx + thumb_r, cy, thumb_r + 5)
        tgc = QColor(C["thumb_core"]); tgc.setAlpha(50 if self._checked else 20)
        tg.setColorAt(0, tgc); tg.setColorAt(1, Qt.transparent)
        q.setBrush(tg); q.setPen(Qt.NoPen)
        q.drawEllipse(QPointF(tx + thumb_r, cy), thumb_r + 5, thumb_r + 5)

        # ── thumb body ───────────────────────────────────────────────
        tbg = QRadialGradient(tx + thumb_r, cy, thumb_r)
        tbg.setColorAt(0.0, QColor(C["thumb_bg"]))
        te2 = QColor(C["thumb_bg"]); te2.setAlpha(170)
        tbg.setColorAt(1.0, te2)
        q.setBrush(tbg)
        q.setPen(QPen(QColor(C["thumb_border"]), 1.0))
        q.drawEllipse(QPointF(tx + thumb_r, cy), thumb_r, thumb_r)

        # ── thumb inner ring ─────────────────────────────────────────
        ir = thumb_r * 0.70
        ig = QRadialGradient(tx + thumb_r, cy, ir)
        igc = QColor(C["thumb_core"]); igc.setAlpha(40)
        ig.setColorAt(0, igc); ig.setColorAt(1, Qt.transparent)
        q.setBrush(ig); q.setPen(Qt.NoPen)
        q.drawEllipse(QPointF(tx + thumb_r, cy), ir, ir)

        # ── thumb core ───────────────────────────────────────────────
        cr = thumb_r * 0.32
        cg = QRadialGradient(tx + thumb_r, cy, cr)
        cc = QColor(C["thumb_core"]); cc.setAlpha(170)
        cg.setColorAt(0, cc)
        ci = QColor(C["thumb_inner"]); ci.setAlpha(90)
        cg.setColorAt(1, ci)
        q.setBrush(cg); q.setPen(Qt.NoPen)
        q.drawEllipse(QPointF(tx + thumb_r, cy), cr, cr)

        # ── bright center ────────────────────────────────────────────
        bc2 = QColor(C["thumb_inner"]); bc2.setAlpha(200)
        q.setBrush(bc2); q.setPen(Qt.NoPen)
        q.drawEllipse(QPointF(tx + thumb_r, cy), cr * 0.4, cr * 0.4)

        # ── scan line ────────────────────────────────────────────────
        sc = QColor(C["scan"]); sc.setAlpha(80)
        q.setPen(QPen(sc, 1.0))
        clip = QPainterPath()
        clip.addEllipse(QPointF(tx + thumb_r, cy), thumb_r, thumb_r)
        q.setClipPath(clip)
        q.drawLine(QPointF(tx - 2, self._scan_y), QPointF(tx + thumb_r * 2 + 2, self._scan_y))
        q.setClipping(False)

        # ── particles ────────────────────────────────────────────────
        self._particles.paint(q, tx + thumb_r, cy, C["thumb_core"])

        # ── Lucide icon on thumb ─────────────────────────────────────
        icon_kind = self._on_icon if self._checked else self._off_icon
        icon_sz = max(8, int(thumb_r * 1.1))
        icon_color = "#FFFFFF" if self._checked else "#A0C0E8"
        icon_pm = _render_svg(icon_kind, icon_sz, icon_color)
        ix = tx + thumb_r - icon_sz / 2
        iy = cy - icon_sz / 2
        q.setOpacity(0.9)
        q.drawPixmap(int(ix), int(iy), icon_pm)
        q.setOpacity(1.0)

        # ── status indicator dot ─────────────────────────────────────
        ind = QColor(C["indicator"])
        ind.setAlpha(140 if self._checked else 60)
        q.setBrush(ind); q.setPen(Qt.NoPen)
        if self._checked:
            q.drawEllipse(QPointF(w - 7, h / 2), 2.5, 2.5)
            ig2 = QRadialGradient(w - 7, h / 2, 4)
            ig2c = QColor(C["indicator"]); ig2c.setAlpha(40)
            ig2.setColorAt(0, ig2c); ig2.setColorAt(1, Qt.transparent)
            q.setBrush(ig2)
            q.drawEllipse(QPointF(w - 7, h / 2), 4, 4)
        else:
            q.drawEllipse(QPointF(w - 7, h / 2), 2, 2)

        q.end()
