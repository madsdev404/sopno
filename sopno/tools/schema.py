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
            "name": "read_file",
            "description": "Read the contents of a file inside an allowed folder (by default the project). PDFs, images, and Office documents (.pdf/.png/.jpg/.docx/.xlsx/.pptx/…) are read automatically with text extraction or OCR. Folders are never listed here — use list_directory for that.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to read."
                    },
                    "lines": {
                        "type": "number",
                        "description": "Optional — positive = first N lines, negative = last N lines."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing one inside an allowed write folder (by default the project). Overwriting a file needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to create or overwrite."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text to write."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one exact string inside a file. The old_string must appear exactly once, so include enough surrounding text to be unique. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to edit."
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to replace (must occur exactly once)."
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text."
                    }
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the files and folders inside an allowed folder (defaults to the project root), with type and size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the folder to list (optional — defaults to the project root)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a single file inside an allowed write folder. Folders are never deleted. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to delete."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Rename or move a single file inside an allowed write folder. The destination must not already exist. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to move."
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Absolute destination path."
                    }
                },
                "required": ["path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Duplicate a file or folder inside an allowed folder. Won't overwrite an existing destination unless overwrite=true. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file or folder to copy."
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Absolute destination path."
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Allow replacing an existing destination (default false)."
                    }
                },
                "required": ["path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a single file inside an allowed folder. The destination must not already exist. Needs the user's Yes/No confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the file to move."
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Absolute destination path."
                    }
                },
                "required": ["path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files by file name (mode='name') or by their contents (mode='content'). Name mode matches fnmatch globs or substrings; content mode matches regex or plain text and returns path:line hits. Searches a folder (defaults to the project root) and skips blocked paths and binary files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Filename pattern (mode='name') or text/regex to find inside files (mode='content')."
                    },
                    "path": {
                        "type": "string",
                        "description": "Absolute folder to search (optional — defaults to the project root)."
                    },
                    "mode": {
                        "type": "string",
                        "description": "'name' or 'content' (default 'content')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a one-shot reminder. Parse the user's request into 'when' (natural language like 'in 10 minutes', '9:30pm', 'tomorrow 9am', '2026-08-20 14:30') and 'text' (what to remind about). Non-destructive — no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "when": {
                        "type": "string",
                        "description": "Natural-language time for the reminder."
                    },
                    "text": {
                        "type": "string",
                        "description": "What to remind the user about."
                    }
                },
                "required": ["when", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List upcoming and recent reminders with their ids, due times, and statuses.",
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
            "name": "cancel_reminder",
            "description": "Cancel a pending reminder by its id (shown by list_reminders).",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The reminder id to cancel."
                    }
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show the working-tree status (branch, staged/unstaged/untracked files) and the last 10 commits of a git repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent git commits, one line each.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of commits to show (1-50, default 10)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show the working-tree diff of a git repository, or only the staged changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "True to show only staged (index) changes."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "List, create, switch, or delete git branches. Deleting needs the user's confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    },
                    "action": {
                        "type": "string",
                        "enum": ["list", "create", "switch", "delete"],
                        "description": "What to do (default 'list')."
                    },
                    "name": {
                        "type": "string",
                        "description": "Branch name for create / switch / delete."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_add",
            "description": "Stage files for the next commit (needs the user's confirmation).",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    },
                    "paths": {
                        "type": "string",
                        "description": "One or more space-separated paths to stage (default '.' stages everything)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create a git commit with the given message (needs the user's confirmation). Use git_commit_message to draft a message first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    },
                    "message": {
                        "type": "string",
                        "description": "The commit message."
                    },
                    "add_all": {
                        "type": "boolean",
                        "description": "Also stage all changes (git add -A) before committing."
                    }
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_stash",
            "description": "List, push, or pop git stashes. Push and pop need the user's confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    },
                    "action": {
                        "type": "string",
                        "enum": ["list", "push", "pop"],
                        "description": "What to do (default 'list')."
                    },
                    "message": {
                        "type": "string",
                        "description": "Optional note for a stash push."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit_message",
            "description": "Ask the local LLM to draft a conventional commit message from the current diff. Read-only — nothing is staged or committed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional absolute path of the repository (defaults to the project root)."
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "True (default) to use the staged diff, else the unstaged one."
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
