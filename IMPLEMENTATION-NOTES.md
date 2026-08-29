# TEMP — Reasoning-Modes Re-Implementation Guide (DRAFT-ONLY)

> ⚠️ TEMPORARY DOCUMENT at the project root. Purpose: after the user reverts the
> implementation, this guide lets us rebuild the whole feature in minutes.
> **This document is NOT part of the design.** The design source of truth is
> `doc/roadmap/thinking-modes.md` and it stays **proposed/not-implemented**.
>
> Remove this file once the feature is re-implemented and reapproved.

---

## 0. HARD USER RULE — DO NOT TOUCH THE HUD / CLI (ONE APPROVED EXCEPTION)

The user explicitly rejected the HUD/CLI changes. **The HUD UI is exactly as it
was before** — except the reasoning-mode selector, which the user explicitly
requested/approved on 2026-08-30 ("i didn't see any think mode btn in hud").
Scope of the approved exception:

- **ALLOWED (approved 2026-08-30):** `sopno/ui/hud/widgets/reasoning_selector.py`
  (new), header wiring in `window.py` (create selector + `_on_reasoning_selected`
  / `set_reasoning_mode` / `_sync_reasoning_selector` / `_on_reasoning_resolved`),
  `worker.py` (`reasoning_changed`/`thinking_changed` signals +
  `set_reasoning_mode` bridge), `behavior s/responsive.py` scaling.
- **STILL FORBIDDEN:** anything else in the HUD/CLI — no other widget edits,
  no CLI changes, no voice/text toggle changes.

Everything else below stands. Forbidden files:

- `sopno/ui/hud/widgets/chat.py`
- `sopno/ui/hud/widgets/mode_toggle.py`
- `sopno/ui/cli.py`

Design doc §5.6 (thinking pane, reasoning label) is **implemented** for the
selector; the live-thinking-bubble remains deferred. The assistant exposes
`thinking_callback` / `reasoning_callback` hooks and `set_reasoning_mode()`;
the worker bridges `reasoning_changed`/`thinking_changed`. Re-implemented
2026-08-30 (core + selector).

---

## 1. `sopno/llm/modes.py` — NEW FILE

Why: mode → Ollama request overrides (design §5.1). One folder = one job.
How: create the file with this exact content (public surface = `normalize /
spec / resolve / VALID`; `_auto_for` private but unit-tested). Copy regexes
**verbatim** from the design doc — do NOT "improve" them.

```python
"""
sopno/llm/modes.py
━━━━━━━━━━━━━━━━━━
Reasoning-mode → Ollama request overrides.

Maps Sopno's selectable reasoning depth onto the LLM request budget:
quick / thinking / deep / plan (+ auto routing). Design doc:
doc/roadmap/thinking-modes.md (§5.1). One folder = one job.
"""

from typing import Any, Optional

import re

QUICK = "quick"
THINKING = "thinking"
DEEP = "deep"
PLAN = "plan"
AUTO = "auto"
VALID = (QUICK, THINKING, DEEP, PLAN, AUTO)

# name -> {think, num_predict, num_ctx, temperature}
MODES: dict[str, dict[str, Any]] = {
    QUICK:    {"think": False, "num_predict": 120, "num_ctx": 2048, "temperature": 0.6},
    THINKING: {"think": True,  "num_predict": 300, "num_ctx": 4096, "temperature": 0.6},
    DEEP:     {"think": True,  "num_predict": 800, "num_ctx": 8192, "temperature": 0.5},
    PLAN:     {"think": True,  "num_predict": 400, "num_ctx": 4096, "temperature": 0.5},
}

# --- Deferred slot -------------------------------------------------------
# Per-mode model selection lands in a later phase. When it does, each entry
# gains an optional "model" key and `client.chat()` passes it through:
#     DEEP: {..., "model": "qwen3:14b"}   # bigger brain for hard thinking
#     QUICK: {..., "model": "qwen3:4b-instruct"}  # small & fast (non-hybrid!)
# MODES with a "model" set override settings.model_name for that turn.
# ------------------------------------------------------------------------

# Headline routing for AUTO (deterministic — no LLM call).
_DEEP_HINTS = re.compile(
    r"\b(deep\s*(think|analy|research|dive)|analyze\s+in\s+detail|"
    r"explain\s+thoroughly|debug|optimize|compare\s+(the\s+)?trade|"
    r"and\s+what\s+would\s+happen\b|গভীর|বিশ্লেষণ|খু?ব\s+ভাবে\s+ভাবো)\b",
    re.IGNORECASE,
)
_PLAN_HINTS = re.compile(
    r"\b(plan|make\s+a\s+plan|set\s+up|configure|set\s+up\s+the\s+project|"
    r"build\b|instal??\b|migrate|prepare\b|outline)\b|"
    r"(প্ল্যান|প্লান|সেট\s+আপ|বানাও|তৈরি\s+করো)\b",
    re.IGNORECASE,
)


def normalize(mode: str) -> Optional[str]:
    mode = (mode or "").strip().lower()
    return mode if mode in VALID else None


def spec(mode: str) -> dict[str, Any]:
    """Return the request spec for a concrete (non-auto) mode."""
    return MODES.get(normalize(mode) or QUICK, MODES[QUICK])


def resolve(mode: str, utterance: str) -> dict[str, Any]:
    """Resolve 'auto' against the utterance → a concrete mode spec."""
    if normalize(mode) not in (None, AUTO):
        return spec(mode)
    return spec(_auto_for(utterance))


def _auto_for(utterance: str) -> str:
    text = utterance.lower()
    if _PLAN_HINTS.search(text):
        return PLAN
    if _DEEP_HINTS.search(text):
        return DEEP
    if len(utterance.split()) <= 4:  # greeting / one-word
        return QUICK
    return THINKING
```

