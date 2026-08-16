# 🗺️ Sopno Next Features — Implementation Plan (v2)

Research-backed implementation plan for the next wave of Sopno capabilities,
written so each feature can be built and tested one at a time, in order.

**Current baseline (all done):** voice (STT/TTS/wakeword/barge-in), persistent
terminal + process/service/log/cron management, internet (search/fetch) + deep
research (RAG), permission-gated file access (read/write/edit/delete/rename +
search/copy/move + PDF/image/Office readers), git tools
(status/log/diff/branch/add/commit/stash + LLM commit messages), memory
(context + SQLite + semantic vectors), tool framework (34 tools), HUD/CLI.

---

## Phasing

| Phase | Features | Est. effort |
|-------|----------|-------------|
| **A — Core** | 1. Git tools · 2. Semantic memory · 3. File access round 2 · 4. Scheduler/reminders | ~4–6 sessions |
| **B — Desktop** | 5. Browser automation · 6. MCP + plugin system · 7. Desktop control + hardware | ~4–6 sessions |
| **C — Power** | 8. DB / packages / networking · 9. Vision / email / calendar / notes / knowledge base · 10. GUI dashboard / automation rules / multi-agent | ongoing |

**Cross-cutting rule (from the features.md security section):** anything
destructive or identity-touching (write/delete/send/commit/push) goes through
the existing confirmation gate (pending action → user Yes/No) or an explicit
permission config key. No feature bypasses `_authorize` or `terminal_blocklist`.

---

## Phase A

### 1. Git Tools — ✅ IMPLEMENTED (Step 13)

> Shipped in `sopno/tools/builtins/git.py` (+ `tests/test_git.py`, 42 tests):
> `git_status`, `git_log`, `git_diff`, `git_branch` (list/create/switch/delete),
> `git_add`, `git_commit` (`add_all` option), `git_stash` (list/push/pop),
> `git_commit_message` (LLM-drafted, read-only). Mutating tools reuse the
> pending-action Yes/No gate; everything runs via `git -C <repo>` through the
> terminal session with shlex-quoted, metachar-checked values.

**Research findings**
- Shell out to the `git` CLI with `subprocess`/`_run_command_raw`, not a library.
  GitPython is in maintenance mode, pygit2 is low-level plumbing, and any
  independent reimplementation breaks on the "1% of configs" (alternates,
  partial clones, config tricks). The CLI gives 100% compatibility. Use
  `--porcelain`-style output and parse it.
- Feed the **staged diff / diff HEAD** to the LLM for AI commit messages and
  reviews; skip binary files; cap huge generated-file diffs.
- `git commit -m` with `-m` is non-interactive (no editor/hooks prompt).
  Respect user `commit.gpgsign`/hooks — if a hook fails, report its output.

**Tools (new `sopno/tools/builtins/git.py`)**
- `git_status()` — `git status --short --branch`, plus `git log --oneline -10`.
- `git_diff(staged, path, max_chars)` — `git diff --staged` or `git diff HEAD`,
  capped output.
- `git_add(paths)` — stage files; requires confirmation (stage-only).
- `git_commit(message, add_all)` — `git add -A` + `git commit -m`; **requires
  confirmation** showing the exact staged diff summary first.
