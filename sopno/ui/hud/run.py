"""
sopno/ui/hud/run.py
━━━━━━━━━━━━━━━━━━
HUD bootstrapping, hot-reload watcher, and the public entry point.
"""

import os
import sys
from pathlib import Path

from PyQt5.QtCore import QFileSystemWatcher, QTimer
from PyQt5.QtWidgets import QApplication

from sopno.ui.hud.window import SopnoHUDWindow


def _watch_paths_for_reload() -> list[str]:
    """Watch every module in this package plus the shared brain files."""
    hud_root = Path(__file__).resolve().parent
    paths = [str(p) for p in hud_root.glob("*.py") if p.exists()]
    for extra in (
        hud_root.parent.parent / "config" / "settings.py",
        hud_root.parent.parent / "core" / "assistant.py",
    ):
        if extra.exists():
            paths.append(str(extra))
    return paths


def _restart_process() -> None:
    print("\n[HUD] File change detected — restarting…\n", flush=True)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _install_hot_reload(app: QApplication) -> QFileSystemWatcher:
    watcher = QFileSystemWatcher(app)
    for path in _watch_paths_for_reload():
        watcher.addPath(path)
        print(f"[HUD] Watching for reload: {path}")

    debounce = QTimer(app)
    debounce.setSingleShot(True)
    debounce.setInterval(400)
    debounce.timeout.connect(_restart_process)

    def on_changed(path: str) -> None:
        if path and Path(path).exists() and path not in watcher.files():
            watcher.addPath(path)
        if not debounce.isActive():
            debounce.start()

    watcher.fileChanged.connect(on_changed)
    return watcher


def run_hud(*, reload: bool = False) -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet("""
        QToolTip {
            background-color: #141A24;
            color: #D7DEE9;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 6px;
            padding: 6px 8px;
            font-size: 11px;
        }
    """)

    if reload:
        _install_hot_reload(app)
        print("[HUD] Hot reload enabled.")
    window = SopnoHUDWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_hud(reload="--reload" in sys.argv)
