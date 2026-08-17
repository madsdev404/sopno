"""
sopno/llm/researcher_index.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Persistent vector index for the researcher (RAG) pipeline.

Stores research chunks in sqlite-vec inside the existing memory.db,
with a hybrid retrieval score (semantic cosine + keyword overlap).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from sopno.config.settings import settings

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "of", "for", "to", "in", "on", "at", "by", "with",
    "from", "as", "into", "about", "what", "how", "why", "who", "when",
    "where", "which", "this", "that", "these", "those", "it", "its", "do",
    "does", "did", "can", "could", "will", "would", "should", "i", "you",
    "we", "they", "he", "she", "me", "my", "your", "tell", "explain",
    "mean", "means", "not", "no", "has", "have", "had", "if", "than", "then",
}


# ── Helpers (also used by researcher.py and memory/semantic.py) ───────────────

def normalize(vector: list[float]) -> list[float]:
    """Return a unit vector (cosine metric requires unit vectors)."""
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def cosine_from_l2(distance: float) -> float:
    """Convert an L2 distance between two unit vectors to cosine similarity."""
    return max(-1.0, min(1.0, 1.0 - (distance * distance) / 2.0))


def _query_terms(question: str) -> list[str]:
    """Extract meaningful keyword terms from a question for hybrid scoring."""
    return [
        t for t in re.findall(r"[a-zA-Z\u0980-\u09FF]+", question.lower())
        if len(t) >= 3 and t not in _STOPWORDS
    ][:12]


# ── Vector index schema ──────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_docs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    url        TEXT NOT NULL,
    title      TEXT,
    text       TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_research_docs_url ON research_docs(url);

CREATE VIRTUAL TABLE IF NOT EXISTS research_vec USING vec0(
    embedding float[768],
    run_id INTEGER
);
"""


class ResearchIndex:
    """
    Persistent, thread-safe store of research chunks in the Sopno memory.db.

    Chunks are kept forever (so repeat questions reuse cached page text), but
    every query only retrieves within its own ``run_id`` — stale content from
    other topics can never pollute an answer.
    """

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.memory_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            from sqlite_vec import load
        except Exception:
            self._conn.close()
            raise RuntimeError("sqlite-vec is not installed (pip install sqlite-vec).")
        load(self._conn)
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── write ──────────────────────────────────────────────────────────────

    def add_chunks(self, run_id: int, chunks: list[dict[str, Any]]) -> int:
        """
        Insert chunks. Each chunk: {"url", "title", "text", "embedding"}.
        Returns the number of chunks inserted.
        """
        if not chunks:
            return 0
        count = 0
        with self._lock:
            for c in chunks:
                cur = self._conn.execute(
                    "INSERT INTO research_docs (run_id, url, title, text)"
                    " VALUES (?, ?, ?, ?)",
                    (run_id, c["url"], c.get("title"), c["text"]),
                )
                doc_id = int(cur.lastrowid)
                self._conn.execute(
                    "INSERT INTO research_vec (rowid, embedding, run_id)"
                    " VALUES (?, ?, ?)",
                    (doc_id, json.dumps(c["embedding"]), run_id),
                )
                count += 1
            self._conn.commit()
        return count

    def cached_text(self, url: str) -> str:
        """Return previously fetched page text for a URL, or '' if not cached."""
        with self._lock:
            row = self._conn.execute(
                "SELECT text FROM research_docs WHERE url = ?"
                " ORDER BY fetched_at DESC LIMIT 1",
                (url,),
            ).fetchone()
        return row["text"] if row else ""

    # ── read ───────────────────────────────────────────────────────────────

    def search(
        self,
        run_id: int,
        query_embedding: list[float],
        question: str = "",
        k: int = 6,
    ) -> list[dict]:
        """
        Retrieve the top-k passages for a query within a run, ranked by a
        hybrid score (semantic cosine + keyword overlap).
        """
        qvec = json.dumps(normalize(query_embedding))
        q_terms = _query_terms(question)
        with self._lock:
            rows = self._conn.execute(
                "SELECT rowid, run_id, distance FROM research_vec"
                " WHERE embedding MATCH ? AND run_id = ? AND k = ?",
                (qvec, run_id, max(k * 4, 20)),
            ).fetchall()
            docs = {
                int(r["id"]): dict(r)
                for r in self._conn.execute(
                    "SELECT id, url, title, text FROM research_docs WHERE run_id = ?",
                    (run_id,),
                ).fetchall()
            }

        scored: list[dict] = []
        for row in rows:
            doc = docs.get(int(row["rowid"]))
            if not doc:
                continue
            cosine = cosine_from_l2(float(row["distance"]))
            kw = self._keyword_overlap(q_terms, doc["text"])
            score = 0.7 * cosine + 0.3 * kw
            scored.append({
                "url": doc["url"],
                "title": doc.get("title"),
                "text": doc["text"],
                "score": score,
            })
        scored.sort(key=lambda d: d["score"], reverse=True)
        return scored[:k]

    def clear(self, run_id: Optional[int] = None) -> int:
        """Delete research rows (optionally just one run). Return docs removed."""
        with self._lock:
            if run_id is None:
                self._conn.execute("DELETE FROM research_vec")
                cur = self._conn.execute("DELETE FROM research_docs")
            else:
                ids = self._conn.execute(
                    "SELECT id FROM research_docs WHERE run_id = ?", (run_id,)
                ).fetchall()
                ids = [r["id"] for r in ids]
                if ids:
                    ph = ",".join("?" for _ in ids)
                    self._conn.execute(f"DELETE FROM research_vec WHERE rowid IN ({ph})", ids)
                cur = self._conn.execute(
                    "DELETE FROM research_docs WHERE run_id = ?", (run_id,)
                )
            self._conn.commit()
            return cur.rowcount

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _keyword_overlap(terms: list[str], text: str) -> float:
        if not terms:
            return 0.0
        lower = text.lower()
        found = sum(1 for t in terms if t in lower)
        return found / len(terms)
