"""
sopno/ui/hud/widgets/chat.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Selectable chat bubbles via QTextBrowser. Plain <p> tags for text
(selection works). QPainter draws rounded bubble backgrounds auto-sized
from QTextBlock layout.
"""

import html as _html
from datetime import datetime

from PyQt5.QtCore import QPointF, QRect, Qt, QTimer
from PyQt5.QtGui import (QColor, QFont, QPainter, QPainterPath,
                         QTextBlockFormat, QTextCursor, QTextLine)
from PyQt5.QtWidgets import QTextBrowser

from sopno.ui.hud.visuals.theme import motion_enabled

_MAX_BLOCKS = 60
_DOTS = "\u25cf\u00a0\u00a0\u25cb\u00a0\u00a0\u25cf"

_C_USER = "#D6EBFF"
_C_ASSIST = "#E8EEF7"
_C_ERROR = "#FFB4BA"
_C_MUTED = "#6B7C94"

_BUBBLE_PAD_X = 14
_BUBBLE_PAD_Y = 12
_CORNER = 14
_CORNER_TAIL = 5

_VIEWPORT_MARGINS = (14, 12, 14, 10)
_USER_MAX_RATIO = 0.78
_ASSIST_MAX_RATIO = 0.82
_GAP_GROUPED = 8
_GAP_SEPARATE = 20

_DOT_R = 2.6
_DOT_GAP = 6.0
_DOT_AMP = 5.0
_DOT_PERIOD = 1.0


def _bubble_path(x: float, y: float, w: float, h: float, *,
                 tail: str | None) -> QPainterPath:
    """Rounded rect with one small corner (chat tail). tail: 'br' | 'bl' | None."""
    tl = tr = br = bl = _CORNER
    if tail == "br":
        br = _CORNER_TAIL
    elif tail == "bl":
        bl = _CORNER_TAIL

    path = QPainterPath()
    path.moveTo(x + tl, y)
    path.lineTo(x + w - tr, y)
    path.quadTo(x + w, y, x + w, y + tr)
    path.lineTo(x + w, y + h - br)
    path.quadTo(x + w, y + h, x + w - br, y + h)
    path.lineTo(x + bl, y + h)
    path.quadTo(x, y + h, x, y + h - bl)
    path.lineTo(x, y + tl)
    path.quadTo(x, y, x + tl, y)
    path.closeSubpath()
    return path


