"""
sopno/ui/hud/window.py
━━━━━━━━━━━━━━━━━━━━━━
The floating HUD main window — builds the layout and wires it to the assistant.
"""

from __future__ import annotations

import threading

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
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
from sopno.ui.hud.visuals.theme import MIN_SIZE
from sopno.ui.hud.widgets import AliveRobotFace, ChatThread, ModeToggle, VoiceModeOrb
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
        QShortcut(QKeySequence("Escape"), self, self.hide_hud)
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

        # ── Header (always visible) ───────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self._header = header

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

        self.listening_chip = QPushButton()
        self.listening_chip.setCursor(Qt.PointingHandCursor)
        self.listening_chip.setFocusPolicy(Qt.NoFocus)
        self.listening_chip.setFixedHeight(18)
        self.listening_chip.setToolTip("Click to toggle wake word / always-on")
        self.listening_chip.clicked.connect(self._toggle_listening_mode)
        self._style_listening_chip()
        voice_layout.addWidget(self.listening_chip, 0, Qt.AlignCenter)

        self.listening_chip = QPushButton()
        self.listening_chip.setCursor(Qt.PointingHandCursor)
        self.listening_chip.setFocusPolicy(Qt.NoFocus)
        self.listening_chip.setFixedHeight(18)
        self.listening_chip.setToolTip("Click to toggle wake word / always-on")
        self.listening_chip.clicked.connect(self._toggle_listening_mode)
        self._style_listening_chip()
        voice_layout.addWidget(self.listening_chip, 0, Qt.AlignCenter)

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

        # ── Text mode: robot face + chat thread ───────────────────────────────
        self.text_stage = QFrame()
        self.text_stage.setObjectName("TextStage")
        self.text_stage.setStyleSheet("QFrame#TextStage { background: transparent; }")
        self.text_stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        text_layout = QVBoxLayout(self.text_stage)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        text_layout.setAlignment(Qt.AlignCenter)

        self.robot = AliveRobotFace(size=100)
        text_layout.addWidget(self.robot, 0, Qt.AlignCenter)

        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("IBM Plex Sans", 9, QFont.Medium))
        self.status_label.setStyleSheet(
            "color: #8B9BB4; background: transparent; letter-spacing: 0.5px;"
        )
        text_layout.addWidget(self.status_label, 0, Qt.AlignCenter)

        root.addWidget(self.text_stage, 1)

        # ── Chat thread (text mode) ───────────────────────────────────────────
        self.chat = ChatThread()
        self.chat.setMinimumHeight(80)
        root.addWidget(self.chat, 1)
        root.addSpacing(6)

        # ── Dashboard ─────────────────────────────────────────────────────────
        self.dashboard = None
        try:
            self.dashboard = DashboardPanel()
            root.addWidget(self.dashboard, 0)
            self.dashboard.setVisible(False)
        except Exception:  # noqa: BLE001
            self.dashboard = None

        # ── Mode toggle (always visible) ──────────────────────────────────────
        self.mode_toggle = ModeToggle()
        self.mode_toggle.mode_changed.connect(self.set_interaction_mode)
        root.addWidget(self.mode_toggle, 0, Qt.AlignHCenter)
        root.addSpacing(6)

        # ── Composer (text mode only) ─────────────────────────────────────────
        self.dock = QFrame()
        self.dock.setObjectName("Dock")
        self.dock.setStyleSheet("""
            QFrame#Dock {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 18px;
            }
        """)
        dock_row = QHBoxLayout(self.dock)
        dock_row.setContentsMargins(10, 6, 6, 6)
        dock_row.setSpacing(6)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a message…")
        self.text_input.setToolTip("Type a message and press Enter to send")
        self.text_input.setFont(QFont("IBM Plex Sans", 10))
        self.text_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #E4EAF2;
                border: none;
                padding: 6px 4px;
                selection-background-color: rgba(94, 177, 245, 0.35);
            }
        """)
        self.text_input.returnPressed.connect(self.send_text_message)

        self.send_btn = self._circle_btn("send", tip="Send message", active=False, accent=False)
        self.send_btn.clicked.connect(self.send_text_message)

        dock_row.addWidget(self.text_input, 1)
        dock_row.addWidget(self.send_btn, 0, Qt.AlignVCenter)
        root.addWidget(self.dock)
        root.addSpacing(4)

        self.log_display = QLabel("Starting…")
        self.log_display.setAlignment(Qt.AlignCenter)
        self.log_display.setFont(QFont("IBM Plex Mono", 7))
        self.log_display.setStyleSheet("color: #3F4D63; background: transparent;")
        self.log_display.setWordWrap(True)
        root.addWidget(self.log_display)

        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        self.resize_hint = QLabel("⋰")
        self.resize_hint.setToolTip("Drag edges or corner to resize")
        self.resize_hint.setStyleSheet("color: #3A4658; background: transparent; font-size: 11px;")
        self.resize_hint.setFixedSize(16, 14)
        grip_row.addWidget(self.resize_hint)
        root.addLayout(grip_row)

        self.setCentralWidget(self.central_widget)
        self.apply_size_preset("medium", anchor_top_right=True)
        self._style_listening_chip()
        self.position_hud()

    def showEvent(self, _event) -> None:
        super().showEvent(_event)
        self._apply_mode_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive()

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)

    def _apply_mode_layout(self) -> None:
        is_text = self.interaction_mode == "text"
        self.dock.setVisible(is_text)
        self.listening_chip.setVisible(not is_text)
        self.mode_toggle.set_mode(self.interaction_mode, emit=False)

        if is_text:
            self.voice_stage.setVisible(False)
            self.text_stage.setVisible(True)
            self.chat.setVisible(True)
            self.voice_transcript.setVisible(False)
            self.context_label.setText("Type a message")
            self.text_input.setFocus()
        else:
            self.voice_stage.setVisible(True)
            self.voice_orb.setVisible(True)
            self.text_stage.setVisible(False)
            self.chat.setVisible(False)
            self.voice_transcript.setVisible(True)
            m = getattr(self, "_metrics", None)
            face_size = m["face"] if m else 110
            self.voice_orb.face.set_face_size(face_size)
            if self.current_status in ("standby", "listening"):
                if self.current_status == "standby" and getattr(settings, "listening_mode", "wake_word") == "wake_word":
                    wake_words_str = ", ".join(getattr(settings, "wake_words", ["dream"]))
                    self.context_label.setText(f"Say '{wake_words_str}'…")
                else:
                    self.context_label.setText(self._listen_hint)

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
        self._style_listening_chip()
        if self.interaction_mode == "voice" and self.current_status in ("standby", "listening"):
            if mode == "wake_word":
                wake_words_str = ", ".join(getattr(settings, "wake_words", ["dream"]))
                self.context_label.setText(f"Say '{wake_words_str}'…")
            else:
                self.context_label.setText(self._listen_hint)

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

        bar = self.voice_transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _toggle_dashboard(self) -> None:
        if self.dashboard is None:
            return
        visible = not self.dashboard.isVisible()
        self.dashboard.setVisible(visible)
        if visible and hasattr(self.dashboard, "refresh"):
            self.dashboard.refresh()

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

    def close_app(self) -> None:
        if hasattr(self, "worker") and self.worker:
            self.worker.stop()
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.hide()
        self.close()
        QApplication.instance().quit()
