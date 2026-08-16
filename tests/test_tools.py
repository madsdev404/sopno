"""
tests/test_tools.py
━━━━━━━━━━━━━━━━━━━
Automated unit tests for Sopno system skills and tools registry.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.tools.registry import execute_tool, get_registered_names
from sopno.tools.builtins.system.datetime_tool import get_current_time
from sopno.tools.builtins.web.search import search_web, fetch_url, web_search
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
        self.assertIn("research", names)
        self.assertIn("run_terminal", names)
        self.assertIn("terminal_send", names)
        self.assertIn("terminal_status", names)
        self.assertIn("list_processes", names)
        self.assertIn("kill_process", names)
        self.assertIn("manage_service", names)
        self.assertIn("read_logs", names)
        self.assertIn("manage_cron", names)
        self.assertIn("read_file", names)
        self.assertIn("write_file", names)
        self.assertIn("edit_file", names)
        self.assertIn("list_directory", names)
        self.assertIn("delete_file", names)
        self.assertIn("rename_file", names)
        self.assertIn("copy_file", names)
        self.assertIn("move_file", names)
        self.assertIn("search_files", names)
        self.assertIn("set_reminder", names)
        self.assertIn("list_reminders", names)
        self.assertIn("cancel_reminder", names)
        self.assertIn("browser_navigate", names)
        self.assertIn("browser_click", names)
        self.assertIn("browser_type", names)
        self.assertIn("browser_extract", names)
        self.assertIn("browser_screenshot", names)
        self.assertIn("browser_back", names)
        self.assertIn("browser_close", names)
        self.assertIn("clipboard_get", names)
        self.assertIn("clipboard_set", names)
        self.assertIn("take_screenshot", names)
        self.assertIn("list_windows", names)
        self.assertIn("focus_window", names)
        self.assertIn("send_keys", names)
        self.assertIn("press_key", names)
        self.assertIn("get_disk_stats", names)
        self.assertIn("get_gpu_stats", names)
        self.assertIn("get_network_stats", names)
        self.assertIn("query_database", names)
        self.assertIn("explain_schema", names)
        self.assertIn("backup_database", names)
        self.assertIn("install_package", names)
        self.assertIn("uninstall_package", names)
        self.assertIn("ping_host", names)
        self.assertIn("traceroute", names)
        self.assertIn("wifi_scan", names)
        self.assertIn("public_ip", names)
        self.assertIn("firewall_status", names)
        self.assertIn("describe_screenshot", names)
        self.assertIn("ocr_image", names)
        self.assertIn("email_read", names)
        self.assertIn("email_send", names)
        self.assertIn("calendar_list", names)
        self.assertIn("calendar_create_event", names)
        self.assertIn("note_write", names)
        self.assertIn("note_list", names)
        self.assertIn("note_search", names)
        self.assertIn("git_status", names)
        self.assertIn("git_log", names)
        self.assertIn("git_diff", names)
        self.assertIn("git_branch", names)
        self.assertIn("git_add", names)
        self.assertIn("git_commit", names)
        self.assertIn("git_stash", names)
        self.assertIn("git_commit_message", names)

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
    def test_bing_parser_decodes_redirect_urls(self, mock_get) -> None:
        """Verify Bing redirect URLs are decoded to real result URLs."""
        from sopno.tools.builtins.web.search import _bing_results
        mock_get.return_value = MagicMock(
            text=self._BING_HTML,
            status_code=200,
            raise_for_status=lambda: None,
        )
        results = _bing_results("python language", max_results=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["url"], "https://www.python.org/")
        self.assertEqual(results[0]["title"], "python.org")
        self.assertIn("Python Software Foundation", results[0]["snippet"])

    @patch("sopno.tools.builtins.web.search._ddg_results")
    @patch("sopno.tools.builtins.web.search._bing_results")
    def test_web_search_merges_and_dedupes(self, mock_bing, mock_ddg) -> None:
        """Verify web_search merges engines and deduplicates by URL."""
        mock_bing.return_value = [
            {"title": "Python.org", "url": "https://www.python.org/", "snippet": "PSF"}
        ]
        mock_ddg.return_value = [
            {"title": "Python.org (dup)", "url": "https://www.python.org/", "snippet": "dup"},
            {"title": "Docs", "url": "https://docs.python.org/", "snippet": "docs"},
        ]
        results = web_search("python language", max_results=5)
        urls = [r["url"] for r in results]
        self.assertEqual(urls, ["https://www.python.org/", "https://docs.python.org/"])

    @patch("sopno.tools.builtins.web.search.web_search")
    def test_search_web_formats_results(self, mock_ws) -> None:
        """Verify search_web turns structured results into a spoken list."""
        mock_ws.return_value = [
            {"title": "Python", "url": "https://www.python.org/", "snippet": "PSF mission."}
        ]
        res = search_web("python language", max_results=2)
        self.assertIn("Top 1 results", res)
        self.assertIn("https://www.python.org/", res)
        self.assertIn("PSF mission", res)

    @patch("sopno.tools.builtins.web.search._ddg_results", side_effect=Exception("timeout"))
    @patch("sopno.tools.builtins.web.search._bing_results", side_effect=Exception("timeout"))
    def test_search_web_network_error(self, mock_bing, mock_ddg) -> None:
        """Verify search_web returns a graceful message when search fails."""
        self.assertTrue(search_web("hello").startswith("I couldn't find any results"))

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
