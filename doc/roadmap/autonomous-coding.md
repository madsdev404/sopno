# 🤖 Sopno Autonomous Coding — Design & Implementation Guide

Research-backed design for turning Sopno into an agent that plans, writes,
tests, and submits real code changes on its own — instead of answering one tool
call at a time. This is expected to be Sopno's **primary workload**, so the
harness (the machinery around the LLM) is the deliverable, not the prompt.

> Status: **implemented** — the coding harness is live. `CodingAgent` in
> `sopno/core/coding/` (refactored from one ~844-line module into the
> single-purpose package `agent`/`tools`/`worktree`/`verify`/`prompts`/`util`)
> runs a plan→recite→act→verify loop in a git worktree with gated writes,
> checkpoint commits, harness-owned docs, and terminal states
> `success | no_op | blocked | stalled | exhausted`. On top of the core loop
> the full harness is wired: red-test baselines (`coding_require_red_test`),
> approval modes (`coding_approval_mode`: `auto_merge_guardrailed` /
> `unattended` / `review_required`), sub-agent escalation (`delegate`,
> `escalate`, `run_review`), and guardrailed auto-merge into main (re-verify
> the merged tree, roll back on red) with optional push (`coding_push_enabled`),
> plus `run_coding_batch` for ticket queues. The coding tools
> (`coding_run`/`coding_status`) and daemon scheduling make it a background
> agent task (see [long-running-agents.md](./long-running-agents.md));
> [features.md](./features.md) §41 lists the original scope under
> "Future Features".

---

## 1. What "autonomous coding" means

A coding agent is a program that takes a natural-language goal ("fix issue 482",
"add Stripe webhooks") and acts on a **real repository over many steps** until it
believes the goal is met. Three properties separate it from an inline autocompleter:

1. **Multi-step planning** — it decomposes the goal into sub-goals and decides
   the next step from observations.
2. **Real tool use** — it runs shell commands, edits files, runs tests, calls git.
3. **Self-verification** — it reads its own output (failing test, stack trace,
   lint error) and decides whether to retry.

The unit of output is a **pull request / committed branch**, not a line.

**Why Sopno needs a real harness, not a bigger prompt:** production coding agents
all run the *same* ReAct loop; the gap between good and bad results is almost
entirely the harness around it. Two agents on the same model scored 16–20 points
apart on SWE-bench Verified purely from scaffold differences (verification
cadence, context management, stopping rules). Only ~1.6% of Claude Code's
codebase is AI decision logic — the rest is operational infrastructure.

---

## 2. The canonical control loop

```
1. INGEST   read the issue, relevant files, failing test
2. PLAN     produce a short ordered task list (plan file)
3. ACT      pick a tool (read_file, edit_file, run_terminal, run_tests)
4. OBSERVE  read the tool output verbatim
5. REFLECT  does the observation match the plan? what changed?
6. DECIDE   continue | replan | escalate | stop
7. VERIFY   tests, type-check, lint, re-read the diff
8. SUBMIT   commit on a branch (or open a PR) with a summary
```

```
while task_not_complete:
    state   = read_files() + read_test_output() + read_errors()
    context = harness.select_context(state, task)
    plan    = model.reason(context, task)
    result  = harness.dispatch_tool(plan.next_action)
    outcome = harness.evaluate(result)
    if outcome.needs_retry:   context += outcome.error_trace; continue
    if outcome.needs_human:   harness.escalate(outcome); break
    harness.checkpoint(result)   # git commit / progress file
```

Every real system (Claude Code, Cursor, Codex CLI, Cline, Aider, OpenDev,
Devin, Replit Agent) is this loop. The differences — and the design work — live
in how each step is executed.

---

## 3. State of the art (2026) — the decisions that matter

### 3.1 Finding the right files
- **Naive embedding RAG misses cross-file symbol relationships.** Working
  approaches: hybrid **BM25 + embeddings** plus a **code-graph / tree-sitter
  symbol index** (Augment Code, Cursor, Claude Code), or **explicit file
  addition** (Aider trades autonomy for precision).
- Sopno already has `search_files` (name + content grep) and terminal access —
  grep-based discovery with symbol-aware hints is the realistic starting point.

### 3.2 Working memory vs. full-repo context
- Agents that keep the whole repo in context **drift**; agents that summarize
  aggressively **forget**. The 2026 pattern: a **main loop with small working
  memory** plus **throwaway sub-agents** that run noisy tools (browser, full
  test suite) and return only a final observation.
- Cursor's finding: agents **drift after ~50 tool calls**; mitigate by reciting
  a `todo.md`/plan file into the end of context every turn.
- Large observations (web pages, big logs) should be **written to disk** and
  only a file reference kept in context (filesystem-as-extended-context).

