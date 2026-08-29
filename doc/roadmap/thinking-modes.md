# Sopno Reasoning Modes — Quick / Thinking / Deep / Plan (+ Auto)

**Status: implemented** — core, LLM config, tests, and the approved HUD
selector landed (see §5.6).

**Date**: August 29, 2026
**Scope**: Give the LLM turn-selectable reasoning depth instead of a single
speed-first personality, plus a guarded plan-then-execute flow for multi-step
goals. Core/LLM + approved HUD selector — see §5.6 for the HUD surface.

---

## 1. The Problem

Sopno today has exactly one LLM personality: **fast and literal**.

- `think: false` is hardcoded for hybrid models (huge CPU win).
- `num_predict` is capped (default 120) for terse spoken replies.
- `num_ctx` is small (default 2048).

That is great for voice Q&A but wrong for hard questions:

| Ask … | What should happen | What happens today |
|---|---|---|
| "what time is it?" | instant reply | instant ✔ |
| "should I buy a MacBook or a ThinkPad?" | deliberate reasoning | 120 tokens of shallow opinion |
| "make a plan to build a todo app" | plan steps, then execute each one | a 120-token answer at best |

So the single `llm_think` boolean is a blunt instrument: either every request
"thinks" (slow, verbatim for voice) or none can. **There is no per-depth
budget, and no plan-then-execute path.**

---

## 2. Proposal — Four Selectable Tiers + An Auto Router

Give every conversation turn a **reasoning mode** selected from:

```
    quick    → think:false, tiny budget   (today's default — unchanged)
    thinking → think:true,  medium budget
    deep     → think:true,  large budget  (the "MacBook vs ThinkPad" answer)
    plan     → think:true,  plan steps, confirm, then execute each step
```

Plus `auto`, where the assistant reads the utterance and routes it itself
(deterministic — no extra LLM call):

```
    plan hints   → plan        ("make a plan to …", "set up …", "build …", Bangla)
    deep hints   → deep        ("deep think", "analyze in detail", "debug …", …)
    ≤4 words     → quick       (greetings, one-liners)
    otherwise    → thinking    (the default answer tier)
```

### 2.1 Mode → Request Overrides

| mode | `think` | `num_predict` | `num_ctx` | `temperature` |
|------|---------|---------------|-----------|---------------|
| `quick`   | false | 120 | 2048 | 0.6 |
| `thinking`| true  | 300 | 4096 | 0.6 |
| `deep`    | true  | 800 | 8192 | 0.5 |
| `plan`    | true  | 400 | 4096 | 0.5 |

Defaults live in code (`modes.py`); `config.json` can override them.
`quick` stays byte-for-byte today's request budget.

### 2.2 Deferred slot — per-mode model

Per-mode *model* selection (e.g. `deep → qwen3:14b`) is deliberately left for a
later phase. Each `MODES` entry is future-ready for an optional `"model"` key;
when present, `client.chat()` would use it instead of `settings.model_name`.
Not now.

### 2.3 Options considered (and rejected)

1. **Just raise `llm_think`.** Wrong — applies to every turn; voice replies
   get verbatim CoT; short Q&A slows down. Rejected.
2. **Hack `num_predict` per command.** Works in isolation but leaves `think`
   off and no plan flow. Rejected as too shallow.
3. **LLM-classified auto routing.** Adds a routing round-trip every turn.
   Deterministic hints cost nothing. Rejected.
4. **This proposal.** Deterministic auto routing + 4 concrete tiers. Chosen.

---

## 3. Design

### 3.1 Turn pipeline (override » setting » auto)

A mode is chosen on **every user turn**, in priority order:

