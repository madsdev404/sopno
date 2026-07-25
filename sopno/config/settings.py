"""
sopno/config/settings.py
━━━━━━━━━━━━━━━━━━━━━━━━
Centralized configuration loader.
Reads config.json from the project root and exposes every setting
as typed attributes on a single `settings` singleton.

Usage anywhere in the project:
    from sopno.config.settings import settings
    print(settings.model_name)   # → "qwen3:8b"
"""

import json
import os
from pathlib import Path

# Always resolve config.json relative to the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH  = _PROJECT_ROOT / "config.json"


class Settings:
    """Typed wrapper around config.json values."""

    def __init__(self, path: Path = _CONFIG_PATH):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ── LLM ──────────────────────────────────────────────
        self.model_name: str        = data.get("model_name", "qwen3:8b")

        # ── Wake-word ─────────────────────────────────────────
        self.wake_words: list       = data.get("wake_words", ["sopno", "dream"])

        # ── Language ──────────────────────────────────────────
        self.voice_lang_bn: str     = data.get("voice_lang_bn", "bn")
        self.voice_lang_en: str     = data.get("voice_lang_en", "en")

        # ── Microphone ────────────────────────────────────────
        self.pause_threshold: float       = data.get("pause_threshold", 0.8)
        self.dynamic_energy_threshold: bool = data.get("dynamic_energy_threshold", True)

        # ── HUD ───────────────────────────────────────────────
        self.hud_opacity: float     = data.get("hud_opacity", 0.85)
        self.hud_position: str      = data.get("hud_position", "top-right")

        # ── Context ───────────────────────────────────────────
        # 1 system prompt + 6 complete turns (12 messages) = 13 before summarization
        self.max_history_length: int = data.get("max_history_length", 13)

        # ── Paths ─────────────────────────────────────────────
        self.project_root: Path     = _PROJECT_ROOT
        self.prompts_dir: Path      = _PROJECT_ROOT / "prompts"
        self.models_dir: Path       = _PROJECT_ROOT / "models"
        self.logs_dir: Path         = _PROJECT_ROOT / "logs"

    def __repr__(self) -> str:
        return f"<Settings model={self.model_name} wake_words={self.wake_words}>"


# Module-level singleton — import this everywhere
settings = Settings()
