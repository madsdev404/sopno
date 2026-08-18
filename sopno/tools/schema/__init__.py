"""
sopno/tools/schema/__init__.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JSON schemas for the LLM tool-calling API.

``TOOLS_SCHEMA`` is the static base set (one list per tool category).
Dynamic tools (plugins, MCP clients) are appended at runtime via
``register_schema`` / ``unregister_schema`` and included in the snapshot
returned by ``get_schema()`` — the LLM prompt must always use
``get_schema()`` so the dynamic tools are visible.

``get_schema_for(text)`` selects only the tools relevant to a user
utterance, keeping the LLM context small enough for CPU-only models.
"""

import re
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

# ── Intent → tool routing ──────────────────────────────────────────
# Maps regex patterns to the tool names relevant for that intent.
# Only matching tools are sent to the LLM, keeping context small.

_ROUTING: list[tuple[re.Pattern, list[str]]] = [
    # Web / search / research / poetry / creative content
    (re.compile(
        r"\b(?:search|google|find|look\s+up|fetch|browse|navigate|"
        r"open\s+(?:a\s+)?website|go\s+to\s+website|webpage|"
        r"latest|news|update|fact|define|explain|who\s+is|what\s+is|what\s+are|"
        r"tell\s+me\s+about|find\s+out|"
        r"poem|poetry|kobita|kobita|shairi|ghazal|gazal|"
        r"romantic|love\s+poem|bangla\s+poem|bengali\s+poem)\b", re.I),
     ["search_web", "fetch_url",
      "browser_navigate", "browser_click", "browser_type",
      "browser_extract", "browser_screenshot", "browser_back", "browser_close"]),
    # Heavy research (in-depth, multi-page) — only when explicitly requested
    (re.compile(
        r"\b(?:research|in[- ]?depth|deep\s+dive|investigate|analyze)\b", re.I),
     ["research"]),
    # Terminal / shell / dev / system commands
    (re.compile(
        r"\b(?:terminal|command|shell|run|execute|install|apt|pip|sudo|git|bash|"
        r"script|compile|build|ping|curl|wget|kill|process|restart|download|"
        r"service|cron|log|journal|systemctl|ps\s+aux|"
        r"uninstall|package|pacman|flatpak)\b", re.I),
     ["run_terminal", "terminal_send", "terminal_status",
      "list_processes", "kill_process", "manage_service",
      "read_logs", "manage_cron", "install_package", "uninstall_package"]),
    # Git
    (re.compile(
        r"\bgit\b", re.I),
     ["git_status", "git_log", "git_diff", "git_branch",
      "git_add", "git_commit", "git_stash", "git_commit_message"]),
    # Files / folders / notes
    (re.compile(
        r"\b(?:file|folder|directory|create|edit|delete|rename|overwrite|write|"
        r"notes?|note\b|copy|duplicate|move|grep|"
        r"read\s+pdf|pdf|docx|xlsx|image|scan)\b", re.I),
     ["read_file", "write_file", "edit_file", "list_directory",
      "delete_file", "rename_file", "copy_file", "move_file",
      "search_files", "note_write", "note_list", "note_search"]),
    # System / hardware / apps / media / clipboard
    (re.compile(
        r"\b(?:open|launch|start|close|volume|mute|unmute|"
        r"play|pause|resume|next|previous|skip|"
        r"time|date|clock|battery|cpu|ram|memory|stats|status|system|"
        r"media|music|song|spotify|browser|chrome|firefox|vscode|"
        r"clipboard|copy\s+that|screenshot|screen\s+shot|windows|window|focus|"
        r"type|typing|keyboard|press|keys|key|disk|storage|gpu|"
        r"graphics|network\s+stats|lock)\b", re.I),
     ["get_current_time", "get_system_stats", "get_disk_stats",
      "get_gpu_stats", "get_network_stats", "control_volume",
      "open_application", "lock_screen", "play_media_control",
      "list_windows", "focus_window", "take_screenshot",
      "clipboard_get", "clipboard_set", "send_keys", "press_key",
      "ping_host", "traceroute", "wifi_scan", "public_ip", "firewall_status"]),
    # Reminders / calendar / email
    (re.compile(
        r"\b(?:remind|reminder|reminders|timer|alert|schedule|remind\s+me|"
        r"email|mail|inbox|calendar|event|meeting)\b", re.I),
     ["set_reminder", "list_reminders", "cancel_reminder",
      "email_read", "email_send", "calendar_list", "calendar_create_event"]),
    # Database / SQL
    (re.compile(
        r"\b(?:database|sql|query)\b", re.I),
     ["query_database", "explain_schema", "backup_database"]),
    # Vision / OCR
    (re.compile(
        r"\b(?:ocr|vision|describe\s+(?:a\s+)?(?:image|picture|screenshot))\b", re.I),
     ["describe_screenshot", "ocr_image"]),
    # Rules / automation
    (re.compile(
        r"\b(?:rule|automation|automate|trigger|condition)\b", re.I),
     ["rule_add", "rule_list", "rule_remove", "rule_set_enabled"]),
    # Agents / subagents / coding
    (re.compile(
        r"\b(?:agent|subagent|delegate|coding|code\s+review|write\s+code|"
        r"write\s+commit|write\s+message)\b", re.I),
     ["run_subagent", "subagent_list",
      "agent_create", "agent_list", "agent_status", "agent_send",
      "agent_pause", "agent_resume", "agent_kill", "agent_log", "agent_align",
      "coding_run", "coding_status"]),
]


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


def get_schema_for(text: str) -> list[dict[str, Any]]:
    """Return only tools relevant to *text*, keeping LLM context small.

    Matches the user utterance against intent patterns and collects the
    union of matching tool names.  Returns the full schema if no intent
    matches (fallback — the LLM decides).
    """
    all_names: set[str] = set()
    for pattern, names in _ROUTING:
        if pattern.search(text):
            all_names.update(names)

    if not all_names:
        return []

    full = get_schema()
    filtered = [s for s in full if s.get("function", {}).get("name") in all_names]
    return filtered if filtered else full
