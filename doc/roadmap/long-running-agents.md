# ⏳ Sopno Long-Running Background Agents — Design & Implementation Guide

Research-backed design for agents that keep making progress **over hours, days,
or weeks** — across many context windows and process restarts — without Sopno's
main voice/CLI loop being involved. Sopno already runs as a daemon (systemd
user service, HUD on login), so this turns that daemon from a passive listener
into a host for persistent worker agents.

> Status: **implemented.** `AgentSessionStore` (durable sessions, status
> machine, heartbeat, action log) and `AgentQueue` (atomic claim, leases,
> backoff, orphan recovery, idempotency, dead-letter) in `sopno/core/agents/`;
> `AgentScheduler` (interval/cron/ETA triggers → `run` jobs) and `AgentEvents`
> (message + `state_delta` → pending input + `resume` job); `AgentWorker`
> (claims `run`/`resume` jobs, drives ORIENT → DECIDE → ACT → OBSERVE, parks on
> approval gates, enforces budgets + tool allowlists, bridges `kind='coding'`
> sessions into the `CodingAgent` worktree harness) and `AgentRuntime` (workers
> + scheduler + watchdog, orphan recovery + stale-session reclaim on boot);
> the agent tools (`agent_create/list/status/send/pause/resume/kill/log`) with
> schemas + registry; config under `agents_*`.
> Related: [autonomous-coding.md](./autonomous-coding.md) (the primary task a
> background agent will run); [features.md](./features.md) §41 lists "long-running
> background agents" under "Future Features".

---

## 1. What "long-running" means

A long-running agent keeps making forward progress on a goal **across many
sessions and sandboxes**, recovers from failure, leaves structured artifacts
behind, and resumes where it left off. The defining properties:

1. **State lives outside the context window** — plans, progress, decisions, and
   results persist to durable storage (files/SQLite), not in chat history.
2. **Pause-and-resume** — the agent sleeps through idle time (waiting for an
   approval, a file change, a schedule) and wakes on an event, not by polling.
3. **Checkpointing** — every unit of work is written durably; a crash resumes
   from the last checkpoint instead of restarting.
4. **Identity beyond a task** — the agent has a name, a goal, a budget, an audit
   trail, and accumulated memory that outlives any single run.

The "amnesiac agent, persistent filesystem" framing: each iteration starts fresh
and reads enough state from disk to keep going. A new session is like a new
engineer arriving for a shift — useless unless the previous shift wrote things
down.

---

## 2. Why this needs a new architecture, not a bigger loop

A stateless chatbot can't survive a two-week workflow. The two failure classes:

| Naive approach | What breaks |
|----------------|-------------|
| Re-prompt everything when the window fills | Forgetfulness; 2.8× more wasted context tokens vs. PAL-style designs |
| Sliding-window summarization | Coherent for ~10–50 calls, degrades on multi-hour tasks |
| Blocking threads / active polling for idle time | Wasted compute; a sleeping workflow can't wait for days |

The fix isn't a bigger context window — it's **explicit, durable, decoupled
state** plus **event-driven dormancy**.

