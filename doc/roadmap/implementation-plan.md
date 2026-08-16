# 🗺️ Sopno Next Features — Implementation Plan (v2)

Research-backed implementation plan for the next wave of Sopno capabilities,
written so each feature can be built and tested one at a time, in order.

**Current baseline (all done):** voice (STT/TTS/wakeword/barge-in), persistent
terminal + process/service/log/cron management, internet (search/fetch) + deep
research (RAG), permission-gated file access (read/write/edit/delete/rename),
git tools (status/log/diff/branch/add/commit/stash + LLM commit messages),
memory (context + SQLite), tool framework (31 tools), HUD/CLI.

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

### 3. File Access Round 2

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

### 8. Database / Packages / Networking
- `query_database(engine, sql)` — read-only SQLite first (reuse
  `memory.db`-style SQLite; Postgres/MySQL/Mongo later via drivers), **never**
  write without confirmation; `backup_database`, `explain_schema`.
- `install_package(name, manager)` / `uninstall_package` — `apt`/`pacman`/
  `pip`/`flatpak` through `_run_command_raw` with **confirmation + sudo-only
  when configured**; block uninstall by default.
- `ping_host(host)`, `traceroute(host)`, `wifi_scan()` (nmcli), `public_ip()`
  (curl if enabled), `firewall_status(action)` — all read-only by default.

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
