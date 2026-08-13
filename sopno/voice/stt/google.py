"""
sopno/voice/stt/google.py
━━━━━━━━━━━━━━━━━━━━━━━━
Online Google STT — only used when stt_online_fallback is enabled.
"""

import concurrent.futures
import re
from typing import Optional

import speech_recognition as sr

from sopno.voice.stt.whisper import _whisper_lang


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
