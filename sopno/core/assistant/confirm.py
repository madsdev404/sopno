"""
sopno/core/assistant/confirm.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Yes/No confirmation patterns (English + Bangla).
"""

from __future__ import annotations

import re

YES_RESPONSES = re.compile(
    r"\b(?:yes|yeah|yep|ok|okay|sure|go ahead|do it|proceed|please do|confirm|allow it)\b",
    re.IGNORECASE,
)
YES_RESPONSES_BN = re.compile(r"(?<!\w)(?:হ্যাঁ|হ্যা|ঠিক আছে|হুম)(?!\w)|করো|করুন|দাও|অনুমতি")
NO_RESPONSES = re.compile(
    r"\b(?:no|nope|nah|cancel|stop|abort|deny|don'?t|do not|refuse|never mind)\b",
    re.IGNORECASE,
)
NO_RESPONSES_BN = re.compile(r"(?<!\w)(?:না|থামো|থাম|বাতিল|নিষেধ)(?!\w)")
