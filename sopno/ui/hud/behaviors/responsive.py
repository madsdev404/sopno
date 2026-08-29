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
                context_pt=8, face=56, mini_face=24, status_pt=7, tag_pt=7, body_pt=8,
                bubble_pad=7, bubble_r=10, bubble_gap=6, log_pt=6,
                send=28, send_icon=14, mode_pad_v=3, mode_pad_h=8,
                mode_font=9, mode_icon=14, mode_r=12, show_status=False, show_log=False,
                hint="Listening…",
                avatar=14, ts_visible=False, copy_visible=False,
                hero_face=52, footer_strip="hidden",
            )
        elif w < 440:
            base = dict(
                margin=10, gap=6, chrome=22, icon=14, chrome_font=13,
                context_pt=8, face=78, mini_face=27, status_pt=8, tag_pt=7, body_pt=9,
                bubble_pad=8, bubble_r=12, bubble_gap=7, log_pt=6,
                send=30, send_icon=15, mode_pad_v=4, mode_pad_h=10,
                mode_font=10, mode_icon=14, mode_r=12, show_status=True, show_log=True,
                hint="Listening… say something",
                avatar=16, ts_visible=True, copy_visible=True,
                hero_face=72, footer_strip="log",
            )
        else:
            base = dict(
                margin=14, gap=8, chrome=24, icon=15, chrome_font=14,
                context_pt=9, face=110, mini_face=30, status_pt=9, tag_pt=8, body_pt=10,
                bubble_pad=10, bubble_r=14, bubble_gap=8, log_pt=7,
                send=34, send_icon=17, mode_pad_v=5, mode_pad_h=12,
                mode_font=11, mode_icon=14, mode_r=12, show_status=True, show_log=True,
                hint="Listening… say something",
                avatar=20, ts_visible=True, copy_visible=True,
                hero_face=100, footer_strip="full",
            )

        if is_voice:
            base["face"] = min(base["face"] + 30, 150)

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
        radius = 8 if self.width() < 320 else 10
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

        if hasattr(self, "voice_orb") and self.voice_orb:
            self.voice_orb.face.set_face_size(m["face"])
        if hasattr(self, "robot") and self.robot:
            # Text mode keeps presence minimal: a tiny face top-left.
            self.robot.set_face_size(m["mini_face"])
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setFont(
                QFont("IBM Plex Sans", m["status_pt"], QFont.Medium)
            )
        if hasattr(self, "hero") and self.hero:
            self.hero.apply_scale(
                pt=m["body_pt"],
                pv=max(2, m["mode_pad_v"] - 1),
                ph=m["mode_pad_h"],
            )
        footer = m["footer_strip"]
        if hasattr(self, "footer_strip"):
            self.footer_strip.setVisible(footer != "hidden")
            self.log_display.setVisible(footer in ("log", "full"))
            self.context_meter.setVisible(footer == "full")
            self.resize_hint.setVisible(footer == "full")
        self.log_display.setFont(QFont("IBM Plex Mono", m["log_pt"]))

        self.mode_toggle.apply_scale(
            pad_v=m["mode_pad_v"],
            pad_h=m["mode_pad_h"],
            font=m["mode_font"],
            icon=m["mode_icon"],
            radius=m["mode_r"],
        )
        reason = getattr(self, "reasoning_selector", None)
        if reason is not None:
            # Header is tight below ~small: defer to phrase/config overrides.
            reason.setVisible(self.width() >= 360)
            reason.apply_scale(
                pad_v=max(2, m["mode_pad_v"] - 2),
                pad_h=max(4, m["mode_pad_h"] - 4),
                font=max(7, m["mode_font"] - 1),
                radius=m["mode_r"],
            )
        self.chat.apply_scale(body_pt=m["body_pt"])
        # §4.3: cap the transcript measure on wide windows (~70ch column).
        self.chat.set_column_width(560 if self.width() >= 440 else None)

        if hasattr(self, "composer"):
            self.composer.apply_scale(
                body_pt=m["body_pt"],
                send=m["send"],
                send_icon=m["send_icon"],
                mode_r=m["mode_r"],
            )

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
