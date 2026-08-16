# 🗺️ SOPNO Assistant — Implementation Roadmap & Status Tracker

This document tracks the incremental progress of transforming **Sopno (স্বপ্ন)** from a simple terminal script into a fully offline, background-running, Jarvis-like AI voice assistant.

---

## 📊 Status Summary
* **Current Phase:** Upgrading Core Foundations
* **Latest Completed Upgrade:** File & Folder Access (Permission-Gated)

---

## 🛠️ Feature Checklist

### 1. Voice Output (Text-to-Speech) — **[COMPLETED]**
* [x] **High-quality Neural Voices:** Upgraded from standard robotic `gTTS` to **offline, high-fidelity Coqui TTS** (the open‑source continuation of Mozilla‑TTS).  
* [x] **Bilingual Language Routing:** Automatically selects the appropriate voice (Bengali or English) from the Coqui model.  
* [x] **Offline‑first:** No network required; fallback to Google `gTTS` remains optional for rare cases.
* [x] **HUD Sync:** Synchronized audio synthesis so both CLI and PyQt5 HUD GUI benefit automatically.

### 2. Wake Word Detection — **[COMPLETED]**
* [x] **Local Offline Activation:** Integrated `sherpa-onnx` Keyword Spotter with a pre-trained Gigaspeech Zipformer model to run lightweight, offline wake-word processing for custom keywords.
* [x] **Dynamic Config Integration:** Automatically loads custom wake words from `config.json`, tokenizes them dynamically using the model's vocabulary, and applies boosting scores at runtime.
* [x] **No Keys Required:** Completely free, open-source, and local, eliminating the need for Picovoice API access keys or cloud accounts.
* [x] **Smart Fallback:** Implemented a continuous, auto-calibrating SpeechRecognition/Google STT wake-word listener if `sherpa-onnx` model files are missing, ensuring 100% out-of-the-box operation.
* [x] **Wired into Main Loop:** Wake word detection is now integrated into `assistant.py` with configurable `listening_mode` ("wake_word" or "always_on"). HUD and CLI reflect the active mode.

### 3. Voice Input (Speech-to-Text) — **[COMPLETED]**
* [x] **Local Offline STT:** Migrated from online Google SpeechRecognition to fully offline, high-speed `faster-whisper`.
* [x] **Bilingual Language Recognition:** Natively detects and transcribes both English and Bangla offline with near-zero latency using the CTranslate2 model.
* [x] **Graceful Fallback:** Implemented automatic online Google STT fallback to handle any temporary CPU/Whisper-loading issues, ensuring 100% voice engine reliability.

### 4. Background Daemon (Always Running) — **[COMPLETED]**
* [x] **systemd User Service:** Enabled Sopno to run seamlessly as a background user daemon (`systemctl --user`).
* [x] **Autostart Configuration:** Autostart .desktop entry created; HUD launches on login.

### 5. OS Control & Tools — **[COMPLETED]**
* [x] **Core Functions:** Time/date, open apps, volume adjust, media controls, system stats, lock screen.
* [x] **CLI Sync:** Tool calling works on the terminal interface (`sopno.py`) as well as the GUI.

### 6. Long-Term Memory (SQLite) — **[PARTIALLY COMPLETED]**
* [x] **SQLite Memory Store:** Persistent long-term memory in `sopno/memory/store.py` (schema, CRUD, FTS5 search) — survives restarts.
* [x] **"Remember" Commands:** "remember that X", "forget X", "what do you remember?" in English and Bangla.
* [x] **Context Injection:** Relevant memories injected into the LLM prompt with a token-budget guard.
* [ ] **Semantic Recall (future):** `sqlite-vec` embeddings for automatic similarity-based recall.
* Design spec: [modules/memory/memory.md](../modules/memory/memory.md)

### 7. Terminal Access (Persistent Shell) — **[COMPLETED]**
* [x] **Persistent Shell Session:** One shared `cleat` PTY shell per Sopno process; `cd`, `export`, and background jobs persist between calls.
* [x] **Structured Output + Real Exit Codes:** OSC 133 marks give Sopno clean stdout and genuine exit codes (no brittle prompt parsing).
* [x] **Interactive Support:** `terminal_send` types into REPLs, installers, and password prompts (`ctrl-c`/`ctrl-d`/`ctrl-z`); `terminal_status` polls long-runners without interfering.
* [x] **Safety Blocklist:** Destructive/irreversible patterns (`rm -rf /`, `mkfs`/`fdisk`, shutdown/reboot, fork bombs, raw disk writes, `curl|sh`) are blocked; fully configurable via `terminal_blocklist` in `config.json`.
* [x] **Graceful Shutdown:** The shared shell session closes when Sopno stops.

