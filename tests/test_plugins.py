"""
tests/test_plugins.py
━━━━━━━━━━━━━━━━━━━━
Dynamic plugin system: discovery, namespaced registration into the registry +
schema, confirmation gate, and unload.
"""

import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.tools import registry, schema
from sopno.tools import plugins as mod
from sopno.tools.builtins import files

PLUGIN_SRC = '''
def plugin_tools():
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    def secret_action(x: str) -> str:
        return f"ACTION {x}"

    return {
        "greet": (
            greet,
            {
                "description": "Greet someone by name.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        ),
        "secret_action": {
            "fn": secret_action,
            "confirm": True,
            "schema": {
                "description": "A mutating action that needs Yes/No.",
                "parameters": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"],
                },
            },
        },
    }
'''


class PluginsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="sopno-plugins-test-"))
        plugin_dir = self.base / "hello"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text(PLUGIN_SRC)
        self._saved = {
            "enabled": settings.plugins_enabled,
            "dir": settings.plugins_dir,
        }
        settings.plugins_enabled = True
        settings.plugins_dir = str(self.base)

    def tearDown(self) -> None:
        mod.unload_plugins()
        settings.plugins_enabled = self._saved["enabled"]
        settings.plugins_dir = self._saved["dir"]

    def test_discovery_and_registration(self) -> None:
        loaded = mod.load_plugins()
        self.assertTrue(any("hello" in item for item in loaded))
        self.assertIn("hello_greet", registry.get_registered_names())
        self.assertIn("hello_secret_action", registry.get_registered_names())

    def test_tool_execution(self) -> None:
        mod.load_plugins()
        out = registry.execute_tool("hello_greet", {"name": "Sopno"})
        self.assertEqual(out, "Hello, Sopno!")

    def test_confirm_gate(self) -> None:
        mod.load_plugins()
        out = registry.execute_tool("hello_secret_action", {"x": "now"})
        self.assertIn("I need your permission", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertEqual(result, "ACTION now")

    def test_confirm_gate_declined(self) -> None:
        mod.load_plugins()
        registry.execute_tool("hello_secret_action", {"x": "now"})
        pending = files.pending_action()
        result = files.resolve_pending(pending["id"], "no")
        self.assertIn("Cancelled", result)

    def test_schema_visible(self) -> None:
        mod.load_plugins()
        names = [s["function"]["name"] for s in schema.get_schema()]
        self.assertIn("hello_greet", names)

    def test_disabled(self) -> None:
        settings.plugins_enabled = False
        self.assertEqual(mod.load_plugins(), [])

    def test_unload(self) -> None:
        mod.load_plugins()
        mod.unload_plugins()
        names = registry.get_registered_names()
        self.assertNotIn("hello_greet", names)
        self.assertNotIn("hello_secret_action", names)


if __name__ == "__main__":
    unittest.main()
