"""Setup Builder tab — mixin for MainWindow (DashboardWindow)."""
from __future__ import annotations

import json
import json as _json  # alias used in _display_setup_result (verbatim copy from dashboard.py)
import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QLabel, QPushButton, QCheckBox,
    QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QLineEdit, QTextEdit,
    QComboBox, QScrollArea,
)

from strategy.setup_ranges import resolve_ranges, save_car_ranges, GENERIC_DEFAULTS
from ui.car_ranges_dialog import CarRangesDialog  # noqa: F401 — used in _open_car_ranges_dialog

# Module-level display constants — must match dashboard.py
_DARK_CARD = "#2A2A2A"
_TEXT       = "#E0E0E0"


def _format_validation_errors_banner(validation_errors: list) -> str:
    """Return an HTML banner string for validation_errors from the AI response.

    Pure helper (no Qt) — renders validation errors as an orange warning
    banner in the same style as the DEF-P2-007 event-restriction banner.
    Returns "" when there are no errors to display.
    """
    if not validation_errors:
        return ""
    items = "".join(
        f"<li style='margin:2px 0;'>{e}</li>" for e in validation_errors
    )
    return (
        "<div style='background:#1A1A00; border:1px solid #C8A020; "
        "border-radius:4px; padding:8px; margin-bottom:8px; color:#C8A020;'>"
        "&#9888; <b>Setup Validation Warnings</b>"
        f"<ul style='margin:4px 0 0 0; padding-left:16px;'>{items}</ul>"
        "</div>"
    )


def _format_engineering_validation_banner(eng_errors: list) -> str:
    """Return an HTML banner string for engineering validation failures.

    Distinct from the standard validation-errors banner — uses a red border
    to signal a higher-severity warning: the AI retry did not resolve the
    engineering contradiction and the recommendation should not be applied
    without manual review.
    Returns "" when there are no errors to display.
    """
    if not eng_errors:
        return ""
    items = "".join(
        f"<li style='margin:2px 0;'>{e}</li>" for e in eng_errors
    )
    return (
        "<div style='background:#2A0A0A; border:2px solid #E05050; "
        "border-radius:4px; padding:8px; margin-bottom:8px; color:#E08080;'>"
        "&#9940; <b>Engineering validation failed after AI retry — review before applying.</b>"
        "<br><span style='font-size:11px; color:#CC6060;'>"
        "The recommendation below survived a correction attempt but still contains "
        "engineering contradictions. Do NOT apply blindly.</span>"
        f"<ul style='margin:6px 0 0 0; padding-left:16px;'>{items}</ul>"
        "</div>"
    )


def _set_spin_readonly(spin, readonly: bool) -> None:
    """Make a spinbox read-only (min==max case) or editable again.

    Read-only is preferred over disabled so the value remains visible and
    copyable.  Buttons are hidden when read-only to signal non-editability.
    """
    spin.setReadOnly(readonly)
    spin.setButtonSymbols(
        QAbstractSpinBox.ButtonSymbols.NoButtons
        if readonly
        else QAbstractSpinBox.ButtonSymbols.UpDownArrows
    )


