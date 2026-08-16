"""
sopno/tools/builtins/system/desktop.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Desktop control + hardware tools.

Linux/X11-first, every dependency optional and detected at runtime — if a
binary is missing (xdotool/wmctrl/xclip/xsel/scrot/maim) the tool answers with
a friendly message instead of failing. On Wayland, input/window tools refuse
when ``desktop_require_x11`` is true.

Mutating tools (``clipboard_set``, ``take_screenshot`` on overwrite,
``send_keys``, ``press_key``) park a pending-action Yes/No gate first.
Hardware reads (disk/GPU/network) are always safe and read-only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import psutil

from sopno.config.settings import settings
from sopno.tools.builtins.files import files as files


def _run(cmd: list[str], input_text: Optional[str] = None) -> tuple[bool, str, str]:
    """Run a command; returns (ok, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=20,
        )
        return proc.returncode == 0, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return False, "", f"{cmd[0]} is not installed."
    except Exception as e:  # noqa: BLE001
        return False, "", str(e)


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


def _enabled() -> str:
    if not getattr(settings, "desktop_enabled", True):
        return "Desktop control is disabled (desktop_enabled = false in config.json)."
    return ""


def _x11_gate() -> str:
    """Refuse X11-only tools when there is no X server or we're on Wayland."""
    if not os.environ.get("DISPLAY"):
        return "No display server is available (DISPLAY is not set)."
    if getattr(settings, "desktop_require_x11", True) and os.environ.get("WAYLAND_DISPLAY"):
        return (
            "This session is on Wayland, and desktop_require_x11 is true — "
            "the X11 desktop tools can't be used reliably. Set "
            "desktop_require_x11 = false to allow them anyway."
        )
    return ""


def _gate(x11: bool = False) -> str:
    err = _enabled()
    if err or not x11:
        return err
    return _x11_gate()


def _confirm(description: str, fn) -> str:
    """Park a pending action (Yes/No) then run `fn` on approval."""
    return files._awaiting_confirmation(description, fn)


# ── Clipboard ────────────────────────────────────────────────────────────────

def clipboard_get() -> str:
    """
    Read the current clipboard contents.

    Returns:
        The clipboard text, or a reason it can't be read.
    """
    err = _gate(x11=True)
    if err:
        return err
    if not (_have("xclip") or _have("xsel")):
        return "Clipboard tools aren't installed (install xclip or xsel)."
    if _have("xclip"):
        ok, out, _ = _run(["xclip", "-selection", "clipboard", "-o"])
    else:
        ok, out, _ = _run(["xsel", "-b", "-o"])
    if not ok:
        return "The clipboard is empty or couldn't be read."
    return out.strip() or "(empty clipboard)"


def clipboard_set(text: str) -> str:
    """
    Put text on the clipboard (confirmed).

    Args:
        text: The text to copy to the clipboard.

    Returns:
        Confirmation, or a reason it failed.
    """
    err = _gate(x11=True)
    if err:
        return err
    if not text.strip():
        return "What should I copy?"
    if not (_have("xclip") or _have("xsel")):
        return "Clipboard tools aren't installed (install xclip or xsel)."
    if _have("xclip"):
        cmd = ["xclip", "-selection", "clipboard"]
    else:
        cmd = ["xsel", "-b", "-i"]

    def _do() -> str:
        ok, _, stderr = _run(cmd, input_text=text)
        if not ok:
            return f"Could not set the clipboard: {stderr.strip() or 'unknown error'}"
        return "Done — copied to the clipboard."

    return _confirm("copy text to the clipboard", _do)


# ── Screenshot ───────────────────────────────────────────────────────────────

def take_screenshot(path: str, region: str = "") -> str:
    """
    Capture the screen to a PNG (confirmed if the file exists).

    Args:
        path: Absolute output path (must be inside the file write roots).
        region: Optional "X,Y,W,H" rectangle; empty = full screen.

    Returns:
        Confirmation, or a reason it can't be taken.
    """
    err = _gate(x11=True)
    if err:
        return err
    if not (_have("scrot") or _have("maim")):
        return "No screenshot tool installed (install scrot or maim)."
    target, err = files._resolve_target(path)
    if err:
        return err
    assert target is not None
    reason = files._authorize(target, "write")
    if reason:
        return reason
    cmd = ["scrot", str(target)] if _have("scrot") else ["maim", str(target)]
    if region.strip():
        # scrot -a X,Y,W,H ; maim -g WxH+X+Y
        if cmd[0] == "scrot":
            cmd = ["scrot", "-a", region.strip(), str(target)]
        else:
            x, y, w, h = region.split(",")
            cmd = ["maim", "-g", f"{w}x{h}+{x}+{y}", str(target)]

    def _do() -> str:
        ok, _, stderr = _run(cmd)
        if not ok:
            return f"Could not take the screenshot: {stderr.strip() or 'unknown error'}"
        return f"Done — saved the screenshot to {target}."

    if target.is_file() and getattr(settings, "file_confirm_writes", True):
        return files._awaiting_confirmation(f"overwrite '{target}'", _do)
    return _do()


# ── Windows ──────────────────────────────────────────────────────────────────

