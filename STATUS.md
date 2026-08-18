# Sopno — Working Status (2026-08-18)

## Project Overview
Sopno (স্বপ্ন / Dream) is an offline AI voice assistant for Linux.
- Branch: `feat@`
- LLM: `qwen3:8b` via Ollama (CPU-only, Ollama 0.31.2)
- STT: faster-whisper `small` model (CPU/int8)
- TTS: gTTS (primary), Coqui (fallback)
- Platform: Wayland / PulseAudio
- Tests: 598 pass (22 skipped from pre-existing `test_memory.py` import error)
- Run tests: `./venv/bin/python -m pytest tests/ -x -q --ignore=tests/core/test_memory.py`

---

## What We Completed

### 1. Schema Refactoring
- `schema.py` (1745L) → 8 files in `schema/` package
- `assistant.py` (779L) → 3 files in `assistant/` package: `__init__.py`, `memory.py`, `confirm.py`
- `researcher.py` (472L) → 2 files: `researcher.py`, `researcher_index.py`

### 2. System Prompt & Tool Routing
- **System prompt rewritten** (`prompts/system.txt`) — lists all 13 capability categories, explicit tool-use instructions: "Do NOT just say 'I will search.' Actually call the tool."
- **`_TOOLISH` regex** expanded — added `source`, `find`, `look`, `internet`, `online`, `poem`, `song`, `video`, `recipe`, `weather` to fix missed tool triggers
- **`get_schema_for(text)`** — intent-based tool routing maps regex patterns to relevant tool groups (7-22 tools per request vs 90). Previously 90 tool schemas overflowed `num_ctx=2048`, Ollama silently dropped tools.
- **`num_ctx` increased from 2048 → 4096** — minimum needed for tool schemas to fit
- **`research` tool removed from web routing** — it's a heavy RAG pipeline that times out on CPU. Only sent when user explicitly says "research" or "in-depth"
- **Poem/poetry/kobita keywords added to `_ROUTING`** — poem queries now get `search_web` + `fetch_url` only

### 3. Search Quality Fixes
- **Bing Accept-Language** — detects Bengali queries (script + topic keywords) and sends `bn-BD,bn;q=0.9` instead of hardcoded `en-US`
- **DuckDuckGo region** — adds `region="bd-bd"` for Bengali queries
- `_is_bengali_query()` helper detects Bengali script (`\u0980-\u09FF`) and topic keywords (`bangla`, `poem`, `romantic`, etc.)

### 4. Dispatcher Fix
- **Only dispatches ≤4 word simple queries** — "search weather" → `search_web`, but "search on internet a romantic Bangla poem" goes to LLM. Previously the dispatcher stripped "search" and passed garbage to `search_web`.

### 5. Bengali STT Improvements
- **Expanded `initial_prompt`** — added common Bengali assistant vocabulary (`খুঁজে বের করো, সার্চ করো, কবিতা, রোমান্টিক, গান`) to bias Whisper
- **Post-transcription corrections** (`filters.py:correct_transcript()`) — fixes Whisper `small` misrecognitions:
  - `bungalow`, `bangalow`, `bengalow`, `Bangalore`, `bengal`, `bangle`, `bongla` → `Bangla`
  - `robust`, `robast` → `romantic`
  - `poam`, `pome` → `poem`
- Runs automatically after Whisper returns, before text reaches LLM

### 6. Always-On Mode Fix
- Added `_wake_word_active()` method — checks both `running` AND `listening_mode == "wake_word"`
- Wake word detector now uses `_wake_word_active` instead of `_voice_active`
- When user toggles to always_on mid-wait, the wake word loop exits immediately

### 7. Barge-In: PyAudio → sounddevice Migration
- Replaced PyAudio with `sounddevice` (`sd.InputStream`) for barge-in mic
- Handles PulseAudio device release/acquire better than PyAudio
- Uses callback-based API with retry (5 attempts, 0.5s backoff steps)
- Added `sd_stream.active` check before each `read()` to prevent race condition

---

## ACTIVE BUG: Segfault After Barge-In

### The Problem
**sounddevice (barge-in) and PyAudio (listener) cannot share the PulseAudio device.** When one closes the mic and the other opens it, PulseAudio takes variable time to release the device. The result:
- ALSA mmap errors: `alsa_snd_pcm_mmap_begin failed`, `PaAlsaStreamComponent_RegisterChannels failed`, `PaAlsaStream_SetUpBuffers failed`
- Followed by **Segmentation fault (core dumped)**

