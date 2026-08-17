# 🗺️ SOPNO Assistant — Implementation Roadmap & Status Tracker

This document tracks the incremental progress of transforming **Sopno (স্বপ্ন)** from a simple terminal script into a fully offline, background-running, Jarvis-like AI voice assistant.

---

## 📊 Status Summary
* **Current Phase:** Complete — all roadmap features implemented
* **Latest Completed Upgrade:** Long-running agents + autonomous coding fully rolled out (Steps 1–7) including budget/watchdog hardening and crash-resume
* **Housekeeping:** Builtin tools and tests reorganized into categorized subpackages (`df047e7`)
* **Test suite:** 620 tests, all passing

---

## 🛠️ Feature Checklist

### 1. Voice Output (Text-to-Speech) — **[COMPLETED]**
* [x] **High-quality Neural Voices:** Upgraded from standard robotic `gTTS` to **offline, high-fidelity Coqui TTS** (the open‑source continuation of Mozilla‑TTS).  
* [x] **Bilingual Language Routing:** Automatically selects the appropriate voice (Bengali or English) from the Coqui model.  
* [x] **Offline‑first:** No network required; fallback to Google `gTTS` remains optional for rare cases.
* [x] **HUD Sync:** Synchronized audio synthesis so both CLI and PyQt5 HUD GUI benefit automatically.

### 2. Wake Word Detection — **[COMPLETED]**
* [x] **Local Offline Activation:** Integrated `sherpa-onnx` Keyword Spotter with a pre-trained Gigaspeech Zipformer model to run lightweight, offline wake-word processing for custom keywords.
* [x] **Dynamic Config Integration:** Automatically loads custom wake words from `config.json`, tokenizes them dynamically using the model's vocabulary, and applies boosting scores at runtime.
* [x] **No Keys Required:** Completely free, open-source, and local, eliminating the need for Picovoice API access keys or cloud accounts.
* [x] **Smart Fallback:** Implemented a continuous, auto-calibrating SpeechRecognition/Google STT wake-word listener if `sherpa-onnx` model files are missing, ensuring 100% out-of-the-box operation.
* [x] **Wired into Main Loop:** Wake word detection is now integrated into `assistant.py` with configurable `listening_mode` ("wake_word" or "always_on"). HUD and CLI reflect the active mode.

### 3. Voice Input (Speech-to-Text) — **[COMPLETED]**
* [x] **Local Offline STT:** Migrated from online Google SpeechRecognition to fully offline, high-speed `faster-whisper`.
* [x] **Bilingual Language Recognition:** Natively detects and transcribes both English and Bangla offline with near-zero latency using the CTranslate2 model.
* [x] **Graceful Fallback:** Implemented automatic online Google STT fallback to handle any temporary CPU/Whisper-loading issues, ensuring 100% voice engine reliability.

### 4. Background Daemon (Always Running) — **[COMPLETED]**
* [x] **systemd User Service:** Enabled Sopno to run seamlessly as a background user daemon (`systemctl --user`).
* [x] **Autostart Configuration:** Autostart .desktop entry created; HUD launches on login.

### 5. OS Control & Tools — **[COMPLETED]**
* [x] **Core Functions:** Time/date, open apps, volume adjust, media controls, system stats, lock screen.
* [x] **CLI Sync:** Tool calling works on the terminal interface (`sopno.py`) as well as the GUI.

### 6. Long-Term Memory (SQLite) — **[COMPLETED]**
* [x] **SQLite Memory Store:** Persistent long-term memory in `sopno/memory/store.py` (schema, CRUD, FTS5 search) — survives restarts.
* [x] **"Remember" Commands:** "remember that X", "forget X", "what do you remember?" in English and Bangla.
* [x] **Context Injection:** Relevant memories injected into the LLM prompt with a token-budget guard.
* [x] **Semantic Recall:** `sqlite-vec` embeddings (local Ollama `nomic-embed-text`) for automatic meaning-based recall, merged with FTS5 keyword matches and degrading gracefully to keywords alone when the model is unavailable.
* Design spec: [modules/memory/memory.md](../modules/memory/memory.md)

### 7. Terminal Access (Persistent Shell) — **[COMPLETED]**
* [x] **Persistent Shell Session:** One shared `cleat` PTY shell per Sopno process; `cd`, `export`, and background jobs persist between calls.
* [x] **Structured Output + Real Exit Codes:** OSC 133 marks give Sopno clean stdout and genuine exit codes (no brittle prompt parsing).
* [x] **Interactive Support:** `terminal_send` types into REPLs, installers, and password prompts (`ctrl-c`/`ctrl-d`/`ctrl-z`); `terminal_status` polls long-runners without interfering.
* [x] **Safety Blocklist:** Destructive/irreversible patterns (`rm -rf /`, `mkfs`/`fdisk`, shutdown/reboot, fork bombs, raw disk writes, `curl|sh`) are blocked; fully configurable via `terminal_blocklist` in `config.json`.
* [x] **Graceful Shutdown:** The shared shell session closes when Sopno stops.

### 8. Process / Service / Log / Cron Management — **[COMPLETED]**
* [x] **Processes:** `list_processes` (top-by-CPU with keyword filter) and `kill_process` (by PID or name, with protected targets).
* [x] **Services:** `manage_service` — start/stop/restart/status/enable/disable/reload via `systemctl --user` (no sudo needed).
* [x] **Logs:** `read_logs` — user/system journal (optionally per unit) or a raw `tail` of an absolute log file path.
* [x] **Cron:** `manage_cron` — list / add / remove crontab jobs non-interactively; blocked or malformed commands are refused.
* [x] **Safety:** everything executes through the shared terminal session, so the `terminal_blocklist` and Sopno's privileges apply uniformly.

