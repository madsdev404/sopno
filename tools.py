import os
import subprocess
import webbrowser
import datetime
import shutil

def get_current_time():
    now = datetime.datetime.now()
    # Format like: "10:15 AM on Tuesday, July 14"
    return f"It is currently {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}."

def open_application(app_name):
    app_name = app_name.lower().strip()
    apps = {
        "chrome": ["google-chrome", "chrome", "google-chrome-stable"],
        "browser": ["xdg-open", "http://google.com"],
        "firefox": ["firefox"],
        "terminal": ["gnome-terminal", "konsole", "xfce4-terminal", "alacritty", "xterm"],
        "files": ["nautilus", "dolphin", "thunar", "pcmanfm"],
        "vscode": ["code"],
        "spotify": ["spotify"],
        "discord": ["discord"],
        "calculator": ["gnome-calculator", "kcalc", "xcalc"],
        "settings": ["gnome-control-center", "systemsettings"]
    }
    
    # Simple matching
    matched_app = None
    for key, cmds in apps.items():
        if key in app_name or app_name in key:
            matched_app = cmds
            break
            
    if not matched_app:
        # Try to run whatever name was given
        matched_app = [app_name]
        
    # Find executable
    executable = None
    for cmd in matched_app:
        if shutil.which(cmd):
            executable = cmd
            break
            
    if executable:
        try:
            # Run in background detach
            subprocess.Popen([executable], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opening {app_name}."
        except Exception as e:
            return f"Failed to open {app_name}: {e}"
    else:
        return f"Sorry, I couldn't find the application '{app_name}' installed on your system."

def search_web(query):
    query = query.strip()
    if not query:
        return "What would you like me to search for?"
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    try:
        webbrowser.open(url)
        return f"Searching Google for: {query}"
    except Exception as e:
        return f"Could not open the browser: {e}"

def control_volume(action):
    action = action.lower().strip()
    try:
        if "up" in action:
            subprocess.run(["amixer", "-q", "-D", "pulse", "sset", "Master", "10%+"])
            return "Volume increased by ten percent."
        elif "down" in action:
            subprocess.run(["amixer", "-q", "-D", "pulse", "sset", "Master", "10%-"])
            return "Volume decreased by ten percent."
        elif "mute" in action or "unmute" in action or "toggle" in action:
            subprocess.run(["amixer", "-q", "-D", "pulse", "sset", "Master", "toggle"])
            return "Volume toggled."
        else:
            return "Invalid volume action. Use up, down, or toggle."
    except Exception as e:
        # Fallback to standard amixer if pulse is not defined
        try:
            if "up" in action:
                subprocess.run(["amixer", "-q", "sset", "Master", "10%+"])
                return "Volume increased."
            elif "down" in action:
                subprocess.run(["amixer", "-q", "sset", "Master", "10%-"])
                return "Volume decreased."
            elif "mute" in action or "unmute" in action or "toggle" in action:
                subprocess.run(["amixer", "-q", "sset", "Master", "toggle"])
                return "Volume toggled."
        except Exception as ex:
            return f"Could not adjust volume: {ex}"

def get_system_stats():
    stats = []
    # CPU usage
    try:
        cpu = subprocess.check_output("top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'", shell=True)
        stats.append(f"CPU usage is at {cpu.decode().strip()}%")
    except:
        pass
        
    # Memory usage
    try:
        mem = subprocess.check_output("free -m | awk 'NR==2{printf \"%.2f%%\", $3*100/$2 }'", shell=True)
        stats.append(f"Memory usage is at {mem.decode().strip()}")
    except:
        pass
        
    # Battery usage
    try:
        battery_path = "/sys/class/power_supply"
        if os.path.exists(battery_path):
            supplies = os.listdir(battery_path)
            for supply in supplies:
                if supply.startswith("BAT"):
                    cap_file = os.path.join(battery_path, supply, "capacity")
                    status_file = os.path.join(battery_path, supply, "status")
                    if os.path.exists(cap_file):
                        with open(cap_file, "r") as f:
                            cap = f.read().strip()
                        status = "discharging"
                        if os.path.exists(status_file):
                            with open(status_file, "r") as f:
                                status = f.read().strip().lower()
                        stats.append(f"Battery is at {cap}% and is currently {status}")
    except:
        pass
        
    if stats:
        return " | ".join(stats)
    return "Could not retrieve system stats."

def lock_screen():
    # Try gnome-screensaver, xdg-screensaver, loginctl lock-session
    commands = [
        ["xdg-screensaver", "lock"],
        ["gnome-screensaver-command", "-l"],
        ["loginctl", "lock-session"]
    ]
    for cmd in commands:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "Screen locked."
            except:
                continue
    return "Could not lock the screen. Make sure your desktop environment supports lock command."

def play_media_control(action):
    # Action can be play, pause, next, previous
    action = action.lower().strip()
    if shutil.which("playerctl"):
        try:
            subprocess.run(["playerctl", action])
            return f"Media {action}ed."
        except Exception as e:
            return f"Failed to control media: {e}"
    else:
        # Fallback to xdotool keystrokes if installed
        if shutil.which("xdotool"):
            keys = {
                "play": "XF86AudioPlay",
                "pause": "XF86AudioPlay",
                "next": "XF86AudioNext",
                "prev": "XF86AudioPrev",
                "previous": "XF86AudioPrev"
            }
            key = keys.get(action)
            if key:
                try:
                    subprocess.run(["xdotool", "key", key])
                    return f"Sent media key {action}."
                except Exception as e:
                    return f"xdotool failed: {e}"
        return "Playerctl or xdotool is not installed. Cannot control media."

def execute_tool(func_name, args):
    """Router to call tools based on model decision"""
    if func_name == "get_current_time":
        return get_current_time()
    elif func_name == "open_application":
        return open_application(args.get("app_name", ""))
    elif func_name == "search_web":
        return search_web(args.get("query", ""))
    elif func_name == "control_volume":
        return control_volume(args.get("action", ""))
    elif func_name == "get_system_stats":
        return get_system_stats()
    elif func_name == "lock_screen":
        return lock_screen()
    elif func_name == "play_media_control":
        return play_media_control(args.get("action", ""))
    return f"Unknown tool {func_name}."