Note: `_DEEP_HINTS`/`_PLAN_HINTS` are the design doc's regexes verbatim
(including the `instal??\b` spelling — do not "fix" it).

---

## 2. `config.json` — ADD KEYS

Why: standing mode + per-mode budgets + plan dir/confirm (design §5.2).
How: add right after `"llm_think"` and after `"llm_temperature"`:

```json
  "llm_think": false,
  "llm_mode": "auto",
  "llm_think_num_predict": 300,
  "llm_deep_num_predict": 800,
  "llm_deep_num_ctx": 8192,
  "llm_num_predict": 120,
  "llm_num_ctx": 2048,
  "llm_temperature": 0.6,
  "plan_dir": "plans",
  "plan_confirm": true,
```

Why those values: defaults must match `MODES` in modes.py; `plan_dir` is
project-root relative; `plan_confirm` defaults true so a plan never executes
without an explicit Yes/No.

---

## 3. `sopno/config/settings.py` — ADD KEYS

Why: make the new config read at runtime (design §5.2). How: add after the
`llm_think` line (~line 32), and add a plan block next to the other Paths
(~~line 376):

```python
        # Reasoning mode: "quick" | "thinking" | "deep" | "plan" | "auto"
        # (doc/roadmap/thinking-modes.md — supersedes llm_think when set)
        self.llm_mode: str          = data.get("llm_mode", "auto")
        # Per-mode budget overrides (defaults match MODES in llm/modes.py)
        self.llm_think_num_predict: int = int(data.get("llm_think_num_predict", 300))
        self.llm_deep_num_predict:  int = int(data.get("llm_deep_num_predict", 800))
        self.llm_deep_num_ctx:      int = int(data.get("llm_deep_num_ctx", 8192))
```

```python
        # ── Plan mode (doc/roadmap/thinking-modes.md §5.2) ─────
        # Plan artifacts land here (relative → project root, like memory paths).
        self.plan_dir: Path = Path(data.get("plan_dir", "plans"))
        if not self.plan_dir.is_absolute():
            self.plan_dir = _PROJECT_ROOT / self.plan_dir
        # Require an explicit Yes/No before executing a plan.
        self.plan_confirm: bool     = bool(data.get("plan_confirm", True))
```

`Path` and `_PROJECT_ROOT` are already defined/imported at the top of
settings.py. Why: `plan_dir` must be rooted at the project root like the other
path settings.

---

## 4. `sopno/llm/client.py` — MODE-AWARE (design §5.3)

Why: every request needs the resolved mode's budget + explicit `think` flag.
How: make these exact edits.

4a. Imports — change:

```python
from typing import Any, Generator, Optional
```
to:
```python
from typing import Any, Generator, Optional, Tuple

from sopno.config.settings import settings
from sopno.llm import modes
```

4b. Replace `_chat_options()`:

```python
def _chat_options(mode: str = "quick") -> dict[str, Any]:
    """Per-mode Ollama options, with settings.py overrides merged in."""
    spec = dict(modes.spec(mode))
    if mode == modes.THINKING:
        spec["num_predict"] = settings.llm_think_num_predict
    elif mode == modes.DEEP:
        spec["num_predict"] = settings.llm_deep_num_predict
        spec["num_ctx"] = settings.llm_deep_num_ctx
    return {
        "num_predict": spec["num_predict"],
        "num_ctx":     spec["num_ctx"],
        "temperature": spec["temperature"],
    }
```

Why: quick stays byte-for-byte today's budget; thinking/deep get their config
overrides; settings are fallbacks when the keys are absent.

4c. `chat()` — add `mode`, send explicit `think`:

