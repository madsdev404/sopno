"""
sopno/voice/stt/filters.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Transcript quality filters — hallucination, babble, and script checks.
"""

import re

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
