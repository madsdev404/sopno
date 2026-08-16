"""
sopno/tools/builtins/browser.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Browser automation via Playwright — optional and opt-in.

Playwright is a heavy dependency (``pip install playwright`` then
``playwright install chromium`` once), so everything here is lazy and
best-effort: if the package isn't installed, or ``browser_enabled`` is false,
the tools reply with a friendly message instead of failing. One browser session
is shared across a conversation ("lazy singleton"); ``browser_close()`` tears
it down and ``set_browser`` swaps it (tests / future multi-session support).

Security model (implementation-plan §5):
- Navigation is restricted to ``browser_allowed_domains`` — deny-by-default.
- Each step obeys ``browser_timeout``; the whole session expires after
  ``browser_task_limit`` seconds.
- ``image/media/font`` requests are blocked (token/bandwidth savings).
- Screenshots only write inside the file write-roots (``files._authorize``) and
  ask for confirmation when overwriting an existing file.
- Page content is treated as untrusted — Sopno never follows page instructions.

The LLM gets a cheap **text snapshot** (title + body + indexed interactive
elements) instead of vision/screenshots; ``browser_click(selector, index)``
targets elements by snapshot index.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from sopno.config.settings import settings
from sopno.tools.builtins import files

# Element kinds that make up the indexed interactive-elements snapshot.
_INTERACTIVE = (
    "button, a, input, select, textarea, "
    "[role=button], [role=link], [role=menuitem], [role=tab], summary"
)
_BLOCKED_RESOURCE_TYPES = ("image", "media", "font")

_SNAPSHOT_CHARS = 6000
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_SESSION: Optional["BrowserSession"] = None


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _domain_allowed(url: str) -> bool:
    host = _host_of(url)
    if not host:
        return False
    allowed = [
        str(d).strip().lower().lstrip(".")
        for d in getattr(settings, "browser_allowed_domains", [])
        if d and str(d).strip()
    ]
    return any(host == d or host.endswith("." + d) for d in allowed)


def _element_label(el) -> str:
    """Best-effort short label for an interactive element in the snapshot."""
    try:
        text = (el.inner_text() or "").strip().replace("\n", " ")
        if not text:
            text = (el.get_attribute("value") or "").strip()
        if not text:
            text = (el.get_attribute("aria-label") or "").strip()
        if not text:
            text = (el.get_attribute("placeholder") or "").strip()
        if len(text) > 80:
            text = text[:80] + "…"
        return text
    except Exception:  # noqa: BLE001
        return ""


def _snapshot(page, title: str = "") -> str:
    """Build the cheap text snapshot the LLM reasons about."""
    parts = [f"Title: {title}".strip(), "---"]
    try:
        body = page.locator("body").inner_text() or ""
    except Exception:  # noqa: BLE001
        body = ""
    if body:
        parts.append(body)
    elements = []
    try:
        for i, el in enumerate(page.locator(_INTERACTIVE).all()):
            label = _element_label(el)
            if label:
                elements.append(f"[{i}] {label}")
    except Exception:  # noqa: BLE001
        pass
    if elements:
        parts.append("---")
        parts.append("Interactive elements (index → click/type target):")
        parts.extend(elements)
    snapshot = "\n".join(p for p in parts if p).strip()
    if len(snapshot) > _SNAPSHOT_CHARS:
        snapshot = snapshot[:_SNAPSHOT_CHARS] + "\n…(snapshot truncated)…"
    return snapshot or "(no readable content)"


def _cap_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) > _SNAPSHOT_CHARS:
        text = text[:_SNAPSHOT_CHARS] + "\n…(content truncated)…"
    return text or "(no text)"


class BrowserSession:
    """Wraps a Playwright Chromium instance; created lazily on first use."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=getattr(settings, "browser_headless", True),
        )
        self._context = self._browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._context.new_page()
        self._page.route("**/*", self._handle_route)
        self._started_at = time.time()

    def _handle_route(self, route, request) -> None:
        try:
            if request.resource_type in _BLOCKED_RESOURCE_TYPES:
                route.abort()
            else:
                route.continue_()
        except Exception:  # noqa: BLE001
            pass

    def _timeout_ms(self) -> int:
        return max(1, int(getattr(settings, "browser_timeout", 30))) * 1000

    def expired(self) -> bool:
        limit = int(getattr(settings, "browser_task_limit", 120))
        return time.time() - self._started_at > limit

    def navigate(self, url: str) -> str:
        self._page.goto(url, timeout=self._timeout_ms(), wait_until="domcontentloaded")
        return _snapshot(self._page, self._page.title())

    def click(self, selector: str, index: int) -> str:
        if selector:
            locator = self._page.locator(selector).nth(max(0, int(index)))
            label = f"{selector}[{int(index)}]"
        else:
            locator = self._page.locator(_INTERACTIVE).nth(max(0, int(index)))
            label = f"[{int(index)}]"
        locator.click(timeout=self._timeout_ms())
        return "Clicked " + label + " —\n" + _snapshot(self._page, self._page.title())

    def type_text(self, selector: str, text: str) -> str:
        locator = (
            self._page.locator(selector)
            if selector
            else self._page.locator("input:not([type=hidden]), textarea").first
        )
        locator.fill(text, timeout=self._timeout_ms())
        return f"Typed into '{selector or 'first input/textarea'}'."

    def extract(self, selector: str) -> str:
        if selector:
            text = self._page.locator(selector).first.inner_text()
        else:
            text = self._page.locator("body").inner_text()
        return _cap_text(text)

    def screenshot(self, path: str, full_page: bool) -> str:
        self._page.screenshot(path=path, full_page=bool(full_page))
        return str(path)

    def back(self) -> str:
        self._page.go_back(timeout=self._timeout_ms())
        return "Back —\n" + _snapshot(self._page, self._page.title())

    def close(self) -> None:
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:  # noqa: BLE001
            pass


