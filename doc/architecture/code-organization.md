# Sopno — Code Organization & File Size Standard

> **Date:** 2026-08-13
> **Scope:** File-size guideline, the "sub-package" split pattern, and a concrete
> decomposition plan for files that have outgrown the limit.
> **Rule of thumb:** a source file should be **300–400 lines**. Over 400 = plan a
> split. Over 500 = split now.

---

## 1. Why this standard exists

Long files are the first sign of a module doing too many jobs. When a file grows
past ~400 lines, one of these is usually true:

1. It mixes **several unrelated responsibilities** (layout, drawing, threading,
   config, boot code all in one file).
2. It keeps **separator comments** like `# ── Icon painting ──` that are really
   "this should be a module".
3. Every change touches the same file, so the whole team (or the same person a
   week later) fights over one edit surface.

The goal of the 300–400 line rule is **not** a magic number. It is a tripwire
that forces a conversation: *"What is this file actually responsible for?"*

### Grounding from industry practice

- Most modern Python guidance treats **~400–600 lines** as the practical ceiling
  before a module needs splitting; multiple well-known projects adopt **600 lines**
  as the hard trigger.
- The safest trigger for a *small personal project* is stricter: **400 lines**.
- Splitting is **by responsibility, never by line count alone**. Moving 50 lines
  into a `utils.py` just to shorten a file is how "junk-drawer" utilities are born.

---

## 2. The core rules

### Rule 1 — One file = one job

Each module answers one question:

| File | Job |
|------|-----|
| `sopno/ui/icons.py` | Draws vector icons only |
| `sopno/ui/window.py` | Builds and drives the HUD window |
| `sopno/voice/stt/whisper.py` | Talks to faster-whisper only |
| `sopno/voice/stt/filters.py` | Judges if a transcript is real speech |

### Rule 2 — No junk-drawer `utils.py`

A shared helper belongs in `utils/` **only if** all of these are true:

- It is **stateless** (pure function).
- It is **generic** — it would work unchanged in an unrelated project.
- It is used by **2+ packages**.

Anything else stays next to the domain that owns it. For example
`_is_babble()` is STT-specific — it lives in `stt/`, never in a shared utils file.

If a small shared module is justified later, use **purpose-built** names, not one
monolith:

```
sopno/utils/
├── __init__.py
├── lang.py        # has_bangla(), has_latin() — used by stt + assistant
└── text.py        # strip_markdown_junk(), collapse_whitespace()  (future)
```

### Rule 3 — The sub-package pattern (module → package)

This is the standard way to split a Python module without breaking callers:

1. Rename `module.py` into a **directory** `module/`.
2. Move each responsibility into its own file inside it.
3. Add `__init__.py` that **re-exports the public API**.
4. **Callers never change** — `from sopno.ui.hud import run_hud` keeps working.

```python
# sopno/ui/hud/__init__.py
"""Public API of the HUD package. Imports elsewhere must not change."""
from sopno.ui.hud.window import SopnoHUDWindow
from sopno.ui.hud.run import run_hud  # or keep run_hud() here directly

__all__ = ["run_hud", "SopnoHUDWindow"]
```

### Rule 4 — Dependencies flow one way

Keep this direction to avoid circular imports:

```
utils  →  config  →  voice / llm / tools  →  core  →  ui
```

If module A needs something from B and B needs something from A, **extract the
shared bit into a third module C** that both import. Never break the cycle with
lazy `import` inside a function unless it is a last resort.

### Rule 5 — Private helpers get an underscore

Internal functions that are not part of the public API start with `_`. When
moving code, first decide what the public entry point of each new module is;
everything else becomes `_private` within that module.

---

## 3. Current state audit (2026-08-13)

| File | Lines | Verdict |
|------|------:|---------|
| `sopno/ui/hud.py` | **1509** | 🔴 split now |
| `sopno/voice/stt.py` | **422** | 🟠 split |
| `sopno/core/assistant.py` | 390 | 🟢 within limit; extract only if it grows |
| `sopno/voice/listener.py` | 269 | 🟢 ok |
| `sopno/voice/vad.py` | 264 | 🟢 ok |
| `sopno/voice/wakeword.py` | 175 | 🟢 ok |
| everything else | ≤ 120 | 🟢 ok |

