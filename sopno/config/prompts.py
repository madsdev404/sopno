"""
sopno/config/prompts.py
━━━━━━━━━━━━━━━━━━━━━━━
Loads prompt text from plain-text files in the prompts/ directory.
Prompts are NEVER hardcoded in Python — edit prompts/*.txt instead.

Usage:
    from sopno.config.prompts import SYSTEM_PROMPT, SUMMARIZE_PROMPT
"""

from pathlib import Path
from sopno.config.settings import settings


def _load(filename: str) -> str:
    """Read a prompt file from the prompts/ directory."""
    path = settings.prompts_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            f"Make sure '{filename}' exists in the prompts/ folder."
        )
    return path.read_text(encoding="utf-8").strip()


# ── Public prompt strings ──────────────────────────────────────────────────────
SYSTEM_PROMPT:    str = _load("system.txt")
SUMMARIZE_PROMPT: str = _load("summarize.txt")
