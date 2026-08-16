"""
tests/test_packages.py
━━━━━━━━━━━━━━━━━━━━━
Package tools with a stubbed terminal runner + blocklist: confirmation gate,
sudo wrapping, manager detection, name validation, and the blocked-by-default
uninstall policy.
"""

import unittest

from sopno.config.settings import settings
from sopno.tools.builtins import packages as mod
from sopno.tools.builtins import files


class PackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "enabled": settings.packages_enabled,
            "uninstall": getattr(settings, "packages_uninstall_allowed", False),
            "sudo": getattr(settings, "packages_require_sudo", True),
        }
        settings.packages_enabled = True
        settings.packages_uninstall_allowed = False
        settings.packages_require_sudo = True
        self.calls: list[str] = []
        self.blocked = ""
        self.exit_code = 0
        self.stdout = ""
        self._orig_run = mod._run_command_raw
        self._orig_blocked = mod._blocked_reason
        self._orig_detect = mod._detect_manager

        def run(command, timeout=None):  # noqa: ANN001
            self.calls.append(command)
            return {"stdout": self.stdout, "exit_code": self.exit_code,
                    "completed": True, "state": "idle"}

        mod._run_command_raw = run  # type: ignore[assignment]
        mod._blocked_reason = lambda command: self.blocked  # type: ignore[assignment]
        mod._detect_manager = lambda: "apt"  # type: ignore[assignment]

    def tearDown(self) -> None:
        mod._run_command_raw = self._orig_run
        mod._blocked_reason = self._orig_blocked
        mod._detect_manager = self._orig_detect
        settings.packages_enabled = self._saved["enabled"]
        settings.packages_uninstall_allowed = self._saved["uninstall"]
        settings.packages_require_sudo = self._saved["sudo"]


class InstallTest(PackageTest):
    def test_disabled(self) -> None:
        settings.packages_enabled = False
        self.assertIn("packages_enabled", mod.install_package("curl"))

    def test_unsafe_name_rejected(self) -> None:
        out = mod.install_package("foo;rm -rf /")
        self.assertIn("characters I don't trust", out)
        self.assertEqual(self.calls, [])

    def test_dotdot_name_rejected(self) -> None:
        self.assertIn("double-check", mod.install_package(".."))

    def test_unknown_manager(self) -> None:
        out = mod.install_package("curl", manager="winget")
        self.assertIn("Unsupported manager", out)
        self.assertEqual(self.calls, [])

    def test_auto_detects_apt_with_sudo(self) -> None:
        out = mod.install_package("curl")
        self.assertIn("permission to install curl", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Installed curl", result)
        self.assertEqual(self.calls, ["sudo -n apt install -y curl"])

    def test_pip_no_sudo(self) -> None:
        mod.install_package("requests", manager="pip")
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        self.assertEqual(self.calls, ["pip install requests"])

    def test_sudo_disabled(self) -> None:
        settings.packages_require_sudo = False
        mod.install_package("curl")
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        self.assertEqual(self.calls, ["apt install -y curl"])

    def test_blocked_by_policy(self) -> None:
        self.blocked = "shutdown"
        out = mod.install_package("curl")
        self.assertIn("refused by the safety policy", out)
        self.assertEqual(self.calls, [])

    def test_failure_tail(self) -> None:
        self.exit_code = 100
        self.stdout = "E: Unable to locate package\nE: failed\n"
        mod.install_package("curl")
        pending = files.pending_action()
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Could not install curl: E: failed", result)


class UninstallTest(PackageTest):
    def test_blocked_by_default(self) -> None:
        out = mod.uninstall_package("curl")
        self.assertIn("blocked by default", out)
        self.assertIn("packages_uninstall_allowed", out)
        self.assertEqual(self.calls, [])

    def test_allowed_when_opted_in(self) -> None:
        settings.packages_uninstall_allowed = True
        out = mod.uninstall_package("curl")
        self.assertIn("permission to uninstall curl", out)
        pending = files.pending_action()
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Removed curl", result)
        self.assertEqual(self.calls, ["sudo -n apt remove -y curl"])

    def test_still_requires_confirmation(self) -> None:
        settings.packages_uninstall_allowed = True
        mod.uninstall_package("curl")
        pending = files.pending_action()
        result = files.resolve_pending(pending["id"], "no")
        self.assertNotIn("Removed", result)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