def set_browser(session: Optional[BrowserSession]) -> None:
    """Swap in a browser session (tests / explicit lifecycle control)."""
    global _SESSION
    _SESSION = session


def _check() -> tuple[Optional[BrowserSession], str]:
    """Return (session, refusal) — exactly one non-empty."""
    global _SESSION
    if not getattr(settings, "browser_enabled", False):
        return None, (
            "Browser automation is disabled — set browser_enabled = true in "
            "config.json and add the domains you trust to browser_allowed_domains."
        )
    if _SESSION is None:
        try:
            _SESSION = BrowserSession()
        except Exception as e:  # noqa: BLE001
            return None, (
                f"Could not start the browser ({e}). Make sure Playwright is "
                "installed and Chromium is downloaded "
                "('pip install playwright' + 'playwright install chromium')."
            )
    return _SESSION, ""


def _session_ready() -> tuple[Optional[BrowserSession], str]:
    session, err = _check()
    if err:
        return None, err
    assert session is not None
    if session.expired():
        return None, (
            f"The browser session has run longer than browser_task_limit "
            f"({settings.browser_task_limit}s) — say 'close the browser' "
            "and try again."
        )
    return session, ""


# ── Tools ────────────────────────────────────────────────────────────────────

def browser_navigate(url: str) -> str:
    """
    Open a web page and return a text snapshot (title + content + indexed
    interactive elements) for the LLM to reason about.

    Args:
        url: The URL to open (scheme optional — https is assumed).

    Returns:
        The page snapshot, or a reason it can't be opened.
    """
    session, err = _session_ready()
    if err:
        return err
    url = (url or "").strip()
    if not url:
        return "Which URL should I open?"
    if "://" not in url:
        url = "https://" + url
    if not _domain_allowed(url):
        allowed = ", ".join(getattr(settings, "browser_allowed_domains", [])) or "none"
        return (
            f"I can only browse the domains in browser_allowed_domains "
            f"(currently {allowed}). '{_host_of(url)}' isn't allowed."
        )
    try:
        return session.navigate(url)
    except Exception as e:  # noqa: BLE001
        return f"Could not load {url}: {e}"


def browser_click(selector: str = "", index: int = 0) -> str:
    """
    Click an element on the current page.

    Args:
        selector: Optional CSS selector; when empty, `index` refers to the
            interactive-elements list from the navigation snapshot.
        index: Element index within the selector or snapshot list.

    Returns:
        A new snapshot of the page after the click.
    """
    session, err = _session_ready()
    if err:
        return err
    try:
        return session.click(selector, int(index))
    except Exception as e:  # noqa: BLE001
        return f"Could not click: {e}"


def browser_type(selector: str, text: str) -> str:
    """
    Type into an input/textarea on the current page.

    Args:
        selector: CSS selector (defaults to the first visible input).
        text: The text to type.

    Returns:
        Confirmation text.
    """
    session, err = _session_ready()
    if err:
        return err
    if not text:
        return "What should I type?"
    try:
        return session.type_text(selector, text)
    except Exception as e:  # noqa: BLE001
        return f"Could not type: {e}"


def browser_extract(selector: str = "") -> str:
    """
    Read text from a region of the current page.

    Args:
        selector: CSS selector; empty reads the whole page body.

    Returns:
        The extracted (capped) text.
    """
    session, err = _session_ready()
    if err:
        return err
    try:
        return session.extract(selector)
    except Exception as e:  # noqa: BLE001
        return f"Could not extract: {e}"


def browser_screenshot(path: str, full_page: bool = False) -> str:
    """
    Save a screenshot of the current page as a PNG.

    Args:
        path: Absolute path (must be inside the file write roots).
        full_page: Capture the full scrollable page (default whole viewport).

    Returns:
        Confirmation, or a reason it can't be saved.
    """
    session, err = _session_ready()
    if err:
        return err
    target, err = files._resolve_target(path)
    if err:
        return err
    assert target is not None
    reason = files._authorize(target, "write")
    if reason:
        return reason

    def _do() -> str:
        try:
            session.screenshot(str(target), bool(full_page))
        except Exception as e:  # noqa: BLE001
            return f"Could not take the screenshot: {e}"
        return f"Done — saved the screenshot to {target}."

    if target.is_file() and getattr(settings, "file_confirm_writes", True):
        return files._awaiting_confirmation(f"overwrite '{target}'", _do)
    return _do()


def browser_back() -> str:
    """
    Go back to the previous page.

    Returns:
        A new snapshot of the previous page.
    """
    session, err = _session_ready()
    if err:
        return err
    try:
        return session.back()
    except Exception as e:  # noqa: BLE001
        return f"Could not go back: {e}"


def browser_close() -> str:
    """Close the browser session (frees the heavy Playwright process)."""
    global _SESSION
    if _SESSION is None:
        return "The browser isn't open."
    _SESSION.close()
    _SESSION = None
    return "Done — closed the browser."
