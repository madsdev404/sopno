# 🌐 Sopno — Internet & Researcher (RAG) System

## What we are doing
Today Sopno can *reach* the internet: `search_web` returns a handful of Bing
snippets and `fetch_url` reads a single page as plain text. But that is a peek,
not an answer. Ask "what are the latest developments in X?" and Sopno would
either read one page or paraphrase one or two snippets — it has no way to
**research**: gather many sources, keep the important passages, and compose a
reasoned answer from all of them.

We are building a **Researcher pipeline** (RAG — retrieval-augmented
generation) on top of the web tools:

```
ask a question → search the web → fetch the best pages → chunk + index →
retrieve the most relevant passages → summarize with the local LLM → reply
```

Everything stays **local and CPU-friendly**: embeddings run through the Ollama
instance Sopno already uses, vectors live inside the SQLite memory store Sopno
already has, and the existing LLM (`qwen3:8b`) does the summarizing. This is a
**design & specification document**; implementation will land in
`sopno/llm/` (research pipeline) and `sopno/tools/builtins/` (web upgrades).

---

## Status — implemented

The pipeline is **implemented** in `sopno/llm/researcher.py` and live via the
`research` tool (registry + schema). Verified end-to-end against Ollama
(`nomic-embed-text` embeddings, `qwen3:8b` summarizer) with cited answers.

Implemented vs. the plan below:

- **Baseline (P1)** — done. `research(query)` = search → fetch → chunk →
  embed (`/api/embed`, `num_ctx` raised) → index (`research_docs` +
  `research_vec` vec0 tables in `memory.db`, `sqlite-vec`) → retrieve → summarize.
- **Hybrid retrieval (P3)** — done early: score = 0.7·cosine + 0.3·keyword
  overlap (sqlite-vec 0.1.9 has no cosine metric, so vectors are normalized and
  `cos = 1 − d²/2`). Retrieval is scoped by `run_id`; page text is cached by URL
  across runs.
- **Search upgrades (P2)** — ddgs added as a second free engine (Bing + DDG,
  merged + deduplicated). `web_search()` returns structured results;
  `fetch_page_text()` uses trafilatura with the stdlib parser as fallback.
