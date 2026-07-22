"""GT7SettingsSheet — a read-only setup view mirroring GT7's in-game Settings Sheet (F2).

Drivers already know GT7's tuning screen, so the "full setup values" view replicates
its layout: two columns of grouped sections (Tyres / Suspension / Differential on the
left; Aerodynamics / Transmission / Performance / ECU / Nitrous on the right), each with
Front/Rear sub-columns and boxed, right-aligned values with tabular figures.

The section data + GT7 ordering come from the canonical, pure
``setup_transcribe_view.build_transcribe_sections`` (no engineering logic here — this
is presentation only). Optionally highlights fields that changed vs the parent setup.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
)

from ui import ngr_theme as _t
from ui.setup_transcribe_view import build_transcribe_sections


# Section titles (as produced by build_transcribe_sections) assigned to the left
# column, GT7-style; everything else falls to the right column in order.
_LEFT_TITLES = ("Tyres", "Suspension", "Differential & Brakes")

# Map a section title to the setup-dict keys behind its rows, so we can flag which
# rows changed. Ordered to match build_transcribe_sections' row order.
_SECTION_FIELD_KEYS: dict[str, list[tuple]] = {
    "Tyres": [("tyre_front", "tyre_rear")],
    "Suspension": [
        ("ride_height_front", "ride_height_rear"),
        ("arb_front", "arb_rear"),
        ("dampers_front_comp", "dampers_rear_comp"),
        ("dampers_front_ext", "dampers_rear_ext"),
        ("springs_front", "springs_rear"),
        ("camber_front", "camber_rear"),
        ("toe_front", "toe_rear"),
    ],
}


def _tabular_font(bold: bool = True) -> QFont:
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(11)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class GT7SettingsSheet(QWidget):
    """Two-column, GT7-style read-only settings sheet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrGt7Sheet")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(_t.SPACE_SM)

        self._columns = QHBoxLayout()
        self._columns.setContentsMargins(0, 0, 0, 0)
        self._columns.setSpacing(_t.SPACE_LG)
        self._left = QVBoxLayout()
        self._right = QVBoxLayout()
        self._left.setSpacing(_t.SPACE_MD)
        self._right.setSpacing(_t.SPACE_MD)
        lw, rw = QWidget(), QWidget()
        lw.setLayout(self._left)
        rw.setLayout(self._right)
        self._columns.addWidget(lw, 1)
        self._columns.addWidget(rw, 1)
        outer.addLayout(self._columns)
        outer.addStretch(1)

        self._empty = QLabel("No setup values yet.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        outer.addWidget(self._empty)

    def set_setup(self, d: Optional[dict], changed_fields: Iterable[str] = ()) -> None:
        """Render a setup dict in GT7 layout. ``changed_fields`` are highlighted."""
        changed = set(changed_fields or ())
        _clear_layout(self._left)
        _clear_layout(self._right)

        sections = []
        if d:
            try:
                sections = build_transcribe_sections(d)
            except Exception:
                sections = []
        self._empty.setVisible(not sections)

        for sec in sections:
            panel = self._render_section(sec, changed)
            if sec.get("title") in _LEFT_TITLES:
                self._left.addWidget(panel)
            else:
                self._right.addWidget(panel)
        self._left.addStretch(1)
        self._right.addStretch(1)

    # ---- rendering --------------------------------------------------------
    def _render_section(self, sec: dict, changed: set) -> QWidget:
        box = QFrame()
        box.setObjectName("ngrGt7Section")
        box.setStyleSheet(
            f"#ngrGt7Section {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_MD}px; }}"
        )
        grid = QGridLayout(box)
        grid.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(_t.SPACE_MD)

        # Centered section header bar (GT7 look)
        title = QLabel(sec.get("title", ""))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-weight: 700; font-size: {_t.FS_LABEL}pt; "
            f"letter-spacing: 0.5px; border-bottom: 1px solid {_t.HAIRLINE}; "
            f"padding-bottom: 3px;"
        )
        grid.addWidget(title, 0, 0, 1, 3)

        rows = sec.get("rows", [])
        has_fr = any(len(r) > 2 and r[2] is not None for r in rows)
        r0 = 1
        if has_fr:
            for ci, cap in ((1, "Front"), (2, "Rear")):
                c = QLabel(cap)
                c.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt; font-weight: 600;")
                c.setAlignment(Qt.AlignmentFlag.AlignRight)
                grid.addWidget(c, r0, ci)
            r0 += 1

        keys = _SECTION_FIELD_KEYS.get(sec.get("title", ""), [])
        for idx, row in enumerate(rows):
            label, front = row[0], row[1]
            rear = row[2] if len(row) > 2 else None
            ri = r0 + idx
            lbl = QLabel(str(label))
            lbl.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
            grid.addWidget(lbl, ri, 0)

            fkeys = keys[idx] if idx < len(keys) else ()
            f_changed = bool(fkeys) and fkeys[0] in changed
            grid.addWidget(self._value_box(front, f_changed), ri, 1)
            if rear is not None:
                r_changed = len(fkeys) > 1 and fkeys[1] in changed
                grid.addWidget(self._value_box(rear, r_changed), ri, 2)

        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        return box

    def _value_box(self, value, changed: bool) -> QLabel:
        text = str(value)
        # Numbers are bold tabular figures; longer enum strings (compound, ECU,
        # transmission type) use a smaller font so they fit the field without clipping.
        is_numeric = _looks_numeric(text)
        v = QLabel(text)
        if is_numeric:
            v.setFont(_tabular_font(bold=True))
        else:
            f = QFont(_t.FONT_FAMILY)
            f.setPointSize(_t.FS_CAPTION)
            v.setFont(f)
        v.setToolTip(text)
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        border = _t.NGR_GREEN if changed else _t.HAIRLINE
        colour = _t.NGR_GREEN if changed else _t.TEXT_HI
        v.setStyleSheet(
            f"color: {colour}; background: {_t.CARBON}; "
            f"border: 1px solid {border}; border-radius: {_t.RADIUS_SM}px; "
            f"padding: 2px 8px; min-width: 44px;"
        )
        return v


def _looks_numeric(text: str) -> bool:
    try:
        float(str(text).replace(":", "").strip())
        return True
    except (TypeError, ValueError):
        return False


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