### 9. File & Folder Access (Permission-Gated) — **[COMPLETED]**
* [x] **Read Tools:** `read_file` (whole file or head/tail lines, size + output capped) and `list_directory` (sorted entries with type + size).
* [x] **Write Tools:** `write_file` (create/overwrite), `edit_file` (exact-string replace with a read-before-edit invariant), `delete_file` (single files only), `rename_file` (never overwrites).
* [x] **Allowlist Roots, Deny-by-Default:** reads allowed only inside `file_allowed_read` and writes only inside `file_allowed_write` (default: the project root) — everything else is refused.
* [x] **Secret Deny-List:** `.env`, `.git`, `.ssh`, `*.pem`/`*.key`, `credentials.json`, Sopno's own `config.json` and `memory.db` are off-limits even inside the roots.
* [x] **Symlink-Safe Paths:** every path is `resolve()`d before checking, so `..`/symlinks can't escape the roots.
* [x] **HUD/CLI Confirmation:** every write/edit/delete/rename/copy parks a pending action and asks the user Yes/No (spoken in voice mode, typed in text mode); `file_confirm_writes` can disable the prompt.
* [x] **Search:** `search_files` — by file name (`mode="name"`, fnmatch glob/substring) or file contents (`mode="content"`, regex → `path:line` hits); skips blocked paths and binaries; capped by `file_search_max_results`.
* [x] **Copy / Move:** `copy_file` (files *and* folders; refuses overwrite unless `overwrite=true`) and `move_file` (alias of `rename_file`) — both confirmed.
* [x] **Binary Document Readers:** `read_file` auto-detects PDFs (PyMuPDF text + OCR fallback for scans), images (Tesseract OCR), `.docx/.pptx/.xlsx` (python-docx/python-pptx/openpyxl), and legacy `.doc/.xls/.ppt` (LibreOffice headless). All optional/graceful; capped by `readers_max_pages`/`readers_max_chars`; OCR gated by `file_ocr_enabled`.

### 10. Git Tools — **[COMPLETED]**
* [x] **Read-Only Tools:** `git_status` (branch + working-tree + recent history), `git_log` (one-line history, clamped), `git_diff` (unstaged or staged, capped), `git_commit_message` (LLM-drafts a conventional message from the diff — read-only).
* [x] **Branch Tools:** `git_branch` list / create / switch / delete (delete confirmed, `branch -d` only — never force).
* [x] **Mutating Tools (Confirmed):** `git_add` (stage files), `git_commit` (optional `add_all`), `git_stash` push/pop — all park a pending action and ask the user Yes/No.
* [x] **Safe by Construction:** every command runs through the persistent terminal session (`git -C <repo> -c color.ui=false …`), so the terminal blocklist applies; interpolated values are shlex-quoted and checked against shell metacharacters; repo/branch/path names are validated; `git_enabled` master switch in `config.json`.

### 11. Scheduler & Reminders — **[COMPLETED]**
* [x] **Natural-Language Times:** `parse_when` understands "now", "in 10 minutes", "2h", "9:30pm" (rolls to tomorrow if already past), "today/tonight/tomorrow at 9am", "tomorrow", and `YYYY-MM-DD[ at] HH:MM` — deterministic, with friendly errors.
* [x] **Tools:** `set_reminder(when, text)` (non-destructive — no confirmation), `list_reminders()`, `cancel_reminder(id)`.
* [x] **Persistent Store:** own SQLite DB (`sopno/memory/reminders.db`, WAL, gitignored) with `pending → delivered | cancelled`; survives restarts.
* [x] **Background Poller:** daemon thread in `SopnoAssistant.run()` delivers due reminders into the reply flow every `reminders_poll_seconds` (30s); delivery is atomic (at-least-once, fires exactly once) and serialized with speech via a lock so a reminder never cuts off a reply.
* [x] **Safety Caps:** `reminders_max` pending (50), `reminders_max_horizon_days` (365); `reminders_enabled` master switch.

### 12. Browser Automation (Playwright) — **[COMPLETED]**
* [x] **Opt-In Master Switch:** `browser_enabled` defaults to `false` (Playwright + Chromium are heavy); when off — or Playwright isn't installed — the tools answer with a friendly message instead of failing.
* [x] **Navigation + Text Snapshot:** `browser_navigate(url)` opens a page (https assumed) and returns a cheap text snapshot — title, body text, and `[0] …`-indexed interactive elements — instead of vision/screenshots.
* [x] **Interaction:** `browser_click(selector, index)` (CSS selector or snapshot index), `browser_type(selector, text)` (defaults to first visible input), `browser_extract(selector)`, `browser_back()` — all returning fresh snapshots/text.
* [x] **Screenshots:** `browser_screenshot(path, full_page)` writes PNGs only inside the file write-roots (`files._authorize`) and asks Yes/No when overwriting.
* [x] **Security:** `browser_allowed_domains` deny-by-default allowlist; per-step `browser_timeout` (30s); whole-session `browser_task_limit` (120s) ceiling; `image/media/font` requests blocked; page content treated as untrusted. `browser_close()` frees the session.
* [x] **Tested without Playwright:** all 17 tests use a fake `BrowserSession`, so the logic is fully covered without the heavy dependency.

### 13. MCP Support + Plugin System — **[COMPLETED]**
* [x] **Dynamic Tool Framework:** `registry.register_tool/unregister_tool` + `schema.register_schema/unregister_schema` let plugins and MCP clients extend the toolset at runtime; the LLM prompt reads `get_schema()` (base + dynamic) every turn.
* [x] **Plugins:** `sopno/tools/plugins.py` discovers `plugins/<name>/plugin.py`, registers each tool as `<plugin>_<tool>` with its schema, and calls `on_load()`/`on_unload()`. Tools opting into confirmation go through the pending-action Yes/No gate; plugins get no implicit powers (default-deny — file roots, terminal blocklist, confirmations still apply).
* [x] **MCP Client:** `McpHub` connects to every `mcp_servers` entry (MCP SDK v2, stdio, own daemon event-loop thread), lists tools, and registers them as `<server>_<tool>` — callable by the LLM like built-ins. `refresh()`/`close()` manage the lifecycle.
* [x] **MCP Server:** `sopno/tools/mcp_server.py` wraps the whole registry as an `MCPServer` — `python -m sopno.tools.mcp_server` lets any MCP host (Claude Desktop, Cursor, opencode) drive Sopno's tools, with Sopno's permission gates intact.
* [x] **Self-Tested Both Directions:** an in-process MCP server subprocess is driven end-to-end by the client, and Sopno's own client drives its own server (`sopno_get_current_time` worked over the wire).
* [x] **Config:** `mcp_enabled` / `mcp_servers` / `plugins_enabled` / `plugins_dir`.

