import subprocess
import webbrowser
import datetime

def open_app(app_name: str) -> str:
    """Open a known application by name.
    Supported apps: chrome, firefox, files, terminal, vscode, spotify.
    Returns a short spoken response."""
    apps = {
        "chrome": "google-chrome",
        "firefox": "firefox",
        "files": "nautilus",
        "terminal": "gnome-terminal",
        "vscode": "code",
        "spotify": "spotify",
    }
    cmd = apps.get(app_name.lower())
    if not cmd:
        return f"I don't know how to open {app_name}."
    try:
        subprocess.Popen([cmd])
        return f"Opening {app_name}."
    except Exception as e:
        return f"Failed to open {app_name}: {e}"

def search_web(query: str) -> str:
    """Search Google for the given query and open the browser."""
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    try:
        webbrowser.open(url)
        return f"Searching the web for {query}."
    except Exception as e:
        return f"Failed to search the web: {e}"

def get_time() -> str:
    """Return a human‑readable current date and time."""
    now = datetime.datetime.now()
    return f"It is {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d')}."

def control_volume(direction: str) -> str:
    """Adjust system volume.
    direction: 'up', 'down', or 'mute'."""
    try:
        if direction == "up":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%+"], check=True)
            return "Volume increased."
        if direction == "down":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%-"], check=True)
            return "Volume decreased."
        if direction == "mute":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "toggle"], check=True)
            return "Volume toggled."
        return "Unknown volume command."
    except Exception as e:
        return f"Failed to adjust volume: {e}"