```python
def chat(
    messages: list[dict],
    *,
    tools: Optional[list] = None,
    stream: bool = False,
    mode: Optional[str] = None,
):
    """
    Call Ollama chat with Sopno's speed-oriented defaults.

    mode: reasoning mode. Defaults to settings.llm_mode; callers resolve
    `auto` first via `modes.resolve` (§5.3). Unresolved modes fall back to
    the quick budget so standalone tool loops stay instant.
    """
    resolved_mode = modes.normalize(mode) or getattr(settings, "llm_mode", modes.AUTO)
    kwargs: dict[str, Any] = {
        "model": settings.model_name,
        "messages": messages,
        "stream": stream,
        "options": _chat_options(resolved_mode),
    }
    if tools is not None:
        kwargs["tools"] = tools
    # Always explicit for hybrid models (Qwen3 needs the flag every request)
    kwargs["think"] = bool(modes.spec(resolved_mode)["think"])

    return ollama.chat(**kwargs)
```

Why: `think` must be sent explicitly every request for hybrid models; the old
`if not llm_think: think=False` block is replaced.

4d. New `stream_mode()` (insert after `stream_reply`):

```python
def stream_mode(
    messages: list[dict], *, mode: str = "quick"
) -> Generator[Tuple[str, str], None, None]:
    """
    Stream a reply tagged by phase — the "Cursor feel" piece (design §5.3).

    Yields ("thinking", text) chunks first, then ("answer", text) chunks,
    so a UI can animate the reasoning phase before the final answer.
    """
    for chunk in chat(messages, mode=mode, stream=True):
        msg = chunk.get("message", {})
        if msg.get("thinking"):
            yield "thinking", msg["thinking"]
        elif msg.get("content"):
            yield "answer", msg["content"]
```

4e. `single_reply()` — add mode pass-through:

```python
def single_reply(messages: list[dict], *, mode: str = "quick") -> str:
    ...
    response = chat(messages, mode=mode)
    msg = response["message"]
    content = msg["content"] if isinstance(msg, dict) else (msg.content or "")
    return str(content).strip()
```

4f. `message_as_dict()` — preserve thinking (`messages["thinking"] = "…"`):

```python
    thinking = getattr(msg, "thinking", None)
    if thinking:
        data["thinking"] = thinking
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = tool_calls
    return data
```

---

## 5. `sopno/llm/researcher.py` — RESOLVED MODE (design §5.3 note)

Why: deep research should inherit the active mode's thinking budget. How: in
`_summarize()`, right before the `requests.post(_CHAT_URL, ...)` call, resolve
the mode and use `resolved["think"]` + `max(...)` budgets:

```python
    # Deep research inherits the active reasoning mode's thinking budget
    # (doc/roadmap/thinking-modes.md §5.3).
    from sopno.llm import modes
    resolved = modes.resolve(
        getattr(settings, "llm_mode", "auto"),
        question,
    )
```

and in the JSON body change:
```python
                "think": bool(resolved["think"]),
                "options": {
                    "num_ctx": max(settings.research_summary_ctx, resolved["num_ctx"]),
                    "num_predict": max(settings.research_summary_tokens, resolved["num_predict"]),
                    "temperature": 0.3,
                },
```

Why: `max()` keeps the research floor while letting `deep` raise the budget.

---

## 6. `prompts/planner.txt` — NEW FILE

Why: editable planner directive (design §5.5). How: create with:

```
You are Sopno's planner. Break the user's goal into at most 5 numbered steps.

Rules:
1. Each step must be independently executable with Sopno's tools.
2. Steps must be concrete, short, and ordered.
3. The final step must produce the user's requested deliverable.
4. Return ONLY the numbered list, one step per line. No preamble, no summary.
```

---

## 7. `.gitignore` — ADD PLANS

Why: plan artifacts are user data (like `sopno/memory/`). How: insert near the
memory ignores:

```
# Plan-mode artifacts (user data — never commit)
plans/
```

---

## 8. `sopno/core/assistant/__init__.py` — ORCHESTRATION + PLAN FLOW (design §5.4/5.5)

NOTE: at HEAD the assistant is a **package** (`sopno/core/assistant/__init__.py`
plus `memory.py` / `confirm.py`), not a single `assistant.py` file. Apply every
edit in this section to `sopno/core/assistant/__init__.py`.

Why: resolve the turn mode and run the plan-then-execute flow. Do all of the
following.

8a. Imports — add `Path`, `modes`, `single_reply`, `stream_mode`,
`_awaiting_confirmation`:

