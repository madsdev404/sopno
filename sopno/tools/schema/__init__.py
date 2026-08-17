"""
sopno/tools/schema/__init__.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JSON schemas for the LLM tool-calling API.

``TOOLS_SCHEMA`` is the static base set (one list per tool category).
Dynamic tools (plugins, MCP clients) are appended at runtime via
``register_schema`` / ``unregister_schema`` and included in the snapshot
returned by ``get_schema()`` — the LLM prompt must always use
``get_schema()`` so the dynamic tools are visible.
"""

from typing import Any

from sopno.tools.schema.agents import SCHEMAS as _AGENTS
from sopno.tools.schema.automation import SCHEMAS as _AUTOMATION
from sopno.tools.schema.data import SCHEMAS as _DATA
from sopno.tools.schema.dev import SCHEMAS as _DEV
from sopno.tools.schema.files import SCHEMAS as _FILES
from sopno.tools.schema.knowledge import SCHEMAS as _KNOWLEDGE
from sopno.tools.schema.system import SCHEMAS as _SYSTEM
from sopno.tools.schema.web import SCHEMAS as _WEB

TOOLS_SCHEMA: list[dict[str, Any]] = (
    _SYSTEM + _WEB + _DEV + _FILES + _DATA
    + _KNOWLEDGE + _AUTOMATION + _AGENTS
)

# Dynamic schemas appended at runtime (plugins, MCP clients).
_DYNAMIC: list[dict[str, Any]] = []


def register_schema(schema: dict[str, Any]) -> None:
    """Add a function-schema dict to the dynamic set (idempotent by name)."""
    name = schema.get("function", {}).get("name")
    if not name:
        return
    unregister_schema(name)
    _DYNAMIC.append(schema)


def unregister_schema(name: str) -> None:
    """Remove a dynamic schema by its function name."""
    for i, s in enumerate(_DYNAMIC):
        if s.get("function", {}).get("name") == name:
            del _DYNAMIC[i]
            return


def get_schema() -> list[dict[str, Any]]:
    """Full tool schema: static base + currently registered dynamic tools."""
    return TOOLS_SCHEMA + list(_DYNAMIC)
