# 🏗️ Sopno — Architecture & Folder Structure

> **Design Philosophy:** *Modular Monolith* — one repo, zero confusion.  
> Every folder has **one job**. Anyone reading the code instantly knows **what** a file does,  
> **why** it exists, and **where** to add something new.

---

## 📋 Why We Are Restructuring

The original project kept all logic in a single flat file (`sopno.py` with 432 lines).
This worked as a prototype, but causes real problems as the project grows:

| Problem (Old) | Solution (New) |
|---|---|
| TTS, STT, LLM, tools all in one file | Each concern lives in its own module |
| Hard to swap TTS/STT engine | Every engine is isolated behind a clean interface |
| Test files scattered at root | All tests in `tests/` |
| Prompts buried inside code strings | Plain text files in `prompts/` |
| Config values hardcoded | Loaded from `config.json` via a Settings class |
| Scripts mixed with source code | Moved to `scripts/` |

---

## 📁 Full Folder Structure

```text
sopno/
│
├── 📄 main.py                          ← START HERE. Boots the entire assistant.
├── 📄 requirements.txt                 ← All Python dependencies
├── 📄 .env                             ← Secrets & local overrides (never commit)
├── 📄 .env.example                     ← Template showing required env variables
├── 📄 .gitignore
├── 📄 README.md                        ← Project overview & quick-start guide
│
├── 📁 sopno/                           ← Core application package
│   ├── 📄 __init__.py
│   │
│   ├── 📁 core/                        ← THE BRAIN: orchestrates the pipeline
│   │   ├── 📄 __init__.py
│   │   ├── 📄 assistant.py             ← Main loop: wakeword → STT → LLM → TTS
│   │   ├── 📄 context.py               ← Conversation history & memory management
│   │   └── 📄 dispatcher.py            ← Routes an intent to the right tool
│   │
│   ├── 📁 voice/                       ← EVERYTHING AUDIO
│   │   ├── 📄 __init__.py
│   │   ├── 📄 listener.py              ← Microphone capture & ambient noise calibration
│   │   ├── 📄 wakeword.py              ← Wake-word engine (sherpa-onnx / fallback)
│   │   ├── 📁 stt/                     ← Speech-to-Text package (was stt.py)
│   │   │   ├── 📄 __init__.py          ← Public API: transcribe()
│   │   │   ├── 📄 whisper.py           ← faster-whisper model + transcription
│   │   │   ├── 📄 filters.py           ← Hallucination / babble / script checks
│   │   │   ├── 📄 scoring.py           ← Transcript scoring & audio sanity
│   │   │   └── 📄 google.py            ← Online Google fallback engine
│   │   └── 📄 tts.py                   ← Text-to-Speech (Coqui TTS / gTTS fallback)
│   │   └── 📄 barge.py                 ← Barge-in: stop TTS when user starts talking
│   │
│   ├── 📁 llm/                         ← THE AI MODEL LAYER
│   │   ├── 📄 __init__.py
│   │   ├── 📄 client.py                ← Ollama wrapper: sends prompt, streams reply
│   │   └── 📄 summarizer.py            ← Compresses long conversation history
│   │
│   ├── 📁 tools/                       ← SKILLS: what Sopno can DO
│   │   ├── 📄 __init__.py              ← Public API: execute_tool(), TOOLS_SCHEMA
│   │   ├── 📄 registry.py              ← Maps tool names → functions (the dispatcher table)
│   │   ├── 📄 schema.py                ← JSON schemas for LLM tool-calling API
│   │   └── 📁 builtins/                ← The skills themselves (one file each)
│   │       ├── 📄 system.py            ← OS tools: volume, lock screen, app launcher
│   │       ├── 📄 search.py            ← Web search tool
│   │       ├── 📄 datetime_tool.py     ← Date/time queries
│   │       └── 📄 media.py             ← Media playback controls
│   │
│   ├── 📁 ui/                          ← EVERYTHING VISIBLE
│   │   ├── 📄 __init__.py
│   │   ├── 📁 hud/                     ← PyQt5 glassmorphic HUD (was hud.py)
│   │   │   ├── 📄 __init__.py          ← Public API: run_hud()
│   │   │   ├── 📄 app.py               ← run_hud() + hot reload
│   │   │   ├── 📄 window.py            ← SopnoHUDWindow layout + wiring
│   │   │   ├── 📄 worker.py            ← AssistantWorker signal bridge
│   │   │   ├── 📁 behaviors/           ← Mixins: chrome, responsive, resizing,
│   │   │   │                            status, tray
│   │   │   ├── 📁 widgets/             ← Reusable widgets: robot, chat, mode_toggle
│   │   │   └── 📁 visuals/             ← Look & feel: theme, icons
│   │   └── 📄 cli.py                   ← Terminal-mode interface (no GUI)
│   │
│   └── 📁 config/                      ← SETTINGS & PROMPTS
│       ├── 📄 __init__.py
│       ├── 📄 settings.py              ← Loads config.json into one Settings object
│       └── 📄 prompts.py               ← Reads prompt text from prompts/*.txt
│
├── 📁 prompts/                         ← PROMPT TEMPLATES (edit without touching code)
│   ├── 📄 system.txt                   ← Sopno's main personality & rules
│   └── 📄 summarize.txt                ← Template for history summarization
│
├── 📁 models/                          ← Local AI model files (gitignored)
│   ├── 📁 wakeword/                    ← sherpa-onnx keyword spotter files
│   └── 📁 whisper/                     ← faster-whisper model cache
│
├── 📁 tests/                           ← ALL TESTS (one file per module)
│   ├── 📄 __init__.py
│   ├── 📄 test_stt.py
│   ├── 📄 test_tts.py
│   ├── 📄 test_tools.py
│   └── 📄 test_assistant.py
│
├── 📁 scripts/                         ← SETUP & DEPLOYMENT
│   ├── 📄 install_daemon.sh            ← Register sopno as a systemd user service
│   └── 📄 setup.sh                     ← One-shot: venv + deps + model download
│
├── 📁 logs/                            ← Runtime logs (gitignored)
│   └── 📄 sopno.log
│
└── 📁 doc/                             ← DOCUMENTATION (see doc/README.md)
    ├── 📁 getting-started/             ← installation, user guide
    ├── 📁 architecture/                ← overview, observations, assessment
    ├── 📁 roadmap/                     ← features vision, status tracker
    └── 📁 modules/                     ← per-package docs (voice/tts, …)
```

