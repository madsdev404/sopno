"""
sopno/ui/hud/behaviors/status.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status, speech, reply, and log rendering mixin.
"""

from PyQt5.QtGui import QFont

from sopno.config.settings import settings
from sopno.ui.hud.visuals.theme import STATUS_COPY


class StatusMixin:
    """Renders assistant state updates onto the HUD labels."""

    def update_status(self, status: str) -> None:
        status_clean = status.lower().strip()
        self.current_status = status_clean if status_clean in STATUS_COPY else "standby"
        self.robot.set_state(self.current_status)

        label, color = STATUS_COPY[self.current_status]
        self.status_label.setText(label)
        pt = getattr(self, "_metrics", {}).get("status_pt", 8)
        self.status_label.setFont(QFont("IBM Plex Sans", pt, QFont.Medium))
        self.status_label.setStyleSheet(
            f"color: {color}; background: transparent; letter-spacing: 0.4px;"
        )

        if self.interaction_mode == "text":
            return
        wake_words_str = ", ".join(getattr(settings, "wake_words", ["dream"]))
        hints = {
            "standby":   f"Say '{wake_words_str}'…" if getattr(settings, "listening_mode", "wake_word") == "wake_word" else self._listen_hint,
            "listening": self._listen_hint,
            "thinking":  "Thinking…",
            "speaking":  "Speaking…",
            "error":     "Something went wrong",
        }
        self.context_label.setText(hints.get(self.current_status, self._listen_hint))

    def update_user_speech(self, text: str) -> None:
        self.chat.add_message("user", text)

    def update_sopno_reply(self, text: str) -> None:
        self.chat.add_message("assistant", text)

    def update_log(self, log: str) -> None:
        short = log if len(log) < 64 else log[:61] + "…"
        self.log_display.setText(short)
        print(f"[HUD Log] {log}")
