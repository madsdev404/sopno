"""
sopno/tools/builtins/search.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Web tools — real internet access.

  - search_web  → run a web search and return the top results (title, url, snippet)
  - fetch_url   → download a URL and return its readable text / content

Both use only the standard library for parsing, so no extra dependency
beyond ``requests`` is required.
"""

import base64
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
)
_TIMEOUT_S = 15
_MAX_FETCH_CHARS = 8000
_MAX_SEARCH_RESULTS = 5


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


class _BingParser(HTMLParser):
    """Parse Bing search result pages (``li.b_algo`` entries)."""

    def __init__(self, max_results: int) -> None:
        super().__init__()
        self._max = max_results
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


def extract_text(html: str) -> str:
    """Return the readable text of an HTML document, whitespace-normalized."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return ""
    return parser.text()


# ── Tools ────────────────────────────────────────────────────────────────────

def search_web(query: str, max_results: int = _MAX_SEARCH_RESULTS) -> str:
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
    max_results = max(1, min(int(max_results or _MAX_SEARCH_RESULTS), 10))

    try:
        resp = requests.get(
            "https://www.bing.com/search",
            params={"q": query},
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
    except Exception as e:
        return f"Web search failed: {e}"

    parser = _BingParser(max_results)
    parser.feed(resp.text)

    results = parser.results[:max_results]
    if not results:
        return f"I couldn't find any results for {query}."

    lines = [f"Top {len(results)} results for {query}:"]
    for i, (title, url, snippet) in enumerate(results, 1):
        lines.append(f"{i}. {title}. {url}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


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
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
    except Exception as e:
        return f"Could not fetch {url}: {e}"

    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()

    # Plain text / JSON / feeds → return raw body; HTML → extract readable text
    if content_type in ("application/json", "text/plain", "application/rss+xml",
                        "application/atom+xml", "application/xml", "text/xml"):
        text = resp.text.strip()
    else:
        text = extract_text(resp.text)

    if not text:
        return f"The page at {url} had no readable text."
    if len(text) > _MAX_FETCH_CHARS:
        text = text[:_MAX_FETCH_CHARS] + "…"
    return text
