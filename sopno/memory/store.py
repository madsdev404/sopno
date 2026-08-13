"""
sopno/memory/store.py
━━━━━━━━━━━━━━━━━━━━
Persistent long-term memory backed by SQLite.

Gives Sopno a human-like memory: facts you tell it to remember are written to a
local SQLite database and survive restarts. Recall uses SQLite's built-in FTS5
full-text index (keyword + importance + recency ranking) so the LLM prompt stays
small while Sopno still "remembers".

Usage:
    from sopno.memory import MemoryStore
    store = MemoryStore()
    mem_id = store.remember("My laptop is called Athena")
    store.recall("laptop")
    store.close()
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from sopno.config.settings import settings

_SCHEMA_VERSION = "1"

# FTS5 external-content table + triggers keep the search index in sync with the
# memories table automatically (SQLite's documented pattern).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content      TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT 'fact',
    importance   INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,
    use_count    INTEGER NOT NULL DEFAULT 0,
    active       INTEGER NOT NULL DEFAULT 1
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, category,
    content='memories', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, category)
    VALUES (new.id, new.content, new.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES('delete', old.id, old.content, old.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES('delete', old.id, old.content, old.category);
    INSERT INTO memories_fts(rowid, content, category)
    VALUES (new.id, new.content, new.category);
END;

CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(active, importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
"""

_MEMORY_COLUMNS = (
    "m.id, m.content, m.category, m.importance, m.created_at, "
    "m.last_used_at, m.use_count"
)


def _fts_terms(query: str) -> list[str]:
    """Extract safe single-word search terms (word chars incl. Bangla)."""
    return re.findall(r"[\w\u0980-\u09FF]+", query.lower())[:6]


def _fts_match_expr(query: str) -> str:
    """Build a valid FTS5 MATCH expression from free-text input."""
    return " AND ".join(_fts_terms(query))


def _clean(*parts: str) -> str:
    """Join extracted intent content and strip trailing punctuation."""
    text = " ".join(p for p in parts if p).strip()
    return text.rstrip("?।.!?.,;:")


