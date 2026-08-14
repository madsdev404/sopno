# Sopno — Complete Codebase Guide

This document is the definitive walkthrough of the entire Sopno codebase. It
explains **every folder, every file, and every key class/function**, and how they
all fit together. It is written so that anyone — including a brand-new developer
with zero knowledge of the project — can read it top to bottom and fully
understand what Sopno does, how it does it, and where to make changes.

---

## Table of Contents

1. [What is Sopno?](#1-what-is-sopno)
2. [The Big Picture (architecture)](#2-the-big-picture)
3. [The Conversation Loop (data flow)](#3-the-conversation-loop)
4. [Repository Layout](#4-repository-layout)
5. [Entry Point — `main.py`](#5-entry-point--mainpy)
6. [The `sopno/` Package](#6-the-sopno-package)
   - [6.1 `config/` — Settings & Prompts](#61-config--settings--prompts)
   - [6.2 `core/` — The Brain](#62-core--the-brain)
   - [6.3 `voice/` — Everything Audio](#63-voice--everything-audio)
   - [6.4 `llm/` — The AI Layer](#64-llm--the-ai-layer)
   - [6.5 `tools/` — What Sopno Can Do](#65-tools--what-sopno-can-do)
   - [6.6 `ui/` — What You See](#66-ui--what-you-see)
7. [Top-Level Folders](#7-top-level-folders)
   - [7.1 `prompts/`](#71-prompts)
   - [7.2 `models/`](#72-models)
   - [7.3 `scripts/`](#73-scripts)
   - [7.4 `tests/`](#74-tests)
   - [7.5 Root files](#75-root-files)
8. [Configuration Reference (`config.json`)](#8-configuration-reference)
9. [How to Extend Sopno](#9-how-to-extend-sopno)
10. [Running & Testing](#10-running--testing)

---

## 1. What is Sopno?

**Sopno** (স্বপ্ন, Bengali for "Dream") is a **bilingual, offline-first AI voice
assistant** for Linux desktops. It behaves like a personal Jarvis:

- You say the **wake word** (default: "dream"), then speak a command in **English
  or Bangla**.
- Sopno **listens** through the microphone, **transcribes** your speech offline
  (faster-whisper), thinks with a **local LLM** (Ollama, default `qwen3:8b`), may
  **run desktop tools** (open apps, change volume, search the web, control media…),
  then **speaks back** using offline neural TTS.
- A floating **glassmorphic HUD** shows its live state (Standby / Listening /
  Thinking / Speaking) and the conversation history.

Everything runs **on your machine** — no cloud APIs by default. The only optional
internet touches are the gTTS fallback (TTS) and the opt-in Google STT fallback.

---

## 2. The Big Picture

Sopno is a **modular monolith**: one repo, one Python package, and every concern
lives in its own folder. The rule is **"one folder = one job."**

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                             │
│             Boots the app → HUD GUI or terminal CLI          │
└───────────────────────────────┬─────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────┐
│                  sopno/core/assistant.py                     │
│        SopnoAssistant — the master conversation loop         │
└───────┬────────────────┬─────────────────┬──────────────────┘
        │                │                 │
        ▼                ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ sopno/voice/ │  │  sopno/llm/  │  │   sopno/tools/   │
│  mic, VAD,   │  │ Ollama LLM   │  │ OS actions the   │
│  wakeword,   │  │ + history    │  │ assistant can    │
│  STT, TTS    │  │ summarizer   │  │ perform          │
└──────┬───────┘  └──────┬───────┘  └────────┬─────────┘
       │                 │                   │
       └─────────────────┴───────────────────┘
        state updates are pushed out to the UI
                        │
                        ▼
        ┌──────────────────────────────┐
        │ sopno/ui/ — HUD (PyQt5) / CLI │
        │  robot face, status, chat     │
        └──────────────────────────────┘
```

Configuration comes from **`config.json`** at the repo root (read by
`sopno/config/settings.py`). Prompts come from plain-text files in **`prompts/`**.

---

## 3. The Conversation Loop

The heart of Sopno is an infinite loop in `SopnoAssistant.run()`
(`sopno/core/assistant.py`). Here is the complete journey of one interaction:

```
1. INTRO        Assistant says "Hello! I'm Sopno…", calibrates the mic
2. STANDBY      Idle. Waits for the wake word (wake_word mode)
                ─ or just listens continuously (always_on mode)
3. WAKE WORD    "dream" detected → sopno/voice/wakeword.py
4. LISTENING    Mic captures one full utterance → sopno/voice/listener.py
                (Silero VAD turn-taking if enabled, else SpeechRecognition)
5. STT          Audio → text (English/Bangla) → sopno/voice/stt/
6. ROUTE        Is this a local tool command or a chat message?
                → sopno/core/dispatcher.py  (fast rule-based path)
                → or the LLM at sopno/llm/client.py
7. TOOLS        If the LLM requests tools → sopno/tools/ executes them
8. THINK        LLM (Ollama) generates the reply
9. CONTEXT      Reply stored in history → sopno/core/context.py
                (auto-compresses when history gets too long)
10. SPEAK       Reply synthesized → sopno/voice/tts.py (barge-in: Sopno stops
                talking if you start talking mid-reply → sopno/voice/barge.py)
11. DISPLAY     Reply shown on the HUD / terminal → sopno/ui/
12. LOOP        Back to step 2 (or exit on "goodbye" / "বিদায়")
```

A short **0.45 s settle pause** after speaking (`_POST_SPEAK_SETTLE_S`) prevents
the mic from hearing Sopno's own voice as a new command.

---

## 4. Repository Layout

```
sopno/                         ← project root
├── main.py                    ← entry point (start here)
├── config.json                ← all user settings
├── requirements.txt           ← Python dependencies
├── README.md                  ← quick overview / quick-start
├── LICENSE                    ← MIT license
├── sopno/                     ← the application package
│   ├── config/                ← settings loader + prompt text loader
│   ├── core/                  ← assistant loop, context, dispatcher
│   ├── voice/                 ← listener, VAD, wake word, STT, TTS
│   ├── llm/                   ← Ollama client, history summarizer
│   ├── tools/                 ← desktop action tools + registry + schema
│   └── ui/                    ← terminal CLI + PyQt5 glassmorphic HUD
├── prompts/                   ← editable prompt templates (*.txt)
├── models/                    ← local AI model files (offline)
├── scripts/                   ← shell setup/deploy scripts
├── tests/                     ← unit tests (unittest)
└── doc/                       ← documentation (this file lives here)
```

---

## 5. Entry Point — `main.py`

`main.py` is the bootstrapper. It parses command-line arguments and launches either
the GUI HUD or the terminal CLI.

**Command-line flags:**

| Flag | Meaning |
|------|---------|
| *(none)* | Default: try HUD, fall back to CLI if PyQt5 is missing |
| `--hud` | Launch the HUD explicitly |
| `--hud --reload` | HUD with auto-restart when HUD source files change (dev) |
| `--cli` | Launch the terminal console mode |

```bash
python main.py            # HUD (or CLI fallback)
python main.py --cli      # terminal mode
python main.py --hud --reload
```

The logic: `--cli` → `sopno.ui.cli.run_cli()`. `--hud` (or default) → try
`sopno.ui.hud.run_hud()`; on `ImportError` (missing PyQt5), gracefully fall back to
CLI.

---

## 6. The `sopno/` Package

### 6.1 `config/` — Settings & Prompts

**`sopno/config/settings.py`** — the configuration brain.

- Reads `config.json` from the project root and exposes every value as a typed
  attribute on a module-level singleton:
  `from sopno.config.settings import settings`.
- Defines the important paths:
  - `settings.project_root` — repo root (resolved from this file's location)
  - `settings.prompts_dir` → `prompts/`
  - `settings.models_dir` → `models/`
  - `settings.logs_dir` → `logs/`
- Notable settings (the full list is in [Section 8](#8-configuration-reference)):
  `model_name`, `llm_think`, `llm_num_predict`, `llm_num_ctx`, `llm_temperature`,
  `stt_model`, `stt_language`, `stt_online_fallback`, `stt_capture`,
  `listening_mode`, `wake_words`, `pause_threshold`, `phrase_threshold`,
  `energy_threshold_floor` / `energy_threshold_ceiling`,
  `dynamic_energy_threshold`, `barge_in_enabled` / `barge_in_baseline_s` /
  `barge_in_multiplier` / `barge_in_margin` / `barge_in_confirm_ms`,
  `hud_opacity`, `hud_position`, `max_history_length`.

**`sopno/config/prompts.py`** — loads prompt text from `prompts/*.txt`.

- Exposes `SYSTEM_PROMPT` and `SUMMARIZE_PROMPT`.
- Prompts are **never hardcoded in Python** — edit the text files instead.
- Raises `FileNotFoundError` if a prompt file is missing.

### 6.2 `core/` — The Brain

**`sopno/core/assistant.py`** — the master orchestrator (`SopnoAssistant`).

This is the most important file in the project. It:

- Accepts four UI callbacks: `status_callback`, `speech_callback`,
  `reply_callback`, `log_callback` — this is how the UI stays in sync.
- Tracks two independent "modes":
  - **Interaction mode**: `"voice"` (speak + hear replies) vs `"text"` (type
    messages, silent replies). Switchable at runtime via `set_interaction_mode()`.
  - **Listening mode**: `"wake_word"` (say "dream" first) vs `"always_on"`
    (continuous listening). Switchable via `set_listening_mode()`.
- `run()` — the main loop described in [Section 3](#3-the-conversation-loop).
  Calibrates the mic, speaks a welcome message, then loops forever.
- `_await_command()` — blocks until a user command arrives:
  - **Text mode**: waits on a `threading.Event` until `submit_text()` is called.
  - **Voice mode**: if `wake_word`, first gates on the wake word, then calls
    `listener.listen_for_turn()`, then `transcribe()`.
  - Picks the STT language hint: a locked `stt_language` wins; otherwise Bangla if
    the current context language is `bn`; otherwise auto-detect.
- `_process_command(cmd_text)` — decides what to do with the text:
  1. **Exit check** — "exit", "quit", "goodbye", "bye", "বিদায়" → farewell + stop.
  2. **Language switch** — phrases like "speak in bangla" / "বাংলায় বল" switch
     `context.current_language` and reply in the new language.
  3. **Rule dispatcher** (`CommandDispatcher.dispatch`) — the fast local path. If a
     rule matches, the tool runs and its result is spoken; no LLM needed.
  4. **LLM path** — otherwise send to Ollama. A regex `_TOOLISH` decides whether to
     attach the tool schema (only for action-oriented phrases, to keep CPU time
     low). If the model calls tools, each is executed and the results are fed back,
     then the model produces the final conversational reply.
  - Reply text is sanitized (markdown characters stripped) before speaking.
- `_speak_with_barge_in(text)` — speaks a reply while a `BargeInMonitor` watches
  the mic. If the user starts talking mid-reply, TTS stops immediately, the log
  shows "Barge-in detected", and the loop returns to listening (skipping the
  0.45s settle pause) so the user can speak right away. Disabled when
  `barge_in_enabled` is `false`.

**`sopno/core/context.py`** — conversation memory (`ConversationContext`).

- Holds the message list starting with the system prompt.
- `add_user_message()` / `add_assistant_message()` append to history.
- `_compress_if_needed()` — when history reaches `max_history_length`
  (default 13), it calls the LLM summarizer to compress.
- `get_messages_for_llm()` — returns the messages with a language constraint
  appended: "You MUST respond in Bangla (বাংলা) only." or English.
- `current_language` — tracks `"en"` / `"bn"` for the conversation.

**`sopno/core/dispatcher.py`** — fast rule-based intent router (`CommandDispatcher`).

- `dispatch(text)` returns a **spoken result string** if a rule matches, or `None`
  if the message should go to the LLM.
- Rules (English keywords):
  - time/date → `get_current_time`
  - "open X" / "launch X" → `open_application`
  - "search X" / "google X" → `search_web`
  - volume up/down/mute → `control_volume`
  - system stats / CPU / RAM / battery → `get_system_stats`
  - lock screen → `lock_screen`
  - play / pause / next / previous → `play_media_control`

### 6.3 `voice/` — Everything Audio

**`sopno/voice/listener.py`** — microphone capture (`Listener`).

- Installs a ctypes ALSA error handler to silence `libasound` probe spam.
- `Listener` wraps a `speech_recognition.Recognizer` and a `TurnTaker` (VAD).
- `calibrate()` — short 0.8 s ambient-noise calibration, then clamps the energy
  threshold between `energy_threshold_floor` (100) and `ceiling` (250).
- `listen_for_turn()` — two capture paths:
  - **classic** (`stt_capture == "classic"`, the default): SpeechRecognition mic at
    the device's native sample rate (never forced to 16 kHz — that corrupted audio).
  - **vad** (`stt_capture == "vad"` + Silero model present): uses `TurnTaker`.
- `_listen_with_level_logs()` — a custom copy of `Recognizer.listen` that logs mic
  RMS every 2 s (so a "deaf" mic is visible in the HUD), enforces pause / phrase
  thresholds, and drops trailing silence / short blips.

**`sopno/voice/vad.py`** — offline voice-activity detection (`TurnTaker`).

- `ensure_silero_model()` — returns `models/silero_vad.onnx`, downloading it from
  two mirror URLs once if missing.
- `TurnTaker` uses Silero VAD through `sherpa_onnx.VoiceActivityDetector` with:
  threshold 0.45, min silence 0.85 s, min speech 0.25 s, max speech 15 s.
- Captures at the mic's **native rate** and resamples to 16 kHz with
  `audioop.ratecv` (forcing 16 kHz on a 44.1 kHz device corrupts speech).
- Adds a ~150 ms pre-roll before the speech onset and soft peak-normalizes so
  Whisper gets clean audio without clipping.
- If the model or PyAudio is missing, it returns `None` and the caller falls back
  to classic listening.

**`sopno/voice/wakeword.py`** — wake-word detection (`WakeWordDetector`).

- **Primary (offline)**: `sherpa_onnx.KeywordSpotter` using the
  `sherpa-onnx-kws-zipformer-gigaspeech-3.3M` model. Wake words from config are
  BPE-tokenized (greedy, longest-match over the model's token table) and written to
  `active_keywords.txt`, then registered with a `:1.5` boosting threshold.
  Listens through `pvrecorder` at 16 kHz and reports on a match.
- **Fallback**: if sherpa-onnx / PvRecorder are unavailable, it loops
  `recognizer.listen()` → `transcribe()` and does substring matching against the
  configured wake words.
- `wait_for_wakeword(recognizer, running_check)` — blocks until the wake word is
  heard; returns `False` if the assistant should stop.

**`sopno/voice/stt/`** — speech-to-text package.

- **`__init__.py`** — public API `transcribe(recognizer, audio, language=None)`.
  Primary: offline Whisper. On failure: if `stt_online_fallback` is `True`, tries
  Google; otherwise raises `sr.UnknownValueError` (stays offline).
- **`whisper.py`** — the faster-whisper engine.
  - Lazy singleton model (`_get_whisper()`), CPU + `int8`, stored in
    `models/whisper`. Loads `local_files_only` first, then performs a one-time
    download. Sets `HF_HUB_OFFLINE=1` after a successful load.
  - Writes audio to a temp 16 kHz mono WAV, then runs Whisper with beam size 5,
    `vad_filter=True`, `no_speech_threshold=0.6`.
  - Language strategy: if a language is configured/focused (`en`/`bn`) force it; if
    "auto", run auto-detect once, then retry the other language(s) only when the
    first result scores badly or detects an unsupported language.
  - Quality gates reject empty / junk / unsupported-script transcripts.
- **`filters.py`** — transcript quality checks: known hallucination phrases
  ("thanks for watching", "subscribe"…), syllable babble / consonant soup
  (e.g. "বাবাবাবাবা"), and script checks — Sopno only accepts Bangla or Latin text.
- **`scoring.py`** — scoring + audio sanity. `_score_result()` scores a transcript
  from Whisper segment log-probabilities (bonus for real diverse Bangla, penalties
  for compression ratio / short text). `_audio_is_too_quiet()` /
  `_audio_is_too_short()` reject near-silent or < 0.7 s clips that make Whisper
  hallucinate. `_is_too_thin()` rejects a single weak token as noise.
- **`google.py`** — optional online fallback. Runs `recognize_google` for `bn-BD`
  and `en-US` **in parallel**, then picks by the language hint or detected script.

**`sopno/voice/tts.py`** — text-to-speech (`speak()`).

- Engine priority: **Coqui TTS** (offline, neural, `your_tts` multilingual model,
  ~200 MB first-run download) → **gTTS** (online Google fallback).
- `speak(text)` plays the audio with `ffplay` from a temp file and cleans up.
- Playback is interruptible: `speak(text, should_stop=…, on_play_start=…)` polls
  `should_stop()` during playback and cuts the audio short (used by barge-in).
- `_is_bangla(text)` detects the Unicode Bangla range to pick `bn` vs `en` for gTTS.
- `engine_name()` reports the active engine.

**`sopno/voice/barge.py`** — barge-in (`BargeInMonitor`).

- Lets you interrupt Sopno: while TTS plays, a background thread watches the mic.
- `BargeDetector` (pure logic, unit-tested) first measures Sopno's *own* voice
  during the first `barge_in_baseline_s`, then confirms an interrupt when the user
  speaks above `max(floor, own_voice × barge_in_multiplier + margin)` for
  `barge_in_confirm_ms`.
- Degrades gracefully: if PyAudio or the mic is unavailable, playback just runs
  to completion.

### 6.4 `llm/` — The AI Layer

**`sopno/llm/client.py`** — the Ollama wrapper.

- `chat(messages, tools=None, stream=False)` — calls `ollama.chat` with Sopno's
  voice-optimized defaults: `num_predict` (120), `num_ctx` (2048), `temperature`
  (0.6). If `settings.llm_think` is `False`, sends the top-level `think=False` to
  skip Qwen3 hidden reasoning (a huge CPU win).
- `stream_reply(messages)` — generator of reply chunks.
- `single_reply(messages)` — full non-streamed reply (used by the summarizer).
- `message_as_dict(msg)` — normalizes Ollama message objects to plain dicts so the
  assistant can append tool messages to history.

**`sopno/llm/summarizer.py`** — history compressor.

- `compress_history(messages)` — when the history is long enough, it:
  1. keeps `messages[0]` (system prompt) and the last 4 messages (2 full turns),
  2. summarizes everything in between using the LLM itself
     (`SUMMARIZE_PROMPT` from `prompts/summarize.txt`),
  3. injects the summary as a `system` message right after the system prompt.
- If summarization fails, it keeps the full history (safe fallback).

### 6.5 `tools/` — What Sopno Can Do

**`sopno/tools/schema.py`** — `TOOLS_SCHEMA`, the JSON tool-calling schema handed to
the LLM (OpenAI-style `function` objects). It defines 7 tools:

| Tool | Purpose | Arguments |
|------|---------|-----------|
| `get_current_time` | Time, date, weekday | — |
| `open_application` | Launch a desktop app | `app_name` |
| `search_web` | Google search in browser | `query` |
| `control_volume` | Volume up/down/mute | `action` |
| `get_system_stats` | CPU/RAM/battery | — |
| `lock_screen` | Lock the desktop | — |
| `play_media_control` | Play/pause/next/previous | `action` |

**`sopno/tools/registry.py`** — maps schema names → Python functions.

- `_REGISTRY` dict (name → callable) importing each skill from `builtins/`.
- `execute_tool(name, arguments)` — runs a registered tool, spreading the argument
  dict; wraps errors into friendly spoken strings.
- `get_registered_names()` — list of registered tools.

**`sopno/tools/builtins/`** — the skills themselves, one file per skill or small
domain:

- **`system.py`** — OS-level tools.
  - `open_application(app_name)` — launches apps via `subprocess.Popen` using the
    `_APP_MAP` friendly-name → command table (chrome, firefox, files, terminal,
    vscode, spotify, calculator, settings).
  - `control_volume(action)` — `amixer -D pulse sset Master 10%+/10%-/toggle`.
  - `get_system_stats()` — CPU% (`psutil.cpu_percent`), RAM GB used/total, battery
    percent + charging status.
  - `lock_screen()` — `gnome-screensaver-command --lock`, falling back to
    `loginctl lock-session`.
- **`search.py`** — `search_web(query)` opens a Google search URL in the default
  browser via `webbrowser`.
- **`datetime_tool.py`** — `get_current_time()` returns e.g.
  "It is 09:41 AM on Thursday, August 13."
- **`media.py`** — `play_media_control(action)` controls media players via
  `playerctl` (MPRIS). Requires `playerctl` and a running media player.

### 6.6 `ui/` — What You See

**`sopno/ui/cli.py`** — terminal mode.

- `run_cli()` creates `SopnoAssistant` with stdout/print callbacks so status,
  transcripts, and replies appear in the console. No GUI needed.

**`sopno/ui/hud/`** — the PyQt5 glassmorphic HUD package. Three layers: the
entry/wiring at the top level, behaviors as mixins in `behaviors/`, reusable
widgets in `widgets/`, and the look & feel in `visuals/`.

- **`__init__.py`** — public API: re-exports `run_hud` and `SopnoHUDWindow`.
- **`app.py`** — `run_hud(reload=False)`: builds the `QApplication`, sets the
  Fusion style + global tooltip theme, optionally installs a hot-reload watcher
  (`--reload` restarts the process when any HUD file or `assistant.py` /
  `settings.py` changes — it watches the whole package recursively), shows the
  window, and enters the Qt event loop.
- **`window.py`** — `SopnoHUDWindow` (the main frame). Frameless, always-on-top,
  translucent; builds the layout: header chrome (size buttons, hide, close), the
  animated robot face, status label + listening-mode chip, the chat thread, the
  Voice|Text mode toggle, the text composer dock, a small log line, and a resize
  grip. Spawns `AssistantWorker` in a daemon thread and wires its Qt signals to UI
  methods. `position_hud()` pins it to the top-right of the screen.
- **`worker.py`** — `AssistantWorker(QObject)`: the bridge between the assistant
  thread and Qt's signal/slot system. Emits `status_changed`, `speech_detected`,
  `reply_generated`, `log_message`; proxies mode / listen-mode / text input to the
  assistant.
- **`behaviors/`** — mixins that dress the window:
  - **`chrome.py`** — `ChromeMixin`: builds the window chrome buttons, the circular
    icon buttons, the "🔔 Wake / 🎤 Always" listening-mode chip, and handles
    sending typed text messages.
  - **`responsive.py`** — `ResponsiveMixin`: maps panel width to a "metrics" dict
    (fonts, icons, robot size, spacing, which rows are visible) and re-styles the
    HUD when resized (`_apply_responsive`). `apply_size_preset(mode)` resizes to a
    preset while keeping the panel on-screen.
  - **`resizing.py`** — `ResizeMixin`: 8-zone edge/corner hit-detection
    (`_edge_at`), drag-to-resize with min/max enforcement, and plain window
    dragging by the body. Sets the proper resize cursors.
  - **`status.py`** — `StatusMixin`: renders assistant state onto the UI —
    updates the status label + robot face color, the contextual hint label
    ("Say 'dream'…", "Listening…", "Thinking…"), adds user/Sopno chat bubbles, and
    shows the latest log line.
  - **`tray.py`** — `TrayMixin`: system tray icon (a radial-gradient orb), context
    menu (Show/Hide HUD, size presets, Exit), and click-to-toggle show/hide.
- **`widgets/`** — self-contained reusable pieces:
  - **`robot.py`** — `AliveRobotFace(QWidget)`: a parametric robot face painted in
    `paintEvent`. It blinks, glances around, "breathes", opens its mouth when
    speaking, and recolors per state (blue listening, purple thinking, green
    speaking) using `STATE_ACCENT` colors. Runs on a ~30 fps `QTimer`.
  - **`chat.py`** — `ChatThread`: a scrolling conversation of message bubbles
    ("You" vs "Sopno"), capped at 40 bubbles, auto-scrolls to bottom.
  - **`mode_toggle.py`** — `ModeToggle`: a segmented Voice | Text capsule control
    with vector icons.
- **`visuals/`** — the look & feel:
  - **`theme.py`** — shared constants and QSS templates: `SIZE_PRESETS`
    (small 280×360 / medium 380×560 / full 520×740), `MIN_SIZE` / `MAX_SIZE`,
    `STATUS_COPY` (state → label + color), `STATE_ACCENT` (state → QColor), and
    CSS templates for chrome buttons, tool icons, segment buttons, and circular
    buttons.
  - **`icons.py`** — `_paint_icon(kind, size, color, active)`: crisp vector glyphs
    drawn with `QPainter` (mic, keyboard, send, size-small/medium/full) — no emoji.

---

## 7. Top-Level Folders

### 7.1 `prompts/`

Plain-text prompt templates — the "personality" and instructions of Sopno.

- **`system.txt`** — `SYSTEM_PROMPT`. Defines Sopno as a bilingual
  (Bangla/English) voice assistant: reply in the user's language, keep replies
  short (2–4 sentences, no markdown), offer to display long content on screen,
  and be warm.
- **`summarize.txt`** — `SUMMARIZE_PROMPT`. Instructs the LLM to compress older
  conversation into 2–3 factual sentences preserving facts, preferences, names,
  and decisions.

> Edit these files to change Sopno's behavior — no Python changes needed.

### 7.2 `models/`

Local AI model files (the reason Sopno works fully offline):

- **`sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/`** — the wake-word
  keyword spotter (encoder / decoder / joiner ONNX files, `tokens.txt` BPE table,
  `keywords.txt`). `active_keywords.txt` is regenerated at runtime with the
  configured wake words. Used by `sopno/voice/wakeword.py`.
- **`silero_vad.onnx`** — the Silero VAD model for turn-taking, auto-downloaded
  by `sopno/voice/vad.py` if missing.
- **`whisper/`** — the faster-whisper model cache (a Hugging Face repo snapshot,
  e.g. `models--Systran--faster-whisper-small/`). Downloaded once on first run,
  then used fully offline by `sopno/voice/stt/whisper.py`.

### 7.3 `scripts/`

Shell setup / deployment scripts.

- **`install_daemon.sh`** — installs Sopno as a **systemd user service**:
  writes `~/.config/systemd/user/sopno.service`, then enables and starts it.
  The service runs `venv/bin/python main.py --hud` with `DISPLAY`/`XAUTHORITY`
  set, and auto-restarts on failure (`Restart=always`).

### 7.4 `tests/`

Unit tests using Python's standard `unittest` library. Run with:

```bash
python3 -m unittest discover -s tests
```

| File | What it verifies |
|------|------------------|
| `test_assistant.py` | `ConversationContext` lifecycle + language constraints; `CommandDispatcher` routing patterns (time, open, search, unknown → LLM) |
| `test_stt.py` | `transcribe()` prefers Whisper; Google fallback only fires when `stt_online_fallback` is `True`; offline default raises `UnknownValueError` |
| `test_tools.py` | Registry contains all 7 tools; `get_current_time()` format; `open_application` and `control_volume` subprocess calls |
| `test_tts.py` | `_is_bangla()` detection; `speak()` routes to the active engine and ignores empty text |
| `test_wakeword.py` | WakeWordDetector falls back when model files are missing; fallback detects / ignores wake words; detector is lazy-created; listening-mode defaults |

### 7.5 Root files

| File | Purpose |
|------|---------|
| `main.py` | Entry point (see [Section 5](#5-entry-point--mainpy)) |
| `config.json` | All user settings (see [Section 8](#8-configuration-reference)) |
| `requirements.txt` | Python dependencies: `ollama`, `gTTS`, `edge-tts`, `SpeechRecognition`, `faster-whisper`, `pyaudio`, `sherpa-onnx`, `pvrecorder`, `numpy`, `PyQt5`, `psutil` |
| `README.md` | Project overview, quick start, usage |
| `LICENSE` | MIT license |
| `doc/` | Documentation (this guide plus architecture / getting-started / roadmap docs) |

---

## 8. Configuration Reference

All settings live in **`config.json`** at the repo root and are read by
`sopno/config/settings.py`. Every key has a sensible default if omitted.

| Key | Default | Meaning |
|-----|---------|---------|
| `model_name` | `qwen3:8b` | Ollama LLM model to use |
| `llm_think` | `false` | Enable Qwen3 hidden "thinking" (slow on CPU — keep off) |
| `llm_num_predict` | `120` | Max tokens in a reply (keeps speech short) |
| `llm_num_ctx` | `2048` | LLM context window size |
| `llm_temperature` | `0.6` | LLM creativity |
| `stt_model` | `small` | Whisper size: `tiny`/`base`/`small` (small = better Bangla) |
| `stt_language` | `auto` | `auto` tries both languages; lock with `en` or `bn` |
| `stt_online_fallback` | `false` | Allow Google STT fallback (offline-first default) |
| `stt_capture` | `classic` | `classic` (SpeechRecognition) or `vad` (Silero/PyAudio) |
| `listening_mode` | `wake_word` | `wake_word` (say the wake word) or `always_on` |
| `wake_words` | `["dream"]` | Wake-word phrases to detect |
| `voice_lang_bn` | `bn` | Bangla locale code for TTS |
| `voice_lang_en` | `en` | English locale code for TTS |
| `pause_threshold` | `1.5` | Silence (s) that ends a spoken turn |
| `phrase_threshold` | `0.3` | Min speech (s) for a phrase to count |
| `energy_threshold_floor` | `100` | Min mic energy to start a phrase |
| `energy_threshold_ceiling` | `250` | Max clamped mic energy threshold |
| `dynamic_energy_threshold` | `false` | SpeechRecognition auto-adjust (kept off) |
| `barge_in_enabled` | `true` | Let the user interrupt TTS by talking (see `barge.py`) |
| `barge_in_baseline_s` | `0.4` | Seconds of Sopno's own voice to measure as the baseline |
| `barge_in_multiplier` | `1.7` | Interrupt threshold = `own_voice × this + margin` |
| `barge_in_margin` | `30` | Extra energy above the baseline before an interrupt counts |
| `barge_in_confirm_ms` | `180` | How long the user must stay above threshold to confirm |
| `hud_opacity` | `0.85` | HUD background opacity |
| `hud_position` | `top-right` | Where the HUD appears |
| `max_history_length` | `13` | Message count that triggers history summarization |

---

## 9. How to Extend Sopno

Because the project is modular, most changes are local and low-risk:

**Add a new tool (skill)**
1. Create `sopno/tools/builtins/your_tool.py` with a function that returns a
   short, speakable string.
2. Register it in `sopno/tools/registry.py` (`_REGISTRY`).
3. Add its schema to `TOOLS_SCHEMA` in `sopno/tools/schema.py` so the LLM can call
   it.
4. Optionally add a quick rule in `sopno/core/dispatcher.py` for the fast path.

**Change the LLM** — edit `model_name` (+ related `llm_*` keys) in `config.json`.

**Change Sopno's personality / rules** — edit `prompts/system.txt`. No code.

**Change wake word** — edit `wake_words` in `config.json` (e.g. `["sopno"]`).

**Switch capture to Silero VAD** — set `stt_capture` to `"vad"` in `config.json`
(requires `models/silero_vad.onnx`, auto-downloaded).

**Change TTS engine** — only touch `sopno/voice/tts.py`.
**Change STT model** — only touch `config.json` (`stt_model`).
**Change UI layout** — only touch `sopno/ui/hud/window.py`.

---

## 10. Running & Testing

**Prerequisites (Linux):**

```bash
sudo apt install -y python3-dev portaudio19-dev ffmpeg flac libnotify-bin
```

**Ollama:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
```

**Setup:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Run:**

```bash
python main.py            # HUD (falls back to CLI)
python main.py --cli      # terminal mode
python main.py --hud --reload   # dev mode with auto-restart
```

**Run as a background daemon:**

```bash
./scripts/install_daemon.sh
systemctl --user status sopno
journalctl --user -u sopno -f
```

**Run the tests:**

```bash
python3 -m unittest discover -s tests
```


