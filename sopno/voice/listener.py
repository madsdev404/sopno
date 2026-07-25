"""
sopno/voice/listener.py
━━━━━━━━━━━━━━━━━━━━━━━
Microphone capture and ambient-noise calibration.

Responsible for:
  - Opening the microphone
  - Calibrating for background noise once at startup
  - Capturing one conversational turn (Silero VAD → classic fallback)

Usage:
    from sopno.voice.listener import Listener
    listener = Listener(log_callback=print)
    listener.calibrate()
    audio = listener.listen_for_turn()   # waits until user speaks, then ends on silence
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

import speech_recognition as sr

from sopno.config.settings import settings
from sopno.voice.vad import TurnTaker


class Listener:
    """Wraps SpeechRecognizer with calibration and VAD turn capture."""

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log = log_callback or (lambda m: print(f"[Listener] {m}"))
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = settings.dynamic_energy_threshold
        self.recognizer.pause_threshold = settings.pause_threshold
        self.turn_taker = TurnTaker(log_callback=self.log)

    def calibrate(self, duration: float = 1.5) -> None:
        """
        Adjust the recognizer's energy threshold for ambient noise.
        Should be called once at startup, before the main listen loop.
        """
        try:
            with sr.Microphone() as source:
                self.log("Calibrating microphone for background noise…")
                self.recognizer.adjust_for_ambient_noise(source, duration=duration)
                self.log("Microphone ready.")
        except Exception as e:
            print(f"[Listener] ERROR: Could not access microphone — {e}")
            print("  Check your microphone connection and PyAudio installation.")
            sys.exit(1)

    def listen(self, phrase_time_limit: int = 10) -> sr.AudioData:
        """
        Classic capture: open the mic and record until a pause.
        Prefer listen_for_turn() for natural conversation.
        """
        with sr.Microphone() as source:
            return self.recognizer.listen(
                source,
                timeout=None,
                phrase_time_limit=phrase_time_limit,
            )

    def listen_for_turn(
        self,
        *,
        running_check: Optional[Callable[[], bool]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        max_wait_s: float = 0.0,
        max_utterance_s: float = 12.0,
        phrase_time_limit: int = 10,
    ) -> Optional[sr.AudioData]:
        """
        Wait for the user to speak, then return one full utterance.

        Uses offline Silero VAD when available; otherwise falls back to
        SpeechRecognition listen(). max_wait_s=0 waits indefinitely.
        """
        if self.turn_taker.available:
            return self.turn_taker.listen_utterance(
                running_check=running_check,
                on_speech_start=on_speech_start,
                max_wait_s=max_wait_s,
                max_utterance_s=max_utterance_s,
            )

        # Classic fallback — blocks until speech starts (timeout=None)
        self.log("VAD unavailable — classic mic listen fallback.")
        if running_check is not None and not running_check():
            return None
        if on_speech_start:
            # Classic path cannot detect speech onset early; notify once we return
            pass
        try:
            audio = self.listen(phrase_time_limit=phrase_time_limit)
            if on_speech_start:
                on_speech_start()
            return audio
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            self.log(f"Classic listen failed: {e}")
            return None