### 3.3 Verification cadence (highest-leverage lever)
- Agents that **run tests after every change** massively outperform agents that
  verify only at the end (16-point SWE-bench swing, same model).
- Simon Willison's **red/green pattern**: write the failing test first, then let
  the agent make it pass. Tightest loop, least drift.

### 3.4 Stopping conditions (the hardest part)
- "All tests pass" is a **weak** signal (tests can be wrong, missing, or
  trivially patched). Strong stopping rule: **tests pass AND diff is small
  enough to review AND the agent can summarize what it changed in one
  paragraph**.
- The five-level verification ladder (what counts as "verified"):

  | Level | Check | Autonomous? |
  |-------|-------|-------------|
  | 1 | Deterministic: exit code, assertion, golden output | ✅ yes |
  | 2 | Rule/constraint: linter, schema, policy check | ✅ yes |
  | 3 | Delayed field truth: full tests, deploy, real response | ⚠️ slow |
  | 4 | Model-as-judge (rubric score) | 🛑 opinion — a *different* model must judge |
  | 5 | Human checkpoint | 🛑 supervision, not verification |

  A loop is only as autonomous as the level its verifier truly sits at.
  Never let the same agent approve its own level-4 judgment.

### 3.5 Terminal states (never let an error be a win)
Name them explicitly: **success · no-op · blocked · stalled · exhausted**.
- *Error / exhausted budget ≠ success.*
- Stopping is rarely an invented number: it's the goal being met, a
  **stagnation detector** (N rounds without progress), or a **budget ceiling**
  (turns / tokens / wall-clock).
- Hard caps on iterations and tokens per ticket are universal (Devin caps,
  Replit caps, all production loops cap).

### 3.6 Error taxonomy (retry vs. stop)
| Condition | Handling |
|-----------|----------|
| Clean finish (no tool calls) | Return final text |
| Max turns / budget hit | Stop, report partial state |
| Transient tool error (network, locked file) | One silent retry, then backoff |
| Permanent tool error (missing binary, bad credential) | Stop and escalate — do not burn turns |
| Model refusal | Log and surface |

Decide which errors are retryable **up front** so one bad call doesn't cascade.