```python
import time
from pathlib import Path
from typing import Callable, Optional
```
```python
from sopno.llm import modes
from sopno.llm.client import (
    chat as llm_chat,
    message_as_dict,
    single_reply,
    stream_mode,
)
```
```python
from sopno.tools.builtins.files.files import (
    _awaiting_confirmation,
    pending_action,
    resolve_pending,
)
```

8b. Module-level helpers — insert after `parse_memory_intent(...)` (design
§5.4). Detection order matters: **plan > deep > thinking > quick**. Mode words
are control words and get stripped, so they never reach the LLM or context:

```python
# ── Per-turn reasoning-mode overrides (English + Bangla) ─────────────────────
# Detection order matters: plan > deep > thinking > quick. Mode words are
# control words, not conversation — stripped before the LLM sees them (§5.4).

_MODE_PLAN_EN = re.compile(
    r"\b(?:make\s+a\s+plan|plan\s+this|plan\s+to)\b", re.IGNORECASE
)
_MODE_PLAN_BN = re.compile(r"(?<!\w)(?:প্ল্যান\s+করো|পরিকল্পনা\s+করো)(?!\w)")
_MODE_DEEP_EN = re.compile(r"\b(?:deep\s+think|deep\s+reasoning)\b", re.IGNORECASE)
_MODE_DEEP_BN = re.compile(r"(?<!\w)গভীর\s+ভাবে\s+ভাবো(?!\w)")
_MODE_THINKING_EN = re.compile(
    r"\b(?:think\s+(?:about|first|before))\b", re.IGNORECASE
)
_MODE_THINKING_BN = re.compile(r"(?<!\w)(?:ভাবো|ভাবা)(?!\w)")
_MODE_QUICK_EN = re.compile(
    r"\b(?:quick\s+answer|short\s+answer|just\s+tell\s+me)\b", re.IGNORECASE
)
_MODE_QUICK_BN = re.compile(r"(?<!\w)সংক্ষেপে(?!\w)")

_MODE_CHECKS: list[tuple[re.Pattern, str]] = [
    (_MODE_PLAN_EN, modes.PLAN),
    (_MODE_PLAN_BN, modes.PLAN),
    (_MODE_DEEP_EN, modes.DEEP),
    (_MODE_DEEP_BN, modes.DEEP),
    (_MODE_THINKING_EN, modes.THINKING),
    (_MODE_THINKING_BN, modes.THINKING),
    (_MODE_QUICK_EN, modes.QUICK),
    (_MODE_QUICK_BN, modes.QUICK),
]


def detect_mode_override(text: str) -> Optional[str]:
    """Detect a per-turn reasoning mode from 'think about X'-style phrases."""
    if not text:
        return None
    for pattern, mode in _MODE_CHECKS:
        if pattern.search(text):
            return mode
    return None


def strip_mode_phrase(text: str, mode: str) -> str:
    """Remove the detected control words so they don't reach the LLM (§5.4)."""
    for pattern, this_mode in _MODE_CHECKS:
        if this_mode == mode and pattern.search(text):
            text = pattern.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── Plan-mode step parsing (design §5.5) ─────────────────────────────────────
_PLAN_STEP = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$")


def plan_steps(text: str) -> list[str]:
    """Parse numbered (or bulleted) steps from a planner reply."""
    goals: list[str] = []
    for line in (text or "").splitlines():
        m = _PLAN_STEP.match(line)
        if not m:
            continue
        step = m.group(1).strip().rstrip(".")
        if step and step not in goals:
            goals.append(step)
    return goals


def _spec_name(spec: dict) -> str:
    """Map a resolved spec dict back to its concrete mode name."""
    for name in modes.MODES:
        if spec is modes.MODES[name]:
            return name
    return modes.QUICK
```

8c. `SopnoAssistant.__init__` — add callbacks + per-turn mode state (after the
`on_log_message` binding):

```python
        # Reasoning-mode render (thinking trace + the active mode label)
        self.on_thinking        = thinking_callback or (lambda t: None)
        self.on_reasoning_mode  = reasoning_callback or (lambda m: None)

        self._turn_mode = modes.QUICK
        self._turn_think = False
        self._streamed_thinking = ""
```
and the two new `__init__` params:
```python
        thinking_callback: Optional[Callable[[str], None]] = None,
        reasoning_callback: Optional[Callable[[str], None]] = None,
```
Why: hooks for a future UI render; both default to no-ops (HUD stays untouched
per the hard rule in section 0).

8d. New `_streamed_reply()` + the plan methods — insert **before**
`_process_command` (all shown in full below). State machine:
PLAN_ENTRY → PLANNING (non-streaming `single_reply`) → ARTIFACT →
GATE (reuse `_awaiting_confirmation`, auto-skip when `plan_confirm=false`) →
EXECUTE loop (each step still passes every existing permission gate) → summary.

