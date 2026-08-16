"""
sopno/tools/mcp_server.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Sopno as an MCP *server*: expose the entire tool registry to any MCP host
(Claude Desktop, Cursor, opencode…) over stdio.

Run it as its own process:

    python -m sopno.tools.mcp_server

Then point your host at it (e.g. ``command: "venv/bin/python",
args: ["-m", "sopno.tools.mcp_server"]``). Every registered tool — built-ins,
plugins, MCP-forwarded tools — becomes an MCP tool on the wire, so hosts can
drive Sopno's file/terminal/git/browser/reminder skills directly. Sopno's own
permission gates (file roots, confirmations, terminal blocklist) still apply.
"""

from __future__ import annotations

import asyncio
from typing import Any

import mcp.types as types
from mcp.server import MCPServer

from sopno.tools.registry import _REGISTRY, execute_tool
from sopno.tools.schema import get_schema

_SERVER_NAME = "sopno"
_SERVER_VERSION = "1.0.0"


def build_server() -> MCPServer:
    """Build an MCPServer wrapping every registered Sopno tool."""
    schemas = {
        s["function"]["name"]: s["function"]
        for s in get_schema()
        if s.get("function", {}).get("name")
    }
    server = MCPServer(_SERVER_NAME, version=_SERVER_VERSION)
    for name, fn in _REGISTRY.items():
        info = schemas.get(name, {})
        description = info.get("description") or f"Sopno tool {name}."
        try:
            # Prefer the real function so the host gets a rich inferred schema.
            server.add_tool(fn, name=name, description=description)
        except Exception:  # noqa: BLE001 — fall back to a kwargs wrapper
            def _call(_name: str = name, **kwargs: Any) -> str:
                return execute_tool(_name, kwargs)

            server.add_tool(_call, name=name, description=description)
    return server


def main() -> None:
    """Run the stdio MCP server (blocking)."""
    asyncio.run(build_server().run_stdio_async())


if __name__ == "__main__":
    main()
