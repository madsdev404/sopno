"""
tests/test_browser.py
━━━━━━━━━━━━━━━━━━━━
Browser-automation tools, tested against a fake BrowserSession (no Playwright
needed): domain allowlist, gate/disable path, snapshot plumbing, screenshot
permissions + overwrite confirmation, session expiry, and close lifecycle.
"""

import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.tools.builtins import browser as mod
from sopno.tools.builtins import files


class FakeSession:
    """Duck-typed stand-in for BrowserSession."""

    def __init__(self) -> None:
        self.url = None
        self.expired_flag = False
        self.closed = False
        self.clicked = None
        self.typed = None
        self.extracted = None

    def expired(self) -> bool:
        return self.expired_flag

    def navigate(self, url: str) -> str:
        self.url = url
        return f"Title: Fake Site — snapshot of {url}"

    def click(self, selector: str, index: int) -> str:
        self.clicked = (selector, index)
        return "Clicked — new snapshot"

    def type_text(self, selector: str, text: str) -> str:
        self.typed = (selector, text)
        return "Typed."

    def extract(self, selector: str) -> str:
        self.extracted = selector
        return "Extracted text"

    def screenshot(self, path: str, full_page: bool) -> str:
        Path(path).write_bytes(b"\x89PNG fake")
        return path

    def back(self) -> str:
        return "Back — snapshot"

    def close(self) -> None:
        self.closed = True


class BrowserToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeSession()
        mod.set_browser(self.fake)
        self._saved = {
            "enabled": settings.browser_enabled,
            "domains": list(getattr(settings, "browser_allowed_domains", [])),
            "roots": list(settings.file_allowed_write),
            "confirm": getattr(settings, "file_confirm_writes", True),
        }
        settings.browser_enabled = True
        settings.browser_allowed_domains = ["example.com", "localhost"]
        self.tmp = Path(tempfile.mkdtemp(prefix="sopno-browser-test-"))
        settings.file_allowed_write = [str(self.tmp)]
        settings.file_confirm_writes = True

    def tearDown(self) -> None:
        mod.set_browser(None)
        settings.browser_enabled = self._saved["enabled"]
        settings.browser_allowed_domains = self._saved["domains"]
        settings.file_allowed_write = self._saved["roots"]
        settings.file_confirm_writes = self._saved["confirm"]

    def test_disabled(self) -> None:
        settings.browser_enabled = False
        self.assertIn("browser_enabled", mod.browser_navigate("https://example.com"))
        self.assertIn("browser_enabled", mod.browser_click())

    def test_navigate_allowed_domain(self) -> None:
        out = mod.browser_navigate("example.com/docs")
        self.assertIn("Fake Site", out)
        self.assertEqual(self.fake.url, "https://example.com/docs")

    def test_navigate_blocked_domain(self) -> None:
        out = mod.browser_navigate("https://evil.example.net")
        self.assertIn("isn't allowed", out)
        self.assertIn("browser_allowed_domains", out)
        self.assertIsNone(self.fake.url)

    def test_navigate_subdomain_allowed(self) -> None:
        out = mod.browser_navigate("https://news.example.com/x")
        self.assertIn("Fake Site", out)
        self.assertEqual(self.fake.url, "https://news.example.com/x")

    def test_navigate_empty_url(self) -> None:
        self.assertIn("Which URL", mod.browser_navigate(""))

    def test_navigate_startup_failure(self) -> None:
        mod.set_browser(None)
        original = mod.BrowserSession

        def boom() -> None:
            raise RuntimeError("chromium missing")

        mod.BrowserSession = boom  # type: ignore[assignment]
        try:
            out = mod.browser_navigate("https://example.com")
            self.assertIn("Could not start the browser", out)
        finally:
            mod.BrowserSession = original
            mod.set_browser(self.fake)

    def test_click_with_index(self) -> None:
        out = mod.browser_click("", 3)
        self.assertEqual(self.fake.clicked, ("", 3))
        self.assertIn("Clicked", out)

    def test_click_with_selector(self) -> None:
        mod.browser_click("button.login", 1)
        self.assertEqual(self.fake.clicked, ("button.login", 1))

    def test_type(self) -> None:
        out = mod.browser_type("input[name=q]", "hello world")
        self.assertEqual(self.fake.typed, ("input[name=q]", "hello world"))
        self.assertIn("Typed", out)

    def test_type_empty_text(self) -> None:
        self.assertIn("What should I type", mod.browser_type("input", ""))

    def test_extract(self) -> None:
        self.assertEqual(mod.browser_extract("#main"), "Extracted text")
        self.assertEqual(self.fake.extracted, "#main")
        self.assertEqual(mod.browser_extract(), "Extracted text")
        self.assertEqual(self.fake.extracted, "")

    def test_back(self) -> None:
        self.assertIn("Back", mod.browser_back())

    def test_expired_session(self) -> None:
        self.fake.expired_flag = True
        out = mod.browser_navigate("https://example.com")
        self.assertIn("browser_task_limit", out)

    def test_screenshot_new_file(self) -> None:
        target = self.tmp / "shot.png"
        out = mod.browser_screenshot(str(target))
        self.assertIn("Done", out)
        self.assertTrue(target.is_file())

    def test_screenshot_outside_roots(self) -> None:
        outside = Path(tempfile.mkdtemp()) / "shot.png"
        out = mod.browser_screenshot(str(outside))
        self.assertIn("outside the allowed write roots", out)

    def test_screenshot_overwrite_confirmation(self) -> None:
        target = self.tmp / "shot.png"
        target.write_bytes(b"old")
        out = mod.browser_screenshot(str(target))
        self.assertIn("I need your permission to overwrite", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Done", result)
        self.assertTrue(target.is_file())

    def test_close(self) -> None:
        self.assertIn("closed", mod.browser_close())
        self.assertTrue(self.fake.closed)
        # Second close is a no-op with a friendly message.
        self.assertIn("isn't open", mod.browser_close())


if __name__ == "__main__":
    unittest.main()
