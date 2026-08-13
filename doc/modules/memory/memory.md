# 🧠 Sopno — SQLite Memory System

## What we are doing
We are giving **Sopno** a *human-like memory*. Today Sopno forgets everything the
moment the app closes — its "memory" is just the conversation history held in RAM
(`sopno/core/context.py`) and compressed by an LLM summarizer when it gets too long.

We are building a **persistent long-term memory layer backed by SQLite**. When you
tell Sopno *"remember that…"*, it writes a fact to a local database file. On every
future conversation, Sopno reads back the relevant memories and injects them into
the LLM prompt — so it can *remember you across restarts*, like a person.

This is a **design & specification document** for that feature. Implementation
landing in `sopno/memory/` will follow.

---

## Why memory? (the gap today)

| Today (short-term only) | With SQLite memory (long-term) |
|---|---|
| Remembers the last ~6 turns in RAM | Remembers facts forever, across restarts |
| Dies on app exit | Survives reboot, `systemctl --user restart sopno` |
| History summarizer keeps only a running gist | Explicit facts you *chose* to teach Sopno are kept verbatim |
| No way to recall "what did I tell you last week" | `sopno remember` → query any time, with timestamps |
| Context grows with every turn | Stable prompt — only *relevant* memories are injected |

The feature philosophy is deliberately **explicit**: Sopno only stores what you
tell it to. This keeps the memory store small, trustworthy, and cheap on the tiny
2048-token context window — no silent auto-capture.

---

## Storage choice: SQLite (and why)

We evaluated four options before choosing SQLite.

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **SQLite** ✅ | Real SQL, ACID, indexes, FTS5 full-text search, `sqlite-vec` for embeddings later, zero deps (stdlib `sqlite3`), one file, offline, no server | Single-writer (writes are instant here), you own schema/migrations | **Chosen** — grows with the "make Sopno very powerful" goal |
| JSON file | Trivial, human-readable | No querying, no indexing, rewrite whole file per write, no search | Good for v0 prototypes; weak long-term |
| Vector DB (Chroma/FAISS) | Semantic similarity recall | Heavy deps, embedding model + RAM/CPU cost, overkill for <a few hundred facts | Add later **on top of** SQLite via `sqlite-vec` |
| mem0 / MemGPT / LangChain memory | Prebuilt "memory frameworks" | Heavy deps, lock-in, conflicts with offline-first/CPU-first design | Avoid |

**Hardware note:** SQLite stores data on the **hard disk** — that is exactly what
long-term memory should be. It maps cleanly to the brain model:

- **Working memory** → RAM (conversation context + summarizer, already exists)
- **Long-term memory** → disk (SQLite file, new)
- **Episodic/declarative recall** → FTS/vector query over the SQLite file (future)

---

## Architecture

### Three memory layers

```
                    ┌───────────────────────────────┐
                    │        WORKING MEMORY          │  RAM, per session
                    │  ConversationContext + summary │  (already built)
                    └───────────────┬───────────────┘
                                    │ context window
                    ┌───────────────▼───────────────┐
                    │        LONG-TERM MEMORY        │  DISK, forever
                    │   SQLite  memory.db  (new)     │
                    │   facts · prefs · timestamps   │
                    └───────────────┬───────────────┘
                                    │ FTS5 / vector recall (future)
                    ┌───────────────▼───────────────┐
                    │        SEMANTIC MEMORY         │  DISK, future
                    │   sqlite-vec embeddings        │  automatic recall
                    └───────────────────────────────┘
```

### Data flow (once implemented)

```
User speaks: "Remember that my laptop is called Athena"
    │
    ▼
assistant.py  ── detect remember-intent (rule + LLM fallback)
    │
    ▼
sopno/memory/store.py  ── MemoryStore().remember(content, category)
    │
    ▼
memory.db  (INSERT with created_at; FTS5 index updated)
    │
    ▼
assistant.py replies: "Got it — I'll remember that."
    │
    ── next session ──
    │
context.py ── get_messages_for_llm()  calls  memory_store.recall(prompt, limit)
    │
    ▼
MemoryStore().recall()  ── FTS5 keyword match (SQLite) → top-N memories
    │
    ▼
[MEMORIES] block injected into system prompt  →  Sopno "remembers" you
```

---

## Schema design

File location: `sopno/memory/memory.db` (path from `settings` / `config.json`).

