"""Compact, read-only "Transcribe to GT7" view for the Setup Builder (DEF-073-001 / -007).

The editable Setup Builder is necessarily tall — spinboxes, ranges, helper text, per-field
explainability. When the driver just needs to copy the finished numbers into GT7's in-game tuning
menu, that chrome is noise. This view renders the whole setup as a dense, read-only table grouped
and ORDERED exactly like GT7's tuning menu, with tabular figures so the numbers align. It is a
reference, not a form: no inputs, visually distinct from the disabled state.

``build_transcribe_sections`` is pure (no Qt) so the mapping/ordering is unit-testable.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QDialog, QScrollArea, QFrame,
    QHBoxLayout, QPushButton,
)

from ui import ngr_theme as _ngr

_TEXT = _ngr.TEXT
_MUTE = _ngr.TEXT_MUTE
_CARD = _ngr.CARBON_RAISED


def _fmt(value, decimals: int) -> str:
    """Format a numeric setup value; blank for None/unset."""
    if value is None or value == "":
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals == 0:
        return f"{int(round(f))}"
    return f"{f:.{decimals}f}"


def build_transcribe_sections(d: dict) -> list[dict]:
    """Map a setup dict to GT7-tuning-menu-ordered sections.

    Returns a list of ``{"title": str, "rows": [(label, front, rear)]}`` where a single-value row
    has ``rear`` = None. Rows/sections with no meaningful value are omitted so the reference stays
    tight (e.g. Nitrous is dropped when 'None', the front LSD only appears for AWD).
    """
    d = d or {}
    sections: list[dict] = []

    def _has(*keys) -> bool:
        return any(d.get(k) not in (None, "", 0, 0.0) for k in keys)

    # 1 — Tyres
    sections.append({"title": "Tyres", "rows": [
        ("Compound", d.get("tyre_front", "—"), d.get("tyre_rear", "—")),
    ]})

    # 2 — Suspension (GT7 row order)
    sections.append({"title": "Suspension", "rows": [
        ("Body Height (mm)",      _fmt(d.get("ride_height_front"), 0), _fmt(d.get("ride_height_rear"), 0)),
        ("Anti-Roll Bar",         _fmt(d.get("arb_front"), 0),         _fmt(d.get("arb_rear"), 0)),
        ("Damping (Compression)", _fmt(d.get("dampers_front_comp"), 0), _fmt(d.get("dampers_rear_comp"), 0)),
        ("Damping (Expansion)",   _fmt(d.get("dampers_front_ext"), 0),  _fmt(d.get("dampers_rear_ext"), 0)),
        ("Natural Frequency (Hz)", _fmt(d.get("springs_front"), 2),    _fmt(d.get("springs_rear"), 2)),
        ("Camber (°)",        _fmt(d.get("camber_front"), 1),      _fmt(d.get("camber_rear"), 1)),
        ("Toe (°)",           _fmt(d.get("toe_front"), 2),         _fmt(d.get("toe_rear"), 2)),
    ]})

    # 3 — Differential
    diff_rows = [
        ("LSD Initial Torque",    _fmt(d.get("lsd_initial"), 0), None),
        ("LSD Accel Sensitivity", _fmt(d.get("lsd_accel"), 0),   None),
        ("LSD Braking Sens.",     _fmt(d.get("lsd_decel"), 0),   None),
    ]
    if str(d.get("drivetrain", "")).upper() == "AWD" or _has("lsd_front_initial", "lsd_front_accel", "lsd_front_decel"):
        diff_rows += [
            ("LSD Front Initial",   _fmt(d.get("lsd_front_initial"), 0), None),
            ("LSD Front Accel",     _fmt(d.get("lsd_front_accel"), 0),   None),
            ("LSD Front Braking",   _fmt(d.get("lsd_front_decel"), 0),   None),
        ]
    diff_rows += [
        ("Torque Distribution (R%)", _fmt(d.get("torque_distribution_rear"), 0), None),
        ("Brake Balance",            _fmt(d.get("brake_bias_front"), 0), None),
    ]
    sections.append({"title": "Differential & Brakes", "rows": diff_rows})

    # 4 — Aero
    sections.append({"title": "Aerodynamics", "rows": [
        ("Downforce", _fmt(d.get("aero_front"), 0), _fmt(d.get("aero_rear"), 0)),
    ]})

    # 5 — Transmission
    trans_rows: list = []
    if _has("final_drive"):
        trans_rows.append(("Final Drive", _fmt(d.get("final_drive"), 3), None))
    if _has("transmission_max_speed_kmh"):
        trans_rows.append(("Top Speed (km/h)", _fmt(d.get("transmission_max_speed_kmh"), 0), None))
    _gears = [g for g in (d.get("gear_ratios") or []) if g not in (None, "", 0, 0.0)]
    for i, g in enumerate(_gears, 1):
        trans_rows.append((f"Gear {i}", _fmt(g, 3), None))
    if _has("transmission_type") and str(d.get("transmission_type")) not in ("Stock", "—"):
        trans_rows.append(("Transmission", str(d.get("transmission_type")), None))
    if trans_rows:
        sections.append({"title": "Transmission", "rows": trans_rows})

    # 6 — Performance Adjustment
    perf_rows: list = []
    if _has("ballast_kg"):
        perf_rows.append(("Ballast (kg)", _fmt(d.get("ballast_kg"), 0), None))
        perf_rows.append(("Ballast Position", _fmt(d.get("ballast_position"), 0), None))
    _pr = d.get("power_restrictor")
    if _pr not in (None, "", 100, 100.0):
        perf_rows.append(("Power Restrictor (%)", _fmt(_pr, 0), None))
    if perf_rows:
        sections.append({"title": "Performance Adjustment", "rows": perf_rows})

    # 7 — ECU
    ecu_rows: list = []
    if _has("ecu_ingame") and str(d.get("ecu_ingame")) not in ("Stock", "—"):
        ecu_rows.append(("ECU", str(d.get("ecu_ingame")), None))
    _eo = d.get("ecu_ingame_output")
    if _eo not in (None, "", 100, 100.0):
        ecu_rows.append(("ECU Output (%)", _fmt(_eo, 0), None))
    if ecu_rows:
        sections.append({"title": "Engine / ECU", "rows": ecu_rows})

    # 8 — Nitrous (only when fitted)
    if _has("nitrous_type") and str(d.get("nitrous_type")) not in ("None", "—"):
        sections.append({"title": "Nitrous", "rows": [
            ("Type", str(d.get("nitrous_type")), None),
            ("Output (%)", _fmt(d.get("nitrous_output"), 0), None),
        ]})

    return sections


#: The canonical GT7 tuning-menu order of every setup FIELD KEY, matching the row
#: order of ``build_transcribe_sections`` above. Any surface that lists setup fields
#: for transcription into GT7 sorts by this so the driver reads top-to-bottom in the
#: same order as the in-game menu instead of hunting for each row.
GT7_FIELD_ORDER: tuple[str, ...] = (
    # 1 — Tyres
    "tyre_front", "tyre_rear",
    # 2 — Suspension
    "ride_height_front", "ride_height_rear",
    "arb_front", "arb_rear",
    "dampers_front_comp", "dampers_rear_comp",
    "dampers_front_ext", "dampers_rear_ext",
    "springs_front", "springs_rear",
    "camber_front", "camber_rear",
    "toe_front", "toe_rear",
    # 3 — Differential & Brakes
    "lsd_initial", "lsd_accel", "lsd_decel",
    "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
    "torque_distribution_rear", "brake_bias_front",
    # 4 — Aerodynamics
    "aero_front", "aero_rear",
    # 5 — Transmission
    "final_drive", "transmission_max_speed_kmh", "gear_ratios", "transmission_type",
    # 6 — Performance Adjustment
    "ballast_kg", "ballast_position", "power_restrictor",
    # 7 — Engine / ECU
    "ecu_ingame", "ecu_ingame_output",
    # 8 — Nitrous
    "nitrous_type", "nitrous_output",
)

_GT7_FIELD_INDEX = {k: i for i, k in enumerate(GT7_FIELD_ORDER)}


def gt7_field_rank(field: str) -> int:
    """Sort key for a setup field key in GT7 tuning-menu order.

    Unknown fields sort after every known one (stable within themselves), so a new
    or unrecognised field is never silently dropped or hoisted to the top.
    """
    return _GT7_FIELD_INDEX.get(str(field or ""), len(GT7_FIELD_ORDER))


def _tabular_font(bold: bool = False) -> QFont:
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(11)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class SetupTranscribeView(QWidget):
    """Dense read-only render of ``build_transcribe_sections`` — a copy-into-GT7 reference."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(4, 4, 4, 4)
        self._root.setSpacing(8)
        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setTextFormat(Qt.TextFormat.RichText)
        self._root.addWidget(self._header)
        self._body = QVBoxLayout()
        self._body.setSpacing(8)
        self._root.addLayout(self._body)
        self._root.addStretch(1)

    def set_setup(self, d: dict, header: Optional[dict] = None) -> None:
        # header line
        h = header or {}
        _car = h.get("car") or d.get("car") or "—"
        _track = h.get("track") or d.get("track") or ""
        _name = h.get("setup_name") or d.get("setup_label") or ""
        self._header.setStyleSheet(
            f"background:{_CARD}; border-left:5px solid {_ngr.NGR_GREEN}; "
            f"border-radius:4px; padding:6px 12px;")
        self._header.setText(
            f"<span style='color:{_ngr.NGR_GREEN}; font-size:14px; font-weight:bold;'>"
            f"Transcribe into GT7</span>"
            f"<span style='color:{_MUTE}; font-size:11px;'> — read-only reference; "
            f"copy each value into the in-game tuning menu (top to bottom).</span><br>"
            f"<span style='color:{_TEXT}; font-size:12px;'>{_car}"
            + (f" &nbsp;·&nbsp; {_track}" if _track else "")
            + (f" &nbsp;·&nbsp; {_name}" if _name else "")
            + "</span>")

        # clear old body
        while self._body.count():
            item = self._body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for sec in build_transcribe_sections(d):
            self._body.addWidget(self._render_section(sec))

    def _render_section(self, sec: dict) -> QWidget:
        box = QFrame()
        box.setStyleSheet(
            f"QFrame {{ background:{_CARD}; border:1px solid {_ngr.HAIRLINE_SOFT}; "
            f"border-radius:4px; }}")
        grid = QGridLayout(box)
        grid.setContentsMargins(10, 6, 10, 6)
        grid.setVerticalSpacing(2)
        grid.setHorizontalSpacing(14)

        title = QLabel(sec["title"])
        title.setStyleSheet(f"color:{_ngr.NGR_GREEN}; font-weight:bold; font-size:11px;")
        grid.addWidget(title, 0, 0, 1, 3)
        # column captions only when any row is front/rear
        has_fr = any(r[2] is not None for r in sec["rows"])
        r0 = 1
        if has_fr:
            for ci, cap in ((1, "Front"), (2, "Rear")):
                c = QLabel(cap)
                c.setStyleSheet(f"color:{_MUTE}; font-size:9px; font-weight:bold;")
                c.setAlignment(Qt.AlignmentFlag.AlignRight)
                grid.addWidget(c, r0, ci)
            r0 += 1

        for ri, (label, front, rear) in enumerate(sec["rows"], start=r0):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{_TEXT}; font-size:11px;")
            grid.addWidget(lbl, ri, 0)
            fv = QLabel(str(front))
            fv.setFont(_tabular_font(bold=True))
            fv.setStyleSheet(f"color:{_TEXT};")
            fv.setAlignment(Qt.AlignmentFlag.AlignRight)
            fv.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(fv, ri, 1)
            if rear is not None:
                rv = QLabel(str(rear))
                rv.setFont(_tabular_font(bold=True))
                rv.setStyleSheet(f"color:{_TEXT};")
                rv.setAlignment(Qt.AlignmentFlag.AlignRight)
                rv.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(rv, ri, 2)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        return box


class SetupTranscribeDialog(QDialog):
    """Non-modal window wrapping SetupTranscribeView so it can stay open beside GT7."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transcribe to GT7")
        self.setModal(False)
        self.resize(420, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self._view = SetupTranscribeView()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._view)
        lay.addWidget(scroll, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_close = QPushButton("Close")
        self._btn_close.clicked.connect(self.close)
        btn_row.addWidget(self._btn_close)
        lay.addLayout(btn_row)

    def set_setup(self, d: dict, header: Optional[dict] = None) -> None:
        self._view.set_setup(d, header)