### 14. Desktop Control + Hardware — **[COMPLETED]**
* [x] **Clipboard:** `clipboard_get` / `clipboard_set` via `xclip`/`xsel`; setting text is confirmed.
* [x] **Screenshot:** `take_screenshot(path, region)` via `scrot`/`maim`; writes only inside the file write-roots (overwrite confirmed), `X,Y,W,H` region support.
* [x] **Windows:** `list_windows` / `focus_window(title)` via `wmctrl`.
* [x] **Keyboard:** `send_keys(text)` / `press_key(combo)` via `xdotool`; both confirmed, and key combos with shell metacharacters are rejected outright.
* [x] **Hardware reads (read-only, no X needed):** `get_disk_stats` (partitions + temps + fans), `get_gpu_stats` (pynvml — graceful "no NVIDIA GPU" note), `get_network_stats` (per-interface RX/TX).
* [x] **Extended `get_system_stats`** to include disk and CPU temperature when psutil can read them.
* [x] **X11-first + honest degradation:** every dependency is optional and detected at runtime (friendly "install X" messages); with `desktop_require_x11` true, input/window/clipboard tools refuse on Wayland instead of silently misbehaving. `open_application` honours `desktop_allowed_apps`.
* [x] **Config:** `desktop_enabled` / `desktop_allowed_apps` / `desktop_require_x11`.

### 15. Database, Packages & Networking — **[COMPLETED]**
* [x] **Database (SQLite, read-only first):** `query_database(path, sql)` — SELECT/PRAGMA/EXPLAIN run immediately on a `mode=ro` connection; any mutating statement parks a Yes/No gate and runs on a read-write connection. Queries respect the file read-roots + blocked-paths list, rows capped at 30, long cells truncated.
* [x] **`explain_schema(path)`** — tables, columns, and row counts; **`backup_database(path, destination)`** — live consistent copy via the SQLite backup API (write-root gated, overwrite confirmed, default `<name>.backup.db`).
* [x] **Packages:** `install_package(name, manager)` — apt/pacman/dnf/pip/flatpak (+ `auto` detection from os-release), always confirmed, runs through the shared terminal (blocklist applies), `sudo -n` for system managers (never hangs on a password prompt). `uninstall_package` is **blocked by default** (`packages_uninstall_allowed`) and confirmed when enabled. Package names are strictly validated (no shell metacharacters, no `..`).
* [x] **Networking (read-only by default):** `ping_host` (`ping -c 4`), `traceroute` (missing-binary note if absent), `wifi_scan` (nmcli), `public_ip` (**opt-in** via `network_public_ip_enabled`), `firewall_status()` (`ufw status verbose`). The only mutating tool is `firewall_status("on"/"off")` — confirmed, `sudo -n`.
* [x] **Config:** `database_enabled` / `packages_enabled` / `packages_uninstall_allowed` / `packages_require_sudo` / `network_enabled` / `network_public_ip_enabled`.

### 16. Vision, Email, Calendar & Notes — **[COMPLETED]**
* [x] **Vision:** `describe_screenshot(path)` — feeds a base64 image to a local Ollama vision model (`vision_model`, opt-in via `vision_enabled`; images must be in the read roots, ≤ 8 MB). `ocr_image(path)` — Tesseract via pytesseract with a `tesseract` CLI fallback; friendly message when missing.
* [x] **Email:** `email_read(limit, mailbox)` — read-only IMAP (subject/from/snippet); `email_send(to, subject, body)` — SMTP+STARTTLS, **confirmed**. Opt-in only (`email_enabled`); passwords come from the env var named by `email_password_env`, never config.json. Recipient/subject/body validated.
* [x] **Calendar:** `calendar_list(limit)` — parses `.ics` files under `calendar_dir` (no external service) and lists upcoming events; `calendar_create_event(...)` — appends a VEVENT to `calendar.ics` (write-root gated, confirmed, values escaped).
* [x] **Notes / knowledge base:** `note_write(title, content)` — markdown under `notes_dir` (confirmed, overwrite confirmed); `note_list()` and `note_search(query)` — read-only grep.
* [x] **Config:** `vision_enabled` / `vision_model` / `email_*` / `calendar_dir` / `notes_dir`.

### 17. Automation Rules, Subagents & GUI Dashboard — **[COMPLETED]**
* [x] **Automation rules:** `rule_add(name, condition, action)` — "if X then Y" persisted in SQLite (`rules.db`, WAL, gitignored). Conditions are an allowlist of numeric metrics (`battery_percent`, `cpu_percent`, `ram_percent`, `disk_free_gb`, `hour_of_day`, `day_of_week`) compared with `< <= > >= ==` — **never eval-ed**. Actions are existing registered tools (e.g. `open_application app="Files"`). A background `RulePoller` thread checks every `rules_poll_seconds` and fires each rule **once per true-period** (no spamming while the condition stays true). The rule is confirmed once at creation; on fire, any pending-action gate the action raises is auto-approved.
* [x] **Rule tools:** `rule_list()` read-only, `rule_remove(id)` confirmed, `rule_set_enabled(id, enabled)` (disabling confirmed). All gated behind the shared `rules_enabled` master switch.
* [x] **Multi-agent:** `run_subagent(agent, task)` — researcher / coder / reviewer subagents, each with a focused system prompt and a **restricted tool schema** (researcher: search/fetch/read; coder: files/git/terminal; reviewer: read-only files/git/logs). They run the same Ollama tool-calling loop as the main assistant but return plain text. `subagent_list()` lists them; `subagents_enabled` + `subagents_max_turns` bound them.
* [x] **GUI dashboard:** `≡` button in the HUD chrome toggles a read-only `DashboardPanel` (5 tabs) backed by the same live objects the CLI uses — **Settings** (config.json + runtime settings, secrets masked), **Memory** (MemoryStore stats + important memories), **Tools** (all 79 registered tools), **Logs** (live stream from the assistant), **Models** (Ollama list). Nothing editable in the panel.
* [x] **Config:** `rules_enabled` / `rules_path` / `rules_poll_seconds` / `subagents_enabled` / `subagents_max_turns`.

---

## 📓 Technical Progress Log

