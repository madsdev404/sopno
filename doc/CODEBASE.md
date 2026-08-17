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
│   ├── llm/                   ← Ollama client, researcher, history summarizer
│   ├── memory/                ← long-term SQLite memory + semantic vectors
│   ├── tools/                 ← desktop action tools + registry + schema
│   └── ui/                    ← terminal CLI + PyQt5 glassmorphic HUD
├── prompts/                   ← editable prompt templates (*.txt)
├── models/                    ← local AI model files (offline)
├── scripts/                   ← shell setup/deploy scripts
├── tests/                     ← unit tests (unittest; voice/ core/ tools/ integration/)
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

**`sopno/core/reminders.py`** — one-shot reminders (backing store for the
`automation/reminders.py` tools).

- `ReminderStore` — own SQLite DB (`settings.reminders_path`, WAL, RLock),
  rows `reminders(id, due_at, text, status, created_at)` with ISO timestamps and
  statuses `pending → delivered | cancelled`. `set`/`cancel`/`list`/`due`
  (delivers due reminders atomically — marked `delivered` in the same
  transaction, so each fires exactly once)/`count_pending`/`close`.
- `parse_when(when, now=None)` — deterministic regex parser returning
  `(due_ts, error)`: "now", "in N units", bare "N units", "today/tonight/tomorrow
  at? HH[:MM] am/pm", time-only (rolls to tomorrow if already past), "tomorrow"
  alone (9am), `YYYY-MM-DD[ at] HH:MM` / `YYYY-MM-DD` (9am).
- `format_due(ts)` — human-friendly "Sunday, August 16 at 02:52 PM".
- `get_store()` / `set_store(store)` — shared singleton the tools + poller use.
- `ReminderPoller` — daemon thread; every `reminders_poll_seconds` it delivers
  due reminders through a `deliver(text)` callback (the assistant's
  `_deliver_reminder`, guarded by a speech lock). Started in `SopnoAssistant.run`
  when `reminders_enabled`.

**`sopno/core/rules.py`** — automation rules ("if X then Y"), backing the
`automation/rules.py` tools.

- `_evaluate(condition)` — allowlist condition grammar only: `metric op value`
  where metric ∈ {`battery_percent`, `cpu_percent`, `ram_percent`,
  `disk_free_gb`, `hour_of_day`, `day_of_week`} and op ∈ {`< <= > >= ==`}.
  Metrics come from `psutil` / the clock. **No eval, no free-form code.**
- `_parse_action(action)` — shlex-parses `tool key="value" …`, validates the
  tool is registered. Action args are simple strings.
- `RuleStore` — own SQLite DB (`settings.rules_path`, WAL, RLock), rows
  `rules(id, name, condition, action, enabled, created_at, last_fired,
  fire_count)`. `add` (validates first), `list_rules`, `remove`,
  `set_enabled`, `run` (fires each enabled rule once per true-period and
  returns the results), `close`.
- `_fire` — executes the action via the registry; if the action parks a
  pending-action confirmation, it is auto-approved (the rule itself was the
  one-time approval). Records `last_fired`/`fire_count`.
- `RulePoller` — daemon thread; every `rules_poll_seconds` calls `store.run()`
  and delivers each result through a `deliver(text)` callback (the assistant's
  `_deliver_rule`, speech-locked). Started in `SopnoAssistant.run` when
  `rules_enabled`.

**`sopno/core/subagents.py`** — multi-agent runners, backing the `automation/subagents.py`
tools.

- `_AGENT_PROMPTS` — focused system prompts for `researcher`, `coder`, `reviewer`.
- `_ALLOWED_TOOLS` — per-agent restricted tool allowlist (researcher:
  search/fetch/read; coder: files/git/terminal; reviewer: read-only).
- `_schema_for(agent)` — filters `get_schema()` down to the agent's allowlist.
- `run_subagent(agent, task)` — builds system + user messages, then runs the
  same Ollama tool-calling loop as the assistant (bounded by
  `subagents_max_turns`): execute tool calls through the registry (unknown
  names are answered safely), feed results back, return the final text.
- `list_agents()` — the available subagent names.

**`sopno/core/agents/`** — durable machinery for long-running background agents
(backing store + work queue; design in `doc/roadmap/long-running-agents.md`).

- `session.py` — `AgentSessionStore`, own SQLite DB (`settings.agents_path`,
  WAL, RLock). `create(name, goal, kind=...)` → durable session with status
  machine `ready → running → done | blocked | dead | waiting_human`
  (`valid_transition` guards every move; illegal transitions raise; `running →
  ready` returns a session to dormancy mid-job). Heartbeat updates `updated_at`
  (running only). Append-only action log (`log_action`) — the session is a
  structured event stream, not a chat transcript. Plan/memory alignment budget
  caps the stored plan+memory size. `kind` (`general`/`coding`) and
  `pending_action` (checkpointed approval gate) columns, no-op migrations.
  `add_alignment(text)` appends a human/reflection correction to the alignment
  record (exposed via `agent_align`).
- `queue.py` — `AgentQueue`, own table in the same SQLite DB. `enqueue` with
  idempotency (a `dedupe_key` collapses repeats); `claim(worker, limit)` claims
  `ready` jobs atomically (`BEGIN IMMEDIATE`, `ORDER BY id ASC`) and stamps a
  lease; `finish`/`fail`/`release`; `renew(worker, id)` heartbeat-extends the
  lease; `recover_orphans()` requeues expired-lease jobs (attempts + 1) or
  dead-letters them past `agents_max_attempts`; failed jobs retry with
  exponential backoff + jitter (`_backoff_seconds`); `stats()` counts by status.