### 8. Process / Service / Log / Cron Management — **[COMPLETED]**
* [x] **Processes:** `list_processes` (top-by-CPU with keyword filter) and `kill_process` (by PID or name, with protected targets).
* [x] **Services:** `manage_service` — start/stop/restart/status/enable/disable/reload via `systemctl --user` (no sudo needed).
* [x] **Logs:** `read_logs` — user/system journal (optionally per unit) or a raw `tail` of an absolute log file path.
* [x] **Cron:** `manage_cron` — list / add / remove crontab jobs non-interactively; blocked or malformed commands are refused.
* [x] **Safety:** everything executes through the shared terminal session, so the `terminal_blocklist` and Sopno's privileges apply uniformly.

### 9. File & Folder Access (Permission-Gated) — **[COMPLETED]**
* [x] **Read Tools:** `read_file` (whole file or head/tail lines, size + output capped) and `list_directory` (sorted entries with type + size).
* [x] **Write Tools:** `write_file` (create/overwrite), `edit_file` (exact-string replace with a read-before-edit invariant), `delete_file` (single files only), `rename_file` (never overwrites).
* [x] **Allowlist Roots, Deny-by-Default:** reads allowed only inside `file_allowed_read` and writes only inside `file_allowed_write` (default: the project root) — everything else is refused.
* [x] **Secret Deny-List:** `.env`, `.git`, `.ssh`, `*.pem`/`*.key`, `credentials.json`, Sopno's own `config.json` and `memory.db` are off-limits even inside the roots.
* [x] **Symlink-Safe Paths:** every path is `resolve()`d before checking, so `..`/symlinks can't escape the roots.
* [x] **HUD/CLI Confirmation:** every write/edit/delete/rename parks a pending action and asks the user Yes/No (spoken in voice mode, typed in text mode); `file_confirm_writes` can disable the prompt.

---

## 📓 Technical Progress Log

