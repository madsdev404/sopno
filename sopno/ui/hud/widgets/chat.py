"""
sopno/ui/hud/widgets/chat.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Conversation thread as ONE selectable rich-text surface (like any normal
app): drag across lines — even across messages — select with the cursor,
copy with Ctrl+C or the native context menu. Flat ChatGPT-style layout:
user turns right-aligned tinted, Sopno's turns plain, errors accented.
No per-message buttons, no timestamps — the page belongs to the text.
"""

import html as _html
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QTextBrowser

_MAX_BLOCKS = 60
_CARET = "\u2548"
_DOTS = "\u25cf\u00a0\u00a0\u00a0\u25cb\u00a0\u00a0\u00a0\u25cf"

_C_USER = "#A9CBEA"
_C_ASSIST = "#E4EAF2"
_C_ERROR = "#F07178"
_C_MUTED = "#5C6B82"


class ChatThread(QTextBrowser):
    """Selectable transcript: native multi-line selection + Ctrl+C."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setFrameShape(QTextBrowser.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Native text behaviour: cursor selects, keyboard copies (§research:
        # "select from cursor and copy using ctrl+c like other apps").
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse
            | Qt.TextSelectableByKeyboard
            | Qt.LinksAccessibleByMouse
        )
        self.setStyleSheet("""
            QTextBrowser {
                background: transparent; border: none; color: #E4EAF2;
            }
            QScrollBar:vertical { background: transparent; width: 3px; }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.12); border-radius: 1px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        self.document().setDefaultFont(QFont("IBM Plex Sans", 10))
        self.document().setDocumentMargin(2)

        # Logical model — rendered to HTML on every change (HUD-scale cheap).
        self._blocks: list[dict] = []
        self._typing = False
        self._caret_on = False
        self._follow = True
        self._col_width: int | None = None

        self.verticalScrollBar().valueChanged.connect(self._track_scroll)
        self._render()

    # ── Public API (unchanged surface for behaviors/tests) ────────────────
    def add_message(self, role: str, text: str, *,
                    ts: datetime | None = None,
                    streaming: bool = False) -> None:
        """Append a turn; consecutive same-role turns merge into one block."""
        text = (text or "").rstrip()
        if not text and not streaming and not self._typing:
            return
        if self._typing:
            self._typing = False
        self._caret_on = bool(streaming)
        if self._blocks and self._blocks[-1]["role"] == role and not streaming:
            prev = self._blocks[-1]["text"]
            self._blocks[-1]["text"] = f"{prev}\n\n{text}" if prev else text
        elif streaming and self._blocks and self._blocks[-1]["role"] == role \
                and self._blocks[-1].get("streaming"):
            pass  # continue an open stream block
        else:
            self._blocks.append(
                {"role": role, "text": text, "interrupted": False,
                 "streaming": bool(streaming)},
            )
        while len(self._blocks) > _MAX_BLOCKS:
            self._blocks.pop(0)
        self._scroll_to_bottom = True
        self._render()

    def append_stream_text(self, chunk: str) -> None:
        """Grow the open streaming block (token-level updates)."""
        if not chunk:
            return
        if not self._blocks or self._blocks[-1]["role"] != "assistant":
            self._blocks.append({"role": "assistant", "text": "",
                                 "interrupted": False, "streaming": True})
        self._blocks[-1]["text"] += chunk
        self._scroll_to_bottom = True
        self._render()

    def finalize_streaming(self, interrupted: bool = False) -> None:
        self._caret_on = False
        if self._blocks and self._blocks[-1]["role"] == "assistant":
            self._blocks[-1]["streaming"] = False
            self._blocks[-1]["interrupted"] = bool(interrupted)
        self._render()

    def begin_typing(self) -> None:
        if not self._typing:
            self._typing = True
            self._scroll_to_bottom = True
            self._render()

    def end_typing(self) -> None:
        if self._typing:
            self._typing = False
            self._render()

    def clear_chat(self) -> None:
        self._blocks.clear()
        self._typing = False
        self._caret_on = False
        self._render()

    @property
    def is_empty(self) -> bool:
        return not self._blocks

    def set_column_width(self, width: int | None) -> None:
        """Wrap the transcript at a fixed measure (~70ch) on wide windows."""
        self._col_width = width
        self._apply_column_width()

    def apply_scale(self, *, body_pt: int, **_ignored) -> None:
        """Responsive hook — the transcript is pure type, so scale the font."""
        self.document().setDefaultFont(QFont("IBM Plex Sans", max(7, body_pt)))
        self._render()

    def transcript_text(self) -> str:
        """Whole conversation as plain text (attribution preserved)."""
        who = {"user": "You", "assistant": "Sopno", "error": "Error"}
        lines = []
        for b in self._blocks:
            body = b["text"]
            if b["interrupted"]:
                body += " (interrupted)"
            lines.append(f"{who.get(b['role'], 'Sopno')}: {body}")
        return "\n\n".join(lines)

    # ── Rendering ─────────────────────────────────────────────────────────
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_column_width()

    def _apply_column_width(self) -> None:
        vw = self.viewport().width()
        if self._col_width and vw > self._col_width + 40:
            self.document().setTextWidth(self._col_width - 8)
        else:
            self.document().setTextWidth(-1)

    def _track_scroll(self, value: int) -> None:
        bar = self.verticalScrollBar()
        self._follow = value >= bar.maximum() - 6

    def _render(self) -> None:
        bar = self.verticalScrollBar()
        stick = getattr(self, "_scroll_to_bottom", False) or self._follow
        self.setHtml(self._build_html())
        if stick:
            bar.setValue(bar.maximum())
        self._scroll_to_bottom = False

    def _build_html(self) -> str:
        colors = {
            "user": _C_USER,
            "assistant": _C_ASSIST,
            "error": _C_ERROR,
        }
        parts: list[str] = []
        for b in self._blocks:
            color = colors.get(b["role"], _C_ASSIST)
            body = _html.escape(b["text"]).replace("\n", "<br>")
            if b.get("streaming"):                      # live caret at edge
                body += f'<span style="color:{_C_ASSIST};">{_CARET}</span>'
            if b["interrupted"]:
                body += (f'<br><span style="color:{_C_MUTED};">'
                         "(interrupted)</span>")
            align = ' align="right"' if b["role"] == "user" else ""
            parts.append(
                f'<p{align} style="margin:5px 0;">'
                f'<span style="color:{color};">{body}</span></p>'
            )
        if self._typing:
            parts.append(
                f'<p style="margin:6px 0;">'
                f'<span style="color:{_C_MUTED};">{_DOTS}</span></p>'
            )
        return "".join(parts) or '<p style="margin:0;"></p>'