- `scheduler.py` — `AgentScheduler`: a polled daemon that fires session
  triggers. `parse_schedule` handles `interval:<seconds>`, `cron:<5 fields>`
  (stdlib-only parser — `*`/`*/n`/`a-b`/`a,b,c`, 3-letter names, dom/dow OR
  semantics), and one-shot `eta:<ISO>`; `next_fire_at` computes the next match.
  `tick()` fires every due trigger as a `run` job (idempotency key tied to the
  fire timestamp — a crash between enqueue and bookkeeping can't double-run) and
  checkpoints `last_fired_at` (new column, migrated in `__init__`). Terminal
  (`done`/`dead`) and paused sessions are skipped.
- `events.py` — `AgentEvents`, the wake channel: `wake(agent_id, message,
  state_delta)` checkpoints the delta (store's `apply_state_delta`, atomic),
  queues the message on pending input, enqueues a `resume` job, and appends an
  audit entry — the event-driven dormancy path for parked sessions.
- `sources.py` — external event sources that produce the *same* durable wake as
  a human reply. `FileWatcher` (polled thread): watches dirs from
  `settings.agents_file_watches`, snapshots `mtime`+`size`, debounces by
  advancing the snapshot on every tick, wakes the named agent on change
  (`first scan is the baseline` — pre-existing files never fire). `WebhookServer`
  (`ThreadingHTTPServer`, bound to `agents_webhook_host`/`agents_webhook_port`,
  port 0 = disabled): `POST /webhook` accepts `{agent, message, state_delta}`
  (agent by id *or* name; unknown → 404), `GET /health` liveness. Singletons
  `get/set_watcher` + `get/set_webhook` for tests.
- `worker.py` — `AgentWorker`, a daemon that claims `run`/`resume` jobs and
  drives a bounded ORIENT → DECIDE → ACT → OBSERVE loop. Per-agent lock (one
  session → one driver) + a shared dispatch lock (serializes the pending-action
  gate in `files.py`). Heartbeats the session and renews the job lease each
  step; executes tool calls through the session's allowlist (default excludes
  the `agent_*`/`coding_*` management tools); an approval gate parks the session
  in `waiting_human` with the pending action checkpointed; queued human input is
  drained on resume (a parked approval is answered Yes/No). Budgets
  (`max_turns`/`max_wall_minutes`/`max_actions_per_day`) end in `dead`; the
  per-job turn budget (`agents_job_max_turns` or `budget.max_turns`) hands the
  session back to `ready` for dormancy. After each general-agent drive it runs a
  periodic **REFLECT** (`reflect_fn`, default `default_reflect` via `llm_chat`);
  bullet notes are promoted into the session's alignment record, and reflection
  failures are silent. A `kind='coding'` session is routed into the worktree
  harness instead (no reflection).
- `runtime.py` — `AgentRuntime`, the lifecycle owner started by the assistant:
  boots `agents_concurrency` workers (wired with `reflect_fn=default_reflect`)
  + the scheduler + a watchdog, starts the event sources (`FileWatcher` when
  watches are configured, `WebhookServer` when a port is set), recovers orphan
  jobs and reclaims stale `running` sessions (no live job + heartbeat older
  than `agents_lease_seconds`) on start and periodically.

**`sopno/core/coding/`** — the autonomous coding harness (design in
`doc/roadmap/autonomous-coding.md`). Split from the original ~844-line
`sopno/core/coding.py` into single-purpose modules per the "one folder = one
job" rule.

- `agent.py` — `CodingAgent.run()`: plan → recite → act → verify loop in a git
  worktree, bounded by `coding_max_turns`/`coding_max_tokens`/
  `coding_max_wall_minutes`/`coding_max_diff_lines` + a stall detector. After
  each change tool it verifies, and commits a checkpoint on green. Terminal
  states `success | no_op | blocked | stalled | exhausted` (LLM errors land in
  `exhausted`, never `success`). The harness owns `PLAN.md`/`progress.md`/
  `SUMMARY.md`; injectables `llm_step`/`git_runner`/`verify_runner`/`store`/
  `session_id` make it fully unit-testable. With a `store` + `session_id`, a
  `[coding-worktree]` record is persisted in the session's working memory and a
  later run reattaches to the same branch (`WorktreeSession.attach`) — the
  background-agent crash-resume path. On top of the loop: three local tools —
  `delegate` (sub-agent digest via `run_subagent`, truncated), `escalate`
  (pauses the run in `review_required` mode with a `blocked_reason`; otherwise
  recorded into `escalations` and the run continues), `run_review` (self-review
  with a structured verdict that gates success in `review_required`) — plus
  `coding_approval_mode` handling (`auto_merge_guardrailed`/`unattended`/
  `review_required`), a red-test baseline on `main` when `coding_require_red_test`
  (green baseline → RED-FIRST advisory note, not a hard block; `baseline_green`
  lands in the result), and `_auto_merge`: branch green → merge into main →
  merged tree re-verified → hard-reset rollback on red or failed push →
  optional push behind `coding_push_enabled`. `run_coding_batch(tickets)` in
  `__init__.py` runs a fresh `CodingAgent` per ticket.
- `tools.py` — `ToolDispatcher`: allowlists `ALLOWED_TOOLS` (+ the local
  `delegate`/`run_review`/`escalate` schemas appended to the LLM-facing schema),
  filters `get_schema()` for `tools_schema()`, and `_gate`'s every write through
  `files._authorize` (bypassing the interactive Yes/No, never the gate).
  Refusals are observations returned to the LLM, not errors.
- `worktree.py` — `WorktreeSession`: creates/cleans the worktree
  (`settings.coding_worktree_dir`, branch `sopno/<slug>-<ts>`, safe-name
  checks), `setup()` captures `base_sha`, `checkpoint()` commits with a
  guarded identity, `diff_lines()` counts changed lines since base,
  `merge_back()` merges the branch into main (`--no-ff`, keeps the pre-merge
  head for rollback), `abort_merge()` undoes an in-progress *or* committed
  merge (`reset --hard` to the pre-merge head), `push()` pushes the branch.
- `verify.py` — `Verifier`: `resolve_recipe` picks the task spec's
  `verify_recipe`, or a default test command (`python -m unittest discover` via
  a `.venv`-aware `guess_python`, `--quiet`); `run()`/`green()` report exit
  code, stderr, and a structured verdict.
- `prompts.py` — `system_prompt`/`task_prompt`/`recitation` (harness docs as a
  single message block each turn).
- `util.py` — `slugify`, `q` (shlex quote), `safe_branch` (branch-safe regex).
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

### 6.4b `memory/` — Long-Term Memory

**`sopno/memory/store.py`** — the persistent memory store (`MemoryStore`).

- SQLite (`memory.db`) with an FTS5 index over memory content; `remember`,
  `forget` (soft-delete), `recall`, `stats`, `wipe`.
- `remember(content, category, importance)` dedupes on exact content; `recall`
  bumps `use_count`/`last_used_at` (recency signal).
- `recall(query, limit, categories)` merges FTS5 keyword matches (bm25, ranked
  first) with semantic vector matches that fill the remaining slots.

**`sopno/memory/semantic.py`** — the vector layer on top of the store.

- Reuses the researcher's Ollama `nomic-embed-text` embedding
  (`embed_texts`) and stores one 768-dim vector per memory in a `sqlite-vec`
  `vec0` table (`memory_vectors`), keyed by the memory rowid.
- `query_embedding()` runs a KNN `MATCH` over the table and converts L2
  distance → cosine (`_MIN_COSINE = 0.4`); candidates are re-joined to the
  `memories` table and filtered by `active`/category.
- Best-effort throughout: if `semantic_memory_enabled` is off, sqlite-vec is
  missing, the model is unreachable, or embeddings don't fit 768 dims, the
  store silently degrades to pure FTS5 recall. Zero vectors are never stored
  (they'd match everything at cosine 0.5).

### 6.5 `tools/` — What Sopno Can Do

**`sopno/tools/schema.py`** — `TOOLS_SCHEMA`, the JSON tool-calling schema handed to
 the LLM (OpenAI-style `function` objects). It defines 79 tools:

| Tool | Purpose | Arguments |
|------|---------|-----------|
| `get_current_time` | Time, date, weekday | — |
| `open_application` | Launch a desktop app | `app_name` |
| `search_web` | Multi-engine web search | `query` |
| `fetch_url` | Fetch a URL as readable text | `url` |
| `research` | Deep, cited web research (RAG) | `query` |
| `run_terminal` | Run a shell command persistently | `command`, `timeout` |
| `terminal_send` | Send keys/stdin to the running program | `keys`, `enter` |
| `terminal_status` | Poll the terminal session state | — |
| `list_processes` | Top processes, optional filter | `query`, `limit` |
| `kill_process` | Terminate a process by PID/name | `target`, `signal` |
| `manage_service` | systemctl --user start/stop/restart/… | `action`, `service` |
| `read_logs` | Journalctl / file-tail log entries | `source`, `unit`, `lines` |
| `manage_cron` | List/add/remove cron jobs | `action`, `schedule`, `command` |
| `read_file` | Read a file inside an allowed root | `path`, `lines` |
| `write_file` | Create/overwrite a file (confirmed) | `path`, `content` |
| `edit_file` | Exact-string replace (confirmed) | `path`, `old_string`, `new_string` |
| `list_directory` | List a folder's entries | `path` |
| `delete_file` | Delete a single file (confirmed) | `path` |
| `rename_file` | Move/rename a file (confirmed) | `path`, `new_path` |
| `copy_file` | Duplicate a file or folder (confirmed) | `path`, `new_path`, `overwrite` |
| `move_file` | Move/rename a file; alias of rename_file | `path`, `new_path` |
| `search_files` | Find files by name or content | `query`, `path`, `mode` |
| `set_reminder` | Set a one-shot reminder (non-destructive) | `when`, `text` |
| `list_reminders` | List upcoming + recent reminders | — |
| `cancel_reminder` | Cancel a pending reminder by id | `id` |
| `browser_navigate` | Open a page → text snapshot (title/body/interactive index) | `url` |
| `browser_click` | Click an element (CSS selector or snapshot index) | `selector`, `index` |
| `browser_type` | Type into an input/textarea | `selector`, `text` |
| `browser_extract` | Read text from a page region | `selector` |
| `browser_screenshot` | Save a PNG screenshot (write-root + confirm) | `path`, `full_page` |
| `browser_back` | Go back to the previous page | — |
| `browser_close` | Close the browser session | — |
| `clipboard_get` | Read the clipboard (xclip/xsel) | — |
| `clipboard_set` | Put text on the clipboard (confirmed) | `text` |
| `take_screenshot` | Screen capture to PNG (write-root + confirm) | `path`, `region` |
| `list_windows` | List open desktop windows (wmctrl) | — |
| `focus_window` | Bring a matching window to the front | `title` |
| `send_keys` | Type text into the focused window (confirmed) | `text` |
| `press_key` | Press a key/combo (confirmed; unsafe combos rejected) | `combo` |
| `get_disk_stats` | Partitions/usage + temps + fans (psutil) | — |
| `get_gpu_stats` | NVIDIA GPU name/util/VRAM/temp (pynvml) | — |
| `get_network_stats` | Per-interface bytes up/down (psutil) | — |
| `query_database` | Run SQL on a SQLite file (reads instant, writes confirmed) | `path`, `sql` |
| `explain_schema` | Tables, columns, row counts of a SQLite file | `path` |
| `backup_database` | Live consistent SQLite backup (confirmed) | `path`, `destination` |
| `install_package` | Install via apt/pacman/dnf/pip/flatpak (confirmed) | `name`, `manager` |
| `uninstall_package` | Remove a package (blocked by default) | `name`, `manager` |
| `ping_host` | Ping a host 4 times | `host` |
| `traceroute` | Trace the path to a host (15 hops) | `host` |
| `wifi_scan` | Nearby Wi-Fi networks via nmcli | — |
| `public_ip` | WAN IP via echo service (opt-in) | — |
| `firewall_status` | ufw status, or on/off (confirmed) | `action` |
| `describe_screenshot` | Describe an image with the local vision model (opt-in) | `path` |
| `ocr_image` | Extract text from an image (Tesseract) | `path` |
| `email_read` | Recent IMAP messages (read-only, opt-in) | `limit`, `mailbox` |
| `email_send` | Send email via SMTP (confirmed, opt-in) | `to`, `subject`, `body` |
| `calendar_list` | Upcoming events from local .ics files | `limit` |
| `calendar_create_event` | Append an event to calendar.ics (confirmed) | `summary`, `start`, `end`, `description` |
| `note_write` | Save a markdown note (confirmed) | `title`, `content` |
| `note_list` | List saved notes | — |
| `note_search` | Keyword-search the notes | `query` |
| `rule_add` | Create "if X then Y" rule (confirmed once) | `name`, `condition`, `action` |
| `rule_list` | List the automation rules | — |
| `rule_remove` | Delete an automation rule (confirmed) | `rule_id` |
| `rule_set_enabled` | Arm/pause a rule (disabling confirmed) | `rule_id`, `enabled` |
| `run_subagent` | Delegate to researcher / coder / reviewer | `agent`, `task` |
| `subagent_list` | List the available subagents | — |
| `agent_create` | Create a durable background agent session | `name`, `goal`, `schedule`, `tools`, `budget`, `task_type` |
| `agent_list` | List background agent sessions | — |
| `agent_status` | Session state, budget usage, activity | `name` |
| `agent_send` | Wake a session / answer an approval gate | `name`, `message` |
| `agent_pause` | Cancel queued jobs + mark paused | `name` |
| `agent_resume` | Clear paused + queue a resume job | `name` |
| `agent_kill` | Permanently terminate a session (confirmed) | `name` |
| `agent_log` | Append-only audit trail | `name`, `limit` |
| `git_status` | Working-tree status + recent history | `repo` |
| `git_log` | Recent commits, one line each | `repo`, `limit` |
| `git_diff` | Unstaged or staged diff (capped) | `repo`, `staged` |
| `git_branch` | List/create/switch/delete branches | `repo`, `action`, `name` |
| `git_add` | Stage files (confirmed) | `repo`, `paths` |
| `git_commit` | Create a commit (confirmed) | `repo`, `message`, `add_all` |
| `git_stash` | List/push/pop stashes | `repo`, `action`, `message` |
| `git_commit_message` | LLM-drafted commit message from the diff | `repo`, `staged` |
| `control_volume` | Volume up/down/mute | `action` |
| `get_system_stats` | CPU/RAM/battery | — |
| `lock_screen` | Lock the desktop | — |
| `play_media_control` | Play/pause/next/previous | `action` |

**`sopno/tools/registry.py`** — maps schema names → Python functions.

- `_REGISTRY` dict (name → callable) importing each skill from `builtins/`.
- `execute_tool(name, arguments)` — runs a registered tool, spreading the argument
  dict; wraps errors into friendly spoken strings.
- `register_tool(name, fn)` / `unregister_tool(name)` — dynamic tools (plugins,
  MCP clients) extend the registry at runtime; `is_builtin(name)` distinguishes
  them from the static base set.
- `get_registered_names()` — list of registered tools.

**`sopno/tools/schema.py`** — JSON schemas for the LLM.

- `TOOLS_SCHEMA` — the static base list; `register_schema()` /
  `unregister_schema()` append/remove dynamic tool schemas at runtime.
- `get_schema()` — base + dynamic snapshot; **the assistant prompt always uses
  this** so plugin/MCP tools are visible to the LLM from the first turn.

**`sopno/tools/plugins.py`** — dynamic plugin loader (opt-in via
`plugins_enabled`).

- Discovers `plugins/<name>/plugin.py` (or standalone `plugins/<name>.py`).
- Module contract: `plugin_tools() -> {tool_name: (fn, schema) | {"fn": …,
  "schema": …, "confirm": bool}}`, plus optional `on_load()` / `on_unload()`,
  `PLUGIN_NAME`, `PLUGIN_CONFIRM`.
- Every tool registers as `<plugin>_<tool>` + its schema (namespaced, no
  collisions); `confirm: true` tools park a pending-action Yes/No gate.
- Default-deny: plugins get no implicit powers — they can't bypass the file
  roots, terminal blocklist, or confirmation system.

**`sopno/tools/mcp_client.py`** — Sopno as an MCP *client* (opt-in via
`mcp_servers` in config).

- `McpHub(servers)` connects to each configured server over stdio (MCP SDK v2,
  own daemon event-loop thread), lists its tools, and registers each as
  `<server>_<tool>` via `register_tool` + `register_schema`.
- Config shape: `"mcp_servers": {"name": {"command": …, "args": […], "env": {}}}`.
- `refresh()` reconnects/registers; `close()` unregisters and tears down.
- `_format_result` flattens MCP text/error content into a spoken string.

**`sopno/tools/mcp_server.py`** — Sopno as an MCP *server*.

- `build_server()` wraps every registered tool (built-ins + dynamic) into an
  `MCPServer`; run as `python -m sopno.tools.mcp_server` so any MCP host
  (Claude Desktop, Cursor, opencode…) can drive Sopno's skills. Sopno's own
  permission gates still apply on the wire.

**`sopno/tools/builtins/`** — the skills themselves, one file per skill or small
domain, organised into category subpackages (the flat module names remain
importable as `from sopno.tools.builtins import <name>` aliases):

- `system/` — OS-level tools (`system`, `manage`, `desktop`, `media`, `datetime_tool`).
- `files/` — permission-gated file access (`files`, `readers`).
- `dev/` — developer tools (`terminal`, `git`).
- `web/` — internet tools (`browser`, `search`, `network`).
- `data/` — data tools (`databases`, `packages`).
- `knowledge/` — knowledge tools (`vision`, `email`, `calendar`, `notes`).
- `automation/` — proactive tools (`reminders`, `rules`, `subagents`, `agents`, `coding`).

- **`system/system.py`** — OS-level tools.
  - `open_application(app_name)` — launches apps via `subprocess.Popen` using the
    `_APP_MAP` friendly-name → command table (chrome, firefox, files, terminal,
    vscode, spotify, calculator, settings).
  - `control_volume(action)` — `amixer -D pulse sset Master 10%+/10%-/toggle`.
  - `get_system_stats()` — CPU% (`psutil.cpu_percent`), RAM GB used/total, battery
    percent + charging status.
  - `lock_screen()` — `gnome-screensaver-command --lock`, falling back to
    `loginctl lock-session`.
- **`web/search.py`** — `search_web(query)` runs a real multi-engine web search (Bing +
  DuckDuckGo), merging and deduplicating results; `fetch_url(url)` downloads a page
  and extracts readable text (trafilatura, with Jina fallback).
- **`dev/terminal.py`** — real persistent shell access via `cleat` (a headless PTY with
  OSC 133 output structure).
  - `run_terminal(command, timeout)` — runs a shell command; `cd`/`export`/background
    jobs persist between calls (one shared session). Long-running or interactive
    commands return partial output plus the session state.
  - `terminal_send(keys, enter)` — sends stdin / control keys (`ctrl-c`, `ctrl-d`,
    `ctrl-z`) to the running program (REPLs, installers, password prompts).
  - `terminal_status()` — polls the session without sending anything.
  - Safety: destructive/irreversible commands are blocked via a configurable
    `terminal_blocklist` (`config.json`), and `curl|sh`-style pipe-to-shell is
    rejected.
- **`system/manage.py`** — process / service / log / cron management, all routed through
  the shared terminal session (so blocklist + privilege rules apply).
  - `list_processes(query, limit)` — `ps aux --sort=-%cpu`, optional keyword filter.
  - `kill_process(target, signal)` — `kill` by PID or `pkill -x` by name; refuses
    kernel/init, systemd/sopno, and Sopno's own shell session.
  - `manage_service(action, service)` — `systemctl --user` start/stop/restart/
    status/enable/disable/reload (no sudo needed for user units).
  - `read_logs(source, unit, lines)` — `journalctl --user/--system` (+ optional
    unit) or `tail` of an absolute log file path.
  - `manage_cron(action, schedule, command)` — list / add / remove crontab jobs
    (installed non-interactively via a temp file); refuses blocked commands and
    validates the schedule.
- **`files/files.py`** — permission-gated file & folder access.
  - `read_file(path, lines)` — file contents (head/tail supported), capped output;
    PDFs/images/Office docs auto-route to the binary readers.
  - `write_file(path, content)` — create or overwrite; identical writes short-circuit.
  - `edit_file(path, old_string, new_string)` — exact-string replace; `old_string`
    must occur exactly once (read-before-edit invariant, re-checked before writing).
  - `list_directory(path)` — sorted entries with type + size (defaults to project root).
  - `delete_file(path)` — remove a single file (folders never deleted).
  - `rename_file(path, new_path)` / `move_file(path, new_path)` — move/rename;
    never overwrites an existing target.
  - `copy_file(path, new_path, overwrite)` — duplicate a file or a whole folder;
    refuses to overwrite unless `overwrite=true`.
  - `search_files(query, path, mode)` — `name` (fnmatch glob or substring over
    file names) or `content` (regex/plain-text grep returning `path:line` hits).
    Skips blocked paths and binary files; results capped by
    `file_search_max_results` (default 50), 5000 files scanned max.
  - **Permission gate** (`_authorize`), applied to every operation in order:
    1. master switch `file_enabled`; 2. absolute resolved (symlink-safe) path;
    3. secret deny-list `file_blocked_paths` (`.env`, `.git`, `.ssh`, `*.pem`,
    `config.json`, `sopno/memory/memory.db`, …); 4. allowed roots
    `file_allowed_read` / `file_allowed_write` (default: project root).
  - **Confirmation**: writes/edits/deletes/renames/copies park a pending action and
    return a Yes/No prompt; the assistant asks the user (spoken in voice mode, typed
    in text mode) and resolves via `pending_action()` / `resolve_pending()` in
    `core/assistant.py`. Disable with `file_confirm_writes: false`.
- **`files/readers.py`** — binary document readers used by `read_file` (all optional).
  - `extract_text(path) -> (text, method)` routes by suffix: `.pdf` (PyMuPDF native
    text, OCR fallback for scanned pages), images `.png/.jpg/…` (Tesseract OCR),
    `.docx/.pptx/.xlsx` (python-docx/python-pptx/openpyxl), legacy `.doc/.xls/.ppt`
    via `libreoffice --headless --convert-to txt`. Capped by `readers_max_pages`
    (20) / `readers_max_chars` (20000); OCR gated by `file_ocr_enabled`.
  - `is_binary_like(path)` — document suffix or null-byte sniff, used by
    `read_file` routing and `search_files` skipping.
- **`automation/reminders.py`** — one-shot reminders (SQLite + background poller).
  - `set_reminder(when, text)` — `parse_when` turns natural language ("in 10
    minutes", "9:30pm", "tomorrow 9am", "2026-08-20 14:30") into a due time;
    non-destructive (no confirmation). Caps: `reminders_max` pending (50),
    `reminders_max_horizon_days` (365).
  - `list_reminders()` — upcoming pending + recent finished reminders.
  - `cancel_reminder(id)` — cancels a pending reminder by id.
  - Backing store: `sopno/core/reminders.py` — `ReminderStore` (own SQLite DB,
    WAL, `pending → delivered | cancelled`), `parse_when`/`format_due`, and
    `ReminderPoller` (daemon thread, every `reminders_poll_seconds`, atomic
    at-least-once delivery into the reply flow; enabled by `reminders_enabled`).
- **`web/browser.py`** — browser automation via Playwright (**opt-in**, heavy dep).
  - Lazy singleton `BrowserSession`; if `browser_enabled` is false or Playwright
    isn't installed, every tool answers with a friendly message.
  - `browser_navigate(url)` — adds `https://` if needed, refuses domains outside
    `browser_allowed_domains`, returns a cheap **text snapshot** (title + body +
    `[0] …`-indexed interactive elements) instead of screenshots.
  - `browser_click(selector, index)` — CSS selector, or snapshot index when the
    selector is empty; `browser_type(selector, text)` fills inputs (defaults to
    the first visible input); `browser_extract(selector)` reads a region;
    `browser_back()` returns a fresh snapshot.
  - `browser_screenshot(path, full_page)` — writes inside the file **write
    roots** (`files._authorize`); overwriting an existing file parks a pending
    action and asks Yes/No.
  - `browser_close()` — tears down the shared session.
  - Security: `image/media/font` requests are aborted (token/bandwidth savings);
    per-step `browser_timeout` (30s) and whole-session `browser_task_limit`
    (120s) ceiling; page content is treated as untrusted (no prompt-injection
    into actions).
- **`system/desktop.py`** — desktop control + hardware reads, **X11-first** with honest
  degradation: every dependency is optional and detected at runtime via
  `shutil.which` (missing binaries → friendly "install X" messages instead of
  crashes). Input/window/clipboard tools check `_gate(x11=True)`, which refuses
  on Wayland while `desktop_require_x11` is true.
  - `clipboard_get()` / `clipboard_set(text)` — `xclip`/`xsel`; setting is a
    pending-action confirmation.
  - `take_screenshot(path, region)` — `scrot` (or `maim`), `X,Y,W,H` regions
    (`scrot -a` / `maim -g`); writes only inside the file write roots
    (`files._authorize`) and overwrites are confirmed.
  - `list_windows()` / `focus_window(title)` — `wmctrl -l` / `wmctrl -a`.
  - `send_keys(text)` / `press_key(combo)` — `xdotool`; both confirmed, and
    combos containing shell metacharacters (`;|&&`$`) are rejected outright.
  - `get_disk_stats()` — psutil partitions/usage + `sensors_temperatures` +
    `sensors_fans` (snap/loop mounts filtered); `get_network_stats()` — per-NIC
    RX/TX; `get_gpu_stats()` — pynvml (`import pynvml` inside the call, so no
    hard dependency), reports name/util/VRAM/temp or "No NVIDIA GPU detected".
  - `open_application` (in `system/system.py`) honours `desktop_allowed_apps` when the
    list is non-empty, and `get_system_stats` now appends disk + CPU temperature.
- **`data/databases.py`** — read-only SQLite first.
  - `query_database(path, sql)` — reads (SELECT/PRAGMA/EXPLAIN/WITH) run
    immediately on a `file:…?mode=ro` URI connection; mutating statements park
    a pending-action Yes/No gate and execute on a read-write connection when
    approved. Output capped at 30 rows with truncated cells; paths must pass
    `files._authorize(path, "read")` (read-roots + blocked-paths apply).
  - `explain_schema(path)` — tables + columns + row counts from `sqlite_master`.
  - `backup_database(path, destination)` — live consistent copy via the SQLite
    backup API (safe for in-use DBs); destination must be inside the write
    roots, overwrite confirmed, default `<name>.backup.db`.
- **`data/packages.py`** — package management, every action confirmed.
  - `install_package(name, manager)` — `auto` detects apt/pacman/dnf from
    `/etc/os-release` (fallback pip); explicit managers include flatpak.
    System managers wrap in `sudo -n` (non-interactive — never hangs, fails
    with a clear "sudo may need your password" hint). Runs through the shared
    terminal (`_run_command_raw`), so the safety blocklist applies.
  - `uninstall_package(name, manager)` — **blocked by default**
    (`packages_uninstall_allowed = false`), confirmed when enabled.
  - Names validated against a safe character set (no shell metacharacters, no
    `..`, length caps).
- **`web/network.py`** — networking, read-only by default.
  - `ping_host(host)` (`ping -c 4`), `traceroute(host)` (`traceroute -m 15`,
    friendly message if not installed), `wifi_scan()` (`nmcli`), and
    `firewall_status()` (`ufw status verbose`) are harmless reads.
  - `public_ip()` calls `curl https://api.ipify.org` (ifconfig.me fallback) and
    is **disabled unless `network_public_ip_enabled = true`**.
  - `firewall_status("on"/"off")` is the only mutating path — confirmed and run
    via `sudo -n ufw <action>`. Host arguments are strictly validated.
- **`knowledge/vision.py`** — image understanding.
  - `describe_screenshot(path)` — **opt-in** (`vision_enabled` + `vision_model`,
    e.g. `qwen2.5vl:7b`); reads the image bytes, base64-encodes them as a
    `data:` URI, and POSTs to Ollama's `/api/chat`. Gated by the file read
    roots and an 8 MB cap; friendly "vision is off" message otherwise.
  - `ocr_image(path)` — pytesseract first, then a `tesseract <file> stdout`
    subprocess fallback; a clear install hint when neither exists.
- **`knowledge/email.py`** — **opt-in only** (`email_enabled`). Passwords never live in
  config.json — they come from the env var named by `email_password_env`
  (default `SOPNO_EMAIL_PASSWORD`).
  - `email_read(limit, mailbox)` — read-only IMAP4_SSL, lists the newest
    messages as subject / from / plain-text snippet.
  - `email_send(to, subject, body)` — SMTP + STARTTLS, **confirmed**; recipient
    is validated against a safe charset, subject must be one line, body capped.
- **`knowledge/calendar.py`** — file-based ICS, no external service.
  - `calendar_list(limit)` — parses `BEGIN:VEVENT` blocks out of every `.ics`
    under `calendar_dir` (datetime regex `YYYYMMDD[T]HHMMSS[Z]` or date-only)
    and lists the upcoming ones, sorted by start time.
  - `calendar_create_event(summary, start, end, description)` — accepts
    `YYYY-MM-DD HH:MM` input, builds an escaped VEVENT and appends it to
    `calendar.ics` (write-root gated + confirmed; creates the VCALENDAR
    wrapper on first use).
- **`knowledge/notes.py`** — markdown knowledge base under `notes_dir`
  (default `sopno/memory/notes`).
  - `note_write(title, content)` — sanitised title → `<title>.md`; confirmed,
    with a separate overwrite confirmation.
  - `note_list()` — names + sizes + mtimes; `note_search(query)` — read-only
    case-insensitive grep returning matching line snippets.
- **`automation/rules.py`** — automation rules ("if X then Y"), backed by
  `sopno/core/rules.py`.
  - `rule_add(name, condition, action)` — condition is an allowlist grammar
    `metric op value` (metrics: `battery_percent`, `cpu_percent`, `ram_percent`,
    `disk_free_gb`, `hour_of_day`, `day_of_week`; ops `< <= > >= ==`) — never
    eval-ed. Action is a tool call like `open_application app="Files"`,
    validated against the registry. Confirmed once; on fire the action's
    pending-action gate (if any) is auto-approved.
  - `rule_list()` read-only; `rule_remove(id)` and
    `rule_set_enabled(id, enabled)` confirmed.
- **`automation/subagents.py`** — delegate to focused workers, backed by
  `sopno/core/subagents.py`.
  - `run_subagent(agent, task)` — researcher (search/fetch/read), coder
    (files/git/terminal), or reviewer (read-only files/git/logs). Each has a
    focused system prompt and a **restricted** `TOOLS_SCHEMA`; runs the same
    Ollama tool-calling loop as the main assistant and returns plain text.
  - `subagent_list()` — names of the available subagents.
- **`automation/agents.py`** — durable background agent management, backed by
  `sopno/core/agents/` (sessions, queue, scheduler, events, worker, runtime).
  - `agent_create(name, goal, schedule?, tools?, budget?, task_type?)` — create a
    session (`task_type` = `general` | `coding`) and put it `ready`; validates
    the schedule spec, tool allowlist, and budget keys.
  - `agent_list()` / `agent_status(name)` — state, goal, budget usage, recent
    activity, pending input.
  - `agent_send(name, message)` — wake a parked/dormant session (the approval
    channel: "yes" approves, anything else declines).
  - `agent_pause(name)` — cancel queued jobs + mark paused; `agent_resume(name)`
    — clear paused + queue a resume job.
  - `agent_kill(name)` — permanently terminate (confirmation gate); cancels
    jobs and clears the schedule.
  - `agent_log(name, limit)` — append-only audit trail (actions, messages,
    transitions, errors).
  - `agent_align(name, correction)` — append a correction/preference to the
    agent's alignment record (drives ORIENT context and the periodic REFLECT).
- **`automation/coding.py`** — the background coding-agent entry points, backed
  by `sopno/core/coding/` (harness) + `sopno/core/agents/` (session/queue).
  - `coding_run(goal | tickets=[…], name?, ...)` — start a coding agent: single
    `goal` or a batch of `tickets` (each `{goal, name?, schedule?, verify_recipe?,
    coding_approval_mode?}`). Creates a `kind='coding'` session (transition
    `ready`) and enqueues a `run` job with an idempotency key; returns the
    session + queued status.
  - `coding_status(name?)` — state + branch: parses the durable
    `[coding-worktree] {…}` marker from the session's working memory so a fresh
    context can see which branch a live coding run is on.
- **`dev/git.py`** — git repository tools, all routed through the shared terminal
  session (`git -C <repo> …`, color forced off) so the blocklist applies and any
  repository can be addressed explicitly.
  - `git_status(repo)` — `git status --short --branch` + last 10 commits.
  - `git_log(repo, limit)` — `git log --oneline -n N` (clamped 1-50).
  - `git_diff(repo, staged)` — working-tree or staged diff, capped by
    `git_max_diff_chars`.
  - `git_branch(repo, action, name)` — list (`branch -a`), create, switch
    (`checkout`), or delete (`branch -d`, confirmed). Branch names are validated.
  - `git_add(repo, paths)` — stage files via `git add -- …` (confirmed).
  - `git_commit(repo, message, add_all)` — `git commit -m`, optionally after
    `git add -A` (confirmed).
  - `git_stash(repo, action, message)` — list / push / pop (push and pop confirmed).
  - `git_commit_message(repo, staged)` — read-only; feeds the diff to the local
    LLM and returns a conventional `type(scope): summary` + body suggestion.
  - Values interpolated into git arguments are shlex-quoted and checked against
    shell metacharacters; the `git_enabled` master switch is in `config.json`.
- **`system/datetime_tool.py`** — `get_current_time()` returns e.g.
  "It is 09:41 AM on Thursday, August 13."
- **`system/media.py`** — `play_media_control(action)` controls media players via
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
  methods. `position_hud()` pins it to the top-right of the screen. The `≡`
  chrome button toggles the read-only `DashboardPanel`.
- **`dashboard.py`** — `DashboardPanel(QTabWidget)`: six read-only tabs backed
  by the same live objects the CLI uses — **Settings** (`config.json` + the
  runtime `settings` snapshot, secret-looking values masked), **Memory**
  (`MemoryStore.stats()` + top memories), **Tools** (all `get_registered_names()`),
  **Logs** (live stream fed by the worker's `log_message` signal via
  `append_log`), **Models** (Ollama `list()`, guarded), and **Agents** (a
  lazy-imported status list of background agents + any live coding branch from
  `_coding_record`). `refresh()` re-reads the static tabs each time the panel
  is shown.
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

Unit tests using Python's standard `unittest` library, organised into
subpackages that mirror the codebase (each directory is a package, so
`unittest discover` recurses into it). Run with:

```bash
python3 -m unittest discover -s tests
```

| Subpackage / file | What it verifies |
|------|------------------|
| `voice/` | Audio stack: `test_tts.py` (`_is_bangla()` + engine routing), `test_stt.py` (Whisper-first, Google fallback only when enabled), `test_wakeword.py` (fallback + lazy detector), `test_barge.py` (interrupt logic) |
| `core/` | Brain: `test_assistant.py` (context lifecycle + dispatcher routing), `test_memory.py`, `test_semantic.py`, `test_researcher.py`, `test_reminders.py`, `test_rules.py`, `test_subagents.py`, `test_agents.py` (session + queue), `test_agent_scheduler.py` (triggers + events), `test_agent_sources.py` (file watcher + webhook wake), `test_agent_worker.py` (worker loop + reflect + coding bridge), `test_agent_runtime.py` (lifecycle + reclaim + sources), `test_agent_tools.py` (agent + coding management tools), `test_coding.py` (coding harness loop + escalation + auto-merge + batch) |
| `tools/` | One file per skill: `test_browser.py`, `test_calendar.py`, `test_databases.py`, `test_desktop.py`, `test_email.py`, `test_files.py`, `test_git.py`, `test_manage.py`, `test_network.py`, `test_notes.py`, `test_packages.py`, `test_readers.py`, `test_terminal.py`, `test_vision.py` |
| `integration/` | Cross-cutting: `test_mcp.py` (client/server), `test_plugins.py` (dynamic loader) |
| `test_tools.py` | Registry-level checks (all registered tools present, tool output formats, subprocess call wiring) |

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
| `terminal_enabled` | `true` | Master switch for terminal access (`run_terminal` & co.) |
| `terminal_shell` | `/bin/bash` | Shell binary for the persistent PTY session |
| `terminal_timeout` | `30` | Default seconds `run_terminal` waits for completion |
| `terminal_max_timeout` | `300` | Hard cap on a single `run_terminal` wait |
| `terminal_output_chars` | `4000` | Output chars shown to the LLM per call (tail kept) |
| `terminal_blocklist` | *(destructive patterns)* | Lowercase substrings that are blocked from execution |
| `desktop_enabled` | `true` | Master switch for the desktop tools (clipboard/windows/keys/screenshot/hardware) |
| `desktop_allowed_apps` | `[]` | When non-empty, `open_application` only launches apps in this list |
| `desktop_require_x11` | `true` | When true, input/window/clipboard tools refuse on Wayland |
| `database_enabled` | `true` | Master switch for the SQLite database tools |
| `packages_enabled` | `true` | Master switch for the package tools |
| `packages_uninstall_allowed` | `false` | Allow `uninstall_package` (still confirmed) |
| `packages_require_sudo` | `true` | Wrap apt/pacman/dnf in `sudo -n` |
| `network_enabled` | `true` | Master switch for the network tools |
| `network_public_ip_enabled` | `false` | Allow `public_ip` to call a WAN echo service |
| `vision_enabled` | `false` | Enable `describe_screenshot` (needs a vision model) |
| `vision_model` | `""` | Ollama vision model, e.g. `qwen2.5vl:7b` |
| `email_enabled` | `false` | Enable the IMAP/SMTP email tools |
| `email_imap_server` | `""` | IMAP host for reading mail |
| `email_smtp_server` | `""` | SMTP host for sending mail |
| `email_user` | `""` | Email account (IMAP + SMTP login) |
| `email_password_env` | `SOPNO_EMAIL_PASSWORD` | Env var that holds the password (never config.json) |
| `calendar_dir` | `sopno/memory/calendar` | Folder of `.ics` calendar files |
| `notes_dir` | `sopno/memory/notes` | Markdown notes folder |
| `rules_enabled` | `true` | Master switch for the automation-rule poller |
| `rules_path` | `sopno/memory/rules.db` | SQLite DB holding the rules |
| `rules_poll_seconds` | `60` | How often the `RulePoller` checks conditions |
| `subagents_enabled` | `true` | Allow `run_subagent` |
| `subagents_max_turns` | `4` | Cap on tool-calling iterations per subagent |
| `agents_enabled` | `true` | Master switch for the long-running-agent machinery |
| `agents_path` | `sopno/memory/agents.db` | SQLite DB for sessions + queue |
| `agents_max_sessions` | `20` | Cap on stored sessions |
| `agents_concurrency` | `2` | Max sessions running at once |
| `agents_lease_seconds` | `300` | Claim lease length (heartbeat renews it) |
| `agents_backoff_base` | `5` | Base (s) for failed-job exponential backoff |
| `agents_backoff_cap` | `3600` | Backoff ceiling (s) |
| `agents_max_attempts` | `3` | Attempts before a job is dead-lettered |
| `agents_poll_seconds` | `30` | How often `AgentScheduler` checks triggers |
| `agents_worker_poll_seconds` | `2` | How often `AgentWorker` polls the queue for jobs |
| `agents_job_max_turns` | `20` | Per-job agent-loop turns before dormancy |
| `agents_watchdog_seconds` | `300` | How often `AgentRuntime` reclaims stale sessions |
| `agents_file_watches` | `[]` | Directories a `FileWatcher` polls; each `{"path", "agent", "message"?, "recursive"?}` |
| `agents_file_poll_seconds` | `10` | How often the `FileWatcher` rescans watched dirs |
| `agents_webhook_host` | `127.0.0.1` | Host the webhook server binds to |
| `agents_webhook_port` | `0` | Port for `POST /webhook` (0 = webhook disabled) |
| `coding_enabled` | `true` | Master switch for autonomous coding |
| `coding_worktree_dir` | `sopno/memory/worktrees` | Where coding worktrees live |
| `coding_max_turns` | `150` | Cap on coding-loop turns |
| `coding_max_tokens` | `300000` | Token budget per run |
| `coding_max_wall_minutes` | `120` | Wall-clock budget per run |
| `coding_max_diff_lines` | `800` | Line budget per run (stall + stop) |
| `coding_stall_rounds` | `6` | No-progress rounds before the run stalls |
| `coding_approval_mode` | `review_required` | How a run ends: `review_required` (pauses on `escalate`, gates success on review) · `auto_merge_guardrailed` (self-reviews, then auto-merges into main if the merged tree stays green) · `unattended` (records escalations, leaves the branch, never merges) |
| `coding_protected_paths` | `[config.json, sopno/memory, .git]` | Paths the coding agent may never write |
| `coding_require_red_test` | `true` | Run the recipe on `main` at setup; a green baseline appends a RED-FIRST advisory |
| `coding_push_enabled` | `false` | Allow pushing branches (`git_push_enabled` also required) |

---

## 9. How to Extend Sopno

Because the project is modular, most changes are local and low-risk:

**Add a new tool (skill)**
1. Create `sopno/tools/builtins/<category>/your_tool.py` (drop it into the most
   fitting category subpackage — `system/`, `files/`, `dev/`, `web/`, `data/`,
   `knowledge/`, or `automation/`) with a function that returns a short, speakable
   string, then add it to that category's `__init__.py` so it is re-exported.
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


