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

        # ── Barge-in ─────────────────────────────────────────
        # Stop talking the moment the user starts talking.
        self.barge_in_enabled: bool = bool(data.get("barge_in_enabled", True))
        # Seconds of Sopno's own voice measured at playback start (the baseline).
        self.barge_in_baseline_s: float = float(data.get("barge_in_baseline_s", 0.4))
        # User speech must exceed own_voice * multiplier + margin to count.
        self.barge_in_multiplier: float = float(data.get("barge_in_multiplier", 1.7))
        self.barge_in_margin: float = float(data.get("barge_in_margin", 30))
        # How long user speech must persist before interrupting (debounce).
        self.barge_in_confirm_ms: float = float(data.get("barge_in_confirm_ms", 180))

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
        # Semantic (vector) recall: sqlite-vec vec0 + the Ollama embed model.
        # When disabled or the model/extension is unavailable, recall falls
        # back to the FTS5 keyword path — memory always works.
        self.semantic_memory_enabled: bool = bool(data.get("semantic_memory_enabled", True))
        # How many semantic (meaning-based) candidates are fetched per recall.
        self.semantic_recall_limit: int = int(data.get("semantic_recall_limit", 4))

        # ── Research (RAG) ────────────────────────────────────
        # Local Ollama embedding model — free, offline, 768-dim, best for CPU.
        self.research_embed_model: str = data.get("research_embed_model", "nomic-embed-text")
        # How many web pages to read per research run (1-10).
        self.research_max_pages: int = int(data.get("research_max_pages", 6))
        # Cap per-page characters read from each fetched page.
        self.research_page_chars: int = int(data.get("research_page_chars", 20000))
        # Chunk size (chars) for embedding/indexing page text.
        self.research_chunk_chars: int = int(data.get("research_chunk_chars", 1800))
        # How many passages the summarizer sees (top-k retrieval).
        self.research_top_k: int = int(data.get("research_top_k", 6))
        # Summary length budget (tokens) for the research answer.
        self.research_summary_tokens: int = int(data.get("research_summary_tokens", 800))
        # Context window for the summarization call (chunks are large).
        self.research_summary_ctx: int = int(data.get("research_summary_ctx", 8192))

        # ── Terminal (persistent shell) ───────────────────────
        # Master switch for terminal access (cleat persistent PTY shell).
        self.terminal_enabled: bool = bool(data.get("terminal_enabled", True))
        # Shell binary for the persistent session.
        self.terminal_shell: str = data.get("terminal_shell", "/bin/bash")
        # Default wait (seconds) for run_terminal before returning partial output.
        self.terminal_timeout: int = int(data.get("terminal_timeout", 30))
        # Hard cap on how long a single run_terminal may block.
        self.terminal_max_timeout: int = int(data.get("terminal_max_timeout", 300))
        # Output shown to the LLM per call (tail kept when longer).
        self.terminal_output_chars: int = int(data.get("terminal_output_chars", 4000))
        # Destructive/irreversible command patterns (lowercase substrings).
        self.terminal_blocklist: list = data.get(
            "terminal_blocklist",
            [
                "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
                "rm -rf /", "rm -fr /", "rm -rf /*", "rm -fr /*",
                "rm -rf ~", "rm -fr ~", "sudo rm -rf /",
                "mkfs", "fdisk", "parted", "mkpart", "mkswap",
                "fork bomb", ":(){",
                "chmod -R 777 /", "chmod 777 /",
                "> /dev/sda", "> /dev/sdb", "> /dev/sdc", "> /dev/sdd",
                "of=/dev/sda", "of=/dev/sdb", "of=/dev/sdc",
            ],
        )

        # ── File access (permission-gated) ────────────────────
        # Master switch for the file tools.
        self.file_enabled: bool = bool(data.get("file_enabled", True))
        # Roots Sopno may READ. "." (or "<project_root>") = the project root.
        self.file_allowed_read: list = data.get(
            "file_allowed_read", [str(_PROJECT_ROOT)]
        )
        # Roots Sopno may WRITE / EDIT / DELETE / RENAME in.
        self.file_allowed_write: list = data.get(
            "file_allowed_write", [str(_PROJECT_ROOT)]
        )
        # Secrets / foot-gun paths that are off-limits even inside the roots.
        self.file_blocked_paths: list = data.get(
            "file_blocked_paths",
            [
                ".env", ".env.*", ".env.local", ".git", ".ssh", ".gnupg",
                ".netrc", ".aws", "id_rsa", "id_dsa", "id_ecdsa",
                "id_ed25519", "*.pem", "*.key", "credentials.json",
                "service-account.json", "*.secret", "*.keychain",
                "config.json", "sopno/memory/memory.db",
            ],
        )
        # Largest file the tools may read or write (bytes).
        self.file_max_size_bytes: int = int(data.get("file_max_size_bytes", 2_000_000))
        # Characters of file content shown to the LLM per call.
        self.file_output_chars: int = int(data.get("file_output_chars", 6000))
        # Ask Yes/No before every write, edit, delete, and rename.
        self.file_confirm_writes: bool = bool(data.get("file_confirm_writes", True))
        # Cap for search_files hits (both name and content modes).
        self.file_search_max_results: int = int(data.get("file_search_max_results", 50))
        # Allow OCR (Tesseract) when native text extraction finds nothing.
        self.file_ocr_enabled: bool = bool(data.get("file_ocr_enabled", True))
        # Page/image limits and text cap for the binary readers (PDF, images,
        # Office docs). Text files still use file_max_size_bytes/file_output_chars.
        self.readers_max_pages: int = int(data.get("readers_max_pages", 20))
        self.readers_max_chars: int = int(data.get("readers_max_chars", 20000))

        # ── Git ───────────────────────────────────────────────
        # Master switch for the git tools.
        self.git_enabled: bool = bool(data.get("git_enabled", True))
        # Diff/status output shown to the LLM per call (tail kept when longer).
        self.git_max_diff_chars: int = int(data.get("git_max_diff_chars", 12000))

        # ── Paths ─────────────────────────────────────────────
        self.project_root: Path     = _PROJECT_ROOT
        self.prompts_dir: Path      = _PROJECT_ROOT / "prompts"
        self.models_dir: Path       = _PROJECT_ROOT / "models"
        self.logs_dir: Path         = _PROJECT_ROOT / "logs"

    def __repr__(self) -> str:
        return f"<Settings model={self.model_name} wake_words={self.wake_words}>"


# Module-level singleton — import this everywhere
settings = Settings()
