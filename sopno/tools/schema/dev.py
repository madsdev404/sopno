"""
sopno/tools/schema/dev.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for terminal, process, service, cron, package, and git operations.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
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
            "name": "install_package",
            "description": "Install a package through the system manager (apt/pacman/dnf/pip/flatpak). Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The package name."
                    },
                    "manager": {
                        "type": "string",
                        "description": "auto, apt, pacman, dnf, pip, or flatpak."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_package",
            "description": "Remove a package. Blocked by default (set packages_uninstall_allowed = true to enable). Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The package name."
                    },
                    "manager": {
                        "type": "string",
                        "description": "auto, apt, pacman, dnf, pip, or flatpak."
                    }
                },
                "required": ["name"]
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
]
