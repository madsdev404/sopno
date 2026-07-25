"""
sopno/voice/stt.py
━━━━━━━━━━━━━━━━━━
Speech-to-Text engine with automatic fallback.

Priority:
  1. faster-whisper  — offline, bilingual, low latency  (requires `pip install faster-whisper`)
  2. Google STT       — online fallback via SpeechRecognition

Usage:
    from sopno.voice.stt import transcribe
    text = transcribe(recognizer, audio)
"""

import concurrent.futures
import os
import re
import tempfile

import speech_recognition as sr

# ── Whisper singleton ──────────────────────────────────────────────────────────
_whisper_model = None


def _get_whisper():
    """Lazy-loads the Faster Whisper model once and caches it."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        # tiny model: fast, low RAM, runs on CPU with int8 quantization
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _whisper_model


# ── Offline transcription (primary) ───────────────────────────────────────────

def _transcribe_whisper(audio: sr.AudioData) -> str:
    """
    Transcribe audio offline using faster-whisper.
    Handles both English and Bangla natively.
    """
    model = _get_whisper()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with open(tmp_path, "wb") as f:
            f.write(audio.get_wav_data())

        segments, _ = model.transcribe(tmp_path, beam_size=5)
        text = " ".join(seg.text for seg in segments).strip()

        if not text:
            raise sr.UnknownValueError("Whisper returned an empty transcription.")

        return text
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ── Online transcription (fallback) ───────────────────────────────────────────

def _transcribe_google(recognizer: sr.Recognizer, audio: sr.AudioData) -> str:
    """
    Bilingual Google STT fallback.
    Runs English and Bangla recognition in parallel; returns the best result.
    """
    def _try_lang(lang: str):
        try:
            return lang, recognizer.recognize_google(audio, language=lang)
        except Exception as e:
            return lang, e

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_try_lang, "bn-BD"), pool.submit(_try_lang, "en-US")]
        results = {lang: res for lang, res in (f.result() for f in futures)}

    bn = results["bn-BD"]
    en = results["en-US"]

    if isinstance(bn, Exception) and isinstance(en, Exception):
        raise bn  # both failed — surface the error

    if isinstance(bn, Exception):
        return en
    if isinstance(en, Exception):
        return bn

    # Both succeeded: prefer Bangla if Bangla characters were returned
    has_bn_chars = bool(re.search(r'[\u0980-\u09FF]', bn))
    return bn if has_bn_chars else en


# ── Public API ─────────────────────────────────────────────────────────────────

def transcribe(recognizer: sr.Recognizer, audio: sr.AudioData) -> str:
    """
    Convert audio to text.

    Uses faster-whisper (offline) first; falls back to Google STT if anything fails.
    Raises sr.UnknownValueError if neither engine can understand the audio.
    """
    try:
        return _transcribe_whisper(audio)
    except sr.UnknownValueError:
        raise  # Empty audio — don't retry with Google
    except Exception as e:
        print(f"[STT] Whisper failed ({e}), falling back to Google STT.")
        return _transcribe_google(recognizer, audio)
