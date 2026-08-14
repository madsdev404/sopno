"""
sopno/voice/tts.py
━━━━━━━━━━━━━━━━━━
Text-to-Speech engine with automatic fallback.

Priority:
  1. Coqui TTS  — offline, neural, high quality  (requires `pip install TTS`)
  2. gTTS        — online fallback via Google     (requires internet)

Usage:
    from sopno.voice.tts import speak
    speak("Hello! I am Sopno.")
"""

import os
import re
import subprocess
import tempfile
from typing import Callable, Optional

# ── Engine detection ───────────────────────────────────────────────────────────
try:
    from TTS.api import TTS as _CoquiTTS
    _ENGINE = "coqui"
except Exception:
    _ENGINE = "gtts"   # gTTS online fallback

_coqui_instance = None  # lazy-loaded singleton


def _is_bangla(text: str) -> bool:
    """Returns True if the text contains Bangla Unicode characters."""
    return bool(re.search(r'[\u0980-\u09FF]', text))


def _play_audio(
    path: str,
    should_stop: Optional[Callable[[], bool]] = None,
    on_play_start: Optional[Callable[[], None]] = None,
) -> None:
    """
    Play a media file with ffplay, stopping early if ``should_stop()`` turns True.

    ``on_play_start()`` fires right after playback begins — used by the
    barge-in monitor to start measuring the assistant's own voice.
    """
    proc = subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
    )
    if on_play_start is not None:
        on_play_start()

    if should_stop is None:
        proc.wait()
        return

    while proc.poll() is None:
        if should_stop():
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            return
        try:
            proc.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass


def _speak_coqui(
    text: str,
    should_stop: Optional[Callable[[], bool]] = None,
    on_play_start: Optional[Callable[[], None]] = None,
) -> None:
    """Synthesize speech offline using Coqui TTS (neural, best quality)."""
    global _coqui_instance
    if _coqui_instance is None:
        # Model is downloaded once to ~/.local/share/tts/ on first run (~200 MB)
        _coqui_instance = _CoquiTTS(
            model_name="tts_models/multilingual/multi-dataset/your_tts",
            progress_bar=False,
            gpu=False,
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _coqui_instance.tts_to_file(text=text, file_path=tmp_path)
        _play_audio(tmp_path, should_stop=should_stop, on_play_start=on_play_start)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _speak_gtts(
    text: str,
    should_stop: Optional[Callable[[], bool]] = None,
    on_play_start: Optional[Callable[[], None]] = None,
) -> None:
    """Synthesize speech online using gTTS (Google TTS fallback)."""
    from gtts import gTTS

    lang = "bn" if _is_bangla(text) else "en"

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        gTTS(text=text, lang=lang).save(tmp_path)
        _play_audio(tmp_path, should_stop=should_stop, on_play_start=on_play_start)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ── Public API ─────────────────────────────────────────────────────────────────

def speak(
    text: str,
    should_stop: Optional[Callable[[], bool]] = None,
    on_play_start: Optional[Callable[[], None]] = None,
) -> None:
    """
    Speak the given text aloud.

    Uses Coqui TTS (offline) if available, otherwise falls back to gTTS (online).
    Automatically detects Bangla vs English for the fallback engine.

    ``should_stop`` is polled during playback — returning True cuts the audio
    short (used for barge-in). ``on_play_start`` fires once playback begins.
    """
    if not text or not text.strip():
        return

    if _ENGINE == "coqui":
        try:
            _speak_coqui(text, should_stop=should_stop, on_play_start=on_play_start)
            return
        except Exception as e:
            print(f"[TTS] Coqui failed ({e}), falling back to gTTS.")

    _speak_gtts(text, should_stop=should_stop, on_play_start=on_play_start)


def engine_name() -> str:
    """Returns the name of the active TTS engine ('coqui' or 'gtts')."""
    return _ENGINE
