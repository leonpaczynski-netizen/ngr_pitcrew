"""SetupFormWidget — a self-contained car-setup form panel.

Each instance encapsulates one purpose's worth of setup fields (Race or
Qualifying) with its own Save/Load/Analyse/Build/Apply buttons.  The host
(SetupBuilderMixin / MainWindow) is passed as ``host`` so the form can
delegate to shared helpers (autofill, rebound ranges, AI invocation, event
context, DB, config persistence, etc.) without re-implementing them.

This module is intentionally thin: it builds the Qt widget tree and exposes
public accessors.  All business logic stays in SetupBuilderMixin methods on
the host; this widget is purely a UI container that owns the field widgets.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QLineEdit, QTextEdit,
    QComboBox,
)

if TYPE_CHECKING:
    pass  # host type is SetupBuilderMixin; avoid circular import

# Module-level display constants — must match dashboard.py / setup_builder_ui.py
_DARK_CARD = "#2A2A2A"
_TEXT       = "#E0E0E0"


def _set_spin_readonly(spin, readonly: bool) -> None:
    """Make a spinbox read-only or editable."""
    spin.setReadOnly(readonly)
    spin.setButtonSymbols(
        QAbstractSpinBox.ButtonSymbols.NoButtons
        if readonly
        else QAbstractSpinBox.ButtonSymbols.UpDownArrows
    )


class SetupFormWidget(QWidget):
    """Self-contained car-setup form for one purpose (Race or Qualifying).

    Parameters
    ----------
    purpose:
        ``"Race"`` or ``"Qualifying"`` — determines the panel title,
        the ``setup_type`` value in ``current_setup_dict()``, and the
        Q/R prefix used for auto-naming saved setups.
    host:
        The ``SetupBuilderMixin`` / ``MainWindow`` instance that owns the
        shared helpers (``_autofill_car_specs``, ``_rebound_setup_spinboxes``,
        ``_build_event_context``, ``_db``, etc.).
    """

    def __init__(self, purpose: str, host) -> None:
        super().__init__()
        self.purpose = purpose  # "Race" or "Qualifying"
        self._host = host

        # --- result state (parallel to host attrs for the old single-form) ---
        self.last_ai_fields: dict = {}
        self.highlighted_fields: set = set()

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the full form layout for this purpose."""
        lbl_s = f"color: {_TEXT};"
        outer = QVBoxLayout(self)
        outer.setSpacing(6)
        outer.setContentsMargins(4, 4, 4, 4)

        # Purpose header
        _purpose_color = "#88CCFF" if self.purpose == "Qualifying" else "#AAE4AA"
        hdr = QLabel(
            f"{self.purpose} Setup",
            styleSheet=f"color: {_purpose_color}; font-size: 14px; font-weight: bold; padding: 4px 0;",
        )
        outer.addWidget(hdr)

        # --- Locked banner ---
        self._setup_locked_banner = QLabel()
        self._setup_locked_banner.setStyleSheet(
            "color: #F5A623; background: #2A1A00; border: 1px solid #F5A623; "
            "border-radius: 4px; padding: 8px; font-size: 12px;"
        )
        self._setup_locked_banner.setWordWrap(True)
        self._setup_locked_banner.hide()
        outer.addWidget(self._setup_locked_banner)

        # --- Car-specs info line ---
        self._lbl_car_specs_info = QLabel(
            "",
            styleSheet="color: #AAAAAA; font-size: 10px;",
        )
        self._lbl_car_specs_info.setVisible(False)
        self._lbl_car_specs_info.setToolTip(
            "Stock car specifications from car_specs.json (PP rating, drivetrain, "
            "aspiration, power, weight).\n"
            "Run 'Refresh Data from Web' in Settings to populate these values."
        )
        outer.addWidget(self._lbl_car_specs_info)

        # --- BOP info row ---
        self._lbl_bop_info = QLabel("")
        self._lbl_bop_info.setStyleSheet("color: #88CCFF; font-style: italic;")
        self._lbl_bop_info.setVisible(False)

        self._btn_bop_edit = QPushButton("Edit BOP File")
        self._btn_bop_edit.setFixedHeight(22)
        self._btn_bop_edit.setToolTip("Open data/bop_data.json in default editor, then click Reload.")
        self._btn_bop_edit.setVisible(False)

        self._btn_bop_reload = QPushButton("Reload BOP")
        self._btn_bop_reload.setFixedHeight(22)
        self._btn_bop_reload.setToolTip("Re-read bop_data.json and refresh the BOP weight/power display.")
        self._btn_bop_reload.setVisible(False)

        _bop_row_w = QWidget()
        _bop_row_h = QHBoxLayout(_bop_row_w)
        _bop_row_h.setContentsMargins(0, 0, 0, 0)
        _bop_row_h.addWidget(self._lbl_bop_info)
        _bop_row_h.addStretch()
        _bop_row_h.addWidget(self._btn_bop_edit)
        _bop_row_h.addWidget(self._btn_bop_reload)
        self._bop_info_row_label = QLabel("BOP Data:", styleSheet=lbl_s)
        self._bop_info_row_label.setVisible(False)
        # Add BOP row to layout so widgets are owned and not garbage-collected
        _bop_outer = QHBoxLayout()
        _bop_outer.setContentsMargins(0, 0, 0, 0)
        _bop_outer.addWidget(self._bop_info_row_label)
        _bop_outer.addWidget(_bop_row_w)
        outer.addLayout(_bop_outer)

        # --- Transmission (auto-fill) sub-section ---
        auto_grp = QGroupBox("Transmission")
        auto_grp.setStyleSheet("QGroupBox { color: #AAE4AA; }")
        auto_inner = QVBoxLayout(auto_grp)
        auto_inner.setSpacing(4)

        def _gear_spin() -> QDoubleSpinBox:
            w = QDoubleSpinBox()
            w.setRange(0.0, 6.999)
            w.setDecimals(3)
            w.setSingleStep(0.001)
            w.setSpecialValueText("—")
            w.setValue(0.0)
            return w

        gear_grid = QGridLayout()
        gear_grid.setHorizontalSpacing(4)
        gear_grid.setVerticalSpacing(2)
        self._gear_ratio_spins: list[QDoubleSpinBox] = []
        for i in range(8):
            col = (i % 4) * 2
            row = i // 4
            lbl = QLabel(f"G{i+1}:")
            lbl.setStyleSheet(f"color: {_TEXT};")
            spin = _gear_spin()
            self._gear_ratio_spins.append(spin)
            gear_grid.addWidget(lbl,  row, col)
            gear_grid.addWidget(spin, row, col + 1)
        auto_inner.addLayout(gear_grid)

        fd_row = QHBoxLayout()
        fd_row.setSpacing(6)
        fd_lbl = QLabel("Final Drive:")
        fd_lbl.setStyleSheet(f"color: {_TEXT};")
        fd_row.addWidget(fd_lbl)
        self._spin_final_drive = QDoubleSpinBox()
        self._spin_final_drive.setRange(0.0, 7.0)
        self._spin_final_drive.setDecimals(3)
        self._spin_final_drive.setSingleStep(0.001)
        self._spin_final_drive.setSpecialValueText("—")
        self._spin_final_drive.setValue(0.0)
        self._spin_final_drive.setToolTip("Final drive ratio — not in UDP telemetry, enter manually")
        fd_row.addWidget(self._spin_final_drive)
        fd_row.addSpacing(20)
        ts_lbl = QLabel("Top Speed:")
        ts_lbl.setStyleSheet(f"color: {_TEXT};")
        fd_row.addWidget(ts_lbl)
        self._spin_top_speed = QDoubleSpinBox()
        self._spin_top_speed.setRange(0, 500)
        self._spin_top_speed.setDecimals(0)
        self._spin_top_speed.setSingleStep(1)
        self._spin_top_speed.setSuffix(" km/h")
        self._spin_top_speed.setSpecialValueText("—")
        self._spin_top_speed.setValue(0)
        self._spin_top_speed.setToolTip("Transmission top speed target — auto-filled from UDP")
        fd_row.addWidget(self._spin_top_speed)
        fd_row.addStretch()
        auto_inner.addLayout(fd_row)

        self._btn_reread_gears = QPushButton("Re-read from Telemetry")
        self._btn_reread_gears.setToolTip(
            "Pull the latest gear ratios and top speed from the live UDP stream.\n"
            "Gear values are captured once on first valid packet — use this to refresh."
        )
        self._btn_reread_gears.setFixedHeight(24)
        self._btn_reread_gears.clicked.connect(
            lambda: self._host._reread_gear_ratios() if hasattr(self._host, "_reread_gear_ratios") else None
        )
        auto_inner.addWidget(self._btn_reread_gears)
        outer.addWidget(auto_grp)

        # --- Manual-entry spinboxes ---
        def _dbl(lo, hi, step=0.5, dec=1, val=0.0):
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(step)
            w.setDecimals(dec)
            w.setValue(val)
            return w

        def _int(lo, hi, val=1):
            w = QSpinBox()
            w.setRange(lo, hi)
            w.setValue(val)
            return w

        self._setup_rh_f       = _int(60, 200, 80)
        self._setup_rh_r       = _int(60, 200, 80)
        self._setup_spr_f      = _dbl(1.00, 20.00, 0.10, 2, 3.50)
        self._setup_spr_f.setToolTip(
            "Spring natural frequency in Hz — GT7's suspension stiffness unit.\n"
            "Higher = stiffer. Stiffer front → more understeer on corner entry.\n"
            "Road cars: 1.5–3 Hz  |  Sport: 3–5 Hz  |  Race (GT3): 4–8 Hz")
        self._setup_spr_r      = _dbl(1.00, 20.00, 0.10, 2, 3.00)
        self._setup_spr_r.setToolTip(
            "Spring natural frequency in Hz — GT7's suspension stiffness unit.\n"
            "Higher = stiffer. Stiffer rear → more oversteer on corner entry.\n"
            "Road cars: 1.5–3 Hz  |  Sport: 3–5 Hz  |  Race (GT3): 4–8 Hz")
        self._setup_dmp_f_comp = _int(1, 100, 30)
        self._setup_dmp_f_comp.setSuffix(" %")
        self._setup_dmp_f_ext  = _int(1, 100, 40)
        self._setup_dmp_f_ext.setSuffix(" %")
        self._setup_dmp_r_comp = _int(1, 100, 25)
        self._setup_dmp_r_comp.setSuffix(" %")
        self._setup_dmp_r_ext  = _int(1, 100, 35)
        self._setup_dmp_r_ext.setSuffix(" %")
        self._setup_arb_f      = _int(1, 7, 5)
        self._setup_arb_r      = _int(1, 7, 4)
        self._setup_cam_f      = _dbl(0.0, 6.0, 0.1, 1, 1.0)
        self._setup_cam_r      = _dbl(0.0, 6.0, 0.1, 1, 1.5)
        self._setup_toe_f      = _dbl(-2.0, 2.0, 0.01, 2, 0.00)
        self._setup_toe_r      = _dbl(-2.0, 2.0, 0.01, 2, 0.05)
        _cam_tip = (
            "0 = no camber; higher values lean the tyre top inward (GT7 shows 0–6).\n"
            "More camber improves cornering grip but reduces braking stability "
            "and straight-line traction.\n"
            "Less camber gives a flatter contact patch but reduces mid-corner grip."
        )
        self._setup_cam_f.setToolTip(_cam_tip)
        self._setup_cam_r.setToolTip(_cam_tip)
        self._setup_toe_f.setToolTip(
            "Front toe-out (negative) sharpens steering response and corner entry.\n"
            "Too much toe-out makes the car nervous on turn-in.\n"
            "Toe-in (positive) increases straight-line stability but slows steering response."
        )
        self._setup_toe_r.setToolTip(
            "Rear toe-in (positive) improves rear stability on throttle and braking.\n"
            "Too much rear toe-in prevents rotation and adds drag.\n"
            "Rear toe-out (negative) increases rotation but can cause snap oversteer."
        )
        self._setup_aero_f     = _int(0, 1000, 400)
        self._setup_aero_r     = _int(0, 1000, 600)
        self._setup_lsd_i      = _int(0, 60, 10)
        self._setup_lsd_a      = _int(0, 60, 15)
        self._setup_lsd_d      = _int(0, 60, 5)
        self._setup_lsd_f_i    = _int(0, 60, 10)
        self._setup_lsd_f_a    = _int(0, 60, 15)
        self._setup_lsd_f_d    = _int(0, 60, 5)
        self._setup_bb         = _int(-5, 5, 0)
        self._setup_bb.setSingleStep(1)

        from data.tyres import compound_names as _cpd_names
        _tyre_names = _cpd_names()
        _rm_idx = _tyre_names.index("Racing Medium")
        self._setup_tyre_f = QComboBox()
        self._setup_tyre_f.addItems(_tyre_names)
        self._setup_tyre_f.setCurrentIndex(_rm_idx)
        self._setup_tyre_r = QComboBox()
        self._setup_tyre_r.addItems(_tyre_names)
        self._setup_tyre_r.setCurrentIndex(_rm_idx)

        self._setup_tvcd = QComboBox()
        self._setup_tvcd.addItems(["None", "Active"])
        self._setup_torque_dist = _int(0, 100, 50)
        self._setup_torque_dist.setSuffix(" (Rear %)")

        self._setup_ecu = QComboBox()
        self._setup_ecu.addItems(["Stock", "Fully Customisable"])
        self._setup_ecu_output = _dbl(0.0, 100.0, 1.0, 1, 100.0)
        self._setup_ecu_output.setSuffix(" %")

        self._setup_trans_type = QComboBox()
        for _tt in ["Stock", "Fully Customisable", "Fully Customisable: Racing",
                    "Fully Customisable: Close-Ratio", "Fully Customisable: Wide-Ratio"]:
            self._setup_trans_type.addItem(_tt)

        self._setup_nitrous = QComboBox()
        self._setup_nitrous.addItems(["None", "Nitrous", "Overtake"])
        self._setup_nitrous_output = _dbl(0.0, 100.0, 1.0, 1, 0.0)
        self._setup_nitrous_output.setSuffix(" %")

        self._setup_min_weight = _dbl(0.0, 1500.0, 1.0, 0, 0.0)
        self._setup_min_weight.setToolTip(
            "Car's minimum weight regulation in kg.\n"
            "0 = no regulation, use car's base weight.\n"
            "AI uses this to recommend how much ballast to add.")
        self._setup_max_power  = _dbl(0.0, 2000.0, 1.0, 0, 0.0)
        self._setup_max_power.setToolTip(
            "Car's maximum allowed power in hp.\n"
            "0 = no regulation, use car's full power.\n"
            "AI uses this to recommend power restrictor setting.")

        self._setup_ballast_kg  = _dbl(0.0, 150.0, 0.5, 1, 0.0)
        self._setup_ballast_kg.setToolTip("Kilograms of ballast added to the car.")
        self._setup_ballast_pos = _int(-50, 50, 0)
        self._setup_ballast_pos.setToolTip(
            "Ballast position: −50 = full rear, +50 = full front, 0 = neutral.")
        self._setup_power_rest  = _dbl(0.0, 100.0, 1.0, 1, 100.0)
        self._setup_power_rest.setToolTip(
            "Power restrictor as percentage of max power.\n"
            "100% = fully unrestricted. Lower to reduce power output.")

        self._setup_actual_bhp = _dbl(0.0, 2000.0, 1.0, 0, 0.0)
        self._setup_actual_bhp.setSpecialValueText("Not specified")
        self._setup_actual_bhp.setSuffix(" hp")
        self._setup_actual_bhp.setToolTip(
            "Car's actual installed power in hp AFTER all engine performance upgrades.\n"
            "This is the real output the car makes — NOT the regulation cap.\n"
            "e.g. fully upgraded 812 Superfast ≈ 1050 hp. AI uses this to correctly\n"
            "calculate which ECU stage + Power Restrictor hits the max_power target.")

        self._setup_num_gears = _int(0, 8, 0)
        self._setup_num_gears.setSpecialValueText("Auto")
        self._setup_num_gears.setToolTip(
            "Number of forward gears in this car.\n"
            "0 = AI will use its knowledge of the car.\n"
            "Set this explicitly to ensure correct gear ratios (e.g. 812 = 7 gears).")

        self._setup_drivetrain = QComboBox()
        for _dt in ("Auto-detect", "FR", "FF", "MR", "RR", "AWD"):
            self._setup_drivetrain.addItem(_dt, _dt if _dt != "Auto-detect" else "")
        self._setup_drivetrain.setToolTip(
            "Car's drivetrain layout. Sets up AI's handling philosophy.\n"
            "FR = front-engine rear-drive, MR = mid-rear-drive, AWD = all-wheel drive.")

        self._setup_label = QLineEdit()
        self._setup_label.setPlaceholderText("e.g. Race Baseline, Wet Setup…")
        self._setup_label.setMaxLength(40)
        self._setup_notes = QLineEdit()
        self._setup_notes.setPlaceholderText("Optional notes")

        # --- Section helpers (local) ---
        def _section(title, color="#AAE4AA"):
            grp = QGroupBox(title)
            grp.setStyleSheet(
                f"QGroupBox {{ color: {color}; font-weight: bold; "
                f"border: 1px solid #333; border-radius: 4px; margin-top: 6px; padding-top: 6px; }}"
                f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
            )
            return grp

        def _fr_grid(grp, rows):
            inner = QGridLayout(grp)
            inner.setContentsMargins(8, 4, 8, 4)
            inner.setVerticalSpacing(3)
            inner.setHorizontalSpacing(8)
            hdr_style = "color: #8BC34A; font-weight: bold;"
            inner.addWidget(QLabel("Front", styleSheet=hdr_style), 0, 1)
            inner.addWidget(QLabel("Rear",  styleSheet=hdr_style), 0, 2)
            for r, row_data in enumerate(rows, 1):
                lbl_text = row_data[0]
                fw       = row_data[1]
                rw       = row_data[2]
                unit     = row_data[3] if len(row_data) > 3 else ""
                inner.addWidget(QLabel(lbl_text, styleSheet=lbl_s,
                                       alignment=Qt.AlignmentFlag.AlignRight), r, 0)
                inner.addWidget(fw, r, 1)
                inner.addWidget(rw, r, 2)
                if unit:
                    inner.addWidget(QLabel(unit, styleSheet="color: #666;"), r, 3)
            inner.setColumnStretch(0, 3)
            inner.setColumnStretch(1, 2)
            inner.setColumnStretch(2, 2)
            inner.setColumnStretch(3, 1)

        # ── Tyres ─────────────────────────────────────────────────────────────
        tyre_grp = _section("Tyres")
        _fr_grid(tyre_grp, [
            ("Compound", self._setup_tyre_f, self._setup_tyre_r),
        ])
        outer.addWidget(tyre_grp)

        # ── Suspension ────────────────────────────────────────────────────────
        susp_grp = _section("Suspension")
        _fr_grid(susp_grp, [
            ("Body Height Adjustment (mm)", self._setup_rh_f,       self._setup_rh_r),
            ("Anti-Roll Bar (Lv.)",         self._setup_arb_f,      self._setup_arb_r),
            ("Damping Ratio (Compression)", self._setup_dmp_f_comp, self._setup_dmp_r_comp),
            ("Damping Ratio (Expansion)",   self._setup_dmp_f_ext,  self._setup_dmp_r_ext),
            ("Natural Frequency",           self._setup_spr_f,      self._setup_spr_r,    "Hz"),
            ("Camber Angle (°)",             self._setup_cam_f,      self._setup_cam_r,    "°"),
            ("Toe Angle (°)",               self._setup_toe_f,      self._setup_toe_r,    "°"),
        ])
        outer.addWidget(susp_grp)

        # ── Differential Gear ─────────────────────────────────────────────────
        diff_grp = _section("Differential Gear")
        diff_inner = QFormLayout(diff_grp)
        diff_inner.setContentsMargins(8, 4, 8, 4)
        diff_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _lsd_w = QWidget()
        _lsd_h = QHBoxLayout(_lsd_w)
        _lsd_h.setContentsMargins(0, 0, 0, 0)
        for lbl_txt, spin in (
            ("Initial Torque",     self._setup_lsd_i),
            ("Accel Sensitivity",  self._setup_lsd_a),
            ("Braking Sensitivity",self._setup_lsd_d),
        ):
            _lsd_h.addWidget(QLabel(lbl_txt + ":", styleSheet="color: #888; font-size: 10px;"))
            _lsd_h.addWidget(spin)
        _lsd_h.addStretch()
        diff_inner.addRow(QLabel("LSD (Rear):", styleSheet=lbl_s), _lsd_w)

        _lsd_f_w = QWidget()
        _lsd_f_h = QHBoxLayout(_lsd_f_w)
        _lsd_f_h.setContentsMargins(0, 0, 0, 0)
        for _lt, _sp in (
            ("Initial Torque",     self._setup_lsd_f_i),
            ("Accel Sensitivity",  self._setup_lsd_f_a),
            ("Braking Sensitivity",self._setup_lsd_f_d),
        ):
            _lsd_f_h.addWidget(QLabel(_lt + ":", styleSheet="color: #888; font-size: 10px;"))
            _lsd_f_h.addWidget(_sp)
        _lsd_f_h.addStretch()
        self._lbl_lsd_front = QLabel("LSD (Front):", styleSheet=lbl_s)
        diff_inner.addRow(self._lbl_lsd_front, _lsd_f_w)
        self._lsd_front_widget = _lsd_f_w

        _is_awd = self._setup_drivetrain.currentText() == "AWD"
        self._lbl_lsd_front.setVisible(_is_awd)
        self._lsd_front_widget.setVisible(_is_awd)
        # AWD visibility is handled by the host's _update_lsd_visibility
        self._setup_drivetrain.currentTextChanged.connect(self._on_drivetrain_changed)

        diff_inner.addRow(QLabel("Torque-Vectoring Centre Diff:", styleSheet=lbl_s), self._setup_tvcd)
        diff_inner.addRow(QLabel("Front/Rear Torque Distribution:", styleSheet=lbl_s), self._setup_torque_dist)
        diff_inner.addRow(QLabel("Brake Bias (−5F … +5R):", styleSheet=lbl_s), self._setup_bb)
        outer.addWidget(diff_grp)

        # ── Aerodynamics ──────────────────────────────────────────────────────
        aero_grp = _section("Aerodynamics")
        _fr_grid(aero_grp, [
            ("Downforce (kg)", self._setup_aero_f, self._setup_aero_r),
        ])
        outer.addWidget(aero_grp)

        # ── Performance Adjustment ────────────────────────────────────────────
        perf_grp = _section("Performance Adjustment", "#CCAAFF")
        perf_inner = QFormLayout(perf_grp)
        perf_inner.setContentsMargins(8, 4, 8, 4)
        perf_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _bal_w = QWidget()
        _bal_h = QHBoxLayout(_bal_w)
        _bal_h.setContentsMargins(0, 0, 0, 0)
        _bal_h.addWidget(self._setup_ballast_kg)
        _bal_h.addWidget(QLabel("kg  pos:", styleSheet="color:#888; font-size:10px;"))
        _bal_h.addWidget(self._setup_ballast_pos)
        _bal_h.addStretch()
        perf_inner.addRow(QLabel("Ballast:", styleSheet=lbl_s), _bal_w)
        perf_inner.addRow(QLabel("Power Restrictor (%):", styleSheet=lbl_s), self._setup_power_rest)
        _wt_w = QWidget()
        _wt_h = QHBoxLayout(_wt_w)
        _wt_h.setContentsMargins(0, 0, 0, 0)
        _wt_h.addWidget(self._setup_min_weight)
        _wt_h.addWidget(QLabel("kg  /  max:", styleSheet="color:#888; font-size:10px;"))
        _wt_h.addWidget(self._setup_max_power)
        _wt_h.addWidget(QLabel("hp", styleSheet="color:#888; font-size:10px;"))
        _wt_h.addStretch()
        perf_inner.addRow(QLabel("Min Weight / Max Power:", styleSheet=lbl_s), _wt_w)
        outer.addWidget(perf_grp)

        # ── Engine / ECU ──────────────────────────────────────────────────────
        ecu_grp = _section("Engine / ECU", "#88CCFF")
        ecu_inner = QFormLayout(ecu_grp)
        ecu_inner.setContentsMargins(8, 4, 8, 4)
        ecu_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        ecu_inner.addRow(QLabel("Installed BHP:", styleSheet=lbl_s), self._setup_actual_bhp)
        ecu_inner.addRow(QLabel("Number of Gears:", styleSheet=lbl_s), self._setup_num_gears)
        ecu_inner.addRow(QLabel("Drivetrain:", styleSheet=lbl_s), self._setup_drivetrain)
        self._lbl_ecu_rec = QLabel(
            "—",
            wordWrap=True,
            styleSheet=(
                "color: #F5C542; background: #1A1A00; border: 1px solid #555;"
                " padding: 4px 6px; border-radius: 3px;"
            ),
        )
        self._lbl_ecu_rec.setToolTip(
            "AI recommendation for ECU stage and/or Power Restrictor to hit the target power.\n"
            "Fill in Max Power above then click 'Build Setup with AI' to generate."
        )
        ecu_inner.addRow(QLabel("ECU / Power Advice:", styleSheet=lbl_s), self._lbl_ecu_rec)
        ecu_inner.addRow(QLabel("ECU (in-game):", styleSheet=lbl_s), self._setup_ecu)
        _ecu_out_w = QWidget()
        _ecu_out_h = QHBoxLayout(_ecu_out_w)
        _ecu_out_h.setContentsMargins(0, 0, 0, 0)
        _ecu_out_h.addWidget(self._setup_ecu_output)
        _ecu_out_h.addStretch()
        ecu_inner.addRow(QLabel("ECU Output Adjustment:", styleSheet=lbl_s), _ecu_out_w)
        outer.addWidget(ecu_grp)

        # ── Transmission type ──────────────────────────────────────────────────
        trans_grp = _section("Transmission", "#FFCC88")
        trans_inner = QFormLayout(trans_grp)
        trans_inner.setContentsMargins(8, 4, 8, 4)
        trans_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        trans_inner.addRow(QLabel("Transmission Type:", styleSheet=lbl_s), self._setup_trans_type)
        outer.addWidget(trans_grp)

        # ── Nitrous / Overtake ────────────────────────────────────────────────
        nitrous_grp = _section("Nitrous / Overtake", "#FF8844")
        nitrous_inner = QFormLayout(nitrous_grp)
        nitrous_inner.setContentsMargins(8, 4, 8, 4)
        nitrous_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        nitrous_inner.addRow(QLabel("Type:", styleSheet=lbl_s), self._setup_nitrous)
        _nos_out_w = QWidget()
        _nos_out_h = QHBoxLayout(_nos_out_w)
        _nos_out_h.setContentsMargins(0, 0, 0, 0)
        _nos_out_h.addWidget(self._setup_nitrous_output)
        _nos_out_h.addStretch()
        nitrous_inner.addRow(QLabel("Output Adjustment:", styleSheet=lbl_s), _nos_out_w)
        outer.addWidget(nitrous_grp)

        # ── Notes ─────────────────────────────────────────────────────────────
        notes_row = QFormLayout()
        notes_row.addRow(QLabel("Setup Label:", styleSheet=lbl_s), self._setup_label)
        notes_row.addRow(QLabel("Notes:", styleSheet=lbl_s), self._setup_notes)
        outer.addLayout(notes_row)

        # ── Race Engineer Brief (Race only) ───────────────────────────────────
        self._re_brief_label = QLabel("Race Engineer Brief:", styleSheet=lbl_s)
        self._re_brief_input = QTextEdit()
        self._re_brief_input.setMaximumHeight(80)
        self._re_brief_input.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #555;")
        self._re_brief_input.setPlaceholderText(
            "Optional race engineer notes — injected verbatim into the AI prompt "
            "(strategy preference, tyre targets, acceptable compromises, traffic, etc.)")
        re_brief_row = QHBoxLayout()
        re_brief_row.addWidget(self._re_brief_label)
        re_brief_row.addWidget(self._re_brief_input)
        outer.addLayout(re_brief_row)
        # Show RE brief for Race; hide for Qualifying
        _show_re = (self.purpose == "Race")
        self._re_brief_label.setVisible(_show_re)
        self._re_brief_input.setVisible(_show_re)

        # ── Save / Load / Analyse row ─────────────────────────────────────────
        self._setup_load_combo = QComboBox()
        self._setup_load_combo.setMinimumWidth(180)
        self._btn_save_setup    = QPushButton("Save Setup")
        self._btn_load_setup    = QPushButton("Load Selected")
        self._btn_analyse_setup = QPushButton("Analyse & Get Setup Fix")
        self._btn_analyse_setup.setStyleSheet(
            "background: #1F4E78; color: white; font-weight: bold; padding: 6px 12px;")
        self._btn_analyse_setup.setToolTip(
            "Analyse all laps tagged with this setup using AI.\n"
            "If you've described a handling issue below, that's included in the analysis too.")

        setup_btn_row = QHBoxLayout()
        setup_btn_row.addWidget(self._btn_save_setup)
        setup_btn_row.addWidget(QLabel("Load:", styleSheet=lbl_s))
        setup_btn_row.addWidget(self._setup_load_combo)
        setup_btn_row.addWidget(self._btn_load_setup)
        setup_btn_row.addStretch()
        setup_btn_row.addWidget(self._btn_analyse_setup)
        outer.addLayout(setup_btn_row)

        self._lbl_setup_save_status = QLabel("")
        self._lbl_setup_save_status.setStyleSheet(
            "color: #8BC34A; font-size: 10px; font-style: italic; padding: 2px 0;")
        outer.addWidget(self._lbl_setup_save_status)

        # ── Result text (analyse output) ──────────────────────────────────────
        self._setup_result_text = QTextEdit()
        self._setup_result_text.setReadOnly(True)
        self._setup_result_text.setMinimumHeight(180)
        self._setup_result_text.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #444;")
        self._setup_result_text.setPlaceholderText(
            "AI setup suggestions will appear here after analysis.")
        outer.addWidget(self._setup_result_text)

        self._btn_apply_ai_setup = QPushButton("Apply Pit Crew recommendation")
        self._btn_apply_ai_setup.setStyleSheet(
            "background: #2E6A4A; color: white; font-weight: bold; padding: 6px 12px;")
        self._btn_apply_ai_setup.setToolTip(
            "Apply the Pit Crew's recommended changes to the setup form.\n"
            "Changed fields are highlighted until you click Save Setup to persist them.")
        self._btn_apply_ai_setup.setVisible(False)
        outer.addWidget(self._btn_apply_ai_setup)

        # NOTE: the old "Rate this result" combo + "Applied" checkbox were removed.

        # ── Build Setup with AI + Set Car Ranges ──────────────────────────────
        _build_row = QHBoxLayout()
        self._btn_build_setup = QPushButton("Build Setup with AI")
        self._btn_build_setup.setStyleSheet(
            "background: #1A5C2A; color: white; font-weight: bold; padding: 6px 16px;")
        # Group 43: ungated AI-build path disabled pending a rule-first baseline generator.
        self._btn_build_setup.setEnabled(False)
        self._btn_build_setup.setVisible(False)
        self._btn_build_setup.setToolTip(
            "Build Setup with AI is unavailable — use Analyse to get AI-guided, "
            "rule-validated setup changes.")
        self._btn_set_car_ranges = QPushButton("Set Car Ranges…")
        self._btn_set_car_ranges.setToolTip(
            "Define per-car min/max bounds for every setup parameter.\n"
            "These bounds constrain the spinboxes and the AI output for this car.")
        _build_row.addWidget(self._btn_build_setup)
        _build_row.addWidget(self._btn_set_car_ranges)
        _build_row.addStretch()
        outer.addLayout(_build_row)

        # ── Build result text ─────────────────────────────────────────────────
        self._build_setup_result = QTextEdit()
        self._build_setup_result.setReadOnly(True)
        self._build_setup_result.setMinimumHeight(280)
        self._build_setup_result.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #444; "
            f"border-left: 3px solid #3A8C4A;")
        self._build_setup_result.setVisible(False)
        outer.addWidget(self._build_setup_result)

        # ── Handling notes ────────────────────────────────────────────────────
        self._setup_feeling_input = QTextEdit()
        self._setup_feeling_input.setMaximumHeight(70)
        self._setup_feeling_input.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #555;")
        self._setup_feeling_input.setPlaceholderText(
            "Optional: describe any handling issues to include in the AI analysis above.\n"
            "e.g.  \"rear is loose on acceleration\"  |  \"locks on braking at T6\"  |  "
            "\"front pushes in fast corners\"")
        feeling_row = QHBoxLayout()
        feeling_row.addWidget(QLabel("Handling notes:", styleSheet=lbl_s))
        feeling_row.addWidget(self._setup_feeling_input)
        outer.addLayout(feeling_row)

        outer.addStretch()

    # ------------------------------------------------------------------
    # Drivetrain → LSD-front visibility (self-contained per form)
    # ------------------------------------------------------------------

    def _on_drivetrain_changed(self, text: str = "") -> None:
        """Show/hide LSD Front row based on drivetrain selection."""
        is_awd = text == "AWD"
        if hasattr(self, "_lbl_lsd_front"):
            self._lbl_lsd_front.setVisible(is_awd)
        if hasattr(self, "_lsd_front_widget"):
            self._lsd_front_widget.setVisible(is_awd)

    # ------------------------------------------------------------------
    # Public accessors used by SetupBuilderMixin
    # ------------------------------------------------------------------

    def current_setup_dict(self) -> dict:
        """Serialise this form's fields to a dict.

        ``setup_type`` is derived from ``self.purpose`` (fixed, not a combo).
        """
        gear_ratios = [s.value() for s in self._gear_ratio_spins if s.value() > 0.0]
        _ev_ctx = self._host._build_event_context() if hasattr(self._host, "_build_event_context") else None
        _car  = (_ev_ctx.car  if _ev_ctx else None) or "Unknown Car"
        _track = (_ev_ctx.track if _ev_ctx else None) or ""
        _weather = (_ev_ctx.weather if _ev_ctx else None) or "Dry"
        _bop = _ev_ctx.bop_enabled if _ev_ctx else False
        _condition = {
            "Fixed Dry": "Dry", "Dry": "Dry", "Random Weather": "Dry",
            "Fixed Wet": "Wet", "Wet": "Wet", "Heavy Rain": "Wet",
            "Light Rain": "Damp", "Wet Risk": "Damp", "Damp": "Damp",
        }.get(_weather, "Dry")
        _setup_type_str = "Qualifying Setup" if self.purpose == "Qualifying" else "Race Setup"
        return {
            "name":      _car,
            "car":       _car,
            "setup_label": self._setup_label.text().strip() or "Setup 1",
            "track":     _track,
            "condition": _condition,
            "setup_type": _setup_type_str,
            "ride_height_front": self._setup_rh_f.value(),
            "ride_height_rear":  self._setup_rh_r.value(),
            "springs_front": self._setup_spr_f.value(),
            "springs_rear":  self._setup_spr_r.value(),
            "dampers_front_comp": self._setup_dmp_f_comp.value(),
            "dampers_front_ext":  self._setup_dmp_f_ext.value(),
            "dampers_rear_comp":  self._setup_dmp_r_comp.value(),
            "dampers_rear_ext":   self._setup_dmp_r_ext.value(),
            "arb_front":     self._setup_arb_f.value(),
            "arb_rear":      self._setup_arb_r.value(),
            "camber_front":  self._setup_cam_f.value(),
            "camber_rear":   self._setup_cam_r.value(),
            "toe_front":     self._setup_toe_f.value(),
            "toe_rear":      self._setup_toe_r.value(),
            "aero_front":    self._setup_aero_f.value(),
            "aero_rear":     self._setup_aero_r.value(),
            "lsd_initial":   self._setup_lsd_i.value(),
            "lsd_accel":     self._setup_lsd_a.value(),
            "lsd_decel":     self._setup_lsd_d.value(),
            "lsd_front_initial": (
                self._setup_lsd_f_i.value()
                if self._setup_drivetrain.currentText() == "AWD" else 0
            ),
            "lsd_front_accel": (
                self._setup_lsd_f_a.value()
                if self._setup_drivetrain.currentText() == "AWD" else 0
            ),
            "lsd_front_decel": (
                self._setup_lsd_f_d.value()
                if self._setup_drivetrain.currentText() == "AWD" else 0
            ),
            "tvcd":          self._setup_tvcd.currentText(),
            "torque_distribution_rear": self._setup_torque_dist.value(),
            "brake_bias_front": self._setup_bb.value(),
            "ballast_kg":       self._setup_ballast_kg.value(),
            "ballast_position": self._setup_ballast_pos.value(),
            "power_restrictor": self._setup_power_rest.value(),
            "tyre_front":     self._setup_tyre_f.currentText(),
            "tyre_rear":      self._setup_tyre_r.currentText(),
            "ecu_ingame":     self._setup_ecu.currentText(),
            "ecu_ingame_output": self._setup_ecu_output.value(),
            "transmission_type": self._setup_trans_type.currentText(),
            "nitrous_type":   self._setup_nitrous.currentText(),
            "nitrous_output": self._setup_nitrous_output.value(),
            "notes":          self._setup_notes.text().strip(),
            "ecu_recommendation": self._lbl_ecu_rec.text() if hasattr(self, "_lbl_ecu_rec") else "",
            "bop_race":       _bop,
            "gear_ratios":    gear_ratios,
            "final_drive":    self._spin_final_drive.value(),
            "transmission_max_speed_kmh": int(self._spin_top_speed.value()),
            "captured_at":    time.strftime("%Y-%m-%d %H:%M"),
        }

    def fill_setup_fields(self, d: dict) -> None:
        """Populate all form fields from a saved setup dict."""
        car = d.get("name", "")
        if car and hasattr(self._host, "_autofill_car_specs"):
            self._host._autofill_car_specs(car)
        if hasattr(self._host, "_rebound_setup_spinboxes"):
            self._host._rebound_setup_spinboxes(car or None)
        self._setup_rh_f.setValue(d.get("ride_height_front", 80))
        self._setup_rh_r.setValue(d.get("ride_height_rear", 80))
        self._setup_spr_f.setValue(d.get("springs_front", 3.50))
        self._setup_spr_r.setValue(d.get("springs_rear",  3.00))
        self._setup_dmp_f_comp.setValue(d.get("dampers_front_comp", d.get("dampers_front", 30)))
        self._setup_dmp_f_ext.setValue(d.get("dampers_front_ext", d.get("dampers_front", 40)))
        self._setup_dmp_r_comp.setValue(d.get("dampers_rear_comp", d.get("dampers_rear", 25)))
        self._setup_dmp_r_ext.setValue(d.get("dampers_rear_ext", d.get("dampers_rear", 35)))
        self._setup_arb_f.setValue(d.get("arb_front", 5))
        self._setup_arb_r.setValue(d.get("arb_rear", 4))
        self._setup_cam_f.setValue(abs(d.get("camber_front", 1.0)))
        self._setup_cam_r.setValue(abs(d.get("camber_rear", 1.5)))
        self._setup_toe_f.setValue(d.get("toe_front", 0.00))
        self._setup_toe_r.setValue(d.get("toe_rear", 0.05))
        self._setup_aero_f.setValue(d.get("aero_front", 400))
        self._setup_aero_r.setValue(d.get("aero_rear", 600))
        self._setup_lsd_i.setValue(d.get("lsd_initial", 10))
        self._setup_lsd_a.setValue(d.get("lsd_accel", 15))
        self._setup_lsd_d.setValue(d.get("lsd_decel", 5))
        self._setup_lsd_f_i.setValue(int(d.get("lsd_front_initial", 10)))
        self._setup_lsd_f_a.setValue(int(d.get("lsd_front_accel", 15)))
        self._setup_lsd_f_d.setValue(int(d.get("lsd_front_decel", 5)))
        _tvcd_idx = self._setup_tvcd.findText(d.get("tvcd", "None"))
        if _tvcd_idx >= 0:
            self._setup_tvcd.setCurrentIndex(_tvcd_idx)
        self._setup_torque_dist.setValue(int(d.get("torque_distribution_rear", 50)))
        self._setup_bb.setValue(int(d.get("brake_bias_front", 0)))
        self._setup_ballast_kg.setValue(float(d.get("ballast_kg", 0.0)))
        self._setup_ballast_pos.setValue(int(d.get("ballast_position", 0)))
        self._setup_power_rest.setValue(float(d.get("power_restrictor", 100.0)))
        from data.tyres import normalise_name as _nn
        _tf = _nn(d.get("tyre_front", "Racing Medium")) or "Racing Medium"
        _tf_idx = self._setup_tyre_f.findText(_tf)
        if _tf_idx >= 0:
            self._setup_tyre_f.setCurrentIndex(_tf_idx)
        _tr = _nn(d.get("tyre_rear", "Racing Medium")) or "Racing Medium"
        _tr_idx = self._setup_tyre_r.findText(_tr)
        if _tr_idx >= 0:
            self._setup_tyre_r.setCurrentIndex(_tr_idx)
        _ecu_idx = self._setup_ecu.findText(d.get("ecu_ingame", "Stock"))
        if _ecu_idx >= 0:
            self._setup_ecu.setCurrentIndex(_ecu_idx)
        self._setup_ecu_output.setValue(float(d.get("ecu_ingame_output", 100.0)))
        _tt_idx = self._setup_trans_type.findText(d.get("transmission_type", "Stock"))
        if _tt_idx >= 0:
            self._setup_trans_type.setCurrentIndex(_tt_idx)
        _nos_idx = self._setup_nitrous.findText(d.get("nitrous_type", "None"))
        if _nos_idx >= 0:
            self._setup_nitrous.setCurrentIndex(_nos_idx)
        self._setup_nitrous_output.setValue(float(d.get("nitrous_output", 0.0)))
        self._setup_label.setText(d.get("setup_label", "Setup 1"))
        self._setup_notes.setText(d.get("notes", ""))
        ecu = d.get("ecu_recommendation", "")
        self._lbl_ecu_rec.setText(ecu if ecu and ecu != "—" else "—")
        saved_ratios = d.get("gear_ratios", [])
        for i, spin in enumerate(self._gear_ratio_spins):
            spin.setValue(float(saved_ratios[i]) if i < len(saved_ratios) else 0.0)
        if hasattr(self._host, "_gear_ratios_captured"):
            self._host._gear_ratios_captured = any(r > 0.0 for r in saved_ratios)
        self._spin_final_drive.setValue(float(d.get("final_drive", 0.0)))
        self._spin_top_speed.setValue(float(d.get("transmission_max_speed_kmh", 0)))

    def purpose_prefix(self) -> str:
        """Return 'Q' for Qualifying, 'R' for Race."""
        return "Q" if self.purpose == "Qualifying" else "R"

    def apply_ai_fields(self, fields: dict) -> None:
        """Merge AI-recommended numeric fields into this form's current dict and re-fill.

        Handles the gear_1..gear_6 → gear_ratios list mapping so that approved
        gearbox fields from the backend (which uses individual gear keys) are
        correctly written into the Transmission spinboxes.

        final_drive is applied directly via _spin_final_drive; it is also
        written into the current setup dict so fill_setup_fields persists it.

        transmission_max_speed_kmh is display-only — never applied here (the
        backend strips it from approved_fields, but we guard defensively).
        """
        current = self.current_setup_dict()

        # Map individual gear_N keys back to the gear_ratios list that
        # fill_setup_fields reads.  Merge into the existing list so un-changed
        # gears are preserved.
        _GEAR_KEYS = ("gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6")
        _existing_ratios: list = list(current.get("gear_ratios", []))
        _gear_updates: dict[int, float] = {}
        for _gear_key in _GEAR_KEYS:
            if _gear_key in fields:
                _idx = int(_gear_key[-1]) - 1  # gear_1 → index 0
                try:
                    _gear_updates[_idx] = float(fields[_gear_key])
                except (TypeError, ValueError):
                    pass
        if _gear_updates:
            # Ensure the list is long enough to hold the highest updated index.
            _max_idx = max(_gear_updates.keys())
            while len(_existing_ratios) <= _max_idx:
                _existing_ratios.append(0.0)
            for _idx, _val in _gear_updates.items():
                _existing_ratios[_idx] = _val
            current["gear_ratios"] = _existing_ratios

        # final_drive: apply directly to the spinbox (not via fill_setup_fields
        # key lookup) and also write into current so the save path persists it.
        if "final_drive" in fields:
            try:
                _fd_val = float(fields["final_drive"])
                current["final_drive"] = _fd_val
                if hasattr(self, "_spin_final_drive"):
                    self._spin_final_drive.setValue(_fd_val)
            except (TypeError, ValueError):
                pass

        # Strip display-only fields and already-applied gearbox keys before update.
        _skip = frozenset(_GEAR_KEYS) | {"transmission_max_speed_kmh", "final_drive"}
        _remaining = {k: v for k, v in fields.items() if k not in _skip}
        current.update(_remaining)
        self.fill_setup_fields(current)

    def clear_highlights(self) -> None:
        """Remove any AI-highlight styling from this form's spinboxes."""
        _HIGHLIGHT_PARAM_MAP: dict[str, str] = {
            "ride_height_front":  "_setup_rh_f",
            "ride_height_rear":   "_setup_rh_r",
            "springs_front":      "_setup_spr_f",
            "springs_rear":       "_setup_spr_r",
            "dampers_front_comp": "_setup_dmp_f_comp",
            "dampers_front_ext":  "_setup_dmp_f_ext",
            "dampers_rear_comp":  "_setup_dmp_r_comp",
            "dampers_rear_ext":   "_setup_dmp_r_ext",
            "arb_front":          "_setup_arb_f",
            "arb_rear":           "_setup_arb_r",
            "camber_front":       "_setup_cam_f",
            "camber_rear":        "_setup_cam_r",
            "toe_front":          "_setup_toe_f",
            "toe_rear":           "_setup_toe_r",
            "aero_front":         "_setup_aero_f",
            "aero_rear":          "_setup_aero_r",
            "lsd_initial":        "_setup_lsd_i",
            "lsd_accel":          "_setup_lsd_a",
            "lsd_decel":          "_setup_lsd_d",
            "lsd_front_initial":  "_setup_lsd_f_i",
            "lsd_front_accel":    "_setup_lsd_f_a",
            "lsd_front_decel":    "_setup_lsd_f_d",
            "brake_bias":         "_setup_bb",
            "ballast_kg":         "_setup_ballast_kg",
            "ballast_position":   "_setup_ballast_pos",
            "power_restrictor":   "_setup_power_rest",
        }
        for key in list(self.highlighted_fields):
            attr = _HIGHLIGHT_PARAM_MAP.get(key)
            if attr:
                w = getattr(self, attr, None)
                if w is not None:
                    w.setStyleSheet("")
        self.highlighted_fields = set()
