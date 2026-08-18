"""
sopno/ui/hud/behaviors/resizing.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Edge-drag resizing and window dragging mixin.
"""

from PyQt5.QtCore import QPoint, QRect, Qt

from sopno.ui.hud.visuals.theme import EDGE, MAX_SIZE, MIN_SIZE


class ResizeMixin:
    """Free-form edge drag-resize plus plain window dragging."""

    def _edge_at(self, pos: QPoint) -> str | None:
        r = self.rect()
        x, y = pos.x(), pos.y()
        left = x <= EDGE
        right = x >= r.width() - EDGE
        top = y <= EDGE
        bottom = y >= r.height() - EDGE
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return None

    def _cursor_for_edge(self, edge: str | None):
        return {
            "l": Qt.SizeHorCursor,
            "r": Qt.SizeHorCursor,
            "t": Qt.SizeVerCursor,
            "b": Qt.SizeVerCursor,
            "tl": Qt.SizeFDiagCursor,
            "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor,
            "bl": Qt.SizeBDiagCursor,
        }.get(edge, Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        edge = self._edge_at(event.pos())
        if edge:
            self._resize_edge = edge
            self._press_geo = self.geometry()
            self._press_global = event.globalPos()
            self.old_pos = None
        else:
            self._resize_edge = None
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event) -> None:
        if self._resize_edge and self._press_geo is not None and self._press_global is not None:
            delta = event.globalPos() - self._press_global
            g = QRect(self._press_geo)
            e = self._resize_edge
            if "l" in e:
                g.setLeft(g.left() + delta.x())
            if "r" in e:
                g.setRight(g.right() + delta.x())
            if "t" in e:
                g.setTop(g.top() + delta.y())
            if "b" in e:
                g.setBottom(g.bottom() + delta.y())

            # Enforce min
            if g.width() < MIN_SIZE[0]:
                if "l" in e:
                    g.setLeft(g.right() - MIN_SIZE[0])
                else:
                    g.setWidth(MIN_SIZE[0])
            if g.height() < MIN_SIZE[1]:
                if "t" in e:
                    g.setTop(g.bottom() - MIN_SIZE[1])
                else:
                    g.setHeight(MIN_SIZE[1])

            self.setGeometry(g)
            self.size_mode = "custom"
            self._apply_responsive()
            return

        if self.old_pos is not None:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()
            return

        # Hover cursor for edges
        self.setCursor(self._cursor_for_edge(self._edge_at(event.pos())))

    def mouseReleaseEvent(self, event) -> None:
        self.old_pos = None
        self._resize_edge = None
        self._press_geo = None
        self._press_global = None
        self.setCursor(Qt.ArrowCursor)
