# Sopno — Project Assessment & Recommendations

> **Date:** 2026-07-28  
> **Scope:** Implementation reality vs roadmap, quality review, missing capabilities, and next steps  
> **Audience:** Maintainer / contributor planning “full power” Sopno

---

## 1. Executive summary

Sopno has a **strong foundation** for a local bilingual voice companion. Architecture is modular and offline-first. The gap to the full AI-OS vision in `roadmap/features.md` is **breadth of tools**, not core design.

| Goal | Rating |
|------|--------|
| Local bilingual voice assistant | **Good** |
| Jarvis / full computer control | **Early (~5% of roadmap built)** |
| Production-ready on all Linux desktops | **GNOME/Ubuntu-focused; needs hardening** |

The ✓ marks in `roadmap/features.md` Phases 1–6 are **aspirational**, not implemented.

---

## 2. What is implemented today

### 2.1 Voice pipeline

| Component | Status | Notes |
|-----------|--------|-------|
| STT | ✅ | `faster-whisper`, offline, EN/BN |
| TTS | ✅ | Coqui → gTTS fallback, file-based via `ffplay` |
| VAD turn-taking | ✅ | Silero VAD; idle listen until user speaks |
| Mic calibration | ✅ | Ambient noise adjustment |
| Wake word | ⚠️ Built, not wired | `wakeword.py` exists; `assistant.py` uses always-on VAD, not “Hey Sopno” |

### 2.2 Brain & conversation

| Component | Status | Notes |
|-----------|--------|-------|
| Ollama chat | ✅ | Default `qwen3:8b`, `think=False` for CPU speed |
| Tool calling | ✅ | 7 tools; regex heuristic skips tools on pure chat |
| Rule dispatcher | ✅ | Fast path before LLM for common commands |
| Session memory | ✅ | In-conversation history + LLM summarization |
| Persistent memory | ❌ | No SQLite / vector DB across restarts |
| Bilingual replies | ✅ | Explicit EN/BN switch + script detection |

### 2.3 Tools (7 registered)

| Tool | What it does |
|------|----------------|
| `get_current_time` | Date/time/day |
| `open_application` | 8 apps (chrome, firefox, terminal, vscode, etc.) |
| `search_web` | Opens Google in browser — **does not fetch results** |
| `control_volume` | up / down / toggle via `amixer` |
| `get_system_stats` | CPU, RAM, battery via `psutil` |
| `lock_screen` | GNOME screensaver or `loginctl` fallback |
| `play_media_control` | play / pause / next / previous via `playerctl` |

### 2.4 UI & deployment

| Component | Status |
|-----------|--------|
| PyQt5 HUD | ✅ Glassmorphic overlay, voice/text modes, tray |
| CLI mode | ✅ `--cli` fallback if PyQt5 missing |
| HUD hot reload | ✅ `--reload` for dev |
| systemd daemon | ✅ `scripts/install_daemon.sh` |
| Unit tests | ✅ `tests/` (tools, assistant, STT, TTS) |

### 2.5 Current pipeline

```
Mic → VAD → faster-whisper → dispatcher OR Ollama (+ tools) → TTS → HUD/CLI
```

---

## 3. Built but not fully connected

1. **Wake word** — Documented and coded (`sherpa-onnx` + fallback), but main loop uses continuous listening. ROADMAP marks it complete; runtime behavior differs.
2. **Web search** — Opens browser tab only; no Playwright extraction or answer synthesis.
3. **Tool calling heuristic** — `_TOOLISH` regex may miss valid action phrases or attach tools unnecessarily.

---

## 4. Roadmap items not yet built

From `roadmap/features.md`, these major areas have **no implementation**:

- File system read/write/search/monitor
- Terminal / shell execution
- Git, code editing, project understanding, test runners
- Browser automation (Playwright), HTTP/API tools
- RAG / semantic memory / local knowledge index
- Task planner / multi-step agent loop
- Plugin system, MCP support
- Permission / security manager
- Desktop control (mouse, keyboard, clipboard, window management)
- Scheduler, reminders, automation rules
- Email, calendar, notes, databases, Docker/K8s
- Multi-agent (planner / coder / researcher)
- Vision / OCR, streaming (turn-based) barge-in → done: local energy-based barge-in (`sopno/voice/barge.py`)
- REST API, mobile companion

---

## 5. Code quality assessment

### Strengths

- **Modular monolith** — `core`, `voice`, `llm`, `tools`, `ui` evolve independently
- **Offline-first** — STT, TTS, LLM local; cloud only as fallback
- **Performance-aware** — dispatcher first, conditional tools, disabled thinking mode
- **Bilingual depth** — STT hints, TTS routing, language switch commands, Bangla regex in tool heuristic
- **Graceful degradation** — HUD→CLI, Coqui→gTTS, lock-screen fallbacks
- **Clear extension points** — `registry.py`, `schema.py`, `dispatcher.py`

### Weaknesses / risks