---

## 🔄 Data Flow / Pipeline

```
User speaks
    │
    ▼
sopno/voice/listener.py        ← Captures mic audio, calibrates for noise
    │
    ▼
sopno/voice/wakeword.py        ← Detects "Sopno" / "Dream" wake word
    │  (wakeword triggered)
    ▼
sopno/voice/stt/__init__.py    ← Offline Whisper transcription → text
    │
    ▼
sopno/core/dispatcher.py       ← Is this a TOOL call or a CHAT message?
    │
    ├──► sopno/tools/...        ← TOOL: run system command, web search, etc.
    │         │
    │         └──► sopno/voice/tts.py  ← Speak the tool result
    │
    └──► sopno/llm/client.py   ← CHAT: stream reply from Ollama (qwen3:8b)
              │
              ▼
         sopno/core/context.py ← Save to history; summarize if too long
              │
              ▼
         sopno/voice/tts.py    ← Coqui TTS synthesizes reply → audio
              │
              ▼
         sopno/ui/hud/window.py  ← Shows text on glassmorphic HUD
              │
              ▼
         🔊 User hears the response
```

---

## 🧩 One Folder = One Job (Quick Reference)

| Folder | Job | Never put here |
|--------|-----|----------------|
| `sopno/core/` | Orchestration & routing | Audio code, LLM API calls |
| `sopno/voice/` | Mic, wakeword, STT, TTS | Business logic, tool code |
| `sopno/llm/` | Ollama client, summarizer | Audio, UI, tools |
| `sopno/tools/` | Skills Sopno can perform | Audio, LLM calls |
| `sopno/ui/` | HUD overlay, CLI display | Any audio or AI logic |
| `sopno/config/` | Settings loader | Runtime logic |
| `prompts/` | Plain-text prompt files | Python code |
| `tests/` | Tests only | Production code |
| `scripts/` | Shell setup/deploy scripts | Python source |

---

## ♻️ Swap Any Piece Without Breaking the Rest

```
Want to change TTS engine?      → Only edit  sopno/voice/tts.py
Want to change LLM model?       → Only edit  sopno/llm/client.py
Want to add a new skill?        → Only add   sopno/tools/builtins/your_tool.py
                                   and register it in sopno/tools/registry.py
Want to change Sopno's persona? → Only edit  prompts/system.txt
Want to change UI layout?       → Only edit  sopno/ui/hud/window.py
```

---

## 📦 Migration Map (Old → New)

| Old file | New location |
|---|---|
| `sopno.py` | `sopno/core/assistant.py` + `sopno/core/dispatcher.py` + `main.py` |
| `gui.py` | `sopno/ui/hud/` (was `sopno/ui/hud.py`) |
| `tools.py` | `sopno/tools/builtins/` (skills) + `sopno/tools/registry.py` + `sopno/tools/schema.py` |
| `tools_schema.py` | `sopno/tools/schema.py` |
| `config.json` | root `config.json` (read via `sopno/config/settings.py`) |
| `test_*.py` (root) | `tests/test_*.py` |
| `install_daemon.sh` | `scripts/install_daemon.sh` |

---

## 🚀 Implementation Phases

| Phase | What | Status |
|-------|------|--------|
| **1** | Create folder skeleton + `__init__.py` files | ✅ Completed |
| **2** | `sopno/config/settings.py` — centralized config | ✅ Completed |
| **3** | `prompts/system.txt` + `prompts/summarize.txt` | ✅ Completed |
| **4** | `sopno/voice/tts.py` — offline TTS with fallback | ✅ Completed |
| **5** | `sopno/voice/stt.py` — Whisper STT with fallback | ✅ Completed |
| **6** | `sopno/voice/listener.py` — mic capture | ✅ Completed |
| **7** | `sopno/llm/client.py` + `sopno/llm/summarizer.py` | ✅ Completed |
| **8** | `sopno/tools/` — all tools + registry + schema | ✅ Completed |
| **9** | `sopno/core/dispatcher.py` + `sopno/core/context.py` | ✅ Completed |
| **10** | `sopno/core/assistant.py` — main loop | ✅ Completed |
| **11** | `main.py` — clean entry point | ✅ Completed |
| **12** | `sopno/ui/hud.py` — move gui.py | ✅ Completed |
| **13** | `tests/` — move & update test files | ✅ Completed |
| **14** | `scripts/` — move shell scripts | ✅ Completed |
| **15** | `requirements.txt` — generate from venv | ✅ Completed |
| **16** | Git commit & push final structure | ✅ Completed |

---

*Document created: July 21, 2026*  
*Last updated: July 21, 2026*  
*Author: Antigravity AI coding assistant*
