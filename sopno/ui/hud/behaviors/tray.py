"""
sopno/ui/hud/behaviors/tray.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
System tray icon and show/hide behaviour mixin.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon


class TrayMixin:
    """System tray integration: icon, menu, show/hide toggling."""

    def init_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        g = QRadialGradient(16, 16, 14)
        g.setColorAt(0.0, QColor(94, 177, 245))
        g.setColorAt(0.7, QColor(12, 16, 24))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(g)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()

        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("Sopno")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #0C1018;
                color: #D7DEE9;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item { padding: 6px 16px; border-radius: 4px; }
            QMenu::item:selected { background: rgba(94,177,245,0.14); color: #B8D9F8; }
        """)
        show_a = QAction("Show HUD", self)
        show_a.triggered.connect(self.restore_hud)
        menu.addAction(show_a)
        hide_a = QAction("Hide HUD", self)
        hide_a.triggered.connect(self.hide_hud)
        menu.addAction(hide_a)
        menu.addSeparator()
        for key, label in (("small", "Size: Small"), ("medium", "Size: Medium"), ("full", "Size: Full")):
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, k=key: self.apply_size_preset(k))
            menu.addAction(act)
        menu.addSeparator()
        exit_a = QAction("Exit", self)
        exit_a.triggered.connect(self.close_app)
        menu.addAction(exit_a)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.hide_hud() if self.isVisible() else self.restore_hud()

    def hide_hud(self) -> None:
        self.hide()
        if hasattr(self, "worker") and self.worker:
            self.worker.log_message.emit("Hidden to tray.")

    def restore_hud(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
