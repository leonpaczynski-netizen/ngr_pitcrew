"""EventHeaderBar — the persistent event context header (F1).

Shows, on every page: the official NGR logo (loaded unchanged), the event
identity (series · event · car · track/layout), the current session/stage, the
connection status, and the active setup. Bound to an AppState; updated by signal,
never rebuilt.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy

from ui import ngr_theme as _t
from ui.app_state import AppState
from ui.components.status import StatusPill


def _dim(text: str, size: int) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {size}pt;")
    return lbl


class EventHeaderBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrEventHeader")
        self.setStyleSheet(
            f"#ngrEventHeader {{ background: {_t.INK_BLACK}; "
            f"border-bottom: 1px solid {_t.HAIRLINE}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_LG, _t.SPACE_SM, _t.SPACE_LG, _t.SPACE_SM)
        lay.setSpacing(_t.SPACE_LG)

        # Logo (official asset, unchanged) with text fallback. Rendered prominently
        # as the brand anchor of the persistent header.
        self._logo = QLabel()
        self._logo.setObjectName("ngrHeaderLogo")
        pix = _t_logo_pixmap(height=48)
        if pix is not None:
            self._logo.setPixmap(pix)
        else:
            self._logo.setText(_t.logo_placeholder_text())
            self._logo.setStyleSheet(
                f"color: {_t.TEXT_HI}; font-weight: 700; letter-spacing: 1px;"
            )
        self._logo.setToolTip("Next Gear Racing — Pit Crew")
        lay.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignVCenter)

        # Identity block (two lines: event name / car · track)
        ident = QVBoxLayout()
        ident.setContentsMargins(0, 0, 0, 0)
        ident.setSpacing(0)
        self._event_line = QLabel()
        self._event_line.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H2}pt; font-weight: 700;"
        )
        self._ctx_line = _dim("", _t.FS_BODY)
        # The identity text (long event name + full track id) must never force the
        # header — and so the whole window — wider than the screen. Let both lines
        # shrink to nothing and clip; the full text stays available as a tooltip.
        for _lbl in (self._event_line, self._ctx_line):
            _lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            _lbl.setMinimumWidth(0)
        # Centre the two lines vertically against the prominent logo.
        ident.addStretch(1)
        ident.addWidget(self._event_line)
        ident.addWidget(self._ctx_line)
        ident.addStretch(1)
        lay.addLayout(ident)

        lay.addStretch(1)

        # Session / stage
        self._stage = _dim("", _t.FS_CAPTION)
        lay.addWidget(self._stage, 0, Qt.AlignmentFlag.AlignVCenter)

        # Active setup
        self._setup = _dim("", _t.FS_CAPTION)
        lay.addWidget(self._setup, 0, Qt.AlignmentFlag.AlignVCenter)

        # Connection pill
        self._conn = StatusPill("NO SIGNAL", tone="neutral")
        lay.addWidget(self._conn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.bind(AppState.empty())

    def bind(self, app_state: AppState) -> None:
        if not isinstance(app_state, AppState):
            app_state = AppState.empty()

        name = app_state.event_name or "No active event"
        series = app_state.event.series if hasattr(app_state.event, "series") else ""
        _event_text = f"{series + ' · ' if series else ''}{name}"
        self._event_line.setText(_event_text)
        self._event_line.setToolTip(_event_text)

        car = app_state.car or "—"
        track = app_state.track or "—"
        layout = app_state.layout_id or ""
        track_disp = f"{track} · {layout}" if layout else track
        _ctx_text = f"{car}   |   {track_disp}"
        self._ctx_line.setText(_ctx_text)
        self._ctx_line.setToolTip(_ctx_text)

        stage = app_state.programme_stage or "—"
        self._stage.setText(f"Stage: {stage.title() if stage != '—' else '—'}")

        if app_state.active_setup_label:
            applied = "applied" if app_state.active_setup_applied else "not applied"
            self._setup.setText(f"Setup: {app_state.active_setup_label} ({applied})")
        else:
            self._setup.setText("Setup: —")

        if app_state.connected:
            self._conn.set_status("LIVE", tone="success", glyph="●")
        else:
            self._conn.set_status("NO SIGNAL", tone="neutral", glyph="○")


def _t_logo_pixmap(height: int = 26):
    """Load the official logo pixmap, or None when missing/headless. Never raises."""
    try:
        return _t.logo_pixmap(height=height)
    except Exception:
        return None
