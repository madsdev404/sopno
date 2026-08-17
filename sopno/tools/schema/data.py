"""
sopno/tools/schema/data.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool schemas for SQLite database operations.
"""

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Run a SQL statement against a SQLite database file. SELECT/PRAGMA/EXPLAIN run immediately; mutating statements ask for confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the .db file (must be inside the read roots)."
                    },
                    "sql": {
                        "type": "string",
                        "description": "The SQL statement to run."
                    }
                },
                "required": ["path", "sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_schema",
            "description": "List the tables, columns, and row counts of a SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the .db file."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "backup_database",
            "description": "Make a live, consistent backup copy of a SQLite database. Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path of the database to back up."
                    },
                    "destination": {
                        "type": "string",
                        "description": "Output path (defaults to '<name>.backup.db'). Must be inside the write roots."
                    }
                },
                "required": ["path"]
            }
        }
    },
]
