"""
sopno/ui/hud/widgets/reasoning_dropdown.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Compact holographic dropdown pills — a [ Auto ▾ ] / [ qwen3:8b ▾ ] pill that
visually belongs to the same family as the HoloToggle buttons (same 26px
height, glass track, border glow) but adds a label + chevron to signal the
menu. Clicking pops a themed QMenu.

Shared base `_HoloDropDownBase` drives reasoning-mode and model selection:
- `ReasoningModeDropdown` — Auto | Quick | Think | Deep | Plan
  (never overloads the Voice|Text HoloToggle, design §5.6).
- `ModelDropdown` — selectable LLM names (HUD-only surface today; the
  assistant's model switching is a deferred slot).

The HUD pushes selections into the assistant via calls it wires itself.
"""

import random
from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QRadialGradient, QPen,
)
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QToolButton

from sopno.config.settings import settings
from sopno.llm import modes
from sopno.ui.hud.visuals.icons import _render_svg

# (mode, short label, menu label, tooltip)
_MODE_OPTIONS = [
    (modes.AUTO, "Auto",  "Auto",     "Auto — phrase hints choose depth per turn"),
    (modes.QUICK, "Quick", "Quick",    "Quick — short, instant answers (fastest)"),
    (modes.THINKING, "Think", "Thinking", "Thinking — visible reasoning before the reply"),
    (modes.DEEP, "Deep",  "Deep",     "Deep — large budget, hard analysis"),
    (modes.PLAN, "Plan",  "Plan",     "Plan — plan-then-execute multi-step goals"),
]

# (model, short label, menu label, tooltip) — placeholder list; the HUD only
# surfaces selection today ("don't work about model"). Defaults to the config.
_MODEL_BASE = [getattr(settings, "model_name", "qwen3:8b") or "qwen3:8b"]
_MODEL_CANDIDATES = [
    "qwen3:14b", "qwen3:32b", "qwen3:4b-instruct", "llama3.1:8b", "phi4-mini:3.8b",
]
_MODEL_OPTIONS = [
    (m, m if len(m) <= 14 else m[:12] + "…", m, f"Use {m} for replies")
    for m in list(dict.fromkeys(_MODEL_BASE + _MODEL_CANDIDATES))
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
    """Slow energy ring rotation around the leading icon — family tie-in."""

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


class _HoloDropDownBase(QToolButton):
    """Shared holographic dropdown pill rendering + popup menu behaviour."""

    def __init__(self, options, *, icon: str = "brain", title: str = "Selection",
                 parent=None, width: int = 96, compact_width: int = 56) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._icon = icon
        self._title = title
        self._full_w = width
        self._compact_w = compact_width
        self._font = 9
        self._pv = 3
        self._ph = 8
        self._compact = False
        self._current = options[0][0]
        self._rings = _Rings()
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setArrowType(Qt.NoArrow)
        self.setToolTip(title)

        self._menu = QMenu(self)
        self._actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        for value, _short, label, tip in options:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.triggered.connect(lambda _c, v=value: self._choose(v))
            group.addAction(act)
            self._actions[value] = act
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

    def set_value(self, value: str, *, emit: bool = False) -> None:
        """Select an option. With `emit`, triggers the concrete signal."""
        value = self._normalize(value)
        if value != self._current:
            self._current = value
            self._apply_style()
        if emit:
            self._emit(value)

    def current_value(self) -> str:
        return self._current

    def _normalize(self, value: str) -> str:
        value = (value or "").strip().lower()
        return value if any(o[0] == value for o in self._options) else self._options[0][0]

    def _emit(self, _value: str) -> None:
        pass

    def _choose(self, value: str) -> None:
        self.set_value(value, emit=True)

    # ── internals ───────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self._rings.tick(16.0)
        self.update()

    def _label(self, value: str) -> str:
        return next((s for v, s, _l, _t in self._options if v == value), "")

    def _apply_style(self) -> None:
        w = self._full_w if not self._compact else self._compact_w
        self.setFixedSize(w, 26)
        self._menu.setStyleSheet(_MENU_QSS.format(
            r=8, pv=max(3, self._pv), ph=max(8, self._ph + 6), font=max(9, self._font),
        ))
        for value, act in self._actions.items():
            act.setChecked(value == self._current)
        short = self._label(self._current)
        self.setToolTip(f"{self._title} (current: {short})")
        self.update()

    def sizeHint(self) -> object:
        from PyQt5.QtCore import QSize
        w = self._full_w if not self._compact else self._compact_w
        return QSize(w, 26)

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

        # ── leading icon with energy rings ───────────────────────────
        icon_sz = 12
        self._rings.paint(q, left, cy, icon_sz / 2, C["accent"])
        icon_pm = _render_svg(
            self._icon, icon_sz, "#B9A6FF" if not down else "#E8DFFF",
        )
        q.drawPixmap(int(left - icon_sz / 2), int(cy - icon_sz / 2), icon_pm)

        # ── label ────────────────────────────────────────────────────
        if not self._compact:
            short = self._label(self._current)
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


class ReasoningModeDropdown(_HoloDropDownBase):
    """Compact holographic dropdown pill for quick/thinking/deep/plan/auto."""

    mode_selected = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(_MODE_OPTIONS, icon="brain", title="Reasoning depth",
                         parent=parent)

    def set_mode(self, mode: str, *, emit: bool = False) -> None:
        """Select a mode. With `emit`, triggers mode_selected."""
        self.set_value(mode, emit=emit)

    def current_mode(self) -> str:
        return self._current

    @property
    def checked_mode(self) -> str:
        return self._current

    def _normalize(self, mode: str) -> str:
        return modes.normalize(mode) or modes.AUTO

    def _emit(self, mode: str) -> None:
        self.mode_selected.emit(mode)


class ModelDropdown(_HoloDropDownBase):
    """Holographic dropdown pill for selectable LLM models (HUD surface only)."""

    model_selected = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(_MODEL_OPTIONS, icon="cpu", title="Model model",
                         parent=parent, width=108, compact_width=56)

    def set_model(self, model: str, *, emit: bool = False) -> None:
        """Select a model. With `emit`, triggers model_selected."""
        self.set_value(model, emit=emit)

    def current_model(self) -> str:
        return self._current

    def _emit(self, model: str) -> None:
        self.model_selected.emit(model)