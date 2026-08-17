"""
sopno/tools/schema/system.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for desktop apps, clipboard, window management, hardware stats,
network diagnostics, email, calendar, volume, media, and screen control.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time, date, and day of the week.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open a desktop application on the PC (e.g., chrome, terminal, vscode, spotify, firefox, files, calculator, settings).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The exact name or keyword of the application to open."
                    }
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_get",
            "description": "Read the current clipboard contents.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_set",
            "description": "Put text on the clipboard. Requires the user's confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to copy to the clipboard."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture the screen to a PNG file. Overwriting an existing file requires the user's confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute output path; must be inside the file write roots."
                    },
                    "region": {
                        "type": "string",
                        "description": "Optional 'X,Y,W,H' rectangle to capture; empty = full screen."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List the open desktop windows, one per line.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Bring a window whose title matches to the front.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Substring of the window title."
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_keys",
            "description": "Type text into the focused window. Requires the user's confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to type."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a key or shortcut combo, e.g. 'Return' or 'ctrl+alt+t'. Requires the user's confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "combo": {
                        "type": "string",
                        "description": "The key or combo to press."
                    }
                },
                "required": ["combo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_stats",
            "description": "Report disk partitions/usage plus CPU temperature and fan speed.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_gpu_stats",
            "description": "Report NVIDIA GPU name, utilisation, VRAM, and temperature.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_stats",
            "description": "Report bytes sent and received per network interface.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ping_host",
            "description": "Ping a host four times and report the round-trip times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "Hostname or IP address."
                    }
                },
                "required": ["host"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "traceroute",
            "description": "Trace the network path to a host (max 15 hops).",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "Hostname or IP address."
                    }
                },
                "required": ["host"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wifi_scan",
            "description": "Scan for nearby Wi-Fi networks via NetworkManager.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "public_ip",
            "description": "Report the public (WAN) IP address. Disabled unless network_public_ip_enabled = true.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "firewall_status",
            "description": "Read the firewall status, or turn the firewall on/off (needs confirmation and sudo).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "status (default), on, or off."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_read",
            "description": "Read the most recent messages in an IMAP mailbox (read-only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "How many messages to list (1-20, default 10)."
                    },
                    "mailbox": {
                        "type": "string",
                        "description": "IMAP folder (default INBOX)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_send",
            "description": "Send an email via SMTP. Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient address."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject."
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text."
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list",
            "description": "List upcoming events from the local .ics calendar files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "How many upcoming events to show (1-20, default 10)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": "Add an event to the local calendar file. Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Event title."
                    },
                    "start": {
                        "type": "string",
                        "description": "Start as 'YYYY-MM-DD HH:MM'."
                    },
                    "end": {
                        "type": "string",
                        "description": "End as 'YYYY-MM-DD HH:MM'."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional note."
                    }
                },
                "required": ["summary", "start", "end"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_volume",
            "description": "Control the PC speaker volume (up to raise, down to lower, toggle to mute/unmute).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["up", "down", "toggle"],
                        "description": "The volume action to perform: 'up' to increase, 'down' to decrease, 'toggle' to mute/unmute."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Get current PC system diagnostics (CPU load percentage, RAM usage, Battery level/status).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lock_screen",
            "description": "Lock the user's PC desktop screen immediately.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_media_control",
            "description": "Control player music/video playback (play, pause, next, previous).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "previous"],
                        "description": "The media control action to send."
                    }
                },
                "required": ["action"]
            }
        }
    },
]
