"""
sopno/ui/hud/behaviors/status.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Text-mode state machine + status rendering mixin.

Routes every assistant state through the §7 machine of the text-mode spec:
drives the header StatusDot, hero face, voice orb, typing dots, the
streaming caret sweep, and the footer context meter.
"""

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont

from sopno.config.settings import settings
from sopno.ui.hud.visuals.theme import STATE_ACCENT, STATUS_COPY


class StatusMixin:
    """Renders assistant state updates onto the HUD chrome and thread."""

    def update_status(self, status: str) -> None:
        status_clean = (status or "").lower().strip()
        self.current_status = status_clean if status_clean in STATE_ACCENT else "standby"
        state = self.current_status

        # ── Presence surfaces ────────────────────────────────────────────
        if hasattr(self, "status_dot") and self.status_dot:
            self.status_dot.set_state(state)
        if hasattr(self, "robot") and self.robot:
            self.robot.set_state(state)
        if hasattr(self, "voice_orb") and self.voice_orb:
            self.voice_orb.set_state(state)

        # ── Status label under the robot ─────────────────────────────────
        label, color = STATUS_COPY[state]
        if hasattr(self, "status_label") and self.status_label:
            pt = getattr(self, "_metrics", {}).get("status_pt", 8)
            self.status_label.setText(label)
            self.status_label.setFont(QFont("IBM Plex Sans", pt, QFont.Medium))
            self.status_label.setStyleSheet(
                f"color: {color}; background: transparent; letter-spacing: 0.4px;"
            )

        # ── Header hint copy (bilingual dict, mirrors old hints) ─────────
        wake_words_str = ", ".join(getattr(settings, "wake_words", ["dream"]))
        if self.interaction_mode == "text":
            hints = {
                "standby":   "Type a message",
                "listening": "Listening…",
                "thinking":  "Thinking…",
                "speaking":  "Speaking…",
                "error":     "Something went wrong",
            }
        else:
            standby = (
                f"Say '{wake_words_str}'…"
                if getattr(settings, "listening_mode", "wake_word") == "wake_word"
                else self._listen_hint
            )
            hints = {
                "standby":   standby,
                "listening": self._listen_hint,
                "thinking":  "Thinking…",
                "speaking":  "Speaking…",
                "error":     "Something went wrong",
            }
        self.context_label.setText(hints.get(state, self._listen_hint))

        # ── Text-mode thread side effects ────────────────────────────────
        if self.interaction_mode == "text" and hasattr(self, "chat"):
            if state == "thinking":
                self.chat.begin_typing()          # ≤200ms acknowledgment (S12)
            elif state in ("standby", "listening", "error"):
                # Stop pressed before any reply, or hard error — never leave
                # orphan dots on screen.
                self.chat.end_typing()

        # ── Send ⇄ Stop morph hook (implemented by the window) ───────────
        if hasattr(self, "_set_generating"):
            self._set_generating(state in ("thinking", "streaming", "speaking"))

    def update_user_speech(self, text: str) -> None:
        if self.interaction_mode != "text":
            # Text mode echoes instantly from the composer; adding here too
            # would duplicate the bubble.
            self.chat.add_message("user", text)
        if hasattr(self, "_add_transcript_line"):
            self._add_transcript_line("user", text)
        self._sync_hero()

    def update_sopno_reply(self, text: str) -> None:
        """Reply arrived (all-at-once today): dots → live bubble + caret sweep."""
        self.chat.end_typing()
        row = self.chat.add_message("assistant", text, streaming=True)
        if hasattr(self, "_add_transcript_line"):
            self._add_transcript_line("assistant", text)
        self._sync_hero()
        self._update_context_meter()

        # Brief caret so completion is explicit, then finalize (§5.6 backend
        # note). Generation counter guards against overlapping turns.
        self._stream_gen = getattr(self, "_stream_gen", 0) + 1
        gen = self._stream_gen

        def _finalize() -> None:
            if getattr(self, "_stream_gen", 0) == gen:
                self.chat.finalize_streaming(interrupted=False)
                self._notify_assistive(row)

        QTimer.singleShot(500, _finalize)

    def _update_context_meter(self) -> None:
        """Footer meter: raw history vs summarization threshold."""
        if not (hasattr(self, "context_meter") and self.context_meter):
            return
        try:
            ratio = len(self.worker.assistant.context.raw_messages) / max(
                1, settings.max_history_length
            )
        except Exception:  # noqa: BLE001
            return
        self.context_meter.set_ratio(min(1.0, ratio))

    def _sync_hero(self) -> None:
        """Hero owns the empty state; collapse it the moment chat starts."""
        if not (hasattr(self, "hero") and self.hero):
            return
        if self.interaction_mode == "text" and self.chat.is_empty:
            if not self.hero.isVisible():
                self.hero.reset()
        elif self.hero.isVisible():
            self.hero.collapse()

    @staticmethod
    def _notify_assistive(row) -> None:
        """Raise one assistive-tech event per finalized message (§10)."""
        if row is None:
            return
        try:
            from PyQt5.QtGui import QAccessible, QAccessibleEvent

            event = QAccessibleEvent(row, QAccessible.AlertMessage)
            QAccessible.updateAccessibility(event)
        except Exception:  # noqa: BLE001
            pass

    def update_log(self, log: str) -> None:
        short = log if len(log) < 64 else log[:61] + "…"
        self.log_display.setText(short)
        print(f"[HUD Log] {log}")
