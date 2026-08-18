"""
sopno/tools/builtins/web/search.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Web tools — real internet access.

  - web_search   → structured results (title, url, snippet) merged from
                   Bing (scraped) and DuckDuckGo (ddgs) — both free, no keys
  - search_web   → spoken wrapper around web_search (the registered tool)
  - fetch_page_text → download a URL and return readable text (trafilatura
                   preferred, stdlib HTMLParser fallback)
  - fetch_url    → spoken wrapper around fetch_page_text (the registered tool)

Parsing uses only the standard library; page extraction prefers the free
``trafilatura`` package and degrades to stdlib HTMLParser if it is absent.
"""

import base64
import html
import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
)
_TIMEOUT_S = 15
_MAX_FETCH_CHARS = 8000

# Detect if a query contains Bengali (Bangla) script or is about Bengali content.
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")  # Bengali Unicode block
_BENGALI_TOPIC_RE = re.compile(
    r"\b(?:bangla|bengali|বাংলা|রোমান্টিক|কবিতা|poem|poetry|song|"
    r"gazal|ghazal|shairi|kobita)\b", re.I
)


# ── HTML → text helpers ──────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Strip tags and collect readable text from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip: str = ""  # "script" | "style" | ""  → drop non-visible blocks

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("script", "style"):
            self._skip = tag
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "blockquote"):
            self._parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag == self._skip:
            self._skip = ""

    def handle_data(self, data) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self._parts.append(text + " ")

    def text(self) -> str:
        return " ".join("".join(self._parts).split())


