"""
sopno/voice/stt
━━━━━━━━━━━━━━━━
Offline Speech-to-Text (faster-whisper).

Whisper runs 100% on-device. Hugging Face is only contacted once if the
model files are missing — then everything stays local. Google STT is
opt-in via config (stt_online_fallback) and OFF by default.

Usage:
    from sopno.voice.stt import transcribe
    text = transcribe(recognizer, audio, language="en")

Public API lives here so callers (`assistant`, `wakeword`, tests) keep the
same import paths after the module → package split. Internal names are also
re-exported so test patches like `sopno.voice.stt._transcribe_whisper`
keep resolving.
"""

from typing import Optional

import speech_recognition as sr

from sopno.config.settings import settings
from sopno.voice.stt.google import _transcribe_google
from sopno.voice.stt.whisper import _transcribe_whisper

__all__ = ["transcribe"]


def transcribe(
    recognizer: sr.Recognizer,
    audio: sr.AudioData,
    language: Optional[str] = None,
) -> str:
    """
    Convert audio to text (offline Whisper).

    Raises sr.UnknownValueError if speech cannot be understood.
    Google fallback is OFF unless settings.stt_online_fallback is True.
    """
    lang = language if language is not None else settings.stt_language
    try:
        return _transcribe_whisper(audio, language=lang)
    except sr.UnknownValueError:
        raise
    except Exception as e:
        if not settings.stt_online_fallback:
            print(f"[STT] Whisper failed ({e}) — staying offline (no Google fallback).")
            raise sr.UnknownValueError(str(e)) from e
        print(f"[STT] Whisper failed ({e}), falling back to Google STT.")
        return _transcribe_google(recognizer, audio, language=lang)
