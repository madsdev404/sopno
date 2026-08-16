"""
tests/test_network.py
━━━━━━━━━━━━━━━━━━━━
Network tools with a stubbed terminal runner: host validation, missing-binary
detection, the opt-in public-IP policy, and the confirmed firewall toggle.
"""

import unittest

from sopno.config.settings import settings
from sopno.tools.builtins import network as mod
from sopno.tools.builtins import files


class NetworkTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "enabled": settings.network_enabled,
            "pubip": getattr(settings, "network_public_ip_enabled", False),
        }
        settings.network_enabled = True
        settings.network_public_ip_enabled = False
        self.calls: list[str] = []
        self._orig_run = mod._run_command_raw
        self._orig_blocked = mod._blocked_reason

        def run(command, timeout=None):  # noqa: ANN001
            self.calls.append(command)
            if command.startswith("command -v "):
                return {"stdout": "", "exit_code": 0, "completed": True,
                        "state": "idle"}
            if "api.ipify.org" in command:
                return {"stdout": "1.2.3.4\n", "exit_code": 0,
                        "completed": True, "state": "idle"}
            return {"stdout": f"output-of: {command}", "exit_code": 0,
                    "completed": True, "state": "idle"}

        mod._run_command_raw = run  # type: ignore[assignment]
        mod._blocked_reason = lambda command: ""  # type: ignore[assignment]

    def tearDown(self) -> None:
        mod._run_command_raw = self._orig_run
        mod._blocked_reason = self._orig_blocked
        settings.network_enabled = self._saved["enabled"]
        settings.network_public_ip_enabled = self._saved["pubip"]


class PingTest(NetworkTest):
    def test_disabled(self) -> None:
        settings.network_enabled = False
        self.assertIn("network_enabled", mod.ping_host("localhost"))

    def test_empty_host(self) -> None:
        self.assertIn("Which host", mod.ping_host(" "))

    def test_unsafe_host(self) -> None:
        out = mod.ping_host("google.com;rm -rf /")
        self.assertIn("characters I don't trust", out)
        self.assertEqual(self.calls, [])

    def test_ping(self) -> None:
        out = mod.ping_host("8.8.8.8")
        self.assertIn("ping -c 4 8.8.8.8", out)


class TracerouteTest(NetworkTest):
    def test_missing_binary(self) -> None:
        def run(command, timeout=None):  # noqa: ANN001
            self.calls.append(command)
            if command.startswith("command -v traceroute"):
                return {"stdout": "", "exit_code": 127, "completed": True,
                        "state": "idle"}
            return {"stdout": "", "exit_code": 0, "completed": True, "state": "idle"}

        mod._run_command_raw = run  # type: ignore[assignment]
        out = mod.traceroute("example.com")
        self.assertIn("isn't installed", out)

    def test_traceroute(self) -> None:
        out = mod.traceroute("example.com")
        self.assertIn("traceroute -m 15 example.com", out)


class WifiPublicIpFirewallTest(NetworkTest):
    def test_wifi_scan(self) -> None:
        out = mod.wifi_scan()
        self.assertIn("nmcli", out)

    def test_public_ip_disabled(self) -> None:
        out = mod.public_ip()
        self.assertIn("disabled by default", out)
        self.assertEqual(self.calls, [])

    def test_public_ip_enabled(self) -> None:
        settings.network_public_ip_enabled = True
        out = mod.public_ip()
        self.assertIn("1.2.3.4", out)

    def test_firewall_status(self) -> None:
        out = mod.firewall_status()
        self.assertIn("ufw status verbose", out)

    def test_firewall_on_confirmed(self) -> None:
        out = mod.firewall_status("on")
        self.assertIn("permission to turn the firewall on", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Firewall is now on", result)
        self.assertIn("sudo -n ufw on", self.calls)

    def test_firewall_bad_action(self) -> None:
        self.assertIn("status', 'on', or 'off'", mod.firewall_status("banana"))


if __name__ == "__main__":
    unittest.main()
