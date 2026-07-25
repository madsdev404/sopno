"""
sopno/ui/hud.py
━━━━━━━━━━━━━━━
Premium Modern Glassmorphic PyQt5 HUD overlay.

Migrated from gui.py. Runs the SopnoAssistant pipeline inside a background
thread and communicates state changes to the translucent, always-on-top
glassmorphism GUI via Qt signals.
"""

import sys
import threading
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QTextEdit, QPushButton, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QPoint, QSize
from PyQt5.QtGui import QFont, QColor

from sopno.config.settings import settings
from sopno.core.assistant import SopnoAssistant


class AssistantWorker(QObject):
    """
    Background worker thread manager.
    Bridges SopnoAssistant callbacks to PyQt thread-safe signals.
    """
    status_changed  = pyqtSignal(str)  # standby, listening, thinking, speaking, error
    speech_detected = pyqtSignal(str)  # What the user said (transcription)
    reply_generated = pyqtSignal(str)  # What Sopno responded
    log_message     = pyqtSignal(str)  # System logs

    def __init__(self) -> None:
        super().__init__()
        # Delegate main assistant logic to SopnoAssistant and bridge callbacks
        self.assistant = SopnoAssistant(
            status_callback=lambda status: self.status_changed.emit(status),
            speech_callback=lambda text: self.speech_detected.emit(text),
            reply_callback=lambda reply: self.reply_generated.emit(reply),
            log_callback=lambda msg: self.log_message.emit(msg)
        )

    @property
    def running(self) -> bool:
        return self.assistant.running

    @running.setter
    def running(self, value: bool) -> None:
        self.assistant.running = value

    def start_loop(self) -> None:
        """Runs the main pipeline blocking loop."""
        self.assistant.run()

    def stop(self) -> None:
        """Stops the assistant loop."""
        self.assistant.stop()


