# Sopno — Architecture Observations & Upgrade Recommendations

> **Date:** 2026-07-26  
> **Scope:** Stack review of the current local voice assistant (HUD + Ollama + wake-word pipeline)  
> **Goal:** Decide what to keep, what to harden, and what to upgrade later — without a pointless rewrite.

---

## 1. Executive verdict

**Sopno’s current architecture is a strong fit for a local desktop companion.**

You already have the right product shape:

- Always-on floating HUD (PyQt)
- Local LLM brain (Ollama)
- Offline-capable wake word (sherpa-onnx)
- Clear pipeline: **Standby → Listening → Thinking → Speaking**
- Voice and text interaction modes

This matches how real companion products work (floating orb / panel + voice session + transcript), not a random chatbot demo.

**Do not rewrite from scratch.**  
The highest ROI is hardening the voice loop, STT/TTS reliability, tool-calling fallbacks, and UI polish — not swapping frameworks for novelty.

---

## 2. Current stack (as observed)

| Layer | Current choice | Role |
|--------|----------------|------|
| Entry | `main.py` (`--hud` / `--cli` / `--reload`) | Boot + mode routing |
| UI | PyQt5 frameless HUD (`sopno/ui/hud.py`) | Always-on-top companion panel |
| Orchestrator | `SopnoAssistant` (`sopno/core/assistant.py`) | Pipeline + callbacks to UI |
| Wake word | sherpa-onnx (+ SpeechRecognition fallback) | Hands-free activation |
| STT | faster-whisper / SpeechRecognition path | Speech → text |
| LLM | Ollama (`qwen3:8b` via `config.json`) | Reasoning + optional tools |
| Tools | `TOOLS_SCHEMA` + dispatcher/registry | System actions |
| TTS | gTTS / edge-tts / Coqui path | Text → speech |
| Config | `config.json` + `settings.py` | Model, wake words, HUD prefs |

### Strengths

1. **Modular monolith** — voice, LLM, tools, and UI are separated enough to evolve independently.
2. **Local-first** — Ollama keeps data and latency under your control.
3. **Wake-word first** — better UX and privacy than always streaming mic audio to the cloud.
4. **HUD + CLI** — same brain, two surfaces; good product discipline.
5. **Hot reload (`--reload`)** — useful for UI iteration without full restarts.
6. **Model switch to `qwen3:8b`** — correct move after `gemma3:4b` failed on tool calling.

### Weaknesses / risks

1. **Tool calling is hard-required** in the LLM path. Models without tools return HTTP 400 and the user sees a failure instead of a normal reply.
2. **Pipeline is mostly blocking** — listen / think / speak are sequential; barge-in (interrupt while speaking) is limited.
3. **TTS often file-based** — generate audio → play → continue. Fine for v1; weaker for “live” conversation feel.
4. **PyQt5 is legacy** — still works, but PySide6 is the actively maintained Qt-for-Python path.
5. **UI is custom-painted** — flexible and unique, but more maintenance than a web-composed HUD if design velocity becomes the bottleneck.
6. **Wake-word ↔ text mode switching** depends on cooperative loops; robust cancellation and state machines will matter as features grow.

---

## 3. Is this the “best” way?

### Best for Sopno’s goal (local Linux companion)

**Yes — with targeted upgrades.**

For a product like:

> “A floating assistant on my PC that listens when I say Sopno, talks back, and can also take typed input”

…the current approach is industry-aligned:

- Floating panel / companion orb pattern (EnConvo-style, Gemini Live floating UI, Copilot popup)
- Circular icon controls for voice/text (ChatGPT composer pattern)
- Local model runtime (Ollama)

### Not the best if your goal changes

| If you want… | Better direction |
|--------------|------------------|
| Continuous interruptible talk like phone voice mode | Streaming voice agent frameworks (Pipecat, LiveKit Agents) |
| Beautiful cross-platform UI very fast | Web UI in Tauri / Electron / pywebview |
| Cloud-only SaaS assistant | Different product; keep local stack only as optional edge client |
| Mobile-first | Native or Flutter/React Native — current HUD is desktop-native |

---

## 4. Library & technology recommendations

### 4.1 Keep (core bets)

| Keep | Why |
|------|-----|
| **Ollama** | Best local DX for swapping models (`qwen3:8b`, etc.) |
| **sherpa-onnx wake word** | Low-latency offline KWS |
| **faster-whisper** | Strong offline STT baseline |
| **Modular `sopno/` package** | Clean place to grow features |
| **Frameless always-on-top HUD** | Correct UX for a companion |

### 4.2 Upgrade when ready (high value)

| Area | Recommendation | Priority | Notes |
|------|----------------|----------|-------|
| Qt binding | **PyQt5 → PySide6** | Medium | Same Qt ideas, better long-term support |
| Tool calling | **Fallback to plain `ollama.chat` without `tools=`** | **High** | Prevents hard failures on non-tool models |
| TTS | Prefer **Piper** / **Kokoro** / solid **edge-tts** path | High | Lower latency, less online dependence than gTTS |
| STT | Standardize on **faster-whisper** (or whisper.cpp) | Medium | One reliable offline path |
| Interrupts | Stop TTS + cancel listen on new speech / UI action | **High** | Feels “alive” |
| Process longevity | systemd user service / autostart (you already have scripts) | Medium | Real “always available” product |
| Observability | Structured logs + simple metrics (latency STT/LLM/TTS) | Medium | Debug production pain |

### 4.3 Consider later (only if product needs it)

