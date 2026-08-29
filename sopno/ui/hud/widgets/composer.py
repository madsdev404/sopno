"""
sopno/ui/hud/widgets/composer.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Text-mode composer: auto-growing input + send/stop button in one glass dock.
"""

from __future__ import annotations

from PyQt5.QtCore import QEvent, Qt, QTimer, QSize, QRect, pyqtSignal
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from sopno.ui.hud.visuals.icons import _paint_icon
from sopno.ui.hud.visuals.theme import _ICON_BTN

_MAX_INPUT_H = 120


class ChatComposer(QFrame):
    """ChatGPT-style composer — rounded glass shell, accent send when ready."""

    submitted = pyqtSignal(str)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Dock")
        self._focused = False
        self._generating = False
        self._resizing = False
        self._metrics: dict = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)

        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText("Type a message…")
        self.text_input.setToolTip(
            "Type a message and press Enter to send\nShift+Enter for a new line"
        )
        self.text_input.setFont(QFont("IBM Plex Sans", 10))
        self.text_input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_input.setTabChangesFocus(True)
        self.text_input.document().setDocumentMargin(0)
        self.text_input.setStyleSheet("""
            QPlainTextEdit {
                background: transparent;
                color: #E8EEF7;
                border: none;
                padding: 1px 2px;
                selection-background-color: rgba(94, 177, 245, 0.35);
            }
            QScrollBar:vertical { background: transparent; width: 3px; }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.14); border-radius: 1px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.text_input.document().contentsChanged.connect(self._schedule_resize)
        self.text_input.textChanged.connect(self._sync_send_state)
        self.text_input.installEventFilter(self)

        btn_slot = QWidget()
        btn_slot.setAttribute(Qt.WA_TranslucentBackground)
        btn_lay = QVBoxLayout(btn_slot)
        btn_lay.setContentsMargins(0, 0, 0, 1)
        btn_lay.addStretch(1)

        self.send_btn = QPushButton()
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setIconSize(self.send_btn.iconSize())
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFocusPolicy(Qt.NoFocus)
        self.send_btn.setToolTip("Send message")
        self.send_btn.setProperty("icon_kind", "send")
        self.send_btn.clicked.connect(self._on_send_clicked)
        btn_lay.addWidget(self.send_btn)

        row.addWidget(self.text_input, 1)
        row.addWidget(btn_slot, 0)

        self._sync_send_state()
        self._apply_shell_style()
        QTimer.singleShot(0, self._auto_resize)

    # ── Public API ───────────────────────────────────────────────────────────
    def apply_scale(self, *, body_pt: int, send: int = 32, send_icon: int = 16,
                    mode_r: int = 12, **_ignored) -> None:
        self._metrics = {"send": send, "send_icon": send_icon, "mode_r": mode_r}
        self.text_input.setFont(QFont("IBM Plex Sans", body_pt))
        self.send_btn.setFixedSize(send, send)
        self.send_btn.setIconSize(self.send_btn.iconSize())
        self._sync_send_state()
        self._apply_shell_style()
        self._auto_resize()

    def set_generating(self, busy: bool) -> None:
        busy = bool(busy)
        if self._generating == busy:
            return
        self._generating = busy
        self._sync_send_state()

    def focus_input(self) -> None:
        self.text_input.setFocus()

    def refresh_height(self) -> None:
        self._auto_resize()

    def clear_input(self) -> None:
        self.text_input.clear()
        self._auto_resize()

    # ── Events ───────────────────────────────────────────────────────────────
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.text_input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self._submit()
                return True
        if obj is self.text_input and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            focused = event.type() == QEvent.FocusIn
            if focused != self._focused:
                self._focused = focused
                self._apply_shell_style()
        return super().eventFilter(obj, event)

    # ── Internals ────────────────────────────────────────────────────────────
    def _on_send_clicked(self) -> None:
        if self._generating:
            self.stop_requested.emit()
        else:
            self._submit()

    def _submit(self) -> None:
        if self._generating:
            return
        text = self.text_input.toPlainText().strip()
        if not text:
            return
        self.text_input.clear()
        self._auto_resize()
        self.submitted.emit(text)

    def _sync_send_state(self) -> None:
        has_text = bool(self.text_input.toPlainText().strip())
        m = self._metrics
        size = m.get("send", 32)
        icon = m.get("send_icon", 16)

        if self._generating:
            kind = "square"
            active = True
            self.send_btn.setToolTip("Stop generating")
            self.send_btn.setEnabled(True)
            bg = "rgba(240, 113, 120, 0.14)"
            border = "rgba(240, 113, 120, 0.55)"
            hbg, hb = "rgba(240, 113, 120, 0.22)", "rgba(240, 113, 120, 0.70)"
            pbg = "rgba(240, 113, 120, 0.32)"
        elif has_text:
            kind = "send"
            active = True
            self.send_btn.setToolTip("Send message")
            self.send_btn.setEnabled(True)
            bg = "rgba(94, 177, 245, 0.88)"
            border = "rgba(94, 177, 245, 0.95)"
            hbg, hb = "rgba(110, 190, 255, 0.95)", "rgba(130, 200, 255, 1.0)"
            pbg = "rgba(80, 165, 235, 1.0)"
        else:
            kind = "send"
            active = False
            self.send_btn.setToolTip("Send message")
            self.send_btn.setEnabled(False)
            bg = "rgba(255, 255, 255, 0.04)"
            border = "rgba(255, 255, 255, 0.08)"
            hbg, hb = "rgba(255, 255, 255, 0.07)", "rgba(255, 255, 255, 0.12)"
            pbg = "rgba(255, 255, 255, 0.10)"

        self.send_btn.setProperty("icon_kind", kind)
        self.send_btn.setIconSize(QSize(icon, icon))
        self.send_btn.setIcon(_paint_icon(kind, size, active=active))
        self.send_btn.setStyleSheet(_ICON_BTN.format(
            bg=bg, border=border, hover_bg=hbg, hover_border=hb, pressed_bg=pbg,
        ))

    def _apply_shell_style(self) -> None:
        radius = max(16, self._metrics.get("mode_r", 12) + 4)
        if self._focused:
            border = "rgba(94, 177, 245, 0.42)"
            bg = "rgba(255, 255, 255, 0.065)"
        else:
            border = "rgba(255, 255, 255, 0.08)"
            bg = "rgba(255, 255, 255, 0.045)"
        self.setStyleSheet(f"""
            QFrame#Dock {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {radius}px;
            }}
        """)

    def _schedule_resize(self) -> None:
        QTimer.singleShot(0, self._auto_resize)

    def _auto_resize(self) -> None:
        if self._resizing:
            return
        self._resizing = True
        try:
            inp = self.text_input
            fm = QFontMetrics(inp.font())
            min_h = fm.height() + 16
            width = max(40, inp.viewport().width() - 3)
            h = self._content_height(width) + 14
            inp.setFixedHeight(int(max(min_h, min(h, _MAX_INPUT_H))))
        finally:
            self._resizing = False

    def _content_height(self, width: int) -> int:
        inp = self.text_input
        doc = inp.document()
        fm = QFontMetrics(inp.font())
        lines = 0
        for i in range(doc.blockCount()):
            text = doc.findBlockByNumber(i).text()
            if not text:
                lines += 1
                continue
            br = fm.boundingRect(QRect(0, 0, width, 10000), Qt.TextWordWrap, text)
            lines += max(1, -(-br.height() // max(1, fm.height())))
        return int(lines * fm.height() + doc.documentMargin() * 2)