def list_windows() -> str:
    """
    List the open desktop windows (wmctrl).

    Returns:
        One window per line, or a reason it can't be listed.
    """
    err = _gate(x11=True)
    if err:
        return err
    if not _have("wmctrl"):
        return "Window tools aren't installed (install wmctrl)."
    ok, out, _ = _run(["wmctrl", "-l"])
    if not ok or not out.strip():
        return "No windows found."
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return "\n".join(lines[:40]) if len(lines) <= 40 else "\n".join(lines[:40]) + "\n…"

def focus_window(title: str) -> str:
    """
    Focus (bring to front) a window whose title matches.

    Args:
        title: Substring of the window title.

    Returns:
        Confirmation, or a reason it can't be focused.
    """
    err = _gate(x11=True)
    if err:
        return err
    if not title.strip():
        return "Which window should I focus?"
    if not _have("wmctrl"):
        return "Window tools aren't installed (install wmctrl)."
    ok, _, stderr = _run(["wmctrl", "-a", title.strip()])
    if not ok:
        return f"Could not find a window matching '{title}'. {stderr.strip()}"
    return f"Focused '{title}'."


# ── Keyboard (xdotool) ───────────────────────────────────────────────────────

def send_keys(text: str) -> str:
    """
    Type text into the focused window (confirmed).

    Args:
        text: The text to type.

    Returns:
        Confirmation, or a reason it failed.
    """
    err = _gate(x11=True)
    if err:
        return err
    if not text.strip():
        return "What should I type?"
    if not _have("xdotool"):
        return "Keyboard tools aren't installed (install xdotool)."

    def _do() -> str:
        ok, _, stderr = _run(["xdotool", "type", "--delay", "30", text])
        if not ok:
            return f"Could not type: {stderr.strip() or 'unknown error'}"
        return "Done — typed it."

    return _confirm("type text via the keyboard", _do)


def press_key(combo: str) -> str:
    """
    Press a key or shortcut combo (confirmed).

    Args:
        combo: e.g. "Return", "ctrl+alt+t", "super+l".

    Returns:
        Confirmation, or a reason it failed.
    """
    err = _gate(x11=True)
    if err:
        return err
    if not combo.strip():
        return "Which key should I press?"
    if not _have("xdotool"):
        return "Keyboard tools aren't installed (install xdotool)."
    if any(c in combo for c in (";", "|", "&&", "`", "$")):
        return "That key combo looks unsafe — I only press real key names."

    def _do() -> str:
        ok, _, stderr = _run(["xdotool", "key", combo.strip()])
        if not ok:
            return f"Could not press {combo}: {stderr.strip() or 'unknown error'}"
        return f"Pressed {combo}."

    return _confirm(f"press {combo.strip()}", _do)


# ── Hardware reads (read-only) ───────────────────────────────────────────────

def get_disk_stats() -> str:
    """
    Report disk partitions/usage plus CPU temperature and fan speed.

    Returns:
        A spoken summary.
    """
    err = _enabled()
    if err:
        return err
    parts = ["Disk usage:"]
    try:
        for part in psutil.disk_partitions(all=False):
            if part.device.startswith("/dev/loop") or part.mountpoint.startswith("/snap/"):
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                parts.append(
                    f"{part.mountpoint} {usage.percent:.0f}% used "
                    f"({usage.used // (1024**3)} of {usage.total // (1024**3)} GB)"
                )
            except (PermissionError, OSError):
                continue
    except Exception:  # noqa: BLE001
        parts.append("(could not read partitions)")
    try:
        temps = psutil.sensors_temperatures()
        for label, entries in temps.items():
            if entries:
                parts.append(f"{label} {entries[0].current:.0f}°C")
    except Exception:  # noqa: BLE001
        pass
    try:
        fans = psutil.sensors_fans()
        for label, entries in fans.items():
            if entries:
                parts.append(f"{label} fan at {entries[0].current} RPM")
    except Exception:  # noqa: BLE001
        pass
    return " ".join(parts)


def get_gpu_stats() -> str:
    """
    Report NVIDIA GPU name, utilisation, VRAM, and temperature.

    Returns:
        A spoken summary, or a "no NVIDIA GPU" note.
    """
    err = _enabled()
    if err:
        return err
    try:
        import pynvml
    except Exception:  # noqa: BLE001
        return "No NVIDIA GPU detected (or nvidia-ml-py isn't installed)."
    try:
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            return "No NVIDIA GPU detected."
        parts = []
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle).decode()
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            parts.append(
                f"{name}: {util.gpu}% util, {mem.used // (1024**2)} of "
                f"{mem.total // (1024**2)} MB VRAM, {temp}°C."
            )
        return " ".join(parts)
    except Exception as e:  # noqa: BLE001
        return f"Could not read GPU stats: {e}"


def get_network_stats() -> str:
    """
    Report bytes sent/received per network interface.

    Returns:
        A spoken summary.
    """
    err = _enabled()
    if err:
        return err
    try:
        stats = psutil.net_io_counters(pernic=True)
        parts = ["Network:"]
        for name, nic in sorted(stats.items()):
            if nic.bytes_sent or nic.bytes_recv:
                parts.append(
                    f"{name}: {nic.bytes_recv // (1024**2)} MB down, "
                    f"{nic.bytes_sent // (1024**2)} MB up"
                )
        return " ".join(parts)
    except Exception as e:  # noqa: BLE001
        return f"Could not read network stats: {e}"