def extract_text(html: str) -> str:
    """Return readable text from raw HTML (stdlib fallback)."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return ""
    return parser.text()


def extract_text_rich(raw_html: str) -> str:
    """
    Return clean, boilerplate-free text from raw HTML.

    Uses trafilatura when installed (best-in-class for articles/news); falls
    back to the stdlib parser otherwise.
    """
    try:
        import trafilatura
    except Exception:
        return extract_text(raw_html)
    try:
        text = trafilatura.extract(
            raw_html,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
    except Exception:
        text = None
    if not (text or "").strip():
        return extract_text(raw_html)
    return " ".join(text.split())


# ── Bing parsing ─────────────────────────────────────────────────────────────

class _BingParser(HTMLParser):
    """Parse Bing search result pages (``li.b_algo`` entries)."""

    def __init__(self, max_results: int) -> None:
        super().__init__()
        self.results: list[tuple[str, str, str]] = []
        self._depth = 0            # nesting depth inside li.b_algo
        self._in_anchor = False
        self._in_p = 0
        self._anchor_text: list[str] = []
        self._p_text: list[str] = []
        self._title = ""
        self._url = ""

    def handle_starttag(self, tag, attrs) -> None:
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "li" and "b_algo" in classes:
            self._depth += 1
            self._title = ""
            self._url = ""
        if self._depth:
            if tag == "a" and not self._url and attrs.get("href"):
                self._in_anchor = True
                self._anchor_text = []
                self._href = attrs["href"]
            elif tag == "p":
                self._in_p += 1
                self._p_text = []

    def handle_data(self, data) -> None:
        if self._in_anchor:
            self._anchor_text.append(data)
        elif self._in_p:
            self._p_text.append(data)

    def handle_endtag(self, tag) -> None:
        if tag == "a" and self._in_anchor:
            self._in_anchor = False
            title = self._clean_title("".join(self._anchor_text))
            if title and not self._url:
                self._title = title
                self._url = _bing_real_url(self._href)
        elif tag == "p" and self._in_p:
            self._in_p -= 1
            if self._in_p == 0 and self._url:
                snippet = " ".join("".join(self._p_text).split()).strip()
                self.results.append((self._title, self._url, snippet))
        elif tag == "li" and self._depth:
            self._depth -= 1

    @staticmethod
    def _clean_title(raw: str) -> str:
        """Bing injects the cite URL into the title anchor; drop it."""
        text = " ".join(raw.split()).strip()
        cut = re.search(r"https?://", text)
        return text[: cut.start()].strip() if cut else text


def _bing_real_url(href: str) -> str:
    """Bing wraps result URLs in /ck/a?...&u=<base64>; unwrap them."""
    if "/ck/a" not in href:
        return href
    token = (parse_qs(urlparse(href).query).get("u") or [""])[0]
    if not token:
        return href
    if token.startswith("a1"):
        token = token[2:]
    try:
        padding = "=" * (-len(token) % 4)
        return base64.b64decode(token + padding, altchars=b"-_").decode("utf-8", "ignore")
    except Exception:
        return href


# ── Engines ──────────────────────────────────────────────────────────────────

def _is_bengali_query(query: str) -> bool:
    """True if the query contains Bengali script or is about Bengali content."""
    return bool(_BENGALI_RE.search(query) or _BENGALI_TOPIC_RE.search(query))


def _bing_results(query: str, max_results: int) -> list[dict]:
    is_bn = _is_bengali_query(query)
    accept_lang = "bn-BD,bn;q=0.9,en-US;q=0.8,en;q=0.7" if is_bn else "en-US,en;q=0.9"
    resp = requests.get(
        "https://www.bing.com/search",
        params={"q": query},
        headers={"User-Agent": USER_AGENT, "Accept-Language": accept_lang},
        timeout=_TIMEOUT_S,
    )
    resp.raise_for_status()
    parser = _BingParser(max_results)
    parser.feed(resp.text)

    # Filter out low-quality dictionary/definition sidebar results
    _LOW_QUALITY_HOSTS = {
        "merriam-webster.com", "cambridge.org", "dictionary.com",
        "longdo.com", "oxfordlearnersdictionaries.com", "collinsdictionary.com",
        "vocabulary.com", "freedictionary.com",
    }
    filtered = []
    for title, url, snippet in parser.results[:max_results * 2]:
        try:
            from urllib.parse import urlparse as _urlparse
            host = _urlparse(url).hostname or ""
            if any(h in host for h in _LOW_QUALITY_HOSTS):
                continue
        except Exception:
            pass
        filtered.append({"title": title, "url": url, "snippet": snippet})
        if len(filtered) >= max_results:
            break
    return filtered[:max_results]


def _ddg_results(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    kwargs: dict = {"max_results": max_results, "safesearch": "moderate"}
    if _is_bengali_query(query):
        kwargs["region"] = "bd-bd"
    with DDGS() as ddgs:
        results = list(ddgs.text(query, **kwargs))
    out: list[dict] = []
    for r in results or []:
        title = html.unescape(str(r.get("title") or "")).strip()
        url = str(r.get("href") or "").strip()
        snippet = html.unescape(str(r.get("body") or "")).strip()
        if title and url:
            out.append({"title": title, "url": url, "snippet": snippet})
    return out[:max_results]


def web_search(
    query: str,
    max_results: int = 5,
    engines: tuple[str, ...] = ("ddg", "bing"),
) -> list[dict]:
    """
    Search the web across free engines and return merged, deduplicated results.

    Args:
        query: The search query string.
        max_results: How many results to keep (1-10).
        engines: Which engines to try, in order ("bing", "ddg").

    Returns:
        List of {"title", "url", "snippet"} dicts, URL-deduplicated.
    """
    query = (query or "").strip()
    if not query:
        return []
    max_results = max(1, min(int(max_results), 10))

    merged: list[dict] = []
    seen: set[str] = set()
    per_engine = max(2, max_results)

    for engine in engines:
        try:
            if engine == "bing":
                results = _bing_results(query, per_engine)
            elif engine == "ddg":
                results = _ddg_results(query, per_engine)
            else:
                continue
        except Exception:
            continue
        for r in results:
            url = r["url"]
            if url in seen:
                continue
            seen.add(url)
            merged.append(r)
        if len(merged) >= max_results:
            break

    return merged[:max_results]


def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the web and return the top matching results.

    Args:
        query: The web search query string.
        max_results: How many results to return (1-10).

    Returns:
        A numbered list of titles, URLs, and snippets, or an error message.
    """
    query = (query or "").strip()
    if not query:
        return "Please provide a search query."

    results = web_search(query, max_results=max_results)
    if not results:
        return f"I couldn't find any results for {query}."

    lines = [f"Top {len(results)} results for {query}:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}. {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
    return "\n".join(lines)


# ── Page fetching ────────────────────────────────────────────────────────────

def fetch_page_text(url: str, max_chars: Optional[int] = None) -> str:
    """
    Download a URL and return its readable text.

    Args:
        url: The URL to fetch (http/https). A bare domain is accepted.
        max_chars: Optional truncation limit.

    Returns:
        The page's clean text, or an empty string on any failure.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
    except Exception:
        return ""

    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()

    if content_type in ("application/json", "text/plain", "application/rss+xml",
                        "application/atom+xml", "application/xml", "text/xml"):
        text = resp.text.strip()
    else:
        text = extract_text_rich(resp.text)

    if not text:
        return ""
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


def fetch_url(url: str) -> str:
    """
    Download a URL and return its content as readable text.

    Args:
        url: The URL to fetch (http/https). A bare domain is also accepted.

    Returns:
        The page's readable text (truncated) or an error message.
    """
    url = (url or "").strip()
    if not url:
        return "Please provide a URL to fetch."

    text = fetch_page_text(url, max_chars=_MAX_FETCH_CHARS)
    if not text:
        return f"Could not fetch readable content from {url}."
    return text