```python
    def _streamed_reply(self, messages: list[dict], mode: str) -> str:
        """Text-mode streaming: live thinking trace, then the buffered answer."""
        self._streamed_thinking = ""
        thinking_buf: list[str] = []
        answer_buf: list[str] = []
        try:
            for tag, chunk in stream_mode(messages, mode=mode):
                if tag == "thinking" and chunk:
                    thinking_buf.append(chunk)
                    self._streamed_thinking = "".join(thinking_buf)
                    self.on_thinking(self._streamed_thinking)
                elif tag == "answer" and chunk:
                    answer_buf.append(chunk)
        except Exception as e:
            self.on_log_message(f"Ollama/stream error: {e}")
        return "".join(answer_buf)

    # ── Plan mode (design §5.5): PLAN_ENTRY → PLANNING → ARTIFACT → GATE → EXECUTE ──
    def _handle_plan_command(self, goal: str) -> bool:
        """User-approved plan-then-execute flow for multi-step goals."""
        self.on_log_message(f"[Plan] planning: '{goal}'")
        self.on_status_changed("thinking")

        plan_text = self._plan_request(goal)
        steps = plan_steps(plan_text)
        if not steps:
            steps = [goal]

        artifact = self._write_plan_artifact(goal, steps)
        self.on_log_message(f"[Plan] artifact → {artifact}")
        self._render_plan(goal, steps, artifact)

        if getattr(settings, "plan_confirm", True):
            # GATE: reuse the pending-action Yes/No machinery (resolved next turn)
            _awaiting_confirmation(
                f"execute this {len(steps)}-step plan",
                lambda: self._plan_execute(goal, steps),
            )
            is_bn = bool(re.search(r"[\u0980-\u09FF]", goal))
            question = (
                f"Should I go ahead with this {len(steps)}-step plan?"
                if not is_bn
                else f"আমি কি এই {len(steps)} ধাপের পরিকল্পনা অনুযায়ী এগিয়ে যাব?"
            )
            self._speak_short(question)
        else:
            # plan_confirm=false → auto-skip the gate (design §5.5)
            summary = self._plan_execute(goal, steps)
            self._deliver_reply(summary)
        return True

    def _plan_request(self, goal: str) -> str:
        """Non-streaming planner call — cheap on CPU (design §5.5)."""
        messages = [
            {"role": "system", "content": self._planner_prompt()},
            {"role": "user", "content": goal},
        ]
        try:
            return single_reply(messages, mode=modes.PLAN)
        except Exception as e:
            self.on_log_message(f"[Plan] planner failed: {e}")
            return "1. " + goal

    def _planner_prompt(self) -> str:
        path = settings.prompts_dir / "planner.txt"
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return (
                "Break the user's goal into at most 5 numbered steps. "
                "Each step must be independently executable and end with "
                "the final deliverable. Return only the numbered list."
            )

    def _write_plan_artifact(self, goal: str, steps: list[str]) -> str:
        """Persist the reviewable plan to plans/<slug>-<ts>.md (gitignored)."""
        directory = getattr(settings, "plan_dir", None)
        directory = Path(directory) if directory else Path("plans")
        directory.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")[:40] or "plan"
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = directory / f"{slug}-{ts}.md"
        lines = [f"# Plan — {goal}", "", f"- Created: {ts}", f"- Steps: {len(steps)}", "", "## Steps", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return str(path)

    def _render_plan(self, goal: str, steps: list[str], artifact: str) -> None:
        """Render the full numbered list; speak only a short summary (§5.5)."""
        is_bn = bool(re.search(r"[\u0980-\u09FF]", goal))
        block = "\n".join(
            ["# Plan", "", goal, ""]
            + [f"{i}. {s}" for i, s in enumerate(steps, 1)]
            + ["", artifact]
        )
        self.on_reply_generated(block)
        short = (
            f"I put together a {len(steps)}-step plan."
            if not is_bn
            else f"আমি {len(steps)} ধাপের একটি পরিকল্পনা তৈরি করেছি।"
        )
        self._speak_short(short)

    def _speak_short(self, text: str) -> None:
        """Speak a short line without re-rendering (plan summary / gate prompt)."""
        with self._speech_lock:
            if self.interaction_mode == "voice":
                self.on_status_changed("speaking")
                self._speak_with_barge_in(text)
                time.sleep(_POST_SPEAK_SETTLE_S)
            else:
                self.on_status_changed("speaking")
                time.sleep(0.2)

    def _plan_execute(self, goal: str, steps: list[str]) -> str:
        """EXECUTE loop — walks approved steps through the normal gates."""
        base = self.context.get_messages_for_llm()
        remaining = list(steps)
        replanned: set[str] = set()
        i = 0
        done = 0

        while i < len(remaining):
            step = remaining[i]
            self.on_log_message(f"[Plan][{i + 1}/{len(remaining)}] {step}")
            self.on_status_changed("thinking")

            output = self._execute_plan_step(base, goal, step)

            if self._plan_looks_error(output) and step not in replanned:
                replanned.add(step)
                revised = self._plan_replan(goal, step, output, remaining[i:])
                if revised:
                    self.on_log_message(f"[Plan] replanning after step {i + 1} failed.")
                    remaining = remaining[:i] + revised
                    continue

            done += 1
            self._deliver_step_result(output)
            i += 1

        is_bn = bool(re.search(r"[\u0980-\u09FF]", goal))
        self.on_log_message("[Plan] complete.")
        return (
            f"Plan complete — {done} of {len(steps)} step(s) done."
            if not is_bn
            else f"পরিকল্পনা সম্পন্ন — {len(steps)} ধাপের মধ্যে {done} ধাপ শেষ হয়েছে।"
        )

    def _execute_plan_step(self, base: list[dict], goal: str, step: str) -> str:
        """One executor iteration — llm_chat(tools) → execute_tool (gates intact)."""
        messages = base + [
            {"role": "user", "content": f"Goal: {goal}\nExecute this step: {step}"}
        ]
        try:
            response = llm_chat(messages, tools=get_schema(), mode=modes.QUICK)
        except Exception as e:
            return f"Error: {e}"

        response_msg = message_as_dict(response["message"])
        tool_calls = response_msg.get("tool_calls") or []
        if not tool_calls:
            return (response_msg.get("content") or "").strip()

        messages.append(response_msg)
        for tool in tool_calls:
            fn = tool["function"] if isinstance(tool, dict) else tool.function
            name = fn["name"] if isinstance(fn, dict) else fn.name
            args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
            if not isinstance(args, dict):
                args = {}
            self.on_log_message(f"[Plan][tool] '{name}' with args {args}")
            tool_result = execute_tool(name, args) or "Done."
            self.on_log_message(f"[Plan][tool] → {tool_result}")
            messages.append({"role": "tool", "content": tool_result})

        try:
            final = llm_chat(messages, mode=modes.QUICK)
        except Exception as e:
            return f"Error: {e}"
        return (message_as_dict(final["message"]).get("content") or "").strip()

    def _plan_replan(self, goal: str, failed_step: str, error: str, remaining: list[str]) -> list[str]:
        """Re-run the planner on the remaining steps (bounded per step, §5.5)."""
        prompt = (
            "A step of the plan failed.\n"
            f"Failed step: {failed_step}\n"
            f"Error: {error[:400]}\n"
            "Remaining steps to revise:\n"
            + "\n".join(f"{i}. {s}" for i, s in enumerate(remaining, 1))
            + "\nReturn ONLY a revised numbered list of the remaining steps."
        )
        try:
            text = single_reply(
                [
                    {"role": "system", "content": self._planner_prompt()},
                    {"role": "user", "content": prompt},
                ],
                mode=modes.PLAN,
            )
        except Exception as e:
            self.on_log_message(f"[Plan] replan failed: {e}")
            return []
        return plan_steps(text)

    @staticmethod
    def _plan_looks_error(text: str) -> bool:
        head = (text or "").strip().lower()[:80]
        return bool(
            re.match(
                r"^(error|failed|failure|exception|unable|permission denied|"
                r"off-limits|sorry|no such)",
                head,
            )
        )

    def _deliver_step_result(self, output: str) -> None:
        """Speak each completed step's output as it finishes (§5.5)."""
        out = (output or "").strip()
        if not out:
            return
        short = out if len(out) <= 160 else out[:157] + "…"
        self._deliver_reply(short)
```