### [August 18, 2026] — Step 27: Budget/Watchdog Hardening + Crash-Resume (closes Step 6)
* **Modified Files:** `tests/core/test_agent_worker.py`, `tests/core/test_coding.py`, `tests/core/test_agent_runtime.py`, `sopno/core/agents/runtime.py`
* **Impact:** Closes rollout step 6 of both `long-running-agents.md` and `autonomous-coding.md`. **Worker budget tests:** `WallClockBudgetTest` (wall-clock budget exhausts session to `dead`), `DailyBudgetTest` (actions-per-day budget exhausts session to `dead`). **Capability profile test:** `CapabilityTest.test_tool_not_in_allowlist_is_refused` — explicit per-agent tool allowlist enforcement. **Watchdog tests:** `WatchdogTest` — 3 tests verifying the watchdog thread starts, reclaims stale running sessions on its interval, and the full runtime start/stop lifecycle. **Crash-resume test:** `test_crash_resume_picks_up_from_last_checkpoint` — mid-run LLM failure, resume from last checkpoint commit, both pre-crash and post-crash files survive. **Runtime cleanup:** `stop()` now joins the watchdog thread instead of dropping the reference. 7 new tests → suite at 620.

### [August 17, 2026] — Step 26: Coding Approval Modes + Escalation + Auto-Merge + Event Sources/REFLECT
* **Added Files:** `sopno/tools/builtins/automation/coding.py`, `sopno/core/agents/sources.py`, `tests/core/test_agent_sources.py`
* **Modified Files:** `sopno/core/coding/agent.py`, `sopno/core/coding/tools.py`, `sopno/core/coding/worktree.py`, `sopno/core/coding/prompts.py`, `sopno/core/coding/__init__.py`, `sopno/core/agents/worker.py`, `sopno/core/agents/runtime.py`, `sopno/core/agents/events.py`, `sopno/tools/builtins/automation/agents.py`, `sopno/tools/builtins/automation/__init__.py`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/config/settings.py`, `config.json`, `sopno/ui/hud/dashboard.py`, `tests/core/test_coding.py`, `tests/core/test_agent_tools.py`, `tests/core/test_agent_worker.py`, `tests/core/test_agent_runtime.py`, `tests/integration/test_mcp.py`, `doc/CODEBASE.md`, `doc/roadmap/autonomous-coding.md`, `doc/roadmap/long-running-agents.md`, `doc/roadmap/status.md`
* **Impact:** Closes rollout steps 4/5/7 of `autonomous-coding.md` and adds the event sources + REFLECT from `long-running-agents.md`. **Escalation & approval modes:** `CodingAgent` gains three local tools (`delegate` — sub-agent digest via `run_subagent`; `escalate` — pauses the run in `review_required`, otherwise records into `escalations` and continues; `run_review` — self-review step) and honors `coding_approval_mode` (`auto_merge_guardrailed`/`unattended`/`review_required`). **Red-test baseline:** when `coding_require_red_test` is on, setup runs the verify recipe on `main`; a green baseline appends a RED-FIRST advisory (not a hard block) and `baseline_green` lands in the result. **Guardrailed auto-merge:** `_auto_merge` runs only in `auto_merge_guardrailed` — branch verified green → `git merge --no-ff` into main → merged tree re-verified → hard-reset rollback on red or failed push (`WorktreeSession.merge_back`/`abort_merge`/`push`); optional push behind `coding_push_enabled`. **Batch mode:** `run_coding_batch(tickets)` runs a fresh `CodingAgent` per ticket. **Tools:** `coding_run` (single goal or `tickets` batch — creates a `kind='coding'` session + queued `run` job with idempotency key) and `coding_status` (branch/state parsed from the durable `[coding-worktree]` memory marker) plus `agent_align(name, correction)` — all in registry + schema + worker management tools. **Event sources (`sources.py`):** poll-based `FileWatcher` (dirs under `agents_file_watches`, first scan is a baseline, mtime/size debounce) and HTTP `WebhookServer` (`POST /webhook {agent, message, state_delta}`, `GET /health`, `agents_webhook_port`) both produce the same durable wake (pending input + `resume` job) as a human reply; runtime starts/stops them with the daemon. **REFLECT:** workers run a periodic reflection for general agents (`reflect_fn` default `default_reflect` via `llm_chat`), promoting bullet notes into the session's alignment record; failure is silent. **HUD:** the dashboard panel is now six tabs incl. an "Agents" tab (lazy-imported status list + coding branch). New config: `agents_file_watches`, `agents_file_poll_seconds` (10), `agents_webhook_host`, `agents_webhook_port` (0). Fixed a pre-existing time/date-dependent `test_mcp` assertion. 26 new tests → suite at 613.

### [August 16, 2026] — Step 25: AgentWorker + AgentRuntime + Agent Tools + Coding Resume
* **Added Files:** `sopno/core/agents/worker.py`, `sopno/core/agents/runtime.py`, `sopno/tools/builtins/automation/agents.py`, `tests/core/test_agent_worker.py`, `tests/core/test_agent_runtime.py`, `tests/core/test_agent_tools.py`
* **Modified Files:** `sopno/core/agents/session.py`, `sopno/core/agents/scheduler.py`, `sopno/core/agents/__init__.py`, `sopno/core/coding/worktree.py`, `sopno/core/coding/agent.py`, `sopno/core/assistant.py`, `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/tools/builtins/automation/__init__.py`, `tests/core/test_agents.py`, `tests/core/test_agent_scheduler.py`, `tests/core/test_coding.py`, `doc/CODEBASE.md`, `doc/roadmap/implementation-plan.md`, `doc/roadmap/long-running-agents.md`, `doc/roadmap/status.md`
* **Impact:** Rollout steps 4–7 of `long-running-agents.md`. **`AgentWorker`** (daemon thread) claims `run`/`resume` jobs from the queue and drives a bounded ORIENT → DECIDE → ACT → OBSERVE loop: a per-agent lock keeps one session to one driver; each step heartbeats the session and renews the job lease; tool calls execute against the agent's allowlist (management tools excluded from the default); an approval gate parks the session in `waiting_human` with the pending action checkpointed; queued human input is drained on resume (a parked approval is answered Yes/No); budgets (`max_turns` / `max_wall_minutes` / `max_actions_per_day`) end in `dead`; the per-job turn budget hands a session back to `ready` (event-driven dormancy). A `kind='coding'` bridge routes sessions into `run_coding_task` (worktree harness). **`AgentRuntime`** is the lifecycle owner: boots `agents_concurrency` workers + the scheduler + a watchdog, recovers orphan jobs and reclaims stale `running` sessions (no live job + heartbeat older than the lease) on start; `SopnoAssistant` wires it in behind `agents_enabled`. The **agent tools** (`agent_create`/`agent_list`/`agent_status`/`agent_send`/`agent_pause`/`agent_resume`/`agent_kill`/`agent_log`) — schema + registry, validation, least-authority allowlists and budgets, `agent_send` as the approval channel, `agent_kill` behind the confirmation gate. **Coding resume (step 7):** `CodingAgent` persists a `[coding-worktree]` record in the session's working memory and reattaches to the same branch via `WorktreeSession.attach` on later runs; `_finish_session` maps `success/no_op → done`, `blocked/stalled → blocked`, `exhausted → dead`. Sessions gained `kind` + `pending_action` columns (no-op migrations). New config: `agents_worker_poll_seconds` (2), `agents_job_max_turns` (20), `agents_watchdog_seconds` (300). 34 new tests → suite at 587.

### [August 16, 2026] — Step 24: AgentScheduler + Event Sources
* **Added Files:** `sopno/core/agents/scheduler.py`, `sopno/core/agents/events.py`, `tests/core/test_agent_scheduler.py`
* **Modified Files:** `sopno/core/agents/session.py`, `sopno/core/agents/__init__.py`, `sopno/config/settings.py`, `config.json`, `doc/CODEBASE.md`, `doc/roadmap/implementation-plan.md`, `doc/roadmap/long-running-agents.md`, `doc/roadmap/status.md`
* **Impact:** Rollout step 3 of `long-running-agents.md`. **`AgentScheduler`** (daemon thread, polled) parses session triggers — `interval:<seconds>`, `cron:<5 fields>` (a self-contained stdlib-only parser with `*`/`*/n`/`a-b`/`a,b,c` and 3-letter month/day names, and dom/dow OR semantics), and one-shot `eta:<ISO>` — computes the next fire with `next_fire_at`, and on the tick enqueues a `run` job for every due trigger. The fire is a unit of work: an idempotency key tied to the fire timestamp dedupes a crash between enqueue and bookkeeping, and each cadence produces exactly one job. Sessions gained a `last_fired_at` column (with a no-op migration for existing DBs). **`AgentEvents`** is the wake channel: a message + optional `state_delta` (applied atomically by the store's new `apply_state_delta`) become pending input + a `resume` job — the event-driven dormancy path for `waiting_human`/parked sessions, with an append-only audit entry. New config: `agents_poll_seconds` (30). 26 new tests → suite at 553.

### [August 16, 2026] — Step 23: Long-Running Agents + Autonomous Coding
* **Added Files:** `sopno/core/agents/session.py`, `sopno/core/agents/queue.py`, `sopno/core/agents/__init__.py`, `sopno/core/coding/` (package: `agent.py`, `tools.py`, `worktree.py`, `verify.py`, `prompts.py`, `util.py`, `__init__.py`), `tests/core/test_agents.py`, `tests/core/test_coding.py`, `doc/roadmap/long-running-agents.md`, `doc/roadmap/autonomous-coding.md`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `.gitignore`, `doc/CODEBASE.md`, `doc/roadmap/implementation-plan.md`, `doc/roadmap/status.md`
* **Impact:** Two new phases from the roadmap. **Long-running agents** (`sopno/core/agents/`) — a durable session store (`AgentSessionStore`, status machine `ready → running → done | failed | cancelled | waiting_human`, heartbeat, append-only action log, plan/memory alignment budget) plus an `AgentQueue` backed by SQLite (`BEGIN IMMEDIATE` atomic claim, expiring leases with heartbeat renewal, exponential backoff + jitter, orphan recovery, idempotency dedupe, dead-letter after max attempts). **Autonomous coding** (`sopno/core/coding/`) — a self-contained `CodingAgent` that runs a goal loop in a git worktree (`sopno/memory/worktrees/` on branch `sopno/<slug>-<ts>`): plan → recite → act (gated writes through a `ToolDispatcher` that reuses `files._authorize`, never the interactive Yes/No), verify after every change (recipe resolution + checkpoint commits), harness-owned `PLAN.md`/`progress.md`/`SUMMARY.md` protected from the agent, and terminal states `success | no_op | blocked | stalled | exhausted` where "an error is never recorded as a win". Turn/token/wall-clock/diff-line budgets + stall detection bound it. Per the project rule "one folder = one job", the original ~844-line `sopno/core/coding.py` was refactored into the single-purpose `coding/` package (`agent`/`tools`/`worktree`/`verify`/`prompts`/`util`) so `core/` stays tidy. New config: `agents_*` (enabled/path/max_sessions/concurrency/lease/backoff/max_attempts) and `coding_*` (enabled/worktree_dir/max_turns/max_tokens/max_wall_minutes/max_diff_lines/stall_rounds/approval_mode/protected_paths/require_red_test/push_enabled). 38 new tests → suite at 527.

### [August 16, 2026] — Step 22: Automation Rules, Subagents & GUI Dashboard
* **Added Files:** `sopno/core/rules.py`, `sopno/core/subagents.py`, `sopno/tools/builtins/rules.py`, `sopno/tools/builtins/subagents.py`, `sopno/ui/hud/dashboard.py`, `tests/test_rules.py`, `tests/test_subagents.py`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/core/assistant.py`, `sopno/ui/hud/window.py`, `doc/CODEBASE.md`, `doc/roadmap/implementation-plan.md`
* **Impact:** Three systems close out the plan. **Automation rules** (`sopno/core/rules.py`) — "if `battery_percent < 20` then `open_application app="Files"`"-style rules in SQLite with an allowlist condition grammar (never `eval`), a `RulePoller` daemon that fires each rule once per true-period and auto-approves pending-action gates the action raises (the rule itself was the one-time confirmation), plus `rule_add`/`rule_list`/`rule_remove`/`rule_set_enabled` tools. **Multi-agent** (`sopno/core/subagents.py`) — researcher / coder / reviewer subagents with focused prompts and restricted tool schemas, running the same Ollama tool-calling loop as the main assistant and returning plain text (`run_subagent` + `subagent_list` tools). **GUI dashboard** (`sopno/ui/hud/dashboard.py`) — a read-only 5-tab panel (Settings / Memory / Tools / Logs / Models) toggled by a `≡` chrome button, reading the same settings, config.json (secrets masked), MemoryStore, registry, and Ollama list the CLI uses; logs stream live from the assistant's `log_message` signal. 6 new tools (73 → 79), 27 new tests → suite at 489.