| Issue | Impact |
|-------|--------|
| GNOME-specific commands | Breaks on KDE, minimal WM, some Arch setups |
| Blocking pipeline | Barge-in added (energy-based) — full turn-based; still sequential listen → think → speak |
| TTS file-based | Temp wav/mp3 → `ffplay`; higher latency than streaming |
| No permission gates | OS actions run without “ask first” |
| Session-only memory | Forgets user after restart |
| Doc drift | README mentions Gemma3 / wake-word flow; code uses Qwen3 + VAD |
| Tests need venv | `requirements.txt` must be installed to run suite |

---

## 6. RAM & dependencies (install vs run)

**Installing packages uses disk, not RAM.** RAM is used only when code is imported or a service runs.

| Situation | Uses RAM? |
|-----------|-----------|
| Package installed, never imported | No |
| Imported at startup (PyQt5, numpy, speech libs) | Yes |
| Tool used on demand (Whisper, browser) | Yes, while active |
| Separate services (Ollama, Postgres, Docker) | Yes, while running |
| AI models | Yes, when loaded (Qwen via Ollama is usually largest) |

Sopno’s modular tool design means installing many packages does **not** multiply RAM unless you load and run them together.

---

## 7. Capabilities missing from the roadmap

`roadmap/features.md` is ~90–95% complete as a vision doc. For maximum power, consider adding:

### 7.1 Safety & reliability infrastructure

- Action **undo / rollback** (git stash before edits, revert file changes)
- **Sandboxed execution** (Firejail, bubblewrap, containers for untrusted code)
- **Resource quotas** (CPU, RAM, disk, time per agent task)
- **Checkpoint & resume** for long tasks
- **Secrets vault** (Linux keyring, `pass`, Bitwarden CLI — managed access, not theft)

### 7.2 Deeper Linux desktop integration

- **AT-SPI accessibility tree** — reliable UI automation vs raw coordinates
- **Wayland vs X11** handling for window/desktop control
- **Unified launcher** — Spotlight-style search (apps, files, commands)
- **PipeWire routing** — mic/output selection beyond volume

### 7.3 Developer pro layer

- **LSP / tree-sitter** — go-to-def, rename, refs
- **CI/CD** — GitHub Actions, GitLab CI, test-on-push
- **IaC** — Terraform, Pulumi, Ansible
- **Security scanning** — `pip-audit`, npm audit, SBOM, license checks
- **Sandboxed REPL / Jupyter** for data work

### 7.4 Brain & model ops

- **Model routing** — small model for routing, large for coding, vision only when needed
- **GPU backend control** — CUDA / ROCm / Vulkan, quantization profiles
- **Local fine-tuning / LoRA**
- **Eval regression suite** — benchmark assistant after changes

### 7.5 Platform surface

- **Local HTTP / WebSocket API**
- **Webhooks & event bus**
- **Workflow engine** (n8n / Temporal-style flows beyond simple if→then)

### 7.6 Workflows

- Meeting mode (record → transcribe → summarize → actions)
- Contacts / CRM-lite
- Offline translation tool
- Backup & snapshots before risky operations

### 7.7 Hybrid (local-first)

- Cloud CLI (`aws`, `gcloud`, `az`) behind strict permissions
- Encrypted sync of memory/config (Syncthing-style)

---

## 8. Prioritized next steps

### Phase A — Harden what exists (highest ROI)

1. Wire **wake word** into `assistant.py` (optional mode: wake word vs always-on)
2. Fix **doc/code drift** (README model name, wake-word diagram vs VAD loop)
3. Add **permission prompts** for lock, volume, app launch
4. **Streaming or lower-latency TTS** (Piper, edge-tts streaming, or chunked playback)
5. ~~**Barge-in** — stop TTS when user speaks~~ ✅ done (energy-based, tunable in `config.json`)

### Phase B — Core agent power

6. **Terminal tool** (sandboxed bash with timeout + output capture)
7. **File tools** (read, write, search, list — with path allowlist)
8. **Git basics** (status, diff, commit with confirmation)
9. **Persistent memory** (SQLite + optional embeddings)

### Phase C — Platform

10. **Plugin registry** + dynamic tool loading
11. **MCP client** for external tools
12. **Local REST API** for scripts and mobile companion

### Phase D — Roadmap breadth

13. Browser automation, RAG, multi-agent, automation rules — per `roadmap/features.md` phases

---

## 9. Documentation layout (this repo)

Docs mirror the codebase:

```
doc/
├── README.md                      ← index
├── getting-started/
│   ├── installation.md
│   └── user-guide.md
├── architecture/
│   ├── overview.md
│   ├── observations.md
│   └── project-assessment.md      ← this file
├── roadmap/
│   ├── features.md
│   └── status.md
└── modules/
    └── voice/
        └── tts.md
```

---

## 10. Related docs

- [overview.md](overview.md) — module boundaries and data flow
- [observations.md](observations.md) — stack review (HUD, PyQt, Pipecat, etc.)
- [../roadmap/features.md](../roadmap/features.md) — full vision
- [../roadmap/status.md](../roadmap/status.md) — completed milestones
- [../getting-started/user-guide.md](../getting-started/user-guide.md) — end-user guide

---

*Update this file when major capabilities ship or when the implementation gap closes significantly.*