### 3.7 Safety architecture (defense in depth — none is enough alone)
1. **Deny-first permission rules** — deny overrides ask overrides allow;
   unrecognized actions escalate to the user (Claude Code's model).
2. **Per-tool gate** — blocklist/allowlist at tool dispatch (Sopno already has
   `terminal_blocklist` + file `_authorize`).
3. **OS-level sandbox** where possible — `bubblewrap`/containers; filesystem
   boundary + network boundary. Anthropic cut permission prompts 84% when
   actions were safe *by construction*.
4. **Git as rollback** — every meaningful step becomes a commit; one bad step is
   one `git revert` away (Aider's model).
5. **Approval-fatigue guard** — interactive-only approvals are behaviorally
   unreliable (users approve ~93% of prompts); safety must hold independently
   of human vigilance.
6. **Secrets** — scan workspace before start, redact in shell output, refuse
   `.env`/`.ssh`/`*.pem` reads (Sopno's `file_blocked_paths` already does this).
7. **Scope discipline** — explicit path bounds ("touch only `lib/billing`") and
   a **diff-size budget**; the biggest cause of unreviewable output is scope
   creep.

### 3.8 Loop engineering (the newest layer)
A **loop specification** is a bounded, reusable artifact a human hands to the
harness: **trigger → goal → execution → verification → stopping rule → memory**.
- Design *the loop that prompts the agent*, not step-by-step prompts.
- Memory lives **on disk** (plan file, progress notes, handoff doc), never only
  in the conversation — "the agent is amnesiac, the filesystem isn't."
- **Maker–checker split**: the one who produces must not be the one who
  approves (separate implementer and reviewer roles/sub-agents).

### 3.9 Human-in-the-loop boundary
Three production postures (pick per task class):
- **Review-required** — every diff reviewed before merge (default for anything
  touching money/auth/production).
- **Auto-merge with guardrails** — merge if tests pass + no protected files
  touched + diff under N lines (low-stakes: bumps, docs, lint).
- **Auto-merge with rollback** — merge + canary watch + auto-revert on metric
  regression (mature infra only).

And the two operation modes: **cloud/background** (tens of minutes, sandboxed,
opens a PR) vs **local/observed** (user watches and steers). Sopno is a *local,
offline* assistant → the **local/observed** mode plus optional unattended mode
with strict guardrails.

---

## 4. Proposed Sopno design

### 4.1 Place in the existing architecture
Reuse, do not duplicate:

| Building block | Existing Sopno asset |
|----------------|----------------------|
| Shell + blocklist | `dev/terminal` tools (`_run_command_raw`, `terminal_blocklist`) |
| File read/write with permission gates | `files/files` tools (`_authorize`, pending-action confirmations) |
| Git | `dev/git` tools (`git_status/diff/add/commit/branch/stash`) |
| Research delegation | `automation/subagents` (`researcher` subagent) |
| Reviewing delegation | `automation/subagents` (`reviewer` subagent) |
| Scheduling / background | `automation/reminders`, `automation/rules`, daemon pollers |
| Long-term memory | `memory/store.py` (facts, decisions, lessons) |
| LLM tool loop | `core/assistant.py` tool-calling loop + `llm/` client |
| Session/handoff persistence | (new — see §4.5) |

### 4.2 New module: `sopno/core/coding.py` — `CodingAgent`

```
CodingAgent
 ├── run(task_spec)            # the loop: INGEST→PLAN→ACT→OBSERVE→REFLECT→DECIDE→VERIFY→SUBMIT
 ├── _plan(task)               # writes plan file; returns ordered task list
 ├── _dispatch(tool_call)      # reuses existing execute_tool + permission pipeline
 ├── _verify()                 # runs the verification recipe (see §4.6)
 ├── _stop_condition(state)    # terminal-state machine: success/no-op/blocked/stalled/exhausted
 ├── _checkpoint()             # git commit + progress file update
 ├── _escalate(reason)         # human approval gate (pending-action pattern)
 └── session                    # durable session state (SQLite) for resume
```

Plus one tool for the user:
- `run_coding_task(task, scope_paths, verify_recipe, max_*  …)` — starts the
  loop on a new isolated branch/worktree; returns progress + final summary.
- `coding_status(session_id)` — progress, last commits, current phase.

### 4.3 Task input (the "ticket")
A good ticket is the difference between a mergeable PR and 800 garbage lines:
- **Explicit acceptance criteria** ("fix the slow page" with no acceptance
  criteria is the classic failure).
- **Optional red test** — write the failing test first (red/green).
- **Scope bounds** — `paths_allowed` (default: empty = whole repo, but
  recommended to bound).
- **Verification recipe** — exact commands: `venv/bin/python -m unittest
  discover -s tests`, `ruff check .`, a smoke command. Stored as a
  `verify_recipe` (list of `{command, kind}`).
- **Checkpoints** — markers in the plan where the loop must stop and ask.

### 4.4 Planning & context (anti-drift)
- Write `PLAN.md` + `progress.md` in the run's workspace. Re-cite the plan's
  remaining items into the tail of every prompt (**recitation**, Cursor's
  anti-drift fix).
- **Just-in-time retrieval** over whole-repo dumps: use `search_files` (grep)
  + tree-sitter-style symbol hints, not embedding RAG over the whole repo.
- Keep a **small working memory** (last 3–5 actions + current sub-goal). Delegate
  expensive reads (full test suites, long logs) to a throwaway **worker
  sub-agent** that returns only a digest.
- Compaction: when the token budget nears the limit, summarize old turns into a
  digest (append-only raw log kept on disk for audit). Filesystem-as-context for
  anything big.

### 4.5 Workspace isolation & git safety (non-negotiable)
- **Always run on a fresh branch in a git worktree** (`git worktree add`)
  derived from the repo's current HEAD. The main checkout stays untouched.
- **Checkpoint = commit**: after each meaningful unit of work, `git commit` with
  a conventional message. Every step is one `git revert`/`git reset` away.
- End state: the worktree branch is left for **human review and merge** by
  default (review-required posture). Optional guardrailed auto-merge (see §4.8).
- **No `git push`** unless an explicit `coding_push_enabled` config key is set
  (same stance as the existing git tools).
- Scope enforcement: before each file write, check against `paths_allowed` +
  existing `_authorize` gates.

### 4.6 Verification (the core of autonomy)
- Run the **verification recipe after every ACT that changes files** (red/green
  cadence). Cheap checks (lint, unit-test subset) on every step; full suite +
  smoke at the end and at checkpoints.
- Track a **per-run verification state**: what passed, what failed, on which
  commit. The loop decides using this state, never vibes.
- Map each recipe step to a **ladder level** (§3.4). Level-4 judgments must be
  made by the `reviewer` sub-agent (a *different* model instantiation / role),
  never the implementing session.

### 4.7 Terminal states & budgets
| State | Meaning | Exit path |
|-------|---------|-----------|
| `success` | Goal met + verifier passed + diff within budget + 1-paragraph summary written | Submit branch + summary to user |
| `no_op` | Nothing changed (nothing to do) | Report cleanly |
| `blocked` | Needs human input (approval, ambiguity, missing info) | Escalate via pending-action gate |
| `stalled` | N rounds (default 6) without progress (stagnation detector) | Escalate with what was tried |
| `exhausted` | Any budget ceiling (turns/tokens/wall-clock/diff-size) | Stop, report partial work |

Config budget keys (defaults): `coding_max_turns` (150), `coding_max_tokens`
(300k), `coding_max_wall_minutes` (120), `coding_max_diff_lines` (800),
`coding_stall_rounds` (6), `coding_verifier` ("reviewer").

### 4.8 Human-in-the-loop postures (config)
```
coding_approval_mode:  "review_required"   # default — human merges every branch
                       | "auto_merge_guardrailed"  # tests green + protected paths untouched + diff ≤ cap
                       | "unattended"       # batch: queue tickets, review results later
coding_protected_paths: ["sopno/core/assistant.py", "config.json", ...]  # deny edits
coding_require_red_test: true
```

### 4.9 Safety checklist (every run)
- [ ] Runs in an isolated worktree/branch; main checkout untouched
- [ ] `terminal_blocklist` + `_authorize` + `file_blocked_paths` all apply
- [ ] No secrets reach the model: workspace pre-scanned, shell output redacted
- [ ] `git push`/remote/network actions gated by config
- [ ] New-dependency changes flagged for human review (lockfile diff)
- [ ] Every shell command logged to the session action log
- [ ] Budgets enforced; errors never recorded as success
- [ ] On session crash: worktree + progress file + action log allow resume

---

## 5. Failure modes & mitigations

| Failure | Mitigation |
|---------|-----------|
| Overconfident wrong patch (tests missing the case) | Red test first; require acceptance criteria; reviewer sub-agent on diff |
| Infinite loop / fix A breaks B breaks A | Stagnation detector + hard turn/token caps; escalate, don't spin |
| Scope creep (refactors surrounding code) | `paths_allowed` bounds + diff-size budget + plan checkpoints |
| Secret leakage | Pre-scan, redact outputs, blocklist `.env`/`.ssh`, pre-commit scan |
| Hallucinated dependency | Lockfile diff review on every change; dependency allowlist |
| Context drift after ~50 calls | Plan recitation + working-memory discipline + sub-agent delegation |
| "Tests pass" but feature is wrong | Strong stopping rule (§3.4); smoke command; reviewer |
| Approval fatigue (user clicks Yes blindly) | Deny-first rules + git rollback + sandbox keep safety independent of attention |

---

## 6. Rollout plan (incremental, each step testable)

| Step | Deliverable | Verification |
|------|-------------|--------------|
| 1 ✅ | `CodingAgent` loop with **plan file + worktree + commits** on a trivial task ("add docstring to X", "write test for Y") | Manual run; branch appears with 1–3 commits |
| 2 ✅ | **Verification recipe + red/green cadence** (run recipe after each change) | Unit tests for `_verify` on fixtures |
| 3 ✅ | **Terminal-state machine + budgets + stagnation detector** | Unit tests for every state transition |
| 4 ✅ | **Escalation gates** (pending-action) + `coding_run`/`coding_status` tools + schemas | Tool tests; approval flow works in CLI + HUD |
| 5 ✅ | **Sub-agent delegation** (`delegate`, `escalate`, `run_review`) | Tests that delegation returns digests only; review gates success |
| 6 | **Resume across sessions** (durable session store, §4.5) | Crash-resume test: kill mid-run, resume from last commit |
| 7 ✅ | **Guardrailed auto-merge + unattended batch mode** (`run_coding_batch`) | Full-suite + smoke runs green on this repo's own tests |

Each step keeps the suite green and adds tests (unittest, per repo convention).
Eval targets after step 3+: **real tickets from this repo's own backlog**, with
"did the branch exist, did tests pass, did the user merge it" as the metric.

---

## 7. Sources
- Cadence — *Building autonomous coding agents in 2026* (loop, verification cadence, stopping, auto-merge guardrails)
- arXiv 2604.14228 — *Dive into Claude Code* (1.6% AI code, deny-first permissions, hook pipeline, sub-agent spawn)
- Morph — *Agent Engineering* (IMPACT framework, loop anatomy, filesystem-as-context, todo recitation, error-recovery hierarchy)
- arXiv 2603.05344 — *Building AI Coding Agents for the Terminal* (OpenDev: dual-agent plan/execute split, 5-layer safety, compaction)
- arXiv 2607.00038 — *Stop Hand-Holding Your Coding Agent* (loop specifications, 5-level verification ladder, terminal states, maker-checker)
- Mastra — *Anatomy of a harness* (approval chains, pause-for-human tools, crash recovery)
- futureagi — *How to Build a Coding Agent Harness* (6 layers, stop conditions, compaction, sandbox, permissions)
- claude-orchestrate (Cursor port) — worktree isolation, handoffs, atomic state writes, file-based Andon pause
- Kunal Ganglani — *AI Coding Workflow 2026* (CLAUDE.md, checkpoints, worktrees, parallel sessions)
- agent-handoff-protocol / agent-handoff-kit — bounded paths, handoff docs, branch-per-agent, conflict rules
