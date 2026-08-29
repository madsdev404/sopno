"""
sopno/llm/researcher.py
━━━━━━━━━━━━━━━━━━━━━━━━
Researcher (RAG) pipeline — turns a question into a cited answer.

Pipeline (all free / local, no API keys):
    question → search (Bing + DuckDuckGo) → fetch pages (trafilatura) →
    chunk → embed (Ollama nomic-embed-text) → index (sqlite-vec inside the
    existing memory.db) → retrieve top-k by hybrid score → summarize with the
    local LLM → cited answer.

Usage:
    from sopno.llm.researcher import research
    answer = research("What is the latest Linux kernel release?")
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests

from sopno.config.settings import settings
from sopno.llm.researcher_index import (  # noqa: F401 – public re-exports
    ResearchIndex,
    normalize,
    cosine_from_l2,
    _query_terms,
)

_OLLAMA_BASE = "http://localhost:11434"
_EMBED_URL = f"{_OLLAMA_BASE}/api/embed"
_CHAT_URL = f"{_OLLAMA_BASE}/api/chat"

# nomic-embed-text task prefixes improve retrieval quality (per Nomic docs).
_QUERY_PREFIX = "search_query: "
_DOC_PREFIX = "search_document: "


# ── Embedding (Ollama) ───────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts with Ollama's nomic-embed-text.

    Returns a list of unit vectors (one per input text).
    Raises RuntimeError if the embed model is unreachable.
    """
    if not texts:
        return []
    try:
        resp = requests.post(
            _EMBED_URL,
            json={
                "model": settings.research_embed_model,
                "input": texts,
                "options": {"num_ctx": settings.research_chunk_chars + 512},
            },
            timeout=180,
        )
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
    except Exception as e:
        raise RuntimeError(
            f"Embedding failed (is '{settings.research_embed_model}' pulled "
            f"in Ollama? `ollama pull {settings.research_embed_model}`): {e}"
        )
    if len(embeddings) != len(texts):
        raise RuntimeError("Ollama returned a mismatched number of embeddings.")
    return [normalize(v) for v in embeddings]


# ── Chunking ─────────────────────────────────────────────────────────────────

