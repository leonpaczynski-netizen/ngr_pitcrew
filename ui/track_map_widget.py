"""Track Map Canvas (QPainter widget — no PyQt dependency in data layer).

Renders TrackMapDrawData primitives from ui.track_map_vm (which is itself
PyQt-free).  Used by the Track Modelling tab.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPolygonF
from PyQt6.QtWidgets import QWidget, QSizePolicy


class TrackMapWidget(QWidget):
    """QPainter-based track map canvas.  Renders TrackMapDrawData primitives.

    Accepts draw data from ui.track_map_vm (which is itself PyQt-free).
    Call set_draw_data() to refresh the display.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._draw_data = None
        self.setMinimumSize(250, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_draw_data(self, data) -> None:
        self._draw_data = data
        self.update()

    def paintEvent(self, event) -> None:
        # PyQt6 propagates unhandled exceptions out of paintEvent and aborts the
        # process. A single bad/transient frame must never crash the app mid-race,
        # so we always end the painter and swallow paint failures (logged once).
        p = QPainter(self)
        try:
            self._paint(p)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("TrackMapWidget paint failed")
            try:
                p.fillRect(self.rect(), QColor("#0A1A0A"))
            except Exception:
                pass
        finally:
            p.end()

    def _paint(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0A1A0A"))

        if self._draw_data is None or not self._draw_data.has_map:
            p.setPen(QPen(QColor("#555"), 1))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No track map loaded")
            return

        from ui.track_map_vm import project_to_screen
        data = project_to_screen(self._draw_data, self.width(), self.height())

        # Width corridor (filled)
        if len(data.width_left) > 1 and len(data.width_right) > 1:
            poly = QPolygonF()
            for pt in data.width_left:
                poly.append(QPointF(pt.x, pt.y))
            for pt in reversed(data.width_right):
                poly.append(QPointF(pt.x, pt.y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#0D2A0D")))
            p.drawPolygon(poly)

        # Width edges
        for edge, color in ((data.width_left, "#254525"), (data.width_right, "#254525")):
            if len(edge) > 1:
                p.setPen(QPen(QColor(color), 1))
                for i in range(len(edge) - 1):
                    a, b = edge[i], edge[i + 1]
                    p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y))

        # Centreline (dotted)
        if len(data.centreline) > 1:
            p.setPen(QPen(QColor("#2EA043"), 1, Qt.PenStyle.DotLine))
            for i in range(len(data.centreline) - 1):
                a, b = data.centreline[i], data.centreline[i + 1]
                p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y))

        # Pit lane overlay (Group 21B) — grey polyline beneath segment highlight
        pit_pts = getattr(data, "pit_lane_polyline", [])
        if len(pit_pts) > 1:
            p.setPen(QPen(QColor("#888888"), 3))
            for i in range(len(pit_pts) - 1):
                a, b = pit_pts[i], pit_pts[i + 1]
                p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y))

        # Segment highlight band (Group 20A) — amber polyline over centreline
        h_start = getattr(data, "highlight_start_progress", None)
        h_end   = getattr(data, "highlight_end_progress", None)
        if h_start is not None and h_end is not None and len(data.centreline) > 1:
            n_pts = len(data.centreline)
            amber = QColor("#F5A623")
            amber.setAlphaF(0.6)
            pen_hl = QPen(amber, 4)
            pen_hl.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen_hl)
            wraps = h_start > h_end  # progress range crosses lap end
            for i in range(n_pts - 1):
                prog = i / (n_pts - 1) if n_pts > 1 else 0.0
                if wraps:
                    in_range = prog >= h_start or prog <= h_end
                else:
                    in_range = h_start <= prog <= h_end
                if in_range:
                    a, b = data.centreline[i], data.centreline[i + 1]
                    p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y))

        # Start/finish marker
        if data.start_finish:
            p.setPen(QPen(QColor("#FFFFFF"), 2))
            p.setBrush(QBrush(QColor("#FFFFFF")))
            p.drawEllipse(QPointF(data.start_finish.x, data.start_finish.y), 4, 4)

        # Corner labels
        p.setFont(QFont("Segoe UI", 7))
        for lbl in data.corner_labels:
            c = "#888" if lbl.is_placeholder else "#F5C542"
            p.setPen(QPen(QColor(c), 1))
            p.drawText(
                QRectF(lbl.x - 12, lbl.y - 8, 24, 12),
                Qt.AlignmentFlag.AlignCenter,
                lbl.text,
            )

        # Car dot
        if data.car_dot:
            _cc = {"high": "#2EA043", "medium": "#F5A623",
                   "low": "#E53E3E", "unknown": "#888888"}
            dot_c = _cc.get(data.car_dot.confidence, "#888888")
            p.setBrush(QBrush(QColor(dot_c)))
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            p.drawEllipse(QPointF(data.car_dot.x, data.car_dot.y), 6, 6)

        # Status bar
        if data.status_text:
            p.setPen(QPen(QColor("#555"), 1))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(
                QRectF(0, self.height() - 18, self.width(), 18),
                Qt.AlignmentFlag.AlignCenter,
                data.status_text,
            )
