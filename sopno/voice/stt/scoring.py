"""
sopno/voice/stt/scoring.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Transcription scoring and audio sanity checks.
"""

import re

import speech_recognition as sr

from sopno.voice.stt.filters import _has_bangla, _is_junk, _is_supported_utterance

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