class SopnoHUDWindow(QMainWindow):
    """The visual, premium, translucent glassmorphic HUD overlay window."""

    def __init__(self) -> None:
        super().__init__()
        self.old_pos = None

        # Load glassmorphic HUD UI
        self.init_ui()

        # Start the background pipeline thread
        self.worker = AssistantWorker()
        self.thread = threading.Thread(target=self.worker.start_loop)
        self.thread.daemon = True

        # Connect worker Qt signals to UI slots
        self.worker.status_changed.connect(self.update_status)
        self.worker.speech_detected.connect(self.update_user_speech)
        self.worker.reply_generated.connect(self.update_sopno_reply)
        self.worker.log_message.connect(self.update_log)

        self.thread.start()

    def init_ui(self) -> None:
        """Initialize the layout, typography, and premium styling."""
        # Configure frameless, translucent, always-on-top window properties
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Main glass container widget
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        
        # Glassmorphic semi-translucent dark slate background with thin border
        self.central_widget.setStyleSheet(f"""
            QWidget#CentralWidget {{
                background-color: rgba(15, 23, 42, {settings.hud_opacity});
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 20px;
            }}
        """)

        # Premium Neon Cyan drop-shadow/glow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 229, 255, 100))
        shadow.setOffset(0, 0)
        self.central_widget.setGraphicsEffect(shadow)

        # Layout container
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Header Bar ──────────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("🌙 SOPNO AI")
        title.setFont(QFont("Outfit", 12, QFont.Bold))
        title.setStyleSheet("color: #FFFFFF; letter-spacing: 2px;")

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8892B0;
                border: none;
                font-size: 14px;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 76, 76, 0.2);
                color: #FF4C4C;
            }
        """)
        self.close_btn.clicked.connect(self.close_app)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        # ── Status Light and Indicator ──────────────────────────────────────────
        status_layout = QHBoxLayout()
        self.status_glow = QLabel()
        self.status_glow.setFixedSize(14, 14)
        self.status_glow.setStyleSheet("background-color: #888888; border-radius: 7px;")

        self.status_label = QLabel("💤 STANDBY")
        self.status_label.setFont(QFont("Inter", 10, QFont.Bold))
        self.status_label.setStyleSheet("color: #8892B0;")

        status_layout.addWidget(self.status_glow)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # ── Speech Input Box ───────────────────────────────────────────────────
        self.speech_display = QLabel("Waiting for voice...")
        self.speech_display.setFont(QFont("Inter", 10))
        self.speech_display.setWordWrap(True)
        self.speech_display.setStyleSheet(
            "color: rgba(255, 255, 255, 0.7); "
            "background-color: rgba(255, 255, 255, 0.05); "
            "padding: 12px; "
            "border-radius: 12px; "
            "border: 1px solid rgba(255, 255, 255, 0.05);"
        )
        self.speech_display.setMinimumHeight(55)
        layout.addWidget(self.speech_display)

        # ── Assistant Speech Output Box ─────────────────────────────────────────
        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setFont(QFont("Inter", 10))
        self.reply_display.setPlaceholderText("Responses will appear here...")
        self.reply_display.setStyleSheet("""
            QTextEdit {
                color: #00FFCC; 
                background-color: rgba(0, 0, 0, 0.2); 
                border: 1px solid rgba(0, 255, 204, 0.1); 
                padding: 10px; 
                border-radius: 12px;
            }
        """)
        self.reply_display.setMinimumHeight(90)
        self.reply_display.setMaximumHeight(150)
        layout.addWidget(self.reply_display)

        # ── Dynamic System Log Bar ──────────────────────────────────────────────
        self.log_display = QLabel("Sopno System active.")
        self.log_display.setFont(QFont("Inter", 8))
        self.log_display.setStyleSheet("color: #4B5563; padding-top: 5px;")
        layout.addWidget(self.log_display)

        self.setCentralWidget(self.central_widget)
        self.resize(380, 420)

        # Place HUD on the screen
        self.position_hud()

    def position_hud(self) -> None:
        """Position the HUD in the configured screen quadrant."""
        screen = QApplication.primaryScreen().geometry()
        # Default top-right quadrant spacing
        x = screen.width() - self.width() - 40
        y = 60
        self.move(x, y)

    # ── Frameless Window Drag Handlers ──────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event) -> None:
        if self.old_pos is not None:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event) -> None:
        self.old_pos = None

    # ── Signal Slots / Updates ──────────────────────────────────────────────────
    def update_status(self, status: str) -> None:
        """Update HUD colors, labels, and shadow glows on state changes."""
        shadow = self.central_widget.graphicsEffect()
        status_clean = status.lower().strip()

        if status_clean == "standby":
            self.status_glow.setStyleSheet("background-color: #888888; border-radius: 7px;")
            self.status_label.setText("💤 STANDBY")
            self.status_label.setStyleSheet("color: #8892B0;")
            if shadow:
                shadow.setColor(QColor(136, 136, 136, 60))
        elif status_clean == "listening":
            self.status_glow.setStyleSheet("background-color: #00E5FF; border-radius: 7px; border: 1px solid #FFFFFF;")
            self.status_label.setText("🎤 LISTENING…")
            self.status_label.setStyleSheet("color: #00E5FF;")
            if shadow:
                shadow.setColor(QColor(0, 229, 255, 180))
        elif status_clean == "thinking":
            self.status_glow.setStyleSheet("background-color: #FF007F; border-radius: 7px; border: 1px solid #FFFFFF;")
            self.status_label.setText("🧠 THINKING…")
            self.status_label.setStyleSheet("color: #FF007F;")
            if shadow:
                shadow.setColor(QColor(255, 0, 127, 180))
        elif status_clean == "speaking":
            self.status_glow.setStyleSheet("background-color: #00FF66; border-radius: 7px; border: 1px solid #FFFFFF;")
            self.status_label.setText("🔊 SPEAKING…")
            self.status_label.setStyleSheet("color: #00FF66;")
            if shadow:
                shadow.setColor(QColor(0, 255, 102, 180))
        elif status_clean == "error":
            self.status_glow.setStyleSheet("background-color: #FF3333; border-radius: 7px;")
            self.status_label.setText("⚠️ SYSTEM ERROR")
            self.status_label.setStyleSheet("color: #FF3333;")
            if shadow:
                shadow.setColor(QColor(255, 51, 51, 150))

    def update_user_speech(self, text: str) -> None:
        self.speech_display.setText(f'“ {text} ”')

    def update_sopno_reply(self, text: str) -> None:
        self.reply_display.setText(text)

    def update_log(self, log: str) -> None:
        self.log_display.setText(log)
        print(f"[HUD Log] {log}")

    def close_app(self) -> None:
        """Safely terminates the background thread and closes the window."""
        self.worker.stop()
        self.close()
        sys.exit(0)


def run_hud() -> None:
    """Initialize and boot the Sopno PyQt5 HUD Window."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = SopnoHUDWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_hud()