1. **Per-turn phrase override** (control words, English + Bangla): the user can
   force a mode per request.
   `"think about …"` → thinking · `"deep think …"` → deep ·
   `"make a plan to …"` → plan · `"quick answer"` → quick.
   Detection order matters: **plan > deep > thinking > quick**. These words are
   *control words*, not conversation — they are stripped before the LLM ever
   sees them (so they don't land in context history or the reply).
2. **Persistent default** from `config.json` → `llm_mode` (default `"auto"`).
3. `auto` resolves the utterance through the deterministic hints above.

Backward compatibility: when `llm_mode` is `auto`, the legacy `llm_think`
toggle still governs whether the "thinking" tier is reachable, so existing
installs keep today's behavior until they opt in. Setting `llm_mode` to a
concrete value supersedes the toggle.

### 3.2 Requesting the LLM (mode awareness)

- `client.chat(..., mode=)` → `_chat_options(mode)` merges the mode's
  `{num_predict, num_ctx, temperature}` with `settings.py` overrides
  (`llm_think_num_predict`/`llm_deep_num_predict`/`llm_deep_num_ctx`).
- `think` is **always sent explicitly** — hybrid models (Qwen3/R1) need the
  flag on every request, not just when it's true.
- Unresolved modes fall back to the quick budget so standalone tool loops stay
  instant.
- `single_reply(messages, *, mode=)` threads the mode through internal calls
  (planner, researcher subagents).
- `stream_mode()` yields `("thinking", …)` chunks before `("answer", …)` — the
  "Cursor feel" the HUD (currently CLI-only) can animate later.
- `message_as_dict()` preserves the model's `thinking` field.

The researcher's `_summarize` inherits the active mode's budget via
`modes.resolve(settings.llm_mode, question)` (`max(...)` keeps its own floor).

### 3.3 Plan mode — plan-then-execute with a confirmation gate

State machine (all in `assistant.py`):

```
 PLAN_ENTRY → PLANNING (single_reply, cheap) → ARTIFACT → GATE → EXECUTE
```

1. **PLANNING** — call the planner (non-streaming `single_reply(mode=plan)`)
   with the directive `prompts/planner.txt` ("at most 5 numbered, executable
   steps … return only the list"). Cheap, no tool calls.
2. **ARTIFACT** — write a reviewable plan to `plans/<slug>-<timestamp>.md`
   (`plan_dir`, gitignored) and render the numbered list.
3. **GATE** — reuse the existing pending-action Yes/No machinery
   (`files._awaiting_confirmation`, spoken in voice mode, typed in text mode).
   `plan_confirm: false` auto-skips the gate.
4. **EXECUTE** — iterate the steps through the *normal* gates: `llm_chat(tools,
   mode=quick)` → `execute_tool` with Sopno's permission/confirmation system
   fully intact. Each step's output is spoken as it finishes. If a step error
   looks fatal (`error|failed|permission denied|off-limits|…`), re-plan the
   remaining steps once (bounded per step) and continue; otherwise keep going.
   Replanning inserts revised steps, never loops forever.

Plan steps never bypass safety: they run as tool-calls with the same
allowlists, blocklists, and confirmations as any LLM request.

### 3.4 Phase plan

- **§5.1** `sopno/llm/modes.py` — `MODES` table + `normalize`/`spec`/`resolve`/
  `_auto_for` + hint regexes (verbatim, below).
- **§5.2** `settings.py` + `config.json` — `llm_mode`, `llm_think_num_predict`,
  `llm_deep_num_predict`, `llm_deep_num_ctx`, `plan_dir`, `plan_confirm`.
- **§5.3** `client.py` — mode-aware `_chat_options`, `chat(mode=)`,
  `stream_mode`, `single_reply(mode=)`, `message_as_dict` thinking.
- **§5.4** `assistant.py` — `_MODE_*_EN/BN` override regexes, `detect_mode_override`,
  `strip_mode_phrase`, D2/D3 routing block in `_process_command`.
- **§5.5** `assistant.py` — plan state machine (§3.3) + `prompts/planner.txt`
  + `plans/` artifact + `.gitignore` entry.
- **§5.6** HUD surface — see the correction below.

#### §5.6 HUD — corrected to match the ACTUAL implemented HUD

**Reminder of the real HUD (as built, `sopno/ui/hud/`):** the header row is
`status_dot` + `context_label` (hint) + small `robot` + `status_label`
("Idle") + window chrome; the reasoning control is a **dropdown pill**
(`ReasoningModeDropdown`) that lives in the controls bar with the Voice|Text
`HoloToggle` (`mic`/`newspaper`) and the wake `HoloToggle` (`bell`/`ear`) —
the toggles are **not** overloaded with a mode label; text mode is hero →
`ChatThread` → composer with a footer (`context_meter`/log/resize hint).

So the HUD surface is deliberately minimal but has one dedicated control:

- **Approved + implemented:** a `ReasoningModeDropdown` — a holographic
  `[ Auto ▾ ]` pill in the same visual family as the `HoloToggle` buttons
  (same 26px height, glass track, border glow, energy rings) — lives inside
  the **controls bar** with the other buttons, on the **right** side:
  `[wake] [voice|text] ﹍ [Auto ▾]`; the dropdown's themed `QMenu` lists
  Auto | Quick | Think | Deep | Plan. There is **no** overloading of the
  Voice|Text `HoloToggle` ("Qwen3 Quick ⇄ modes" is the rejected earlier-draft
  label). The bar travels whole between the voice stage and the text root, so
  the buttons stay grouped in both modes. Selecting a mode calls
  `assistant.set_reasoning_mode()`; a per-turn phrase override still wins
  (D2), and the dropdown live-mirrors the resolved mode via
  `reasoning_callback` → `worker.reasoning_changed`. `settings.llm_mode`
  remains the default when the dropdown is on **Auto**. Below ~360px the pill
  collapses to icon+chevron (compact) so it still fits beside the toggles.
- **Still deferred:** the live thinking trace into the `ChatThread`
  (subtle thinking bubble above the answer — data already arrives via
  `thinking_callback`).
- **Scope now:** `assistant.py` exposes `thinking_callback` /
  `reasoning_callback` + `set_reasoning_mode()`; `AssistantWorker` bridges
  `reasoning_changed`/`thinking_changed` and `set_reasoning_mode`; the CLI
  renders the reasoning trace; the HUD wires the approved dropdown only.

---

## 4. Auto-Routing Hints (verbatim source)

### Plan hints

```
\b(plan|make\s+a\s+plan|set\s+up|configure|set\s+up\s+the\s+project|build\b|instal??\b|migrate|prepare\b|outline)\b|(প্ল্যান|প্লান|সেট\s+আপ|বানাও|তৈরি\s+করো)\b
```

### Deep hints

```
\b(deep\s*(think|analy|research|dive)|analyze\s+in\s+detail|explain\s+thoroughly|debug|optimize|compare\s+(the\s+)?trade|and\s+what\s+would\s+happen\b|গভীর|বিশ্লেষণ|খু?ব\s+ভাবে\s+ভাবো)\b
```

(Yes, `instal??` is a typo in the plan hints. It is kept **verbatim** — do not
"fix" it; it behaves as "install without the double-L", and the design treats
hint accuracy as tunable, not sacred.)

---

## 5. Tests

- `modes.py`: normalize/spec/resolve/auto routing (plan/quick/deep/thinking),
  verbatim-hint coverage.
- `client.py`: per-mode `_chat_options` (incl. settings overrides), explicit
  `think`, defaults-follow-`llm_mode`, `stream_mode` phase ordering.
- `assistant.py`: override order & stripping, plan GATE (no/yes/cancel) and
  EXECUTE loop via `llm_chat`/`execute_tool` mocks, artifact file, bounded
  replan, `think about …` streaming via a mocked `stream_mode`.
- No Ollama network; suite stays ~660 tests green.

---

## 6. References

- `doc/roadmap/autonomous-coding.md` — plan → recite → act loop; gated writes
  as the pattern for "steps still need confirmation".
- `doc/roadmap/long-running-agents.md` — pending-action gates reused by plan
  mode's GATE step.
- `doc/text-mode-ui-design.md` §1.3 / §7 — the HUD "thinking" aliveness
  contract that the deferred UI must honor.