"""Setup Builder tab — mixin for MainWindow (DashboardWindow)."""
from __future__ import annotations

import json
import json as _json  # alias used in _display_setup_result (verbatim copy from dashboard.py)
import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QLineEdit, QTextEdit,
    QComboBox, QScrollArea, QSplitter,
)

from strategy.setup_ranges import resolve_ranges, save_car_ranges, GENERIC_DEFAULTS
from ui.car_ranges_dialog import CarRangesDialog  # noqa: F401 — used in _open_car_ranges_dialog
from ui.setup_form_widget import SetupFormWidget

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


def _setup_response_looks_complete(payload: str) -> bool:
    """Heuristic: does the advisor payload look like a complete setup JSON?

    A response truncated at the API token cap ends mid-value (no closing brace)
    or omits the ``setup_fields`` key entirely.  Detecting that lets the UI show
    a clear "try again" message instead of dumping raw/partial JSON at the user
    (UAT: analyse button "returned jargon to text box").
    """
    s = (payload or "").strip()
    return s.endswith("}") and '"setup_fields"' in s


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

    def _active_form(self) -> "SetupFormWidget":
        """Return the currently-active setup form (Race form by default).

        The Race form's widgets are aliased to ``self._setup_*`` attributes, so
        all legacy mixin methods (``_current_setup_dict``, ``_fill_setup_fields``,
        ``_apply_build_setup_result``, etc.) continue to work unchanged.
        Exposed as a method so callers can be parameterised by form in the future.
        """
        return self._race_form

    def _build_car_setup_group(self) -> QWidget:
        """Build the side-by-side Race + Qualifying setup panel.

        Returns a QWidget that contains:
        - A tab-level "Live Session Mode" row (self._setup_type combo)
        - A QSplitter with Race form on the left and Qualifying form on the right
        - Shared Shift RPM display box below the splitter

        All self._setup_* widget attributes are aliased to the Race form's widgets
        so that every existing mixin method (AI, save, load, highlight, rebound)
        continues to operate on the Race form through self.
        """
        lbl_s = f"color: {_TEXT};"
        container = QWidget()
        outer_layout = QVBoxLayout(container)
        outer_layout.setSpacing(8)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        if hasattr(self, "_tab_intro_header"):
            outer_layout.addWidget(self._tab_intro_header(
                "Setup Builder",
                "Build and tune your qualifying and race setups side by side. Ask "
                "AI for a full setup or a targeted fix, then Apply and Save. Next: "
                "set Min Weight and Max Power, then Build Setup with AI — or "
                "describe a handling issue and click Analyse."))

        # self._setup_type stays on self (required by main.py + tests). It picks
        # which shift-RPM threshold the live beep uses during Practice telemetry.
        # It is NOT a form-selector — both forms are always visible side-by-side —
        # so it lives in the Shift RPM box below (next to the two RPM values it
        # chooses between) rather than as a prominent row at the top of the tab.
        self._setup_type = QComboBox()
        self._setup_type.addItems(["Race Setup", "Qualifying Setup"])
        self._setup_type.setToolTip(
            "Which shift-RPM threshold the live beep uses during Practice telemetry.\n"
            "Race Setup: use race shift RPM.  Qualifying Setup: use qualifying shift RPM."
        )
        # Connect session-type signals (required by tests + main.py sync)
        self._setup_type.currentTextChanged.connect(self._on_setup_type_changed)
        self._on_setup_type_changed(self._setup_type.currentText())

        # ── Create Race and Qualifying form widgets ────────────────────────────
        self._race_form = SetupFormWidget("Race", self)
        self._qual_form = SetupFormWidget("Qualifying", self)

        # ── Alias self._setup_* to Race form widgets ──────────────────────────
        # Every legacy mixin method that accesses self._setup_rh_f etc. will
        # transparently read/write the Race form's widgets.
        _RACE_ALIASES = [
            "_setup_rh_f", "_setup_rh_r",
            "_setup_spr_f", "_setup_spr_r",
            "_setup_dmp_f_comp", "_setup_dmp_f_ext",
            "_setup_dmp_r_comp", "_setup_dmp_r_ext",
            "_setup_arb_f", "_setup_arb_r",
            "_setup_cam_f", "_setup_cam_r",
            "_setup_toe_f", "_setup_toe_r",
            "_setup_aero_f", "_setup_aero_r",
            "_setup_lsd_i", "_setup_lsd_a", "_setup_lsd_d",
            "_setup_lsd_f_i", "_setup_lsd_f_a", "_setup_lsd_f_d",
            "_setup_tvcd", "_setup_torque_dist", "_setup_bb",
            "_setup_tyre_f", "_setup_tyre_r",
            "_setup_ecu", "_setup_ecu_output",
            "_setup_trans_type",
            "_setup_nitrous", "_setup_nitrous_output",
            "_setup_min_weight", "_setup_max_power",
            "_setup_ballast_kg", "_setup_ballast_pos", "_setup_power_rest",
            "_setup_actual_bhp", "_setup_num_gears", "_setup_drivetrain",
            "_setup_label", "_setup_notes",
            "_gear_ratio_spins", "_spin_final_drive", "_spin_top_speed",
            "_lbl_ecu_rec",
            # UI-state widgets referenced by dashboard.py helpers
            "_lbl_car_specs_info",
            "_lbl_bop_info", "_btn_bop_edit", "_btn_bop_reload", "_bop_info_row_label",
            "_lbl_lsd_front", "_lsd_front_widget",
            "_setup_locked_banner",
            # Action/result widgets for existing mixin methods
            "_setup_result_text", "_btn_analyse_setup",
            "_btn_apply_ai_setup",
            "_setup_feeling_input",
            "_build_setup_result", "_btn_build_setup", "_btn_set_car_ranges",
            "_setup_load_combo", "_lbl_setup_save_status",
            "_re_brief_label", "_re_brief_input",
            "_btn_reread_gears",
        ]
        for _attr in _RACE_ALIASES:
            setattr(self, _attr, getattr(self._race_form, _attr))

        # State attributes that live on self (not on the form widget)
        self._last_setup_ai_fields: dict = {}
        self._highlighted_fields: set = set()

        # ── Wire Race form buttons to existing mixin methods ──────────────────
        self._race_form._btn_save_setup.clicked.connect(self._setup_save)
        self._race_form._btn_load_setup.clicked.connect(self._setup_load_selected)
        self._race_form._btn_analyse_setup.clicked.connect(self._setup_analyse_ai)
        self._race_form._btn_apply_ai_setup.clicked.connect(self._apply_and_save_ai_setup)
        self._race_form._btn_build_setup.clicked.connect(self._run_build_setup)
        self._race_form._btn_set_car_ranges.clicked.connect(self._open_car_ranges_dialog)
        self._race_form._btn_bop_edit.clicked.connect(self._open_bop_file)
        self._race_form._btn_bop_reload.clicked.connect(self._reload_bop_data)

        # ── Wire Qualifying form buttons to per-form handlers ─────────────────
        qf = self._qual_form
        qf._btn_save_setup.clicked.connect(
            lambda: self._setup_save_for_form(self._qual_form)
        )
        qf._btn_load_setup.clicked.connect(
            lambda: self._setup_load_selected_for_form(self._qual_form)
        )
        qf._btn_analyse_setup.clicked.connect(
            lambda: self._setup_analyse_ai_for_form(self._qual_form)
        )
        qf._btn_apply_ai_setup.clicked.connect(
            lambda: self._apply_ai_setup_for_form(self._qual_form)
        )
        qf._btn_build_setup.clicked.connect(
            lambda: self._run_build_setup_for_form(self._qual_form)
        )
        qf._btn_set_car_ranges.clicked.connect(self._open_car_ranges_dialog)
        qf._btn_bop_edit.clicked.connect(self._open_bop_file)
        qf._btn_bop_reload.clicked.connect(self._reload_bop_data)

        # ── Tyre compound → Lap Data tab default compound (Race form only) ────
        self._race_form._setup_tyre_f.currentTextChanged.connect(
            lambda name: setattr(self, "_default_lap_compound",
                                 self._TYRE_NAME_TO_CODE.get(name, ""))
        )
        self._race_form._setup_tyre_f.currentTextChanged.connect(
            lambda _: self._refresh_live_tyre_label()
        )

        # ── QSplitter — Race left, Qualifying right ───────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Wrap each form in a QScrollArea so it scrolls independently
        race_scroll = QScrollArea()
        race_scroll.setWidgetResizable(True)
        race_scroll.setWidget(self._race_form)
        race_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        qual_scroll = QScrollArea()
        qual_scroll.setWidgetResizable(True)
        qual_scroll.setWidget(self._qual_form)
        qual_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        splitter.addWidget(race_scroll)
        splitter.addWidget(qual_scroll)
        splitter.setSizes([1, 1])  # equal initial split
        outer_layout.addWidget(splitter, 1)  # the splitter takes all extra height

        # ── Shift RPM display (shared, below the splitter) ────────────────────
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
        # The live shift-beep threshold selector (formerly the top-of-tab "Live
        # Session Mode" row) sits here next to the two RPM values it chooses.
        shift_rpm_form.addRow("Live beep uses:", self._setup_type)
        outer_layout.addWidget(shift_rpm_box)

        self._refresh_setup_combo()
        self._refresh_qual_setup_combo()
        return container

    def _current_setup_dict(self) -> dict:
        """Read all manual fields including editable gear ratios.

        Phase 5: the event-identity fields (car/track/weather/bop) come from
        the canonical EventContext (DB-first) instead of the legacy fan-out —
        byte-identical in sync. Safe off the UI thread too (the voice query
        listener holds this as its setup getter): SessionDB is
        check_same_thread=False with an internal lock.
        """
        gear_ratios = [s.value() for s in self._gear_ratio_spins if s.value() > 0.0]
        _ev_ctx = self._build_event_context()
        return {
            "name":      _ev_ctx.car or "Unknown Car",
            "car":       _ev_ctx.car or "Unknown Car",
            "setup_label": self._setup_label.text().strip() or "Setup 1",
            "track":     _ev_ctx.track,
            "condition": {
                "Fixed Dry": "Dry", "Dry": "Dry", "Random Weather": "Dry",
                "Fixed Wet": "Wet", "Wet": "Wet", "Heavy Rain": "Wet",
                "Light Rain": "Damp", "Wet Risk": "Damp", "Damp": "Damp",
            }.get(_ev_ctx.weather, "Dry"),
            "setup_type": (
                self._race_form.purpose + " Setup"
                if hasattr(self, "_race_form")
                else self._setup_type.currentText()
            ),
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
            "bop_race":       _ev_ctx.bop_enabled,
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
        # The setup type is now spatial (two side-by-side forms with fixed purposes).
        # Loading a saved setup does NOT switch the tab-level live-session combo
        # (self._setup_type) — that combo controls shift-RPM threshold selection,
        # not which form panel is active.  The form panel is fixed by its purpose.
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
        """Refresh the Race form's load combo (filters to Race setups)."""
        if not hasattr(self, "_setup_load_combo"):
            return
        self._setup_load_combo.blockSignals(True)
        self._setup_load_combo.clear()
        self._setup_load_combo.addItem("— select to load —")   # placeholder at index 0
        for s in self._saved_setups:
            setup_lbl = s.get("setup_label") or "Setup"
            car_name  = s.get("name", "Unnamed")
            label = f"{setup_lbl} ({car_name}) — {s.get('track', '')} [{s.get('setup_type', s.get('session', ''))}]"
            self._setup_load_combo.addItem(label)
        # select_index is relative to _saved_setups; shift by 1 for the placeholder
        if 0 <= select_index < len(self._saved_setups):
            self._setup_load_combo.setCurrentIndex(select_index + 1)
        else:
            self._setup_load_combo.setCurrentIndex(0)   # show placeholder
        self._setup_load_combo.blockSignals(False)

    def _refresh_qual_setup_combo(self, select_index: int = -1) -> None:
        """Refresh the Qualifying form's load combo (all setups; filter to Q if desired)."""
        if not hasattr(self, "_qual_form"):
            return
        combo = self._qual_form._setup_load_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— select to load —")
        for s in self._saved_setups:
            setup_lbl = s.get("setup_label") or "Setup"
            car_name  = s.get("name", "Unnamed")
            label = f"{setup_lbl} ({car_name}) — {s.get('track', '')} [{s.get('setup_type', s.get('session', ''))}]"
            combo.addItem(label)
        if 0 <= select_index < len(self._saved_setups):
            combo.setCurrentIndex(select_index + 1)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Per-form handlers for the Qualifying panel
    # ------------------------------------------------------------------

    def _setup_save_for_form(self, form: "SetupFormWidget") -> None:
        """Save the setup from ``form`` (used for the Qualifying panel)."""
        from PyQt6.QtWidgets import QMessageBox
        _evt_name = ""
        if hasattr(self, "_active_event"):
            _evt_name = (self._active_event() or {}).get("name", "") or ""
        if not _evt_name:
            QMessageBox.warning(
                self,
                "No Active Event",
                "Please select an active event in the Event Planner before saving a setup.",
            )
            return
        from ui.setup_name_helper import resolve_save_name
        _prefix = form.purpose_prefix()
        form._setup_label.setText(
            resolve_save_name(
                form._setup_label.text(),
                _prefix,
                _evt_name,
                self._saved_setups,
            )
        )
        form.clear_highlights()
        if form.purpose == "Race":
            self._save_re_brief_to_active_event()
        d = form.current_setup_dict()
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

        if self._db is not None:
            _meta_keys = {"name", "setup_label", "setup_id", "captured_at", "ai_notes"}
            _car_name = d.get("name", "")
            _car_id = self._db.get_car_id(_car_name) if _car_name else 0
            _event_id = int(self._build_event_context().event_id or 0)
            _label = d.get("setup_label", "Setup")
            _fields = {k: v for k, v in d.items() if k not in _meta_keys}
            _existing_db_id = d.get("setup_id") if existing is not None else 0
            if _existing_db_id:
                self._db.update_setup(_existing_db_id, _label, _fields)
            else:
                _new_id = self._db.save_setup(_car_id, _event_id, _label, _fields)
                d["setup_id"] = _new_id
                self._saved_setups[target_idx]["setup_id"] = _new_id

        ca["setups"] = self._saved_setups
        self._persist_config()
        self._refresh_setup_combo(select_index=target_idx)
        self._refresh_qual_setup_combo(select_index=target_idx)
        self._refresh_all_setup_combos()
        self._bridge.event_log_entry.emit(f"[Setup] saved: {d['name']} (ID {d.get('setup_id', '?')})")
        lbl = d.get("setup_label", "") or "Setup"
        form._lbl_setup_save_status.setText(f"Saved: {lbl}  (ID {d.get('setup_id', '?')})")
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(4000, lambda: (
            form._lbl_setup_save_status.setText("")
            if hasattr(form, "_lbl_setup_save_status") else None
        ))

    def _setup_load_selected_for_form(self, form: "SetupFormWidget") -> None:
        """Load the selected setup into ``form``."""
        idx = form._setup_load_combo.currentIndex()
        real_idx = idx - 1
        if 0 <= real_idx < len(self._saved_setups):
            form.fill_setup_fields(self._saved_setups[real_idx])
            self._after_setup_load()

    def _setup_analyse_ai_for_form(self, form: "SetupFormWidget") -> None:
        """Run the AI setup-analysis for ``form`` and put results in that form's result text."""
        if self._driving_advisor is None:
            form._setup_result_text.setPlainText("Driving advisor not available.")
            return
        d = form.current_setup_dict()
        _car_name, _car_specs = self._load_car_specs_for_current()
        setup_id = d.get("setup_id")
        n_laps = 5
        if setup_id:
            count = sum(
                1 for r in range(self._lap_table.rowCount())
                if (w := self._lap_table.cellWidget(r, 14)) is not None
                and w.currentText().startswith(f"{setup_id} —")
            )
            if count > 0:
                n_laps = count
        feeling = form._setup_feeling_input.toPlainText().strip()
        form._setup_result_text.setPlainText("Analysing setup… please wait.")
        form._btn_analyse_setup.setEnabled(False)
        import threading as _threading
        _ai_snap = self._build_setup_ai_snapshot()
        _allowed  = _ai_snap.allowed_tuning_or_none()
        _locked   = _ai_snap.tuning_locked
        _compound = _ai_snap.mandatory_compounds_str

        def _worker():
            try:
                resp = self._driving_advisor.build_combined_setup_response(
                    d, n_laps=n_laps, car_name=_car_name, car_specs=_car_specs,
                    feeling=feeling or None,
                    allowed_tuning=_allowed, tuning_locked=_locked,
                    compound=_compound)
                self._setup_result_queue.put(("ok", resp, "analyse_setup", feeling or None, form))
            except Exception as exc:
                self._setup_result_queue.put(("error", str(exc), "analyse_setup", None, form))

        _threading.Thread(target=_worker, daemon=True).start()

    def _apply_ai_setup_for_form(self, form: "SetupFormWidget") -> None:
        """Apply AI-recommended fields to ``form`` (per-form apply button handler)."""
        if not getattr(form, "last_ai_fields", {}):
            return
        form.apply_ai_fields(form.last_ai_fields)
        # Keep the form's structured Q/R setup name — do NOT rename to "AI Fix N".
        # Save advances the structured name to the next numbered attempt.
        form.last_ai_fields = {}
        form._btn_apply_ai_setup.setVisible(False)

    def _run_build_setup_for_form(self, form: "SetupFormWidget") -> None:
        """Build a complete setup with AI for the given form (Qualifying panel)."""
        # Delegates to the main _run_build_setup but uses the form's purpose as session_type.
        # We temporarily proxy self._setup_type to match the form's purpose so the existing
        # _run_build_setup reads the correct session type.
        # The session_type is captured at call time from the form's purpose.
        import threading as _threading
        from strategy.ai_planner import build_car_setup

        api_key = self._ai_api_key.text().strip()
        if not api_key:
            form._build_setup_result.setPlainText(
                "No API key configured. Add your Anthropic API key in the AI Race Analysis section.")
            form._build_setup_result.setVisible(True)
            return

        _ai_snap = self._build_setup_ai_snapshot()
        car          = _ai_snap.car
        track        = _ai_snap.track
        session_type = f"{form.purpose} Setup"
        race_laps    = _ai_snap.race_laps
        min_weight   = form._setup_min_weight.value()
        max_power    = form._setup_max_power.value()
        actual_bhp   = form._setup_actual_bhp.value()
        num_gears    = form._setup_num_gears.value()
        drivetrain   = form._setup_drivetrain.currentData()
        bop_data     = self._get_bop_data_for_car()
        _duration_mins   = _ai_snap.duration_mins
        _mandatory_stops = _ai_snap.mandatory_stops
        _refuel_rate_lps = _ai_snap.refuel_rate_lps
        _pit_loss_secs   = _ai_snap.pit_loss_secs
        _re_brief        = (
            form._re_brief_input.toPlainText().strip()
            if hasattr(form, "_re_brief_input") and form._re_brief_input.isVisible()
            else ""
        )
        _, _car_specs = self._load_car_specs_for_current()
        _allowed_tuning = _ai_snap.allowed_tuning_or_none()
        _tuning_locked  = _ai_snap.tuning_locked
        _tyre_wear_mult  = _ai_snap.tyre_wear_multiplier
        _fuel_mult       = _ai_snap.fuel_multiplier
        _avail_tyres     = _ai_snap.avail_tyres_list()
        _req_tyres       = _ai_snap.required_tyres_list()
        _race_type_build = _ai_snap.race_type
        _track_loc_id    = _ai_snap.track_location_id
        _layout_id_build = _ai_snap.layout_id
        _last_lap = self._recorder.last_lap() if self._recorder else None
        _gearbox_analysis = _last_lap.gearbox_analysis if _last_lap else {}
        _car_id_build = self._db.get_car_id(car) if self._db and car and car != "Unknown" else 0
        self._car_id_build = _car_id_build
        _ofr2_laps = self._resolve_recent_laps(_car_id_build, track)

        form._btn_build_setup.setEnabled(False)
        form._btn_build_setup.setText("Building…")
        form._build_setup_result.setPlainText(
            "Asking AI for complete car setup — this takes 20–30 seconds…")
        form._build_setup_result.setVisible(True)

        _session_id_build = (
            int(self._dispatcher._session_id)
            if hasattr(self, "_dispatcher") and self._dispatcher is not None
            else 0
        )

        def _worker():
            try:
                _setup_history_str = ""
                _setup_comparison_str = ""
                if self._db and _car_id_build > 0 and track:
                    try:
                        _setup_history_str = self._db.get_setup_history_for_car_track(
                            _car_id_build, track, limit=10)
                    except Exception:
                        pass
                    try:
                        _setup_comparison_str = self._build_setup_comparison_text(track)
                    except Exception:
                        pass
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
                                      race_engineer_brief=_re_brief,
                                      per_lap_telemetry=_ofr2_laps or None)
                self._build_setup_queue.put(("ok", rec, session_type, form))
            except Exception as exc:
                self._build_setup_queue.put(("err", str(exc), session_type, form))

        _threading.Thread(target=_worker, daemon=True).start()

    def _build_setup_context(self, recommendation: dict | None = None,
                             diagnosis: dict | None = None):
        """Canonical read model of the active setup recommendation.

        State Consolidation 3: separates setup-recommendation state (purpose,
        source, adjustments, baseline/target setup, confidence, validation) from
        the event truth (EventContext) and strategy truth (StrategyContext /
        StrategyPromptSnapshot) it was built against, keying the setup to
        ``EventContext.change_hash`` and ``StrategyPromptSnapshot.snapshot_id``
        so stale setups are detectable (see ``data/setup_context.py``). Reads the
        baseline from ``_current_setup_dict()`` and event/strategy keys from the
        other context helpers. Never raises — returns an EMPTY-source context on
        failure. Legacy config/DB setup storage is unchanged.
        """
        try:
            from data.setup_context import build_setup_context
            ev = self._build_event_context() if hasattr(self, "_build_event_context") else None
            strat_snap = None
            try:
                from data.strategy_context import (
                    build_strategy_context, build_strategy_prompt_snapshot,
                )
                sc = build_strategy_context(
                    strategy=self._config.get("strategy", {}), event_context=ev)
                strat_snap = build_strategy_prompt_snapshot(sc, ev)
            except Exception:  # pragma: no cover - defensive
                strat_snap = None
            return build_setup_context(
                setup=self._current_setup_dict(),
                recommendation=recommendation,
                event_context=ev,
                strategy_snapshot=strat_snap,
                diagnosis=diagnosis,
            )
        except Exception:  # pragma: no cover - defensive; must never break the UI
            from data.setup_context import empty_setup_context
            return empty_setup_context()

    def _build_setup_ai_snapshot(self):
        """Frozen AI-input snapshot for the setup AI paths.

        AI Snapshot Migration: freezes the event/track fields the Build-Setup
        and Analyse-Setup calls need (owners: EventContext race rules,
        StrategyContext pit loss, TrackContext identity, SetupContext via the
        last captured setup context) instead of live config["strategy"] reads.
        Byte-identical to the legacy expressions when the stores are in sync
        (proven by tests/test_ai_context_snapshot.py). Never raises; falls back
        to exact legacy expressions when no event context exists.
        OFR-2: session_type is passed so SetupAISnapshot.discipline is real.
        """
        # OFR-2: read session_type defensively — combo may not exist yet.
        _stype = self._setup_type.currentText() if hasattr(self, "_setup_type") else None
        try:
            from data.ai_context_snapshot import build_setup_ai_snapshot
            ev = self._build_event_context() if hasattr(self, "_build_event_context") else None
            sc = self._build_strategy_context() if hasattr(self, "_build_strategy_context") else None
            tc = self._build_track_context() if hasattr(self, "_build_track_context") else None
            setup_snap = None
            try:
                last = getattr(self, "_last_setup_context", None)
                if last is not None:
                    from data.setup_context import build_setup_prompt_snapshot
                    setup_snap = build_setup_prompt_snapshot(last)
            except Exception:
                setup_snap = None
            return build_setup_ai_snapshot(
                event_context=ev, strategy_context=sc,
                setup_snapshot=setup_snap, track_context=tc,
                legacy_strategy=self._config.get("strategy", {}),
                session_type=_stype)
        except Exception:  # pragma: no cover - defensive; must never break AI calls
            from data.ai_context_snapshot import build_setup_ai_snapshot
            _legacy = self._config.get("strategy", {}) if hasattr(self, "_config") else None
            return build_setup_ai_snapshot(legacy_strategy=_legacy, session_type=_stype)

    def _setup_type_prefix(self) -> str:
        """'Q' for a qualifying setup, 'R' for a race setup.

        State Consolidation 3: setup purpose classification is owned by
        SetupContext — derive it via the canonical ``normalise_purpose`` rather
        than an ad-hoc substring test (behaviour-preserving: "qual" → Q, else R).

        After the side-by-side refactor: reads self._setup_type.currentText() so
        that the tab-level "Live Session Mode" combo (and test stubs that set it)
        still drive the prefix.  When the Race form is active (mixin default),
        this returns "R"; when a stub sets it to "Qualifying Setup" the tests
        still get "Q" as expected.
        """
        from data.setup_context import normalise_purpose, SetupPurpose
        purpose = normalise_purpose(self._setup_type.currentText())
        return "Q" if purpose == SetupPurpose.QUALIFYING else "R"

    def _generate_setup_name(self, prefix: str | None = None) -> str | None:
        """Build '<Q|R> <event name> <number>' for the active event, or None if no event.

        ``prefix`` defaults to ``_setup_type_prefix()`` (reads the tab-level combo,
        so test stubs that set ``self._setup_type`` keep working).  Callers that
        want the prefix fixed to a specific form purpose pass it explicitly.
        """
        from ui.setup_name_helper import build_setup_name, next_setup_number
        event_name = ""
        if hasattr(self, "_active_event"):
            event_name = (self._active_event() or {}).get("name", "") or ""
        if not event_name:
            return None
        _prefix = prefix if prefix is not None else self._setup_type_prefix()
        n = next_setup_number(self._saved_setups, _prefix, event_name)
        return build_setup_name(_prefix, event_name, n)

    def _prefill_setup_label(self) -> None:
        """Pre-fill the editable setup-label field with the auto-generated name.

        Fires when the active event changes.  Uses the Race form's purpose prefix
        ("R") so the Race panel label matches correctly regardless of the Live
        Session Mode combo state.  No-op when there is no active event.
        """
        _prefix = (
            self._race_form.purpose_prefix()
            if hasattr(self, "_race_form")
            else self._setup_type_prefix()
        )
        name = self._generate_setup_name(prefix=_prefix)
        if name:
            self._setup_label.setText(name)
        # Also prefill the Qualifying form label
        if hasattr(self, "_qual_form"):
            _q_prefix = self._qual_form.purpose_prefix()
            _q_name = self._generate_setup_name(prefix=_q_prefix)
            if _q_name:
                self._qual_form._setup_label.setText(_q_name)

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
        # Side-by-side refactor: the Race form's mixin save path always uses "R"
        # prefix.  _setup_type_prefix() now reads from the Live Session Mode
        # toggle (tab-level combo) which is independent of the form purpose.
        # Use the Race form's purpose_prefix() directly so the label is correct.
        _save_prefix = (
            self._race_form.purpose_prefix()
            if hasattr(self, "_race_form")
            else self._setup_type_prefix()
        )
        self._setup_label.setText(
            resolve_save_name(
                self._setup_label.text(),
                _save_prefix,
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
            # Phase 5: event id from the canonical EventContext (DB-first;
            # byte-identical in sync — the fan-out stored the same DB id).
            _event_id = int(self._build_event_context().event_id or 0)
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

    def _after_setup_load(self) -> None:
        """Refresh the Home Setup card after a setup is loaded into a form.

        Loading only filled the form widgets; unlike Save and AI-apply it never
        rebuilt the canonical SetupContext (`_last_setup_context`) or refreshed
        Home, so the Home 'Setup Brain' card stayed stale after a load.
        """
        try:
            self._last_setup_context = self._build_setup_context()
        except Exception:
            pass
        if hasattr(self, "_home_refresh_if_visible"):
            self._home_refresh_if_visible()

    def _setup_load_selected(self) -> None:
        idx = self._setup_load_combo.currentIndex()
        # index 0 is the placeholder; real setups start at index 1
        real_idx = idx - 1
        if 0 <= real_idx < len(self._saved_setups):
            self._fill_setup_fields(self._saved_setups[real_idx])
            self._after_setup_load()

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

        # AI Snapshot Migration: event tuning-legality + mandatory compounds
        # come from a frozen snapshot (owner: EventContext) instead of live
        # config["strategy"] reads. Byte-identical when the stores are in sync
        # (tests/test_ai_context_snapshot.py).
        _ai_snap = self._build_setup_ai_snapshot()
        _allowed  = _ai_snap.allowed_tuning_or_none()
        _locked   = _ai_snap.tuning_locked
        _compound = _ai_snap.mandatory_compounds_str

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
        # Per-form routing: if a SetupFormWidget is in position 4, use its result
        # text and buttons instead of the (Race-aliased) self attrs.
        _form = result[4] if len(result) > 4 else None
        _result_text   = _form._setup_result_text   if _form else self._setup_result_text
        _btn_analyse   = _form._btn_analyse_setup   if _form else getattr(self, "_btn_analyse_setup", None)
        _btn_apply     = _form._btn_apply_ai_setup  if _form else getattr(self, "_btn_apply_ai_setup", None)

        if _btn_analyse:
            _btn_analyse.setEnabled(True)

        if status == "error":
            _result_text.setHtml(
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

        # Rating/applied labels are no longer captured here — the rate control
        # moved to the Practice Review per-run feedback and "applied" is derived
        # from lap setup tags. History entries save without subjective labels.

        # Try to parse structured JSON from the advisor.  A truncated response
        # (the model hit the token cap mid-JSON) or a non-JSON reply must NEVER
        # dump raw text at the user — guard for completeness first, then show a
        # clear, actionable message instead of leaking JSON.
        try:
            if not _setup_response_looks_complete(payload):
                raise _json.JSONDecodeError(
                    "response appears truncated or non-JSON", (payload or "").strip() or " ", 0)
            data = json.loads(payload)
            analysis = str(data.get("analysis", ""))
            changes: list = data.get("changes", [])
            setup_fields: dict = data.get("setup_fields", {})
            _validation_errors: list = data.get("validation_errors", [])
            _eng_validation_failed: bool = bool(data.get("engineering_validation_failed", False))
            _eng_validation_errors: list = data.get("engineering_validation_errors", [])
            _diagnosis: dict = data.get("diagnosis") or {}
        except (_json.JSONDecodeError, AttributeError):
            # Friendly fallback — never surface raw JSON to the user.
            _err_html = (
                "<div style='background:#2A1A1A; border:1px solid #C0453B; "
                "border-radius:4px; padding:10px; color:#E8A9A3;'>"
                "<b style='color:#E86A5E;'>Couldn't read the setup analysis</b><br>"
                "The AI response looks incomplete — it was likely cut off. "
                "Click <b>Analyse &amp; Get Setup Fix</b> again to retry. "
                "If it keeps happening, shorten the driver-feeling text and try once more."
                "</div>"
            )
            _result_text.setHtml(_violation_banner + _err_html)
            if _btn_apply:
                _btn_apply.setVisible(False)
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

        # Store parsed fields so the apply button can use them.
        # Route to the per-form storage when a form widget is in the result tuple.
        _parsed_ai_fields = {
            k: v for k, v in setup_fields.items()
            if isinstance(v, (int, float))
        }
        if _form is not None:
            _form.last_ai_fields = _parsed_ai_fields
        else:
            self._last_setup_ai_fields = _parsed_ai_fields
        if _btn_apply:
            _btn_apply.setVisible(bool(_parsed_ai_fields))

        # State Consolidation 3: capture the canonical SetupContext for this
        # displayed recommendation, keyed to EventContext.change_hash and the
        # StrategyPromptSnapshot.snapshot_id it was built against, so a later
        # sprint can detect a stale setup. Read-only and additive — it does not
        # alter the displayed HTML, the history save, or the apply button.
        try:
            self._last_setup_context = self._build_setup_context(
                recommendation={
                    "analysis": analysis,
                    "changes": changes,
                    "setup_fields": setup_fields,
                    "validation_errors": _validation_errors,
                    "primary_issue": data.get("primary_issue", ""),
                    "confidence": data.get("confidence", ""),
                },
                diagnosis=_diagnosis,
            )
        except Exception:  # pragma: no cover - defensive; never break the display
            self._last_setup_context = None

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

        _result_text.setHtml(html)

        # Save to history
        config_id = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
        car  = self._config.get("strategy", {}).get("car", "")
        track = self._config.get("strategy", {}).get("track", "")
        if config_id:
            try:
                from data.setup_history import save_entry
                # Subjective labels (liked/hated/applied) are no longer written
                # from here — that signal now comes from the Practice Review
                # per-run rating. Still record the feeling text for context.
                save_entry(config_id, car, track, {
                    "type": entry_type,
                    "feeling": feeling or "",
                    "analysis": analysis,
                    "changes": changes,
                }, driver_feedback=feeling or "")
            except Exception as _e:
                print(f"[SetupHistory] save failed: {_e}")

        # Home Dashboard: a new setup context was captured above — keep an open
        # Home tab current (display-only; no-op when Home is not visible).
        if hasattr(self, "_home_refresh_if_visible"):
            self._home_refresh_if_visible()

    def _apply_and_save_ai_setup(self) -> None:
        """Apply AI-recommended setup_fields to the form and save as a new entry."""
        if not getattr(self, "_last_setup_ai_fields", {}):
            return
        current = self._current_setup_dict()
        current.update(self._last_setup_ai_fields)
        self._fill_setup_fields(current)
        # Keep the structured R/Q setup name (e.g. "R NGR Porsche Cup Rd7 2")
        # instead of overwriting it with "AI Fix N" — on Save, resolve_save_name
        # advances it to the next numbered attempt for the event, so the naming
        # convention is preserved. The AI-fix linkage for learning is recorded in
        # the DB (apply_recommendation_for_car_track) and setup_history, not here.
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

    def _resolve_recent_laps(self, car_id: int, track: str) -> list:
        """Return per-lap telemetry rows for the most recent session of car+track.

        OFR-2: feeds per_lap_telemetry into build_car_setup so the discipline
        block in the setup-build prompt is real.  Always returns a list (empty
        on any error, missing DB, zero car_id, or no previous session).
        Fetches on the UI thread so the worker closure captures a plain list.
        """
        # OFR-2: guard — no db, no car, no track → nothing to resolve.
        if not (self._db and car_id > 0 and track):
            return []
        try:
            sid = self._db.get_previous_session_id(car_id, track, 99_999_999)
            if not sid:
                return []
            return self._db.get_session_laps(
                sid, exclude_pit=True, exclude_out=True, limit=5, latest=True
            )
        except Exception as _ofr2_err:  # pragma: no cover - defensive
            print(f"[OFR-2] _resolve_recent_laps failed: {_ofr2_err}")
            return []

    def _run_build_setup(self) -> None:
        """Ask AI to generate a complete from-scratch car setup and auto-fill all fields."""
        import threading as _threading
        from strategy.ai_planner import build_car_setup

        api_key = self._ai_api_key.text().strip()
        if not api_key:
            self._build_setup_result.setPlainText("No API key configured. Add your Anthropic API key in the AI Race Analysis section.")
            self._build_setup_result.setVisible(True)
            return

        # AI Snapshot Migration: all event/track fields for build_car_setup come
        # from one frozen snapshot (owners: EventContext race rules,
        # StrategyContext pit loss, TrackContext identity) instead of scattered
        # live config["strategy"] reads. Byte-identical when the stores are in
        # sync (tests/test_ai_context_snapshot.py); the build-setup legacy
        # defaults (refuel/pit-loss 0.0) are preserved exactly.
        _ai_snap = self._build_setup_ai_snapshot()
        car          = _ai_snap.car
        track        = _ai_snap.track
        session_type = self._setup_type.currentText()
        race_laps    = _ai_snap.race_laps
        min_weight   = self._setup_min_weight.value()
        max_power    = self._setup_max_power.value()
        actual_bhp   = self._setup_actual_bhp.value() if hasattr(self, "_setup_actual_bhp") else 0.0
        num_gears    = self._setup_num_gears.value() if hasattr(self, "_setup_num_gears") else 0
        drivetrain   = self._setup_drivetrain.currentData() if hasattr(self, "_setup_drivetrain") else ""
        bop_data     = self._get_bop_data_for_car()
        _duration_mins   = _ai_snap.duration_mins
        _mandatory_stops = _ai_snap.mandatory_stops
        _refuel_rate_lps = _ai_snap.refuel_rate_lps
        _pit_loss_secs   = _ai_snap.pit_loss_secs
        _re_brief        = self._re_brief_input.toPlainText().strip() if hasattr(self, "_re_brief_input") else ""
        _, _car_specs = self._load_car_specs_for_current()
        _allowed_tuning = _ai_snap.allowed_tuning_or_none()
        _tuning_locked  = _ai_snap.tuning_locked
        _tyre_wear_mult  = _ai_snap.tyre_wear_multiplier
        _fuel_mult       = _ai_snap.fuel_multiplier
        _avail_tyres     = _ai_snap.avail_tyres_list()
        _req_tyres       = _ai_snap.required_tyres_list()
        _race_type_build = _ai_snap.race_type
        _track_loc_id    = _ai_snap.track_location_id
        _layout_id_build = _ai_snap.layout_id
        _last_lap = self._recorder.last_lap() if self._recorder else None
        _gearbox_analysis = _last_lap.gearbox_analysis if _last_lap else {}
        _car_id_build = self._db.get_car_id(car) if self._db and car and car != "Unknown" else 0
        self._car_id_build = _car_id_build

        # OFR-2: resolve most-recent-session laps on the UI thread so the worker
        # closure captures a plain list (no DB access inside the thread needed).
        _ofr2_laps = self._resolve_recent_laps(_car_id_build, track)

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
                                      race_engineer_brief=_re_brief,
                                      per_lap_telemetry=_ofr2_laps or None)
                from strategy._rec_parser import parse_recommendations_from_response as _parse_recs
                try:
                    _ai_id_build = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id_build = None
                # AI Snapshot Migration: recommendation metadata uses the SAME
                # frozen track identity the prompt was built with — no re-read
                # of config["strategy"] inside the worker thread (which could
                # have changed mid-flight).
                _build_track = track
                _build_layout = _layout_id_build
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
        status, payload, *rest = result
        session_type = rest[0] if rest else "Race"
        # Per-form routing: position 3 (rest[1]) may hold a SetupFormWidget
        _form = rest[1] if len(rest) > 1 and hasattr(rest[1], "purpose") else None
        _btn_build    = _form._btn_build_setup    if _form else self._btn_build_setup
        _build_result = _form._build_setup_result if _form else self._build_setup_result
        _btn_build.setEnabled(True)
        _btn_build.setText("Build Setup with AI")
        if status == "err":
            _build_result.setPlainText(f"Build Setup failed: {payload}")
            return
        if _form is not None:
            self._apply_build_setup_result_for_form(payload, session_type, _form)
        else:
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
        config_id = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
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

    def _apply_build_setup_result_for_form(
        self, rec, session_type: str, form: "SetupFormWidget"
    ) -> None:
        """Fill a specific form's fields from an AI CarSetupRecommendation.

        Mirrors ``_apply_build_setup_result`` but targets ``form``'s widgets
        instead of the aliased ``self._setup_*`` attrs (which always point to
        the Race form).  Used when the Qualifying panel's Build button fires.
        """
        from strategy.setup_ranges import resolve_ranges
        _car_name = (self._build_setup_ai_snapshot().car or "") if hasattr(self, "_build_setup_ai_snapshot") else ""
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

        _set_int(form._setup_rh_f,       "ride_height_front",  rec.ride_height_front)
        _set_int(form._setup_rh_r,       "ride_height_rear",   rec.ride_height_rear)
        _set_dbl(form._setup_spr_f,      "springs_front",      rec.springs_front)
        _set_dbl(form._setup_spr_r,      "springs_rear",       rec.springs_rear)
        _set_int(form._setup_dmp_f_comp, "dampers_front_comp", rec.dampers_front_comp)
        _set_int(form._setup_dmp_f_ext,  "dampers_front_ext",  rec.dampers_front_ext)
        _set_int(form._setup_dmp_r_comp, "dampers_rear_comp",  rec.dampers_rear_comp)
        _set_int(form._setup_dmp_r_ext,  "dampers_rear_ext",   rec.dampers_rear_ext)
        _set_int(form._setup_arb_f,      "arb_front",          rec.arb_front)
        _set_int(form._setup_arb_r,      "arb_rear",           rec.arb_rear)
        _set_dbl(form._setup_cam_f,      "camber_front",       rec.camber_front)
        _set_dbl(form._setup_cam_r,      "camber_rear",        rec.camber_rear)
        _set_dbl(form._setup_toe_f,      "toe_front",          rec.toe_front)
        _set_dbl(form._setup_toe_r,      "toe_rear",           rec.toe_rear)
        _set_int(form._setup_aero_f,     "aero_front",         rec.aero_front)
        _set_int(form._setup_aero_r,     "aero_rear",          rec.aero_rear)
        _set_int(form._setup_lsd_i,      "lsd_initial",        rec.lsd_initial)
        _set_int(form._setup_lsd_a,      "lsd_accel",          rec.lsd_accel)
        _set_int(form._setup_lsd_d,      "lsd_decel",          rec.lsd_decel)
        _set_int(form._setup_lsd_f_i,    "lsd_front_initial",  rec.lsd_front_initial)
        _set_int(form._setup_lsd_f_a,    "lsd_front_accel",    rec.lsd_front_accel)
        _set_int(form._setup_lsd_f_d,    "lsd_front_decel",    rec.lsd_front_decel)
        _set_int(form._setup_bb,         "brake_bias",         rec.brake_bias)
        _set_dbl(form._setup_ballast_kg, "ballast_kg",         rec.ballast_kg)
        _set_int(form._setup_ballast_pos,"ballast_position",   rec.ballast_position)
        _set_dbl(form._setup_power_rest, "power_restrictor",   rec.power_restrictor)
        if hasattr(rec, "ecu_recommendation") and rec.ecu_recommendation:
            form._lbl_ecu_rec.setText(rec.ecu_recommendation)
        else:
            form._lbl_ecu_rec.setText("—")
        if rec.final_drive > 0.0:
            form._spin_final_drive.setValue(rec.final_drive)
        for i, spin in enumerate(form._gear_ratio_spins):
            spin.setValue(rec.gear_ratios[i] if i < len(rec.gear_ratios) else 0.0)
        if rec.transmission_max_speed_kmh > 0:
            form._spin_top_speed.setValue(rec.transmission_max_speed_kmh)
        form._build_setup_result.setHtml(
            f"<b>AI Setup Reasoning ({form.purpose})</b><br>"
            f"<p style='line-height:1.5;'>{rec.reasoning}</p>"
        )
        form._build_setup_result.setVisible(True)

    def _sync_qual_form_ui_state(self) -> None:
        """Sync the Qualifying form's BOP/locked/permissions state from the Race form.

        Called from ``_sync_setup_builder_from_event`` after the Race-form state
        is updated via the aliased self attrs.  Ensures the Qualifying panel's
        UI widgets reflect the same event constraints.
        """
        if not hasattr(self, "_qual_form"):
            return
        qf = self._qual_form
        rf = self._race_form
        # BOP row visibility (controlled by _on_bop_toggled which only updates
        # the aliased Race-form widgets through self)
        for _src, _dst in (
            ("_lbl_bop_info",       "_lbl_bop_info"),
            ("_btn_bop_edit",       "_btn_bop_edit"),
            ("_btn_bop_reload",     "_btn_bop_reload"),
            ("_bop_info_row_label", "_bop_info_row_label"),
        ):
            src_w = getattr(rf, _src, None)
            dst_w = getattr(qf, _dst, None)
            if src_w is not None and dst_w is not None:
                dst_w.setVisible(src_w.isVisible())
                if hasattr(src_w, "text"):
                    dst_w.setText(src_w.text())
        # Locked banner
        if hasattr(rf, "_setup_locked_banner") and hasattr(qf, "_setup_locked_banner"):
            qf._setup_locked_banner.setText(rf._setup_locked_banner.text())
            if rf._setup_locked_banner.isVisible():
                qf._setup_locked_banner.show()
            else:
                qf._setup_locked_banner.hide()

    def _sync_setup_builder_from_event(self) -> None:
        try:
            evt = self._active_event()
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
            # Legacy Fan-Out Removal Phase 2: the READOUT labels below reflect
            # the canonical EventContext (DB-event-first — consistent with what
            # the strategy/setup AI already consumes since the AI Snapshot
            # Migration). int() preserves the integer QSpinBox formatting so the
            # labels are byte-identical when the DB event and the
            # config["strategy"] fan-out are in sync. Phase 3 moved the
            # FUNCTIONAL gating (BoP toggle + setup permissions) onto
            # EventContext; Phase 4 moved the remaining labels (refuel/req/
            # avail) and the car spinbox rebind — this method no longer reads
            # config["strategy"] at all.
            ev_ctx = self._build_event_context()
            name  = evt.get("name", "?")
            track = ev_ctx.track or "?"
            car   = ev_ctx.car or "—"
            tw    = int(ev_ctx.tyre_wear_multiplier)
            fm    = int(ev_ctx.fuel_multiplier)
            rt    = ev_ctx.race_type
            laps  = ev_ctx.laps
            dur   = ev_ctx.race_duration_minutes
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
            # Phase 4: the last three readout labels (refuel/required/available
            # tyres) join the rest on EventContext — int() keeps the integer
            # QSpinBox refuel formatting; the tyre labels join the same compound
            # CODES the fan-out carried. Byte-identical in sync.
            if hasattr(self, "_lbl_rc_refuel_rate"):
                self._lbl_rc_refuel_rate.setText(f"{int(ev_ctx.refuel_rate_lps)} L/s")
                self._lbl_rc_refuel_rate.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_req_tyre"):
                _rq_str = ", ".join(ev_ctx.required_tyres)
                self._lbl_rc_req_tyre.setText(_rq_str or "—")
                self._lbl_rc_req_tyre.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_avail_tyres"):
                _at_str = ", ".join(ev_ctx.available_tyres)
                self._lbl_rc_avail_tyres.setText(_at_str or "—")
                self._lbl_rc_avail_tyres.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_mand_pits"):
                self._lbl_rc_mand_pits.setText(str(ev_ctx.mandatory_stops))
                self._lbl_rc_mand_pits.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_weather"):
                self._lbl_rc_weather.setText(ev_ctx.weather or "—")
                self._lbl_rc_weather.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_damage"):
                self._lbl_rc_damage.setText(ev_ctx.damage or "—")
                self._lbl_rc_damage.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_bop"):
                self._lbl_rc_bop.setText("Yes" if ev_ctx.bop_enabled else "No")
                self._lbl_rc_bop.setStyleSheet(_green)
            if hasattr(self, "_lbl_rc_tuning"):
                self._lbl_rc_tuning.setText("Allowed" if ev_ctx.tuning_allowed else "Not Allowed")
                self._lbl_rc_tuning.setStyleSheet(_green)
            # Legacy Fan-Out Removal Phase 3 (functional gating): the BoP toggle
            # and setup-permission gating now read the canonical EventContext
            # (DB-event-first — consistent with the AI inputs, the Phase 2 labels,
            # and the DEF-P3-012 validation). Byte-identical when the DB event and
            # the config["strategy"] fan-out are in sync; when an event was edited
            # + Saved but not re-activated, the editable fields now follow the
            # fresh DB truth (the intended, signed-off behaviour change).
            _bop    = ev_ctx.bop_enabled
            _tuning = ev_ctx.tuning_allowed
            _cats   = list(ev_ctx.allowed_tuning_categories)
            self._on_bop_toggled(_bop)
            self._apply_setup_permissions(_bop, _tuning, _cats)
            self._refresh_live_tyre_label()
            # Re-bound spinboxes for the new car and load race engineer brief.
            # Phase 4: car via EventContext (strategy-first there and events
            # never store a car — byte-identical, proven in Phase 1 tests).
            self._rebound_setup_spinboxes(ev_ctx.car or "")
            self._load_re_brief_from_active_event()
            # Sync the Qualifying form's BOP/locked state from the Race-aliased widgets
            self._sync_qual_form_ui_state()
        except Exception:
            pass

    def _build_setup_builder_tab(self) -> QWidget:
        # Outer container: VBox holding the header strip (scrollable) + the
        # side-by-side form panel (expands to fill the tab, scrolls per-form).
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setSpacing(6)
        tab_layout.setContentsMargins(6, 6, 6, 6)

        # ── Header strip (event ctx + race conditions + history) — scrollable ──
        header_scroll = QScrollArea()
        header_scroll.setWidgetResizable(True)
        header_scroll.setMaximumHeight(320)
        header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header_container = QWidget()
        layout = QVBoxLayout(header_container)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

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
        layout.addStretch()

        header_scroll.setWidget(header_container)
        tab_layout.addWidget(header_scroll, 0)  # fixed height

        # ── Side-by-side setup panel — expands to fill remaining space ─────────
        setup_panel = self._build_car_setup_group()
        tab_layout.addWidget(setup_panel, 1)  # stretch factor 1

        return tab_widget

    def _refresh_setup_history_combo(self) -> None:
        try:
            config_id    = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
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
            config_id    = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
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