### [August 16, 2026] — Step 21: Vision, Email, Calendar & Notes
* **Added Files:** `sopno/tools/builtins/vision.py`, `sopno/tools/builtins/email.py`, `sopno/tools/builtins/calendar.py`, `sopno/tools/builtins/notes.py`, `tests/test_vision.py`, `tests/test_email.py`, `tests/test_calendar.py`, `tests/test_notes.py`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/tools/builtins/__init__.py`, `sopno/core/assistant.py`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Four new skills (9 tools). **vision.py** — `describe_screenshot` posts a base64 image to Ollama's `/api/chat` with the configured `vision_model` (opt-in), and `ocr_image` extracts text via pytesseract with a `tesseract` CLI fallback. **email.py** — read-only IMAP (`email_read`) and confirmed SMTP+STARTTLS `email_send`; the whole feature is opt-in (`email_enabled` false by default), and the password is read from an environment variable (`email_password_env`, default `SOPNO_EMAIL_PASSWORD`) so secrets never touch config.json. **calendar.py** — a dependency-free `.ics` parser under `calendar_dir` (`calendar_list`) plus a confirmed `calendar_create_event` that appends a properly-escaped VEVENT to `calendar.ics`. **notes.py** — markdown knowledge base under `notes_dir` (`note_write` confirmed + overwrite confirmed, `note_list`, `note_search`). 35 new tests → suite at 462.

### [August 16, 2026] — Step 20: Database, Packages & Networking
* **Added Files:** `sopno/tools/builtins/databases.py`, `sopno/tools/builtins/packages.py`, `sopno/tools/builtins/network.py`, `tests/test_databases.py`, `tests/test_packages.py`, `tests/test_network.py`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/tools/builtins/__init__.py`, `sopno/core/assistant.py`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Three new skills (10 tools). **databases.py** gives read-only SQLite access: `query_database` runs reads on a `mode=ro` connection and gates any mutating statement behind Yes/No (then executes on a read-write connection); `explain_schema` lists tables/columns/row counts; `backup_database` uses the SQLite backup API (write-root gated, overwrite confirmed). All queries honour the file read-roots + blocked-paths. **packages.py** — `install_package` (apt/pacman/dnf/pip/flatpak, `auto` detection, confirmed, `sudo -n` for system managers) and `uninstall_package` (blocked by default, confirmed when enabled); names strictly validated. **network.py** — read-only `ping_host`, `traceroute`, `wifi_scan`, `firewall_status()`, opt-in `public_ip`; only `firewall_status("on"/"off")` mutates (confirmed, `sudo -n`). Everything routes through the shared terminal so the safety blocklist still applies. 38 new tests → suite at 427.

