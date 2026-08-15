"""
tests/test_tools.py
━━━━━━━━━━━━━━━━━━━
Automated unit tests for Sopno system skills and tools registry.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.tools.registry import execute_tool, get_registered_names
from sopno.tools.builtins.datetime_tool import get_current_time
from sopno.tools.builtins.search import search_web, fetch_url
from sopno.tools.builtins.system import open_application, control_volume


class TestSopnoTools(unittest.TestCase):
    """Verifies registry resolution, system tool bindings, and time formatted strings."""

    def test_registered_tools_list(self) -> None:
        """Verify registry contains all defined tools."""
        names = get_registered_names()
        self.assertIn("get_current_time", names)
        self.assertIn("open_application", names)
        self.assertIn("search_web", names)
        self.assertIn("fetch_url", names)
        self.assertIn("control_volume", names)
        self.assertIn("get_system_stats", names)
        self.assertIn("lock_screen", names)
        self.assertIn("play_media_control", names)

    def test_get_current_time(self) -> None:
        """Verify datetime string conforms to standard pattern (e.g. 'It is ... on ...')."""
        time_str = get_current_time()
        self.assertTrue(time_str.startswith("It is "))
        self.assertIn(" on ", time_str)

    @patch("subprocess.Popen")
    def test_open_application_success(self, mock_popen) -> None:
        """Verify successful desktop app launcher triggering."""
        res = open_application("chrome")
        self.assertEqual(res, "Opening chrome.")
        mock_popen.assert_called_once_with(["google-chrome"])

    def test_open_application_unknown(self) -> None:
        """Verify response when an unregistered application is requested."""
        res = open_application("non_existent_app_xyz")
        self.assertTrue(res.startswith("I don't know how to open"))

    @patch("subprocess.run")
    def test_control_volume_up(self, mock_run) -> None:
        """Verify sound volume up command structure."""
        res = control_volume("up")
        self.assertEqual(res, "Volume increased.")
        mock_run.assert_called_once_with(
            ["amixer", "-D", "pulse", "sset", "Master", "10%+"],
            check=True,
            capture_output=True
        )

    # ── Web tools ────────────────────────────────────────────────────────────

    _BING_HTML = """
    <ol id="b_results">
      <li class="b_algo">
        <h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly93d3cucHl0aG9uLm9yZy8=&ntb=1">
          python.org<span>https://www.python.org</span></a></h2>
        <p>The mission of the Python Software Foundation.</p>
      </li>
      <li class="b_algo">
        <h2><a href="https://w3schools.com/python/">
          w3schools.com<span>https://w3schools.com/python</span></a></h2>
        <p>Learn Python, a popular programming language.</p>
      </li>
    </ol>
    """

    @patch("requests.get")
    def test_search_web_parses_bing_results(self, mock_get) -> None:
        """Verify search_web decodes Bing redirect URLs and returns results."""
        mock_get.return_value = MagicMock(
            text=self._BING_HTML,
            status_code=200,
            raise_for_status=lambda: None,
        )
        res = search_web("python language", max_results=2)
        self.assertIn("Top 2 results", res)
        self.assertIn("https://www.python.org/", res)
        self.assertIn("Python Software Foundation", res)

    @patch("requests.get")
    def test_search_web_network_error(self, mock_get) -> None:
        """Verify search_web returns a graceful error message on failure."""
        mock_get.side_effect = Exception("timeout")
        self.assertTrue(search_web("hello").startswith("Web search failed"))

    @patch("requests.get")
    def test_fetch_url_extracts_text(self, mock_get) -> None:
        """Verify fetch_url extracts readable text from an HTML page."""
        mock_get.return_value = MagicMock(
            text="<html><body><h1>Hello</h1><script>var x=1;</script>"
                 "<p>Some <b>readable</b> content.</p></body></html>",
            headers={"Content-Type": "text/html"},
            status_code=200,
            raise_for_status=lambda: None,
        )
        res = fetch_url("example.com")
        self.assertEqual(res, "Hello Some readable content.")
        self.assertEqual(
            mock_get.call_args.args[0], "https://example.com"
        )

    @patch("requests.get")
    def test_fetch_url_json_passthrough(self, mock_get) -> None:
        """Verify fetch_url returns raw body for JSON content types."""
        mock_get.return_value = MagicMock(
            text='{"status": "ok"}',
            headers={"Content-Type": "application/json"},
            status_code=200,
            raise_for_status=lambda: None,
        )
        self.assertEqual(fetch_url("https://api.example.com/x"), '{"status": "ok"}')

    @patch("requests.get")
    def test_fetch_url_error(self, mock_get) -> None:
        """Verify fetch_url returns a graceful error message on failure."""
        mock_get.side_effect = Exception("connection refused")
        self.assertTrue(fetch_url("https://example.com").startswith("Could not fetch"))


if __name__ == "__main__":
    unittest.main()