class ChatThread(QTextBrowser):
    """Selectable chat bubbles. User right, assistant left."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setFrameShape(QTextBrowser.NoFrame)
        self.setCursorWidth(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse
            | Qt.TextSelectableByKeyboard
            | Qt.LinksAccessibleByMouse
        )
        self.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                color: #E8EEF7;
            }
            QScrollBar:vertical { background: transparent; width: 4px; margin: 2px 0; }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.14);
                border-radius: 2px;
                min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.setViewportMargins(*_VIEWPORT_MARGINS)
        self.document().setDefaultFont(QFont("IBM Plex Sans", 10))
        self.document().setDocumentMargin(_BUBBLE_PAD_Y)

        self._blocks: list[dict] = []
        self._typing = False
        self._dots_clock = 0.0
        self._dots_timer = QTimer(self)
        self._dots_timer.setInterval(33)
        self._dots_timer.timeout.connect(self._tick_dots)
        self._follow = True
        self._col_width: int | None = None

        self.verticalScrollBar().valueChanged.connect(self._track_scroll)
        self._render()

    # ── Public API ─────────────────────────────────────────────────────────
    def add_message(self, role: str, text: str, *,
                    ts: datetime | None = None,
                    streaming: bool = False) -> None:
        text = (text or "").rstrip()
        if not text and not streaming and not self._typing:
            return
        if self._typing:
            self._typing = False
        self._blocks.append({
            "role": role,
            "text": text,
            "ts": ts or datetime.now(),
            "interrupted": False,
            "streaming": bool(streaming),
        })
        while len(self._blocks) > _MAX_BLOCKS:
            self._blocks.pop(0)
        self._scroll_to_bottom = True
        self._render()

    def append_stream_text(self, chunk: str) -> None:
        if not chunk:
            return
        if not self._blocks or self._blocks[-1]["role"] != "assistant":
            self._blocks.append({"role": "assistant", "text": "",
                                 "ts": datetime.now(),
                                 "interrupted": False, "streaming": True})
        self._blocks[-1]["text"] += chunk
        self._scroll_to_bottom = True
        self._render()

    def finalize_streaming(self, interrupted: bool = False) -> None:
        if self._blocks and self._blocks[-1]["role"] == "assistant":
            self._blocks[-1]["streaming"] = False
            self._blocks[-1]["interrupted"] = bool(interrupted)
        self._render()

    def begin_typing(self) -> None:
        if not self._typing:
            self._typing = True
            self._scroll_to_bottom = True
            self._dots_clock = 0.0
            if motion_enabled():
                self._dots_timer.start()
            self._render()

    def end_typing(self) -> None:
        if self._typing:
            self._typing = False
            self._dots_timer.stop()
            self._dots_clock = 0.0
            self._render()

    def clear_chat(self) -> None:
        self._blocks.clear()
        self._typing = False
        self._dots_timer.stop()
        self._dots_clock = 0.0
        self._render()

    @property
    def is_empty(self) -> bool:
        return not self._blocks

    def set_column_width(self, width: int | None) -> None:
        self._col_width = width
        self._apply_column_width()

    def apply_scale(self, *, body_pt: int, **_ignored) -> None:
        self.document().setDefaultFont(QFont("IBM Plex Sans", max(7, body_pt)))
        self._render()

    def transcript_text(self) -> str:
        who = {"user": "You", "assistant": "Sopno", "error": "Error"}
        lines = []
        for b in self._blocks:
            body = b["text"]
            if b["interrupted"]:
                body += " (interrupted)"
            lines.append(f"{who.get(b['role'], 'Sopno')}: {body}")
        return "\n\n".join(lines)

    # ── Grouping ───────────────────────────────────────────────────────────
    def _is_grouped(self, idx: int) -> bool:
        if idx == 0:
            return False
        prev = self._blocks[idx - 1]
        curr = self._blocks[idx]
        if prev["role"] != curr["role"]:
            return False
        if prev.get("streaming") or curr.get("streaming"):
            return False
        try:
            delta = curr["ts"] - prev["ts"]
            return abs(delta.total_seconds()) < 60
        except Exception:
            return False

    # ── Rendering ──────────────────────────────────────────────────────────
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_column_width()
        doc = self.document()
        if doc.textWidth() <= 0:
            doc.setTextWidth(self._content_width())
        self._apply_block_formats()
        doc.documentLayout().documentSize()
        self.viewport().update()

    def _content_width(self) -> float:
        m = self.viewportMargins()
        return float(max(1, self.viewport().width() - m.left() - m.right()))

    def _doc_width(self) -> float:
        w = self.document().textWidth()
        return float(w if w > 0 else self._content_width())

    def _apply_block_formats(self) -> None:
        """Margins + alignment: text sits padded inside painted bubbles."""
        if not self._blocks and not self._typing:
            return
        doc_w = self._doc_width()
        comp = _BUBBLE_PAD_Y - 2.0
        block = self.document().firstBlock()
        idx = 0
        while block.isValid() and idx < len(self._blocks):
            b = self._blocks[idx]
            role = b["role"]
            grouped = self._is_grouped(idx)
            gap = _GAP_GROUPED if grouped else _GAP_SEPARATE

            fmt = QTextBlockFormat()
            fmt.setTopMargin((gap + _BUBBLE_PAD_Y) if idx > 0 else _BUBBLE_PAD_Y)
            fmt.setBottomMargin(_BUBBLE_PAD_Y)
            if role == "user":
                fmt.setAlignment(Qt.AlignRight)
                max_w = doc_w * _USER_MAX_RATIO
                fmt.setLeftMargin(max(0.0, doc_w - max_w - comp))
                fmt.setRightMargin(_BUBBLE_PAD_X - comp)
            else:
                fmt.setAlignment(Qt.AlignLeft)
                fmt.setLeftMargin(_BUBBLE_PAD_X - comp)
                fmt.setRightMargin(max(0.0, doc_w - doc_w * _ASSIST_MAX_RATIO - comp))

            QTextCursor(block).setBlockFormat(fmt)
            block = block.next()
            idx += 1

        if self._typing and block.isValid():
            fmt = QTextBlockFormat()
            fmt.setAlignment(Qt.AlignLeft)
            fmt.setTopMargin(_GAP_SEPARATE + _BUBBLE_PAD_Y if self._blocks else _BUBBLE_PAD_Y)
            fmt.setBottomMargin(_BUBBLE_PAD_Y)
            fmt.setLeftMargin(_BUBBLE_PAD_X - comp)
            fmt.setRightMargin(max(0.0, doc_w - doc_w * _ASSIST_MAX_RATIO - comp))
            QTextCursor(block).setBlockFormat(fmt)

    @staticmethod
    def _text_bounds(block, br) -> tuple[float, float, float, float] | None:
        layout = block.layout()
        if layout is None or layout.lineCount() < 1:
            return None
        pos = layout.position()
        ox = pos.x()
        oy = pos.y()
        left = top = float("inf")
        right = bottom = 0.0
        for i in range(layout.lineCount()):
            line = layout.lineAt(i)
            start = line.textStart()
            line_left = ox + line.cursorToX(start, QTextLine.Leading)[0]
            line_right = ox + line.cursorToX(start + line.textLength(), QTextLine.Trailing)[0]
            ly = oy + line.y()
            lh = line.height()
            left = min(left, line_left)
            right = max(right, line_right)
            top = min(top, ly)
            bottom = max(bottom, ly + lh)
        if left is float("inf"):
            return None
        return left, top, right, bottom

    def _apply_column_width(self) -> None:
        cw = self._content_width()
        if self._col_width and cw > self._col_width + 40:
            self.document().setTextWidth(float(self._col_width))
        else:
            self.document().setTextWidth(cw)

    def paintEvent(self, event) -> None:
        self._paint_bubbles()
        super().paintEvent(event)
        self._paint_typing_dots()

    def _doc_x_offset(self, content_w: float) -> float:
        doc_w = self.document().textWidth()
        if 0 < doc_w < content_w:
            return (content_w - doc_w) / 2.0
        return 0.0

    def _paint_origin(self) -> tuple[float, float]:
        """Paint coords == doc coords (up to vertical scroll).

        QTextBrowser already shifts the document (and our painted bubbles)
        by the viewport margins; the only extra translation we must add is
        the scroll offset, otherwise the margin cancels the bubble padding.
        """
        return 0.0, -float(self.verticalScrollBar().value())

    def _bubble_rect(self, left: float, top: float, right: float, bottom: float, *,
                     origin_x: float, origin_y: float, doc_x: float,
                     max_right: float) -> tuple[float, float, float, float]:
        bx = origin_x + doc_x + left - _BUBBLE_PAD_X
        by = origin_y + top - _BUBBLE_PAD_Y
        bw = (right - left) + _BUBBLE_PAD_X * 2
        bh = (bottom - top) + _BUBBLE_PAD_Y * 2
        if bx + bw > max_right:
            bx = max(origin_x, max_right - bw)
        return bx, by, bw, bh

    def _paint_bubbles(self) -> None:
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)

        content_w = self._content_width()
        doc_x = self._doc_x_offset(content_w)
        origin_x, origin_y = self._paint_origin()
        max_right = origin_x + content_w
        dl = self.document().documentLayout()

        block = self.document().begin()
        idx = 0
        while block.isValid() and idx < len(self._blocks):
            b = self._blocks[idx]
            br = dl.blockBoundingRect(block)
            if br.height() < 1:
                block = block.next()
                idx += 1
                continue

            if block.layout().lineCount() < 1:
                block = block.next()
                idx += 1
                continue

            bounds = self._text_bounds(block, br)
            if bounds is None:
                block = block.next()
                idx += 1
                continue
            left, top, right, bottom = bounds

            role = b["role"]
            is_user = role == "user"
            is_error = role == "error"
            grouped = self._is_grouped(idx)

            bx, bubble_y, bw, bubble_h = self._bubble_rect(
                left, top, right, bottom,
                origin_x=origin_x, origin_y=origin_y, doc_x=doc_x,
                max_right=max_right,
            )

            if is_user:
                bg = QColor(94, 177, 245, 72)
                border = QColor(94, 177, 245, 130)
                tail = "br" if not grouped else None
            elif is_error:
                bg = QColor(240, 113, 120, 55)
                border = QColor(240, 113, 120, 120)
                tail = "bl"
            else:
                bg = QColor(255, 255, 255, 22)
                border = QColor(255, 255, 255, 38)
                tail = "bl" if not grouped else None

            path = _bubble_path(bx, bubble_y, bw, bubble_h, tail=tail)
            p.setPen(border)
            p.setBrush(bg)
            p.drawPath(path)

            block = block.next()
            idx += 1
        p.end()

    def _track_scroll(self, value: int) -> None:
        bar = self.verticalScrollBar()
        self._follow = value >= bar.maximum() - 6

    def _typing_block(self):
        idx = 0
        block = self.document().begin()
        while block.isValid():
            if idx == len(self._blocks):
                return block
            block = block.next()
            idx += 1
        return None

    def _typing_dot_rect(self) -> QRect | None:
        if not self._typing:
            return None
        block = self._typing_block()
        if block is None:
            return None
        br = self.document().documentLayout().blockBoundingRect(block)
        if br.height() < 1:
            return None
        bounds = self._text_bounds(block, br)
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        ox, oy = self._paint_origin()
        x = int(ox + self._doc_x_offset(self._content_width()) + left - _BUBBLE_PAD_X)
        y = int(oy + top - _BUBBLE_PAD_Y)
        return QRect(x, y,
                     int(right - left) + _BUBBLE_PAD_X * 2,
                     int(bottom - top) + _BUBBLE_PAD_Y * 2)

    def _tick_dots(self) -> None:
        if not self._typing:
            self._dots_timer.stop()
            return
        self._dots_clock += 0.033
        rect = self._typing_dot_rect()
        if rect is None:
            self.viewport().update()
        else:
            self.viewport().update(rect)

    def _paint_typing_dots(self) -> None:
        if not self._typing:
            return
        block = self._typing_block()
        if block is None:
            return
        br = self.document().documentLayout().blockBoundingRect(block)
        if br.height() < 1:
            return
        bounds = self._text_bounds(block, br)
        if bounds is None:
            return
        left, top, right, bottom = bounds
        content_w = self._content_width()
        doc_x = self._doc_x_offset(content_w)
        ox, oy = self._paint_origin()
        px = ox + doc_x + left
        cy = oy + (top + bottom) / 2.0

        p = QPainter(self.viewport())
        if not p.isActive():
            return
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_C_MUTED))

        active = self._dots_timer.isActive()
        cx = px + _DOT_R
        for i in range(3):
            yoff = 0.0
            if active and motion_enabled():
                t = (self._dots_clock / _DOT_PERIOD + i / 3.0) % 1.0
                if t < 0.4:
                    k = t / 0.4
                    yoff = -_DOT_AMP * (1.0 - k * k)
            p.drawEllipse(QPointF(cx, cy + yoff), _DOT_R, _DOT_R)
            cx += _DOT_R * 2 + _DOT_GAP
        p.end()

    def _render(self) -> None:
        bar = self.verticalScrollBar()
        stick = getattr(self, "_scroll_to_bottom", False) or self._follow
        self.setHtml(self._build_html())
        self._apply_column_width()
        doc = self.document()
        if doc.textWidth() <= 0:
            doc.setTextWidth(self._content_width())
        self._apply_block_formats()
        doc.documentLayout().documentSize()
        if stick:
            bar.setValue(bar.maximum())
        self._scroll_to_bottom = False

    def _build_html(self) -> str:
        parts: list[str] = []
        for b in self._blocks:
            role = b["role"]
            is_user = role == "user"
            is_error = role == "error"

            body = _html.escape(b["text"]).replace("\n", "<br>")
            if b["interrupted"]:
                body += (f'<br><span style="color:{_C_MUTED};font-size:0.92em;">'
                         "(interrupted)</span>")

            text_color = _C_ERROR if is_error else (
                _C_USER if is_user else _C_ASSIST
            )
            weight = "500" if is_user else "400"

            parts.append(
                f'<p style="margin:0; padding:0; line-height:1.45;">'
                f'<span style="color:{text_color}; font-weight:{weight};">{body}</span></p>'
            )

        if self._typing:
            parts.append(
                f'<p style="margin:0;">'
                f'<span style="color:transparent; letter-spacing:2px;">{_DOTS}</span></p>'
            )

        parts.append('<p style="margin:0; font-size:4px; color:transparent;">&nbsp;</p>')

        return "".join(parts) or '<p style="margin:0;"></p>'
