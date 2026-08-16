"""
sopno/tools/plugins.py
━━━━━━━━━━━━━━━━━━━━━━
Dynamic plugin system.

A plugin is a folder ``plugins/<name>/plugin.py`` (or a standalone
``plugins/<name>.py``) that exposes a small module contract:

    PLUGIN_NAME = "weather"            # namespace; defaults to the folder name
    PLUGIN_CONFIRM = False             # require Yes/No for every tool? (default deny)
    def plugin_tools() -> dict:        # {tool_name: (fn, schema)} or
                                       # {tool_name: {"fn": ..., "schema": ...}}
    def on_load() -> None: ...         # optional hook
    def on_unload() -> None: ...       # optional hook

Each tool is registered as ``<PLUGIN_NAME>_<tool_name>`` (namespaced to avoid
colliding with built-ins) and its schema is appended to the LLM tool schema.

**Default-deny:** plugins are an explicit opt-in (`plugins_enabled: true`), and
a plugin that does not declare ``PLUGIN_CONFIRM = True`` runs its tools under
the same rules as every other tool: anything destructive must use the file
tools' pending-action Yes/No gate itself — plugins get no implicit powers and
cannot bypass the file roots or terminal blocklist.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from sopno.config.settings import settings
from sopno.tools import registry, schema

# Tool names registered by plugins (so unload only touches our own).
_REGISTERED_NAMES: set[str] = set()


def _plugins_dir() -> Path:
    raw = getattr(settings, "plugins_dir", None)
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = settings.project_root / p
        return p
    return settings.project_root / "plugins"


def _discover() -> list[Path]:
    """plugin.py files — one per folder, or standalone .py files."""
    base = _plugins_dir()
    if not base.is_dir():
        return []
    found: list[Path] = []
    for entry in sorted(base.iterdir()):
        if entry.is_dir():
            candidate = entry / "plugin.py"
            if candidate.is_file():
                found.append(candidate)
        elif entry.suffix == ".py" and entry.name != "__init__.py":
            found.append(entry)
    return found


def _plugin_name(module_path: Path) -> str:
    if module_path.name == "plugin.py":
        return module_path.parent.name
    return module_path.stem


def _load_module(path: Path) -> Any:
    name = f"sopno_plugin_{_plugin_name(path)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _normalize(entry: Any) -> tuple[Callable[..., str], Optional[dict], bool]:
    """(fn, schema, confirm) from a plugin_tools() entry."""
    confirm = False
    if isinstance(entry, dict):
        fn = entry.get("fn")
        schema_d = entry.get("schema")
        confirm = bool(entry.get("confirm", False))
    else:
        fn, schema_d = entry  # (fn, schema) tuple
    if not callable(fn):
        raise TypeError("plugin tool fn must be callable")
    return fn, schema_d, confirm


def _confirm_wrapper(fn: Callable[..., str], name: str) -> Callable[..., str]:
    """Park a pending action before running the plugin tool (Yes/No gate)."""
    import uuid

    from sopno.tools.builtins import files

    def wrapper(**kwargs: Any) -> str:
        action_id = uuid.uuid4().hex[:8]
        description = f"run plugin tool '{name}'"
        files._PENDING_ACTION = {
            "id": action_id,
            "description": description,
            "fn": lambda: _safe_call(fn, kwargs),
        }
        return (
            f"I need your permission to {description}. "
            f"Say 'yes' to allow it, or 'no' to cancel. "
            f"(pending action {action_id})"
        )

    return wrapper


def _safe_call(fn: Callable[..., str], kwargs: dict[str, Any]) -> str:
    try:
        return fn(**kwargs)
    except Exception as e:  # noqa: BLE001
        return f"Error executing plugin tool: {e}"


def load_plugins() -> list[str]:
    """
    Discover and register all plugins.

    Returns:
        Names of the loaded plugins (for logging).
    """
    if not getattr(settings, "plugins_enabled", True):
        return []
    loaded: list[str] = []
    for path in _discover():
        name = _plugin_name(path)
        try:
            module = _load_module(path)
            get_confirm = getattr(module, "PLUGIN_CONFIRM", False)
            tools = module.plugin_tools()
            registered = 0
            for tool_name, entry in (tools or {}).items():
                fn, schema_d, confirm = _normalize(entry)
                full = f"{name}_{tool_name}"
                fn = _confirm_wrapper(fn, full) if (confirm or get_confirm) else fn
                registry.register_tool(full, fn)
                _REGISTERED_NAMES.add(full)
                if schema_d:
                    schema_d = dict(schema_d)
                    schema_d["name"] = full
                    schema.register_schema(
                        {
                            "type": "function",
                            "function": {
                                "name": full,
                                "description": schema_d.get("description", f"Plugin {name} tool {tool_name}."),
                                "parameters": schema_d.get("parameters", {"type": "object", "properties": {}}),
                            },
                        }
                    )
                registered += 1
            if hasattr(module, "on_load"):
                module.on_load()
            loaded.append(f"{name} ({registered} tool{'s' if registered != 1 else ''})")
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[plugins] failed to load '{name}': {e}\n")
    return loaded


def unload_plugins() -> None:
    """Unregister every dynamically loaded plugin tool."""
    for path in _discover():
        name = _plugin_name(path)
        try:
            module = sys.modules.get(f"sopno_plugin_{name}")
            if module is not None and hasattr(module, "on_unload"):
                module.on_unload()
        except Exception:  # noqa: BLE001
            pass
    for tool in list(_REGISTERED_NAMES):
        registry.unregister_tool(tool)
        schema.unregister_schema(tool)
    _REGISTERED_NAMES.clear()