```sql
-- Core fact table: one row = one memory
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,               -- what Sopno should remember
    category    TEXT NOT NULL DEFAULT 'fact',-- fact | preference | project | contact | ...
    importance  INTEGER NOT NULL DEFAULT 1,  -- 1..3, user can say "this is important"
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,                        -- bumped on each recall (recency signal)
    use_count   INTEGER NOT NULL DEFAULT 0,  -- for recency/frequency ranking later
    active      INTEGER NOT NULL DEFAULT 1   -- soft delete; forget = set 0
);

-- Full-text search over memory content (FTS5 ships inside SQLite)
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, category,
    content='memories', content_rowid='id'
);

-- Keep the FTS index in sync automatically
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT  ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, category)
    VALUES (new.id, new.content, new.category);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE  ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES('delete', old.id, old.content, old.category);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE  ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES('delete', old.id, old.content, old.category);
    INSERT INTO memories_fts(rowid, content, category)
    VALUES (new.id, new.content, new.category);
END;
```

Indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(active, importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
```

Design notes:
- **Soft delete** (`active=0`) — "forget" never destroys data destructively; easy
  to undo and safe.
- **`importance` + `use_count` + `last_used_at`** — give a clean ranking signal so
  we can later inject "top-K most relevant memories" within the token budget.
- **FTS5 external-content table** — keyword search (Bangla works: tokenized per
  character) is the cheap recall path before we ever add embeddings.
- **Migrations** — keep `schema_version` in a tiny `meta` table; run incremental
  migrations on open. (One table now, but the project plans to grow.)

```sql
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1');
```

---

## Module API design (`sopno/memory/store.py`)

One class, used everywhere, kept decoupled from the LLM:

```python
class MemoryStore:
    def __init__(self, db_path: Path | None = None) -> None: ...

    def remember(self, content: str, category: str = "fact",
                 importance: int = 1) -> int: ...
    # Returns new memory id. content is deduped lightly (exact match → update instead).

    def forget(self, memory_id: int | None = None, text: str | None = None) -> bool: ...
    # Soft-delete by id, or by fuzzy match on content. False if nothing matched.

    def recall(self, query: str = "", limit: int = 8, *,
               categories: list[str] | None = None) -> list[dict]: ...
    # FTS5 ranking + importance + recency; returns [{id, content, category,
    # importance, created_at, use_count}] and bumps last_used_at/use_count.

    def all(self, active_only: bool = True) -> list[dict]: ...   # for "what do you remember?"
    def stats(self) -> dict: ...                                   # counts per category
    def wipe(self) -> int: ...                                     # forget EVERYTHING (safe mode)
    def close(self) -> None: ...
```

`MemoryStore` is a **singleton at app level** (opened once in `SopnoAssistant`),
because opening/closing SQLite per voice turn would add latency to every reply.

Threading: SQLite handles our write pattern (rare, tiny writes) with WAL mode;
enable `PRAGMA journal_mode=WAL` and one shared connection guarded by a lock.

---

## Integration points

| File | Change |
|---|---|
| `sopno/memory/store.py` | **New** — `MemoryStore` class + schema bootstrap |
| `sopno/memory/__init__.py` | **New** — package exports (`MemoryStore`) |
| `sopno/core/assistant.py` | Detect remember/forget/recall intents; own the `MemoryStore` instance |
| `sopno/core/context.py` | `get_messages_for_llm()` injects the `[MEMORIES]` block |
| `sopno/config/settings.py` | `memory_path`, `memory_max_tokens`, `memory_recall_limit` |
| `config.json` | Add the memory keys above |
| `prompts/system.txt` | Tell Sopno it has long-term memory and when to use it |
| `prompts/` | Add `remember.txt` extractor prompt (for LLM-based intent parsing) |
| `.gitignore` | Ignore `sopno/memory/memory.db` (user data, never commit) |
| `tests/` | `tests/test_memory.py` |

### Intent detection in `assistant.py`

Two-stage, mirroring the existing dispatcher pattern:

1. **Rule regex (fast path)** — cheap, before any LLM call:
   - English: `remember that ...`, `remember ...`, `don't forget ...`
   - Bangla: `মনে রাখো ...`, `মনে রেখো ...`, `ভুলো না ...`
   - `forget ...`, `ভুলে যাও ...` · `what do you remember?`, `কী মনে আছে?`
2. **LLM fallback** — if no rule matches but the reply would be toolish, let the
   model emit a `remember` / `forget` / `recall` tool call (add to `TOOLS_SCHEMA`),
   exactly like the existing tool-calling path in `assistant.py:_process_command`.

### Context injection (`context.py`)

`get_messages_for_llm()` injects a compact memory block right after the system
prompt, **only when memories exist**:

```
[Memories]
• My laptop is called Athena (important)
• I prefer dark theme
• I am working on a Django project called sopno
```

Token budget guard: memories are trimmed so the block fits
`memory_max_tokens` (default ≈ 400) — read all active memories, keep the most
important/recent ones, truncate long ones. This protects the 2048 `num_ctx` window
so memory never degrades conversation quality.

---

## Voice & text commands

| Command (EN) | Command (BN) | Behavior |
|---|---|---|
| "Remember that my laptop is Athena" | "মনে রাখো আমার ল্যাপটপের নাম অ্যাথেনা" | Store fact, confirm out loud |
| "Remember this is important" | "এটা গুরুত্বপূর্ণ মনে রাখো" | `importance=3` |
| "Forget that" / "Forget my laptop name" | "ভুলে যাও" | Soft-delete matching memory |
| "What do you remember about me?" | "আমার সম্পর্কে কী মনে আছে?" | Recall + speak top memories |
| "Forget everything" | "সব ভুলে যাও" | Confirmation prompt → `wipe()` |

---

## Security & privacy

- The DB is **plain local user data** — like any notes file. Never commit it
  (`.gitignore`).
- Store **facts, never secrets**. A `remember that my password is X` should be
  refused/flagged — memories are injected into a model prompt and could leak into
  logs. Add this rule to `prompts/system.txt`.
- Path defaults to `sopno/memory/memory.db` with `0600` permissions if the OS
  supports it.
- Optional future: `sqlite3` transparent DB encryption is not stdlib — keep plain
  file + OS-level permissions unless a real threat model demands more.

---

## Testing plan (`tests/test_memory.py`)

- [ ] `remember` inserts a row; `recall("laptop")` finds it; `use_count` bumps.
- [ ] Exact-duplicate remember updates instead of duplicating.
- [ ] `forget` soft-deletes; `recall` no longer returns it; `stats` reflects it.
- [ ] `wipe` removes all active rows (and requires explicit flag in code).
- [ ] FTS5 triggers keep the index in sync on insert/update/delete.
- [ ] Bangla content round-trips correctly (Unicode) through FTS5.
- [ ] Token guard: `memory_max_tokens` respected even with 100+ memories.
- [ ] Store is fast enough for a voice turn (<50ms per recall on CPU).
- [ ] Assistant integration: "remember X" does not call the LLM (rule path).
- [ ] Language: BN remember command replies in Bangla.

---

## Roadmap / phases

| Phase | Scope | Status |
|---|---|---|
| **P0** | `sopno/memory/store.py` schema + CRUD + FTS5, `test_memory.py` | ⬜ Planned |
| **P1** | Wire into `assistant.py` (remember/forget/recall commands, EN+BN), confirm replies | ⬜ Planned |
| **P2** | `context.py` memory injection + token guard, `config.json` keys | ⬜ Planned |
| **P3** | LLM tool-call path (`remember`/`forget` tools in `TOOLS_SCHEMA`) | ⬜ Planned |
| **P4** | `sqlite-vec` semantic recall — auto-retrieve "similar" memories without explicit tags | 🔮 Future |
| **P5** | Learning system (features.md §35) — Sopno recalls corrections/preferences on its own | 🔮 Future |

### Future extensions (same DB, additive)
- **FTS5 "search my memories"** tool → `"what did I ask you about Flask last month?"`
- **`sqlite-vec` embeddings** → semantic recall, no extra database server.
- **Category management** → projects, contacts, preferences surfaced in the HUD.
- **Memory browser in HUD** → features.md §32 lists a "Memory" GUI panel.

---

## Related docs

- [overview.md](../../architecture/overview.md) — folder structure & module boundaries
- [CODEBASE.md](../../CODEBASE.md) — complete codebase guide
- [features.md](../../roadmap/features.md) — §8 Memory (short / long / semantic)
- [status.md](../../roadmap/status.md) — progress tracker
- [tts.md](../voice/tts.md) — module-doc convention this file follows

---

*Document created: August 13, 2026*  
*Author: MD. Abduss Sobhan with AI assistant*  
*Status: Design spec — implementation pending*
