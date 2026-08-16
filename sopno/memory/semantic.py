"""
sopno/memory/semantic.py
━━━━━━━━━━━━━━━━━━━━━━━━
Semantic (vector) layer on top of the SQLite memory store.

Backed by a ``vec0`` virtual table (sqlite-vec) holding the embedding of each
memory, computed with the same local Ollama model the researcher uses
(``nomic-embed-text``, 768-dim). Recall can then find memories by *meaning*
instead of by keyword alone.

Everything degrades gracefully: if the embed model, sqlite-vec, or the
dimensions don't match, the vector path is skipped and memory keeps working
through the FTS5 keyword path.
"""

from __future__ import annotations

import json
import sqlite3
import threading

from sopno.config.settings import settings
from sopno.llm.researcher import cosine_from_l2, embed_texts

# vec0 table, keyed by the memory rowid (one vector per memory).
_VEC_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
    embedding float[768]
);
"""

# nomic-embed-text stores 768-dim unit vectors.
_VEC_DIM = 768

# Below this cosine similarity a memory is "not about" the query.
_MIN_COSINE = 0.4


def _store_vector(conn: sqlite3.Connection, memory_id: int, content: str) -> bool:
    """Embed ``content`` and store its vector for ``memory_id``. Best-effort."""
    try:
        emb = embed_texts([content])[0]
    except Exception:  # noqa: BLE001 — Ollama down / model missing
        return False
    if len(emb) != _VEC_DIM:
        return False
    if max(abs(x) for x in emb) < 1e-9:
        return False  # degenerate zero vector would match everything
    try:
        conn.execute(
            "INSERT INTO memory_vectors (rowid, embedding) VALUES (?, ?)",
            (memory_id, json.dumps(emb)),
        )
        conn.commit()
        return True
    except Exception:  # noqa: BLE001
        return False


def query_embedding(conn: sqlite3.Connection, query: str, k: int) -> list[tuple[int, float]]:
    """
    Semantic candidates for ``query`` as ``[(memory_id, cosine), ...]``.

    Returns the top-k memories whose embedding is close to the query's, above
    ``_MIN_COSINE``. Best-effort — an empty list on any failure.
    """
    try:
        qvec = embed_texts([query])[0]
    except Exception:  # noqa: BLE001
        return []
    if len(qvec) != _VEC_DIM:
        return []
    try:
        rows = conn.execute(
            "SELECT rowid, distance FROM memory_vectors"
            " WHERE embedding MATCH ? AND k = ?",
            (json.dumps(qvec), k),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    results: list[tuple[int, float]] = []
    for row in rows:
        cosine = cosine_from_l2(float(row["distance"]))
        if cosine >= _MIN_COSINE:
            results.append((int(row["rowid"]), cosine))
    results.sort(key=lambda r: r[1], reverse=True)
    return results


def available(conn: sqlite3.Connection) -> bool:
    """True if sqlite-vec is loaded and the vec0 table exists."""
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_vectors'"
        ).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def enabled() -> bool:
    return bool(getattr(settings, "semantic_memory_enabled", True))


def recall_limit() -> int:
    return max(1, int(getattr(settings, "semantic_recall_limit", 4)))


def create_vec_table(conn: sqlite3.Connection) -> bool:
    """Load sqlite-vec and create the vec0 table. Best-effort."""
    if not enabled():
        return False
    try:
        from sqlite_vec import load
    except Exception:  # noqa: BLE001 — extension not installed
        return False
    try:
        load(conn)
        conn.executescript(_VEC_SCHEMA)
        conn.commit()
        return True
    except Exception:  # noqa: BLE001
        return False