### [August 16, 2026] — Step 19: Desktop Control + Hardware
* **Added Files:** `sopno/tools/builtins/desktop.py`, `tests/test_desktop.py`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/tools/builtins/system.py`, `sopno/tools/builtins/__init__.py`, `sopno/core/assistant.py`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** New `desktop.py` skill adds 10 tools: clipboard get/set (`xclip`/`xsel`), `take_screenshot` (`scrot`/`maim`, write-root gated + overwrite confirmed, `X,Y,W,H` regions), `list_windows`/`focus_window` (`wmctrl`), `send_keys`/`press_key` (`xdotool`, both confirmed; unsafe combos rejected), and three read-only hardware reads — `get_disk_stats`, `get_gpu_stats` (pynvml, graceful no-GPU note), `get_network_stats`. `get_system_stats` now also reports disk and CPU temperature. Design is X11-first with honest degradation: all dependencies optional (runtime `which` detection → friendly install messages), and with `desktop_require_x11` true the input/window/clipboard tools refuse on Wayland rather than silently misbehaving. `open_application` gained the `desktop_allowed_apps` allowlist. 35 new tests (fake `_run`/`_have`, confirm-gate flows, Wayland gate, fake pynvml module) → suite at 389.

### [August 16, 2026] — Step 18: MCP Support + Plugin System
* **Added Files:** `sopno/tools/plugins.py`, `sopno/tools/mcp_client.py`, `sopno/tools/mcp_server.py`, `tests/test_plugins.py`, `tests/test_mcp.py`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/tools/__init__.py`, `sopno/core/assistant.py`, `requirements.txt`, `doc/CODEBASE.md`
* **Impact:** Sopno's toolset is no longer closed. The registry + schema gained `register/unregister` for dynamic tools, and the LLM prompt reads `get_schema()` every turn, so anything added at startup is immediately callable. **Plugins** are folders under `plugins/` exposing a `plugin_tools()` contract; each tool is namespaced `<plugin>_<tool>`, can opt into the pending-action Yes/No gate, and inherits the default-deny posture (no bypass of file roots / terminal blocklist / confirmations). **MCP** works both ways: as a client, `McpHub` connects to every `mcp_servers` entry over stdio (MCP SDK v2, its own daemon event-loop thread) and registers each remote tool as `<server>_<tool>`; as a server, `python -m sopno.tools.mcp_server` exposes the full registry to any MCP host. Both directions are covered by real stdio tests, including Sopno's client driving Sopno's own server (`sopno_get_current_time` over the wire). 16 new tests → suite at 354.

