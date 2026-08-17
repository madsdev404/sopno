"""
sopno/core/assistant/memory.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Memory intent detection via regex (English + Bangla).

Evaluation order: forget_all → recall → remember → forget.
"""

from __future__ import annotations

import re
from typing import Optional


# ── Memory intent patterns (English + Bangla) ────────────────────────────────
# Order of evaluation matters: recall before remember (recall phrases contain
# "remember"), and remember before forget ("don't forget X" must REMEMBER).

MEMORY_FORGET_ALL_EN = re.compile(
    r"\bforget everything\b|\berase\s+(?:all|your|every)\s+(?:memory|memories)\b|"
    r"\bclear\s+(?:your|all)\s+(?:memory|memories)\b",
    re.IGNORECASE,
)

MEMORY_RECALL_EN = re.compile(
    r"\bwhat do you remember\b|\bwhat memories\b|\bwhat have you remembered\b|"
    r"\bdo you remember anything\b|\bwhat did i tell you\b|"
    r"\bwhat did you remember\b|\btell me what you remember\b",
    re.IGNORECASE,
)

MEMORY_REMEMBER_EN = re.compile(
    r"\b(?:remember\s+that|remember\s+this|remember|don'?t\s+forget|"
    r"do\s+not\s+forget|note\s+that|take\s+a\s+note|take\s+note)"
    r"\s+(?:that\s+)?(?:about\s+)?(.+)$",
    re.IGNORECASE,
)

MEMORY_FORGET_EN = re.compile(
    r"\bforget\s+(?:that\s+|about\s+)?(.+)$",
    re.IGNORECASE,
)

MEMORY_FORGET_ALL_BN = re.compile(
    r"(?<!\w)সব\s+ভুলে\s+যাও(?!\w)|(?<!\w)সব\s+ভুলে\s+যেও(?!\w)|"
    r"(?<!\w)সব\s+মনে\s+থাকা\s+মুছে\s+দাও(?!\w)|"
    r"(?<!\w)সব\s+মুছে\s+দাও(?!\w)|"
    r"(?<!\w)মনে\s+থাকা\s+সব\s+মুছে\s+দাও(?!\w)",
)

MEMORY_RECALL_BN = re.compile(
    r"(?<!\w)(?:কী|কি)\s+মনে\s+আছে(?!\w)|(?<!\w)(?:কী|কি)\s+মনে\s+রেখেছ(?!\w)|"
    r"(?<!\w)(?:কী|কি)\s+মনে\s+রেখেছো(?!\w)|(?<!\w)(?:কী|কি)\s+মনে\s+রেখ(?!\w)|"
    r"(?<!\w)তুমি\s+(?:কী|কি)\s+মনে\s+(?:রাখো|রাখ)(?!\w)|"
    r"(?<!\w)(?:কী|কি)\s+জিনিস\s+মনে\s+আছে(?!\w)|"
    r"(?<!\w)আমার\s+সম্পর্কে\s+(?:কী|কি)\s+মনে\s+আছে(?!\w)",
)

MEMORY_REMEMBER_BN = re.compile(
    r"(?<!\w)(?:মনে\s+রাখো|মনে\s+রাখ|মনে\s+রাখুন|মনে\s+রেখো|মনে\s+রেখ)"
    r"\s+(?:যে\s+)?(.+)$"
    r"|(?<!\w)(?:ভুলো\s+না|ভুলে\s+যেও\s+না)\s+(?:যে\s+)?(.+)$"
)

MEMORY_FORGET_BN = re.compile(
    r"(?<!\w)(?:ভুলে\s+যাও|ভুলে\s+যেও|মুছে\s+ফেলো|মনে\s+থেকে\s+মুছে\s+দাও)"
    r"\s+(?:যে\s+)?(.+)$",
)

MEMORY_TOPIC_EN = re.compile(r"\b(?:about|regarding)\s+(.+)$", re.IGNORECASE)
# Bangla puts the topic BEFORE সম্পর্কে/নিয়ে: "ফ্লাস্ক সম্পর্কে কী মনে আছে"
MEMORY_TOPIC_BN = re.compile(r"(.+?)\s+(?:সম্পর্কে|নিয়ে)\s+(?:কী|কি)\s+মনে")


def _memory_topic(text: str, is_bn: bool) -> str:
    """Extract the recall topic from 'what do you remember about <topic>'."""
    pattern = MEMORY_TOPIC_BN if is_bn else MEMORY_TOPIC_EN
    match = pattern.search(text.strip())
    if not match:
        return ""
    return match.group(1).strip().rstrip("?।.!?")


def parse_memory_intent(text: str) -> Optional[tuple[str, str]]:
    """
    Detect explicit memory commands via rules (fast path, no LLM call).

    Returns (action, content):
      ("remember",  fact)    — store this fact
      ("forget",    target)  — forget a specific memory
      ("forget_all", "")     — forget everything
      ("recall",    topic)   — recall memories (topic may be "")
      None                   — not a memory command

    Evaluation order: forget_all → recall → remember → forget.
    """
    if not text:
        return None

    txt = text.strip()
    is_bn = bool(re.search(r"[\u0980-\u09FF]", txt))

    if is_bn:
        if MEMORY_FORGET_ALL_BN.search(txt):
            return ("forget_all", "")
        if MEMORY_FORGET_BN.search(txt):
            target = MEMORY_FORGET_BN.search(txt).group(1).strip().rstrip("?।.!?")
            return ("forget", target) if target else None
        if MEMORY_RECALL_BN.search(txt):
            return ("recall", _memory_topic(txt, True))
        if (m := MEMORY_REMEMBER_BN.search(txt)) is not None:
            content = (m.group(1) or m.group(2) or "").strip().rstrip("?।.!?")
            return ("remember", content) if content else None
    else:
        if MEMORY_FORGET_ALL_EN.search(txt):
            return ("forget_all", "")
        if MEMORY_RECALL_EN.search(txt):
            return ("recall", _memory_topic(txt, False))
        if (m := MEMORY_REMEMBER_EN.search(txt)) is not None:
            content = m.group(1).strip().rstrip("?.!")
            return ("remember", content) if content else None
        if (m := MEMORY_FORGET_EN.search(txt)) is not None:
            target = m.group(1).strip().rstrip("?.!")
            return ("forget", target) if target else None

    return None
