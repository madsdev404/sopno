"""
sopno/ui/hud/window.py
━━━━━━━━━━━━━━━━━━━━━━
The floating HUD main window — builds the layout and wires it to the assistant.
"""

from __future__ import annotations

import threading

from PyQt5.QtCore import QSize, Qt, QEvent, QRect, QTimer
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sopno.config.settings import settings
from sopno.ui.hud.behaviors import ChromeMixin, ResponsiveMixin, ResizeMixin, StatusMixin, TrayMixin
from sopno.ui.hud.dashboard import DashboardPanel
from sopno.ui.hud.visuals.icons import _paint_icon
from sopno.ui.hud.visuals.theme import MIN_SIZE, motion_enabled
from sopno.ui.hud.widgets import AliveRobotFace, ChatThread, ContextMeter, StatusDot, VoiceModeOrb
from sopno.ui.hud.widgets.holo_toggle import HoloToggle
from sopno.ui.hud.widgets.text_hero import TextHero
from sopno.ui.hud.worker import AssistantWorker


class SopnoHUDWindow(
    QMainWindow,
    ChromeMixin,
    ResponsiveMixin,
    ResizeMixin,
    StatusMixin,
    TrayMixin,
):
    """Floating companion panel — preset sizes + drag-resize."""

    def __init__(self) -> None:
        super().__init__()
        self.old_pos = None
        self._resize_edge = None
        self._press_geo = None
        self._press_global = None
        self.size_mode = "medium"
        self.interaction_mode = "voice"
        self.current_status = "listening"
        self._listen_hint = "Listening… say something"
        self._is_maximized = False
        self._prev_geo = None
        self._generating = False
        self._ph_idx = 0

        self.init_ui()
        self.init_tray()
        self._init_shortcuts()

        self.worker = AssistantWorker()
        self.thread = threading.Thread(target=self.worker.start_loop, daemon=True)
        self.worker.status_changed.connect(self.update_status)
        self.worker.speech_detected.connect(self.update_user_speech)
        self.worker.reply_generated.connect(self.update_sopno_reply)
        self.worker.log_message.connect(self.update_log)
        self.worker.log_message.connect(
            lambda msg: self.dashboard.append_log(msg) if self.dashboard else None
        )
        self.thread.start()

    def _init_shortcuts(self) -> None:
        from PyQt5.QtWidgets import QShortcut
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close_app)
        QShortcut(QKeySequence("Escape"), self, self._escape_pressed)
        QShortcut(QKeySequence("Ctrl+M"), self, self._toggle_maximize)
        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_dashboard)
        QShortcut(QKeySequence("Ctrl+T"), self, lambda: self.set_interaction_mode("text"))
        QShortcut(QKeySequence("Ctrl+R"), self, lambda: self.set_interaction_mode("voice"))

    def init_ui(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysShowToolTips, True)
        self.setMinimumSize(*MIN_SIZE)
        self.setMouseTracking(True)

        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setMouseTracking(True)
        self.central_widget.setStyleSheet(f"""
            QWidget#CentralWidget {{
                background-color: rgba(12, 16, 24, {settings.hud_opacity});
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 8)
        self.central_widget.setGraphicsEffect(shadow)

        root = QVBoxLayout(self.central_widget)
        root.setContentsMargins(12, 8, 8, 8)
        root.setSpacing(0)
        self._root = root

        # ── Header (always visible): status line · mode toggle · chrome ──────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self._header = header

        self.status_dot = StatusDot()
        self.status_dot.set_state("standby")
        header.addWidget(self.status_dot, 0, Qt.AlignVCenter)

        self.context_label = QLabel(self._listen_hint)
        self.context_label.setFont(QFont("IBM Plex Sans", 8))
        self.context_label.setStyleSheet("color: #6B7C94; background: transparent;")
        self.context_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.context_label.setMaximumHeight(20)

        # ── Window controls ───────────────────────────────────────────────────
        self._win_btns: dict[str, QPushButton] = {}

        chrome = QHBoxLayout()
        chrome.setSpacing(0)
        chrome.setContentsMargins(0, 0, 0, 0)
        chrome.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._chrome = chrome

        self.hide_btn = self._chrome_btn(
            "", "#E8A0BF", "Hide to system tray", size=22, font_size=14,
        )
        self.hide_btn.setIcon(_paint_icon("hide", 14, active=False))
        self.hide_btn.setIconSize(QSize(14, 14))
        self.hide_btn.clicked.connect(self.hide_hud)
        chrome.addWidget(self.hide_btn, 0, Qt.AlignVCenter)

        self.maximize_btn = self._chrome_btn(
            "", "#E8EEF7", "Maximize", size=22, font_size=14,
        )
        self.maximize_btn.setIcon(_paint_icon("maximize", 14, active=False))
        self.maximize_btn.setIconSize(QSize(14, 14))
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        self._win_btns["maximize"] = self.maximize_btn
        chrome.addWidget(self.maximize_btn, 0, Qt.AlignVCenter)

        self.close_btn = self._chrome_btn(
            "", "#F07178", "Close", size=22, font_size=14,
        )
        self.close_btn.setIcon(_paint_icon("close", 14, active=False))
        self.close_btn.setIconSize(QSize(14, 14))
        self.close_btn.clicked.connect(self.close_app)
        chrome.addWidget(self.close_btn, 0, Qt.AlignVCenter)

        header.addWidget(self.context_label, 1)
        header.addLayout(chrome)
        root.addLayout(header)
        root.addSpacing(4)

        # ── Voice mode stage ──────────────────────────────────────────────────
        self.voice_stage = QFrame()
        self.voice_stage.setObjectName("VoiceStage")
        self.voice_stage.setStyleSheet("QFrame#VoiceStage { background: transparent; }")
        self.voice_stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        voice_layout = QVBoxLayout(self.voice_stage)
        voice_layout.setContentsMargins(0, 0, 0, 0)
        voice_layout.setSpacing(4)

        self.voice_orb = VoiceModeOrb(size=300)
        self.voice_orb.setVisible(False)
        voice_layout.addWidget(self.voice_orb, 1)

        # ── Controls row: wake toggle (left) + mode toggle (right) ─────
        self._controls_row = QHBoxLayout()
        self._controls_row.setContentsMargins(0, 0, 0, 0)
        self._controls_row.setSpacing(6)
        self._controls_row.addStretch(1)

        self.wake_toggle = HoloToggle("bell", "ear",
            initial=(getattr(settings, "listening_mode", "wake_word") == "always_on"))
        self.wake_toggle.setToolTip("Toggle wake word vs always-on listening")
        self.wake_toggle.toggled.connect(self._on_wake_toggle)
        self._controls_row.addWidget(self.wake_toggle, 0, Qt.AlignVCenter)

        self.mode_toggle = HoloToggle("mic", "newspaper", initial=False)
        self.mode_toggle.setToolTip("Toggle voice ↔ text mode")
        self.mode_toggle.toggled.connect(self._on_mode_toggle)
        self._controls_row.addWidget(self.mode_toggle, 0, Qt.AlignVCenter)
        self._controls_row.addStretch(1)

        voice_layout.addLayout(self._controls_row)

        # ── Compact transcript (voice mode) ───────────────────────────────────
        self.voice_transcript = QScrollArea()
        self.voice_transcript.setObjectName("VoiceTranscript")
        self.voice_transcript.setWidgetResizable(True)
        self.voice_transcript.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.voice_transcript.setFrameShape(QFrame.NoFrame)
        self.voice_transcript.setMaximumHeight(80)
        self.voice_transcript.setStyleSheet("""
            QScrollArea#VoiceTranscript {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.1);
                border-radius: 1px;
                min-height: 10px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self._transcript_inner = QWidget()
        self._transcript_inner.setStyleSheet("background: transparent;")
        self._transcript_col = QVBoxLayout(self._transcript_inner)
        self._transcript_col.setContentsMargins(8, 4, 8, 4)
        self._transcript_col.setSpacing(2)
        self._transcript_col.addStretch(1)
        self.voice_transcript.setWidget(self._transcript_inner)
        self._transcript_count = 0
        self._transcript_max = 10
        voice_layout.addWidget(self.voice_transcript, 0)

        root.addWidget(self.voice_stage, 1)

        # ── Text mode is about the TEXT. Presence shrinks to a minimal
        # robot + state word pinned top-left; the transcript owns the page. ──
        self.text_stage = QFrame()
        self.text_stage.setObjectName("TextStage")
        self.text_stage.setStyleSheet("QFrame#TextStage { background: transparent; }")
        self.text_stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        text_layout = QVBoxLayout(self.text_stage)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        presence_row = QHBoxLayout()
        presence_row.setContentsMargins(2, 0, 0, 0)
        presence_row.setSpacing(7)

        self.robot = AliveRobotFace(size=30)
        presence_row.addWidget(self.robot, 0, Qt.AlignVCenter)

        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setFont(QFont("IBM Plex Sans", 8, QFont.Medium))
        self.status_label.setStyleSheet(
            "color: #8B9BB4; background: transparent; letter-spacing: 0.4px;"
        )
        presence_row.addWidget(self.status_label, 0, Qt.AlignVCenter)
        presence_row.addStretch(1)
        text_layout.addLayout(presence_row)

        root.addWidget(self.text_stage, 1)

        # ── Chat thread (text mode) ───────────────────────────────────────────
        self.chat = ChatThread()
        self.chat.setMinimumHeight(80)
        text_layout.addWidget(self.chat, 1)

        # Empty-state hero floats over the transcript region (§5.3); it is
        # geometry-synced to the chat and collapses on the first message.
        self.hero = TextHero(self.text_stage)
        self.hero.compose_requested.connect(self._hero_compose)
        self.hero.hide()
        root.addSpacing(6)

        # ── Dashboard: overlay sheet above the transcript (§5.10) ────────────
        self.dashboard = None
        self._dash_backdrop = QWidget(self.central_widget)
        self._dash_backdrop.setStyleSheet("background: rgba(0, 0, 0, 0.35);")
        self._dash_backdrop.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._dash_backdrop.mousePressEvent = lambda _e: self._close_dashboard()
        self._dash_backdrop.hide()
        try:
            self.dashboard = DashboardPanel(self.central_widget)
            self.dashboard.hide()
        except Exception:  # noqa: BLE001
            self.dashboard = None
            self._dash_backdrop.hide()

        # ── Composer (text mode only) ─────────────────────────────────────────
        # ChatGPT-style anatomy (research §composer): the textarea and the
        # send/stop button are ONE rounded container; the button anchors to
        # the bottom-right so it rides down as the field grows, and the whole
        # dock lights up with a focus ring. Heights derive from font metrics,
        # never magic pixels.
        self._dock_focused = False
        self.dock = QFrame()
        self.dock.setObjectName("Dock")
        self.dock.setProperty("focused", False)
        dock_row = QHBoxLayout(self.dock)
        dock_row.setContentsMargins(12, 7, 8, 7)
        dock_row.setSpacing(8)

        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText("Type a message…")
        self.text_input.setToolTip("Type a message and press Enter to send\nShift+Enter for a new line")
        self.text_input.setFont(QFont("IBM Plex Sans", 10))
        self.text_input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_input.setTabChangesFocus(True)
        self.text_input.document().setDocumentMargin(0)
        self.text_input.setStyleSheet("""
            QPlainTextEdit {
                background: transparent;
                color: #E4EAF2;
                border: none;
                padding: 0px 2px;
                selection-background-color: rgba(94, 177, 245, 0.35);
            }
            QScrollBar:vertical { background: transparent; width: 3px; }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.14); border-radius: 1px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.text_input.document().contentsChanged.connect(self._schedule_resize_input)
        self.text_input.textChanged.connect(self._sync_composer_enabled)
        self.text_input.installEventFilter(self)

        # Send ⇄ Stop lives in a bottom-pinned slot: centered on a single-line
        # composer, anchored bottom-right once the field grows multiline.
        btn_slot = QWidget()
        btn_slot.setAttribute(Qt.WA_TranslucentBackground)
        btn_slot_lay = QVBoxLayout(btn_slot)
        btn_slot_lay.setContentsMargins(0, 0, 0, 1)
        btn_slot_lay.addStretch(1)

        self.send_btn = self._circle_btn("send", tip="Send message", active=False, accent=False)
        self.send_btn.clicked.connect(self.send_text_message)
        btn_slot_lay.addWidget(self.send_btn)

        dock_row.addWidget(self.text_input, 1)
        dock_row.addWidget(btn_slot, 0)
        root.addWidget(self.dock)
        root.addSpacing(4)

        # ── Footer strip: context meter · 1-line log · resize hint (§5.9) ────
        self.footer_strip = QFrame()
        self.footer_strip.setObjectName("FooterStrip")
        self.footer_strip.setStyleSheet("QFrame#FooterStrip { background: transparent; }")
        footer_row = QHBoxLayout(self.footer_strip)
        footer_row.setContentsMargins(2, 0, 2, 0)
        footer_row.setSpacing(8)

        self.context_meter = ContextMeter()
        footer_row.addWidget(self.context_meter, 0, Qt.AlignVCenter)

        self.log_display = QLabel("Starting…")
        self.log_display.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.log_display.setFont(QFont("IBM Plex Mono", 7))
        self.log_display.setStyleSheet("color: #3F4D63; background: transparent;")
        self.log_display.setWordWrap(False)
        self.log_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.log_display.setMaximumHeight(16)
        footer_row.addWidget(self.log_display, 1)

        self.resize_hint = QLabel("⋰")
        self.resize_hint.setToolTip("Drag edges or corner to resize")
        self.resize_hint.setStyleSheet("color: #3A4658; background: transparent; font-size: 11px;")
        self.resize_hint.setFixedSize(16, 14)
        footer_row.addWidget(self.resize_hint, 0, Qt.AlignVCenter)

        root.addWidget(self.footer_strip)

        self.setCentralWidget(self.central_widget)
        self.apply_size_preset("medium", anchor_top_right=True)
        self.position_hud()

    def showEvent(self, _event) -> None:
        super().showEvent(_event)
        self._apply_mode_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive()
        if getattr(self, "dashboard", None) is not None and self.dashboard.isVisible():
            self.dashboard.setGeometry(self._dash_rect())
            self._dash_backdrop.setGeometry(self.central_widget.rect())

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.text_input:
            if event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    if event.modifiers() & Qt.ShiftModifier:
                        return False
                    self.send_text_message()
                    return True
            elif event.type() in (QEvent.FocusIn, QEvent.FocusOut):
                # Focus ring on the whole composer container (research rule).
                focused = event.type() == QEvent.FocusIn
                if focused != self._dock_focused:
                    self._dock_focused = focused
                    self._style_dock()
        return super().eventFilter(obj, event)

    def _apply_mode_layout(self) -> None:
        is_text = self.interaction_mode == "text"
        self.dock.setVisible(is_text)
        self.wake_toggle.setVisible(not is_text)

        self.mode_toggle.blockSignals(True)
        self.mode_toggle.setChecked(is_text)
        self.mode_toggle.blockSignals(False)

        self.wake_toggle.blockSignals(True)
        self.wake_toggle.setChecked(getattr(settings, "listening_mode", "wake_word") == "always_on")
        self.wake_toggle.blockSignals(False)

        root = self._root
        if is_text:
            self._controls_row.removeWidget(self.wake_toggle)
            self.wake_toggle.setParent(self.central_widget)
            dock_idx = root.indexOf(self.dock)
            if dock_idx >= 0:
                root.insertWidget(dock_idx, self.wake_toggle, 0, Qt.AlignHCenter)
            else:
                root.addWidget(self.wake_toggle, 0, Qt.AlignHCenter)
            self._controls_row.removeWidget(self.mode_toggle)
            self.mode_toggle.setParent(self.central_widget)
            root.addWidget(self.mode_toggle, 0, Qt.AlignHCenter)
            self.voice_stage.setVisible(False)
            self.text_stage.setVisible(True)
            self.chat.setVisible(True)
            self.voice_transcript.setVisible(False)
            self._sync_hero()
            self._sync_hero_geometry()
            self.context_label.setText("Type a message")
            self.text_input.setFocus()
            self._start_placeholder_cycle()
        else:
            root.removeWidget(self.wake_toggle)
            self.wake_toggle.setParent(self.voice_stage)
            self._controls_row.insertWidget(1, self.wake_toggle, 0, Qt.AlignVCenter)
            root.removeWidget(self.mode_toggle)
            self.mode_toggle.setParent(self.voice_stage)
            self._controls_row.insertWidget(2, self.mode_toggle, 0, Qt.AlignVCenter)
            self.voice_stage.setVisible(True)
            self.voice_orb.setVisible(True)
            self.text_stage.setVisible(False)
            self.chat.setVisible(False)
            self.voice_transcript.setVisible(True)
            self._stop_placeholder_cycle()
            self.hero.collapse()
            m = getattr(self, "_metrics", None)
            face_size = m["face"] if m else 110
            self.voice_orb.face.set_face_size(face_size)
            if self.current_status in ("standby", "listening"):
                if self.current_status == "standby" and getattr(settings, "listening_mode", "wake_word") == "wake_word":
                    wake_words_str = ", ".join(getattr(settings, "wake_words", ["dream"]))
                    self.context_label.setText(f"Say '{wake_words_str}'…")
                else:
                    self.context_label.setText(self._listen_hint)

    def _on_mode_toggle(self, checked: bool) -> None:
        mode = "text" if checked else "voice"
        self.set_interaction_mode(mode)

    # ── Empty-state hero ──────────────────────────────────────────────────
    def _hero_compose(self, text: str) -> None:
        """Chip click fills the composer — never auto-sends (§5.3)."""
        self.text_input.setPlainText(text)
        cursor = self.text_input.textCursor()
        cursor.movePosition(cursor.End)
        self.text_input.setTextCursor(cursor)
        self.text_input.setFocus()

    def _sync_hero_geometry(self) -> None:
        """Keep the hero exactly over the transcript region."""
        if not hasattr(self, "hero"):
            return
        g = self.chat.geometry()
        self.hero.setGeometry(g.adjusted(0, 0, 0, 0))
        self.hero.raise_()

    # ── Bilingual placeholder cycle (§5.8) ───────────────────────────────
    _PLACEHOLDERS = ("Type a message…", "লিখুন…")

    def _start_placeholder_cycle(self) -> None:
        if getattr(self, "_ph_timer", None) is not None or not motion_enabled():
            return
        self._ph_idx = 0
        self.text_input.setPlaceholderText(self._PLACEHOLDERS[0])
        timer = QTimer(self)
        timer.setInterval(6000)
        timer.timeout.connect(self._cycle_placeholder)
        timer.start()
        self._ph_timer = timer

    def _stop_placeholder_cycle(self) -> None:
        timer = getattr(self, "_ph_timer", None)
        if timer is not None:
            timer.stop()
            self._ph_timer = None

    def _cycle_placeholder(self) -> None:
        if self.text_input.toPlainText():
            return  # user is typing — leave them alone
        self._ph_idx = (self._ph_idx + 1) % len(self._PLACEHOLDERS)
        self.text_input.setPlaceholderText(self._PLACEHOLDERS[self._ph_idx])

    def set_interaction_mode(self, mode: str) -> None:
        mode = mode.lower().strip()
        if mode not in ("voice", "text"):
            return
        self.interaction_mode = mode
        self._apply_mode_layout()
        if hasattr(self, "worker") and self.worker:
            self.worker.set_mode(mode)

    def set_listening_mode(self, mode: str) -> None:
        mode = mode.lower().strip()
        if mode not in ("wake_word", "always_on"):
            return
        settings.listening_mode = mode
        if hasattr(self, "worker") and self.worker:
            self.worker.set_listening_mode(mode)
            self.worker.log_message.emit(f"Listening mode → {mode}")
        self.wake_toggle.blockSignals(True)
        self.wake_toggle.setChecked(mode == "always_on")
        self.wake_toggle.blockSignals(False)
        if self.interaction_mode == "voice" and self.current_status in ("standby", "listening"):
            if mode == "wake_word":
                wake_words_str = ", ".join(getattr(settings, "wake_words", ["dream"]))
                self.context_label.setText(f"Say '{wake_words_str}'…")
            else:
                self.context_label.setText(self._listen_hint)

    def _on_wake_toggle(self, checked: bool) -> None:
        mode = "always_on" if checked else "wake_word"
        self.set_listening_mode(mode)

    def _add_transcript_line(self, role: str, text: str) -> None:
        """Add a compact line to the voice mode transcript."""
        text = (text or "").strip()
        if not text:
            return
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMaximumHeight(32)
        label.setFont(QFont("IBM Plex Sans", 7))
        if role == "user":
            label.setStyleSheet("color: #6EA8D8; background: transparent;")
            label.setText(f"▸ {text}")
        else:
            label.setStyleSheet("color: #9AAABF; background: transparent;")
            label.setText(f"● {text}")

        self._transcript_col.insertWidget(self._transcript_col.count() - 1, label)
        self._transcript_count += 1

        while self._transcript_count > self._transcript_max and self._transcript_col.count() > 1:
            item = self._transcript_col.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
                self._transcript_count -= 1

        from PyQt5.QtCore import QTimer as _QTimer
        _QTimer.singleShot(10, self._scroll_transcript_to_bottom)

    def _scroll_transcript_to_bottom(self) -> None:
        bar = self.voice_transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _escape_pressed(self) -> None:
        """Esc priority: close dashboard → stop generating → hide HUD."""
        if self.dashboard is not None and self.dashboard.isVisible():
            self._close_dashboard()
            return
        if getattr(self, "_generating", False):
            self.stop_generation()
            return
        self.hide_hud()

    # ── Dashboard overlay sheet (§5.10) ──────────────────────────────────
    def _dash_rect(self, *, offscreen: bool = False) -> QRect:
        """Target geometry: transcript region expanded, right-aligned sheet."""
        m = getattr(self, "_metrics", None) or self._metrics_for_width(self.width())
        w = self.central_widget.width()
        h = self.central_widget.height()
        pad = max(0, m["margin"] - 2)
        top = pad + m["chrome"] + 4          # header bottom
        avail = max(80, w - pad * 2)
        if self.width() < 320:
            dw = avail
        elif self.width() < 440:
            dw = min(320, avail)
        else:
            dw = min(360, avail)
        x = w - pad - dw
        if offscreen:
            x = w                             # parked just past the right edge
        return QRect(x, top, dw, max(60, h - top - pad))

    def _toggle_dashboard(self) -> None:
        if self.dashboard is None:
            return
        if self.dashboard.isVisible():
            self._close_dashboard()
        else:
            self._open_dashboard()

    def _open_dashboard(self) -> None:
        if self.dashboard is None or self.dashboard.isVisible():
            return
        if hasattr(self.dashboard, "refresh"):
            self.dashboard.refresh()
        target = self._dash_rect()
        start = self._dash_rect(offscreen=True)
        self._dash_backdrop.setGeometry(self.central_widget.rect())
        self._dash_backdrop.show()
        self._dash_backdrop.raise_()
        self.dashboard.setGeometry(start)
        self.dashboard.show()
        self.dashboard.raise_()
        if not motion_enabled():
            self.dashboard.setGeometry(target)
            return
        from PyQt5.QtCore import QEasingCurve, QPropertyAnimation

        slide = QPropertyAnimation(self.dashboard, b"geometry", self.dashboard)
        slide.setDuration(260)
        slide.setStartValue(start)
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        slide.start(QPropertyAnimation.DeleteWhenStopped)
        self._dash_anim = slide

        effect = QGraphicsOpacityEffect(self._dash_backdrop)
        self._dash_backdrop.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self._dash_backdrop)
        fade.setDuration(260)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.start(QPropertyAnimation.DeleteWhenStopped)

    def _close_dashboard(self) -> None:
        if self.dashboard is None or not self.dashboard.isVisible():
            return
        if not motion_enabled():
            self.dashboard.hide()
            self._dash_backdrop.hide()
            return
        from PyQt5.QtCore import QEasingCurve, QPropertyAnimation

        exit_rect = self._dash_rect(offscreen=True)
        slide = QPropertyAnimation(self.dashboard, b"geometry", self.dashboard)
        slide.setDuration(260)
        slide.setStartValue(self.dashboard.geometry())
        slide.setEndValue(exit_rect)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        slide.finished.connect(lambda: (self.dashboard.hide(), self._dash_backdrop.hide()))
        slide.start(QPropertyAnimation.DeleteWhenStopped)
        self._dash_anim = slide

    def position_hud(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + screen.width() - self.width() - 36, screen.y() + 56)

    def _toggle_maximize(self) -> None:
        if self._is_maximized:
            if self._prev_geo:
                self.setGeometry(self._prev_geo)
                self._prev_geo = None
            self._is_maximized = False
        else:
            self._prev_geo = self.geometry()
            screen = QApplication.primaryScreen().availableGeometry()
            self.setGeometry(screen)
            self._is_maximized = True
        self._refresh_win_btns()

    def _refresh_win_btns(self) -> None:
        btn = self._win_btns.get("maximize")
        if btn:
            kind = "restore" if self._is_maximized else "maximize"
            ic = getattr(self, "_metrics", {}).get("icon", 14)
            btn.setIcon(_paint_icon(kind, ic, active=False))

    def _auto_resize_input(self) -> None:
        """Auto-grow bound by max height — derived from font metrics.

        QTextDocument.size() is unreliable for plain-text documents (it can
        report block counts instead of pixels), so the wrapped line count is
        measured directly with QFontMetrics. setFixedHeight triggers layout,
        which can re-enter here via resizeEvent → _apply_responsive; the
        guard turns that cycle into a no-op instead of a stack overflow.
        """
        if getattr(self, "_resizing_input", False):
            return
        self._resizing_input = True
        try:
            inp = self.text_input
            fm = QFontMetrics(inp.font())
            min_h = fm.height() + 14                  # one comfortable line
            # Measure slightly narrow so a scrollbar appearing/disappearing
            # cannot flip the wrap count back and forth.
            width = max(40, inp.viewport().width() - 3)
            h = self._input_content_height(width) + 12
            inp.setFixedHeight(int(max(min_h, min(h, 120))))
        finally:
            self._resizing_input = False

    def _input_content_height(self, width: int) -> int:
        """Pixel height of the editor's text incl. soft-wrapped lines."""
        inp = self.text_input
        doc = inp.document()
        fm = QFontMetrics(inp.font())
        lines = 0
        for i in range(doc.blockCount()):
            text = doc.findBlockByNumber(i).text()
            if not text:
                lines += 1
                continue
            br = fm.boundingRect(QRect(0, 0, width, 10000), Qt.TextWordWrap, text)
            lines += max(1, -(-br.height() // fm.height()))
        return int(lines * fm.height() + doc.documentMargin() * 2)

    def _schedule_resize_input(self) -> None:
        from PyQt5.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, self._auto_resize_input)

    def _style_dock(self) -> None:
        """Composer container style: glass at rest, focus ring when active."""
        m = getattr(self, "_metrics", None) or {}
        radius = max(14, m.get("mode_r", 12) + 2)
        if self._dock_focused:
            border = "rgba(94, 177, 245, 0.38)"
            bg = "rgba(255, 255, 255, 0.055)"
        else:
            border = "rgba(255, 255, 255, 0.07)"
            bg = "rgba(255, 255, 255, 0.04)"
        self.dock.setStyleSheet(f"""
            QFrame#Dock {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {radius}px;
            }}
        """)

    def close_app(self) -> None:
        if hasattr(self, "worker") and self.worker:
            self.worker.stop()
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.hide()
        self.close()
        QApplication.instance().quit()
