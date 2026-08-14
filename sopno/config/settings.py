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
        # Qwen3 "thinking" burns 30–90s on CPU for short voice replies — keep off
        self.llm_think: bool        = bool(data.get("llm_think", False))
        self.llm_num_predict: int   = int(data.get("llm_num_predict", 120))
        self.llm_num_ctx: int       = int(data.get("llm_num_ctx", 2048))
        self.llm_temperature: float = float(data.get("llm_temperature", 0.6))

        # ── STT ───────────────────────────────────────────────
        # tiny = fast but inaccurate; base = good CPU default; small = better Bangla
        self.stt_model: str         = data.get("stt_model", "small")
        # "auto" | "en" | "bn" — auto tries BOTH (needed for Bangla); lock with en/bn
        self.stt_language: str      = data.get("stt_language", "auto")
        # Keep False — Sopno is offline-first; Google STT is opt-in only
        self.stt_online_fallback: bool = bool(data.get("stt_online_fallback", False))
        # "classic" = SpeechRecognition mic (reliable). "vad" = Silero/PyAudio path.
        self.stt_capture: str = data.get("stt_capture", "classic")

        # ── Listening mode ─────────────────────────────────────
        # "wake_word" = wait for wake word before listening; "always_on" = continuous VAD
        self.listening_mode: str = data.get("listening_mode", "wake_word")

        # ── Wake-word ─────────────────────────────────────────
        self.wake_words: list       = data.get("wake_words", ["dream"])

        # ── Language ──────────────────────────────────────────
        self.voice_lang_bn: str     = data.get("voice_lang_bn", "bn")
        self.voice_lang_en: str     = data.get("voice_lang_en", "en")

        # ── Microphone ────────────────────────────────────────
        # Higher pause = wait longer before ending a turn (avoids mid-sentence cuts)
        self.pause_threshold: float       = float(data.get("pause_threshold", 1.5))
        # Min speaking seconds before a phrase counts (ignores coughs / "bal" blips)
        self.phrase_threshold: float      = float(data.get("phrase_threshold", 0.3))
        # Energy band after calibration — too high = never hears you; too low = noise
        self.energy_threshold_floor: float = float(data.get("energy_threshold_floor", 100))
        self.energy_threshold_ceiling: float = float(
            data.get("energy_threshold_ceiling", 250)
        )
        # Dynamic threshold often rises mid-phrase and cuts speech early — keep off
        self.dynamic_energy_threshold: bool = bool(
            data.get("dynamic_energy_threshold", False)
        )

        # ── HUD ───────────────────────────────────────────────
        self.hud_opacity: float     = data.get("hud_opacity", 0.85)
        self.hud_position: str      = data.get("hud_position", "top-right")

        # ── Context ───────────────────────────────────────────
        # 1 system prompt + 6 complete turns (12 messages) = 13 before summarization
        self.max_history_length: int = data.get("max_history_length", 13)

        # ── Memory ────────────────────────────────────────────
        # Persistent long-term memory (SQLite). Relative paths resolve to project root.
        self.memory_path: Path = Path(data.get("memory_path", "sopno/memory/memory.db"))
        if not self.memory_path.is_absolute():
            self.memory_path = _PROJECT_ROOT / self.memory_path
        # Token budget for the [Memories] block injected into the LLM prompt.
        # Protects the small num_ctx window (2048) from memory bloat.
        self.memory_max_tokens: int = int(data.get("memory_max_tokens", 400))
        # How many memories are injected / recalled per turn.
        self.memory_recall_limit: int = int(data.get("memory_recall_limit", 8))

        # ── Paths ─────────────────────────────────────────────
        self.project_root: Path     = _PROJECT_ROOT
        self.prompts_dir: Path      = _PROJECT_ROOT / "prompts"
        self.models_dir: Path       = _PROJECT_ROOT / "models"
        self.logs_dir: Path         = _PROJECT_ROOT / "logs"

    def __repr__(self) -> str:
        return f"<Settings model={self.model_name} wake_words={self.wake_words}>"


# Module-level singleton — import this everywhere
settings = Settings()
