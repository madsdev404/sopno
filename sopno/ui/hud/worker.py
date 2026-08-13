"""
sopno/ui/hud/worker.py
━━━━━━━━━━━━━━━━━━━━━
QObject bridge between the SopnoAssistant pipeline and Qt signal/slots.
"""

from PyQt5.QtCore import QObject, pyqtSignal

from sopno.core.assistant import SopnoAssistant


class AssistantWorker(QObject):
    status_changed  = pyqtSignal(str)
    speech_detected = pyqtSignal(str)
    reply_generated = pyqtSignal(str)
    log_message     = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.assistant = SopnoAssistant(
            status_callback=lambda status: self.status_changed.emit(status),
            speech_callback=lambda text: self.speech_detected.emit(text),
            reply_callback=lambda reply: self.reply_generated.emit(reply),
            log_callback=lambda msg: self.log_message.emit(msg),
        )

    @property
    def running(self) -> bool:
        return self.assistant.running

    @running.setter
    def running(self, value: bool) -> None:
        self.assistant.running = value

    def start_loop(self) -> None:
        self.assistant.run()

    def stop(self) -> None:
        self.assistant.stop()

    def set_mode(self, mode: str) -> None:
        self.assistant.set_interaction_mode(mode)

    def set_listening_mode(self, mode: str) -> None:
        self.assistant.set_listening_mode(mode)

    def submit_text(self, text: str) -> None:
        self.assistant.submit_text(text)
