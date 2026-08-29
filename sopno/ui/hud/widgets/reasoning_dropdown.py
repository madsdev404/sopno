"""
sopno/ui/hud/widgets/reasoning_dropdown.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Compact holographic reasoning-mode dropdown — a [ Auto ▾ ] pill that
visually belongs to the same family as the HoloToggle buttons (same 26px
height, glass track, border glow) but adds a label + chevron to signal the
menu. Clicking pops a themed menu (Auto | Quick | Think | Deep | Plan).

Sibling of `HoloToggle`, never overloading it (design §5.6). Emits the chosen
mode; the HUD pushes it into the assistant via `set_reasoning_mode()`.
"""

import random
from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QRadialGradient, QPen,
)
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QToolButton

from sopno.llm import modes
from sopno.ui.hud.visuals.icons import _render_svg

# (mode, short label, menu label, tooltip)
_OPTIONS = [
    (modes.AUTO, "Auto",  "Auto",     "Auto — phrase hints choose depth per turn"),
    (modes.QUICK, "Quick", "Quick",    "Quick — short, instant answers (fastest)"),
    (modes.THINKING, "Think", "Thinking", "Thinking — visible reasoning before the reply"),
    (modes.DEEP, "Deep",  "Deep",     "Deep — large budget, hard analysis"),
    (modes.PLAN, "Plan",  "Plan",     "Plan — plan-then-execute multi-step goals"),
]

_MENU_QSS = """
    QMenu {{
        background: rgba(12, 16, 24, 0.97);
        border: 1px solid rgba(155, 140, 242, 0.35);
        border-radius: {r}px;
        padding: 4px;
    }}
    QMenu::item {{
        background: transparent;
        color: #9AABC2;
        padding: {pv}px {ph}px;
        border-radius: {r}px;
        font-size: {font}px;
    }}
    QMenu::item:selected {{
        background: rgba(155, 140, 242, 0.22);
        color: #E9E3FF;
    }}
    QMenu::item:checked {{
        color: #CDE9FF;
        font-weight: 600;
    }}
    QMenu::separator {{
        height: 1px;
        background: rgba(255, 255, 255, 0.06);
        margin: 3px {ph}px;
    }}
"""

_PALETTE = {
    "bg":        QColor(0, 18, 45),
    "border":    QColor(0, 130, 210),
    "glow":      QColor(0, 110, 200),
    "inner":     QColor(155, 140, 242),
    "accent":    QColor(155, 140, 242),
    "label":     QColor(220, 230, 248),
}


class _Rings:
    """Slow energy ring rotation around the brain icon — family tie-in."""

    def __init__(self) -> None:
        self.angle = 0.0

    def tick(self, dt: float = 16.0) -> None:
        self.angle = (self.angle + dt * 0.12) % 360.0

    def paint(self, p: QPainter, cx: float, cy: float, r: float, color: QColor) -> None:
        for i, (rr, spd, span) in enumerate([(r + 3, 1.0, 200), (r + 6, -1.2, 150)]):
            c = QColor(color)
            c.setAlpha(60 - i * 18)
            p.setPen(QPen(c, 1.0, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), int(self.angle * spd * 16), int(span * 16))


