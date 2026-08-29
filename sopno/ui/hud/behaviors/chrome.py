"""
sopno/ui/hud/behaviors/chrome.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Header chrome, circular buttons, and composer mixin.
"""

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QPushButton

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

    def send_text_message(self, text: str | None = None) -> None:
        """Submit the composer draft (Enter / Send).

        Locked while generating — never two interleaved answers (S10). The
        input itself stays editable so a draft typed mid-generation survives.
        """
        if getattr(self, "_generating", False):
            return
        cleaned = (text if text is not None else self.text_input.toPlainText()).strip()
        if not cleaned:
            return
        if text is None:
            self.text_input.clear()
            if hasattr(self, "composer"):
                self.composer.refresh_height()
        self.chat.add_message("user", cleaned)
        self._sync_hero()
        if hasattr(self, "worker") and self.worker:
            self.worker.submit_text(cleaned)

    def stop_generation(self) -> None:
        """Stop button / Esc while generating — halts the in-flight turn."""
        if hasattr(self, "worker") and self.worker:
            self.worker.stop_generation()

    def _set_generating(self, busy: bool) -> None:
        """Send ⇄ Stop morph on the composer."""
        busy = bool(busy)
        if getattr(self, "_generating", False) == busy:
            return
        self._generating = busy
        if hasattr(self, "composer"):
            self.composer.set_generating(busy)

    def _sync_composer_enabled(self) -> None:
        """Composer manages its own send-button state."""
        if hasattr(self, "composer"):
            self.composer._sync_send_state()
