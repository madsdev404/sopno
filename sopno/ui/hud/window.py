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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sopno.config.settings import settings
from sopno.ui.hud.behaviors import ChromeMixin, ResponsiveMixin, ResizeMixin, StatusMixin, TrayMixin
from sopno.ui.hud.dashboard import DashboardPanel
from sopno.ui.hud.visuals.icons import _paint_icon
from sopno.ui.hud.visuals.theme import MIN_SIZE
from sopno.ui.hud.widgets import AliveRobotFace, ChatThread, ModeToggle
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
        """Keyboard shortcuts for common actions."""
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

        # ── Header (compact chrome) ───────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self._header = header

        self.context_label = QLabel(self._listen_hint)
        self.context_label.setFont(QFont("IBM Plex Sans", 8))
        self.context_label.setStyleSheet("color: #6B7C94; background: transparent;")
        self.context_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.context_label.setMaximumHeight(20)

        # ── Window controls (VS Code style) ───────────────────────────────────
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

        # ── Robot stage ───────────────────────────────────────────────────────
        stage = QVBoxLayout()
        stage.setSpacing(2)
        stage.setAlignment(Qt.AlignCenter)
        self._stage = stage

        self.robot = AliveRobotFace(size=100)

        # Status row: label + listening mode chip
        status_row = QHBoxLayout()
        status_row.setAlignment(Qt.AlignCenter)
        status_row.setSpacing(6)
        self._status_row = status_row

        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("IBM Plex Sans", 9, QFont.Medium))
        self.status_label.setStyleSheet(
            "color: #8B9BB4; background: transparent; letter-spacing: 0.5px;"
        )

        self.listening_chip = QPushButton()
        self.listening_chip.setCursor(Qt.PointingHandCursor)
        self.listening_chip.setFocusPolicy(Qt.NoFocus)
        self.listening_chip.setFixedHeight(18)
        self.listening_chip.setToolTip("Click to toggle wake word / always-on")
        self.listening_chip.clicked.connect(self._toggle_listening_mode)
        self._style_listening_chip()

        status_row.addWidget(self.status_label)
        status_row.addWidget(self.listening_chip)

        stage.addWidget(self.robot, 0, Qt.AlignCenter)
        stage.addLayout(status_row)
        root.addLayout(stage)
        root.addSpacing(8)

        # ── Clean conversation thread ─────────────────────────────────────────
        self.chat = ChatThread()
        self.chat.setMinimumHeight(80)
        root.addWidget(self.chat, 1)
        root.addSpacing(10)

        # ── Dashboard (toggled via Ctrl+D or tray) ───────────────────────────
        self.dashboard = None
        try:
            self.dashboard = DashboardPanel()
            root.addWidget(self.dashboard, 0)
            self.dashboard.setVisible(False)
        except Exception:  # noqa: BLE001
            self.dashboard = None

        # ── Mode toggle (Voice | Text) ─────────────────────────────────────────
        self.mode_toggle = ModeToggle()
        self.mode_toggle.mode_changed.connect(self.set_interaction_mode)
        root.addWidget(self.mode_toggle, 0, Qt.AlignHCenter)
        root.addSpacing(8)

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
        root.addSpacing(6)

        self.log_display = QLabel("Starting…")
        self.log_display.setAlignment(Qt.AlignCenter)
        self.log_display.setFont(QFont("IBM Plex Mono", 7))
        self.log_display.setStyleSheet("color: #3F4D63; background: transparent;")
        self.log_display.setWordWrap(True)
        root.addWidget(self.log_display)

        # Resize grip hint (bottom-right)
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
        self._apply_mode_layout()
        self.position_hud()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive()

    def keyPressEvent(self, event) -> None:
        """Route Enter/Return from text_input (already handled by returnPressed)."""
        super().keyPressEvent(event)

    def _apply_mode_layout(self) -> None:
        """Show/hide elements based on voice vs text mode."""
        is_text = self.interaction_mode == "text"
        self.dock.setVisible(is_text)
        self.listening_chip.setVisible(not is_text)
        self.mode_toggle.set_mode(self.interaction_mode, emit=False)

        if is_text:
            self.robot.set_face_size(56)
            self.context_label.setText("Type a message")
            self.text_input.setFocus()
        else:
            m = getattr(self, "_metrics", None)
            face_size = m["face"] if m else 100
            self.robot.set_face_size(face_size)
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

    def _toggle_dashboard(self) -> None:
        """Toggle dashboard panel visibility."""
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
