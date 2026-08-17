"""
sopno/ui/hud/dashboard.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Read-only dashboard panel: settings (config.json), long-term memory,
tool status, live logs, and local Ollama models. Reads the same config,
settings, memory, and registry objects the CLI/assistant use — no copies.
"""

from __future__ import annotations

import json
from typing import Optional

from PyQt5.QtWidgets import (
    QPlainTextEdit,
    QTabWidget,
)

from sopno.config.settings import settings

_SECRET_KEYS = ("password", "token", "secret", "apikey", "api_key", "api-key")
_MAX_MEMORY_ROWS = 200
_MAX_LOG_ROWS = 500


def _mask(key: str, value) -> str:
    if any(s in key.lower() for s in _SECRET_KEYS):
        return "********"
    return str(value)


class DashboardPanel(QTabWidget):
    """Six read-only tabs backed directly by the live config/state objects."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Dashboard")
        self._log_edit: Optional[QPlainTextEdit] = None

        self._settings_tab = self._build_tab("Settings")
        self._memory_tab = self._build_tab("Memory")
        self._agents_tab = self._build_tab("Agents")
        self._tools_tab = self._build_tab("Tools")
        self._logs_tab = self._build_tab("Logs")
        self._models_tab = self._build_tab("Models")
        self._log_edit = self._logs_tab

        self.addTab(self._settings_tab, "Settings")
        self.addTab(self._memory_tab, "Memory")
        self.addTab(self._agents_tab, "Agents")
        self.addTab(self._tools_tab, "Tools")
        self.addTab(self._logs_tab, "Logs")
        self.addTab(self._models_tab, "Models")

        self.setStyleSheet("""
            QTabWidget::pane { border: 1px solid rgba(255, 255, 255, 0.07);
                               border-radius: 12px; background: rgba(255, 255, 255, 0.02); }
            QTabBar::tab { color: #8B9BB4; padding: 4px 10px;
                           background: transparent; border-top-left-radius: 8px;
                           border-top-right-radius: 8px; }
            QTabBar::tab:selected { color: #E4EAF2; background: rgba(94, 177, 245, 0.18); }
        """)
        self.refresh()
        self.setVisible(False)

    @staticmethod
    def _build_tab(placeholder: str) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        edit.setStyleSheet(
            "QPlainTextEdit { background: rgba(0, 0, 0, 0.25); color: #C3CFDF;"
            " border: none; border-radius: 8px; padding: 6px;"
            " font-family: 'IBM Plex Mono'; font-size: 10px; }"
        )
        edit.setPlaceholderText(placeholder)
        return edit

    def append_log(self, text: str) -> None:
        """Live log feed (connected to the assistant's log_message signal)."""
        if self._log_edit is None:
            return
        doc = self._log_edit.document()
        if doc.blockCount() > _MAX_LOG_ROWS:
            self._log_edit.clear()
        self._log_edit.appendPlainText(text)

    def refresh(self) -> None:
        """Re-read the live sources for the static tabs."""
        self._settings_tab.setPlainText(self._settings_text())
        self._memory_tab.setPlainText(self._memory_text())
        self._agents_tab.setPlainText(self._agents_text())
        self._tools_tab.setPlainText(self._tools_text())
        self._models_tab.setPlainText(self._models_text())

    # ── Tab content builders ──────────────────────────────────────────────

    def _settings_text(self) -> str:
        lines = ["# config.json + runtime settings\n"]
        cfg = settings.project_root / "config.json"
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                for key in sorted(data):
                    lines.append(f"{key} = {_mask(key, data[key])}")
            except (OSError, ValueError) as e:
                lines.append(f"(could not read config.json: {e})")
        else:
            lines.append("(no config.json found)")
        lines.append("\n# active settings snapshot")
        for name in sorted(dir(settings)):
            if name.startswith("_") or name in ("project_root",):
                continue
            val = getattr(settings, name)
            if isinstance(val, (str, int, float, bool)):
                lines.append(f"{name} = {_mask(name, val)}")
        return "\n".join(lines)

    def _memory_text(self) -> str:
        try:
            from sopno.memory.store import MemoryStore

            store = MemoryStore(settings.memory_path)
        except Exception as e:  # noqa: BLE001
            return f"Memory store unavailable: {e}"
        try:
            stats = store.stats()
            lines = [f"total active: {stats['total']}", ""]
            for cat, n in stats.get("by_category", {}).items():
                lines.append(f"  {cat}: {n}")
            lines.append("")
            lines.append("# most important / recent")
            for mem in store.all(active_only=True, limit=_MAX_MEMORY_ROWS):
                marker = "★" if mem.get("importance", 0) >= 3 else " "
                lines.append(f"{marker} [{mem.get('category', '?')}] {mem['content']}")
            return "\n".join(lines)
        finally:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass

    def _agents_text(self) -> str:
        try:
            from sopno.core.agents.session import get_store
            from sopno.core.agents.worker import get_workers
            from sopno.tools.builtins.automation.coding import _coding_record

            agents = get_store().list()
            workers = get_workers()
        except Exception as e:  # noqa: BLE001
            return f"Agent store unavailable: {e}"
        lines = [f"# {len(workers)} worker(s), {len(agents)} agent(s)\n"]
        if not agents:
            lines.append("(no background agents — try agent_create or coding_run)")
        for agent in agents:
            record = _coding_record(agent)
            branch = f" | branch {record.get('branch', '')}" if record else ""
            budget = agent.get("budget") or {}
            budget_txt = ", ".join(f"{k}={v}" for k, v in budget.items()) or "default"
            lines.append(
                f"[{agent['state']}/{agent['status']}] "
                f"#{agent['id']} {agent['name']} "
                f"({agent.get('kind', 'general')}){branch}"
            )
            lines.append(f"  goal: {agent['goal'][:160]}")
            lines.append(
                f"  budget: {budget_txt} | used {agent['budget_used']} turns | "
                f"memory {len(agent.get('working_memory') or [])} entries"
            )
            if agent.get("pending_action"):
                lines.append(
                    "  pending approval: "
                    f"{(agent['pending_action'].get('description') or '?')[:120]}"
                )
            lines.append("")
        return "\n".join(lines).rstrip()

    def _tools_text(self) -> str:
        try:
            from sopno.tools.registry import get_registered_names

            names = get_registered_names()
        except Exception as e:  # noqa: BLE001
            return f"Tool registry unavailable: {e}"
        lines = [f"# {len(names)} tools registered\n"]
        lines.extend(f"{name}" for name in sorted(names))
        return "\n".join(lines)

    def _models_text(self) -> str:
        try:
            import ollama

            listing = ollama.list()
            models = listing.get("models", [])
        except Exception as e:  # noqa: BLE001
            return f"Ollama unreachable: {e}"
        lines = [f"# {len(models)} local model(s)\n"]
        for m in models:
            name = m.get("model") if isinstance(m, dict) else getattr(m, "model", "?")
            lines.append(name)
        return "\n".join(lines)