- `git_commit_message(staged)` — **no file mutation**: sends the diff to the
  LLM and returns a suggested `type(scope): subject` + body message (matches
  this repo's conventional-commit style).
- `git_branch(action, name)` — list/create/delete/switch branches.
- `git_log(limit)` — pretty one-line log with dates.
- `git_stash(action, message)` — list/push/pop.

**Safety:** runs through `_run_command_raw` (blocklist applies). `git_commit`
and `git_add` and `git_branch -D` park a pending action + confirm. Refuse
`git push` unless a future `git_push_enabled` config key is set. Protect the
`.git/` dir (already in `file_blocked_paths`).

**Config keys:** `git_enabled` (true), `git_max_diff_chars` (12000).

### 2. Semantic Memory

**Research findings**
- `sqlite-vec` is a tiny C SQLite extension (`pip install sqlite-vec`,
  `sqlite_vec.load(db)`) providing `vec0` virtual tables + KNN `MATCH`.
  Sub-10ms queries for <100k vectors; perfect for a local assistant; keeps
  everything in the existing `memory.db`.
- Embeddings should come from the **already-installed Ollama
  `nomic-embed-text`** (Sopno uses it for research today) → 768-dim, free,
  offline. No new model stack needed (sentence-transformers/ONNX is the
  fallback if Ollama is absent).
- Store raw text + normalized float32 BLOB together; cosine ≈ dot product on
  normalized vectors; join `vec0` rowid → memory table on recall.

**Design (`sopno/memory/semantic.py`)**
- On `remember()`: also compute embedding, insert into `memory_vectors`
  (`vec0(embedding float[768])`) keyed by the memory rowid (soft-delete keeps
  the vector; delete both on wipe).
- On recall: embed the query, `SELECT rowid FROM memory_vectors WHERE
  embedding MATCH ? ORDER BY distance LIMIT k`, join back to memories, merge
  with the existing FTS5 keyword results (interleave by score).
- Lazy model load; degrade gracefully to FTS5-only when Ollama is down
  (never block the assistant on an embed).

**Config keys:** `semantic_memory_enabled` (true), `semantic_recall_limit` (4).

**Testing:** temp-DB tests — embed via a mocked model (fixed vectors), assert
recall returns the nearest row; assert graceful fallback when Ollama missing.

> **✅ IMPLEMENTED (Step 14, Aug 16 2026):** `sopno/memory/semantic.py` +
> integration in `sopno/memory/store.py` (vec0 table guarded by
> `semantic_memory_enabled` + sqlite-vec availability, embeddings on
> `remember()`, KNN on recall with `_MIN_COSINE = 0.4`, keyword matches kept
> first with semantic matches filling the remaining slots). Zero vectors are
> never stored (they'd match everything at cosine 0.5). Fallback to FTS5-only
> verified in `tests/test_semantic.py` (14 tests, mocked embeddings).

### 3. File Access Round 2 — ✅ IMPLEMENTED (Step 15)

**Research findings**
- **Search:** filename → `Path.rglob` + `fnmatch`/regex; content → read text
  files and `re.search` (or `grep -n` via the safe runner, capped); skip
  binaries/`.git`; respect `file_blocked_paths`.
- **Copy/move/duplicate:** `shutil.copy2` / `Path.rename` (already safe from
  #1). Folders copy allowed, delete still files-only.
- **Binary readers** (all local, no cloud):
  - PDF: `pymupdf` (PyMuPDF) text extraction; scanned → Tesseract OCR.
  - Images: `Pillow` + Tesseract OCR (`pytesseract`).
  - Office: `python-docx`, `python-pptx`, `openpyxl` directly; legacy
    `.doc/.xls/.ppt` via `libreoffice --headless --convert-to`.
  - Keep it layered like `kreuzberg`/`ocr-extractor`: fast native extract →
    OCR fallback → LibreOffice for legacy; cap page/image counts and output
    chars; report which path was used.

**Tools (extend `files.py`)**
- `search_files(query, path, mode)` — mode `name` (filename glob/regex) or
  `content` (text grep); returns capped `path:line` hits.
- `copy_file(path, new_path, overwrite)` — confirmed.
- `rename_file` already exists; add `move_file` = alias with confirmation.
- `read_file` auto-detects `.pdf/.png/.jpg/.docx/.xlsx/.pptx/...` and routes
  to the right extractor (new `sopno/tools/builtins/readers.py`), capped by
  `file_max_size_bytes`/`file_output_chars`.

**Config keys:** `file_search_max_results` (50), `file_ocr_enabled` (true),
`readers_max_pages` (20), `readers_max_chars` (20000).

**Deps (optional, graceful import):** `pymupdf`, `Pillow`, `pytesseract`,
`python-docx`, `python-pptx`, `openpyxl`; system `tesseract-ocr`, `libreoffice`.

> **✅ IMPLEMENTED (Step 15, Aug 16 2026):** `sopno/tools/builtins/readers.py`
> + new tools in `files.py`. `search_files` (name/content modes, `path:line`
> hits, `file_search_max_results` cap, skips blocked + binary), `copy_file`
> (files & folders, `overwrite` flag, confirmed), `move_file` (confirmed alias
> of `rename_file`). `read_file` routes binary docs by suffix through a layered
> extractor (PDF native → OCR; image OCR; Office; legacy LibreOffice), capped by
> `readers_max_pages`/`readers_max_chars`, and tags output with the method used.
> Binary-file skip in content search uses `readers.is_binary_like` (suffix or
> null-byte sniff). 41 new tests → suite at 291.

### 4. Scheduler / Reminders

**Research findings**
- **Let the LLM parse intent, keep execution deterministic.** The LLM tool-call
  returns `(when, what)`; a parser normalizes to a due timestamp or cron expr.
  Don't build an NLU pipeline.
- **Persist in SQLite, not memory** — a restart must not lose reminders.
  States: `pending → delivered | missed | cancelled`. A poller checks every
  ~15–60s; overdue-while-offline fire on the next tick (at-least-once, no
  explosion).
- **"A cron job is just a message"** — reuse the assistant loop for delivery:
  fire the reminder through `_deliver_reply` (HUD text + optional TTS spoken
  alert). Simplest reliable path for a local assistant; no separate agent
  process.
- One-shots (reminders) and recurring (cron) are different domains: reminders
  = SQLite + poller; recurring = existing `manage_cron` via crontab.

**Design (`sopno/core/reminders.py` + `sopno/tools/builtins/reminders.py`)**
- Table `reminders(id, due_at, text, status, created_at)`.
- Tools: `set_reminder(when, text)`, `list_reminders()`, `cancel_reminder(id)`.
  `when` accepts `now + N m/h/d`, `HH:MM`, `YYYY-MM-DD HH:MM`, `tomorrow 9am`
  etc. — a small deterministic parser; on ambiguity, ask (LLM clarification).
- A daemon thread in `SopnoAssistant.run()` polls `due_at <= now AND status =
  pending`, marks `delivered`, and pushes text into the reply flow
  ("Reminder: {text}").
- **Safety:** setting a reminder is non-destructive (no confirmation); cancel
  confirms only when it matches an existing id. Cap `reminders_max` (50) and
  max horizon (365 days).

**Config keys:** `reminders_enabled` (true), `reminders_poll_seconds` (30).

**Testing:** set/due/deliver/cancel with a fake clock; persistence across a
store reopen; malformed `when` → friendly error.

> **✅ IMPLEMENTED (Step 16, Aug 16 2026):** `sopno/core/reminders.py` +
> `sopno/tools/builtins/reminders.py` + `tests/test_reminders.py` (30 tests).
> `ReminderStore` (own SQLite DB, WAL, `pending → delivered | cancelled`),
> `parse_when` (deterministic regex → absolute epoch; past wall-clock times roll
> to tomorrow), `ReminderPoller` daemon thread started in `SopnoAssistant.run()`
> delivering "Reminder: {text}" through `_deliver_reminder` (speech-lock
> guarded). Config: `reminders_enabled`, `reminders_poll_seconds`,
> `reminders_max` (50), `reminders_max_horizon_days` (365), `reminders_path`.
> Suite → 321.

---

## Phase B

### 5. Browser Automation (Playwright)

**Research findings**
- Playwright is the 2026 default (30–50% faster than Selenium, bundles its own
  Chromium/Firefox/WebKit, auto-waiting). Python package + `playwright install
  chromium` once.
- **Separate planning from execution.** Expose discrete, guarded tools
  (`navigate`, `click`, `type`, `extract`, `screenshot`) to the LLM rather than
  a free-form agent loop. Isolate one `BrowserContext` per task (no cookie
  leakage). Block `image/media/font` resources for token/bandwidth savings.
  Feed the LLM an **accessibility snapshot / text** (cheap) instead of
  screenshots (vision) except when needed.
- **Security:** `browser_allowed_domains` allowlist (deny navigation outside),
  hard per-step timeout (30s) + per-task ceiling, no downloads, treat page
  content as untrusted (prompt-injection → the LLM should not follow page
  instructions for mutating actions).
- Honest limits: stock Playwright is detectable by Cloudflare/DataDome; for
  personal use that's acceptable.

**Tools (new `sopno/tools/builtins/browser.py`)** — lazy singleton browser:
- `browser_navigate(url)` — goto, return page title + text snapshot (capped).
- `browser_click(selector, index)` / `browser_type(selector, text)` —
  element-index based on the snapshot; refactor-safe.
- `browser_extract(selector)` — text of a region.
- `browser_screenshot(path, full_page)` — writes PNG **inside an allowed read
  root** via `files._authorize`, confirmed if overwriting.
- `browser_back()` / `browser_close()`.

**Config keys:** `browser_enabled` (false — opt-in; heavy dep),
`browser_allowed_domains` ([]), `browser_timeout` (30), `browser_task_limit`
(120s), `browser_headless` (true).

**Deps:** `playwright` (pip) + `playwright install chromium` (one-time).

> **✅ IMPLEMENTED (Step 17, Aug 16 2026):** `sopno/tools/builtins/browser.py`
> + `tests/test_browser.py` (17 tests). Lazy singleton `BrowserSession`; tools
> `browser_navigate` (text snapshot: title + body + `[0]…`-indexed interactive
> elements), `browser_click(selector, index)`, `browser_type(selector, text)`,
> `browser_extract(selector)`, `browser_screenshot(path, full_page)` (write-root
> + overwrite confirm), `browser_back`, `browser_close`. Security:
> `browser_allowed_domains` deny-by-default, `browser_timeout`,
> `browser_task_limit` session ceiling, `image/media/font` blocked, untrusted
> page content. `browser_enabled` defaults to **false** (opt-in; graceful
> message when Playwright is missing). Config keys:
> `browser_enabled`/`browser_allowed_domains`/`browser_timeout`/
> `browser_task_limit`/`browser_headless`. Suite → 338.

### 6. MCP Support + Plugin System

**Research findings**
- Official **MCP Python SDK v2** (`mcp` package): `MCPServer` +
  `@mcp.tool()` to expose tools; `mcp.Client` to consume remote servers.
  Transport: `stdio` for local, `streamable-http` for remote; SSE is legacy.
- Two directions for Sopno:
  1. **Sopno as an MCP *server*** (`sopno-mcp.py`): wraps `_REGISTRY` so any
     MCP host (Claude Desktop, Cursor, opencode…) can drive Sopno's tools —
     essentially zero extra code, one entry file.
  2. **Sopno as an MCP *client***: read `mcp_servers` from config
     (`{"name": {"command": [...], "args": [...]}}`), connect over stdio,
     `list_tools()`, and merge the returned tool schemas into `TOOLS_SCHEMA`
     with a `name:` prefix; dispatch calls to the remote server.
- Plugin system = dynamic tool loading: a plugin exposes
  `plugin_tools()` → `{name: (fn, schema)}`; loader registers into
  `_REGISTRY` + `TOOLS_SCHEMA` at startup. Keep the permission gate: plugins
  get a default-deny policy unless they declare an explicit allow scope.

**Design**
- `sopno/tools/mcp_client.py` — connect/refresh/execute; `mcp_server.py` —
  wraps registry as `MCPServer`.
- `sopno/tools/plugins.py` — discover `plugins/*/plugin.py`, register tools,
  load `config.json` per plugin, call `on_load()`/`on_unload()`.

**Config keys:** `mcp_servers` ({}), `mcp_enabled` (true),
`plugins_enabled` (true), `plugins_dir` (project/plugins).

> **✅ IMPLEMENTED (Step 18, Aug 16 2026):** `sopno/tools/plugins.py` +
> `sopno/tools/mcp_client.py` + `sopno/tools/mcp_server.py` +
> `tests/test_plugins.py` + `tests/test_mcp.py` (16 tests). Registry/schema
> gained `register/unregister` for dynamic tools; the LLM prompt uses
> `get_schema()` so plugin/MCP tools are visible from the first turn. Plugin
> contract: `plugin_tools() -> {name: (fn, schema)}`, namespaced
> `<plugin>_<tool>`, optional confirm gate, `on_load`/`on_unload`, default-deny
> (no bypass of file roots / blocklist / confirmations). MCP client `McpHub`
> connects to `mcp_servers` over stdio (SDK v2, own event-loop thread) and
> registers `<server>_<tool>`; MCP server `python -m sopno.tools.mcp_server`
> exposes the full registry to any host. Both directions tested over real stdio
> (client↔server, and Sopno client driving Sopno server). Suite → 354.

> **✅ IMPLEMENTED (Step 19, Aug 16 2026):** `sopno/tools/builtins/desktop.py`
> + `tests/test_desktop.py` (35 tests). New tools: `clipboard_get`/`clipboard_set`
> (xclip/xsel, set confirmed), `take_screenshot(path, region)` (scrot/maim,
> write-root gated + overwrite confirmed), `list_windows`/`focus_window`
> (wmctrl), `send_keys`/`press_key` (xdotool, confirmed, unsafe combos
> rejected), `get_disk_stats` (psutil partitions/temps/fans, snap+loop
> filtered), `get_gpu_stats` (pynvml, graceful no-GPU note), `get_network_stats`
> (psutil per-interface). `get_system_stats` extended with disk + CPU temp.
> `open_application` honours `desktop_allowed_apps`. X11-first with honest
> degradation: every dep optional (runtime detection → friendly messages);
> `desktop_require_x11` refuses input/window/clipboard on Wayland. Config:
> `desktop_enabled` / `desktop_allowed_apps` / `desktop_require_x11`. Suite → 389.

### 7. Desktop Control + Hardware

**Research findings**
- Linux/X11-first (matches existing `system.py`): `xdotool` (input + windows),
  `wmctrl` (window list/focus), `xclip`/`xsel` (clipboard), `scrot`/`maim`/
  `gnome-screenshot` (screenshots), `tesseract` (screen OCR). Wayland is
  partial (ydotool/portals) — detect `WAYLAND_DISPLAY` and degrade honestly
  (report unavailable capabilities instead of failing silently).
- Hardware: `psutil` (already used) covers disk usage/partitions, network,
  `sensors_temperatures()`, `sensors_fans()`, `sensors_battery()`. GPU via
  `nvidia-ml-py` (pynvml, no subprocess) when an NVIDIA driver exists,
  gracefully skipped otherwise.

**Tools (extend `system.py` + new `sopno/tools/builtins/desktop.py`)**
- `clipboard_get()` / `clipboard_set(text)` — `xclip`/`xsel`; set confirmed.
- `take_screenshot(path, region)` — writes into an allowed root, confirmed.
- `list_windows()` / `focus_window(title)` — `wmctrl -l` / `wmctrl -a`.
- `send_keys(keys)` / `press_key(combo)` — `xdotool type` / `xdotool key`.
- `get_disk_stats()` — partitions + usage + temps + fans (psutil).
- `get_gpu_stats()` — pynvml: name, util%, vram, temp; "no GPU" otherwise.
- `get_network_stats()` — per-interface RX/TX (psutil).
- Extend `get_system_stats` to include disk/temp when available.

**Config keys:** `desktop_enabled` (true), `desktop_allowed_apps` (for launch),
`desktop_require_x11` (true — refuse on Wayland for input/window tools).

**Deps (optional, detected at runtime):** `xdotool`, `wmctrl`, `xclip`,
`scrot`, `nvidia-ml-py`; system `tesseract-ocr` for OCR.

---

## Phase C (order flexible)

> **✅ IMPLEMENTED (Step 20, Aug 16 2026):** three new skills, 10 tools.
> `databases.py` — read-only SQLite first: `query_database(path, sql)` runs
> SELECT/PRAGMA/EXPLAIN on a `mode=ro` connection and gates mutating
> statements behind Yes/No (read-write connection on approval); queries
> respect file read-roots + blocked-paths; `explain_schema` (tables/columns/
> row counts); `backup_database` (SQLite backup API, write-root gated,
> overwrite confirmed). `packages.py` — `install_package(name, manager)`
> (apt/pacman/dnf/pip/flatpak, auto-detection, confirmed, `sudo -n` for
> system managers) and `uninstall_package` (blocked by default, confirmed
> when enabled); strict name validation. `network.py` — read-only
> `ping_host`/`traceroute`/`wifi_scan`/`firewall_status()`, opt-in
> `public_ip`; only the firewall on/off toggle mutates (confirmed). All
> routed through the shared terminal so the blocklist applies. Config:
> `database_enabled`, `packages_enabled`, `packages_uninstall_allowed`,
> `packages_require_sudo`, `network_enabled`, `network_public_ip_enabled`.
> Suite → 427.

### 8. Database / Packages / Networking
- `query_database(engine, sql)` — read-only SQLite first (reuse
  `memory.db`-style SQLite; Postgres/MySQL/Mongo later via drivers), **never**
  write without confirmation; `backup_database`, `explain_schema`.
- `install_package(name, manager)` / `uninstall_package` — `apt`/`pacman`/
  `pip`/`flatpak` through `_run_command_raw` with **confirmation + sudo-only
  when configured**; block uninstall by default.
- `ping_host(host)`, `traceroute(host)`, `wifi_scan()` (nmcli), `public_ip()`
  (curl if enabled), `firewall_status(action)` — all read-only by default.

> **✅ IMPLEMENTED (Step 21, Aug 16 2026):** four new skills, 9 tools.
> `vision.py` — `describe_screenshot` (opt-in `vision_enabled` +
> `vision_model`; base64 image to Ollama `/api/chat`, ≤8 MB, read-root
> gated), `ocr_image` (pytesseract with `tesseract` CLI fallback).
> `email.py` — read-only `email_read` (IMAP) and confirmed `email_send`
> (SMTP+STARTTLS); opt-in (`email_enabled`), password from the env var named
> by `email_password_env` (never config.json), input validated.
> `calendar.py` — dependency-free `.ics` parser under `calendar_dir`
> (`calendar_list`) and confirmed `calendar_create_event` (appends an escaped
> VEVENT to `calendar.ics`, write-root gated). `notes.py` — markdown knowledge
> base under `notes_dir`: `note_write` (confirmed, overwrite confirmed),
> `note_list`, `note_search`. Suite → 462.

### 9. Vision / Email / Calendar / Notes / Knowledge Base
- **Vision:** `describe_screenshot(path)` — feed image to an Ollama vision
  model (`qwen2.5vl` etc., opt-in config); `ocr_image(path)` — Tesseract.
- **Email:** `email_read/send/reply` — read-only via IMAP + send via SMTP,
  gated behind explicit config + confirmation on send; never store passwords
  in config (env/keyring).
- **Calendar:** `calendar_list/create_event` — read via `gcalcli`/file-based
  ICS first; creation confirmed.
- **Notes/knowledge base:** `notes` = markdown files under an allowed root
  (already possible via file tools) + optional semantic index (ties into #2).

### 10. GUI Dashboard / Automation Rules / Multi-Agent
- **GUI dashboard:** new HUD tabs — settings (config.json), memory viewer,
  tool status, logs, models (Ollama list) — reading the same config/settings
  objects the CLI uses.
- **Automation rules:** "if {condition} then {action}" persisted in SQLite,
  checked on the scheduler poll (e.g. battery < 20% → enable power saving).
  Conditions/actions are thin wrappers over existing tools; each rule action
  is confirmed once at creation, not per fire.
- **Multi-agent:** subagent runners (researcher/coder/reviewer) = calling the
  same `_process_command`-style loop with a focused system prompt + restricted
  `TOOLS_SCHEMA`; results returned as text. Skip until #1–#6 are stable.

> **✅ IMPLEMENTED (Step 22, Aug 16 2026):** three systems. **Automation rules**
> (`sopno/core/rules.py` + `rules` tools) — "if `metric op value` then `tool key="v"`"
> persisted in SQLite; conditions are an allowlist grammar (battery_percent,
> cpu_percent, ram_percent, disk_free_gb, hour_of_day, day_of_week) — never
> eval-ed; a `RulePoller` daemon fires each rule once per true-period and
> auto-approves pending-action gates the action raises (one-time rule
> confirmation). **Multi-agent** (`sopno/core/subagents.py` + `run_subagent`)
> — researcher / coder / reviewer subagents, focused prompts + restricted
> `TOOLS_SCHEMA`, same Ollama tool-calling loop, text results. **GUI
> dashboard** (`sopno/ui/hud/dashboard.py`) — read-only Settings / Memory /
> Tools / Logs / Models tabs toggled by a `≡` chrome button, backed by the
> same config, MemoryStore, registry, and Ollama objects the CLI uses. 6 tools
> (73 → 79), 27 tests → suite at 489. This completes the roadmap.

---

## Dependency & safety summary
- Every new tool registers in `registry.py` + `schema.py` + `builtins/__init__.py`.
- Mutating tools (commit/push/copy/overwrite/delete/send/clipboard-set)
  reuse the pending-action confirmation from `files.py`.
- External binaries (`tesseract`, `soffice`, `xdotool`, `git`, `playwright`)
  are detected at runtime; tools report a clear "install X" message when
  missing, never crash.
- Heavy deps (`playwright`, vision models, MCP SDK) ship behind config
  switches so default install stays light.
- All new features get `tests/test_<feature>.py` following the existing
  `test_manage.py` / `test_files.py` patterns, plus doc updates in
  `CODEBASE.md` and `status.md` (numbered steps).
