"""
sopno/tools/builtins/system/system.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OS-level system tools.

Covers:
  - open_application  → launch a desktop app
  - control_volume    → raise / lower / mute speakers
  - get_system_stats  → CPU, RAM, battery info
  - lock_screen       → lock the desktop

All functions return a short human-readable string suitable for speaking aloud.
"""

import subprocess
import psutil

from sopno.config.settings import settings


# ── App launcher ───────────────────────────────────────────────────────────────

# Map friendly names → executable commands
_APP_MAP: dict[str, str] = {
    "chrome":    "google-chrome",
    "firefox":   "firefox",
    "files":     "nautilus",
    "terminal":  "gnome-terminal",
    "vscode":    "code",
    "spotify":   "spotify",
    "calculator":"gnome-calculator",
    "settings":  "gnome-control-center",
}


def open_application(app_name: str) -> str:
    """
    Launch a desktop application by friendly name.

    Args:
        app_name: e.g. "chrome", "terminal", "vscode"

    Returns:
        Short spoken confirmation or error message.
    """
    cmd = _APP_MAP.get(app_name.lower().strip())
    if not cmd:
        supported = ", ".join(_APP_MAP.keys())
        return f"I don't know how to open {app_name}. Supported apps: {supported}."
    allowed = getattr(settings, "desktop_allowed_apps", None)
    if allowed:
        if app_name.lower().strip() not in {a.lower().strip() for a in allowed}:
            return (
                f"I'm not allowed to open {app_name}. Allowed apps: "
                f"{', '.join(sorted(allowed))}."
            )
    try:
        subprocess.Popen([cmd])
        return f"Opening {app_name}."
    except FileNotFoundError:
        return f"{app_name} doesn't seem to be installed on this system."
    except Exception as e:
        return f"Failed to open {app_name}: {e}"


# ── Volume control ─────────────────────────────────────────────────────────────

def control_volume(action: str) -> str:
    """
    Adjust system volume via PulseAudio (amixer).

    Args:
        action: "up", "down", or "toggle" (mute/unmute)

    Returns:
        Short spoken confirmation or error message.
    """
    _cmds = {
        "up":     ["amixer", "-D", "pulse", "sset", "Master", "10%+"],
        "down":   ["amixer", "-D", "pulse", "sset", "Master", "10%-"],
        "toggle": ["amixer", "-D", "pulse", "sset", "Master", "toggle"],
    }
    cmd = _cmds.get(action.lower())
    if not cmd:
        return "Unknown volume action. Use 'up', 'down', or 'toggle'."
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return {"up": "Volume increased.", "down": "Volume decreased.", "toggle": "Volume toggled."}.get(action, "Done.")
    except Exception as e:
        return f"Volume control failed: {e}"


# ── System stats ───────────────────────────────────────────────────────────────

def get_system_stats() -> str:
    """
    Return a spoken summary of current CPU, RAM, and battery status.
    """
    try:
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        used = ram.used  // (1024 ** 3)
        total= ram.total // (1024 ** 3)

        parts = [f"CPU is at {cpu:.0f} percent.", f"RAM usage is {used} of {total} gigabytes."]

        battery = psutil.sensors_battery()
        if battery:
            status = "charging" if battery.power_plugged else "on battery"
            parts.append(f"Battery is at {battery.percent:.0f} percent and {status}.")

        try:
            usage = psutil.disk_usage("/")
            parts.append(
                f"Disk is at {usage.percent:.0f} percent "
                f"({usage.used // (1024**3)} of {usage.total // (1024**3)} gigabytes)."
            )
        except Exception:  # noqa: BLE001
            pass

        try:
            temps = psutil.sensors_temperatures()
            for entries in temps.values():
                if entries:
                    parts.append(f"Temperature is {entries[0].current:.0f} degrees Celsius.")
                    break
        except Exception:  # noqa: BLE001
            pass

        return " ".join(parts)
    except Exception as e:
        return f"Could not read system stats: {e}"


# ── Lock screen ────────────────────────────────────────────────────────────────

def lock_screen() -> str:
    """Lock the desktop session."""
    try:
        subprocess.Popen(["gnome-screensaver-command", "--lock"])
        return "Locking the screen."
    except FileNotFoundError:
        try:
            subprocess.Popen(["loginctl", "lock-session"])
            return "Locking the screen."
        except Exception as e:
            return f"Could not lock the screen: {e}"
