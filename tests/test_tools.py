"""
tests/test_tools.py
━━━━━━━━━━━━━━━━━━━
Automated unit tests for Sopno system skills and tools registry.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.tools.registry import execute_tool, get_registered_names
from sopno.tools.builtins.datetime_tool import get_current_time
from sopno.tools.builtins.system import open_application, control_volume


class TestSopnoTools(unittest.TestCase):
    """Verifies registry resolution, system tool bindings, and time formatted strings."""

    def test_registered_tools_list(self) -> None:
        """Verify registry contains all defined tools."""
        names = get_registered_names()
        self.assertIn("get_current_time", names)
        self.assertIn("open_application", names)
        self.assertIn("search_web", names)
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


if __name__ == "__main__":
    unittest.main()
