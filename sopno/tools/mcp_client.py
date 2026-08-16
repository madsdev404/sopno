"""
sopno/tools/mcp_client.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Sopno as an MCP *client*: connect to remote MCP servers (config
``mcp_servers``) over stdio, list their tools, and register each as a namespaced
Sopno tool so the LLM can call them like any built-in.

Config shape (config.json):

    "mcp_servers": {
        "weather": {
            "command": ["/path/to/weather-server"],   # or a bare command string
            "args": ["--port", "9000"],
            "env": {"KEY": "value"}
        }
    }

Every remote tool is exposed as ``<server>_<tool>`` (e.g. ``weather_forecast``)
so names can never collide with built-ins. The MCP SDK is async, so the hub
runs its own daemon thread with a persistent event loop; the synchronous
assistant/tool paths submit coroutines to it and block for the result.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Optional

from sopno.config.settings import settings
from sopno.tools import registry, schema


def _format_result(result) -> str:
    """Flatten an MCP CallToolResult into a spoken string."""
    parts = []
    for block in getattr(result, "content", []):
        if getattr(block, "type", "") == "text":
            parts.append(getattr(block, "text", ""))
        else:
            parts.append(str(getattr(block, "text", block)))
    text = "\n".join(parts).strip()
    if getattr(result, "is_error", False):
        return f"Error (remote server): {text or 'unknown error'}"
    return text or "(no result)"


def _schema_for(full: str, tool) -> dict[str, Any]:
    """Convert a remote MCP Tool into Sopno's function-schema dict."""
    params = getattr(tool, "input_schema", None) or {
        "type": "object",
        "properties": {},
    }
    params.pop("$schema", None)
    params.pop("title", None)
    return {
        "type": "function",
        "function": {
            "name": full,
            "description": getattr(tool, "description", "") or f"MCP tool {full}.",
            "parameters": params,
        },
    }


class _LoopThread(threading.Thread):
    """Dedicated daemon thread running a persistent asyncio event loop."""

    def __init__(self) -> None:
        super().__init__(name="mcp-event-loop", daemon=True)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()

    def submit(self, coro, timeout: float = 60.0) -> Any:
        self._ready.wait(timeout=5)
        if self._loop is None:
            raise RuntimeError("MCP event loop did not start.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)


class McpHub:
    """Owns the connections to configured MCP servers and their registered tools."""

    def __init__(self, servers: Optional[dict[str, dict]] = None) -> None:
        self._servers: dict[str, dict] = dict(servers or {})
        self._loop_thread: Optional[_LoopThread] = None
        self._sessions: dict[str, tuple] = {}  # server -> (cm, read, write, session)
        self._tools: dict[str, tuple] = {}  # prefixed name -> (server, tool name, Tool)

    # ── sync surface ─────────────────────────────────────────────────────────

    def _submit(self, coro, timeout: float = 60.0) -> Any:
        if self._loop_thread is None:
            self._loop_thread = _LoopThread()
            self._loop_thread.start()
        return self._loop_thread.submit(coro, timeout)

    def refresh(self) -> str:
        """
        (Re)connect to every configured server and register its tools.

        Returns:
            A short summary string for logging.
        """
        self._unregister_all()
        tools: dict[str, tuple] = self._submit(self._refresh_async())
        for full, (server, tool, tinfo) in tools.items():
            registry.register_tool(full, self._make_wrapper(server, tool))
            schema.register_schema(_schema_for(full, tinfo))
        self._tools = tools
        if not tools:
            return "No MCP tools found (mcp_servers in config.json)."
        by_server: dict[str, int] = {}
        for full, (server, _, _) in tools.items():
            by_server[server] = by_server.get(server, 0) + 1
        summary = "; ".join(f"{s}: {n} tool(s)" for s, n in sorted(by_server.items()))
        return f"MCP connected — {summary}"

    def close(self) -> None:
        """Disconnect all servers and drop their registered tools."""
        self._unregister_all()
        try:
            self._submit(self._close_async(), timeout=10)
        except Exception:  # noqa: BLE001
            pass
        self._sessions.clear()

    # ── registry helpers ─────────────────────────────────────────────────────

    def _make_wrapper(self, server: str, tool: str) -> Callable[..., str]:
        def wrapper(**kwargs: Any) -> str:
            return self._submit(self._call_async(server, tool, kwargs))
        return wrapper

    def _unregister_all(self) -> None:
        for full in list(self._tools):
            registry.unregister_tool(full)
            schema.unregister_schema(full)
        self._tools.clear()

    # ── async internals ──────────────────────────────────────────────────────

    async def _refresh_async(self) -> dict[str, tuple]:
        for name, cfg in self._servers.items():
            try:
                await self._connect_async(name, cfg)
                session = self._sessions[name][3]
                result = await session.list_tools()
                for tool in getattr(result, "tools", []):
                    tool_name = getattr(tool, "name", "")
                    if tool_name:
                        self._tools[f"{name}_{tool_name}"] = (name, tool_name, tool)
            except Exception:  # noqa: BLE001 — keep the rest of the servers working
                continue
        return dict(self._tools)

    async def _connect_async(self, name: str, cfg: dict) -> None:
        if name in self._sessions:
            return
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        command = cfg.get("command")
        args = cfg.get("args", [])
        if isinstance(command, (list, tuple)):
            command, args = command[0], command[1:]
        env = cfg.get("env")
        params = StdioServerParameters(
            command=str(command),
            args=[str(a) for a in args],
            env=dict(env) if isinstance(env, dict) else None,
        )
        cm = stdio_client(params)
        read, write = await cm.__aenter__()
        session = ClientSession(read, write)
        await session.__aenter__()  # starts the JSON-RPC dispatcher
        await session.initialize()
        self._sessions[name] = (cm, read, write, session)

    async def _call_async(self, server: str, tool: str, args: dict) -> str:
        entry = self._sessions.get(server)
        if not entry:
            return f"Error: MCP server '{server}' is not connected."
        session = entry[3]
        try:
            result = await session.call_tool(tool, dict(args))
            return _format_result(result)
        except Exception as e:  # noqa: BLE001
            return f"Error calling MCP tool '{server}_{tool}': {e}"

    async def _close_async(self) -> None:
        for name, (cm, _, _, session) in list(self._sessions.items()):
            try:
                await session.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            try:
                await cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._sessions.pop(name, None)


def refresh_mcp() -> str:
    """One-shot convenience: build a hub from settings and connect."""
    if not getattr(settings, "mcp_enabled", True):
        return "MCP is disabled (mcp_enabled = false in config.json)."
    servers = getattr(settings, "mcp_servers", {}) or {}
    if not servers:
        return "No MCP servers configured (mcp_servers in config.json)."
    return McpHub(servers).refresh()