class MemoryStore:
    """
    Thread-safe SQLite-backed memory for Sopno.

    One connection is shared across the app (open once, reuse, close on exit).
    Writes are rare and tiny (a "remember X" per voice turn) so a single
    connection plus a lock is more than enough.
    """

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.memory_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._bootstrap()

    # ── Schema / lifecycle ──────────────────────────────────────────────────

    def _bootstrap(self) -> None:
        """Create tables/indexes and run incremental migrations."""
        with self._lock:
            self._conn.executescript(_SCHEMA)
            cur = self._conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            )
            row = cur.fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                    (_SCHEMA_VERSION,),
                )
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._conn.close()

    # ── Write: remember / forget / wipe ─────────────────────────────────────

    def remember(
        self,
        content: str,
        category: str = "fact",
        importance: int = 1,
    ) -> int:
        """
        Store a memory. Returns its id.

        An exact duplicate (same content, still active) is updated instead of
        duplicated, so "remember X" twice never creates two rows.
        """
        content = _clean(content)
        if not content:
            raise ValueError("Cannot remember empty content.")

        with self._lock:
            cur = self._conn.execute(
                "SELECT id FROM memories WHERE content = ? AND active = 1 LIMIT 1",
                (content,),
            )
            row = cur.fetchone()
            if row is not None:
                self._conn.execute(
                    "UPDATE memories SET category = ?, importance = ?,"
                    " updated_at = datetime('now') WHERE id = ?",
                    (category, importance, row["id"]),
                )
                self._conn.commit()
                return row["id"]

            cur = self._conn.execute(
                "INSERT INTO memories (content, category, importance)"
                " VALUES (?, ?, ?)",
                (content, category, importance),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def forget(
        self,
        memory_id: Optional[int] = None,
        text: Optional[str] = None,
    ) -> bool:
        """
        Soft-delete a memory by id or by fuzzy text match.

        Deletion is `active = 0`, never a hard DELETE — safe and reversible.
        """
        with self._lock:
            if memory_id is not None:
                cur = self._conn.execute(
                    "UPDATE memories SET active = 0 WHERE id = ? AND active = 1",
                    (memory_id,),
                )
                self._conn.commit()
                return cur.rowcount > 0

            if text:
                target = _clean(text)
                # Exact match first, then substring; prefer most important row.
                cur = self._conn.execute(
                    "SELECT id FROM memories WHERE content = ? AND active = 1"
                    " ORDER BY importance DESC LIMIT 1",
                    (target,),
                )
                row = cur.fetchone()
                if row is None:
                    like = f"%{target}%"
                    cur = self._conn.execute(
                        "SELECT id FROM memories WHERE content LIKE ? AND active = 1"
                        " ORDER BY importance DESC LIMIT 1",
                        (like,),
                    )
                    row = cur.fetchone()
                if row is None:
                    return False
                cur = self._conn.execute(
                    "UPDATE memories SET active = 0 WHERE id = ?",
                    (row["id"],),
                )
                self._conn.commit()
                return cur.rowcount > 0

            return False

    def wipe(self) -> int:
        """Forget EVERYTHING (soft-delete all active memories)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE memories SET active = 0 WHERE active = 1"
            )
            self._conn.commit()
            return cur.rowcount

    # ── Read: recall / all / stats ──────────────────────────────────────────

    def recall(
        self,
        query: str = "",
        limit: Optional[int] = None,
        categories: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the most relevant active memories.

        Uses FTS5 keyword matching ranked by bm25, then importance and recency.
        An empty query returns the most important/recent memories.
        Recall bumps `use_count` / `last_used_at` (recency signal).
        """
        limit = limit or settings.memory_recall_limit
        terms = _fts_terms(query)

        if not terms:
            return self.all(active_only=True, limit=limit, categories=categories)

        with self._lock:
            sql = (
                "SELECT " + _MEMORY_COLUMNS + ", bm25(memories_fts) AS rank"
                " FROM memories_fts"
                " JOIN memories m ON m.id = memories_fts.rowid"
                " WHERE memories_fts MATCH ? AND m.active = 1"
            )
            params: list[Any] = [_fts_match_expr(query)]
            if categories:
                placeholders = ",".join("?" for _ in categories)
                sql += f" AND m.category IN ({placeholders})"
                params.extend(categories)
            sql += (
                " ORDER BY m.importance DESC, bm25(memories_fts),"
                " COALESCE(m.last_used_at, '') DESC LIMIT ?"
            )
            params.append(limit)

            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                # Malformed MATCH for exotic input — degrade to substring scan.
                return self.all(active_only=True, limit=limit, categories=categories)

            results = [dict(r) for r in rows]
            self._bump_usage([r["id"] for r in results])
            return results

    def all(
        self,
        active_only: bool = True,
        limit: Optional[int] = None,
        categories: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """List memories ordered by importance, then recency. Pure read."""
        with self._lock:
            sql = "SELECT " + _MEMORY_COLUMNS + " FROM memories m WHERE 1=1"
            params: list[Any] = []
            if active_only:
                sql += " AND m.active = 1"
            if categories:
                placeholders = ",".join("?" for _ in categories)
                sql += f" AND m.category IN ({placeholders})"
                params.extend(categories)
            sql += (
                " ORDER BY m.active ASC, m.importance DESC,"
                " COALESCE(m.last_used_at, '') DESC, m.created_at DESC"
            )
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Return memory counts: total active + per-category breakdown."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS total FROM memories WHERE active = 1"
            )
            total = cur.fetchone()["total"]
            cur = self._conn.execute(
                "SELECT category, COUNT(*) AS n FROM memories WHERE active = 1"
                " GROUP BY category ORDER BY n DESC"
            )
            by_category = {r["category"]: r["n"] for r in cur.fetchall()}
            return {"total": total, "by_category": by_category}

    # ── Internal helpers ────────────────────────────────────────────────────

    def _bump_usage(self, memory_ids: list[int]) -> None:
        """Update recency signals for recalled memories."""
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        self._conn.execute(
            "UPDATE memories SET use_count = use_count + 1,"
            " last_used_at = datetime('now') WHERE id IN (" + placeholders + ")",
            memory_ids,
        )
        self._conn.commit()
