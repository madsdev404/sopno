"""
sopno/ui/hud/behaviors/chrome.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Header chrome, circular buttons, listening chip, and composer mixin.
"""

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QPushButton

from sopno.config.settings import settings
from sopno.ui.hud.visuals.icons import _paint_icon
from sopno.ui.hud.visuals.theme import _CHROME, _ICON_BTN


class ChromeMixin:
    """Window chrome buttons, listening-mode chip, and the text composer."""

    def _chrome_btn(
        self,
        text: str,
        hover: str,
        tip: str,
        *,
        size: int = 22,
        font_size: int = 14,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(size, size)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(tip)
        btn.setStyleSheet(_CHROME.format(hover=hover, font_size=font_size))
        btn.setProperty("hover_color", hover)
        return btn

    def _circle_btn(self, kind: str, *, tip: str, active: bool, accent: bool) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(32, 32)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(tip)
        btn.setIcon(_paint_icon(kind, 32, active=active))
        btn.setProperty("icon_kind", kind)
        bg, border = "rgba(255, 255, 255, 0.04)", "rgba(255, 255, 255, 0.08)"
        hbg, hb = "rgba(255, 255, 255, 0.08)", "rgba(255, 255, 255, 0.14)"
        pbg = "rgba(255, 255, 255, 0.12)"
        btn.setStyleSheet(_ICON_BTN.format(
            bg=bg, border=border, hover_bg=hbg, hover_border=hb, pressed_bg=pbg,
        ))
        return btn

    def _style_listening_chip(self) -> None:
        mode = getattr(settings, "listening_mode", "wake_word")
        is_wake = mode == "wake_word"
        text = "🔔 Wake" if is_wake else "🎤 Always"
        self.listening_chip.setText(text)
        self.listening_chip.setChecked(is_wake)
        self.listening_chip.setFixedWidth(68)
        if is_wake:
            self.listening_chip.setStyleSheet("""
                QPushButton {
                    background: rgba(155, 140, 242, 0.15);
                    color: #C4B8F0;
                    border: 1px solid rgba(155, 140, 242, 0.25);
                    border-radius: 9px;
                    font-size: 8px;
                    font-weight: 600;
                    padding: 0px 6px;
                }
                QPushButton:hover {
                    background: rgba(155, 140, 242, 0.25);
                    border-color: rgba(155, 140, 242, 0.40);
                }
            """)
        else:
            self.listening_chip.setStyleSheet("""
                QPushButton {
                    background: rgba(74, 222, 154, 0.15);
                    color: #A0F0C8;
                    border: 1px solid rgba(74, 222, 154, 0.25);
                    border-radius: 9px;
                    font-size: 8px;
                    font-weight: 600;
                    padding: 0px 6px;
                }
                QPushButton:hover {
                    background: rgba(74, 222, 154, 0.25);
                    border-color: rgba(74, 222, 154, 0.40);
                }
            """)

    def send_text_message(self) -> None:
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self.chat.add_message("user", text)
        if hasattr(self, "worker") and self.worker:
            self.worker.submit_text(text)

    def _toggle_listening_mode(self) -> None:
        current = getattr(settings, "listening_mode", "wake_word")
        new_mode = "always_on" if current == "wake_word" else "wake_word"
        self.set_listening_mode(new_mode)
