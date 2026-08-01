"""LivePracticeDiagnosticsPanel — the Live Activation 1 diagnostics header (§9).

A quiet, collapsible advisory card that renders the authoritative live-Practice identity +
recording state from ``LiveShellBridge.live_practice_diagnostics()``. The driver-facing summary
(recording state + connection + valid-lap count) is always visible; the full canonical
identifiers (event / programme / plan / run / stint + car-spec / setup / context / driver /
track revisions) live behind an expander so normal presentation stays immersive but every id is
available during UAT.

Conveys meaning by colour + text together (never colour alone); long ids are monospaced and
carry the full value as a tooltip. Read-only — it renders state, it never drives it.
"""
from __future__ import annotations

from typing import Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import ngr_theme as _t
from ui.components.status import StatusPill

_MONO = "Consolas, 'Cascadia Mono', 'Courier New', monospace"

#: recording_state → (StatusPill tone, glyph)
_STATE_TONE = {
    "recording": ("success", "●"),
    "starting": ("info", "◐"),
    "paused": ("warn", "❚❚"),
    "disconnected": ("danger", "⚠"),
    "completing": ("info", "◑"),
    "completed": ("neutral", "✓"),
    "abandoned": ("neutral", "✕"),
    "not_started": ("neutral", "○"),
}

#: The identifier rows, in display order: (dict key, label, section).
_ROWS = [
    ("event_id", "Event ID", "Identity"),
    ("event_programme_id", "Event Programme", "Identity"),
    ("session_plan_id", "Session Plan ID", "Identity"),
    ("session_run_id", "Session Run ID", "Identity"),
    ("stint_id", "Stint", "Identity"),
    ("session_type", "Session Type", "Identity"),
    ("car_id", "Car", "Provenance"),
    ("car_spec_revision_id", "Car-Spec Revision", "Provenance"),
    ("setup_snapshot_id", "Setup Snapshot", "Provenance"),
    ("context_revision_id", "Context Revision", "Provenance"),
    ("driver_profile_version_id", "Driver-Profile Version", "Provenance"),
    ("track_model_version_id", "Track-Model Version", "Provenance"),
]


def _caption(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt; "
        f"font-weight: 700; letter-spacing: 1px;")
    return lbl


class LivePracticeDiagnosticsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrLiveDiag")
        self.setStyleSheet(
            f"#ngrLiveDiag {{ background: {_t.ADVISORY_TINT}; "
            f"border: 1px solid {_t.HAIRLINE_SOFT}; "
            f"border-left: 3px solid {_t.ADVISORY_EDGE}; "
            f"border-radius: {_t.RADIUS_MD}px; }}")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
        outer.setSpacing(_t.SPACE_SM)

        # -- header row (always visible) ------------------------------------ #
        head = QHBoxLayout()
        head.setSpacing(_t.SPACE_SM)
        #: The header title, session-type-aware (Practice / Qualifying); _on_toggle reuses it.
        self._diag_title = "LIVE PRACTICE DIAGNOSTICS"
        self._toggle = QPushButton("▸  LIVE PRACTICE DIAGNOSTICS")
        self._toggle.setCheckable(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; text-align: left; "
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt; font-weight: 700; "
            f"letter-spacing: 1px; padding: 0; }}"
            f"QPushButton:hover {{ color: {_t.TEXT_HI}; }}")
        self._toggle.toggled.connect(self._on_toggle)
        head.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self._laps = QLabel("")
        self._laps.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_LABEL}pt; font-weight: 700;")
        head.addWidget(self._laps, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        self._state_pill = StatusPill("NOT STARTED", "neutral", "○")
        self._conn_pill = StatusPill("NO SIGNAL", "neutral", "○")
        head.addWidget(self._state_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self._conn_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(head)

        # -- body (collapsed by default) ------------------------------------ #
        self._body = QWidget()
        grid = QGridLayout(self._body)
        grid.setContentsMargins(0, _t.SPACE_XS, 0, 0)
        grid.setHorizontalSpacing(_t.SPACE_LG)
        grid.setVerticalSpacing(_t.SPACE_XS)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._values: dict[str, QLabel] = {}
        # Two columns of rows (Identity left, Provenance right) to stay compact.
        left = [r for r in _ROWS if r[2] == "Identity"]
        right = [r for r in _ROWS if r[2] == "Provenance"]
        grid.addWidget(_caption("IDENTITY"), 0, 0, 1, 2)
        grid.addWidget(_caption("PROVENANCE"), 0, 2, 1, 2)
        for i in range(max(len(left), len(right))):
            if i < len(left):
                self._add_row(grid, i + 1, 0, left[i])
            if i < len(right):
                self._add_row(grid, i + 1, 2, right[i])

        self._empty = QLabel("No active live recording.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_BODY}pt;")
        grid.addWidget(self._empty, len(left) + 1, 0, 1, 4)

        self._body.setVisible(False)
        outer.addWidget(self._body)

        self.set_diagnostics({"active": False, "recording_state": "not_started"})

    # ---------------------------------------------------------------------- #
    def _add_row(self, grid, row, col, spec) -> None:
        key, label, _section = spec
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        val = QLabel("—")
        val.setStyleSheet(
            f"color: {_t.TEXT}; font-size: {_t.FS_CAPTION}pt; font-family: {_MONO};")
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        val.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        val.setMinimumWidth(0)
        grid.addWidget(lbl, row, col, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(val, row, col + 1)
        self._values[key] = val

    def _on_toggle(self, on: bool) -> None:
        self._toggle.setText(("▾" if on else "▸") + f"  {self._diag_title}")
        self._body.setVisible(on)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def set_diagnostics(self, d: Mapping) -> None:
        """Render the authoritative diagnostics dict. Inactive-safe; never raises."""
        try:
            d = d if isinstance(d, Mapping) else {}
            active = bool(d.get("active"))
            state = str(d.get("recording_state") or "not_started")
            tone, glyph = _STATE_TONE.get(state, ("neutral", "○"))
            self._state_pill.set_status(state.replace("_", " ").upper(), tone, glyph)

            # Session-type-aware header title (Live Activation 1 = Practice, 2 = Qualifying).
            is_qual = str(d.get("session_type") or "").lower() == "qualifying"
            self._diag_title = "LIVE QUALIFYING DIAGNOSTICS" if is_qual else "LIVE PRACTICE DIAGNOSTICS"
            self._toggle.setText(("▾" if self._toggle.isChecked() else "▸") + f"  {self._diag_title}")

            if active:
                connected = bool(d.get("connected"))
                self._conn_pill.set_status(
                    "LIVE" if connected else "NO SIGNAL",
                    "success" if connected else "danger",
                    "●" if connected else "○")
                # A qualifying summary tracks the best flying lap + phase (a supplied headline);
                # a practice summary counts valid laps. Fall back to the lap count either way.
                headline = str(d.get("headline") or "")
                if headline:
                    self._laps.setText(headline)
                else:
                    laps = d.get("valid_lap_count", 0)
                    self._laps.setText(f"{laps} valid lap{'s' if laps != 1 else ''}")
                self._laps.setVisible(True)
                self._empty.setVisible(False)
                for key, lblwidget in self._values.items():
                    v = str(d.get(key) or "")
                    lblwidget.setText(v if v else "—")
                    lblwidget.setToolTip(v)
                    lblwidget.setVisible(True)
            else:
                self._conn_pill.set_status("NO SIGNAL", "neutral", "○")
                self._laps.setText("")
                self._laps.setVisible(False)
                self._empty.setVisible(True)
                for lblwidget in self._values.values():
                    lblwidget.setText("—")
                    lblwidget.setToolTip("")
                    lblwidget.setVisible(False)
        except Exception:
            pass
