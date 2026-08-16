"""
sopno/tools/builtins/web/network.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network tools — all read-only by default.

``ping_host``, ``traceroute``, ``wifi_scan`` and ``firewall_status()`` are
harmless reads. ``public_ip`` calls out to a public IP echo service and is
disabled unless the user opts in (``network_public_ip_enabled``). The only
mutating tool is ``firewall_status(action="on"/"off")``, which is confirmed.
"""

from __future__ import annotations

from typing import Optional

from sopno.config.settings import settings
from sopno.tools.builtins.files.files import _awaiting_confirmation
from sopno.tools.builtins.dev.terminal import _run_command_raw, _blocked_reason

_HOST_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"


def _enabled() -> str:
    if not getattr(settings, "network_enabled", True):
        return "Network tools are disabled (network_enabled = false in config.json)."
    return ""


def _validate_host(host: str) -> Optional[str]:
    host = (host or "").strip()
    if not host:
        return "Which host should I reach?"
    if len(host) > 253 or any(c not in _HOST_SAFE for c in host):
        return "That host name contains characters I don't trust."
    return None


def _run(shell: str) -> str:
    res = _run_command_raw(shell, timeout=120)
    if res.get("blocked"):
        return f"Refused — {res['blocked']}."
    if res.get("error"):
        return res["error"]
    out = (res.get("stdout") or "").strip()
    if res.get("exit_code") != 0 and not out:
        return f"Command failed with exit code {res.get('exit_code')}."
    return out or "(no output)"


def ping_host(host: str) -> str:
    """
    Ping a host four times and report the round-trip times.

    Args:
        host: Hostname or IP address.

    Returns:
        The ping output, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    bad = _validate_host(host)
    if bad:
        return bad
    return _run(f"ping -c 4 {host}")


def traceroute(host: str) -> str:
    """
    Trace the network path to a host (max 15 hops).

    Args:
        host: Hostname or IP address.

    Returns:
        The traceroute output, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    bad = _validate_host(host)
    if bad:
        return bad
    res = _run_command_raw(f"command -v traceroute", timeout=30)
    if res.get("exit_code") != 0:
        return "traceroute isn't installed."
    return _run(f"traceroute -m 15 {host}")


def wifi_scan() -> str:
    """
    Scan for nearby Wi-Fi networks via NetworkManager.

    Returns:
        The nmcli scan output, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    res = _run_command_raw("command -v nmcli", timeout=30)
    if res.get("exit_code") != 0:
        return "nmcli (NetworkManager) isn't available."
    return _run("nmcli -f SSID,SIGNAL,SECURITY device wifi list")


def public_ip() -> str:
    """
    Report the public (WAN) IP address via an echo service (opt-in).

    Returns:
        The public IP, or a reason it's disabled/unavailable.
    """
    err = _enabled()
    if err:
        return err
    if not getattr(settings, "network_public_ip_enabled", False):
        return (
            "Checking your public IP is disabled by default. Set "
            "network_public_ip_enabled = true in config.json to allow it."
        )
    res = _run_command_raw("curl -s -m 10 https://api.ipify.org", timeout=30)
    if res.get("exit_code") != 0:
        res2 = _run_command_raw("curl -s -m 10 https://ifconfig.me", timeout=30)
        out = (res2.get("stdout") or "").strip()
        if res2.get("exit_code") == 0 and out:
            return f"Your public IP is {out}."
        return "Could not reach a public IP service."
    out = (res.get("stdout") or "").strip()
    return f"Your public IP is {out}."


def firewall_status(action: str = "status") -> str:
    """
    Read the firewall status, or turn the firewall on/off (confirmed).

    Args:
        action: 'status' (default), 'on', or 'off'.

    Returns:
        The status output, or a confirmation/failure reason.
    """
    err = _enabled()
    if err:
        return err
    action = (action or "status").strip().lower()
    if action == "status":
        res = _run_command_raw("command -v ufw", timeout=30)
        if res.get("exit_code") != 0:
            return "ufw isn't installed."
        return _run("ufw status verbose")
    if action not in ("on", "off"):
        return "Use 'status', 'on', or 'off'."

    shell = f"sudo -n ufw {action}"
    if _blocked_reason(shell):
        return "Refused by the safety policy."

    def _do() -> str:
        res = _run_command_raw(shell, timeout=120)
        if res.get("blocked"):
            return f"Refused — {res['blocked']}."
        if res.get("error"):
            return res["error"]
        if res.get("exit_code") == 0:
            return f"Firewall is now {action}."
        out = (res.get("stdout") or "").strip()
        return f"Could not change the firewall: {out or res.get('exit_code')}"

    return _awaiting_confirmation(
        f"turn the firewall {action} (this needs sudo)", _do
    )