**Target after refactor:** every production file ≤ ~400 lines, most in the
200–350 range.

### 3.1 Audit after refactor (2026-08-13)

`hud.py` and `stt.py` were converted to packages (steps 1–4 below). Largest
files now:

| File | Lines | Verdict |
|------|------:|---------|
| `sopno/core/assistant.py` | ~606 | 🟡 grew with barge-in; split if it passes ~700 |
| `sopno/ui/hud/window.py` | 321 | 🟢 ok |
| `sopno/ui/hud/widgets/robot.py` | 233 | 🟢 ok |
| `sopno/ui/hud/widgets/chat.py` | ~170 | 🟢 ok |
| `sopno/ui/hud/behaviors/chrome.py` | ~100 | 🟢 ok |
| `sopno/voice/stt/whisper.py` | 206 | 🟢 ok |
| `sopno/voice/barge.py` | ~130 | 🟢 ok |
| everything else | ≤ 155 | 🟢 ok |

The hud migration below is **✅ done** (see `doc/roadmap/status.md` Step 7):
hud now lives in `behaviors/` + `widgets/` + `visuals/` subfolders, and the
hot-reload watcher watches the whole package via `rglob("*.py")`.

---

## 4. Migration plan — `sopno/ui/hud.py` (1509 lines)

> **Status: ✅ completed** (2026-08-14). Kept below for reference; the live
> structure is described in `doc/CODEBASE.md` §6.6.

### 4.1 What it actually contains

| Lines | Symbol | Responsibility |
|-------|--------|----------------|
| 66–150 | `SIZE_PRESETS`, `MIN_SIZE`, `MAX_SIZE`, `EDGE`, `STATUS_COPY`, `STATE_ACCENT`, `_CHROME`, `_TOOL_ICON`, `_SEGMENT`, `_ICON_BTN` | Constants & QSS templates |
| 155–224 | `_paint_icon()` | Vector icon painter |
| 228–445 | `AliveRobotFace` | Animated robot face (drawing + animation timer) |
| 449–561 | `ModeToggle` | Voice/Text segmented control |
| 564–699 | `ChatThread` | Scrollable chat bubbles |
| 702–738 | `AssistantWorker` | QObject signals bridging `SopnoAssistant` → UI |
| 741–1447 | `SopnoHUDWindow` | Window, layout, resize, tray, responsive scaling |
| 1450–1482 | `_watch_paths_for_reload`, `_restart_process`, `_install_hot_reload` | `--reload` dev helper |
| 1485–1505 | `run_hud()` | Entry point + hot-reload wiring |

### 4.2 Target structure

```
sopno/ui/
├── __init__.py          # re-export run_hud() → callers unchanged
├── cli.py               # (existing, untouched)
├── hud/                 # NEW package (replaces hud.py)
│   ├── __init__.py      # from .window import SopnoHUDWindow; from .run import run_hud
│   ├── theme.py         # constants + QSS templates  (~85 lines)
│   ├── icons.py         # _paint_icon()             (~70 lines)
│   ├── robot.py         # AliveRobotFace            (~220 lines)
│   ├── widgets.py       # ModeToggle + ChatThread   (~250 lines)
│   ├── worker.py        # AssistantWorker           (~40 lines)
│   ├── window.py        # SopnoHUDWindow            (~700 lines → see 4.3)
│   └── run.py           # run_hud() + hot-reload    (~65 lines)
```

### 4.3 `window.py` is still ~700 lines — split it again

`SopnoHUDWindow` genuinely is the largest single class. It has three separable
jobs, so split the class's *helpers*, not the class:

| Extract to | Contents | Lines saved |
|------------|----------|-------------|
| `hud/responsive.py` | `_metrics_for_width()`, `_apply_responsive()`, `_refresh_size_chips()`, `apply_size_preset()` | ~140 |
| `hud/resizing.py` | `_edge_at()`, `_cursor_for_edge()`, `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent` | ~90 |
| `hud/tray.py` | `init_tray()`, `on_tray_activated()`, `hide_hud()`, `restore_hud()` | ~50 |
| `hud/status.py` | `update_status()`, `update_user_speech()`, `update_sopno_reply()`, `update_log()` | ~40 |
| `hud/chrome.py` | `_chrome_btn()`, `_circle_btn()`, `_style_listening_chip()`, `send_text_message()`, `_toggle_listening_mode()` | ~100 |