- **Query rewriting** — questions are rewritten subject-first (e.g. "What is the
  latest version of Python?" → "python latest version") so engines return the
  real pages instead of news-spam portals.
- **Not yet done** — LLM query expansion (2–3 queries), Tavily/Brave API keys,
  reranking, Jina/Playwright for JS-heavy pages, agent promotion (P5).

Tests: `tests/test_researcher.py` + web tests in `tests/test_tools.py`
(75 tests total pass).

---

## Why? (the gap today)

| Today (peek) | With Researcher (answer) |
|---|---|
| `search_web` returns ~5 Bing snippets | Fetches the top pages and reads them in full |
| One page at a time via `fetch_url` | Gathers many pages, keeps the relevant passages |
| No memory of what was searched | Indexed results can be re-queried / cached |
| Answer quality = one model pass over a snippet | Answer grounded in retrieved passages + citations |
| Google-class depth missing | Keyword + semantic retrieval over real page content |

The philosophy stays aligned with Sopno's design: **minimal dependencies,
offline-first, one small pipeline that grows** — no agent frameworks, no hosted
vector databases.

---

## Options evaluated

### 1. RAG framework: build vs adopt

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Custom pipeline (stdlib + Ollama + SQLite)** ✅ | Zero framework deps; fits Sopno's modular monolith; one path we fully control; CPU-first | We write the chunk/embed/search glue (it is small) | **Chosen** — the research flow is ~4 steps; a framework adds more weight than value here |
| **LlamaIndex** | Fastest to a working RAG (~15 lines), best retrieval defaults | 28 core deps, global `Settings` state, thick abstraction; conflicts with Sopno's lean philosophy | Add later *only if* retrieval quality needs deep tuning |
| **LangChain / LangGraph** | Biggest ecosystem, agent orchestration | Heaviest overhead; `langchain-community` is being deprecated | Avoid — overkill for a single research flow |
| **Haystack** | Explicit, debuggable DAG pipelines | Verbose wiring; smaller community | Avoid for now |

### 2. Search layer: free scraping vs paid APIs

| Option | Cost | Pros | Cons | Verdict |
|---|---|---|---|---|
| **Bing scraping (already implemented)** ✅ | Free | Works today, zero key, no signup | Scraper can break; no Google index | **Default** free tier |
| **`duckduckgo-search` (ddgs) package** | Free | Clean package, no key | Same anti-bot fragility as any scraper | Fallback / second engine |
| **Tavily** | $8/1K, 1,000 free/mo | AI-optimized results + extracted content + optional answer in one call | Paid; aggregated index | **Optional upgrade** via config key |
| **Brave Search API** | $5/1K, 2,000 free/mo | Independent non-Google index, high agentic accuracy | Card required for key | Optional |
| **Serper** | $1/1K | Real Google SERP data, cheapest | Snippets only; separate fetch step | Optional |
| **Self-hosted SearXNG** | Your VPS bill | Privacy, multi-engine, unlimited | Run + maintain a server | Later option |

### 3. Embedding model (all via Ollama — no new server)

| Model | Size | Dims | Max tokens | Verdict |
|---|---|---|---|---|
| **`nomic-embed-text`** ✅ | 274 MB | 768 | 8,192 | **Chosen** — best quality/size, fastest serious CPU model, ~8K chunks |
| `qwen3-embedding:0.6b` | 1.2 GB | 1024 | 32K | Upgrade path if retrieval needs more quality |
| `bge-m3` | 1.2 GB | 1024 | 8,192 | Only if multilingual retrieval matters |
| `all-minilm` | 46 MB | 384 | 256 | Too small/truncating for production RAG |

Note: use `POST /api/embed` (batching) and raise `num_ctx` to 8192 —
`nomic-embed-text` silently truncates at its 2K default. Pin with `keep_alive`
to skip ~1.3 s cold starts.

### 4. Vector store

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **`sqlite-vec`** ✅ | SQLite extension; vectors ride in the existing `memory.db`; exact brute-force KNN (<5 ms under ~50k chunks); zero server; one backup file | Linear scan past ~50k vectors; pre-v1 API | **Chosen** — matches the memory store exactly; Sopno's corpus is personal-scale |
| Chroma | Friendliest API, metadata filtering | In-memory index (RAM-bound), 84% default recall, slowest build | Fine for prototypes; unnecessary dep |
| LanceDB | Disk-based, versioned, hybrid search | Extra engine + format to adopt | Overkill for now |

### 5. Page content extraction

| Option | Verdict |
|---|---|
| **stdlib `HTMLParser` (already implemented)** | Keep as the zero-dep base |
| **`trafilatura`** | Add — best-in-class HTML → clean text, handles boilerplate/news well |
| **Jina Reader (`r.jina.ai/<url>`)** | Free no-key fallback that fetches *and* cleans JS-heavy pages |
| **Playwright** | Full JS rendering (Twitter, SPAs) — heavy dep, **later** optional stage |

### 6. Reranking (quality lever)

Cross-encoder reranking lifts retrieval more than swapping embedding models.
`bge-reranker-v2-m3` (via `sentence-transformers`, not in Ollama) is the
standard choice — **optional**, added after the baseline works.

---

## Architecture

```
┌──────────────────────────────  sopno/llm/researcher.py  ──────────────────────────────┐
│                                                                                       │
│  User question ──► 1. EXPAND   LLM rewrites into 2-3 search queries                   │
│                          │                                                             │
│                          ▼                                                             │
│                   2. SEARCH   search_web() per query (Bing now, API key optional)      │
│                          │                                                             │
│                          ▼                                                             │
│                   3. FETCH    top N URLs → fetch_url() (+ trafilatura / Jina fallback) │
│                          │                                                             │
│                          ▼                                                             │
│                   4. INDEX    chunk text → embed via Ollama nomic-embed-text           │
│                              → store vectors in memory.db (sqlite-vec table)           │
│                          │                                                             │
│                          ▼                                                             │
│                   5. RETRIEVE top-k passages (cosine) per question                      │
│                          │                                                             │
│                          ▼                                                             │
│                   6. SUMMARIZE LLM (qwen3:8b) over passages + question → cited answer  │
│                                                                                       │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Where it lives

```
sopno/llm/researcher.py     # the pipeline: research(question) -> str
sopno/llm/__init__.py       # expose research()
sopno/tools/builtins/search.py  # search_web, fetch_url (upgraded extraction)
sopno/tools/schema.py       # new "research" tool schema
sopno/tools/registry.py     # register research
sopno/config/settings.py    # optional: tavily/brave api key, embed model, counts
sopno/memory/store.py       # reuse connection; new vectors table via sqlite-vec
```

### Data flow through the existing assistant

1. User says something research-like (detected by `_TOOLISH` + the LLM choosing
   the `research` tool).
2. `execute_tool("research", {"query": ...})` runs the pipeline above.
3. The tool result (the cited answer) is handed back to the LLM, which shapes it
   into the final spoken reply — no new top-level wiring needed.

---

## Implementation plan

- **P1 — Baseline researcher (no new deps beyond `sqlite-vec` + `trafilatura`):**
  search → fetch → chunk (recursive, ~500 tokens) → embed via Ollama
  `/api/embed` → store in a `research_chunks` table → retrieve top-k by cosine →
  summarize with the existing LLM. Wire `research` into registry/schema.
- **P2 — Search upgrades:** `duckduckgo-search` fallback engine; optional
  Tavily/Brave key in `config.json`; search-result caching.
- **P3 — Quality levers:** `bge-reranker-v2-m3` rerank stage; `num_ctx` +
  `keep_alive` tuning; hybrid keyword+semantic retrieval.
- **P4 — JS-heavy sites:** Jina Reader fallback, then optional Playwright stage.
- **P5 — Agents:** promote the researcher into the multi-agent plan in
  `doc/agen/agent-implementation.md` (Researcher Agent).

## Dependencies to add

```
# requirements.txt additions
sqlite-vec        # vector search inside the existing SQLite memory.db
trafilatura       # high-quality HTML → text extraction
# optional / behind config keys
duckduckgo-search # free second search engine
sentence-transformers  # only when adding the bge reranker (P3)
playwright        # only when adding JS rendering (P4)
```

Plus one-time: `ollama pull nomic-embed-text` (~274 MB).

## Resource quotas

Each research run should respect configurable limits:

- Max pages fetched (default ~5)
- Max chunks embedded / stored per run
- Max passages sent to the LLM (default ~8)
- Max tokens for the final summary
- Result cache TTL so repeated questions don't re-fetch the web

---

## Future

Once working, this becomes the foundation for the **Researcher Agent** in the
multi-agent plan and for the **local knowledge base** (index PDFs/books in
`doc/roadmap/features.md` §36) by swapping the "search the web" stage for
"search the local corpus."
