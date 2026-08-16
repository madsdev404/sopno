"""
sopno/tools/builtins/data/packages.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Package-management tools — every install is confirmed, and uninstalls are
blocked unless the user opts in via ``packages_uninstall_allowed``.

Commands run through the shared terminal session (so the safety blocklist and
timeout clamps apply). System managers (apt/pacman/dnf) use ``sudo -n`` when
``packages_require_sudo`` is true; ``-n`` means it never hangs on a password
prompt — it just fails with a clear message instead.
"""

from __future__ import annotations

from typing import Optional

from sopno.config.settings import settings
from sopno.tools.builtins.files.files import _awaiting_confirmation
from sopno.tools.builtins.dev.terminal import _run_command_raw, _blocked_reason

_MANAGERS = ("auto", "apt", "pacman", "dnf", "pip", "flatpak")
_SYSTEM_MANAGERS = ("apt", "pacman", "dnf")
_INSTALL = {
    "apt":    ["apt", "install", "-y"],
    "pacman": ["pacman", "-S", "--noconfirm"],
    "dnf":    ["dnf", "install", "-y"],
    "pip":    ["pip", "install"],
    "flatpak":["flatpak", "install", "-y"],
}
_UNINSTALL = {
    "apt":    ["apt", "remove", "-y"],
    "pacman": ["pacman", "-R", "--noconfirm"],
    "dnf":    ["dnf", "remove", "-y"],
    "pip":    ["pip", "uninstall", "-y"],
    "flatpak":["flatpak", "uninstall", "-y"],
}
_NAME_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-@="


def _enabled() -> str:
    if not getattr(settings, "packages_enabled", True):
        return "Package tools are disabled (packages_enabled = false in config.json)."
    return ""


def _detect_manager() -> str:
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            data = f.read().lower()
    except OSError:
        return "pip"
    if "debian" in data or "ubuntu" in data:
        return "apt"
    if "arch" in data or "manjaro" in data:
        return "pacman"
    if "fedora" in data or "centos" in data or "rhel" in data:
        return "dnf"
    return "pip"


def _validate_name(name: str) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return "Which package should I manage?"
    if len(name) > 200:
        return "That package name is too long."
    if any(c not in _NAME_SAFE for c in name):
        return "That package name contains characters I don't trust."
    if ".." in name or name.startswith(".") or name.endswith("."):
        return "That package name looks off — please double-check it."
    return None


def _manager_for(manager: str) -> str:
    manager = (manager or "auto").strip().lower()
    if manager == "auto":
        return _detect_manager()
    if manager not in _MANAGERS:
        return "unsupported"
    return manager


def _build(mode: str, manager: str, name: str) -> tuple[Optional[str], Optional[list]]:
    """Return (error, command) — sudo may wrap the command when required."""
    if manager == "unsupported":
        return "Unsupported manager. Use auto, apt, pacman, dnf, pip, or flatpak.", None
    table = _INSTALL if mode == "install" else _UNINSTALL
    base = table[manager] + [name]
    if manager in _SYSTEM_MANAGERS and getattr(settings, "packages_require_sudo", True):
        return None, ["sudo", "-n"] + base
    return None, base


def install_package(name: str, manager: str = "auto") -> str:
    """
    Install a package through the system manager (confirmed).

    Args:
        name: The package name.
        manager: 'auto', 'apt', 'pacman', 'dnf', 'pip', or 'flatpak'.

    Returns:
        Confirmation, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    bad = _validate_name(name)
    if bad:
        return bad
    manager = _manager_for(manager)
    err, cmd = _build("install", manager, name)
    if err:
        return err
    assert cmd is not None
    shell = " ".join(cmd)
    if _blocked_reason(shell):
        return "That install was refused by the safety policy."

    def _do() -> str:
        res = _run_command_raw(shell, timeout=300)
        if res.get("blocked"):
            return f"Refused — {res['blocked']}."
        if res.get("error"):
            return res["error"]
        if res.get("exit_code") == 0:
            return f"Installed {name}."
        out = (res.get("stdout") or "").strip().splitlines()
        tail = out[-1] if out else f"exit code {res.get('exit_code')}"
        if manager == "apt" and "sudo" in cmd:
            tail = (tail + " (sudo may need your password)").strip()
        return f"Could not install {name}: {tail}"

    return _awaiting_confirmation(f"install {name} using {manager}", _do)


def uninstall_package(name: str, manager: str = "auto") -> str:
    """
    Remove a package (blocked by default; opt in via config).

    Args:
        name: The package name.
        manager: 'auto', 'apt', 'pacman', 'dnf', 'pip', or 'flatpak'.

    Returns:
        Confirmation, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    if not getattr(settings, "packages_uninstall_allowed", False):
        return (
            "I won't uninstall packages — it's blocked by default. To allow it, "
            "set packages_uninstall_allowed = true in config.json."
        )
    bad = _validate_name(name)
    if bad:
        return bad
    manager = _manager_for(manager)
    err, cmd = _build("uninstall", manager, name)
    if err:
        return err
    assert cmd is not None
    shell = " ".join(cmd)
    if _blocked_reason(shell):
        return "That uninstall was refused by the safety policy."

    def _do() -> str:
        res = _run_command_raw(shell, timeout=300)
        if res.get("blocked"):
            return f"Refused — {res['blocked']}."
        if res.get("error"):
            return res["error"]
        if res.get("exit_code") == 0:
            return f"Removed {name}."
        out = (res.get("stdout") or "").strip().splitlines()
        tail = out[-1] if out else f"exit code {res.get('exit_code')}"
        return f"Could not remove {name}: {tail}"

    return _awaiting_confirmation(f"uninstall {name} using {manager}", _do)