Two clean ways to apply this:

- **Option A (preferred): mixins.** `SopnoHUDWindow(HudMixinResize, HudMixinTray, ...)`. Each mixin defines the extracted methods using `self` attributes.
- **Option B (simpler): module-level helper functions** taking `self`-like state (`def _apply_responsive(win) -> None`). Slightly less idiomatic, less indirection.

After the extraction `window.py` holds the constructor, `init_ui()` and
`set_interaction_mode`/`set_listening_mode` wiring — ~300 lines.

### 4.4 Caller compatibility

| Caller | Today | After |
|--------|-------|-------|
| `main.py:53,63` | `from sopno.ui.hud import run_hud` | **unchanged** (re-exported) |
| hot-reload watcher | watches `root / "hud.py"` | must watch the whole `root / "hud"` directory — update `_watch_paths_for_reload` in `run.py` |

---

## 5. Migration plan — `sopno/voice/stt.py` (422 lines)

### 5.1 What it actually contains

| Lines | Symbol | Responsibility |
|-------|--------|----------------|
| 29–46 | `HF_HUB_DISABLE_TELEMETRY`, whisper singleton globals, `_HALLUCINATIONS` | Module state |
| 49–115 | `_whisper_download_root()`, `_get_whisper()`, `_whisper_lang()` | Whisper model loading |
| 118–176 | `_is_junk()`, `_is_babble()`, `_has_bangla()`, `_has_latin()`, `_is_supported_utterance()` | Transcript filters |
| 180–246 | `_score_result()`, audio checks, `_is_too_thin()` | Scoring & audio sanity |
| 249–355 | `_transcribe_whisper()` | Whisper transcription + retry logic |
| 358–398 | `_transcribe_google()` | Online Google fallback |
| 401–422 | `transcribe()` | **Public entry point** |

### 5.2 Target structure

```
sopno/voice/stt/
├── __init__.py      # re-export transcribe()
├── whisper.py       # _whisper_download_root, _get_whisper, _whisper_lang, _transcribe_whisper  (~110)
├── filters.py       # _is_junk, _is_babble, _has_bangla, _has_latin, _is_supported_utterance  (~60)
├── scoring.py       # _score_result, audio checks, _is_too_thin, thresholds  (~80)
└── google.py        # _transcribe_google  (~45)
```

`transcribe()` (the public API) lives in `__init__.py` and imports the pieces:

```python
# sopno/voice/stt/__init__.py
from sopno.voice.stt.google import _transcribe_google
from sopno.voice.stt.whisper import _transcribe_whisper
from sopno.config.settings import settings

def transcribe(recognizer, audio, language=None):
    ...  # current fallback logic, unchanged

__all__ = ["transcribe"]
```

### 5.3 Test compatibility — important subtlety

`tests/test_stt.py` currently patches **module attributes**:

```python
@patch("sopno.voice.stt._transcribe_whisper")
@patch("sopno.voice.stt.settings")
```

Because `__init__.py` imports those names into the `sopno.voice.stt` namespace
(and `transcribe()` references them as module globals), these patches **keep
working**. Do **not** move `transcribe()` into `whisper.py` — the patch path would
then be wrong. This is the documented payoff of the sub-package pattern.

### 5.4 Caller compatibility

| Caller | Today | After |
|--------|-------|-------|
| `sopno/core/assistant.py:27` | `from sopno.voice.stt import transcribe` | **unchanged** |
| `sopno/voice/wakeword.py:20` | `from sopno.voice.stt import transcribe` | **unchanged** |
| `tests/test_stt.py` | patches `sopno.voice.stt.*` | **unchanged** |

---

## 6. Migration plan — `sopno/core/assistant.py` (390 lines)

This one is **already within the limit** — do not split it just to split it.
Document here what to extract **if/when it grows** (it is the busiest file in the
project and will cross 400 soon):

