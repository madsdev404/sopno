"""
sopno/voice/listener.py
━━━━━━━━━━━━━━━━━━━━━━━
Microphone capture and ambient-noise calibration.

Responsible for:
  - Opening the microphone
  - Calibrating for background noise once at startup
  - Continuously capturing audio frames for the STT engine

Usage:
    from sopno.voice.listener import Listener
    listener = Listener()
    listener.calibrate()
    audio = listener.listen()          # blocks until a phrase is captured
"""

import sys
import speech_recognition as sr
from sopno.config.settings import settings


class Listener:
    """Wraps SpeechRecognizer with calibration and capture helpers."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold  = settings.dynamic_energy_threshold
        self.recognizer.pause_threshold           = settings.pause_threshold

    def calibrate(self, duration: float = 1.5) -> None:
        """
        Adjust the recognizer's energy threshold for ambient noise.
        Should be called once at startup, before the main listen loop.
        """
        try:
            with sr.Microphone() as source:
                print("[Listener] Calibrating microphone for background noise…")
                self.recognizer.adjust_for_ambient_noise(source, duration=duration)
                print("[Listener] Microphone ready.\n")
        except Exception as e:
            print(f"[Listener] ERROR: Could not access microphone — {e}")
            print("  Check your microphone connection and PyAudio installation.")
            sys.exit(1)

    def listen(self, phrase_time_limit: int = 10) -> sr.AudioData:
        """
        Open the microphone and capture one spoken phrase.
        Blocks until the user starts and finishes speaking.

        Returns:
            sr.AudioData ready to be passed to sopno/voice/stt.py
        """
        with sr.Microphone() as source:
            audio = self.recognizer.listen(
                source,
                timeout=None,
                phrase_time_limit=phrase_time_limit,
            )
        return audio