class ReasoningModeDropdown(QToolButton):
    """Compact holographic dropdown pill for quick/thinking/deep/plan/auto."""

    mode_selected = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._font = 9
        self._pv = 3
        self._ph = 8
        self._compact = False
        self._current = modes.AUTO
        self._rings = _Rings()
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setArrowType(Qt.NoArrow)
        self.setToolTip("Reasoning depth")

        self._menu = QMenu(self)
        self._actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        for mode, short, label, tip in _OPTIONS:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.triggered.connect(lambda _c, m=mode: self._choose(m))
            group.addAction(act)
            self._actions[mode] = act
            self._menu.addAction(act)
        self._menu.triggered.connect(lambda act: None)
        self.setMenu(self._menu)
        self._apply_style()

        self._tick = QTimer(self)
        self._tick.setInterval(60)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

    # ── Public API ──────────────────────────────────────────────────────

    def apply_scale(self, *, pad_v: int = 3, pad_h: int = 8,
                    font: int = 9, compact: bool = False) -> None:
        self._pv = pad_v
        self._ph = pad_h
        self._font = font
        self._compact = compact
        self._apply_style()

    def set_mode(self, mode: str, *, emit: bool = False) -> None:
        """Select a mode. With `emit`, triggers mode_selected."""
        mode = modes.normalize(mode) or modes.AUTO
        if mode != self._current:
            self._current = mode
            self._apply_style()
        if emit:
            self.mode_selected.emit(mode)

    def current_mode(self) -> str:
        return self._current

    @property
    def checked_mode(self) -> str:
        return self._current

    def _choose(self, mode: str) -> None:
        self.set_mode(mode, emit=True)

    # ── internals ───────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self._rings.tick(16.0)
        self.update()

    def _apply_style(self) -> None:
        w = 96 if not self._compact else 56
        self.setFixedSize(w, 26)
        self._menu.setStyleSheet(_MENU_QSS.format(
            r=8, pv=max(3, self._pv), ph=max(8, self._ph + 6), font=max(9, self._font),
        ))
        for mode, act in self._actions.items():
            act.setChecked(mode == self._current)
        short = next((s for m, s, _l, _t in _OPTIONS if m == self._current), "")
        self.setToolTip(f"Reasoning depth (current: {short})")
        self.update()

    def sizeHint(self) -> object:
        from PyQt5.QtCore import QSize
        return QSize(96 if not self._compact else 56, 26)

    def paintEvent(self, _event) -> None:
        q = QPainter(self)
        if not q.isActive():
            return
        q.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        r = h / 2
        C = _PALETTE
        down = self.isDown() or self.isChecked()

        # ── holo glow ────────────────────────────────────────────────
        g = QRadialGradient(w / 2, h / 2, w / 2)
        gc = QColor(C["glow"]); gc.setAlpha(38 if not down else 60)
        g.setColorAt(0, gc); g.setColorAt(1, Qt.transparent)
        q.setBrush(g); q.setPen(Qt.NoPen)
        q.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # ── track body ───────────────────────────────────────────────
        tb = QRadialGradient(w / 2, h / 2, w / 2)
        tb.setColorAt(0.0, QColor(C["bg"]))
        te = QColor(C["bg"]); te.setAlpha(35)
        tb.setColorAt(1.0, te)
        q.setBrush(tb)
        bc = QColor(C["border"]); bc.setAlpha(80 if not down else 130)
        q.setPen(QPen(bc, 1))
        q.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

        # ── glass highlight ──────────────────────────────────────────
        gh_c = QColor(C["border"]); gh_c.setAlpha(22)
        gh = QLinearGradient(0, 2, 0, h * 0.35)
        gh.setColorAt(0, gh_c); gh.setColorAt(1, Qt.transparent)
        q.setBrush(gh); q.setPen(Qt.NoPen)
        q.drawRoundedRect(QRectF(2, 2, w - 4, h * 0.35), r, r)

        cy = h / 2
        left = 14

        # ── brain icon with energy rings ─────────────────────────────
        icon_sz = 12
        self._rings.paint(q, left, cy, icon_sz / 2, C["accent"])
        icon_pm = _render_svg(
            "brain", icon_sz, "#B9A6FF" if not down else "#E8DFFF",
        )
        q.drawPixmap(int(left - icon_sz / 2), int(cy - icon_sz / 2), icon_pm)

        # ── label ────────────────────────────────────────────────────
        if not self._compact:
            short = next((s for m, s, _l, _t in _OPTIONS if m == self._current), "")
            q.setPen(QColor(C["label"]))
            q.setFont(self.font())
            q.drawText(
                QRectF(left + 7, 0, w - left - 24, h),
                Qt.AlignVCenter | Qt.AlignLeft, short,
            )

        # ── chevron ──────────────────────────────────────────────────
        chev = _render_svg("chevron-down", 9, "#7E93AE")
        q.drawPixmap(int(w - 13), int(cy - 4), chev)

        # ── scan line ────────────────────────────────────────────────
        sc = QColor(C["border"]); sc.setAlpha(45)
        q.setPen(QPen(sc, 1.0))
        sy = (self._rings.angle * 0.07) % h
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(1, 1, w - 2, h - 2), r, r)
        q.setClipPath(clip)
        q.drawLine(QPointF(1, sy), QPointF(w - 1, sy))
        q.setClipping(False)

        q.end()