| Lines | Symbol | Candidate extraction |
|-------|--------|----------------------|
| 33–42 | `_TOOLISH` regex | `sopno/core/rules.py` |
| 46 | `_POST_SPEAK_SETTLE_S` | keep in `assistant.py` |
| 259–282 | bangla/english keyword lists | `sopno/core/language.py` as `LANG_SWITCH_KEYWORDS` |
| 294–356 | LLM + tool-call section of `_process_command()` | `sopno/llm/chat_session.py` → `run_llm_turn(context, cmd_text, use_tools, log) -> Optional[str]` |
| 141–240 | voice loop body of `_await_command()` | `sopno/core/voice_loop.py` → `capture_command(...) -> Optional[str]` |

**Suggested public helper signatures** (keeps `SopnoAssistant` as a thin
orchestrator):

```python
# sopno/core/language.py
BANGLA_SWITCH = [...]
ENGLISH_SWITCH = [...]
def detect_language(text: str) -> str  # "bn" | "en"

# sopno/llm/chat_session.py
def run_llm_turn(chat_messages, *, use_tools: bool, log: Callable[[str], None]) -> Optional[str]:
    """Appends tool calls/results, returns cleaned assistant reply or None on error."""
```

---

## 7. What NOT to do

1. **Do not create `sopno/utils/utils.py`** and dump `_is_babble` + `_paint_icon`
   + random helpers into it. Helpers stay with their domain.
2. **Do not rename imports in callers.** The whole point of the sub-package
   pattern is zero caller churn (`main.py`, `assistant.py`, `wakeword.py`, tests).
3. **Do not split a 300-line file** just to hit 200. The rule is a ceiling, not a
   target to chase.
4. **Do not move `transcribe()`'s patched internals** without checking
   `tests/test_stt.py` (see §5.3).
5. **Do not forget the hot-reload watcher** in `hud.py` when `hud.py` becomes a
   directory (§4.4).

---

## 8. Verification checklist

Run after **each** extraction step, in order:

```bash
cd /home/madsdev404/Projects/sopno
# 1. No syntax / import errors anywhere
python -m compileall sopno
# 2. Unit tests (need venv deps installed)
./venv/bin/python -m pytest tests -q
# 3. CLI boots far enough to print config / banner (no GUI needed)
./venv/bin/python main.py --cli --exit
# 4. HUD boots (if on a desktop session)
./venv/bin/python main.py --hud --reload
```

Additional checks specific to this refactor:

- [ ] `grep -rn "sopno.ui.hud\|sopno.voice.stt" main.py sopno tests` → all imports
      still resolve.
- [ ] `wc -l` on every new file → none exceed ~400 lines.
- [ ] `python -c "from sopno.ui.hud import run_hud; from sopno.voice.stt import transcribe"`
      imports cleanly.
- [ ] Tests still pass **without editing** `test_stt.py` (proves the API-stability rule).

---

## 9. Suggested execution order

| Step | Work | Depends on |
|------|------|-----------|
| 1 | `sopno/ui/hud/` package — move `theme`, `icons`, `robot`, `widgets`, `worker` | — |
| 2 | `hud/window.py` + mixin extraction (§4.3) | step 1 |
| 3 | `hud/run.py` — move `run_hud()` + hot-reload, fix watcher path | step 2 |
| 4 | `sopno/voice/stt/` package (§5) | — |
| 5 | Extract `assistant.py` helpers **only if it exceeds 400 lines** (§6) | — |

Each step is independently reversible and ends with a green test run.

---

## 10. Progress tracker

| Task | Status |
|------|--------|
| File-size audit (2026-08-13) | ✅ done |
| `sopno/ui/hud/` package split | ✅ done |
| `hud/window.py` mixin extraction | ✅ done |
| `hud/run.py` + hot-reload path fix | ✅ done |
| `sopno/voice/stt/` package split | ✅ done |
| `assistant.py` extraction (only if >400) | ✅ n/a — still 390 lines |
| Doc sync (`doc/architecture/overview.md` folder tree) | ✅ done |

---

## 11. Related docs

- [overview.md](overview.md) — folder structure, module boundaries, "one folder = one job"
- [project-assessment.md](project-assessment.md) — implementation status & priorities
- [observations.md](observations.md) — stack review & upgrade recommendations

---

*Update this file when the plan changes, when a step ships, or when the audit
numbers drift.*
