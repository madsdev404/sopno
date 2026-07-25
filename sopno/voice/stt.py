"""
sopno/voice/stt.py
━━━━━━━━━━━━━━━━━━
Offline Speech-to-Text (faster-whisper).

Whisper runs 100% on-device. Hugging Face is only contacted once if the
model files are missing — then everything stays local. Google STT is
opt-in via config (stt_online_fallback) and OFF by default.

Usage:
    from sopno.voice.stt import transcribe
    text = transcribe(recognizer, audio, language="en")
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import speech_recognition as sr

from sopno.config.settings import settings

# Quiet HF Hub noise; we prefer local files
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# ── Whisper singleton ──────────────────────────────────────────────────────────
_whisper_model = None
_whisper_model_name: Optional[str] = None

# Common hallucinations on silence / noise / clipped audio
_HALLUCINATIONS = {
    "thanks for watching",
    "thank you for watching",
    "subscribe",
    "please subscribe",
    "mbc news",
    "www",
    "you",
    ".",
    "",
}


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


def _is_junk(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s\u0980-\u09FF]", "", text or "", flags=re.UNICODE).strip().lower()
    if cleaned in _HALLUCINATIONS or len(cleaned) < 2:
        return True
    return _is_babble(cleaned)


def _is_babble(text: str) -> bool:
    """
    Catch Whisper syllable loops and consonant-soup hallucinations
    like 'বাবাবাবাবাবা' or 'স্রকবিবি পচতিবিককা…'.
    """
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) < 4:
        return False
    if re.search(r"(.)\1{3,}", compact):
        return True
    if len(compact) >= 6 and len(set(compact)) <= 3:
        return True
    for n in (1, 2, 3, 4):
        unit = compact[:n]
        if not unit:
            continue
        reps = len(compact) // n
        if reps >= 3 and unit * reps == compact[: n * reps] and n * reps >= 6:
            return True

    # Repeated short chunks anywhere (…বিকবিকবিক… / …কবাকবা…)
    for n in (2, 3, 4):
        for i in range(max(0, len(compact) - n)):
            unit = compact[i : i + n]
            if len(set(unit)) == 1:
                continue
            hits = compact.count(unit)
            if hits >= 5 and hits * n >= len(compact) * 0.22:
                return True

    # Bangla script with almost no vowels/matras ≈ random consonant soup
    bn = re.findall(r"[\u0980-\u09FF]", compact)
    if len(bn) >= 12:
        vowels = len(re.findall(r"[অআইঈউঊঋএঐওঔািীুূৃেৈোৌ]", compact))
        if vowels / len(bn) < 0.12:
            return True
    return False


def _has_bangla(text: str) -> bool:
    return bool(re.search(r"[\u0980-\u09FF]", text or ""))


def _has_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", text or ""))


def _is_supported_utterance(text: str) -> bool:
    """Sopno is en/bn only — drop Arabic/CJK/etc. hallucinations."""
    if not text or _is_junk(text):
        return False
    return _has_bangla(text) or _has_latin(text)


# Accept soft-but-real speech (e.g. score≈-1.0). Still reject garbage (~-1.5 / -999).
_MIN_ACCEPT_SCORE = -1.25
# Only re-run Whisper when auto is weak or wrong language — not for OK English.
_RETRY_SCORE = -1.15


def _score_result(text: str, segments) -> float:
    """Higher is better. Do NOT blindly reward Bangla script (causes বাবাবা junk wins)."""
    if not text or _is_junk(text) or not _is_supported_utterance(text):
        return -999.0
    segs = list(segments) if segments is not None else []
    if segs:
        avg_lp = sum(float(getattr(s, "avg_logprob", -1.0) or -1.0) for s in segs) / len(segs)
        no_speech = sum(float(getattr(s, "no_speech_prob", 0.5) or 0.5) for s in segs) / len(segs)
        comp = sum(float(getattr(s, "compression_ratio", 1.0) or 1.0) for s in segs) / len(segs)
    else:
        avg_lp, no_speech, comp = -1.0, 0.5, 1.0

    score = avg_lp - (no_speech * 0.8)
    if comp > 2.2:
        score -= 1.0
    if len(text.strip()) < 4:
        score -= 0.5
    # Mild bonus only for diverse Bangla (real words, not babble)
    if _has_bangla(text) and len(set(text)) >= 6:
        score += 0.35
    return score


def _audio_duration_s(audio: sr.AudioData) -> float:
    try:
        return len(audio.frame_data) / float(audio.sample_rate * audio.sample_width or 1)
    except Exception:
        return 0.0


def _audio_is_too_quiet(audio: sr.AudioData) -> bool:
    """Reject near-silent clips that make Whisper invent text."""
    try:
        import array

        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        samples = array.array("h")
        samples.frombytes(raw)
        if not samples:
            return True
        acc = sum(int(s) * int(s) for s in samples) / len(samples)
        # Slightly stricter than before — soft noise still invented words
        return (acc ** 0.5) < 120
    except Exception:
        return False


def _audio_is_too_short(audio: sr.AudioData) -> bool:
    """Reject blips — Whisper fills them with random words."""
    return _audio_duration_s(audio) < 0.7


def _is_too_thin(text: str, score: float) -> bool:
    """Single short token with weak confidence is usually noise, not a command."""
    words = re.findall(r"[\w\u0980-\u09FF]+", text or "", flags=re.UNICODE)
    if len(words) == 0:
        return True
    if len(words) == 1 and len(words[0]) <= 4 and score < -0.55:
        return True
    if len(words) <= 2 and sum(len(w) for w in words) <= 5 and score < -0.7:
        return True
    return False


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

        if forced_lang:
            text, segments, detected, prob = _run(forced_lang)
            score = _score_result(text, segments)
            print(f"[STT] forced={forced_lang} score={score:.2f} text={text[:80]!r}")
        else:
            # 1) Auto-detect once (best when audio is clean)
            text, segments, detected, prob = _run(None)
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
                    alt_text, alt_segs, alt_det, alt_prob = _run(alt)
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


def _transcribe_google(
    recognizer: sr.Recognizer,
    audio: sr.AudioData,
    language: Optional[str] = None,
) -> str:
    """Online Google STT — only used when stt_online_fallback is enabled."""
    hinted = _whisper_lang(language)

    def _try_lang(lang: str):
        try:
            return lang, recognizer.recognize_google(audio, language=lang)
        except Exception as e:
            return lang, e

    if hinted == "bn":
        order = ["bn-BD", "en-US"]
    elif hinted == "en":
        order = ["en-US", "bn-BD"]
    else:
        order = ["bn-BD", "en-US"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_try_lang, code) for code in order]
        results = {lang: res for lang, res in (f.result() for f in futures)}

    bn = results.get("bn-BD")
    en = results.get("en-US")

    if isinstance(bn, Exception) and isinstance(en, Exception):
        raise bn
    if isinstance(bn, Exception):
        return en
    if isinstance(en, Exception):
        return bn

    has_bn_chars = bool(re.search(r"[\u0980-\u09FF]", bn))
    if hinted == "bn":
        return bn
    if hinted == "en":
        return en
    return bn if has_bn_chars else en


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