### [August 16, 2026] — Step 12: File & Folder Access (Permission-Gated)
* **Added Files:** `sopno/tools/builtins/files.py`, `tests/test_files.py`
* **Modified Files:** `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/config/settings.py`, `config.json`, `sopno/core/assistant.py`, `sopno/tools/builtins/__init__.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now read and write files and folders — but only where the user grants it. Every operation passes the `_authorize` gate: master switch (`file_enabled`), absolute symlink-resolved path, a secret deny-list (`.env`, `.git`, `.ssh`, `*.pem`/`*.key`, `credentials.json`, `config.json`, `sopno/memory/memory.db`, …), then allowlist roots (`file_allowed_read` / `file_allowed_write`, default project root). Reads are free inside the roots; `write_file` / `edit_file` / `delete_file` / `rename_file` park a pending action and ask the user for a Yes/No confirmation (spoken in voice mode, typed in text mode), resolved in `assistant.py` via `pending_action()` / `resolve_pending()`. `edit_file` enforces a read-before-edit invariant and re-checks uniqueness before writing. Content is capped by `file_max_size_bytes` / `file_output_chars`.
### [August 16, 2026] — Step 11: Process / Service / Log / Cron Management
* **Added Files:** `sopno/tools/builtins/manage.py`, `tests/test_manage.py`
* **Modified Files:** `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/core/assistant.py`, `sopno/tools/builtins/terminal.py`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now manage the system it runs on, all executed through the persistent terminal session (so the safety blocklist applies everywhere): `list_processes` / `kill_process` (kernel, init, systemd, and Sopno's own shell are protected), `manage_service` via `systemctl --user` (start/stop/restart/status/enable/disable/reload), `read_logs` from the user/system journal or any log file, and `manage_cron` (list/add/remove, with schedule validation and blocked-command refusal). `terminal.py` gained `_run_command_raw` (structured stdout + exit code for higher-level tools) and `_shell_pid` (self-session kill guard).
### [August 16, 2026] — Step 10: Terminal Access (Persistent Shell)
* **Added Files:** `sopno/tools/builtins/terminal.py`, `tests/test_terminal.py`
* **Modified Files:** `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/config/settings.py`, `config.json`, `sopno/core/assistant.py`, `requirements.txt`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now execute real shell commands through a persistent, structured PTY session (`cleat`): `run_terminal` runs commands with real exit codes, `terminal_send` types into interactive programs, and `terminal_status` polls long-running jobs without interfering. `cd`/`export`/background jobs persist across calls. Destructive or irreversible commands are blocked by a configurable safety blocklist (`terminal_blocklist`), and the session closes cleanly on shutdown.
### [August 14, 2026] — Step 9: Barge-In (Interruptible Voice)
* **Added Files:** `sopno/voice/barge.py`, `tests/test_barge.py`
* **Modified Files:** `sopno/voice/tts.py`, `sopno/core/assistant.py`, `sopno/config/settings.py`, `config.json`, `tests/test_tts.py`, `doc/CODEBASE.md`
* **Impact:** Sopno now stops speaking the moment you start talking and returns to listening (no settle pause). `BargeInMonitor` measures Sopno's own voice for 0.4s, then flags an interrupt when the user speaks above `own_voice × 1.7 + 30` for 180ms — all tunable in `config.json`. Graceful degradation if PyAudio/mic is missing.

### [August 14, 2026] — Step 7: Clean Folder Organization (HUD + Tools)
* **Modified Files:** `sopno/ui/hud/` (reorganized), `sopno/tools/` (reorganized)
* **Impact:** HUD package split into `behaviors/` (5 mixins), `widgets/` (robot, chat, mode_toggle), `visuals/` (theme, icons); `run.py` renamed `app.py`; hot-reload watcher now uses `rglob("*.py")`. Tools split into a framework (`registry.py` + `schema.py` stay top-level) + `tools/builtins/` for skills. Public APIs preserved (`sopno.ui.hud.run_hud`, `sopno.tools.execute_tool`).

### [July 20, 2026] — Finalization of Offline TTS & Daemon
* **Modified Files:** `sopno.py`, `install_daemon.sh`, `doc/ROADMAP_STATUS.md`
* **Added Files:** `.config/autostart/sopno_hud.desktop`
* **Impact:** Fully offline TTS via Coqui TTS, systemd user service enabled, autostart configured, CLI sync completed.
* **Added Files:** `test_edge_tts.py`
* **Impact:** Drastically reduced TTS response latency (~2s down to ~400ms) and made the voice incredibly natural, human-like, and expressive.

### [July 14, 2026] — Step 2: Integrated Dual-Mode Wake-Word Engine
* **Modified Files:** `gui.py`, `doc/ROADMAP_STATUS.md`
* **Impact:** Integrated Picovoice Porcupine for offline, near-zero CPU wake-word detection with an automated fallback to continuous SpeechRecognition.

### [July 14, 2026] — Step 3: Implemented Offline Faster Whisper STT
* **Modified Files:** `sopno.py`, `doc/ROADMAP_STATUS.md`
* **Added Files:** `test_whisper.py`
* **Impact:** Fully offline voice recognition with native bilingual support. Eliminates internet latency for voice transcribing.

### [July 17, 2026] — Step 4: Replaced Picovoice with sherpa-onnx KWS
* **Modified Files:** `gui.py`, `config.json`, `doc/ROADMAP_STATUS.md`
* **Impact:** Upgraded wake-word detection to a completely free, local, open-source model using `sherpa-onnx`. Removed requirements for Picovoice access keys and commercial licenses, allowing unlimited custom local wake words (e.g., "Sopno", "Dream").

### [July 28, 2026] — Step 5: Wired Wake Word into Main Loop
* **Modified Files:** `assistant.py`, `config.json`, `settings.py`, `hud.py`, `cli.py`, `tests/test_wakeword.py`, `doc/roadmap/status.md`
* **Impact:** Wake word detection is now fully integrated into the assistant pipeline. Added `listening_mode` config option ("wake_word" or "always_on") to choose between gated wake-word activation and continuous VAD listening. HUD shows "Say 'Sopno'…" in wake_word standby; CLI banner reflects active mode. Added unit tests for `WakeWordDetector`.

### [August 13, 2026] — Step 6: SQLite Long-Term Memory
* **Added Files:** `sopno/memory/store.py`, `sopno/memory/__init__.py`, `tests/test_memory.py`, `doc/modules/memory/memory.md`
* **Modified Files:** `sopno/core/assistant.py`, `sopno/core/context.py`, `sopno/config/settings.py`, `config.json`, `.gitignore`, `doc/README.md`, `doc/roadmap/status.md`
* **Impact:** Sopno now has human-like long-term memory. Facts are persisted to a SQLite DB (FTS5 search index, importance/recency ranking, soft-delete) and survive restarts. New bilingual commands: "remember that X" / "মনে রাখো X", "forget X" / "ভুলে যাও X", "what do you remember?" / "কী মনে আছে", plus "forget everything". Memories are injected into the LLM prompt via `context.py` with a token-budget guard (`memory_max_tokens`).