Call-count rule of thumb (when to reach for what):
- **< 10 calls** — prompt chaining is fine.
- **10–50 calls** — sliding window + basic tool orchestration.
- **50–500 calls** — full persistent state management + structured task
  decomposition (this is the regime Sopno's agents will live in).
- **> 500 calls** — multi-agent coordination + human-in-the-loop alignment.

---

## 3. State of the art (2026) — the reference architecture (PAL)

The *Persistent Agent Loop* (PAL) generalizes what Google ADK, Anthropic's
harness guidance, MemGPT, and file-backed harnesses converged on. It runs five
phases and persists four stores between iterations:

```
while task_incomplete:
    1. ORIENT   load relevant context from persistent state
    2. DECIDE   present context to LLM, obtain next action
    3. ACT      execute via the tool-orchestration layer
    4. OBSERVE  capture results, update persistent state
    5. REFLECT  periodically assess progress & alignment (every N≈10 iters)
```

**Four persistent stores (serialized to disk between iterations):**

| Store | Contents |
|-------|----------|
| **Task graph** | Goal decomposed into subtasks with status, dependencies, outputs |
| **Working memory** | Key facts, decisions, intermediate results needed across iterations |
| **Action log** | Append-only record of every action, result, and failure (audit) |
| **Alignment record** | Human feedback, corrections, preferences accumulated over time |

**Context selection** each ORIENT phase (priority order, within token budget B):
1. Current task + immediate dependencies
2. Recent action results (last 3–5)
3. Active working-memory entries
4. Alignment constraints
5. Compressed historical context

**Three-tier failure recovery:**
- **Tier 1 (automatic):** transient failures → retry with backoff (≤3 tries).
- **Tier 2 (adaptive):** persistent failures → log the failed approach, consider
  alternatives explicitly.
- **Tier 3 (escalation):** exhausted alternatives → human with a structured
  failure report.

**Results (47 long-horizon tasks):** PAL beat the strongest baseline by 34%
absolute task-completion and cut wasted context tokens 2.8×. File-backed state
was the single largest contributor. Most pronounced in software engineering
(89% vs. 58%), where multi-file edits survive context resets.

---

## 4. Durable execution: state machines, checkpoints, event-driven wake

Google ADK's onboarding-coordinator pattern is the canonical blueprint:

1. **Explicit state schema, not chat history.** A state machine
   (`START → WELCOME_SENT → DOCUMENTS_SIGNED → … → COMPLETED`) in a durable
   store. The agent reads its current step from session state; it can't skip or
   hallucinate progress because the machine enforces the sequence.
2. **Every tool call is a checkpoint.** State is written before the next
   inference. Crash → restart reads `current_step = WELCOME_SENT` and resumes
   exactly there.
3. **Persistent sessions.** Sessions live in SQLite (survive restarts), not
   memory.
4. **Event-driven dormancy.** The agent *sleeps* during idle time; a webhook /
   file event / schedule wakes it, applies a `state_delta`, and the agent
   resumes — no polling, no blocked threads, no compute while idle.
5. **Specialized sub-agents** for stages (provisioning, review) — the coordinator
   keeps a lean prompt; each stage agent has a narrow tool set. This preserves
   reasoning quality even after weeks of accumulated state.

**Idempotency & the event log.** The append-only action/event log is what makes
an agent *recoverable and auditable*. If you can't reconstruct what the agent did
in the last 24 hours from durable storage, what you have is a long-running shell
script that happens to call an LLM. Worker queues make this concrete:
- **Atomic claim** (`BEGIN IMMEDIATE … UPDATE … WHERE status='ready'`) so one
  task goes to exactly one worker.
- **Leases + heartbeats**: a worker that dies mid-task leaves the job `running`;
  on boot, **orphan recovery** re-queues it (or fails it if attempts are
  exhausted). No silent loss.
- **Retry with exponential backoff + jitter** (base×2ⁿ capped, jittered),
  then terminal failure → **dead-letter queue** kept for inspection/retry.
- **Hard timeouts that end in real `SIGKILL`** (per-job process isolation) —
  a cooperative `AbortController` a busy loop can ignore isn't a timeout.
- **Idempotency keys** to dedupe re-delivered events/actions.

---

## 5. Five architectural dimensions (the design space)

1. **Context & memory persistence** — how state survives context-window resets
   (best: file-backed state + structured memory banks).
2. **Task decomposition & delegation** — dynamic DAG of subtasks; sub-agents
   execute leaves as dependencies resolve; coordinator never grows fat.
3. **Failure recovery & self-healing** — the three tiers above + watchdog +
   crash-resume.
4. **Tool orchestration & permissions** — capability scoping per agent
   (least authority), budgets, approval queues. *"Separate the interface a model
   can request from the authority a runtime can exercise."* (Agent libOS)
5. **Human–agent alignment over time** — an explicit alignment record that
   accumulates corrections and preferences; periodic REFLECT flags drift.

---

## 6. Proposed Sopno design

### 6.1 Reuse
| Asset | Role |
|-------|------|
| `sopno/core/reminders.py` | `ReminderPoller` daemon + SQLite store — the template for an agent scheduler |
| `sopno/core/rules.py` | `RulePoller` allowlist conditions — the template for event triggers |
| `sopno/memory/store.py` | Long-term facts/decisions/lessons store for the **alignment record** |
| `sopno/tools/builtins/automation/subagents.py` | Existing researcher/coder/reviewer runners — extend, don't fork |
| `sopno/core/assistant.py` | The tool-calling loop to drive each agent turn |
| `sopno/config/settings.py` + `config.json` | Config keys (offline-first, per-repo convention) |
| daemon service | systemd user service already hosts Sopno 24/7 |

### 6.2 New module: `sopno/core/agents/` (package)
- `session.py` — `AgentSession`: durable state machine per agent
  (SQLite; schema: `id, name, goal, state, status, plan, working_memory,
  alignment, budget_used, created_at, updated_at`).
- `queue.py` — `AgentQueue`: SQLite job queue with atomic claim, leases,
  heartbeats, retries+backoff, dead-letter, idempotency keys.
- `scheduler.py` — `AgentScheduler`: cron / interval / ETA triggers (reuses the
  reminder/rules pattern), wakes sessions on their events.
- `events.py` — event sources: file-system watcher (inotify), HTTP/webhook
  listener, schedule tick, manual message. Event → `state_delta` applied
  atomically before resume.
- `worker.py` — `AgentWorker`: daemon thread that claims ready sessions, runs
  `ORIENT→DECIDE→ACT→OBSERVE→REFLECT`, checkpoints after every ACT, and parks
  sessions that are waiting on humans or events.
- `runtime.py` — `AgentRuntime`: lifecycle (start/stop/pause/resume/kill),
  per-agent **capability profile** (allowed tools), budgets, watchdog,
  orphan recovery on boot.

### 6.3 The agent lifecycle
```
created → ready → running → waiting_human ─┐
             ↑        │                    │ (approval/reply event)
             └────────┴─ resumed by scheduler/event ─┐
             → running → done | blocked | dead       ←─┘
```
- `waiting_human` sessions **don't poll** — they sleep in the DB; a human reply,
  webhook, file event, or schedule resumes them (event-driven dormancy).
- Every transition is a row write (checkpoint); the action log is append-only.

### 6.4 Tools exposed to the user (and to sub-agents)
- `agent_create(name, goal, schedule?, tools?, budget?)` — define an agent.
- `agent_list()` / `agent_status(name)` — queue, state, progress, last actions.
- `agent_send(name, message)` — wake a waiting agent with input (human approval).
- `agent_pause(name)` / `agent_resume(name)` / `agent_kill(name)`.
- `agent_log(name)` — audit trail from the action log.

### 6.5 Safety & control (per-agent capability profile)
- Each agent gets an **allowlist of tools** (`tools: ["search_files",
  "read_file", …]`) — least authority. A news agent gets no terminal.
- **Budgets**: `max_turns`, `max_tokens`, `max_wall_minutes`, `max_actions/day`
  (rate limit) — enforced by the runtime, not the model.
- **Approval gates**: any action crossing a policy (write outside roots, send,
  push, install) parks in `waiting_human` and resumes on approval — exactly the
  existing pending-action pattern, but resumable.
- **Secrets**: never in agent state; env-var indirection only; blocklist applies.
- **Concurrency cap** (backpressure): default 2 active agents; excess wait in
  the queue.
- **Watchdog**: stale `running` sessions (no heartbeat) are reclaimed by orphan
  recovery on boot and periodically while running.

### 6.6 Alignment & memory
- Corrections/refusals are appended to the agent's **alignment record** and
  injected into ORIENT context (with a token budget).
- Durable lessons can promote into `memory/store.py` (project/agent scoped) so
  future sessions start smarter — but the alignment record is *agent-scoped*
  and auditable, and memory drift is governed like a microservice: who can read
  and write which banks.

---

## 7. Failure modes & mitigations

| Failure | Mitigation |
|---------|-----------|
| Process crash mid-task | Checkpoint after every ACT; orphan recovery on boot; action log for audit |
| Context loss across window resets | File-backed persistent state (task graph + working memory), not chat replay |
| Agent sleeps forever / missed wake | Event-driven triggers + scheduler; a stale `waiting` session alerts |
| Retry storm on a permanent error | Error taxonomy: retryable vs terminal; dead-letter after `max_attempts` |
| Agent loops or burns budget | Stagnation detector + hard turn/token/time budgets + rate limits |
| Tool misuse (scope creep) | Per-agent tool allowlist + approval gates + path bounds |
| Memory drift (over-applying a few atypical lessons) | Agent-scoped alignment record + explicit promotion to shared memory |
| Conflicting parallel agents | One-agent-per-task queue with atomic claim; idempotency keys |

---

## 8. Rollout plan (incremental, each step testable)

| Step | Deliverable | Verification |
|------|-------------|--------------|
| 1 | `AgentSession` SQLite store + state machine | Unit tests for transitions, persistence, crash-resume |
| 2 | `AgentQueue` (atomic claim, lease, retries+backoff, DLQ) | Unit tests incl. orphan recovery and idempotency |
| 3 | `AgentScheduler` + event sources (schedule, file event, message) | Tests: event wakes a parked session, applies `state_delta` |
| 4 | `AgentWorker` — one real agent (e.g. "news digest" using search + notes) | End-to-end: agent runs on schedule, writes artifact, parks on approval |
| 5 | Tools (`agent_create/list/status/send/pause/resume/kill/log`) + schemas + HUD tab | Tool tests; CLI + HUD flows |
| 6 | Capability profiles + budgets + watchdog (hardening) | Tests: budget exhaust → dead; watchdog reclaims stale runs |
| 7 | Hook `CodingAgent` (autonomous-coding.md) into a background agent session | A coding task survives a process restart and resumes from its last commit |

Each step keeps the suite green and follows repo conventions (`unittest`,
`settings.py` + `config.json` keys, `doc/CODEBASE.md` updates).

---

## 9. Sources
- clawRxiv 2604.01045 — *Persistent Agentic Harnesses / PAL* (five dimensions, four stores, three-tier recovery, results)
- Google Developers Blog — *Long-running agents with ADK* (state machines, SQLite sessions, webhook resume, `state_delta`)
- Addy Osmani — *Long-running Agents* (persistence/recovery/verification, Ralph loop, session-as-event-log, memory-layered context, memory drift)
- bunqueue / mcp-job-queue / pybgworker — SQLite durable job queues (atomic claim, leases, orphan recovery, retries+backoff+jitter, DLQ, SIGKILL timeouts)
- pyergon — durable execution for Python (suspend/resume on signals, cached steps, retry policies)
- agentask — task board as a state machine with atomic claiming and reviewer routing
- arXiv 2606.03895 — *Agent libOS* (agent as process: identity, capabilities, human queues, checkpoints, audit)
- arXiv 2607.00038 — *Stop Hand-Holding Your Coding Agent* (durable on-disk memory, named terminal states)
- Permafrost — background daemon threads, scheduler with ack tracking, watchdog, stall detection, L1–L6 memory