8e. `_process_command` — insert D2/D3 and make §F mode-aware.

i) Right after the status line at the top of `_process_command`, add:
```python
        self.on_thinking("")  # clear any previous turn's reasoning bubble
```

ii) Insert D2/D3 **after the §D memory-intent block** (before §E dispatcher):
```python
        # D2. Reasoning mode for this turn — override >> default >> auto
        override = detect_mode_override(cmd_text)
        if override:
            self.on_log_message(f"Mode override → {override}")
            cmd_text = strip_mode_phrase(cmd_text, override) or cmd_text
            turn_mode = override
        else:
            turn_mode = modes.normalize(getattr(settings, "llm_mode", "auto")) or modes.AUTO

        # D3. Plan mode — plan-then-execute branch (between D and E, §5.4/5.5)
        if turn_mode == modes.PLAN:
            return self._handle_plan_command(cmd_text)

        # §5.2 backward-compat: auto's non-deep default tier honors the legacy
        # llm_think toggle (llm_mode supersedes it when present).
        self._turn_mode = _spec_name(modes.resolve(turn_mode, cmd_text))
        if (
            self._turn_mode == modes.THINKING
            and not bool(getattr(settings, "llm_think", False))
            and modes.normalize(turn_mode) in (None, modes.AUTO)
        ):
            self._turn_mode = modes.QUICK
        self._turn_think = bool(modes.spec(self._turn_mode)["think"])
        self.on_log_message(f"Reasoning mode → {self._turn_mode}")
        self.on_reasoning_mode(self._turn_mode)
        if self._turn_think:
            self.on_status_changed("thinking")
```