| Option | What it gives you | Cost |
|--------|-------------------|------|
| **Pipecat** | Streaming, barge-in, voice-agent graphs | Learning curve; more moving parts |
| **LiveKit Agents** | Realtime sessions, scalable voice infra | Heavier; may be overkill for single-PC |
| **Tauri + web UI** | Modern design systems, CSS motion | Split stack (Python brain + web shell) |
| **pywebview / Qt WebEngine** | Keep Python, design HUD in HTML/CSS | Hybrid complexity |
| **Rive / Lottie avatar** | Pro animated persona | Asset pipeline + runtime |

**Recommendation:** stay native Qt until the voice pipeline feels excellent. UI frameworks don’t fix blocking speech loops.

---

## 5. Suggested architecture target (evolutionary)

Keep the modular monolith. Evolve the assistant into a clearer state machine:

```text
┌─────────────────────────────────────────────────────┐
│                     Sopno Shell                      │
│  HUD (PySide6 later)  ·  CLI  ·  Tray  ·  Daemon     │
└───────────────────────────┬─────────────────────────┘
                            │ callbacks / events
┌───────────────────────────▼─────────────────────────┐
│                 Assistant Runtime                    │
│  states: idle · listening · thinking · speaking      │
│  modes:  voice · text                                │
│  cancel tokens for barge-in / mode switch            │
└───────┬─────────────┬─────────────┬─────────────────┘
        │             │             │
   Wake/STT        LLM+Tools       TTS
   (local)     (Ollama+fallback)  (local preferred)
```

### Design rules

1. **UI never blocks on LLM/TTS** — workers + signals (already started; keep enforcing).
2. **Every long operation is cancellable** — mode switch, hide, close, barge-in.
3. **Models are config, not code** — already true via `config.json`; keep it that way.
4. **Tools are optional enhancement** — never a hard requirement for basic chat.
5. **One conversation transcript surface** — voice and text write into the same history.

---

## 6. Prioritized roadmap (practical)

### P0 — Reliability (do next)

1. **Tool-calling fallback**
   - Try `tools=...`
   - On “does not support tools” / 400 → retry plain chat
2. **Graceful LLM errors in HUD**
   - Show human message in transcript, keep avatar in `error` briefly, return to idle
3. **Mode switch robustness**
   - Ensure wake-word wait exits promptly when entering text mode (partially done)

### P1 — “Feels premium”

1. Interruptible TTS (stop speaking immediately on new input / stop button)
2. Streaming tokens into the reply panel (optional but high polish)
3. Latency footer: `STT 320ms · LLM 1.8s · TTS 400ms` (debug / power-user)
4. Continue HUD maturity (icon controls, spacing, tooltips — in progress)

### P2 — Platform maturity

1. Migrate to PySide6
2. systemd user service + tray-first autostart as default happy path
3. Config UI or tray menu for model / wake word / opacity
4. Test suite around assistant state transitions (not only unit helpers)

### P3 — Optional moonshots

1. Pipecat/LiveKit-style realtime loop for continuous dialogue
2. Web-rendered HUD shell if design velocity demands it
3. Multi-profile personalities / voices

---

## 7. UI direction (aligned with current HUD work)

Observed good patterns already adopted or recommended:

| Pattern | Source inspiration | Sopno application |
|---------|--------------------|-------------------|
| Floating companion panel | Gemini Live floating UI, Copilot popup | Frameless always-on-top HUD |
| Circular icon controls | ChatGPT composer | Mic / keyboard / send icon buttons |
| Living avatar by state | Persona / robot-face runtimes | Painted `AliveRobotFace` reacting to status |
| Compact ↔ expanded | Companion orb collapse | Minimize chrome control |
| Single transcript card | Chat products | You / Sopno combined surface |

**UI tech advice:** keep polishing PyQt HUD now. Revisit PySide6 or web shell only after voice reliability is excellent.

---

## 8. Model guidance

| Model | Use when | Caution |
|-------|----------|---------|
| **`qwen3:8b` (current default)** | General chat + tools on capable machines | Needs enough RAM/VRAM |
| Smaller Qwen / Llama variants | Low-RAM machines | May weaken tool quality |
| Models without tool support | Plain conversation | Must use **no-tools fallback** |

**Rule:** Sopno should run on *any* Ollama chat model for basic talk. Tools are a bonus when supported.

---

## 9. What not to do

1. **Don’t rewrite the whole app** into Electron “just because.”
2. **Don’t add five STT engines** — pick one primary offline path.
3. **Don’t couple UI widgets to Ollama calls** — keep the worker/callback boundary.
4. **Don’t treat emoji as the avatar long-term** — parametric/drawn or real animation assets age better (already moving this way).
5. **Don’t block the Qt UI thread** on network/model/TTS.

---

## 10. Summary recommendation

**Best near-term path for Sopno:**

> Keep the current modular local architecture.  
> Make the assistant **unbreakable** (tool fallback, cancels, better TTS/STT).  
> Keep polishing the floating HUD into a mature companion.  
> Only adopt realtime frameworks (Pipecat/LiveKit) or a web UI shell when you specifically need continuous voice or faster visual design throughput.

That sequence produces a “million-dollar company” feel through **reliability and interaction quality**, not through chasing libraries.

---

## 11. Related docs

- `doc/ARCHITECTURE.md` — folder structure and module boundaries  
- `doc/ROADMAP_STATUS.md` — feature completion status  
- `doc/SOPNO_COMPLETE_GUIDE.md` — end-to-end product guide  
- `doc/tts_integration.md` — TTS engine notes  

---

*This document captures an architecture/product review of the repository as of the HUD + `qwen3:8b` era. Update it when major runtime choices change (e.g., PySide6 migration or Pipecat adoption).*