### [August 16, 2026] — Step 17: Browser Automation (Playwright)
* **Added Files:** `sopno/tools/builtins/browser.py`, `tests/test_browser.py`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/tools/builtins/__init__.py`, `sopno/core/assistant.py`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now browse the web. A lazy singleton `BrowserSession` wraps Playwright Chromium (installed on demand via `browser_enabled: true` + `pip install playwright` + `playwright install chromium`); the LLM drives it through 7 discrete tools. `browser_navigate` returns a *text snapshot* (title, body, `[0]…`-indexed interactive elements) so no vision is needed; `browser_click`/`browser_type` target elements by snapshot index or CSS selector; `browser_extract` reads regions; `browser_screenshot` writes PNGs inside the file write-roots (overwrite confirmed); `browser_back`/`browser_close` round it out. Security is deny-by-default: `browser_allowed_domains`, per-step `browser_timeout`, a `browser_task_limit` session ceiling, blocked image/media/font resources, and untrusted-page discipline. Off (or missing Playwright) the tools degrade to a friendly message. 7 new tools (44 total), 17 new tests (fake session, no Playwright needed) → suite at 338.

### [August 16, 2026] — Step 16: Scheduler & Reminders
* **Added Files:** `sopno/core/reminders.py`, `sopno/tools/builtins/reminders.py`, `tests/test_reminders.py`
* **Modified Files:** `sopno/config/settings.py`, `config.json`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/tools/builtins/__init__.py`, `sopno/core/assistant.py`, `tests/test_tools.py`, `.gitignore`, `doc/CODEBASE.md`
* **Impact:** Sopno can now plan ahead. "Remind me in 10 minutes to drink water" — `parse_when` turns the natural-language time into an absolute timestamp (rolled to tomorrow when a wall-clock time has already passed), `set_reminder` stores it in its own SQLite DB (`reminders.db`, WAL, gitignored) with no confirmation needed (non-destructive), and a daemon `ReminderPoller` thread inside `SopnoAssistant.run()` delivers anything due into the reply flow every `reminders_poll_seconds`. Delivery is atomic — each reminder fires exactly once (marked `delivered` in the same transaction), and the speech lock guarantees a fired reminder never overlaps a spoken reply. `list_reminders`/`cancel_reminder` manage pending items; caps (`reminders_max` = 50 pending, `reminders_max_horizon_days` = 365) and the `reminders_enabled` master switch keep it bounded. 3 new tools (37 total), 30 new tests → suite at 321.

### [August 16, 2026] — Step 15: File Access Round 2 (Search, Copy, Binary Readers)
* **Added Files:** `sopno/tools/builtins/readers.py`, `tests/test_readers.py`
* **Modified Files:** `sopno/tools/builtins/files.py`, `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/config/settings.py`, `config.json`, `sopno/core/assistant.py`, `tests/test_files.py`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now *find* and *handle* real-world documents, all still inside the permission roots. `search_files` finds files by name (globs/substrings) or greps contents (regex → `path:line`, capped at `file_search_max_results`, skipping blocked paths and binaries). `copy_file` duplicates files or whole folders (refuses overwrite unless asked) and `move_file` is a confirmed alias of `rename_file`. `read_file` now auto-detects PDFs, images, `.docx/.pptx/.xlsx`, and legacy Office files via a layered reader pipeline (`readers.py`): fast native extraction → OCR for scans/images (Tesseract) → LibreOffice for legacy formats — every dependency optional and best-effort, with page/output caps and a `[method]` label so Sopno knows how each document was read. 3 new tools (34 total), 41 new tests → suite at 291.

### [August 16, 2026] — Step 14: Semantic (Vector) Memory
* **Added Files:** `sopno/memory/semantic.py`, `tests/test_semantic.py`
* **Modified Files:** `sopno/memory/store.py`, `sopno/config/settings.py`, `config.json`, `tests/test_memory.py`, `doc/CODEBASE.md`
* **Impact:** Sopno's long-term memory now understands meaning, not just keywords. Each remembered fact also gets an embedding from the same local Ollama `nomic-embed-text` model the researcher uses, stored in a `sqlite-vec` `vec0` table inside `memory.db`. Recall merges FTS5 keyword hits (ranked first) with vector matches (cosine ≥ 0.4) that fill the remaining slots, so "what do you remember about the talk I have tomorrow" finds a memory about a "presentation". The vector layer is best-effort: if the model, the extension, or the dimensions are unavailable it silently falls back to the existing FTS5 path — memory never breaks. New config: `semantic_memory_enabled`, `semantic_recall_limit`. 14 new tests (deterministic fake embeddings) bring the suite to 250.

