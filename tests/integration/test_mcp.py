"""
tests/test_mcp.py
━━━━━━━━━━━━━━━━━
MCP client: result/schema formatting, and a real end-to-end stdio round trip
against a tiny in-process MCP server spawned as a subprocess.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sopno.tools import registry, schema
from sopno.tools.mcp_client import McpHub, _format_result, _schema_for

SERVER_SCRIPT = """
import asyncio
from mcp.server import MCPServer

server = MCPServer("testsrv", version="0.1.0")


def greet(name: str) -> str:
    return f"Hello, {name}!"


def add(a: int, b: int) -> int:
    return a + b


server.add_tool(greet, name="greet", description="Greet someone by name")
server.add_tool(add, name="add", description="Add two integers")

asyncio.run(server.run_stdio_async())
"""


class FormattingTest(unittest.TestCase):
    def test_format_text_result(self) -> None:
        result = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Hello, world!")],
            is_error=False,
        )
        self.assertEqual(_format_result(result), "Hello, world!")

    def test_format_error_result(self) -> None:
        result = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="boom")],
            is_error=True,
        )
        self.assertIn("Error (remote server)", _format_result(result))

    def test_format_empty(self) -> None:
        result = SimpleNamespace(content=[], is_error=False)
        self.assertEqual(_format_result(result), "(no result)")

    def test_schema_for(self) -> None:
        tool = SimpleNamespace(
            name="greet",
            description="Greet someone.",
            input_schema={
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        out = _schema_for("srv_greet", tool)
        self.assertEqual(out["function"]["name"], "srv_greet")
        self.assertNotIn("$schema", out["function"]["parameters"])
        self.assertEqual(out["function"]["parameters"]["required"], ["name"])


class EndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="sopno-mcp-test-"))
        self.server_script = self.dir / "srv.py"
        self.server_script.write_text(SERVER_SCRIPT)
        self.hub = McpHub(
            {
                "testsrv": {
                    "command": sys.executable,
                    "args": ["-u", str(self.server_script)],
                }
            }
        )

    def tearDown(self) -> None:
        self.hub.close()

    def test_refresh_registers_tools(self) -> None:
        summary = self.hub.refresh()
        self.assertIn("testsrv", summary)
        self.assertIn("testsrv_greet", registry.get_registered_names())
        self.assertIn("testsrv_add", registry.get_registered_names())
        schema_names = [s["function"]["name"] for s in schema.get_schema()]
        self.assertIn("testsrv_greet", schema_names)

    def test_call_remote_tool(self) -> None:
        self.hub.refresh()
        out = registry.execute_tool("testsrv_greet", {"name": "Sopno"})
        self.assertEqual(out, "Hello, Sopno!")
        out2 = registry.execute_tool("testsrv_add", {"a": 20, "b": 22})
        self.assertEqual(out2, "42")

    def test_close_unregisters(self) -> None:
        self.hub.refresh()
        self.hub.close()
        self.assertNotIn("testsrv_greet", registry.get_registered_names())
        self.assertNotIn("testsrv_add", registry.get_registered_names())


class ServerDirectionTest(unittest.TestCase):
    """Sopno as an MCP server: its own client drives its own registry."""

    def setUp(self) -> None:
        self.hub = McpHub(
            {"sopno": {"command": sys.executable, "args": ["-u", "-m", "sopno.tools.mcp_server"]}}
        )

    def tearDown(self) -> None:
        self.hub.close()

    def test_server_exposes_registry(self) -> None:
        summary = self.hub.refresh()
        self.assertIn("sopno", summary)
        self.assertIn("sopno_get_current_time", registry.get_registered_names())

    def test_server_call_builtin(self) -> None:
        from datetime import datetime

        self.hub.refresh()
        out = registry.execute_tool("sopno_get_current_time", {})
        self.assertTrue(any(mark in out for mark in ("AM", "PM")),
                        f"expected a 12-hour clock, got: {out}")
        expected = datetime.now().strftime("%A, %B %d").replace(" 0", " ")
        self.assertIn(expected, out)


if __name__ == "__main__":
    unittest.main()
