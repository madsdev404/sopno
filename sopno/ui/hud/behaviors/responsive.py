"""
sopno/ui/hud/behaviors/responsive.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Responsive sizing mixin: preset sizes, drag-resize scaling, density tokens.
"""

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from sopno.config.settings import settings
from sopno.ui.hud.visuals.icons import _paint_icon
from sopno.ui.hud.visuals.theme import SIZE_PRESETS, _CHROME


class ResponsiveMixin:
    """Sizes, scales, and re-styles the HUD from the current window width."""

    def _metrics_for_width(self, w: int) -> dict:
        """Responsive tokens from panel width — voice mode has larger orb."""
        is_voice = getattr(self, "interaction_mode", "voice") == "voice"

        if w < 320:
            base = dict(
                margin=8, gap=4, chrome=20, icon=12, chrome_font=12,
                context_pt=8, face=56, status_pt=7, tag_pt=7, body_pt=8,
                bubble_pad=7, bubble_r=10, bubble_gap=6, log_pt=6,
                send=28, send_icon=14, mode_pad_v=3, mode_pad_h=8,
                mode_font=9, mode_icon=11, mode_r=12, show_status=False, show_log=False,
                hint="Listening…",
            )
        elif w < 440:
            base = dict(
                margin=10, gap=6, chrome=22, icon=14, chrome_font=13,
                context_pt=8, face=78, status_pt=8, tag_pt=7, body_pt=9,
                bubble_pad=8, bubble_r=12, bubble_gap=7, log_pt=6,
                send=30, send_icon=15, mode_pad_v=4, mode_pad_h=10,
                mode_font=10, mode_icon=12, mode_r=14, show_status=True, show_log=True,
                hint="Listening… say something",
            )
        else:
            base = dict(
                margin=14, gap=8, chrome=24, icon=15, chrome_font=14,
                context_pt=9, face=110, status_pt=9, tag_pt=8, body_pt=10,
                bubble_pad=10, bubble_r=14, bubble_gap=8, log_pt=7,
                send=34, send_icon=17, mode_pad_v=5, mode_pad_h=12,
                mode_font=11, mode_icon=13, mode_r=16, show_status=True, show_log=True,
                hint="Listening… say something",
            )

        if is_voice:
            base["face"] = min(base["face"] + 30, 150)
        else:
            base["face"] = 56

        return base

    def _apply_responsive(self) -> None:
        """Scale header, type, icons, robot, chat to current window size."""
        if not hasattr(self, "context_label"):
            return
        m = self._metrics_for_width(self.width())
        self._metrics = m
        self._listen_hint = m["hint"]

        pad = m["margin"]
        self._root.setContentsMargins(pad, pad - 2, pad - 2, pad - 2)
        radius = 8 if self.width() < 320 else (10 if self.width() < 440 else 10)
        self.central_widget.setStyleSheet(f"""
            QWidget#CentralWidget {{
                background-color: rgba(12, 16, 24, {settings.hud_opacity});
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {radius}px;
            }}
        """)

        self.context_label.setFont(QFont("IBM Plex Sans", m["context_pt"]))
        self.context_label.setMaximumHeight(m["chrome"] + 2)
        if self.interaction_mode == "voice" and self.current_status in ("standby", "listening"):
            self.context_label.setText(self._listen_hint)

        c = m["chrome"]
        ic = m["icon"]
        for key, btn in self._win_btns.items():
            btn.setFixedSize(c, c)
            btn.setIconSize(QSize(ic, ic))

        for btn, hover in (
            (self.hide_btn, "#E8A0BF"),
            (self.close_btn, "#F07178"),
        ):
            btn.setFixedSize(c, c)
            btn.setIconSize(QSize(ic, ic))
            btn.setStyleSheet(_CHROME.format(hover=hover, font_size=m["chrome_font"]))

        self._refresh_win_btns()

        self.robot.set_face_size(m["face"])
        self.status_label.setVisible(m["show_status"])
        self.status_label.setFont(QFont("IBM Plex Sans", m["status_pt"], QFont.Medium))
        self.log_display.setVisible(m["show_log"])
        self.log_display.setFont(QFont("IBM Plex Mono", m["log_pt"]))

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

        self.dock.setStyleSheet(f"""
            QFrame#Dock {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: {max(12, m['mode_r'])}px;
            }}
        """)

        self._apply_mode_layout()

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