def chunk_text(text: str, max_chars: int = 1800, overlap: int = 120) -> list[str]:
    """
    Split text into overlapping chunks at sentence boundaries.

    Chunks break on ". ", "? ", "! " near the size limit so a single thought is
    rarely cut in half; a small overlap keeps boundary-straddling context.
    """
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    cut = -1
    for sep in (". ", "? ", "! "):
        pos = text.rfind(sep, max_chars // 2, max_chars)
        if pos > cut:
            cut = pos
    if cut == -1:
        cut = text.rfind(" ", max_chars // 2, max_chars)
    if cut == -1:
        cut = max_chars

    chunk = text[: cut + 2].strip()
    rest = chunk[-overlap:] + text[cut + 2:]
    return [chunk] + chunk_text(rest, max_chars, overlap)


# ── Query rewriting ──────────────────────────────────────────────────────────

# Words that, when leading a search query, push engines into "news mode" and
# return generic portal pages (e.g. "latest version X" → spam news aggregators).
_FUNCTION_WORDS = {
    "latest", "news", "new", "update", "updates", "current", "now", "today",
    "version", "versions", "release", "releases", "whats", "info",
    "information", "status", "statuses", "best", "top", "recent", "trending",
}


def _research_query(question: str) -> str:
    """
    Turn a question into a subject-first search query.

    Engines return junk portals for queries that lead with words like "latest"
    ("latest version python" → news aggregators), but lead with the subject and
    they return the real pages. So order content terms subject-first.
    """
    terms = _query_terms(question)
    if not terms:
        return question
    head = next((t for t in terms if t not in _FUNCTION_WORDS), terms[0])
    rest = [t for t in terms if t != head]
    return " ".join([head] + rest)


# ── Search + fetch ───────────────────────────────────────────────────────────

def _fetch_pages(results: list[dict], max_pages: int, index: ResearchIndex) -> list[dict]:
    """Fetch page texts in parallel, reusing cached text where possible."""
    from sopno.tools.builtins.web.search import fetch_page_text

    def one(r: dict) -> Optional[dict]:
        url = r["url"]
        cached = index.cached_text(url)
        text = cached if len(cached) > 500 else fetch_page_text(
            url, max_chars=settings.research_page_chars
        )
        if not text:
            return None
        return {"url": url, "title": r.get("title"), "text": text}

    with ThreadPoolExecutor(max_workers=min(4, max_pages)) as pool:
        fetched = [f.result() for f in [pool.submit(one, r) for r in results]]
    return [d for d in fetched if d][:max_pages]


# ── Summarize ────────────────────────────────────────────────────────────────

def _summarize(question: str, passages: list[dict]) -> str:
    """Ask the local LLM to write a concise, cited answer from the passages."""
    numbered = []
    for i, p in enumerate(passages, 1):
        text = p["text"]
        if len(text) > 1400:
            text = text[:1400].rsplit(" ", 1)[0] + "…"
        title = p.get("title") or p["url"]
        numbered.append(f"[{i}] {title} — {p['url']}\n{text}")

    system = (
        "You are Sopno's researcher. Answer the user's question using ONLY the "
        "provided passages. Be factual, specific, and complete. Cite supporting "
        "passages inline as [1], [2], etc. After the answer, list 'Sources:' "
        "with the numbered URLs. If the passages don't contain the answer, say "
        "that clearly instead of guessing."
    )
    user = f"Question: {question}\n\nPassages:\n\n" + "\n\n".join(numbered)

    # Deep research inherits the active reasoning mode's thinking budget
    # (doc/roadmap/thinking-modes.md §5.3).
    from sopno.llm import modes
    resolved = modes.resolve(
        getattr(settings, "llm_mode", "auto"),
        question,
    )

    try:
        resp = requests.post(
            _CHAT_URL,
            json={
                "model": settings.model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "think": bool(resolved["think"]),
                "options": {
                    "num_ctx": max(settings.research_summary_ctx, resolved["num_ctx"]),
                    "num_predict": max(settings.research_summary_tokens, resolved["num_predict"]),
                    "temperature": 0.3,
                },
            },
            timeout=300,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
    except Exception as e:
        # Degrade gracefully: return the raw top passages so the caller can
        # still give the user something useful.
        raw = "\n\n".join(
            f"{p.get('title') or 'Untitled'} ({p['url']}): {p['text'][:400]}"
            for p in passages
        )
        return f"Summarization failed ({e}). Here are the most relevant passages:\n\n{raw}"
    return content.strip()


# ── Public API ───────────────────────────────────────────────────────────────

def research(query: str, max_pages: Optional[int] = None) -> str:
    """
    Research a question on the web and return a cited answer.

    Args:
        query: The research question (English or Bangla).
        max_pages: How many web pages to read (default from settings, 1-10).

    Returns:
        A concise, cited answer string, or a helpful error message.
    """
    question = (query or "").strip()
    if not question:
        return "Please provide a research question."
    max_pages = max(1, min(int(max_pages or settings.research_max_pages), 10))

    # 1. Search the web (free engines).
    from sopno.tools.builtins.web.search import web_search

    try:
        results = web_search(
            _research_query(question),
            max_results=settings.research_max_pages + 2,
        )
    except Exception as e:
        return f"Research search failed: {e}"
    if not results:
        return f"I couldn't find anything about {question} on the web."

    # 2. Fetch the top pages (cached text reused).
    index = ResearchIndex()
    try:
        docs = _fetch_pages(results, max_pages, index)
        if not docs:
            return "I found pages but couldn't read their content."
        run_id = int(time.monotonic() * 1_000_000)  # unique per run

        # 3. Chunk.
        chunks: list[dict] = []
        for d in docs:
            for piece in chunk_text(
                d["text"],
                max_chars=settings.research_chunk_chars,
                overlap=120,
            ):
                chunks.append({
                    "url": d["url"],
                    "title": d["title"],
                    "text": piece,
                })

        # 4. Embed chunks + question.
        embeddings = embed_texts(
            [_DOC_PREFIX + c["text"] for c in chunks]
        )
        for c, emb in zip(chunks, embeddings):
            c["embedding"] = emb
        question_emb = embed_texts([_QUERY_PREFIX + question])[0]

        # 5. Index + retrieve.
        index.add_chunks(run_id, chunks)
        passages = index.search(
            run_id,
            question_emb,
            question=question,
            k=settings.research_top_k,
        )
    finally:
        index.close()

    if not passages:
        return f"I searched but couldn't find useful passages about {question}."

    # 6. Summarize.
    return _summarize(question, passages)