class SetupBuilderMixin:
    """Setup Builder tab methods — mixed into MainWindow."""

    def _build_car_setup_group(self) -> QGroupBox:
        setup_box = QGroupBox("Car Setup")
        setup_layout = QVBoxLayout(setup_box)

        setup_layout.addWidget(QLabel(
            "Enter your current car setup below.  Gear ratios auto-fill from live telemetry "
            "and remain editable.  Final drive must be entered manually.  "
            "Use  Analyse Setup with AI  to get setup change recommendations.",
            styleSheet="color: #999;",
            wordWrap=True,
        ))

        # Transmission sub-section — auto-filled from UDP but fully editable
        auto_grp = QGroupBox("Transmission")
        auto_grp.setStyleSheet(f"QGroupBox {{ color: #AAE4AA; }}")
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
        self._btn_reread_gears.clicked.connect(self._reread_gear_ratios)
        auto_inner.addWidget(self._btn_reread_gears)
        setup_layout.addWidget(auto_grp)

        # Manual entry sub-section
        manual_form = QFormLayout()
        manual_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_s = f"color: {_TEXT};"


        self._lbl_car_specs_info = QLabel(
            "",
            styleSheet="color: #AAAAAA; font-size: 10px;",
        )
        self._lbl_car_specs_info.setVisible(False)
        self._lbl_car_specs_info.setToolTip(
            "Stock car specifications from car_specs.json (PP rating, drivetrain, aspiration, power, weight).\n"
            "Run 'Refresh Data from Web' in Settings to populate these values."
        )

        self._setup_type = QComboBox()
        self._setup_type.addItems(["Race Setup", "Qualifying Setup"])
        self._setup_type.setToolTip(
            "Race Setup: optimise for consistency, tyre life, and fuel efficiency.\n"
            "Qualifying Setup: optimise for single-lap peak pace and tyre warm-up."
        )


        self._lbl_bop_info = QLabel("")
        self._lbl_bop_info.setStyleSheet("color: #88CCFF; font-style: italic;")
        self._lbl_bop_info.setVisible(False)

        self._btn_bop_edit = QPushButton("Edit BOP File")
        self._btn_bop_edit.setFixedHeight(22)
        self._btn_bop_edit.setToolTip("Open data/bop_data.json in default editor, then click Reload.")
        self._btn_bop_edit.clicked.connect(self._open_bop_file)
        self._btn_bop_edit.setVisible(False)

        self._btn_bop_reload = QPushButton("Reload BOP")
        self._btn_bop_reload.setFixedHeight(22)
        self._btn_bop_reload.setToolTip("Re-read bop_data.json and refresh the BOP weight/power display.")
        self._btn_bop_reload.clicked.connect(self._reload_bop_data)
        self._btn_bop_reload.setVisible(False)

        def _dbl(lo, hi, step=0.5, dec=1, val=0.0):
            w = QDoubleSpinBox(); w.setRange(lo, hi); w.setSingleStep(step)
            w.setDecimals(dec); w.setValue(val); return w
        def _int(lo, hi, val=1):
            w = QSpinBox(); w.setRange(lo, hi); w.setValue(val); return w

        self._setup_rh_f       = _int(60, 200, 80)               # ride height front mm
        self._setup_rh_r       = _int(60, 200, 80)               # ride height rear mm
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
        self._setup_dmp_f_comp = _int(1, 100, 30); self._setup_dmp_f_comp.setSuffix(" %")
        self._setup_dmp_f_ext  = _int(1, 100, 40); self._setup_dmp_f_ext.setSuffix(" %")
        self._setup_dmp_r_comp = _int(1, 100, 25); self._setup_dmp_r_comp.setSuffix(" %")
        self._setup_dmp_r_ext  = _int(1, 100, 35); self._setup_dmp_r_ext.setSuffix(" %")
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
        self._setup_bb.setSingleStep(1)  # ensure 1-step increment regardless of Qt defaults

        # Tyre compound selectors — populated from shared compound list
        from data.tyres import compound_names as _cpd_names
        _tyre_names = _cpd_names()
        _rm_idx = _tyre_names.index("Racing Medium")
        self._setup_tyre_f = QComboBox(); self._setup_tyre_f.addItems(_tyre_names)
        self._setup_tyre_f.setCurrentIndex(_rm_idx)
        self._setup_tyre_r = QComboBox(); self._setup_tyre_r.addItems(_tyre_names)
        self._setup_tyre_r.setCurrentIndex(_rm_idx)

        # Differential extras
        self._setup_tvcd = QComboBox(); self._setup_tvcd.addItems(["None", "Active"])
        self._setup_torque_dist = _int(0, 100, 50); self._setup_torque_dist.setSuffix(" (Rear %)")

        # ECU settings (GT7 in-game)
        self._setup_ecu = QComboBox(); self._setup_ecu.addItems(["Stock", "Fully Customisable"])
        self._setup_ecu_output = _dbl(0.0, 100.0, 1.0, 1, 100.0); self._setup_ecu_output.setSuffix(" %")

        # Transmission type
        self._setup_trans_type = QComboBox()
        for _tt in ["Stock", "Fully Customisable", "Fully Customisable: Racing",
                    "Fully Customisable: Close-Ratio", "Fully Customisable: Wide-Ratio"]:
            self._setup_trans_type.addItem(_tt)

        # Nitrous / Overtake
        self._setup_nitrous = QComboBox(); self._setup_nitrous.addItems(["None", "Nitrous", "Overtake"])
        self._setup_nitrous_output = _dbl(0.0, 100.0, 1.0, 1, 0.0); self._setup_nitrous_output.setSuffix(" %")

        # Performance envelope (used as context for Build Setup AI)
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

        # Weight / power management
        self._setup_ballast_kg  = _dbl(0.0, 150.0, 0.5, 1, 0.0)
        self._setup_ballast_kg.setToolTip("Kilograms of ballast added to the car.")
        self._setup_ballast_pos = _int(-50, 50, 0)
        self._setup_ballast_pos.setToolTip("Ballast position: −50 = full rear, +50 = full front, 0 = neutral.")
        self._setup_power_rest  = _dbl(0.0, 100.0, 1.0, 1, 100.0)
        self._setup_power_rest.setToolTip(
            "Power restrictor as percentage of max power.\n"
            "100% = fully unrestricted. Lower to reduce power output.")

        # Car hardware specs (passed to AI for accurate setup generation)
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

        self._setup_label  = QLineEdit(); self._setup_label.setPlaceholderText("e.g. Race Baseline, Wet Setup…"); self._setup_label.setMaxLength(40)
        self._setup_notes  = QLineEdit(); self._setup_notes.setPlaceholderText("Optional notes")

        def _form_row(form, label, *widgets):
            if len(widgets) == 1:
                form.addRow(QLabel(label, styleSheet=lbl_s), widgets[0])
            else:
                w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
                for ww in widgets:
                    h.addWidget(ww)
                h.addStretch()
                form.addRow(QLabel(label, styleSheet=lbl_s), w)

        def _section(title, color="#AAE4AA"):
            grp = QGroupBox(title)
            grp.setStyleSheet(
                f"QGroupBox {{ color: {color}; font-weight: bold; "
                f"border: 1px solid #333; border-radius: 4px; margin-top: 6px; padding-top: 6px; }}"
                f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
            )
            return grp

        def _fr_grid(grp, rows):
            """Build a Front / Rear grid inside grp. rows = [(label, front_w, rear_w, unit?)]"""
            inner = QGridLayout(grp)
            inner.setContentsMargins(8, 4, 8, 4)
            inner.setVerticalSpacing(3)
            inner.setHorizontalSpacing(8)
            hdr_style = f"color: #8BC34A; font-weight: bold;"
            inner.addWidget(QLabel("Front", styleSheet=hdr_style), 0, 1)
            inner.addWidget(QLabel("Rear",  styleSheet=hdr_style), 0, 2)
            for r, row_data in enumerate(rows, 1):
                lbl_text = row_data[0]
                fw       = row_data[1]
                rw       = row_data[2]
                unit     = row_data[3] if len(row_data) > 3 else ""
                inner.addWidget(QLabel(lbl_text, styleSheet=lbl_s, alignment=Qt.AlignmentFlag.AlignRight), r, 0)
                inner.addWidget(fw, r, 1)
                inner.addWidget(rw, r, 2)
                if unit:
                    inner.addWidget(QLabel(unit, styleSheet="color: #666;"), r, 3)
            inner.setColumnStretch(0, 3)
            inner.setColumnStretch(1, 2)
            inner.setColumnStretch(2, 2)
            inner.setColumnStretch(3, 1)

        # ── Locked banner (shown when event tuning is disabled) ───────────────
        self._setup_locked_banner = QLabel()
        self._setup_locked_banner.setStyleSheet(
            "color: #F5A623; background: #2A1A00; border: 1px solid #F5A623; "
            "border-radius: 4px; padding: 8px; font-size: 12px;"
        )
        self._setup_locked_banner.setWordWrap(True)
        self._setup_locked_banner.hide()
        manual_form.addRow(self._setup_locked_banner)

        # ── Session info ────────────────────────────────────────
        _form_row(manual_form, "", self._lbl_car_specs_info)
        _session_w = QWidget(); _session_h = QHBoxLayout(_session_w); _session_h.setContentsMargins(0, 0, 0, 0)
        _session_h.addWidget(self._setup_type); _session_h.addStretch()
        manual_form.addRow(QLabel("Setup Type:", styleSheet=lbl_s), _session_w)
        _bop_info_w = QWidget(); _bop_ih = QHBoxLayout(_bop_info_w); _bop_ih.setContentsMargins(0, 0, 0, 0)
        _bop_ih.addWidget(self._lbl_bop_info); _bop_ih.addStretch()
        _bop_ih.addWidget(self._btn_bop_edit); _bop_ih.addWidget(self._btn_bop_reload)
        self._bop_info_row_label = QLabel("BOP Data:", styleSheet=lbl_s)
        self._bop_info_row_label.setVisible(False)
        manual_form.addRow(self._bop_info_row_label, _bop_info_w)
        setup_layout.addLayout(manual_form)

        # ── Tyres ─────────────────────────────────────────────────────────────
        tyre_grp = _section("Tyres")
        _fr_grid(tyre_grp, [
            ("Compound", self._setup_tyre_f, self._setup_tyre_r),
        ])
        setup_layout.addWidget(tyre_grp)
        # Tyre compound drives default tagging in Lap Data tab
        self._setup_tyre_f.currentTextChanged.connect(
            lambda name: setattr(self, "_default_lap_compound",
                                 self._TYRE_NAME_TO_CODE.get(name, ""))
        )
        self._setup_tyre_f.currentTextChanged.connect(
            lambda _: self._refresh_live_tyre_label()
        )

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
        setup_layout.addWidget(susp_grp)

        # ── Differential Gear ─────────────────────────────────────────────────
        diff_grp = _section("Differential Gear")
        diff_inner = QFormLayout(diff_grp)
        diff_inner.setContentsMargins(8, 4, 8, 4)
        diff_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _lsd_w = QWidget(); _lsd_h = QHBoxLayout(_lsd_w); _lsd_h.setContentsMargins(0, 0, 0, 0)
        for lbl_txt, spin in (("Initial Torque", self._setup_lsd_i), ("Accel Sensitivity", self._setup_lsd_a), ("Braking Sensitivity", self._setup_lsd_d)):
            _lsd_h.addWidget(QLabel(lbl_txt + ":", styleSheet="color: #888; font-size: 10px;"))
            _lsd_h.addWidget(spin)
        _lsd_h.addStretch()
        diff_inner.addRow(QLabel("LSD (Rear):", styleSheet=lbl_s), _lsd_w)
        _lsd_f_w = QWidget(); _lsd_f_h = QHBoxLayout(_lsd_f_w); _lsd_f_h.setContentsMargins(0, 0, 0, 0)
        for _lt, _sp in (("Initial Torque", self._setup_lsd_f_i),
                         ("Accel Sensitivity", self._setup_lsd_f_a),
                         ("Braking Sensitivity", self._setup_lsd_f_d)):
            _lsd_f_h.addWidget(QLabel(_lt + ":", styleSheet="color: #888; font-size: 10px;"))
            _lsd_f_h.addWidget(_sp)
        _lsd_f_h.addStretch()
        self._lbl_lsd_front = QLabel("LSD (Front):", styleSheet=lbl_s)
        diff_inner.addRow(self._lbl_lsd_front, _lsd_f_w)
        self._lsd_front_widget = _lsd_f_w
        _is_awd = self._setup_drivetrain.currentText() == "AWD"
        self._lbl_lsd_front.setVisible(_is_awd)
        self._lsd_front_widget.setVisible(_is_awd)
        self._setup_drivetrain.currentTextChanged.connect(self._update_lsd_visibility)
        diff_inner.addRow(QLabel("Torque-Vectoring Centre Diff:", styleSheet=lbl_s), self._setup_tvcd)
        diff_inner.addRow(QLabel("Front/Rear Torque Distribution:", styleSheet=lbl_s), self._setup_torque_dist)
        diff_inner.addRow(QLabel("Brake Bias (−5F … +5R):", styleSheet=lbl_s), self._setup_bb)
        setup_layout.addWidget(diff_grp)

        # ── Aerodynamics ──────────────────────────────────────────────────────
        aero_grp = _section("Aerodynamics")
        _fr_grid(aero_grp, [
            ("Downforce (kg)", self._setup_aero_f, self._setup_aero_r),
        ])
        setup_layout.addWidget(aero_grp)

        # ── Performance Adjustment ────────────────────────────────────────────
        perf_grp = _section("Performance Adjustment", "#CCAAFF")
        perf_inner = QFormLayout(perf_grp)
        perf_inner.setContentsMargins(8, 4, 8, 4)
        perf_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _bal_w = QWidget(); _bal_h = QHBoxLayout(_bal_w); _bal_h.setContentsMargins(0, 0, 0, 0)
        _bal_h.addWidget(self._setup_ballast_kg)
        _bal_h.addWidget(QLabel("kg  pos:", styleSheet="color:#888; font-size:10px;"))
        _bal_h.addWidget(self._setup_ballast_pos)
        _bal_h.addStretch()
        perf_inner.addRow(QLabel("Ballast:", styleSheet=lbl_s), _bal_w)
        perf_inner.addRow(QLabel("Power Restrictor (%):", styleSheet=lbl_s), self._setup_power_rest)
        _wt_w = QWidget(); _wt_h = QHBoxLayout(_wt_w); _wt_h.setContentsMargins(0, 0, 0, 0)
        _wt_h.addWidget(self._setup_min_weight)
        _wt_h.addWidget(QLabel("kg  /  max:", styleSheet="color:#888; font-size:10px;"))
        _wt_h.addWidget(self._setup_max_power)
        _wt_h.addWidget(QLabel("hp", styleSheet="color:#888; font-size:10px;"))
        _wt_h.addStretch()
        perf_inner.addRow(QLabel("Min Weight / Max Power:", styleSheet=lbl_s), _wt_w)
        setup_layout.addWidget(perf_grp)

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
        _ecu_out_w = QWidget(); _ecu_out_h = QHBoxLayout(_ecu_out_w); _ecu_out_h.setContentsMargins(0, 0, 0, 0)
        _ecu_out_h.addWidget(self._setup_ecu_output); _ecu_out_h.addStretch()
        ecu_inner.addRow(QLabel("ECU Output Adjustment:", styleSheet=lbl_s), _ecu_out_w)
        setup_layout.addWidget(ecu_grp)

        # ── Transmission ──────────────────────────────────────────────────────
        trans_grp = _section("Transmission", "#FFCC88")
        trans_inner = QFormLayout(trans_grp)
        trans_inner.setContentsMargins(8, 4, 8, 4)
        trans_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        trans_inner.addRow(QLabel("Transmission Type:", styleSheet=lbl_s), self._setup_trans_type)
        setup_layout.addWidget(trans_grp)

        # ── Nitrous / Overtake ────────────────────────────────────────────────
        nitrous_grp = _section("Nitrous / Overtake", "#FF8844")
        nitrous_inner = QFormLayout(nitrous_grp)
        nitrous_inner.setContentsMargins(8, 4, 8, 4)
        nitrous_inner.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        nitrous_inner.addRow(QLabel("Type:", styleSheet=lbl_s), self._setup_nitrous)
        _nos_out_w = QWidget(); _nos_out_h = QHBoxLayout(_nos_out_w); _nos_out_h.setContentsMargins(0, 0, 0, 0)
        _nos_out_h.addWidget(self._setup_nitrous_output); _nos_out_h.addStretch()
        nitrous_inner.addRow(QLabel("Output Adjustment:", styleSheet=lbl_s), _nos_out_w)
        setup_layout.addWidget(nitrous_grp)

        # ── Notes ─────────────────────────────────────────────────────────────
        notes_row = QFormLayout()
        notes_row.addRow(QLabel("Setup Label:", styleSheet=lbl_s), self._setup_label)
        notes_row.addRow(QLabel("Notes:", styleSheet=lbl_s), self._setup_notes)
        setup_layout.addLayout(notes_row)

        # ── Race Engineer Brief ───────────────────────────────────────────────
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
        setup_layout.addLayout(re_brief_row)
        # Visibility controlled by session type — shown for Race, hidden for Qualifying
        self._setup_type.currentTextChanged.connect(self._update_re_brief_visibility)
        self._update_re_brief_visibility(self._setup_type.currentText())
        # Write practice_is_qual ref whenever session type changes
        self._setup_type.currentTextChanged.connect(self._on_setup_type_changed)
        self._on_setup_type_changed(self._setup_type.currentText())

        # Save / Load / Analyse row
        setup_btn_row = QHBoxLayout()
        btn_save_setup   = QPushButton("Save Setup")
        self._setup_load_combo = QComboBox()
        self._setup_load_combo.setMinimumWidth(200)
        btn_load_setup   = QPushButton("Load Selected")
        self._btn_analyse_setup = QPushButton("Analyse & Get Setup Fix")
        self._btn_analyse_setup.setStyleSheet(
            "background: #1F4E78; color: white; font-weight: bold; padding: 6px 12px;")
        self._btn_analyse_setup.setToolTip(
            "Analyse all laps tagged with this setup using AI.\n"
            "If you've described a handling issue below, that's included in the analysis too.")
        self._setup_result_text = QTextEdit()
        self._setup_result_text.setReadOnly(True)
        self._setup_result_text.setMinimumHeight(220)
        self._setup_result_text.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #444;")
        self._setup_result_text.setPlaceholderText(
            "AI setup suggestions will appear here after analysis.")

        btn_save_setup.clicked.connect(self._setup_save)
        btn_load_setup.clicked.connect(self._setup_load_selected)
        self._btn_analyse_setup.clicked.connect(self._setup_analyse_ai)

        self._btn_apply_ai_setup = QPushButton("Apply to Setup")
        self._btn_apply_ai_setup.setStyleSheet(
            "background: #2E6A4A; color: white; font-weight: bold; padding: 6px 12px;")
        self._btn_apply_ai_setup.setToolTip(
            "Apply the AI's recommended changes to the setup form.\n"
            "Changed fields are highlighted until you click Save Setup to persist them.")
        self._btn_apply_ai_setup.setVisible(False)
        self._btn_apply_ai_setup.clicked.connect(self._apply_and_save_ai_setup)
        self._last_setup_ai_fields: dict = {}
        self._highlighted_fields: set = set()

        # ── Driver Feedback Controls ───────────────────────────────────────────
        # Rating combo + Applied checkbox shown below the AI result; values are
        # translated into labels and passed to save_entry when saving to history.
        _feedback_row = QHBoxLayout()
        _feedback_row.setContentsMargins(0, 2, 0, 0)
        _feedback_lbl = QLabel("Rate this result:", styleSheet=f"color: {_TEXT}; font-size: 11px;")
        self._setup_rating_combo = QComboBox()
        self._setup_rating_combo.addItems(["—", "Liked", "Hated", "Neutral"])
        self._setup_rating_combo.setFixedWidth(90)
        self._setup_rating_combo.setStyleSheet(
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; "
            f"border: 1px solid #555; padding: 2px 4px; border-radius: 3px; }}"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )
        self._setup_applied_check = QCheckBox("Applied")
        self._setup_applied_check.setStyleSheet(f"color: {_TEXT}; font-size: 11px;")
        self._setup_applied_check.setToolTip(
            "Tick if you applied this recommendation to the car setup.")
        _feedback_row.addWidget(_feedback_lbl)
        _feedback_row.addWidget(self._setup_rating_combo)
        _feedback_row.addSpacing(8)
        _feedback_row.addWidget(self._setup_applied_check)
        _feedback_row.addStretch()

        setup_btn_row.addWidget(btn_save_setup)
        setup_btn_row.addWidget(QLabel("Load:", styleSheet=lbl_s))
        setup_btn_row.addWidget(self._setup_load_combo)
        setup_btn_row.addWidget(btn_load_setup)
        setup_btn_row.addStretch()
        setup_btn_row.addWidget(self._btn_analyse_setup)
        self._lbl_setup_save_status = QLabel("")
        self._lbl_setup_save_status.setStyleSheet(
            "color: #8BC34A; font-size: 10px; font-style: italic; padding: 2px 0;")

        setup_layout.addLayout(setup_btn_row)
        setup_layout.addWidget(self._lbl_setup_save_status)
        setup_layout.addWidget(self._setup_result_text)
        setup_layout.addWidget(self._btn_apply_ai_setup)
        setup_layout.addLayout(_feedback_row)

        # Build Setup with AI + Set Car Ranges
        _build_row = QHBoxLayout()
        self._btn_build_setup = QPushButton("Build Setup with AI")
        self._btn_build_setup.setStyleSheet(
            "background: #1A5C2A; color: white; font-weight: bold; padding: 6px 16px;")
        self._btn_build_setup.setToolTip(
            "AI generates a complete from-scratch car setup for this car, track, and session.\n"
            "Uses GT7 physics knowledge + your personal driving style profile.\n"
            "Fill in Min Weight and Max Power above first — all fields will be auto-filled.\n"
            "You can adjust any value after the AI fills them.")
        self._btn_build_setup.clicked.connect(self._run_build_setup)
        self._btn_set_car_ranges = QPushButton("Set Car Ranges…")
        self._btn_set_car_ranges.setToolTip(
            "Define per-car min/max bounds for every setup parameter.\n"
            "These bounds constrain the spinboxes and the AI output for this car.")
        self._btn_set_car_ranges.clicked.connect(self._open_car_ranges_dialog)
        _build_row.addWidget(self._btn_build_setup)
        _build_row.addWidget(self._btn_set_car_ranges)
        _build_row.addStretch()
        setup_layout.addLayout(_build_row)

        # Shift RPM — auto-filled by AI Build Setup, used by the live shift beep
        _sb = self._config.get("shift_beep", {})
        shift_rpm_box = QGroupBox("Shift RPM (auto-set by AI Build Setup)")
        shift_rpm_box.setStyleSheet(self._group_style())
        shift_rpm_form = QFormLayout(shift_rpm_box)
        self._spin_shift_rpm_qual = QSpinBox()
        self._spin_shift_rpm_qual.setRange(0, 20000)
        self._spin_shift_rpm_qual.setSingleStep(100)
        self._spin_shift_rpm_qual.setSuffix(" RPM")
        self._spin_shift_rpm_qual.setSpecialValueText("Not set")
        self._spin_shift_rpm_qual.setValue(int(_sb.get("qual_rpm", _sb.get("rpm", 0))))
        self._spin_shift_rpm_qual.setToolTip(
            "Optimal RPM to upshift for qualifying / unrestricted power.\n"
            "Auto-filled when you run 'Build Setup with AI' with session = Qualifying.\n"
            "Edit via the Live tab Shift Beep controls.")
        _set_spin_readonly(self._spin_shift_rpm_qual, True)
        self._spin_shift_rpm_race = QSpinBox()
        self._spin_shift_rpm_race.setRange(0, 20000)
        self._spin_shift_rpm_race.setSingleStep(100)
        self._spin_shift_rpm_race.setSuffix(" RPM")
        self._spin_shift_rpm_race.setSpecialValueText("Not set")
        self._spin_shift_rpm_race.setValue(int(_sb.get("race_rpm", _sb.get("rpm", 0))))
        self._spin_shift_rpm_race.setToolTip(
            "Optimal RPM to upshift during the race (may be lower if ECU/power restrictor is applied).\n"
            "Auto-filled when you run 'Build Setup with AI' with session = Race.\n"
            "Edit via the Live tab Shift Beep controls.")
        _set_spin_readonly(self._spin_shift_rpm_race, True)
        shift_rpm_form.addRow("Qualifying:", self._spin_shift_rpm_qual)
        shift_rpm_form.addRow("Race:", self._spin_shift_rpm_race)
        setup_layout.addWidget(shift_rpm_box)

        self._build_setup_result = QTextEdit()
        self._build_setup_result.setReadOnly(True)
        self._build_setup_result.setMinimumHeight(320)
        self._build_setup_result.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #444; "
            f"border-left: 3px solid #3A8C4A;")
        self._build_setup_result.setVisible(False)
        setup_layout.addWidget(self._build_setup_result)

        # Optional driver feeling — combined with telemetry by the merged analyse button above
        feeling_label = QLabel("Handling notes:", styleSheet=lbl_s)
        self._setup_feeling_input = QTextEdit()
        self._setup_feeling_input.setMaximumHeight(70)
        self._setup_feeling_input.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #555;")
        self._setup_feeling_input.setPlaceholderText(
            "Optional: describe any handling issues to include in the AI analysis above.\n"
            "e.g.  \"rear is loose on acceleration\"  |  \"locks on braking at T6\"  |  "
            "\"front pushes in fast corners\"")
        feeling_row = QHBoxLayout()
        feeling_row.addWidget(feeling_label)
        feeling_row.addWidget(self._setup_feeling_input)
        setup_layout.addLayout(feeling_row)
        self._refresh_setup_combo()
        return setup_box

    def _current_setup_dict(self) -> dict:
        """Read all manual fields including editable gear ratios."""
        gear_ratios = [s.value() for s in self._gear_ratio_spins if s.value() > 0.0]
        return {
            "name":      self._config.get("strategy", {}).get("car", "Unknown Car") or "Unknown Car",
            "car":       self._config.get("strategy", {}).get("car", "Unknown Car") or "Unknown Car",
            "setup_label": self._setup_label.text().strip() or "Setup 1",
            "track":     self._config.get("strategy", {}).get("track", ""),
            "condition": {
                "Fixed Dry": "Dry", "Dry": "Dry", "Random Weather": "Dry",
                "Fixed Wet": "Wet", "Wet": "Wet", "Heavy Rain": "Wet",
                "Light Rain": "Damp", "Wet Risk": "Damp", "Damp": "Damp",
            }.get(self._config.get("strategy", {}).get("weather", ""), "Dry"),
            "setup_type": self._setup_type.currentText(),
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
            "lsd_front_initial": self._setup_lsd_f_i.value() if self._setup_drivetrain.currentText() == "AWD" else 0,
            "lsd_front_accel":   self._setup_lsd_f_a.value() if self._setup_drivetrain.currentText() == "AWD" else 0,
            "lsd_front_decel":   self._setup_lsd_f_d.value() if self._setup_drivetrain.currentText() == "AWD" else 0,
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
            "bop_race":       bool(self._config.get("strategy", {}).get("bop", False)),
            "gear_ratios":    gear_ratios,
            "final_drive":    self._spin_final_drive.value(),
            "transmission_max_speed_kmh": int(self._spin_top_speed.value()),
            "captured_at":    time.strftime("%Y-%m-%d %H:%M"),
        }

    def _fill_setup_fields(self, d: dict) -> None:
        car = d.get("name", "")
        if car:
            self._autofill_car_specs(car)
        # Re-bound spinbox ranges for this car BEFORE setting values, so per-car
        # range overrides take effect and values are not silently truncated.
        # NOTE: _rebound_setup_spinboxes must NOT trigger an AI/build call.
        self._rebound_setup_spinboxes(car or None)
        _st_map = {"Race": "Race Setup", "Qualifying": "Qualifying Setup", "Practice": "Race Setup"}
        _st_raw = d.get("setup_type", _st_map.get(d.get("session", ""), "Race Setup"))
        idx = self._setup_type.findText(_st_raw)
        if idx >= 0:
            self._setup_type.setCurrentIndex(idx)
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
        if _tvcd_idx >= 0: self._setup_tvcd.setCurrentIndex(_tvcd_idx)
        self._setup_torque_dist.setValue(int(d.get("torque_distribution_rear", 50)))
        self._setup_bb.setValue(int(d.get("brake_bias_front", 0)))
        self._setup_ballast_kg.setValue(float(d.get("ballast_kg", 0.0)))
        self._setup_ballast_pos.setValue(int(d.get("ballast_position", 0)))
        self._setup_power_rest.setValue(float(d.get("power_restrictor", 100.0)))
        from data.tyres import normalise_name as _nn
        _tf = _nn(d.get("tyre_front", "Racing Medium")) or "Racing Medium"
        _tf_idx = self._setup_tyre_f.findText(_tf)
        if _tf_idx >= 0: self._setup_tyre_f.setCurrentIndex(_tf_idx)
        _tr = _nn(d.get("tyre_rear", "Racing Medium")) or "Racing Medium"
        _tr_idx = self._setup_tyre_r.findText(_tr)
        if _tr_idx >= 0: self._setup_tyre_r.setCurrentIndex(_tr_idx)
        _ecu_idx = self._setup_ecu.findText(d.get("ecu_ingame", "Stock"))
        if _ecu_idx >= 0: self._setup_ecu.setCurrentIndex(_ecu_idx)
        self._setup_ecu_output.setValue(float(d.get("ecu_ingame_output", 100.0)))
        _tt_idx = self._setup_trans_type.findText(d.get("transmission_type", "Stock"))
        if _tt_idx >= 0: self._setup_trans_type.setCurrentIndex(_tt_idx)
        _nos_idx = self._setup_nitrous.findText(d.get("nitrous_type", "None"))
        if _nos_idx >= 0: self._setup_nitrous.setCurrentIndex(_nos_idx)
        self._setup_nitrous_output.setValue(float(d.get("nitrous_output", 0.0)))
        self._setup_label.setText(d.get("setup_label", "Setup 1"))
        self._setup_notes.setText(d.get("notes", ""))
        ecu = d.get("ecu_recommendation", "")
        self._lbl_ecu_rec.setText(ecu if ecu and ecu != "—" else "—")
        saved_ratios = d.get("gear_ratios", [])
        for i, spin in enumerate(self._gear_ratio_spins):
            spin.setValue(float(saved_ratios[i]) if i < len(saved_ratios) else 0.0)
        self._gear_ratios_captured = any(r > 0.0 for r in saved_ratios)
        self._spin_final_drive.setValue(float(d.get("final_drive", 0.0)))
        self._spin_top_speed.setValue(float(d.get("transmission_max_speed_kmh", 0)))

    def _load_car_specs_for_current(self) -> tuple[str, dict]:
        """Return (car_name, specs_dict) for the currently selected car in the Setup tab."""
        car_name = self._config.get("strategy", {}).get("car", "")
        if not car_name:
            return "", {}
        from pathlib import Path
        specs_path = Path(__file__).parent.parent / "data" / "car_specs.json"
        try:
            all_specs: dict = json.loads(specs_path.read_text(encoding="utf-8"))
            return car_name, all_specs.get(car_name, {})
        except Exception:
            return car_name, {}

    def _apply_setup_permissions(
        self,
        bop: bool,
        tuning_allowed: bool,
        allowed_cats: list[str],
    ) -> None:
        if not hasattr(self, "_setup_locked_banner"):
            return
        fully_locked = not tuning_allowed
        partially_restricted = tuning_allowed and bool(allowed_cats)
        if fully_locked:
            if bop:
                msg = ("Setup Builder is locked — BoP is enabled and tuning is not allowed for this Event.\n"
                       "You can view the car and event context but cannot edit or generate a setup.")
            else:
                msg = ("Setup Builder is locked — this Event has tuning disabled.\n"
                       "You can view the car and event context but cannot edit or generate a setup.")
            self._setup_locked_banner.setText(msg)
            self._setup_locked_banner.show()
        else:
            self._setup_locked_banner.hide()
        for cat, attrs in self._SETUP_TUNING_GROUPS.items():
            enabled = not fully_locked and (not partially_restricted or cat in allowed_cats)
            for attr in attrs:
                w = getattr(self, attr, None)
                if w is not None:
                    w.setEnabled(enabled)
            if cat == "transmission":
                for gs in getattr(self, "_gear_ratio_spins", []):
                    gs.setEnabled(enabled and not bop)
        # Tyre compound selection is NEVER locked by BoP in GT7 — BoP only locks
        # mechanical tuning. Always re-enable tyre widgets regardless of permissions.
        for attr in ("_setup_tyre_f", "_setup_tyre_r"):
            w = getattr(self, attr, None)
            if w is not None:
                w.setEnabled(True)
        for attr in ("_setup_label", "_setup_notes"):
            w = getattr(self, attr, None)
            if w:
                w.setEnabled(True)

    def _refresh_setup_combo(self, select_index: int = -1) -> None:
        if not hasattr(self, "_setup_load_combo"):
            return
        self._setup_load_combo.blockSignals(True)
        self._setup_load_combo.clear()
        self._setup_load_combo.addItem("— select to load —")   # placeholder at index 0
        for s in self._saved_setups:
            setup_lbl = s.get("setup_label") or "Setup"
            car_name  = s.get("name", "Unnamed")
            label = f"{setup_lbl} ({car_name}) — {s.get('track', '')} [{s.get('session', '')}]"
            self._setup_load_combo.addItem(label)
        # select_index is relative to _saved_setups; shift by 1 for the placeholder
        if 0 <= select_index < len(self._saved_setups):
            self._setup_load_combo.setCurrentIndex(select_index + 1)
        else:
            self._setup_load_combo.setCurrentIndex(0)   # show placeholder
        self._setup_load_combo.blockSignals(False)

    def _setup_type_prefix(self) -> str:
        """'Q' for a qualifying setup, 'R' for a race setup, from the type combo."""
        return "Q" if "qual" in self._setup_type.currentText().lower() else "R"

    def _generate_setup_name(self) -> str | None:
        """Build '<Q|R> <event name> <number>' for the active event, or None if no event."""
        from ui.setup_name_helper import build_setup_name, next_setup_number
        event_name = ""
        if hasattr(self, "_active_event"):
            event_name = (self._active_event() or {}).get("name", "") or ""
        if not event_name:
            return None
        prefix = self._setup_type_prefix()
        n = next_setup_number(self._saved_setups, prefix, event_name)
        return build_setup_name(prefix, event_name, n)

    def _prefill_setup_label(self) -> None:
        """Pre-fill the editable setup-label field with the auto-generated name.

        Fires when the setup type or active event changes. No-op when there is no
        active event (the user can still type a name; the save guard handles it).
        """
        name = self._generate_setup_name()
        if name:
            self._setup_label.setText(name)

    def _setup_save(self) -> None:
        # Require an active event so setups are always named/grouped by event.
        _evt_name = ""
        if hasattr(self, "_active_event"):
            _evt_name = (self._active_event() or {}).get("name", "") or ""
        if not _evt_name:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "No Active Event",
                "Please select an active event in the Event Planner before saving a setup.",
            )
            return
        # D-RESAVE: resolve the final label before persisting. A structured auto-name
        # (or empty field) advances to the next numbered attempt for this event, so
        # saving a loaded/previously-saved structured setup creates a NEW number
        # instead of overwriting. Manual/freeform names are kept exactly as typed.
        from ui.setup_name_helper import resolve_save_name
        self._setup_label.setText(
            resolve_save_name(
                self._setup_label.text(),
                self._setup_type_prefix(),
                _evt_name,
                self._saved_setups,
            )
        )
        # Clear any field highlights from AI apply — user has chosen to persist.
        self._clear_setup_highlights()
        # Persist race engineer brief to active event before saving setup
        self._save_re_brief_to_active_event()
        d = self._current_setup_dict()
        ca = self._config.setdefault("car_setup", {})
        existing = next(
            (i for i, s in enumerate(self._saved_setups)
             if s.get("name") == d["name"] and s.get("setup_label") == d["setup_label"]),
            None,
        )
        if existing is not None:
            d["setup_id"] = self._saved_setups[existing].get("setup_id") or d.get("setup_id")
            self._saved_setups[existing] = d
            target_idx = existing
        else:
            if not d.get("setup_id"):
                next_id = ca.get("next_setup_id", 1)
                d["setup_id"] = next_id
                ca["next_setup_id"] = next_id + 1
            self._saved_setups.append(d)
            target_idx = len(self._saved_setups) - 1

        # Write to DB (authoritative store for setups)
        if self._db is not None:
            _meta_keys = {"name", "setup_label", "setup_id", "captured_at", "ai_notes"}
            _car_name = d.get("name", "")
            _car_id = self._db.get_car_id(_car_name) if _car_name else 0
            _event_id = int(self._config.get("strategy", {}).get("event_id", 0))
            _label = d.get("setup_label", "Setup")
            _fields = {k: v for k, v in d.items() if k not in _meta_keys}
            _existing_db_id = d.get("setup_id") if existing is not None else 0
            if _existing_db_id:
                self._db.update_setup(_existing_db_id, _label, _fields)
            else:
                _new_id = self._db.save_setup(_car_id, _event_id, _label, _fields)
                d["setup_id"] = _new_id
                self._saved_setups[target_idx]["setup_id"] = _new_id

        # Keep config in sync during transition period
        ca["setups"] = self._saved_setups
        self._persist_config()
        self._refresh_setup_combo(select_index=target_idx)
        self._refresh_all_setup_combos()
        self._bridge.event_log_entry.emit(f"[Setup] saved: {d['name']} (ID {d.get('setup_id', '?')})")
        if hasattr(self, "_lbl_setup_save_status"):
            lbl = d.get("setup_label", "") or "Setup"
            self._lbl_setup_save_status.setText(f"Saved: {lbl}  (ID {d.get('setup_id', '?')})")
            from PyQt6.QtCore import QTimer as _QTimer
            _QTimer.singleShot(4000, lambda: (
                self._lbl_setup_save_status.setText("") if hasattr(self, "_lbl_setup_save_status") else None
            ))

    def _setup_load_selected(self) -> None:
        idx = self._setup_load_combo.currentIndex()
        # index 0 is the placeholder; real setups start at index 1
        real_idx = idx - 1
        if 0 <= real_idx < len(self._saved_setups):
            self._fill_setup_fields(self._saved_setups[real_idx])

    def _setup_analyse_ai(self) -> None:
        if self._driving_advisor is None:
            self._setup_result_text.setPlainText(
                "Driving advisor not available.")
            return
        d = self._current_setup_dict()
        _car_name, _car_specs = self._load_car_specs_for_current()

        # Count laps tagged with this setup in the lap table so the AI
        # sees all relevant laps (not just the last 5).
        setup_id = d.get("setup_id")
        n_laps = 5  # fallback if no setup ID or no tagged laps
        if setup_id:
            count = sum(
                1 for r in range(self._lap_table.rowCount())
                if (w := self._lap_table.cellWidget(r, 14)) is not None
                and w.currentText().startswith(f"{setup_id} —")
            )
            if count > 0:
                n_laps = count

        feeling = self._setup_feeling_input.toPlainText().strip()
        self._setup_result_text.setPlainText("Analysing setup… please wait.")
        if hasattr(self, "_btn_analyse_setup"):
            self._btn_analyse_setup.setEnabled(False)
        import threading as _threading

        _sc = self._config.get("strategy", {})
        _allowed  = _sc.get("allowed_tuning_categories", []) or None
        _locked   = not bool(_sc.get("tuning", True))
        _compound = _sc.get("mandatory_compounds", "") or ""

        def _worker():
            try:
                resp = self._driving_advisor.build_combined_setup_response(
                    d, n_laps=n_laps, car_name=_car_name, car_specs=_car_specs,
                    feeling=feeling or None,
                    allowed_tuning=_allowed, tuning_locked=_locked,
                    compound=_compound)
                self._setup_result_queue.put(("ok", resp, "analyse_setup", feeling or None))
            except Exception as exc:
                self._setup_result_queue.put(("error", str(exc), "analyse_setup", None))

        _threading.Thread(target=_worker, daemon=True).start()

    def _display_setup_result(self, result: tuple) -> None:
        if not hasattr(self, "_setup_result_text"):
            return
        status = result[0]
        payload = result[1]
        entry_type = result[2] if len(result) > 2 else "analyse_setup"
        feeling = result[3] if len(result) > 3 else None

        if hasattr(self, "_btn_analyse_setup"):
            self._btn_analyse_setup.setEnabled(True)

        if status == "error":
            self._setup_result_text.setHtml(
                f"<span style='color:#F55;'>Analysis failed:</span> {payload}")
            return

        # DEF-P2-007 — validate AI response for event tuning compliance before display
        from strategy.ai_planner import validate_ai_setup_response as _vld_setup
        _sc_v = self._config.get("strategy", {})
        _viol_cats = _vld_setup(
            payload if isinstance(payload, str) else "",
            not bool(_sc_v.get("tuning", True)),
            _sc_v.get("allowed_tuning_categories", []) or None,
        )
        _violation_banner = ""
        if _viol_cats:
            _vc = ", ".join(_viol_cats)
            _violation_banner = (
                "<div style='background:#2A1A00; border:1px solid #F5A623; "
                "border-radius:4px; padding:8px; margin-bottom:8px; color:#F5A623;'>"
                f"&#9888; <b>Event Restriction Warning</b> — AI response may recommend "
                f"changes to locked areas: <b>{_vc}</b>. Review before applying.</div>"
            )

        # Snapshot driver feedback controls before resetting them.
        # The user may have rated the PREVIOUS result; capture that rating so it
        # can be saved with the previous entry's history record, then reset so the
        # new result starts fresh.
        _prev_rating_text = ""
        _prev_hist_labels: list[str] = []
        if hasattr(self, "_setup_rating_combo"):
            _prev_rating_text = self._setup_rating_combo.currentText()
            if _prev_rating_text == "Liked":
                _prev_hist_labels.append("liked")
            elif _prev_rating_text == "Hated":
                _prev_hist_labels.append("hated")
            elif _prev_rating_text == "Neutral":
                _prev_hist_labels.append("neutral")
        if hasattr(self, "_setup_applied_check"):
            if self._setup_applied_check.isChecked():
                _prev_hist_labels.append("applied")
            else:
                _prev_hist_labels.append("not_applied")

        # Reset controls for the incoming fresh result
        if hasattr(self, "_setup_rating_combo"):
            self._setup_rating_combo.setCurrentIndex(0)
        if hasattr(self, "_setup_applied_check"):
            self._setup_applied_check.setChecked(False)

        # Try to parse structured JSON from the advisor
        try:
            data = json.loads(payload)
            analysis = str(data.get("analysis", ""))
            changes: list = data.get("changes", [])
            setup_fields: dict = data.get("setup_fields", {})
            _validation_errors: list = data.get("validation_errors", [])
            _eng_validation_failed: bool = bool(data.get("engineering_validation_failed", False))
            _eng_validation_errors: list = data.get("engineering_validation_errors", [])
            _diagnosis: dict = data.get("diagnosis") or {}
        except (_json.JSONDecodeError, AttributeError):
            # Fallback: display raw text, no changes section
            if _violation_banner:
                self._setup_result_text.setHtml(
                    _violation_banner
                    + f"<pre style='color:#E0E0E0; white-space:pre-wrap;'>{payload}</pre>")
            else:
                self._setup_result_text.setPlainText(payload)
            if hasattr(self, "_btn_apply_ai_setup"):
                self._btn_apply_ai_setup.setVisible(False)
            return

        # Build an engineering-validation-failed banner (distinct, red) when the
        # AI retry did not resolve the engineering contradiction.
        _eng_banner = ""
        if _eng_validation_failed:
            _eng_banner = _format_engineering_validation_banner(_eng_validation_errors)

        # Build a validation-errors banner when the server-side validator flagged issues.
        _validation_banner = _format_validation_errors_banner(_validation_errors)

        # Build a compact diagnosis summary when the backend diagnosis is present.
        _diagnosis_html = ""
        if _diagnosis:
            _dom   = _diagnosis.get("dominant_problem") or "—"
            _btm   = _diagnosis.get("bottoming_band") or "—"
            _ws    = _diagnosis.get("wheelspin_band") or "—"
            _gbx   = _diagnosis.get("gearbox_flag") or "none"
            _conf  = _diagnosis.get("location_confidence") or "—"
            _diagnosis_html = (
                "<div style='background:#1A2A1A; border:1px solid #3A5A3A; "
                "border-radius:4px; padding:6px 10px; margin-bottom:6px; "
                "color:#88BB88; font-size:11px;'>"
                "<b style='color:#8BC34A;'>App diagnosis:</b>&nbsp;"
                f"<b>{_dom}</b>"
                f" &nbsp;|&nbsp; bottoming: {_btm}"
                f" &nbsp;|&nbsp; wheelspin: {_ws}"
                f" &nbsp;|&nbsp; gearbox: {_gbx}"
                f" &nbsp;|&nbsp; track-model confidence: {_conf}"
                "</div>"
            )

        # Store parsed fields so the apply button can use them
        self._last_setup_ai_fields = {
            k: v for k, v in setup_fields.items()
            if isinstance(v, (int, float))
        }
        if hasattr(self, "_btn_apply_ai_setup"):
            self._btn_apply_ai_setup.setVisible(bool(self._last_setup_ai_fields))

        # Build HTML: engineering banner (highest priority) + diagnosis + event
        # restriction banner + validation warnings + analysis block + changes
        card = "background:#1C2A3A; border-radius:6px; padding:10px; margin-bottom:8px;"
        chg_hdr = "background:#2A3A1C; border-left:4px solid #8BC34A; border-radius:4px; " \
                  "padding:8px 12px; margin-bottom:4px;"
        chg_row = "padding:4px 0 4px 8px; border-bottom:1px solid #2A3A1C;"

        html = (
            _eng_banner
            + _diagnosis_html
            + _violation_banner
            + _validation_banner
            + f"<div style='{card}'><p style='margin:0;line-height:1.5;'>{analysis}</p></div>"
        )

        if changes:
            html += f"<div style='{chg_hdr}'>" \
                    "<b style='color:#8BC34A;'>&#9745; CHANGES TO MAKE IN CAR SETUP</b></div>"
            for ch in changes:
                s       = ch.get("setting", "?")
                frm     = ch.get("from", "?")
                to_raw  = ch.get("to", "?")
                # Backend supplies to_clamped (value already within the car's allowed range).
                # Falls back to raw to when field is None or to is non-numeric.
                _clamped_val = ch.get("to_clamped", to_raw)
                why     = ch.get("why", "")
                # Prefer the clamped value when the param field was resolved by the backend.
                # field is None when the backend could not identify the param — show raw value.
                _field = ch.get("field")
                _clamp_note = ""
                if _field is not None:
                    # Field resolved — display the clamped value, never the raw out-of-range one.
                    to_display = _clamped_val
                    # Annotate only when clamped differs from raw (numeric guard).
                    try:
                        if abs(float(_clamped_val) - float(to_raw)) > 1e-9:
                            _clamp_note = f" (clamped to {_clamped_val})"
                    except (TypeError, ValueError):
                        pass  # non-numeric (e.g. tyre name) — no annotation needed
                else:
                    # Field unresolvable — acceptable degradation: show raw value as-is.
                    to_display = to_raw
                html += (
                    f"<div style='{chg_row}'>"
                    f"<b style='color:#E0E0E0;'>{s}</b>&nbsp;&nbsp;"
                    f"<span style='color:#F5A623;'>{frm}</span>"
                    f"&nbsp;&#8594;&nbsp;"
                    f"<span style='color:#8BC34A;'>{to_display}</span>"
                    + (f"<span style='color:#AAA; font-size:10px;'>{_clamp_note}</span>" if _clamp_note else "")
                    + (f"<br><span style='color:#888;font-size:11px;'>&nbsp;&nbsp;&nbsp;{why}</span>" if why else "")
                    + "</div>"
                )

        self._setup_result_text.setHtml(html)

        # Save to history
        config_id = self._config.get("strategy", {}).get("config_id", "")
        car  = self._config.get("strategy", {}).get("car", "")
        track = self._config.get("strategy", {}).get("track", "")
        if config_id:
            try:
                from data.setup_history import save_entry
                # Use the labels snapshot captured from the controls before they
                # were reset.  These reflect what the user rated on the PREVIOUS
                # result (or the first-ever run defaults if this is the first result).
                # driver_feedback: prefer the feeling text; fall back to rating word.
                _hist_feedback = feeling or _prev_rating_text or ""
                save_entry(config_id, car, track, {
                    "type": entry_type,
                    "feeling": feeling or "",
                    "analysis": analysis,
                    "changes": changes,
                }, labels=_prev_hist_labels if _prev_hist_labels else None,
                   driver_feedback=_hist_feedback)
            except Exception as _e:
                print(f"[SetupHistory] save failed: {_e}")

    def _apply_and_save_ai_setup(self) -> None:
        """Apply AI-recommended setup_fields to the form and save as a new entry."""
        if not getattr(self, "_last_setup_ai_fields", {}):
            return
        current = self._current_setup_dict()
        current.update(self._last_setup_ai_fields)
        self._fill_setup_fields(current)
        car = self._config.get("strategy", {}).get("car", "") or "Unknown"
        ai_count = sum(
            1 for s in self._saved_setups
            if s.get("name") == car and str(s.get("setup_label", "")).startswith("AI Fix")
        )
        self._setup_label.setText(f"AI Fix {ai_count + 1}")
        # Highlight changed fields so the user can see what was modified.
        # The save is intentionally deferred — click Save Setup to persist.
        self._highlight_changed_fields(list(self._last_setup_ai_fields.keys()))
        # Link recommendation to this session
        _car_id_apply = getattr(self, "_car_id_build", 0)
        _track_apply = self._config.get("strategy", {}).get("track", "")
        _sid_apply = (
            int(self._dispatcher._session_id)
            if hasattr(self, "_dispatcher") and self._dispatcher is not None
            else 0
        )
        if self._db and _car_id_apply > 0 and _track_apply and _sid_apply > 0:
            try:
                self._db.apply_recommendation_for_car_track(
                    _car_id_apply, _track_apply, _sid_apply
                )
            except Exception as _are:
                print(f"[SetupHistory] apply_recommendation failed: {_are}")
        if hasattr(self, "_btn_apply_ai_setup"):
            self._btn_apply_ai_setup.setVisible(False)
        self._last_setup_ai_fields = {}

    def _run_build_setup(self) -> None:
        """Ask AI to generate a complete from-scratch car setup and auto-fill all fields."""
        import threading as _threading
        from strategy.ai_planner import build_car_setup

        api_key = self._ai_api_key.text().strip()
        if not api_key:
            self._build_setup_result.setPlainText("No API key configured. Add your Anthropic API key in the AI Race Analysis section.")
            self._build_setup_result.setVisible(True)
            return

        car          = self._config.get("strategy", {}).get("car", "") or "Unknown"
        track        = self._config.get("strategy", {}).get("track", "")
        session_type = self._setup_type.currentText()
        race_laps    = self._config.get("strategy", {}).get("total_laps", 25)
        min_weight   = self._setup_min_weight.value()
        max_power    = self._setup_max_power.value()
        actual_bhp   = self._setup_actual_bhp.value() if hasattr(self, "_setup_actual_bhp") else 0.0
        num_gears    = self._setup_num_gears.value() if hasattr(self, "_setup_num_gears") else 0
        drivetrain   = self._setup_drivetrain.currentData() if hasattr(self, "_setup_drivetrain") else ""
        bop_data     = self._get_bop_data_for_car()
        # Hybrid event fields for build_car_setup
        _sc_ev = self._config.get("strategy", {})
        _duration_mins   = int(_sc_ev.get("race_duration_minutes", 0))
        _mandatory_stops = int(_sc_ev.get("mandatory_stops", 0))
        _refuel_rate_lps = float(_sc_ev.get("refuel_speed_lps", 0.0))
        _pit_loss_secs   = float(_sc_ev.get("pit_loss_secs", 0.0))
        _re_brief        = self._re_brief_input.toPlainText().strip() if hasattr(self, "_re_brief_input") else ""
        _, _car_specs = self._load_car_specs_for_current()
        _sc_build = self._config.get("strategy", {})
        _allowed_tuning = _sc_build.get("allowed_tuning_categories", []) or None
        _tuning_locked  = not bool(_sc_build.get("tuning", True))
        _tyre_wear_mult  = float(_sc_build.get("tyre_wear_multiplier", 1.0))
        _fuel_mult       = float(_sc_build.get("fuel_multiplier", 1.0))
        _avail_tyres     = _sc_build.get("avail_tyres", []) or []
        _req_tyres       = _sc_build.get("required_tyres", []) or []
        _race_type_build = _sc_build.get("race_type", "lap")
        _track_loc_id    = _sc_build.get("track_location_id", "")
        _layout_id_build = _sc_build.get("layout_id", "")
        _last_lap = self._recorder.last_lap() if self._recorder else None
        _gearbox_analysis = _last_lap.gearbox_analysis if _last_lap else {}
        _car_id_build = self._db.get_car_id(car) if self._db and car and car != "Unknown" else 0
        self._car_id_build = _car_id_build

        self._btn_build_setup.setEnabled(False)
        self._btn_build_setup.setText("Building…")
        self._build_setup_result.setPlainText("Asking AI for complete car setup — this takes 20–30 seconds…")
        self._build_setup_result.setVisible(True)

        _session_id_build = (
            int(self._dispatcher._session_id)
            if hasattr(self, "_dispatcher") and self._dispatcher is not None
            else 0
        )

        def _worker():
            try:
                # Auto-fetch setup history for this car+track
                _setup_history_str = ""
                _setup_comparison_str = ""
                if self._db and _car_id_build > 0 and track:
                    try:
                        _setup_history_str = self._db.get_setup_history_for_car_track(
                            _car_id_build, track, limit=10
                        )
                    except Exception as _she:
                        print(f"[SetupHistory] history fetch failed: {_she}")
                    try:
                        _setup_comparison_str = self._build_setup_comparison_text(track)
                    except Exception as _sce:
                        print(f"[SetupHistory] comparison fetch failed: {_sce}")
                rec = build_car_setup(car, track, session_type, race_laps,
                                      min_weight, max_power, api_key,
                                      bop_data=bop_data,
                                      actual_bhp=actual_bhp, num_gears=num_gears,
                                      drivetrain=drivetrain,
                                      car_specs=_car_specs,
                                      allowed_tuning=_allowed_tuning,
                                      tuning_locked=_tuning_locked,
                                      gearbox_analysis=_gearbox_analysis or None,
                                      tyre_wear_multiplier=_tyre_wear_mult,
                                      fuel_multiplier=_fuel_mult,
                                      avail_tyres=_avail_tyres or None,
                                      req_tyres=_req_tyres or None,
                                      race_type=_race_type_build,
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=_car_id_build,
                                      track_location_id=_track_loc_id,
                                      layout_id=_layout_id_build,
                                      session_id=_session_id_build,
                                      setup_history=_setup_history_str,
                                      setup_comparison=_setup_comparison_str,
                                      duration_mins=_duration_mins,
                                      mandatory_stops=_mandatory_stops,
                                      refuel_rate_lps=_refuel_rate_lps,
                                      pit_loss_secs=_pit_loss_secs,
                                      race_engineer_brief=_re_brief)
                from strategy._rec_parser import parse_recommendations_from_response as _parse_recs
                try:
                    _ai_id_build = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id_build = None
                _build_track = self._config.get("strategy", {}).get("track", "")
                _build_layout = self._config.get("strategy", {}).get("layout_id", "")
                _recs_build = _parse_recs(
                    getattr(rec, "raw_response", ""),
                    "Build Car Setup",
                    _car_id_build,
                    _build_track,
                    layout_id=_build_layout,
                    session_id=_session_id_build,
                    ai_interaction_id=_ai_id_build,
                )
                if _recs_build:
                    self._db.insert_setup_recommendations(_recs_build)
                    # Wire corner issue IDs to the saved recommendations
                    if hasattr(self, '_db') and self._db is not None:
                        try:
                            issues = self._db.get_corner_issues(
                                _car_id_build,
                                _build_track,
                            )
                            issue_ids = [r["id"] for r in (issues or [])]
                            rec_ids = self._db.get_last_recommendation_ids(
                                _car_id_build, _build_track, len(_recs_build)
                            )
                            for rec_id in rec_ids:
                                self._db.set_recommendation_corner_issues(rec_id, issue_ids)
                        except Exception:
                            pass  # non-critical: traceability is best-effort
                self._build_setup_queue.put(("ok", rec, session_type))
            except Exception as exc:
                self._build_setup_queue.put(("err", str(exc), session_type))

        _threading.Thread(target=_worker, daemon=True).start()

    def _display_build_setup_result(self, result: tuple) -> None:
        self._btn_build_setup.setEnabled(True)
        self._btn_build_setup.setText("Build Setup with AI")
        status, payload, *rest = result
        session_type = rest[0] if rest else "Race"
        if status == "err":
            self._build_setup_result.setPlainText(f"Build Setup failed: {payload}")
            return
        self._apply_build_setup_result(payload, session_type)

    def _apply_build_setup_result(self, rec, session_type: str = "Race") -> None:
        """Fill all Car Setup form fields from an AI CarSetupRecommendation."""
        # Re-bound spinboxes with per-car ranges before setting values
        _car_name = self._config.get("strategy", {}).get("car", "") or ""
        _ranges = resolve_ranges(_car_name)

        def _set_int(spin, param, val):
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            spin.setRange(int(lo), int(hi))
            _set_spin_readonly(spin, lo >= hi)
            spin.setValue(max(int(lo), min(int(hi), int(round(val)))))

        def _set_dbl(spin, param, val):
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            spin.setRange(float(lo), float(hi))
            _set_spin_readonly(spin, lo >= hi)
            spin.setValue(max(float(lo), min(float(hi), float(val))))

        _set_int(self._setup_rh_f,       "ride_height_front",  rec.ride_height_front)
        _set_int(self._setup_rh_r,       "ride_height_rear",   rec.ride_height_rear)
        _set_dbl(self._setup_spr_f,      "springs_front",      rec.springs_front)
        _set_dbl(self._setup_spr_r,      "springs_rear",       rec.springs_rear)
        _set_int(self._setup_dmp_f_comp, "dampers_front_comp", rec.dampers_front_comp)
        _set_int(self._setup_dmp_f_ext,  "dampers_front_ext",  rec.dampers_front_ext)
        _set_int(self._setup_dmp_r_comp, "dampers_rear_comp",  rec.dampers_rear_comp)
        _set_int(self._setup_dmp_r_ext,  "dampers_rear_ext",   rec.dampers_rear_ext)
        _set_int(self._setup_arb_f,      "arb_front",          rec.arb_front)
        _set_int(self._setup_arb_r,      "arb_rear",           rec.arb_rear)
        _set_dbl(self._setup_cam_f,      "camber_front",       rec.camber_front)
        _set_dbl(self._setup_cam_r,      "camber_rear",        rec.camber_rear)
        _set_dbl(self._setup_toe_f,      "toe_front",          rec.toe_front)
        _set_dbl(self._setup_toe_r,      "toe_rear",           rec.toe_rear)
        _set_int(self._setup_aero_f,     "aero_front",         rec.aero_front)
        _set_int(self._setup_aero_r,     "aero_rear",          rec.aero_rear)
        _set_int(self._setup_lsd_i,      "lsd_initial",        rec.lsd_initial)
        _set_int(self._setup_lsd_a,      "lsd_accel",          rec.lsd_accel)
        _set_int(self._setup_lsd_d,      "lsd_decel",          rec.lsd_decel)
        _set_int(self._setup_lsd_f_i,    "lsd_front_initial",  rec.lsd_front_initial)
        _set_int(self._setup_lsd_f_a,    "lsd_front_accel",    rec.lsd_front_accel)
        _set_int(self._setup_lsd_f_d,    "lsd_front_decel",    rec.lsd_front_decel)
        _set_int(self._setup_bb,         "brake_bias",         rec.brake_bias)
        _set_dbl(self._setup_ballast_kg, "ballast_kg",         rec.ballast_kg)
        _set_int(self._setup_ballast_pos,"ballast_position",   rec.ballast_position)
        _set_dbl(self._setup_power_rest, "power_restrictor",   rec.power_restrictor)
        if hasattr(rec, "ecu_recommendation") and rec.ecu_recommendation:
            self._lbl_ecu_rec.setText(rec.ecu_recommendation)
        else:
            self._lbl_ecu_rec.setText("—")
        if rec.final_drive > 0.0:
            self._spin_final_drive.setValue(rec.final_drive)
        for i, spin in enumerate(self._gear_ratio_spins):
            spin.setValue(rec.gear_ratios[i] if i < len(rec.gear_ratios) else 0.0)
        if rec.transmission_max_speed_kmh > 0:
            self._spin_top_speed.setValue(rec.transmission_max_speed_kmh)
        # Prevent the telemetry packet timer from overwriting the AI-filled values.
        self._gear_ratios_captured = True
        # Highlight all params the build populated so the user can see what changed.
        _build_param_keys = [
            "ride_height_front", "ride_height_rear", "springs_front", "springs_rear",
            "dampers_front_comp", "dampers_front_ext", "dampers_rear_comp", "dampers_rear_ext",
            "arb_front", "arb_rear", "camber_front", "camber_rear", "toe_front", "toe_rear",
            "aero_front", "aero_rear", "lsd_initial", "lsd_accel", "lsd_decel",
            "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
            "brake_bias", "ballast_kg", "ballast_position", "power_restrictor",
        ]
        self._highlight_changed_fields(_build_param_keys)

        # Auto-fill shift RPM from AI recommendation.
        # Use new dual fields (shift_rpm_qual / shift_rpm_race) with legacy fallback.
        _qual_rpm = getattr(rec, "shift_rpm_qual", 0) or 0
        _race_rpm = getattr(rec, "shift_rpm_race", 0) or 0
        _legacy_rpm = getattr(rec, "shift_rpm", 0) or 0
        if _qual_rpm == 0 and _legacy_rpm > 0:
            _qual_rpm = _legacy_rpm
        if _race_rpm == 0 and _legacy_rpm > 0:
            _race_rpm = _legacy_rpm
        if _qual_rpm > 0 or _race_rpm > 0:
            sb = self._config.setdefault("shift_beep", {})
            if _qual_rpm > 0:
                sb["qual_rpm"] = _qual_rpm
                if hasattr(self, "_spin_shift_rpm_qual"):
                    self._spin_shift_rpm_qual.blockSignals(True)
                    self._spin_shift_rpm_qual.setValue(_qual_rpm)
                    self._spin_shift_rpm_qual.blockSignals(False)
                if hasattr(self, "_spin_live_shift_rpm_qual"):
                    self._spin_live_shift_rpm_qual.blockSignals(True)
                    self._spin_live_shift_rpm_qual.setValue(_qual_rpm)
                    self._spin_live_shift_rpm_qual.blockSignals(False)
            if _race_rpm > 0:
                sb["race_rpm"] = _race_rpm
                if hasattr(self, "_spin_shift_rpm_race"):
                    self._spin_shift_rpm_race.blockSignals(True)
                    self._spin_shift_rpm_race.setValue(_race_rpm)
                    self._spin_shift_rpm_race.blockSignals(False)
                if hasattr(self, "_spin_live_shift_rpm_race"):
                    self._spin_live_shift_rpm_race.blockSignals(True)
                    self._spin_live_shift_rpm_race.setValue(_race_rpm)
                    self._spin_live_shift_rpm_race.blockSignals(False)
            self._persist_config()

        gear_section = ""
        if rec.final_drive > 0.0 or rec.transmission_max_speed_kmh > 0 or rec.gear_ratios:
            gear_section = "<b>Transmission Recommendation</b><br>"
            if rec.final_drive > 0.0:
                gear_section += f"Final drive: <b>{rec.final_drive:.3f}</b>&nbsp;&nbsp;"
            if rec.transmission_max_speed_kmh > 0:
                gear_section += f"Top speed target: <b>{rec.transmission_max_speed_kmh:.0f} km/h</b><br>"
            else:
                gear_section += "<br>"
            if rec.gear_ratios:
                ratio_str = "&nbsp;&nbsp;".join(
                    f"G{i+1}: {r:.3f}" for i, r in enumerate(rec.gear_ratios)
                )
                gear_section += ratio_str + "<br>"
            gear_section += "<i style='color:#888;'>Enter these in GT7 transmission settings</i><br><br>"

        ecu_section = ""
        if hasattr(rec, "ecu_recommendation") and rec.ecu_recommendation and rec.ecu_recommendation != "—":
            ecu_section = (
                "<b>ECU / Power Advice</b><br>"
                f"<span style='color:#F5C542;'>{rec.ecu_recommendation}</span><br><br>"
            )

        rpm_section = ""
        if hasattr(rec, "shift_rpm") and rec.shift_rpm > 0:
            rpm_section = (
                f"<b>Shift RPM ({session_type}):</b> "
                f"<span style='color:#6CF;'>{rec.shift_rpm:,} RPM</span> "
                f"<span style='color:#888;'>(saved to Shift Beep settings)</span><br><br>"
            )
        # Format reasoning: AI returns paragraphs separated by \n\n — render as proper HTML paragraphs
        _para_style = "margin: 0 0 10px 0; line-height: 1.5;"
        _paras = [p.strip().replace("\n", " ") for p in rec.reasoning.split("\n\n") if p.strip()]
        if not _paras:  # fallback if AI returned a single block
            _paras = [s.strip() for s in rec.reasoning.split(". ") if s.strip()]
            _paras = [". ".join(_paras[:3]), ". ".join(_paras[3:6]), ". ".join(_paras[6:])]
            _paras = [p for p in _paras if p]
        reasoning_html = "".join(f"<p style='{_para_style}'>{p}</p>" for p in _paras)
        # Append a neutral note when reasoning is present to indicate that all values
        # have been clamped to the car's allowed parameter ranges.
        _range_note_html = ""
        if _paras:
            _range_note_html = (
                "<p style='color:#888; font-size:11px; margin:4px 0 0 0;'>"
                "(Values shown applied to the car's allowed range.)"
                "</p>"
            )
        self._build_setup_result.setHtml(
            rpm_section
            + ecu_section
            + gear_section
            + f"<b>AI Setup Reasoning</b><br>"
            + reasoning_html
            + _range_note_html
        )

        # Save build setup to history
        config_id = self._config.get("strategy", {}).get("config_id", "")
        car  = self._config.get("strategy", {}).get("car", "")
        track = self._config.get("strategy", {}).get("track", "")
        if config_id:
            try:
                from data.setup_history import save_entry
                snapshot = self._current_setup_dict()
                is_qual = "qual" in session_type.lower()
                save_entry(config_id, car, track, {
                    "type": "build_qual" if is_qual else "build_race",
                    "session_type": session_type,
                    "setup_snapshot": snapshot,
                    "reasoning": rec.reasoning,
                    "shift_rpm": getattr(rec, "shift_rpm", 0),
                    "shift_rpm_qual": getattr(rec, "shift_rpm_qual", 0),
                    "shift_rpm_race": getattr(rec, "shift_rpm_race", 0),
                    "ecu_recommendation": getattr(rec, "ecu_recommendation", ""),
                })
            except Exception as _e:
                print(f"[SetupHistory] build save failed: {_e}")

    def _sync_setup_builder_from_event(self) -> None:
        try:
            evt = self._active_event()
            sc  = self._config.get("strategy", {})
            if not evt:
                if hasattr(self, "_lbl_setup_event_ctx"):
                    self._lbl_setup_event_ctx.setText(
                        "No active event — go to Event Planner and click 'Set as Active' first."
                    )
                _warn = "— (set active event first) —"
                for attr in ("_lbl_rc_race_type", "_lbl_rc_race_length", "_lbl_rc_fuel_mult",
                             "_lbl_rc_tyre_wear", "_lbl_rc_refuel_rate", "_lbl_rc_req_tyre",
                             "_lbl_rc_avail_tyres", "_lbl_rc_mand_pits", "_lbl_rc_weather",
                             "_lbl_rc_damage", "_lbl_rc_bop", "_lbl_rc_tuning"):
                    if hasattr(self, attr):
                        getattr(self, attr).setText(_warn)
                        getattr(self, attr).setStyleSheet("color: #F5C542; font-size: 11px;")
                return
            name  = evt.get("name", "?")
            track = sc.get("track") or evt.get("track", "?")
            car   = sc.get("car", "") or "—"
            tw    = sc.get("tyre_wear_multiplier", evt.get("tyre_wear", 1))
            fm    = sc.get("fuel_mult", evt.get("fuel_mult", 1))
            rt    = sc.get("race_type", "lap")
            laps  = int(sc.get("total_laps", 25))
            dur   = int(sc.get("race_duration_minutes", 60))
            length_str = f"{dur} min" if rt == "timed" else f"{laps} laps"

            if hasattr(self, "_lbl_setup_event_ctx"):
                self._lbl_setup_event_ctx.setText(
                    f"Active Event: {name}  |  Track: {track}  |  Car: {car}"
                )
            # Refresh the structured setup-name suggestion for the active event.
            if hasattr(self, "_setup_label"):
                self._prefill_setup_label()

            _green = "color: #AAE4AA; font-size: 11px;"
            if hasattr(self, "_lbl_rc_race_type"):
                self._lbl_rc_race_type.setText("Timed Race" if rt == "timed" else "Lap Race")
                self._lbl_rc_race_type.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_race_length"):
                self._lbl_rc_race_length.setText(length_str)
                self._lbl_rc_race_length.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_fuel_mult"):
                self._lbl_rc_fuel_mult.setText(f"×{int(fm)}")
                self._lbl_rc_fuel_mult.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_tyre_wear"):
                self._lbl_rc_tyre_wear.setText(f"×{int(tw)}")
                self._lbl_rc_tyre_wear.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_refuel_rate"):
                self._lbl_rc_refuel_rate.setText(f"{sc.get('refuel_speed_lps', 10)} L/s")
                self._lbl_rc_refuel_rate.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_req_tyre"):
                _rq = sc.get("required_tyres", [])
                _rq_str = ", ".join(_rq) if isinstance(_rq, list) else (sc.get("mandatory_compounds", "") or "")
                self._lbl_rc_req_tyre.setText(_rq_str or "—")
                self._lbl_rc_req_tyre.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_avail_tyres"):
                _at = sc.get("avail_tyres", evt.get("avail_tyres", []))
                _at_str = ", ".join(_at) if isinstance(_at, list) else (_at or "")
                self._lbl_rc_avail_tyres.setText(_at_str or "—")
                self._lbl_rc_avail_tyres.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_mand_pits"):
                self._lbl_rc_mand_pits.setText(str(int(sc.get("mandatory_stops", 0))))
                self._lbl_rc_mand_pits.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_weather"):
                self._lbl_rc_weather.setText(sc.get("weather", "—") or "—")
                self._lbl_rc_weather.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_damage"):
                self._lbl_rc_damage.setText(sc.get("damage", "—") or "—")
                self._lbl_rc_damage.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_bop"):
                self._lbl_rc_bop.setText("Yes" if sc.get("bop") else "No")
                self._lbl_rc_bop.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_tuning"):
                self._lbl_rc_tuning.setText("Allowed" if sc.get("tuning") else "Not Allowed")
                self._lbl_rc_tuning.setStyleSheet(_green)
            _bop    = bool(sc.get("bop", evt.get("bop", False)))
            _tuning = bool(sc.get("tuning", evt.get("tuning", True)))
            _cats   = sc.get("allowed_tuning_categories", [])
            self._on_bop_toggled(_bop)
            self._apply_setup_permissions(_bop, _tuning, _cats)
            self._refresh_live_tyre_label()
            # Re-bound spinboxes for the new car and load race engineer brief
            self._rebound_setup_spinboxes(sc.get("car", "") or "")
            self._load_re_brief_from_active_event()
        except Exception:
            pass

    def _build_setup_builder_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        self._lbl_setup_event_ctx = QLabel("No active event — go to Event Planner and click 'Set as Active' first.")
        self._lbl_setup_event_ctx.setWordWrap(True)
        self._lbl_setup_event_ctx.setStyleSheet("color: #F5C542; font-size: 11px; padding: 4px;")
        layout.addWidget(self._lbl_setup_event_ctx)

        _rc_group = QGroupBox("Race Conditions (from Event Planner)")
        _rc_group.setStyleSheet(self._group_style())
        _rc_form = QFormLayout(_rc_group)
        _rc_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _rc_lbl_s = "color: #AAE4AA; font-size: 11px;"
        _rc_key_s = f"color: {_TEXT}; font-size: 11px;"

        self._lbl_rc_race_type   = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_race_length = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_fuel_mult   = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_tyre_wear   = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_refuel_rate = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_req_tyre    = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_avail_tyres = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_mand_pits   = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_weather     = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_damage      = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_bop         = QLabel("—", styleSheet=_rc_lbl_s)
        self._lbl_rc_tuning      = QLabel("—", styleSheet=_rc_lbl_s)

        _rc_form.addRow(QLabel("Race Type:",        styleSheet=_rc_key_s), self._lbl_rc_race_type)
        _rc_form.addRow(QLabel("Race Length:",      styleSheet=_rc_key_s), self._lbl_rc_race_length)
        _rc_form.addRow(QLabel("Fuel Multiplier:",  styleSheet=_rc_key_s), self._lbl_rc_fuel_mult)
        _rc_form.addRow(QLabel("Tyre Wear:",        styleSheet=_rc_key_s), self._lbl_rc_tyre_wear)
        _rc_form.addRow(QLabel("Refuel Rate:",      styleSheet=_rc_key_s), self._lbl_rc_refuel_rate)
        _rc_form.addRow(QLabel("Required Tyres:",   styleSheet=_rc_key_s), self._lbl_rc_req_tyre)
        _rc_form.addRow(QLabel("Available Tyres:",  styleSheet=_rc_key_s), self._lbl_rc_avail_tyres)
        _rc_form.addRow(QLabel("Mandatory Pits:",   styleSheet=_rc_key_s), self._lbl_rc_mand_pits)
        _rc_form.addRow(QLabel("Weather:",          styleSheet=_rc_key_s), self._lbl_rc_weather)
        _rc_form.addRow(QLabel("Damage:",           styleSheet=_rc_key_s), self._lbl_rc_damage)
        _rc_form.addRow(QLabel("BoP:",              styleSheet=_rc_key_s), self._lbl_rc_bop)
        _rc_form.addRow(QLabel("Tuning Allowed:",   styleSheet=_rc_key_s), self._lbl_rc_tuning)
        _rc_note = QLabel("To change these, update the active event in Event Planner.")
        _rc_note.setStyleSheet("color: #888; font-size: 10px;")
        _rc_note.setWordWrap(True)
        _rc_form.addRow(_rc_note)
        layout.addWidget(_rc_group)

        history_group = QGroupBox("Setup History")
        history_group.setStyleSheet(self._group_style())
        history_h = QHBoxLayout(history_group)
        history_h.addWidget(QLabel("Past AI iteration:"))
        self._setup_history_combo = QComboBox()
        self._setup_history_combo.setMinimumWidth(300)
        self._setup_history_combo.setToolTip("Select a past AI setup iteration to review")
        self._setup_history_combo.currentIndexChanged.connect(self._on_setup_history_selected)
        history_h.addWidget(self._setup_history_combo)
        btn_refresh_hist = QPushButton("Refresh")
        btn_refresh_hist.setStyleSheet(
            "QPushButton { background: #2A2A2A; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background: #3A3A3A; }"
        )
        btn_refresh_hist.clicked.connect(self._refresh_setup_history_combo)
        history_h.addWidget(btn_refresh_hist)
        history_h.addStretch()
        layout.addWidget(history_group)

        layout.addWidget(self._build_car_setup_group())
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _refresh_setup_history_combo(self) -> None:
        try:
            config_id    = self._config.get("strategy", {}).get("config_id", "")
            history_path = Path(__file__).parent.parent / "data" / "setup_history.json"
            if not history_path.exists():
                self._setup_history_combo.clear()
                return
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get(config_id, [])
            self._setup_history_combo.blockSignals(True)
            self._setup_history_combo.clear()
            for i, entry in enumerate(reversed(entries)):
                self._setup_history_combo.addItem(entry.get("timestamp", f"Entry {i + 1}"))
            self._setup_history_combo.blockSignals(False)
        except Exception:
            try:
                self._setup_history_combo.clear()
            except Exception:
                pass

    def _on_setup_history_selected(self, index: int) -> None:
        if index < 0:
            return
        try:
            config_id    = self._config.get("strategy", {}).get("config_id", "")
            history_path = Path(__file__).parent.parent / "data" / "setup_history.json"
            if not history_path.exists():
                return
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = list(reversed(data.get(config_id, [])))
            if index >= len(entries):
                return
            text = entries[index].get("reasoning", entries[index].get("analysis", "No details available."))
            result_widget = getattr(self, "_build_setup_result", None)
            if result_widget is not None:
                result_widget.setPlainText(text)
                result_widget.setVisible(True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Story 4 — field highlight helpers
    # ------------------------------------------------------------------

    # Param key → widget attribute name mapping (mirrors _rebound_setup_spinboxes _PARAM_MAP).
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

    _HIGHLIGHT_STYLE = "background:#2A4A2A; border:1px solid #8BC34A;"

    def _highlight_changed_fields(self, field_names: list[str]) -> None:
        """Highlight spinboxes for the given param keys with a green tint.

        Clears any previous highlights first so re-applying replaces cleanly.
        """
        self._clear_setup_highlights()
        _highlighted: set[str] = getattr(self, "_highlighted_fields", set())
        for key in field_names:
            attr = self._HIGHLIGHT_PARAM_MAP.get(key)
            if attr is None:
                continue
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            widget.setStyleSheet(self._HIGHLIGHT_STYLE)
            _highlighted.add(key)
        self._highlighted_fields = _highlighted

    def _clear_setup_highlights(self) -> None:
        """Remove highlight styling from all currently-highlighted spinboxes."""
        _highlighted: set[str] = getattr(self, "_highlighted_fields", set())
        for key in list(_highlighted):
            attr = self._HIGHLIGHT_PARAM_MAP.get(key)
            if attr is None:
                continue
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            widget.setStyleSheet("")
        self._highlighted_fields = set()

    # ------------------------------------------------------------------
    # Task 1 — spinbox re-bounding slot
    # ------------------------------------------------------------------

    def _rebound_setup_spinboxes(self, car_name: str | None = None) -> None:
        """Re-apply per-car (min,max) to every in-scope setup spinbox.

        Called when the active car changes (via _sync_setup_builder_from_event /
        autofill) and after saving car ranges.  Must NOT trigger an AI call.
        """
        _car = (car_name or "").strip() or self._config.get("strategy", {}).get("car", "") or ""
        _ranges = resolve_ranges(_car)

        # Map: (param_key, spinbox_attr, is_double)
        _PARAM_MAP = [
            ("ride_height_front",  "_setup_rh_f",       False),
            ("ride_height_rear",   "_setup_rh_r",       False),
            ("springs_front",      "_setup_spr_f",      True),
            ("springs_rear",       "_setup_spr_r",      True),
            ("dampers_front_comp", "_setup_dmp_f_comp", False),
            ("dampers_front_ext",  "_setup_dmp_f_ext",  False),
            ("dampers_rear_comp",  "_setup_dmp_r_comp", False),
            ("dampers_rear_ext",   "_setup_dmp_r_ext",  False),
            ("arb_front",          "_setup_arb_f",      False),
            ("arb_rear",           "_setup_arb_r",      False),
            ("camber_front",       "_setup_cam_f",      True),
            ("camber_rear",        "_setup_cam_r",      True),
            ("toe_front",          "_setup_toe_f",      True),
            ("toe_rear",           "_setup_toe_r",      True),
            ("aero_front",         "_setup_aero_f",     False),
            ("aero_rear",          "_setup_aero_r",     False),
            ("lsd_initial",        "_setup_lsd_i",      False),
            ("lsd_accel",          "_setup_lsd_a",      False),
            ("lsd_decel",          "_setup_lsd_d",      False),
            ("lsd_front_initial",  "_setup_lsd_f_i",    False),
            ("lsd_front_accel",    "_setup_lsd_f_a",    False),
            ("lsd_front_decel",    "_setup_lsd_f_d",    False),
            ("brake_bias",         "_setup_bb",         False),
            ("ballast_kg",         "_setup_ballast_kg", True),
            ("ballast_position",   "_setup_ballast_pos",False),
            ("power_restrictor",   "_setup_power_rest", True),
        ]

        for param, attr, is_dbl in _PARAM_MAP:
            spin = getattr(self, attr, None)
            if spin is None:
                continue
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            if is_dbl:
                lo, hi = float(lo), float(hi)
                spin.setRange(lo, hi)
                cur = spin.value()
                spin.setValue(max(lo, min(hi, cur)))
            else:
                lo, hi = int(lo), int(hi)
                spin.setRange(lo, hi)
                cur = spin.value()
                spin.setValue(max(lo, min(hi, cur)))
            # Read-only when min==max (parameter not adjustable on this car)
            _set_spin_readonly(spin, lo >= hi)

    # ------------------------------------------------------------------
    # Task 2 — "Set Car Ranges…" dialog
    # ------------------------------------------------------------------

    def _open_car_ranges_dialog(self) -> None:
        """Open the CarRangesDialog for the currently active car."""
        car_name = self._config.get("strategy", {}).get("car", "") or ""
        dlg = CarRangesDialog(car_name, self)
        dlg.ranges_saved.connect(self._rebound_setup_spinboxes)
        dlg.exec()

    # ------------------------------------------------------------------
    # Task 3 — Race Engineer Brief visibility + persistence helpers
    # ------------------------------------------------------------------

    def _on_setup_type_changed(self, session_type_text: str = "") -> None:
        """Write _practice_is_qual_ref[0] when the Setup-tab session type changes.

        The ref is read by on_packet in main.py to select the correct shift RPM
        threshold when the live mode is Practice.  Guard with hasattr since tests
        may construct the window before main() injects the ref.
        """
        is_qual = "qual" in (session_type_text or "").lower()
        if hasattr(self, "_practice_is_qual_ref"):
            import main
            with main._state_lock:
                self._practice_is_qual_ref[0] = is_qual
        # Regenerate the structured setup-name suggestion for the new Q/R prefix.
        if hasattr(self, "_setup_label"):
            self._prefill_setup_label()

    def _update_re_brief_visibility(self, session_type_text: str = "") -> None:
        """Show Race Engineer Brief for race sessions; hide for Qualifying."""
        is_qual = "qual" in (session_type_text or "").lower()
        for w in (getattr(self, "_re_brief_label", None),
                  getattr(self, "_re_brief_input", None)):
            if w is not None:
                w.setVisible(not is_qual)

    def _load_re_brief_from_active_event(self) -> None:
        """Populate _re_brief_input from the active event's race_engineer_brief."""
        if not hasattr(self, "_re_brief_input"):
            return
        evt = self._active_event() if hasattr(self, "_active_event") else {}
        brief = evt.get("race_engineer_brief", "") or ""
        self._re_brief_input.blockSignals(True)
        self._re_brief_input.setPlainText(brief)
        self._re_brief_input.blockSignals(False)

    def _save_re_brief_to_active_event(self) -> None:
        """Write _re_brief_input text into the active event in config and persist."""
        if not hasattr(self, "_re_brief_input"):
            return
        aid = self._config.get("active_event_id")
        if not aid:
            return
        brief = self._re_brief_input.toPlainText() or ""
        # Update in config["events"]
        for evt in self._config.get("events", []):
            if evt.get("name") == aid:
                evt["race_engineer_brief"] = brief
                break
        # Also update in DB if available
        if self._db is not None:
            try:
                existing = self._db.get_event(aid)
                if existing:
                    existing["race_engineer_brief"] = brief
                    self._db.upsert_event(existing)
            except Exception as _e:
                print(f"[SetupBuilder] re_brief DB save failed: {_e}")
        self._persist_config()