### [August 16, 2026] — Step 13: Git Tools
* **Added Files:** `sopno/tools/builtins/git.py`, `tests/test_git.py`
* **Modified Files:** `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/config/settings.py`, `config.json`, `sopno/tools/builtins/__init__.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now work with git repositories end to end. Read-only tools cover status, log, and diff (diff capped by `git_max_diff_chars`, ANSI/OSC control marks stripped for clean LLM output). `git_branch` handles list/create/switch/delete, `git_add` stages files, `git_commit` creates commits (optionally after `git add -A`), and `git_stash` pushes/pops. Every mutating tool reuses the pending-action Yes/No gate from the file tools (`_awaiting_confirmation` / `resolve_pending` in `core/assistant.py`), so nothing is staged, committed, deleted, or stashed without the user's OK. `git_commit_message` is read-only and asks the local LLM for a conventional `type(scope): summary` message from the diff. All commands run through the persistent terminal session (`git -C <repo> …`) so the terminal blocklist and privileges apply; values are shlex-quoted and validated. 42 new tests exercise the real `git` binary in throwaway repositories.

### [August 16, 2026] — Step 12: File & Folder Access (Permission-Gated)
* **Added Files:** `sopno/tools/builtins/files.py`, `tests/test_files.py`
* **Modified Files:** `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/config/settings.py`, `config.json`, `sopno/core/assistant.py`, `sopno/tools/builtins/__init__.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now read and write files and folders — but only where the user grants it. Every operation passes the `_authorize` gate: master switch (`file_enabled`), absolute symlink-resolved path, a secret deny-list (`.env`, `.git`, `.ssh`, `*.pem`/`*.key`, `credentials.json`, `config.json`, `sopno/memory/memory.db`, …), then allowlist roots (`file_allowed_read` / `file_allowed_write`, default project root). Reads are free inside the roots; `write_file` / `edit_file` / `delete_file` / `rename_file` park a pending action and ask the user for a Yes/No confirmation (spoken in voice mode, typed in text mode), resolved in `assistant.py` via `pending_action()` / `resolve_pending()`. `edit_file` enforces a read-before-edit invariant and re-checks uniqueness before writing. Content is capped by `file_max_size_bytes` / `file_output_chars`.
### [August 16, 2026] — Step 11: Process / Service / Log / Cron Management
* **Added Files:** `sopno/tools/builtins/manage.py`, `tests/test_manage.py`
* **Modified Files:** `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/core/assistant.py`, `sopno/tools/builtins/terminal.py`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now manage the system it runs on, all executed through the persistent terminal session (so the safety blocklist applies everywhere): `list_processes` / `kill_process` (kernel, init, systemd, and Sopno's own shell are protected), `manage_service` via `systemctl --user` (start/stop/restart/status/enable/disable/reload), `read_logs` from the user/system journal or any log file, and `manage_cron` (list/add/remove, with schedule validation and blocked-command refusal). `terminal.py` gained `_run_command_raw` (structured stdout + exit code for higher-level tools) and `_shell_pid` (self-session kill guard).
### [August 16, 2026] — Step 10: Terminal Access (Persistent Shell)
* **Added Files:** `sopno/tools/builtins/terminal.py`, `tests/test_terminal.py`
* **Modified Files:** `sopno/tools/registry.py`, `sopno/tools/schema.py`, `sopno/config/settings.py`, `config.json`, `sopno/core/assistant.py`, `requirements.txt`, `tests/test_tools.py`, `doc/CODEBASE.md`
* **Impact:** Sopno can now execute real shell commands through a persistent, structured PTY session (`cleat`): `run_terminal` runs commands with real exit codes, `terminal_send` types into interactive programs, and `terminal_status` polls long-running jobs without interfering. `cd`/`export`/background jobs persist across calls. Destructive or irreversible commands are blocked by a configurable safety blocklist (`terminal_blocklist`), and the session closes cleanly on shutdown.
### [August 14, 2026] — Step 9: Barge-In (Interruptible Voice)
* **Added Files:** `sopno/voice/barge.py`, `tests/test_barge.py`
* **Modified Files:** `sopno/voice/tts.py`, `sopno/core/assistant.py`, `sopno/config/settings.py`, `config.json`, `tests/test_tts.py`, `doc/CODEBASE.md`
* **Impact:** Sopno now stops speaking the moment you start talking and returns to listening (no settle pause). `BargeInMonitor` measures Sopno's own voice for 0.4s, then flags an interrupt when the user speaks above `own_voice × 1.7 + 30` for 180ms — all tunable in `config.json`. Graceful degradation if PyAudio/mic is missing.

### [August 14, 2026] — Step 7: Clean Folder Organization (HUD + Tools)
* **Modified Files:** `sopno/ui/hud/` (reorganized), `sopno/tools/` (reorganized)
* **Impact:** HUD package split into `behaviors/` (5 mixins), `widgets/` (robot, chat, mode_toggle), `visuals/` (theme, icons); `run.py` renamed `app.py`; hot-reload watcher now uses `rglob("*.py")`. Tools split into a framework (`registry.py` + `schema.py` stay top-level) + `tools/builtins/` for skills. Public APIs preserved (`sopno.ui.hud.run_hud`, `sopno.tools.execute_tool`).

### [July 20, 2026] — Finalization of Offline TTS & Daemon
* **Modified Files:** `sopno.py`, `install_daemon.sh`, `doc/ROADMAP_STATUS.md`
* **Added Files:** `.config/autostart/sopno_hud.desktop`
* **Impact:** Fully offline TTS via Coqui TTS, systemd user service enabled, autostart configured, CLI sync completed.
* **Added Files:** `test_edge_tts.py`
* **Impact:** Drastically reduced TTS response latency (~2s down to ~400ms) and made the voice incredibly natural, human-like, and expressive.

### [July 14, 2026] — Step 2: Integrated Dual-Mode Wake-Word Engine
* **Modified Files:** `gui.py`, `doc/ROADMAP_STATUS.md`
* **Impact:** Integrated Picovoice Porcupine for offline, near-zero CPU wake-word detection with an automated fallback to continuous SpeechRecognition.

### [July 14, 2026] — Step 3: Implemented Offline Faster Whisper STT
* **Modified Files:** `sopno.py`, `doc/ROADMAP_STATUS.md`
* **Added Files:** `test_whisper.py`
* **Impact:** Fully offline voice recognition with native bilingual support. Eliminates internet latency for voice transcribing.

### [July 17, 2026] — Step 4: Replaced Picovoice with sherpa-onnx KWS
* **Modified Files:** `gui.py`, `config.json`, `doc/ROADMAP_STATUS.md`
* **Impact:** Upgraded wake-word detection to a completely free, local, open-source model using `sherpa-onnx`. Removed requirements for Picovoice access keys and commercial licenses, allowing unlimited custom local wake words (e.g., "Sopno", "Dream").

### [July 28, 2026] — Step 5: Wired Wake Word into Main Loop
* **Modified Files:** `assistant.py`, `config.json`, `settings.py`, `hud.py`, `cli.py`, `tests/test_wakeword.py`, `doc/roadmap/status.md`
* **Impact:** Wake word detection is now fully integrated into the assistant pipeline. Added `listening_mode` config option ("wake_word" or "always_on") to choose between gated wake-word activation and continuous VAD listening. HUD shows "Say 'Sopno'…" in wake_word standby; CLI banner reflects active mode. Added unit tests for `WakeWordDetector`.

### [August 13, 2026] — Step 6: SQLite Long-Term Memory
* **Added Files:** `sopno/memory/store.py`, `sopno/memory/__init__.py`, `tests/test_memory.py`, `doc/modules/memory/memory.md`
* **Modified Files:** `sopno/core/assistant.py`, `sopno/core/context.py`, `sopno/config/settings.py`, `config.json`, `.gitignore`, `doc/README.md`, `doc/roadmap/status.md`
* **Impact:** Sopno now has human-like long-term memory. Facts are persisted to a SQLite DB (FTS5 search index, importance/recency ranking, soft-delete) and survive restarts. New bilingual commands: "remember that X" / "মনে রাখো X", "forget X" / "ভুলে যাও X", "what do you remember?" / "কী মনে আছে", plus "forget everything". Memories are injected into the LLM prompt via `context.py` with a token-budget guard (`memory_max_tokens`).