iii) In §F, change the two `llm_chat` calls to pass `mode=self._turn_mode`, add
the text-mode streaming branch, and render the trace:
```python
            if not use_tools and self.interaction_mode == "text":
                # Text mode streams the reasoning trace live (design §5.3/5.6)
                assistant_reply = self._streamed_reply(chat_messages, self._turn_mode)
                thinking_trace = getattr(self, "_streamed_thinking", "")
            else:
                response = llm_chat(
                    chat_messages,
                    tools=get_schema() if use_tools else None,
                    mode=self._turn_mode,
                )
                ...
                # (inside the tool_calls loop, final call becomes:)
                final_response = llm_chat(chat_messages, mode=self._turn_mode)
                ...
            # after the empty-reply fallback, before _deliver_reply:
            if thinking_trace:
                self.on_thinking(thinking_trace)
```

Why: mode resolves once per turn (override → `settings.llm_mode` → auto), plan
branches before the dispatcher so a "plan…" turn never hits the LLM launcher,
and tool loops keep the quick budget.

---

## 9. TESTS (re-create these files)

Why: prove the feature without tapping Ollama (design §6). Tests patch
`SopnoAssistant` construction with `patch("sopno.core.assistant.MemoryStore")`
and `patch("sopno.core.assistant.Listener")`; speech is silenced by patching the
class method `_speak_with_barge_in` (module-level patching does NOT work — it's
a method) plus `time.sleep`. Reset `files._PENDING_ACTION = None` in
setUp/tearDown.

