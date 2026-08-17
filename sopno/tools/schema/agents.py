"""
sopno/tools/schema/agents.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for subagents, background agents, and autonomous coding sessions.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_subagent",
            "description": "Delegate a focused task to a subagent (researcher / coder / reviewer). The researcher finds source-backed facts, the coder inspects and modifies the codebase, the reviewer reviews code read-only. Returns the subagent's text answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": ["researcher", "coder", "reviewer"],
                        "description": "Which subagent to run."
                    },
                    "task": {
                        "type": "string",
                        "description": "What to do, described precisely."
                    }
                },
                "required": ["agent", "task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "subagent_list",
            "description": "List the available subagents.",
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
            "name": "agent_create",
            "description": "Create a durable background agent with a goal it keeps making progress on, optionally on a schedule, with a tool allowlist and budget. Use agent_status to watch it, agent_send to talk to it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Unique agent name (identity across restarts)."
                    },
                    "goal": {
                        "type": "string",
                        "description": "The objective, written down so a fresh context can resume it."
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Optional trigger: interval:<seconds>, cron:<min hour dom month dow>, or eta:YYYY-MM-DD HH:MM:SS."
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tool allowlist; empty = all safe tools."
                    },
                    "budget": {
                        "type": "object",
                        "description": "Optional ceilings: max_turns, max_wall_minutes, max_actions_per_day."
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["general", "coding"],
                        "description": "general = LLM loop, coding = CodingAgent in a git worktree."
                    }
                },
                "required": ["name", "goal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_list",
            "description": "List all background agents with their state, schedule, and budget usage.",
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
            "name": "agent_status",
            "description": "Show a background agent's state, goal, budget usage, and recent activity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The agent's name."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_send",
            "description": "Send a message to a background agent (wakes it from waiting_human / dormant). A parked approval is answered: 'yes' approves, anything else declines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The agent's name."
                    },
                    "message": {
                        "type": "string",
                        "description": "What to tell it, e.g. 'yes, go ahead'."
                    }
                },
                "required": ["name", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_pause",
            "description": "Pause a background agent: it stops being scheduled/resumed until agent_resume. Queued jobs are cancelled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The agent's name."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_resume",
            "description": "Resume a paused or parked background agent (queues a resume job).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The agent's name."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_kill",
            "description": "Terminate a background agent permanently (confirmed). Jobs cancelled, schedule cleared, session marked dead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The agent's name."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_log",
            "description": "Show a background agent's append-only audit trail (actions, messages, transitions, errors).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The agent's name."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many entries to show (max 100)."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_align",
            "description": "Give a background agent a durable correction/preference. It is stored and injected into the agent's ORIENT phase on resume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The agent's name."
                    },
                    "correction": {
                        "type": "string",
                        "description": "The instruction to keep going forward."
                    }
                },
                "required": ["name", "correction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "coding_run",
            "description": "Kick off an autonomous coding ticket in the background (or a batch of tickets). Creates a coding session and queues its run job; watch it with coding_status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The ticket — what to implement / fix."
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional session name (auto-generated from the goal otherwise)."
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Optional trigger: interval:<seconds>, cron:<min hour dom month dow>, or eta:YYYY-MM-DD HH:MM:SS."
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tool allowlist; empty = all safe tools."
                    },
                    "budget": {
                        "type": "object",
                        "description": "Optional ceilings: max_turns, max_wall_minutes, max_actions_per_day."
                    },
                    "tickets": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Optional batch of ticket dicts ({goal, name?, schedule?, tools?, budget?}) for unattended runs."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "coding_status",
            "description": "Show coding sessions (state, budget usage, and the worktree branch each is working on).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "A specific session name (default: all coding sessions)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many sessions to show (default 20)."
                    }
                }
            }
        }
    },
]