This happens at the **C level in PortAudio** — Python `try/except` CANNOT catch it. The segfault kills the entire process.

### When It Happens
1. **At startup** — after `listener.calibrate()` closes PyAudio mic, barge-in's sounddevice tries to open it → FIXED by skipping barge-in for welcome message (`barge_in=False`)
2. **After barge-in fires** — sounddevice closes mic, listener's PyAudio tries to reopen → PARTIALLY MITIGATED by delays/retries, but segfault still occurs

### What We Tried (All Insufficient)
- `time.sleep(0.8/1.0/1.5)` after calibration — not enough
- `time.sleep(0.5/1.0)` after barge-in stops — not enough
- Listener retry mechanism (4 attempts, 1s/2s/3s backoff) — can't catch C-level segfault
- Listener `_last_barge_close` settle — only works once, then resets
- `sd_stream.active` check — doesn't prevent segfault during concurrent read+close

### Root Cause
PulseAudio requires **exclusive access** to the audio device. When sounddevice closes its stream, PulseAudio doesn't immediately release the device. If PyAudio tries to open it before release completes, PortAudio's C code hits a segfault.

### Possible Solutions (Not Yet Implemented)
1. **Use sounddevice for BOTH listener and barge-in** — eliminates the PyAudio/sounddevice conflict entirely. Would require rewriting `listener.py` to use `sd.InputStream` instead of SpeechRecognition's PyAudio-based `Microphone`.
2. **Use PyAudio for BOTH** — revert barge-in to PyAudio, accept the original segfault risk
3. **Use a shared audio pipeline** — one mic stream that both listener and barge-in read from (we tried this before, caused segfaults from two threads reading same stream)
4. **Use PulseAudio directly** via `pactl`/`pactl` commands to manage device access
5. **Use PipeWire** instead of PulseAudio — better device sharing, but requires user to have PipeWire installed

### Recommendation
**Option 1 (sounddevice for both)** is the cleanest fix. The listener would use `sd.InputStream` to capture audio, and the barge-in would share or use a separate stream. This eliminates the PyAudio dependency for mic capture entirely.

---

## Other Notes

### Config: `config.json` at project root
```json
{
  "stt_model": "small",
  "llm_num_ctx": 4096,
  "llm_think": false,
  "llm_timeout": 60
}
```

### Key Files
- `sopno/config/settings.py` — singleton config loader, all timeout/threshold settings
- `sopno/core/assistant/__init__.py` — main loop, `_process_command()`, `_speak_with_barge_in()`, `_deliver_reply()`
- `sopno/tools/schema/__init__.py` — `get_schema_for(text)`, `_ROUTING` intent→tool mapping
- `sopno/tools/builtins/web/search.py` — `search_web()`, `web_search()`, Bengali query detection
- `sopno/voice/barge.py` — `BargeInMonitor` using sounddevice, `BargeDetector` pure logic
- `sopno/voice/listener.py` — `Listener` class, mic calibration, `listen_for_turn()`
- `sopno/voice/stt/whisper.py` — Whisper transcription, Bengali retry, `correct_transcript()`
- `sopno/voice/stt/filters.py` — `correct_transcript()`, `_WHISPER_CORRECTIONS`, hallucination filters
- `sopno/core/dispatcher.py` — `CommandDispatcher`, 7 hardcoded rules (time, open, search, volume, stats, lock, media)
- `prompts/system.txt` — system prompt with tool-use instructions

### Coding Convention
- One folder = one job, each file does one thing
- All changes committed only when user provides commit message

### Pre-existing Issues
- `test_memory.py` has import error (`ModuleNotFoundError: No module named 'sopno.core.memory'`) — 22 tests skipped
- `audioop` module deprecated in Python 3.11+, removed in Python 3.13 — will break on upgrade

### Search Quality Remaining Issues
- LLM sometimes generates poor search queries (e.g., "bangla poem until" for "find the poem")
- Search results for Bengali poem queries still return English-centric results (Wikipedia about Bengali language, not actual poems)
- Need better query enhancement or use `fetch_url` on known Bengali poetry sites
