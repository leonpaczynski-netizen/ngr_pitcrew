"""GT7SettingsSheet — setup view mirroring GT7's in-game Settings Sheet (F2).

Drivers already know GT7's tuning screen, so the "full setup values" view replicates
its layout: two columns of grouped sections (Tyres / Suspension / Differential on the
left; Aerodynamics / Transmission / Performance / ECU / Nitrous on the right), each with
Front/Rear sub-columns and boxed, right-aligned values with tabular figures.

The section data + GT7 ordering come from the canonical, pure
``setup_transcribe_view.build_transcribe_sections`` (no engineering logic here — this
is presentation only). Optionally highlights fields that changed vs the parent setup.

The right column also hosts an editable Transmission section (gear ratios, final drive,
top speed) so the driver can enter gear values without leaving the full setup view.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QDoubleSpinBox,
)

from ui import ngr_theme as _t
from ui.setup_transcribe_view import build_transcribe_sections


# Section titles (as produced by build_transcribe_sections) assigned to the left
# column, GT7-style; everything else falls to the right column in order.
_LEFT_TITLES = ("Tyres", "Suspension", "Differential & Brakes")

# Map each rendered row LABEL to the setup-dict key(s) behind it (front, rear), so a
# recommended change highlights the right value. Keyed by LABEL — not by row position —
# because build_transcribe_sections inserts/omits rows (e.g. the AWD front-LSD rows,
# unused gears), which a positional map got wrong: it only covered Tyres + Suspension,
# so a Differential change (LSD accel), Aero, Transmission etc. never highlighted.
# Labels MUST match build_transcribe_sections exactly. Gear rows ("Gear N") are handled
# dynamically in _keys_for_label.
_FIELD_KEYS_BY_LABEL: dict[str, tuple] = {
    # Tyres
    "Compound": ("tyre_front", "tyre_rear"),
    # Suspension
    "Body Height (mm)": ("ride_height_front", "ride_height_rear"),
    "Anti-Roll Bar": ("arb_front", "arb_rear"),
    "Damping (Compression)": ("dampers_front_comp", "dampers_rear_comp"),
    "Damping (Expansion)": ("dampers_front_ext", "dampers_rear_ext"),
    "Natural Frequency (Hz)": ("springs_front", "springs_rear"),
    "Camber (°)": ("camber_front", "camber_rear"),
    "Toe (°)": ("toe_front", "toe_rear"),
    # Differential & Brakes
    "LSD Initial Torque": ("lsd_initial",),
    "LSD Accel Sensitivity": ("lsd_accel",),
    "LSD Braking Sens.": ("lsd_decel",),
    "LSD Front Initial": ("lsd_front_initial",),
    "LSD Front Accel": ("lsd_front_accel",),
    "LSD Front Braking": ("lsd_front_decel",),
    "Torque Distribution (R%)": ("torque_distribution_rear",),
    "Brake Balance": ("brake_bias_front",),
    # Aerodynamics
    "Downforce": ("aero_front", "aero_rear"),
    # Transmission
    "Final Drive": ("final_drive",),
    "Top Speed (km/h)": ("transmission_max_speed_kmh",),
    "Transmission": ("transmission_type",),
    # Performance Adjustment
    "Ballast (kg)": ("ballast_kg",),
    "Ballast Position": ("ballast_position",),
    "Power Restrictor (%)": ("power_restrictor",),
    # Engine / ECU
    "ECU": ("ecu_ingame",),
    "ECU Output (%)": ("ecu_ingame_output",),
    # Nitrous
    "Type": ("nitrous_type",),
    "Output (%)": ("nitrous_output",),
}


def _keys_for_label(label: str) -> tuple:
    """The (front[, rear]) setup keys behind a rendered row label, for highlighting.

    Handles the numbered gear rows ("Gear 1".."Gear 8") dynamically — a recommendation
    may name an individual gear (gear_N) or the whole ratio set (gear_ratios).
    """
    s = str(label or "")
    if s.startswith("Gear "):
        n = s[5:].strip()
        return (f"gear_{n}", "gear_ratios") if n.isdigit() else ("gear_ratios",)
    return _FIELD_KEYS_BY_LABEL.get(s, ())


def _tabular_font(bold: bool = True) -> QFont:
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(11)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class GT7SettingsSheet(QWidget):
    """Two-column, GT7-style settings sheet with editable Transmission section.

    The read-only sections mirror GT7's in-game layout; the editable Transmission
    section sits in the right column (under the read-only right sections) so the
    driver can enter gear ratios without switching tabs.
    """

    #: Emitted when the driver finishes editing any gear ratio, final drive, or top speed.
    #: Payload: {gear_ratios: [float, ...], final_drive: float, transmission_max_speed_kmh: float}
    gearing_changed = pyqtSignal(dict)

    #: Emitted when the driver finishes editing ballast weight or position.
    #: Payload: {ballast_kg: float, ballast_position: int}
    ballast_changed = pyqtSignal(dict)

    #: Emitted when the driver finishes editing a series-regulated weight or power.
    #: Payload: {weight_kg: float, power_hp: float} (0 = use the stock car spec).
    regulation_changed = pyqtSignal(dict)

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
        # No addStretch(1) here — removed to fix the large empty gap below the last
        # section on the full setup page (FIX 3). Content sizes to its natural height;
        # the enclosing QScrollArea handles overflow without forcing a stretch.

        self._empty = QLabel("No setup values yet.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        outer.addWidget(self._empty)

        # Editable Transmission section — placed in the right column by set_setup()
        # so the driver can enter gear ratios without leaving the Full setup page.
        # It is a persistent widget (not rebuilt on each set_setup call); set_setup
        # rescues it before clearing the column and re-adds it after.
        self._trans_section = self._build_transmission_section()
        self._ballast_section = self._build_ballast_section()
        self._regulation_section = self._build_regulation_section()

    def _build_regulation_section(self) -> QFrame:
        """Editable series-regulation (BOP) entry: minimum weight and maximum power.

        Weight and power otherwise default from the stock car spec, but a series can
        mandate a specific figure (e.g. Supercars: 1335 kg / 606 bhp) that a car built
        with parts + ballast doesn't match. Entering them here makes the setup brain reason
        from the real regulated car. 0 = leave on the stock spec. editingFinished emits
        regulation_changed."""
        box = QFrame()
        box.setObjectName("ngrGt7Section")
        box.setStyleSheet(
            f"#ngrGt7Section {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_MD}px; }}")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
        outer.setSpacing(_t.SPACE_XS)

        title = QLabel("Series regulation (entry)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-weight: 700; font-size: {_t.FS_LABEL}pt; "
            f"letter-spacing: 0.5px; border-bottom: 1px solid {_t.HAIRLINE}; "
            f"padding-bottom: 3px;")
        outer.addWidget(title)

        note = QLabel("Only if the series sets them — e.g. a minimum weight or a power cap. "
                      "Leave at 0 to use the car's stock figures.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        outer.addWidget(note)

        qss = (f"QDoubleSpinBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
               f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
               f"padding: 4px 8px; font-size: {_t.FS_LABEL}pt; }}")
        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_SM)
        grid.setVerticalSpacing(2)

        w_cap = QLabel("Weight (kg)")
        w_cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        w_cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(w_cap, 0, 0)
        self._weight_spin = QDoubleSpinBox()
        self._weight_spin.setRange(0.0, 3000.0)
        self._weight_spin.setSingleStep(1.0)
        self._weight_spin.setDecimals(0)
        self._weight_spin.setSpecialValueText("stock")   # 0 shows "stock"
        self._weight_spin.setMinimumHeight(_t.TOUCH_MIN_H)
        self._weight_spin.setMaximumWidth(110)
        self._weight_spin.setStyleSheet(qss)
        self._weight_spin.editingFinished.connect(self._on_regulation_edited)
        grid.addWidget(self._weight_spin, 1, 0)

        p_cap = QLabel("Power (bhp)")
        p_cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        p_cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(p_cap, 0, 1)
        self._power_spin = QDoubleSpinBox()
        self._power_spin.setRange(0.0, 2000.0)
        self._power_spin.setSingleStep(1.0)
        self._power_spin.setDecimals(0)
        self._power_spin.setSpecialValueText("stock")
        self._power_spin.setMinimumHeight(_t.TOUCH_MIN_H)
        self._power_spin.setMaximumWidth(110)
        self._power_spin.setStyleSheet(qss)
        self._power_spin.editingFinished.connect(self._on_regulation_edited)
        grid.addWidget(self._power_spin, 1, 1)

        grid.setColumnStretch(2, 1)
        outer.addLayout(grid)
        return box

    def _on_regulation_edited(self) -> None:
        self.regulation_changed.emit({
            "weight_kg": float(self._weight_spin.value()),
            "power_hp": float(self._power_spin.value()),
        })

    def set_regulation(self, weight_kg: float = 0.0, power_hp: float = 0.0) -> None:
        """Load stored regulated weight/power. Blocks signals; skips a focused spin so a
        mid-edit isn't overwritten by the 750 ms feed."""
        spins = (self._weight_spin, self._power_spin)
        if any(s.hasFocus() for s in spins):
            return
        self._weight_spin.blockSignals(True)
        self._weight_spin.setValue(float(weight_kg or 0.0))
        self._weight_spin.blockSignals(False)
        self._power_spin.blockSignals(True)
        self._power_spin.setValue(float(power_hp or 0.0))
        self._power_spin.blockSignals(False)

    def _build_ballast_section(self) -> QFrame:
        """Editable Ballast entry: weight (kg) and position (front −/rear +).

        Ballast is a real handling tool AND often a regulation requirement (a series
        minimum weight is met by adding ballast), so the driver must be able to enter both
        how much and where it sits — the balance shifts with position. editingFinished
        emits ballast_changed; the value goes through the same clamp/persist path as any
        setup field."""
        box = QFrame()
        box.setObjectName("ngrGt7Section")
        box.setStyleSheet(
            f"#ngrGt7Section {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_MD}px; }}")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
        outer.setSpacing(_t.SPACE_XS)

        title = QLabel("Ballast (entry)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-weight: 700; font-size: {_t.FS_LABEL}pt; "
            f"letter-spacing: 0.5px; border-bottom: 1px solid {_t.HAIRLINE}; "
            f"padding-bottom: 3px;")
        outer.addWidget(title)

        note = QLabel("Weight added to meet a minimum; position −50 (front) … +50 (rear) "
                      "shifts the balance.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        outer.addWidget(note)

        qss = (f"QDoubleSpinBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
               f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
               f"padding: 4px 8px; font-size: {_t.FS_LABEL}pt; }}")
        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_SM)
        grid.setVerticalSpacing(2)

        kg_cap = QLabel("Ballast (kg)")
        kg_cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        kg_cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(kg_cap, 0, 0)
        self._ballast_kg_spin = QDoubleSpinBox()
        self._ballast_kg_spin.setRange(0.0, 200.0)
        self._ballast_kg_spin.setSingleStep(1.0)
        self._ballast_kg_spin.setDecimals(0)
        self._ballast_kg_spin.setMinimumHeight(_t.TOUCH_MIN_H)
        self._ballast_kg_spin.setMaximumWidth(100)
        self._ballast_kg_spin.setStyleSheet(qss)
        self._ballast_kg_spin.editingFinished.connect(self._on_ballast_edited)
        grid.addWidget(self._ballast_kg_spin, 1, 0)

        pos_cap = QLabel("Position")
        pos_cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        pos_cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(pos_cap, 0, 1)
        self._ballast_pos_spin = QDoubleSpinBox()
        self._ballast_pos_spin.setRange(-50.0, 50.0)
        self._ballast_pos_spin.setSingleStep(1.0)
        self._ballast_pos_spin.setDecimals(0)
        self._ballast_pos_spin.setMinimumHeight(_t.TOUCH_MIN_H)
        self._ballast_pos_spin.setMaximumWidth(100)
        self._ballast_pos_spin.setStyleSheet(qss)
        self._ballast_pos_spin.editingFinished.connect(self._on_ballast_edited)
        grid.addWidget(self._ballast_pos_spin, 1, 1)

        grid.setColumnStretch(2, 1)
        outer.addLayout(grid)
        return box

    def _on_ballast_edited(self) -> None:
        self.ballast_changed.emit({
            "ballast_kg": float(self._ballast_kg_spin.value()),
            "ballast_position": int(self._ballast_pos_spin.value()),
        })

    def set_ballast(self, ballast_kg: float = 0.0, ballast_position: int = 0) -> None:
        """Load stored ballast into the entry spins. Blocks signals so the programmatic
        feed doesn't re-emit; skips while a spin has focus so a mid-edit isn't overwritten."""
        spins = (self._ballast_kg_spin, self._ballast_pos_spin)
        if any(s.hasFocus() for s in spins):
            return
        self._ballast_kg_spin.blockSignals(True)
        self._ballast_kg_spin.setValue(float(ballast_kg or 0.0))
        self._ballast_kg_spin.blockSignals(False)
        self._ballast_pos_spin.blockSignals(True)
        self._ballast_pos_spin.setValue(float(ballast_position or 0))
        self._ballast_pos_spin.blockSignals(False)

    def _build_transmission_section(self) -> QFrame:
        """Build the editable Transmission entry box (gear ratios, final drive, top speed).

        Per-discipline: Race and Qualifying hold independent gearing. The 750ms feed
        loads whichever discipline is selected; editingFinished emits gearing_changed.
        Leave unused gears at 0 — they are filtered in gearing_changed (>0 only).
        """
        box = QFrame()
        box.setObjectName("ngrGt7Section")
        box.setStyleSheet(
            f"#ngrGt7Section {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_MD}px; }}"
        )
        outer = QVBoxLayout(box)
        outer.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
        outer.setSpacing(_t.SPACE_XS)

        # Section header — same style as the read-only section titles
        title = QLabel("Transmission (entry)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-weight: 700; font-size: {_t.FS_LABEL}pt; "
            f"letter-spacing: 0.5px; border-bottom: 1px solid {_t.HAIRLINE}; "
            f"padding-bottom: 3px;"
        )
        outer.addWidget(title)

        note = QLabel(
            "Per-discipline gearing — Race and Qualifying are independent. "
            "Leave unused gears at 0.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        outer.addWidget(note)

        _gear_qss = (
            f"QDoubleSpinBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
            f"padding: 4px 8px; font-size: {_t.FS_LABEL}pt; }}")

        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_SM)
        grid.setVerticalSpacing(2)

        self._gear_spins: list = []
        for i, lbl in enumerate(["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]):
            cap = QLabel(lbl)
            cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
            cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            grid.addWidget(cap, 0, i)
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 5.000)
            spin.setSingleStep(0.001)
            spin.setDecimals(3)
            spin.setSpecialValueText("—")   # "—" for unused gear
            spin.setMinimumHeight(_t.TOUCH_MIN_H)
            spin.setMaximumWidth(90)
            spin.setStyleSheet(_gear_qss)
            spin.editingFinished.connect(self._on_gearing_edited)
            grid.addWidget(spin, 1, i)
            self._gear_spins.append(spin)

        # Final drive
        fd_cap = QLabel("Final")
        fd_cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        fd_cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(fd_cap, 0, 8)
        self._final_drive_spin = QDoubleSpinBox()
        self._final_drive_spin.setRange(0.0, 9.999)
        self._final_drive_spin.setSingleStep(0.001)
        self._final_drive_spin.setDecimals(3)
        self._final_drive_spin.setSpecialValueText("—")
        self._final_drive_spin.setMinimumHeight(_t.TOUCH_MIN_H)
        self._final_drive_spin.setMaximumWidth(90)
        self._final_drive_spin.setStyleSheet(_gear_qss)
        self._final_drive_spin.editingFinished.connect(self._on_gearing_edited)
        grid.addWidget(self._final_drive_spin, 1, 8)

        # Top speed / transmission max speed
        ts_cap = QLabel("Top speed (km/h)")
        ts_cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        ts_cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(ts_cap, 0, 9)
        self._top_speed_spin = QDoubleSpinBox()
        self._top_speed_spin.setRange(0.0, 999.0)
        self._top_speed_spin.setSingleStep(1.0)
        self._top_speed_spin.setDecimals(0)
        self._top_speed_spin.setSpecialValueText("—")
        self._top_speed_spin.setMinimumHeight(_t.TOUCH_MIN_H)
        self._top_speed_spin.setMaximumWidth(90)
        self._top_speed_spin.setStyleSheet(_gear_qss)
        self._top_speed_spin.editingFinished.connect(self._on_gearing_edited)
        grid.addWidget(self._top_speed_spin, 1, 9)

        outer.addLayout(grid)
        return box

    def set_setup(self, d: Optional[dict], changed_fields: Iterable[str] = ()) -> None:
        """Render a setup dict in GT7 layout. ``changed_fields`` are highlighted."""
        changed = set(changed_fields or ())

        # Rescue the persistent editable sections before clearing the column so they
        # aren't scheduled for deletion by _clear_layout.
        self._right.removeWidget(self._trans_section)
        self._right.removeWidget(self._ballast_section)
        self._right.removeWidget(self._regulation_section)

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

        # Always show the editable Transmission + Ballast sections in the right column,
        # whether or not there are setup values — the driver can enter them at any time.
        self._right.addWidget(self._trans_section)
        self._right.addWidget(self._ballast_section)
        self._right.addWidget(self._regulation_section)
        self._left.addStretch(1)
        self._right.addStretch(1)

    # ---- editable gearing -------------------------------------------------

    def set_gearing(self, gear_ratios=(), final_drive: float = 0.0,
                    transmission_max_speed_kmh: float = 0.0) -> None:
        """Load the discipline's gear ratios into the Transmission spins.

        Blocks signals while setting so the programmatic feed does not re-emit
        ``gearing_changed`` (same pattern as ``SetupWorkspace.set_shift_rpm``).
        Skips the update while any spin has focus so a driver mid-edit is not
        overwritten by the 750ms refresh feed.
        """
        all_spins = self._gear_spins + [self._final_drive_spin, self._top_speed_spin]
        if any(s.hasFocus() for s in all_spins):
            return
        gears = list(gear_ratios or ())
        for i, spin in enumerate(self._gear_spins):
            spin.blockSignals(True)
            spin.setValue(float(gears[i]) if i < len(gears) else 0.0)
            spin.blockSignals(False)
        self._final_drive_spin.blockSignals(True)
        self._final_drive_spin.setValue(float(final_drive or 0.0))
        self._final_drive_spin.blockSignals(False)
        self._top_speed_spin.blockSignals(True)
        self._top_speed_spin.setValue(float(transmission_max_speed_kmh or 0.0))
        self._top_speed_spin.blockSignals(False)

    def _on_gearing_edited(self) -> None:
        """Emit when the driver commits a gear value (editingFinished, not valueChanged).

        Only ratios > 0 are included in gear_ratios — zeros represent unused gears and
        are dropped, matching ``_gears()`` in ``strategy.setup_sheet``.
        """
        self.gearing_changed.emit({
            "gear_ratios": [s.value() for s in self._gear_spins if s.value() > 0],
            "final_drive": self._final_drive_spin.value(),
            "transmission_max_speed_kmh": self._top_speed_spin.value(),
        })

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
        grid.setVerticalSpacing(3)
        grid.setHorizontalSpacing(_t.SPACE_SM)

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

        for idx, row in enumerate(rows):
            label, front = row[0], row[1]
            rear = row[2] if len(row) > 2 else None
            ri = r0 + idx
            lbl = QLabel(str(label))
            lbl.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
            grid.addWidget(lbl, ri, 0)

            # Highlight by LABEL so every section (Differential, Aero, Transmission …)
            # flags its changed rows, not just Tyres/Suspension.
            fkeys = _keys_for_label(label)
            f_changed = bool(fkeys) and fkeys[0] in changed
            grid.addWidget(self._value_box(front, f_changed), ri, 1)
            if rear is not None:
                r_changed = len(fkeys) > 1 and fkeys[1] in changed
                grid.addWidget(self._value_box(rear, r_changed), ri, 2)

        # Labels take all the slack (max readability); value fields stay compact —
        # they only hold short numbers.
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnMinimumWidth(1, 50)
        grid.setColumnMinimumWidth(2, 50)
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
            f"padding: 1px 6px; min-width: 38px;"
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