- `tests/llm/__init__.py` — empty package marker.
- `tests/llm/test_modes.py` — `normalize` (valid/auto/unknown/None), `spec`
  (quick = today's budget; thinking has think True; deep biggest; plan separate;
  unknown falls back to quick), `resolve` (concrete passthrough; auto →
  plan hints / deep hints / short greetings → quick / long default question →
  thinking). Pitfalls observed when re-resolving after the doc-faithful revert:
  - `modes.resolve` has **no** `default_think` param now → delete both
    `default_think=False` call sites (the `llm_think` backward-compat lives in
    `assistant._process_command`; assert it there instead: with `llm_think`
    off and `llm_mode=auto`, a THINKING-resolved turn downgrades to QUICK).
  - After reverting `_DEEP_HINTS` and `_PLAN_HINTS` to the doc's verbatim
    regexes, several phrases route less cleverly than intuition (tests are
    aligned with this verified reality — run `resolve`, don't assume):
    - `"research quantum computing"` → QUICK (no standalone `research` hint;
      doc only has `deep\s*(analy|research|…)`, and 3 words ≤ 4 → quick tier).
    - `"analyze this in detail"` → QUICK (`analyze\s+in\s+detail` must be
      literally contiguous; doc does not allow a word in between).
    - `"install ollama"` → QUICK (the doc's `instal??` typo never matches
      across the double `l` — keep the typo; use `"set up the
      project"`/`"configure my editor"`/`"make a plan to refactor"` instead).
    - `"deep analyze the code"` → QUICK (regex closes with `\b` after
      `deep\s*(analy|…)`, so "analy" has no boundary before "ze").
    - `"গভীরভাবে ভাবো"` → QUICK, but `"গভীর ভাবো"` (space-separated) → DEEP
      (`\bগভীর\b` does not cross a compounded Bengali word).
    - Verified doc-covered deep phrases: `"deep research …"`,
      `"deep think …"`, `"deep dive …"`, `"analyze in detail"`,
      `"debug my code"`, `"optimize the loop"`, `"explain thoroughly"`.
- `tests/llm/test_client.py` — `_chat_options` per mode incl. patched settings
  overrides (`patch.object(client.settings, ...)`); `chat` sends `think=True`
  for thinking/deep, `think=False` for quick; defaults follow
  `settings.llm_mode`; `stream_mode` yields `("thinking", …)` then
  `("answer", …)`; `single_reply` passes `mode`; `message_as_dict` preserves
  `thinking`.
- `tests/core/test_plan_mode.py` — `detect_mode_override` + `strip_mode_phrase`
  (En+Bn, plan>deep>thinking>quick order); `plan_steps` (numbered/bulleted);
  plan flow with `plan_confirm=False` executes immediately (2 steps, patched
  `llm_chat` + `execute_tool`, artifact written to a temp `plan_dir`); with
  `plan_confirm=True` nothing executes until `files.resolve_pending(id, "yes")`;
  `"no"` cancels; failed step triggers exactly one bounded replan; artifact is a
  reviewable `.md`; `_process_command("think about …")` sets `_turn_mode` to
  `thinking` and streams via patched `stream_mode` (set
  `asst.interaction_mode = "text"`); `_process_command("make a plan to …")`
  routes to the plan flow and writes the artifact.

Run: `python3 -m unittest discover -s tests` (🗸 re-implemented run: **702**
tests OK — the repo has grown past the old 620; all green).

---

## 10. VERIFICATION + REVERT SEQUENCE

If asked to re-implement after a full revert, do it in this order:
1. Steps 1–7 (modes.py, config, settings, client, researcher, planner.txt, .gitignore) — no dependencies on each other.
2. Step 8 (assistant — `sopno/core/assistant/__init__.py` package) — depends on 1, 4, 6.
3. Step 9 (tests) — then run the full suite.
4. Do NOT touch the HUD/CLI (section 0). Re-add the two callbacks wiring only
   if the user explicitly asks for UI rendering later.

Remember: the design doc `doc/roadmap/thinking-modes.md` status header is
flipped to **"implemented"** after the 2026-08-30 re-implementation (§11); the
HUD *selector* landed in the §11a follow-up with explicit user approval (only
the live thinking bubble stays deferred). Do not flip it back.

---

## 11. RE-IMPLEMENTATION RUN — 2026-08-30

User pointed at this note as the guide: "check the hud design first. if any
docs is outdated about this design, update that first. then complete the
implementations. and also add doc, i have reverted git so it also deleted."

HUD check first: real HUD confirmed — `window.py:117-188` header row
(status_dot + context_label hint + robot + status_label ("Idle") + chrome),
and the only mode control is the **Voice|Text** `HoloToggle("mic","newspaper")`
(`window.py:216`) — NOT a reasoning selector. Left untouched (§5.6 deferred).

Design doc re-created from scratch (`doc/roadmap/thinking-modes.md`) with the
corrected §5.6 (real HUD facts; earlier "Qwen3 Quick ⇄ modes" label was the
mistake the user rejected). Status header flipped to "implemented" afterward —
the user's directive was to complete the implementations, so the doc now
reflects reality here.

Everything re-applied per steps 1–9, with two deviations verified live:
- The assistant is a package at HEAD; edits went to
  `sopno/core/assistant/__init__.py` (imports edit landed first, then module
  helpers, callback args, streaming/plan methods, D2/D3 in `_process_command`,
  mode-aware §F).
- Test phrase reality differs from this note's §9 guesses — see the §9
  corrections (QUICK for "research quantum computing" / "analyze this in
  detail" / "deep analyze …", and the Bengali `গভীর` boundary rule).

Full suite: **702 tests, all green.** HUD/CLI untouched.

---

## 11a. HUD SELECTOR FOLLOW-UP — 2026-08-30

User: "i didn't see any think mode btn in hud. have you forgot it?" — the §5.6
deferral was overridden by explicit approval. Implemented:

- **New** `sopno/ui/hud/widgets/reasoning_selector.py` — `ReasoningModeSelector`:
  5-segment glass pill (Auto | Quick | Think | Deep | Plan), `mode_selected`
  signal, `set_mode(emit=)` normalize, `apply_scale`. Exported in
  `widgets/__init__.py`.
- **window.py** — selector placed in the header (never the Voice|Text HoloToggle,
  §5.6); `mode_selected` → `_on_reasoning_selected` → `set_reasoning_mode` →
  `worker.set_reasoning_mode`. `worker.reasoning_changed` → `_on_reasoning_resolved`
  live-mirrors the resolved mode.
- **worker.py** — added `reasoning_changed` + `thinking_changed` signals and
  `set_reasoning_mode()`; assistant's `thinking_callback`/`reasoning_callback`
  now wired.
- **assistant** — `set_reasoning_mode()` sets `_forced_mode` (None = follow
  config); D2 priority: phrase override >> HUD force >> `settings.llm_mode` >>
  auto. Forced PLAN routes into the existing plan flow.
- **responsive.py** — selector scales with mode tokens; auto-hidden below 360px.
- Tests: `tests/ui/test_reasoning_selector.py` (7) + `TestForcedMode`
  (4) in `tests/core/test_plan_mode.py`. Full suite re-run: **713 tests, all
  green** (was 702).