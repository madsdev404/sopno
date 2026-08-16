"""
sopno/tools/schema.py
━━━━━━━━━━━━━━━━━━━━━
JSON schemas for the LLM tool-calling API.

These define what functions Sopno has access to, what arguments they expect,
and when the AI should invoke them.
"""

TOOLS_SCHEMA = [
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
            "name": "search_web",
            "description": "Search the web for a query and return the top results with titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The web search query string."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch a webpage or URL and return its readable text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch (e.g. https://en.wikipedia.org/wiki/Python_(programming_language))."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research",
            "description": "Research a question in depth across the web and return a complete, cited answer (uses multiple search engines and reads several full pages).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question to research, phrased as a full question (e.g., 'What is the latest Linux kernel release?')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal",
            "description": "Run a shell command in Sopno's persistent terminal session and return the output and exit code. cd/export/background jobs persist between calls. For long-running or interactive commands, returns partial output with the session state; use terminal_send to send input and terminal_status to check progress. Destructive commands are blocked for safety.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run (e.g. 'pip install requests' or 'git log --oneline -5')."
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Optional seconds to wait for completion (default 30, max 300)."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_send",
            "description": "Send keys or stdin to the program currently running in the terminal session. Use for REPLs, installers, password prompts, or to interrupt a stuck command. Control keys: 'ctrl-c', 'ctrl-d', 'ctrl-z'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "Text to type, or 'ctrl-c' / 'ctrl-d' / 'ctrl-z' for a control key."
                    },
                    "enter": {
                        "type": "boolean",
                        "description": "Press Enter after the keys (default false)."
                    }
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_status",
            "description": "Check what the terminal session is doing now without sending anything: current output, whether the command finished (and its exit code), and the session state.",
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
            "name": "list_processes",
            "description": "List the top running processes by CPU usage, optionally filtered by a keyword (matches user, process name, or command line).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional keyword to filter processes by (e.g. 'chrome' or 'python')."
                    },
                    "limit": {
                        "type": "number",
                        "description": "Max rows to show (1-50, default 10)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Terminate a running process by PID (e.g. '4321') or exact process name (e.g. 'firefox'). System-critical processes and Sopno's own session are protected. Prefer signal TERM unless the process is stuck.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "The PID or the exact process name to kill."
                    },
                    "signal": {
                        "type": "string",
                        "enum": ["TERM", "INT", "KILL", "HUP", "STOP", "CONT"],
                        "description": "Signal to send (default TERM)."
                    }
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_service",
            "description": "Control a systemd user service (systemctl --user, no sudo needed): start, stop, restart, status, enable, disable, or reload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "stop", "restart", "status", "enable", "disable", "reload"],
                        "description": "The service action to perform."
                    },
                    "service": {
                        "type": "string",
                        "description": "The unit name (e.g. 'sopno.service')."
                    }
                },
                "required": ["action", "service"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_logs",
            "description": "Read recent log entries. Source 'user' reads the user journal, 'system' the system journal; pass a unit to filter by service. A source that is an absolute path (e.g. '/var/log/syslog') tails that log file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "'user' (default), 'system', or an absolute log file path."
                    },
                    "unit": {
                        "type": "string",
                        "description": "Optional systemd unit to filter the journal by (e.g. 'sopno.service')."
                    },
                    "lines": {
                        "type": "number",
                        "description": "Number of most-recent lines (1-300, default 30)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_cron",
            "description": "Manage the current user's cron jobs: 'list' shows them, 'add' schedules a new job (schedule + command), 'remove' deletes jobs matching a command. Schedule uses 5 cron fields (e.g. '0 9 * * *') or a shortcut like '@daily'. Blocked/destructive commands are refused.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "add", "remove"],
                        "description": "What to do (default 'list')."
                    },
                    "schedule": {
                        "type": "string",
                        "description": "For add: 5 cron fields or @shortcut, e.g. '0 9 * * *' or '@daily'."
                    },
                    "command": {
                        "type": "string",
                        "description": "For add: the command to run. For remove: text that identifies the job."
                    }
                },
                "required": []
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
    }
]
