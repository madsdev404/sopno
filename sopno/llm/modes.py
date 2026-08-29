"""
sopno/llm/modes.py
━━━━━━━━━━━━━━━━━━
Reasoning-mode → Ollama request overrides.

Maps Sopno's selectable reasoning depth onto the LLM request budget:
quick / thinking / deep / plan (+ auto routing). Design doc:
doc/roadmap/thinking-modes.md. One folder = one job.
"""

from typing import Any, Optional

import re

QUICK = "quick"
THINKING = "thinking"
DEEP = "deep"
PLAN = "plan"
AUTO = "auto"
VALID = (QUICK, THINKING, DEEP, PLAN, AUTO)

# name -> {think, num_predict, num_ctx, temperature}
MODES: dict[str, dict[str, Any]] = {
    QUICK:    {"think": False, "num_predict": 120, "num_ctx": 2048, "temperature": 0.6},
    THINKING: {"think": True,  "num_predict": 300, "num_ctx": 4096, "temperature": 0.6},
    DEEP:     {"think": True,  "num_predict": 800, "num_ctx": 8192, "temperature": 0.5},
    PLAN:     {"think": True,  "num_predict": 400, "num_ctx": 4096, "temperature": 0.5},
}

# --- Deferred slot -------------------------------------------------------
# Per-mode model selection lands in a later phase. When it does, each entry
# gains an optional "model" key and `client.chat()` passes it through:
#     DEEP: {..., "model": "qwen3:14b"}   # bigger brain for hard thinking
#     QUICK: {..., "model": "qwen3:4b-instruct"}  # small & fast (non-hybrid!)
# MODES with a "model" set override settings.model_name for that turn.
# ------------------------------------------------------------------------

# Headline routing for AUTO (deterministic — no LLM call).
_DEEP_HINTS = re.compile(
    r"\b(deep\s*(think|analy|research|dive)|analyze\s+in\s+detail|"
    r"explain\s+thoroughly|debug|optimize|compare\s+(the\s+)?trade|"
    r"and\s+what\s+would\s+happen\b|গভীর|বিশ্লেষণ|খু?ব\s+ভাবে\s+ভাবো)\b",
    re.IGNORECASE,
)
_PLAN_HINTS = re.compile(
    r"\b(plan|make\s+a\s+plan|set\s+up|configure|set\s+up\s+the\s+project|"
    r"build\b|instal??\b|migrate|prepare\b|outline)\b|"
    r"(প্ল্যান|প্লান|সেট\s+আপ|বানাও|তৈরি\s+করো)\b",
    re.IGNORECASE,
)


def normalize(mode: str) -> Optional[str]:
    mode = (mode or "").strip().lower()
    return mode if mode in VALID else None


def spec(mode: str) -> dict[str, Any]:
    """Return the request spec for a concrete (non-auto) mode."""
    return MODES.get(normalize(mode) or QUICK, MODES[QUICK])


def resolve(mode: str, utterance: str) -> dict[str, Any]:
    """Resolve 'auto' against the utterance → a concrete mode spec."""
    if normalize(mode) not in (None, AUTO):
        return spec(mode)
    return spec(_auto_for(utterance))


def _auto_for(utterance: str) -> str:
    text = utterance.lower()
    if _PLAN_HINTS.search(text):
        return PLAN
    if _DEEP_HINTS.search(text):
        return DEEP
    if len(utterance.split()) <= 4:  # greeting / one-word
        return QUICK
    return THINKING