# Text Mode UI Design Specification

**Date**: August 24, 2026
**Scope**: The HUD's text page (text interaction mode) — full research digest,
component placement, responsiveness system, animated effects, state machine,
and a phased implementation plan with code-level guidance.
**Status**: Voice page is complete and untouched; this doc covers text mode only.
**Companion docs**: [`voice-mode-ui-design.md`](voice-mode-ui-design.md),
[`hud/DESIGN.md`](hud/DESIGN.md), [`hud/PYWEBVIEW.md`](hud/PYWEBVIEW.md)

---

## Table of Contents

1. [Research Summary](#1-research-summary)
   - 1.1 [Sources consulted](#11-sources-consulted)
   - 1.2 [Thread & bubbles](#12-thread--bubbles-the-reading-surface)
   - 1.3 [Streaming & thinking](#13-streaming--thinking-the-aliveness-contract)
   - 1.4 [Empty state & composer](#14-empty-state--composer)
   - 1.5 [Glassmorphism discipline](#15-glassmorphism-discipline-production-rules)
   - 1.6 [Gaps in the current build](#16-what-our-text-page-gets-wrong-today)
2. [Design Principles for the Text Page](#2-design-principles-for-the-text-page)
3. [Component Inventory & Placement](#3-component-inventory--placement)
4. [Layout Blueprints (per breakpoint)](#4-layout-blueprints-per-breakpoint)
5. [Component Specs](#5-component-specs)
6. [Motion & Animation Spec](#6-motion--animation-spec)
7. [Text-Mode State Machine](#7-text-mode-state-machine)
8. [Responsive Token Map](#8-responsive-token-map)
9. [Implementation Plan](#9-implementation-plan)
10. [Performance & Accessibility Budget](#10-performance--accessibility-budget)
11. [Research Sources](#11-research-sources)

---

## 1. Research Summary

### 1.1 Sources consulted

Live research performed August 24, 2026 across production AI chat surfaces,
streaming-UX engineering guides, chat-bubble UX studies, and glassmorphism
production guides:

| # | Source | Focus |
|---|--------|-------|
| S1 | Conferbot — *Chatbot Window UI Design* | Bubble metrics table, dark mode, WCAG |
| S2 | AI UX Design Guide — *Anatomy of a Chat Interface* | Alignment/width/rich-content rules |
| S3 | UXPin — *Chat UI Design 2026* | Sender identification, accessibility |
| S4 | Lovable — *How to Build a Chatbot UI* | Sender differentiation, NNGroup citation |
| S5 | Ethora — *Chat App UI/UX Patterns* | Grouping thresholds, timestamps, composer growth |
| S6 | MUI X Chat — *Look and feel* | variant/density model (bubbles vs flat) |
| S7 | Metacto — *AI Chat UX Patterns for Production* | TTFT, stop control semantics, error taxonomy |
| S8 | SmoothUI — *AI / chat surfaces* | Seven AI states, caret contract, scroll discipline |
| S9 | AI UX Design Guide — *Typing Indicators & Streaming* | Dots vs streaming decision, status phases |
| S10 | Frontend Patterns — *Managing AI Response States* | Full generation state machine, regeneration |
| S11 | AppSavvy — *Streaming AI Responses* | Stable-layout streaming, interruptibility |
| S12 | UXMagic — *AI Chat Interface Design Patterns* | Latency acknowledgment ≤200ms, escalation copy |
| S13 | Tim Severien — *Glassmorph responsibly* | Worst-case contrast testing |
| S14 | Clay — *Why Everything Is Going Glassmorphism* | Glass on chrome not content; dark-mode opacity |
| S15 | PixCode — *CSS Glassmorphism 2025* | Blur/alpha production ranges, GPU cost |
| S16 | Superdesign — *Glassmorphism recipe* | 4-property canonical recipe, border-as-a11y |

Cross-checked against our own completed voice-page research
(`voice-mode-ui-design.md`: ChatGPT Advanced Voice, Gemini Live, Siri edge-glow)
so both pages share one evidence base.

### 1.2 Thread & bubbles (the reading surface)

Consensus across S1–S6:

| Decision | Production consensus | Why |
|---|---|---|
| Alignment | User right / assistant left — universal convention, never broken | Instant sender scanning |
| Sender distinction | Alignment **or** tint — pick the *minimum* cue combination, then stop | Stacking every cue (color + tail + weight + avatar flip) reads as noise (S5) |
| Two viable styles | **Bubbled** (WhatsApp/Telegram: colored, right-aligned) or **Flat** (ChatGPT/Claude: no bubble, inline author) — both valid; be consistent (S6) | Our compact floating panel favors soft bubbles for scanability at small sizes |
| Bubble max-width | ~65–75% of column on desktop, up to 85% narrow/mobile | Full-width bubbles destroy the "who spoke" cue; >75ch hurts reading (S1, S2, S8) |
| Body size | 15–16px web equivalent; floor = 4.5:1 contrast (WCAG AA) | Below 14px fails legibility; above 17px wastes narrow columns (S1) |
| Corner radius | 8–16px soft radius, **identical across every message type** | Pills break on multi-line; inconsistent radii "feel" wrong even when users can't articulate why (S5) |
| Message grouping | Same sender within ~60s ⇒ one cluster: one tag/avatar, tight spacing (~4px); role change ⇒ wide spacing (10–16px). NOT 5-minute grouping — threads look artificially sparse | "The single pattern that makes a thread look like a conversation rather than a log file" (S5) |
| Timestamps | First message of group only, dim; full time on hover/tap | Per-message timestamps turn the thread into a log (S5) |
| Assistant surface | Neutral translucent surface; saturated accent reserved for send button / links / user tint | If every sender has an accent bubble nothing is highlighted (S5) |
| Long replies | Break into shorter sequential messages rather than one wall; ~60 words per screen in narrow columns (S1) | Walls get skipped |

### 1.3 Streaming & thinking (the aliveness contract)

Consensus across S7–S12 — these are hard rules in every production guide:

- **First visible pixel < 400ms** (Doherty threshold). Echo the user's message
  and paint a thinking indicator the instant the request leaves — never a blank
  gap after Send. Acknowledge input within ~200ms (S12).
- **Caret always visible while tokens arrive** — blinking block/pulse at the
  tail. No caret ⇒ "is it broken?" panic (S8).
- **Thinking indicator**: three bouncing dots for short waits (<3s, S9);
  if thinking exceeds ~2s **escalate** with quiet progress copy
  ("Still thinking…"), never a static spinner past 3s (S8, S12).
- **Interruptibility**: while generating, **Send morphs into Stop in the same
  position**, no confirmation dialog, Esc bound at page level. A stop that
  doesn't halt upstream work is theater (S7). Partial output stays visible,
  marked "(interrupted)" with edit-and-resend options (S10).
- **Scroll discipline**: auto-follow the stream tail, pause the moment the user
  scrolls up, resume only on send or explicit jump-to-bottom (S8).
- **Completion is explicit**: caret disappears, copy/regenerate appear; users
  must never guess whether more text is coming (S7, S10).
- **Lock submission while generating** (never the Stop button) — prevents two
  interleaved answers (S10).
- **Progressive rendering**: never buffer the whole reply then paint once;
  render markdown/structure progressively as chunks arrive (S8, S11).
- **Stable layout during streaming**: reserve space, stream into it; jarring
  reflows undermine perceived speed (S11).
- Distinct lifecycle states beat one spinner: idle → submitted → thinking →
  streaming → complete/stopped/error, tracked **per turn** (S10).

### 1.4 Empty state & composer

- Fresh conversations earn a **generous guided empty state**: presence mark +
  one-line greeting + suggested starter prompts (keyboard reachable);
  continuing conversations stay focused on the transcript (S8, S10).
- Composer starts single-line, grows to ~5 lines, then scrolls internally —
  cap prevents the composer eating small viewports (S5). *(Ours already caps
  at 120px — correct.)*
- Input pinned to bottom edge at all sizes, visible without scrolling gates (S8).
- Hybrid GUI > pure chat for finite choices: chips/cards handle deterministic
  actions, free text handles open exploration (S12) — starter chips follow this.

### 1.5 Glassmorphism discipline (production rules)

From S13–S16:

- **Glass belongs on chrome** (docks, headers, chips, modals) — never on the
  long-form reading surface. Apple keeps glass on nav/overlays, not content;
  NN/g found usability regressions exactly where glass meets dense text.
- Dark-mode glass needs **higher fill opacity** (0.06→0.08+) because luminance
  contrast drops; the 1px light border is an accessibility feature (survives
  forced-colors mode), not decoration.
- Production ranges: blur 12–20px web-equivalent, fill alpha 12–25%, max 2–3
  stacked glass layers per view (GPU cost scales with area × radius²). Our HUD
  approximates glass with cheap `rgba` QSS fills over an opaque base — keep it.
- Contrast checked against the **worst case**, not average (S13). Our body
  text (#E4EAF2 on ≤8% white-over-dark ≥ 9:1) clears 4.5:1 comfortably.

### 1.6 What our text page gets wrong today

Audited against `window.py`, `widgets/chat.py`, `behaviors/status.py`,
`behaviors/responsive.py`:

| Issue | Where | Fix direction |
|---|---|---|
| No empty state — blank screen on fresh open | text stage | Guided hero (robot + greeting + chips) |
| Bubbles unconstrained width; roles differ only by tint+tag | `chat.py` | Max-width wrappers + role asymmetry + grouping + timestamps |
| No thinking indicator / no streaming caret | `status.py`, `chat.py` | Dots row + caret + Stop morph |
| Robot face + status label burn ~150px above the chat forever | `window.py:245-254` | Hero only when empty; 20px avatar inside assistant bubbles after |
| Mode toggle re-parents between layouts (fragile `removeWidget`/`setParent`) | `window.py:370-394` | Fixed header slot |
| Dashboard pushes layout when toggled (inserted into `root`) | `window.py:264-271` | Overlay sheet |
| No message actions (copy) | `chat.py` | Hover-visible copy per assistant bubble |
| Reply arrives all-at-once (`worker.reply_generated`) | `worker.py` | Caret/dots now; true token streaming later via `reply_chunk` |
| No scroll discipline (always jumps to bottom) | `chat.py` `_scroll_bottom` | Follow-with-pause + jump pill |

---

## 2. Design Principles for the Text Page

Carrying the Premium Formula (`DESIGN.md §1`) into text mode:

1. **The conversation IS the content.** Once chatting starts, chrome recedes;
   nothing competes with the thread.
2. **Presence without space tax.** The robot face is the soul (voice-page
   principle #6) — it owns the empty state, then compresses to a 20px avatar
   costing zero vertical space during conversation.
3. **Every state has a unique visual** — idle, composing, thinking, streaming,
   speaking(TTS), error — driven by the *same* `STATE_ACCENT` palette as the
   voice orb (`visuals/theme.py`). One brain, two skins.
4. **Asymmetry tells the story**: user = right + tinted; Sopno = left +
   neutral glass + avatar. Minimum viable cues (research rule).
5. **Motion is purposeful, spring-eased, interruptible**; entrances ≤ 250ms;
   accent lerps ≈ 400ms (voice-page `TRANSITION_SPEED` parity).
6. **Reading comfort beats decoration**: 65–75ch measure, generous line-height,
   glass on chrome only.
7. **Never strand the user**: Stop always available mid-stream; partial output
   preserved; errors render inline with retry; drafts survive interrupts.

---

## 3. Component Inventory & Placement

Final answer to *"best places for all components"* — z-order top to bottom:

```
┌──────────────────────────────────────────────────────┐
│ ① STATUS LINE            ② MODE TOGGLE  ③ CHROME     │  header · 30–34px · always visible
│    ● Listening…             [🎙|⌨]      – □ ✕        │
├──────────────────────────────────────────────────────┤
│                                                      │
│ ④ EMPTY-STATE HERO  (only when 0 messages)           │
│    ┌──────────┐                                      │
│    │  robot   │  breathing, state-colored aura       │
│    └──────────┘                                      │
│    "Ask me anything — English বা বাংলায়।"             │
│    ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│    │ chip 01 │ │ chip 02 │ │ chip 03 │  ← starters   │
│    └─────────┘ └─────────┘ └─────────┘               │
│                                                      │
│ ⑤ TRANSCRIPT  (flex:1, scrolls)                      │
│   ┌───────────────────────────────┐                  │
│   │ ◉ Sopno                14:32 ⧉│  avatar·tag·copy │
│   │ Response, max-width 82%,      │                  │
│   │ left-aligned, neutral glass   │                  │
│   └───────────────────────────────┘                  │
│            ┌───────────────────────────┐             │
│            │ You                14:33  │  tinted,    │
│            │ user text, max 75%, right │  right      │
│            └───────────────────────────┘             │
│   ● ● ●   ← ⑥ TYPING DOTS (assistant slot)           │
│   response text▊  ← ⑦ STREAMING CARET                │
│                                     [↓ Latest] pill  │  ⑬ when scrolled up
├──────────────────────────────────────────────────────┤
│ ⑧ COMPOSER DOCK                                      │
│  ╭────────────────────────────────────╮ ⟶ ⏹/➤       │
│  │ Type a message…  (autogrow 36→120) │  send⇄stop   │
│  ╰────────────────────────────────────╯              │
├──────────────────────────────────────────────────────┤
│ ⑨ FOOTER STRIP:  context ▓▓░░ 38% · last log line ⋰  │  ≤18px · hides <320w
└──────────────────────────────────────────────────────┘
   ⑩ DASHBOARD = overlay sheet sliding over ④–⑨ (not in-flow)
```

Placement rationale, component by component:

| # | Component | Place | Why there |
|---|---|---|---|
| ① | Status line (dot + hint) | Header left | Replaces the old `status_label` under the robot — state belongs in chrome; saves a whole row. Extends existing `context_label`. |
| ② | Mode toggle (voice\|text) | Header center-right, **fixed slot**, never re-parented | Kills fragile re-parenting in `_apply_mode_layout`; discoverable; symmetric with chrome. Wake toggle stays voice-only. |
| ③ | Window controls | Header right | Unchanged (hide/maximize/close). |
| ④ | Empty-state hero | Centered in transcript region; fades out on first message | Research: fresh chats earn guided welcome; continuing chats stay focused (S8/S10). Gives the robot face a real home. |
| ⑤ | Transcript | flex:1, full bleed minus root margins | Main surface; bubbles capped 75%/82% with role asymmetry. |
| ⑥ | Typing dots | Transient assistant-row at thread tail | Occupies Sopno's slot so dots→first-token handoff is spatially seamless. |
| ⑦ | Streaming caret | Inline tail of streaming bubble | Aliveness contract (S8). Removed on completion. |
| ⑧ | Composer dock | Bottom, pinned, autogrow, Send⇄Stop morph | Standard; Stop-in-send-position per S7. |
| ⑨ | Footer strip | Very bottom, ≤18px | Context meter % left + 1-line log right; both widgets exist — consolidated; hidden <320w. |
| ⑩ | Dashboard (Ctrl+D) | Overlay sheet above transcript, slides from right | Today it shoves the chat; overlays never reflow the thread. |
| ⑪ | Robot avatar | 20px circle left of "Sopno" tag on assistant bubbles | Presence continuity after hero collapse. |
| ⑫ | Copy action | Right side of assistant tag row; dim → bright on hover; persistent on last message | Research: copy is mandatory; hover-reveal elsewhere (S8). |
| ⑬ | Jump-to-bottom pill | Floating bottom-center of transcript; only when scrolled up ≥200px | Scroll-discipline without yanking the view (S8). |

**Removed / relocated from current build**

- `status_label` ("Idle") under robot → merged into ①.
- Robot-as-permanent-fixture above chat → becomes ④ hero + ⑪ avatars.
- `wake_toggle` in text mode → hidden entirely (voice-only concept).
- `resize_hint` glyph → merged into footer strip right edge.

---

## 4. Layout Blueprints (per breakpoint)

Maps onto presets in `visuals/theme.py` (`SIZE_PRESETS`, `MIN_SIZE`) and the
existing three tiers of `_metrics_for_width()` (`behaviors/responsive.py`).

### 4.1 Small — w < 320 (preset 280×360)

```
┌──────────────────────────┐
│ ● Ready      [🎙|⌨] – □ ✕ │  header 28px, icons 12
├──────────────────────────┤
│      (hero, compact)     │
│        ┌──────┐          │
│        │robot │ 56px     │
│        └──────┘          │
│   Ask me anything…       │
│  ┌───────┐┌───────┐ →    │  chips: single-row horizontal scroll
│  └───────┘└───────┘      │
│ ┌─────────────────────┐  │
│ │ ◉ Sopno             │  │  bubbles max-width 85%
│ │ text 8pt, pad 7     │  │  no timestamps, no copy button
│ └─────────────────────┘  │
│        ┌───────────────┐ │
│        │ You           │ │
│        └───────────────┘ │
├──────────────────────────┤
│ ╭──────────────────────╮ │
│ │ Message…          ➤  │ │  dock radius 12, send 28
│ ╰──────────────────────╯ │
└──────────────────────────┘  footer strip HIDDEN
```

### 4.2 Medium — 320 ≤ w < 440 (preset 380×560) — canonical blueprint

Section 3 diagram verbatim: header 32px · hero robot 78px · chips wrap 2+1 ·
bubbles max 80% · body 9pt · timestamps on group-first only · footer strip
16px (log only).

### 4.3 Large — w ≥ 440 (preset/full 520×740+)

Same skeleton with air: header 34px · hero robot 110px · chips grid 2×2 ·
bubbles max 75% (~70ch measure enforced) · body 10pt · line-height ≈1.55 ·
footer shows context meter + log. When maximized, the thread column itself is
center-capped at ~560px so line measure never exceeds comfortable reading —
extra width becomes symmetric gutters, not longer sentences.

---

## 5. Component Specs

All colors reference `STATE_ACCENT` / existing literals (`visuals/theme.py`)
so text mode and voice mode stay one family:
standby `#8B9BB4` · listening `#5EB1F5` · thinking `#9B8CF2` · speaking
`#4ADE9A` · error `#F07178`.

### 5.1 Header status line (①)

```python
# widgets/status_dot.py — 8px circle + halo, QPainter pulse
# hint label reuses context_label styling (IBM Plex Sans 8–9pt)
```

- Dot color = `STATE_ACCENT[state]`; pulses (scale 1→1.25, InOutSine 1.6s loop)
  only in *thinking*/*speaking*; static otherwise.
- Hint copy mirrors the bilingual `hints` dict already in `status.py`.
- Error: dot `#F07178`; hint "Something went wrong".

### 5.2 Mode toggle relocation (②)

Move `HoloToggle("mic", "newspaper")` from the voice-stage controls row into
the header layout between `context_label` and chrome. `_apply_mode_layout()`
then reduces to visibility flips — no `removeWidget`/`setParent` dance.
Wake toggle simply hides in text mode. Tooltips gain the shortcuts:
"Voice ↔ Text (Ctrl+T / Ctrl+R)".

### 5.3 Empty-state hero (④)

```python
class TextHero(QWidget):
    """Guided welcome: robot face + greeting + starter chips.
    Visible only while chat count == 0; fades out on first message."""
```

- Composition: `AliveRobotFace(size=hero_size)` + greeting QLabel + chips row.
- Greeting: "Ask me anything — English or Bangla." (9pt, `#8B9BB4`,
  letter-spacing 0.4). Optional time-aware variant ("Good evening…").
- Chips (3 starters, e.g. *"What can you do?"*, *"আজকের সময় কত?"*,
  *"Summarize my notes"*): glass pill QSS — fill 6%, border 10%, radius-full,
  9pt, ≥24px hit height. Click **fills the composer** (not auto-send — user
  stays in control) and focuses input. Tab-focusable, Space/Enter activates.
- Exit: opacity 1→0 + y −8 + scale .98 over 220ms OutCubic → `setVisible(False)`.

### 5.4 Transcript & bubbles (⑤⑪⑫) — `ChatThread` upgrade

New public API (keeps `add_message(role, text)` backward-compatible):

```python
def add_message(self, role, text, *, ts=None, streaming=False): ...
def begin_typing(self) -> None           # inserts dots row
def end_typing(self) -> None
def finalize_streaming(self) -> None     # caret off, copy enabled
```

Bubble anatomy (assistant):

```
┌──────────────────────────────────────┐
│ (◉) Sopno                     14:32  │  tag row: 20px avatar · 7pt tag · dim ts · copy ⧉
│ Body text 9–10pt #D7DEE9, lh 1.5,    │
│ selectable, word-wrap                │
└──────────────────────────────────────┘
 fill rgba(255,255,255,.05) · border rgba(255,255,255,.08)
 radius 14 (top-left 4)
```

User bubble mirrored: fill `rgba(94,177,245,.13)`, border
`rgba(94,177,245,.22)`, radius 14 (top-right 4), **no avatar**, tag "You"
in `#6EA8D8`.

Rules encoded:

- Max width via width-constrained wrapper rows — `QHBoxLayout` with
  leading/trailing stretch ratios **1:4** (user, right) / **4:1**
  (assistant, left). Pure layout, no custom painting.
- Grouping: consecutive same-role within 60s ⇒ drop tag row, spacing 4px;
  role change or >60s ⇒ spacing 10–12px + tag row restored.
- Timestamps: `HH:MM`, 7pt, 35% alpha, tag-row right, group-first only.
- Copy button: flat 16px icon in tag row; copies raw text.
- Cap 40 bubbles (existing behavior kept); trim drops **whole groups** from
  head so grouping stays correct.
- Streaming bubble created once via `streaming=True`; body label updated
  in place (`setText`) — no relayout storms; caret appended per §5.6.

### 5.5 Typing dots (⑥)

Assistant-slot row: three 5px circles in `#9B8CF2`, staggered bounce
(y ±4px, 1.0s loop, 140ms offsets) + faint glow. Appears immediately on submit
(≤200ms acknowledgment, S12). After 2s a dim caption fades in beneath:
"Still thinking…" (escalation rule, S8/S12). Removed the instant the first
reply chunk lands — replaced by the real bubble in the same slot.

### 5.6 Streaming caret (⑦)

Inline trailing block `▊` (~0.9em) in `#818cf8`, step-end blink 0.8s.
Hidden on finalize. While active, header dot rides thinking→speaking shift.

> Backend note: today `worker.reply_generated` fires once with full text.
> Ship caret+dots against that signal now (dots → full text + brief caret
> sweep → finalize). True token streaming arrives later by emitting an
> additional `reply_chunk(str)` from the assistant pipeline (Ollama already
> streams — emit per token); the widget API above accepts incremental updates.

### 5.7 Jump-to-bottom pill (⑬)

Glass chip "↓ Latest", bottom-center of transcript, visible only when
`scrollbar.value < maximum - 200`. Click ⇒ smooth-scroll to bottom and resume
auto-follow. Auto-follow pauses on any upward user scroll (wheel/drag),
exactly per S8.

### 5.8 Composer dock (⑧)

Keep existing glass dock + autogrow (36→120px); add:

- **Send ⇄ Stop morph**: while thinking/streaming, circular send swaps icon
  to stop glyph, border shifts to `rgba(240,113,120,.5)`, tooltip
  "Stop generating". Press emits `worker.stop_generation()` (new plumbing;
  Esc also maps to it while streaming). Partial text remains, timestamp slot
  shows "(interrupted)".
- **Send disabled** when input empty *or* generation busy — Stop never disabled.
- Placeholder cycles bilingual hints when idle: "Type a message…" /
  "লিখুন…" (subtle, ~6s period).
- Keep Enter=send / Shift+Enter=newline (already correct).

### 5.9 Footer strip (⑨)

Single 16–18px row: left — mini context meter (2px-high rounded bar, ~64px,
green→amber→red thresholds reused from the TokenRing logic in
`hud/PYWEBVIEW.md` §TokenRing); right — existing 1-line log (mono 6–7pt,
truncated). Hidden below 320w (`show_log=False` exists — extend to strip).

### 5.10 Dashboard overlay (⑩)

Re-parent `DashboardPanel` out of `root` into an overlay child of
`central_widget`; geometry = transcript region expanded; slide-in translate-x
260ms OutCubic + backdrop dim `rgba(0,0,0,0.35)` click-to-close. Ctrl+D
unchanged. Thread never reflows.

---

## 6. Motion & Animation Spec

One motion language with the voice page — lerp/ease-out-cubic everywhere,
nothing linear except rotation/blink loops.

| Element | Animation | Curve | Duration |
|---|---|---|---|
| Bubble entrance | opacity 0→1, y +12→0, scale .98→1 | OutCubic | 220ms |
| Hero exit | opacity→0, y −8, scale .98 | OutCubic | 220ms |
| Typing dots | per-dot y ±4 loop, stagger 140ms | SinEase loop 1.0s | while thinking |
| "Still thinking…" caption | fade in to 45% alpha | OutQuad | 300ms @ t+2s |
| Caret blink | alpha step-end 1⇄0 | discrete | 800ms loop |
| Send⇄Stop morph | icon crossfade + border-color lerp | OutQuad | 160ms |
| Header dot pulse | scale 1→1.25→1 | InOutSine loop | 1.6s (thinking/speaking only) |
| State accent shifts | color lerp | OutCubic | 400ms (voice parity) |
| Jump-pill pop | scale .9→1 | OutBack | 180ms |
| Dashboard sheet | x-slide + backdrop fade | OutCubic | 260ms |
| Error bubble shake | x ±4 decaying ×3 | — | 350ms |

Implementation notes:

- One shared `QTimer` at 33ms (voice-page `TICK_MS` parity) drives dot pulse /
  typing dots; entrances via `QPropertyAnimation` on a float `pyqtProperty`
  per bubble (avoids `QGraphicsEffect` rasterization cost).
- All loops live only while their state is active — zero timers when idle.
- Reduced motion: `config.json → hud_reduced_motion: false` (default off).
  When true: entrances instant, dots become static "…" label, caret solid,
  pulse disabled.

---

## 7. Text-Mode State Machine

Same states as voice (`AppState` parity in `DESIGN.md §5.2`), rendered
text-side. Tracked per turn (S10):

```
            submit()
 ┌──────┐ ─────────► ┌─────────┐ first chunk ┌───────────┐
 │ IDLE │            │ THINKING│ ──────────► │ STREAMING │
 └──────┘ ◄───────── └─────────┘             └─────┬─────┘
    ▲        stop()/error                          │ done
    │                                              ▼
    │              ┌──────────┐  tts starts  ┌──────────┐
    └───────────── │  ERROR   │◄─ tts error ─│ SPEAKING │ ──► IDLE
                   └──────────┘              └──────────┘
```

Visual contract per state (dot / hero face / thread / dock):

| State | Header dot | Hero face | Thread | Dock |
|---|---|---|---|---|
| idle/standby | `#8B9BB4` static | breathing | — | send enabled iff text |
| composing | `#5EB1F5` | breathing | — | send enabled |
| thinking | `#9B8CF2` pulse | swirl | dots row (+2s caption) | Stop |
| streaming | `#9B8CF2→#5EB1F5` | attentive | caret | Stop |
| speaking (TTS) | `#4ADE9A` pulse | mouth anim | finalized + actions | send locked |
| error | `#F07178` | concerned | inline error bubble w/ Retry | draft preserved |

Submission lock: `THINKING`/`STREAMING` disable send (never Stop); input stays
editable so drafts survive interrupts (research rule: never clear the draft).

---

## 8. Responsive Token Map

Extends `_metrics_for_width()` — additive keys only; existing keys untouched;
breakpoint edges stay `320` / `440` so voice and text share metrics.

| Key | <320 | 320–439 | ≥440 | Consumer |
|---|---|---|---|---|
| `bubble_max_user` | .85 | .80 | .75 | stretch ratio |
| `bubble_max_bot` | .88 | .84 | .82 | stretch ratio |
| `avatar` | 16 | 20 | 22 | assistant tag row |
| `ts_visible` | False | True | True | tag row |
| `copy_visible` | False | True | True | tag row |
| `chip_flow` | h-scroll row | wrap 2+1 | grid 2×2 | hero |
| `hero_face` | 56 | 78 | 110 | TextHero |
| `thread_gutter` | 0 | 8 | auto (center-cap 560) | transcript margins |
| `footer_strip` | hidden | log only | log + context meter | footer |
| `dash_overlay_w` | 100% | min(320,w−24) | 360 | dashboard sheet |
| `body_lh` | 1.45 | 1.50 | 1.55 | bubble label spacing |

---

## 9. Implementation Plan

Phased so each step ships visible value without touching the working voice
page. File-by-file, following the package layout
(`widgets/` for components, `behaviors/` for mixins, `visuals/` for shared
constants — per Step 7 folder organization in `roadmap/status.md`).

### P1 — Skeleton & placement (the layout itself)

1. **`window.py`** — relocate mode toggle into header row; delete
   `status_label` row; insert footer strip; move dashboard into overlay
   container; simplify `_apply_mode_layout()` to visibility flips.
2. **`widgets/text_hero.py`** (new) — `TextHero` widget; visibility bound to
   `chat.is_empty`.
3. **`responsive.py`** — extend metric dicts per §8; apply calls in
   `_apply_responsive`.

```python
"""
sopno/ui/hud/widgets/text_hero.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Empty-state hero: robot face + bilingual greeting + starter prompt chips.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from sopno.ui.hud.visuals.icons import _paint_icon

_CHIP_QSS = """
    QPushButton {{
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 14px;
        padding: {pv}px {ph}px;
        font-size: {pt}pt;
        color: #AAB8CC;
    }}
    QPushButton:hover {{
        background: rgba(94, 177, 245, 0.14);
        border-color: rgba(94, 177, 245, 0.35);
        color: #E4EAF2;
    }}
"""


class TextHero(QWidget):
    """Shown while the transcript is empty; collapses on first message."""

    compose_requested = pyqtSignal(str)   # chip text → fills composer

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(10)

        self.face = ...  # AliveRobotFace(size=hero_size) — sized via apply_scale
        col.addWidget(self.face, 0, Qt.AlignCenter)

        self.greeting = QLabel("Ask me anything — English or Bangla.")
        self.greeting.setAlignment(Qt.AlignCenter)
        self.greeting.setFont(QFont("IBM Plex Sans", 9))
        self.greeting.setStyleSheet(
            "color: #8B9BB4; background: transparent; letter-spacing: 0.4px;")
        col.addWidget(self.greeting, 0, Qt.AlignCenter)

        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(6)
        col.addLayout(self._chips_row)

    def set_chips(self, labels: list[str]) -> None:
        """Build starter-prompt chips; clicks emit compose_requested(label)."""
        ...
    def apply_scale(self, *, face: int, pt: int, pv: int, ph: int) -> None: ...
    def collapse(self) -> None:
        """220ms OutCubic fade+rise, then setVisible(False)."""
```

### P2 — Thread quality

4. **`chat.py`** — role asymmetry, max-width stretch wrappers, grouping +
   timestamps, avatars, copy action, entrance tween property.
5. **`chat.py`** — `begin_typing`/`end_typing` dots row + 2s escalation
   caption (QTimer-guarded).
6. **`widgets/status_dot.py`** (new) + **`status.py`** — route states through
   the §7 machine; drive dot color/pulse from `STATE_ACCENT`.

```python
"""
sopno/ui/hud/widgets/chat.py   (upgraded public surface)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Role-asymmetric grouped transcript with streaming support.
"""

class ChatThread(QScrollArea):
    GROUP_WINDOW_S = 60          # same-role merge window (research: ~60s)

    def begin_typing(self) -> None:
        """Insert 3-dot assistant-slot row immediately on submit."""

    def end_typing(self) -> None:
        """Remove dots; called on first chunk or error."""

    def add_message(self, role: str, text: str, *,
                    ts=None, streaming: bool = False) -> None:
        """streaming=True creates the live bubble (caret attached)."""

    def update_streaming(self, chunk: str) -> None:
        """Append/replace text in the live bubble without relayout storms."""

    def finalize_streaming(self) -> None:
        """Caret off; copy enabled; '(interrupted)' aware."""
```

Bubble row construction (core trick — width capping by stretch ratios):

```python
row = QHBoxLayout()
row.setContentsMargins(0, 0, 0, 0)
if is_user:                       # right-aligned, capped
    row.addStretch(4)             # 4 : 1  → bubble ≈ 80% max
    row.addWidget(bubble, 1)
else:                             # left-aligned, capped
    row.addWidget(bubble, 4)      # 4 : 1
    row.addStretch(1)
self._col.insertWidget(self._col.count() - 1, _wrap(row))
```

### P3 — Streaming & control

7. **`window.py`** — send⇄stop morph (icon swap + QSS state), Esc-stop
   shortcut while streaming, draft preservation (input never cleared on
   interrupt).
8. **`chat.py`** — streaming caret label + jump-to-bottom pill + follow logic:

```python
def _on_scroll(self, value: int) -> None:
    at_bottom = value >= self.verticalScrollBar().maximum() - 4
    if not at_bottom and value < self._last_value:      # user scrolled up
        self._follow = False
        self._pill.show_animated()
    elif at_bottom:
        self._follow = True
        self._pill.hide()
    self._last_value = value

def _maybe_autoscroll(self) -> None:
    if self._follow:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
```

9. **Optional backend** — `worker.py` gains `reply_chunk = pyqtSignal(str)`;
   assistant pipeline emits per Ollama token; `finalize` on done. UI already
   prepared by the P2 API.

### P4 — Polish

10. Error bubble w/ Retry action; interrupted marker; bilingual placeholder
    cycle.
11. Context meter in footer strip; `hud_reduced_motion` honored everywhere
    (single helper: `motion_enabled() → bool` reading settings once).
12. **Tests** (mirror `tests/` naming): `tests/ui/test_chat_thread.py`
    (grouping window, trim-drops-whole-groups, streaming finalize),
    `tests/ui/test_text_hero.py` (chip emission, collapse), extending the
    existing suite style (`python3 -m unittest discover -s tests`).

---

## 10. Performance & Accessibility Budget

- **Frame budget**: shared 33ms timer; per-frame work = dot pulse (2 ellipses)
  + caret alpha flip + at most one entrance tween. No per-bubble timers.
  Idle ⇒ zero repaints (all loops state-gated).
- **Glass layering**: dock + chips + jump-pill only; thread bodies sit on the
  opaque central background — reading surface exempt from translucency
  (production glass rule, S14/S16).
- **Contrast**: body `#D7DEE9`/`#E4EAF2` on ≤8% white-over-`rgb(12,16,24)`
  ≥ 9:1 worst case; dim styles reserved for non-essential info (timestamps,
  hints); accent pairings > 4.5:1 at tag sizes (S13 worst-case discipline).
- **Hit targets**: chips/copy/jump-pill ≥ 24px effective height (WCAG 2.2);
  keyboard — chips tabbable, Enter sends (existing), Esc = stop / close
  dashboard, Ctrl+T/R/D/Q/M unchanged.
- **Selection & AT**: bubble bodies stay `Qt.TextSelectableByMouse`;
  accessibility event raised on message **finalize**, not per-token
  (polite-live-region analog).

---

## 11. Research Sources

Primary URLs consulted August 24, 2026:

1. https://www.conferbot.com/blog/chatbot-window-ui-design
2. https://www.aiuxdesign.guide/guides/conversational-ui-guide/anatomy-of-a-chat-interface
3. https://www.uxpin.com/studio/blog/chat-user-interface-design/
4. https://lovable.dev/guides/how-to-build-a-chatbot-ui
5. https://ethora.com/blog/chat-app-ui-ux-design/
6. https://mui.com/x/react-chat/customization/look-and-feel/
7. https://www.metacto.com/blogs/ai-chat-ux-patterns-for-production
8. https://skills.smoothui.dev/docs/ai-chat
9. https://www.aiuxdesign.guide/guides/conversational-ui-guide/typing-indicators-and-streaming-responses
10. https://frontendpatterns.dev/guides/managing-ai-response-states
11. https://appsavvy.dev/blog/streaming-ai-responses
12. https://uxmagic.ai/blog/ai-chat-interface-design-patterns
13. https://tsev.dev/posts/2025-07-14-glassmorphism-test-worst-case-scenario/
14. https://clay.global/blog/glassmorphism-ui
15. https://pixcode.io/en/blog/css-glassmorphism-2025/
16. https://superdesign.dev/styles/glassmorphism

Internal baselines: `doc/voice-mode-ui-design.md` (orb research + animation
constants), `doc/hud/DESIGN.md` (premium formula, theme tokens),
`doc/hud/PYWEBVIEW.md` (TokenRing thresholds reused by the context meter).

---

**Document Version**: 1.1
**Last Updated**: August 24, 2026
