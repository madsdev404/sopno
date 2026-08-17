"""
sopno/tools/schema/automation.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for reminders and automation rules.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
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
            "name": "rule_add",
            "description": "Create an automation rule 'if {condition} then {action}', confirmed once. Condition is a metric compared with < <= > >= ==, e.g. 'battery_percent < 20' or 'hour_of_day >= 21'. Metrics: battery_percent, cpu_percent, ram_percent, disk_free_gb, hour_of_day, day_of_week (0=Monday..6=Sunday). Action is a registered tool with key=value args, e.g. open_application app=\"Files\" or note_write title=\"daily\" content=\"...\". The rule acts automatically whenever the condition is true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short rule name."
                    },
                    "condition": {
                        "type": "string",
                        "description": "e.g. 'battery_percent < 20'."
                    },
                    "action": {
                        "type": "string",
                        "description": "Tool call, e.g. 'open_application app=\"Files\"'."
                    }
                },
                "required": ["name", "condition", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rule_list",
            "description": "List the automation rules with their conditions, actions, and fire counts.",
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
            "name": "rule_remove",
            "description": "Delete an automation rule. Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {
                        "type": "integer",
                        "description": "The rule id from rule_list."
                    }
                },
                "required": ["rule_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rule_set_enabled",
            "description": "Enable or disable an automation rule (disabling is confirmed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {
                        "type": "integer",
                        "description": "The rule id from rule_list."
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "True to arm the rule, False to pause it."
                    }
                },
                "required": ["rule_id", "enabled"]
            }
        }
    },
]
