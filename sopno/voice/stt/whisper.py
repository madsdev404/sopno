"""
sopno/voice/stt/whisper.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
faster-whisper model loading and offline transcription.
"""

import concurrent.futures
import os
import tempfile
from pathlib import Path
from typing import Optional

import speech_recognition as sr

from sopno.config.settings import settings
from sopno.voice.stt.filters import _is_supported_utterance
from sopno.voice.stt.scoring import (
    _audio_is_too_quiet,
    _audio_is_too_short,
    _is_too_thin,
    _score_result,
)

# Quiet HF Hub noise; we prefer local files
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Shared pool for Whisper transcription timeouts.
_STT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")

# ── Whisper singleton ──────────────────────────────────────────────────────────
_whisper_model = None
_whisper_model_name: Optional[str] = None


def _whisper_download_root() -> Path:
    root = settings.models_dir / "whisper"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _get_whisper():
    """Lazy-loads Faster Whisper from local disk (offline-first)."""
    global _whisper_model, _whisper_model_name
    name = settings.stt_model
    if _whisper_model is not None and _whisper_model_name == name:
        return _whisper_model

    from faster_whisper import WhisperModel

    root = str(_whisper_download_root())
    print(f"[STT] Loading Whisper '{name}' offline (cpu/int8)…")

    try:
        # Use whatever is already on disk (HF cache or models/whisper) — no Hub call
        _whisper_model = WhisperModel(
            name,
            device="cpu",
            compute_type="int8",
            download_root=root,
            local_files_only=True,
        )
    except Exception:
        try:
            # Fall back to the default Hugging Face cache (still offline)
            _whisper_model = WhisperModel(
                name,
                device="cpu",
                compute_type="int8",
                local_files_only=True,
            )
        except Exception:
            # First run only: pull model weights once, then fully offline
            print(
                f"[STT] Model '{name}' not cached — "
                "one-time download, then fully offline."
            )
            _whisper_model = WhisperModel(
                name,
                device="cpu",
                compute_type="int8",
                download_root=root,
                local_files_only=False,
            )

    _whisper_model_name = name
    # After a successful load, block further Hub chatter this process
    os.environ["HF_HUB_OFFLINE"] = "1"
    print(f"[STT] Whisper '{name}' ready (offline).")
    return _whisper_model


def _whisper_lang(language: Optional[str]) -> Optional[str]:
    """Map Sopno language codes to Whisper language codes."""
    if not language or language in ("auto", ""):
        return None
    lang = language.lower().strip()
    if lang in ("bn", "bn-bd", "bangla", "bengali"):
        return "bn"
    if lang in ("en", "en-us", "en-gb", "english"):
        return "en"
    return lang


def _transcribe_whisper(audio: sr.AudioData, language: Optional[str] = None) -> str:
    """
    Transcribe audio offline using faster-whisper.

    Writes a clean 16 kHz WAV (from whatever rate the mic captured),
    lets Whisper auto-detect language, and only retries the other
    language if the first result looks like junk.
    """
    if _audio_is_too_short(audio):
        raise sr.UnknownValueError("Audio too short for reliable transcription.")
    if _audio_is_too_quiet(audio):
        raise sr.UnknownValueError("Audio too quiet for reliable transcription.")

    model = _get_whisper()
    forced_lang = _whisper_lang(language)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Always hand Whisper 16 kHz mono PCM — mic may be 44100/48000
        with open(tmp_path, "wb") as f:
            f.write(audio.get_wav_data(convert_rate=16000, convert_width=2))

        print(
            f"[STT] Audio in: {audio.sample_rate} Hz, "
            f"{len(audio.frame_data)} bytes → wav@16kHz"
        )

        def _run(lang: Optional[str]):
            segments_gen, info = model.transcribe(
                tmp_path,
                language=lang,  # None = Whisper auto-detect
                beam_size=5,
                best_of=5,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=400,
                    speech_pad_ms=200,
                ),
                condition_on_previous_text=False,
                without_timestamps=True,
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.2,
            )
            segments = list(segments_gen)
            text = " ".join(seg.text for seg in segments).strip()
            detected = getattr(info, "language", lang or "?")
            prob = float(getattr(info, "language_probability", 0.0) or 0.0)
            return text, segments, detected, prob

        def _run_with_timeout(lang: Optional[str]):
            """Run transcription in a thread with timeout to prevent hangs."""
            timeout = settings.stt_timeout
            future = _STT_EXECUTOR.submit(_run, lang)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                raise RuntimeError(
                    f"Whisper transcription timed out after {timeout}s"
                )

        if forced_lang:
            text, segments, detected, prob = _run_with_timeout(forced_lang)
            score = _score_result(text, segments)
            print(f"[STT] forced={forced_lang} score={score:.2f} text={text[:80]!r}")
        else:
            # 1) Auto-detect once (best when audio is clean)
            text, segments, detected, prob = _run_with_timeout(None)
            score = _score_result(text, segments)
            print(
                f"[STT] auto={detected} p={prob:.2f} score={score:.2f} text={text[:80]!r}"
            )

            # 2) Retry only when auto is junk, unsupported lang, or truly weak
            need_retry = (
                score <= -900
                or not _is_supported_utterance(text)
                or detected not in ("en", "bn")
                or (score < _RETRY_SCORE and prob < 0.55)
            )
            if need_retry:
                # Prefer the other Sopno language; if auto was ar/etc., try both
                alts = ("en", "bn") if detected not in ("en", "bn") else (
                    ("en",) if detected == "bn" else ("bn",)
                )
                for alt in alts:
                    alt_text, alt_segs, alt_det, alt_prob = _run_with_timeout(alt)
                    alt_score = _score_result(alt_text, alt_segs)
                    print(
                        f"[STT] retry={alt_det} p={alt_prob:.2f} "
                        f"score={alt_score:.2f} text={alt_text[:80]!r}"
                    )
                    if alt_score > score:
                        text, segments, detected, score = (
                            alt_text,
                            alt_segs,
                            alt_det,
                            alt_score,
                        )

        if (
            score <= -900
            or not text
            or not _is_supported_utterance(text)
            or score < _MIN_ACCEPT_SCORE
            or _is_too_thin(text, score)
        ):
            raise sr.UnknownValueError("Whisper returned an empty or junk transcription.")

        print(f"[STT] Final '{detected}' (score={score:.2f}): {text[:80]}")
        return text
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
