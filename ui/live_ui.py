"""Live Race Engineer tab — mixin for MainWindow (decomposition slice 5, final).

Extracted from ui/dashboard.py: the Live tab builder (race / practice / qualifying
panels), the live-telemetry display refreshers, live-strategy combo, and the
read-only live-replan / track-progress resolvers. These do NOT touch
config["strategy"]; the one pinned method that does (_live_init_from_plan) stays
on MainWindow and resolves here via the MRO. Does not import ui.dashboard (acyclic).
"""
from __future__ import annotations

import time  # noqa: F401

from PyQt6.QtCore import Qt  # noqa: F401
from PyQt6.QtGui import QFont  # noqa: F401
from telemetry.packet import GT7Packet, format_laptime_display  # noqa: F401
from telemetry.state import SessionType, TyreThresholds  # noqa: F401
from ui.widgets import TyreWidget, FuelBar, BigValueLabel  # noqa: F401
from PyQt6.QtWidgets import (  # noqa: F401
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QStackedWidget, QAbstractItemView,
)

# Module-level display constants — now sourced from the NGR design system so
# these surfaces stay consistent with the global theme (ui/ngr_theme.py) instead
# of drifting on ad-hoc hex.
from ui import ngr_theme as _ngr
_DARK_CARD = _ngr.CARBON_RAISED   # was "#2A2A2A" — carbon card surface
_TEXT = _ngr.TEXT                 # was "#E0E0E0" — body text
_ACCENT = _ngr.NGR_GREEN          # was "#2EA043" — NGR neon-green accent


class LiveMixin:
    """Live Race Engineer tab construction + telemetry display for MainWindow."""

    def _build_live_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(self._tab_intro_header(
            "Live Race Engineer",
            "Real-time coaching during a session — fuel, tyres, pit windows and "
            "voice alerts. Next: pick Practice or Race mode and start driving; "
            "alerts and push-to-talk queries run automatically."))

        # UAT #6 Phase 2A: "refined track model available" notice — click to review
        # in Track Modelling. Hidden until a refinement produces an improving candidate.
        self._live_refine_banner = QPushButton("")
        self._live_refine_banner.setStyleSheet(
            "QPushButton { background: #1A2A1A; border: 1px solid #4CAF50; "
            "border-radius: 4px; padding: 6px 10px; color: #AAE4AA; font-size: 12px; "
            "text-align: left; }"
            "QPushButton:hover { background: #22371F; }")
        self._live_refine_banner.setCursor(Qt.CursorShape.PointingHandCursor)
        self._live_refine_banner.clicked.connect(self._on_refine_banner_clicked)
        self._live_refine_banner.setVisible(False)
        root.addWidget(self._live_refine_banner)

        # Row 1: Race info bar
        info_row = QHBoxLayout()
        self._lbl_speed    = BigValueLabel("—",  "km/h", 28)
        self._lbl_gear     = BigValueLabel("—",  "",     36)
        self._lbl_position = BigValueLabel("—",  "",     22)
        self._lbl_countdown= BigValueLabel("—",  "",     18)

        for lbl in (self._lbl_speed, self._lbl_gear, self._lbl_position, self._lbl_countdown):
            lbl.setStyleSheet(f"color: {_TEXT}; background: {_DARK_CARD}; border-radius: 6px; padding: 4px 10px;")

        self._lbl_gear.setStyleSheet(
            f"color: #F5C542; background: {_DARK_CARD}; border-radius: 6px; padding: 4px 10px;")

        self._lbl_session = BigValueLabel("—", "", 14)
        self._lbl_session.setStyleSheet(
            f"color: #AAE4AA; background: {_DARK_CARD}; border-radius: 6px; padding: 4px 10px;")

        info_row.addWidget(QLabel("Speed:", styleSheet=f"color:{_TEXT}"))
        info_row.addWidget(self._lbl_speed)
        info_row.addWidget(QLabel("Gear:", styleSheet=f"color:{_TEXT}"))
        info_row.addWidget(self._lbl_gear)
        info_row.addWidget(QLabel("Position:", styleSheet=f"color:{_TEXT}"))
        info_row.addWidget(self._lbl_position)
        info_row.addWidget(QLabel("Remaining:", styleSheet=f"color:{_TEXT}"))
        info_row.addWidget(self._lbl_countdown)
        info_row.addWidget(QLabel("Session:", styleSheet=f"color:{_TEXT}"))
        info_row.addWidget(self._lbl_session)

        self._combo_live_mode = QComboBox()
        self._combo_live_mode.addItems(["Race", "Practice", "Qualifying"])
        self._combo_live_mode.setStyleSheet(
            f"QComboBox {{ background:{_DARK_CARD}; color:{_TEXT}; border:1px solid #555;"
            f" border-radius:4px; padding:3px 8px; min-width:90px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
            f"QComboBox QAbstractItemView {{ background:{_DARK_CARD}; color:{_TEXT}; }}"
        )
        self._combo_live_mode.currentTextChanged.connect(self._on_live_mode_changed)
        info_row.addWidget(QLabel("Mode:", styleSheet=f"color:{_TEXT}"))
        info_row.addWidget(self._combo_live_mode)

        self._live_ptt_status_lbl = QLabel("RADIO READY")
        self._live_ptt_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._live_ptt_status_lbl.setStyleSheet(
            "color: #2EA043; background: #0D1B10; border: 1px solid #2EA043; "
            "border-radius: 3px; padding: 3px 10px; font-size: 11px; font-weight: bold; "
            "letter-spacing: 1px;"
        )
        info_row.addWidget(self._live_ptt_status_lbl)
        info_row.addStretch()

        self._btn_reset = QPushButton("Reset Session")
        self._btn_reset.setStyleSheet(
            "QPushButton { background: #5A3A00; color: #FFB347; border: 1px solid #8B6000;"
            " border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
            "QPushButton:hover { background: #7A5000; }"
            "QPushButton:pressed { background: #3A2000; }"
        )
        self._btn_reset.setToolTip(
            "Reset race tracking state.\n"
            "Lap Data / Excel history is preserved."
        )
        self._btn_reset.clicked.connect(self._on_reset_clicked)
        info_row.addWidget(self._btn_reset)

        root.addLayout(info_row)

        # Row 2: Tyre grid + Lap info side-by-side
        mid_row = QHBoxLayout()

        tyre_grid = QGridLayout()
        tyre_grid.setSpacing(6)
        self._tyre_widgets: dict[str, TyreWidget] = {
            "fl": TyreWidget("FL"), "fr": TyreWidget("FR"),
            "rl": TyreWidget("RL"), "rr": TyreWidget("RR"),
        }
        tyre_grid.addWidget(self._tyre_widgets["fl"], 0, 0)
        tyre_grid.addWidget(self._tyre_widgets["fr"], 0, 1)
        tyre_grid.addWidget(self._tyre_widgets["rl"], 1, 0)
        tyre_grid.addWidget(self._tyre_widgets["rr"], 1, 1)

        self._lbl_live_tyre_compound = QLabel("Current Tyre: Not Set")
        self._lbl_live_tyre_compound.setStyleSheet(
            f"color: #AAE4AA; font-size: 11px; font-weight: bold; padding-bottom: 2px;")
        _tyre_vbox = QVBoxLayout()
        _tyre_vbox.setSpacing(4)
        _tyre_vbox.setContentsMargins(0, 0, 0, 0)
        _tyre_vbox.addWidget(self._lbl_live_tyre_compound)
        _tyre_vbox.addLayout(tyre_grid)

        tyre_box = QGroupBox("Tyres")
        tyre_box.setStyleSheet(self._group_style())
        tyre_box.setLayout(_tyre_vbox)

        lap_box = QGroupBox("Lap Times")
        lap_box.setStyleSheet(self._group_style())
        lap_layout = QFormLayout(lap_box)
        lap_layout.setSpacing(8)

        self._lbl_last_lap  = QLabel("--:--.---")
        self._lbl_best_lap  = QLabel("--:--.---")
        self._lbl_delta     = QLabel("—")
        self._lbl_current_lap = QLabel("—")
        self._lbl_rpm       = QLabel("—")

        for lbl in (self._lbl_last_lap, self._lbl_best_lap, self._lbl_delta,
                    self._lbl_current_lap, self._lbl_rpm):
            lbl.setFont(QFont("Segoe UI", 13))
            lbl.setStyleSheet(f"color: {_TEXT};")

        self._lbl_last_lap.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self._lbl_best_lap.setStyleSheet(f"color: {_ACCENT};")

        lap_layout.addRow("Last Lap:", self._lbl_last_lap)
        lap_layout.addRow("Best Lap:", self._lbl_best_lap)
        lap_layout.addRow("Delta:",   self._lbl_delta)
        lap_layout.addRow("Lap #:",   self._lbl_current_lap)
        lap_layout.addRow("RPM:",     self._lbl_rpm)

        mid_row.addWidget(tyre_box)
        mid_row.addWidget(lap_box)
        root.addLayout(mid_row)

        # Row 3: Fuel bar
        fuel_box = QGroupBox("Fuel")
        fuel_box.setStyleSheet(self._group_style())
        fuel_layout = QVBoxLayout(fuel_box)
        self._fuel_bar = FuelBar()
        fuel_layout.addWidget(self._fuel_bar)
        root.addWidget(fuel_box)

        # Row 3b: Shift Beep controls — shared across all mode panels
        _sb_cfg = self._config.get("shift_beep", {})
        shift_beep_box = QGroupBox("Shift Beep")
        shift_beep_box.setStyleSheet(self._group_style())
        shift_beep_layout = QHBoxLayout(shift_beep_box)
        shift_beep_layout.setSpacing(12)

        self._chk_shift_beep_enabled = QCheckBox("Enable shift beep")
        self._chk_shift_beep_enabled.setChecked(bool(_sb_cfg.get("enabled", True)))
        self._chk_shift_beep_enabled.setStyleSheet(f"color: {_TEXT};")
        shift_beep_layout.addWidget(self._chk_shift_beep_enabled)

        shift_beep_layout.addWidget(QLabel("Shift RPM — Qualifying:", styleSheet=f"color:{_TEXT};"))
        self._spin_live_shift_rpm_qual = QSpinBox()
        self._spin_live_shift_rpm_qual.setRange(0, 20000)
        self._spin_live_shift_rpm_qual.setSingleStep(100)
        self._spin_live_shift_rpm_qual.setSuffix(" RPM")
        self._spin_live_shift_rpm_qual.setValue(int(_sb_cfg.get("qual_rpm", 7000)))
        shift_beep_layout.addWidget(self._spin_live_shift_rpm_qual)

        shift_beep_layout.addWidget(QLabel("Shift RPM — Race:", styleSheet=f"color:{_TEXT};"))
        self._spin_live_shift_rpm_race = QSpinBox()
        self._spin_live_shift_rpm_race.setRange(0, 20000)
        self._spin_live_shift_rpm_race.setSingleStep(100)
        self._spin_live_shift_rpm_race.setSuffix(" RPM")
        self._spin_live_shift_rpm_race.setValue(int(_sb_cfg.get("race_rpm", 6500)))
        shift_beep_layout.addWidget(self._spin_live_shift_rpm_race)

        shift_beep_layout.addStretch()
        root.addWidget(shift_beep_box)

        # Connect signals after both spinboxes exist
        self._chk_shift_beep_enabled.stateChanged.connect(self._on_shift_beep_setting_changed)
        self._spin_live_shift_rpm_qual.valueChanged.connect(self._on_shift_beep_setting_changed)
        self._spin_live_shift_rpm_race.valueChanged.connect(self._on_shift_beep_setting_changed)

        # Qualifying sector-tracking state (initialised before panels are built)
        self._qual_road_dist_max: float = 0.0
        self._qual_prev_rd: float = 0.0
        self._qual_tod_at_lap_start: int = 0
        self._qual_s1_done: bool = False
        self._qual_s2_done: bool = False

        # Row 4: Mode-specific panel (Race / Practice / Qualifying)
        self._live_mode_stack = QStackedWidget()
        self._live_mode_stack.addWidget(self._build_live_race_panel())       # 0
        self._live_mode_stack.addWidget(self._build_live_practice_panel())   # 1
        self._live_mode_stack.addWidget(self._build_live_qualifying_panel()) # 2
        root.addWidget(self._live_mode_stack)

        # Restore saved mode
        _saved_mode = self._config.get("live", {}).get("mode", "Race")
        _mode_idx = {"Race": 0, "Practice": 1, "Qualifying": 2}.get(_saved_mode, 0)
        self._combo_live_mode.setCurrentIndex(_mode_idx)

        return w

    def _build_live_race_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        strat_box = QGroupBox("Race Strategy")
        strat_box.setStyleSheet(self._group_style())
        strat_layout = QVBoxLayout(strat_box)

        sel_row = QHBoxLayout()
        sel_lbl = QLabel("Select:", styleSheet=f"color: {_TEXT};")
        sel_row.addWidget(sel_lbl)
        self._combo_live_strategy = QComboBox()
        self._combo_live_strategy.addItem("No Strategy (Fuel Only)")
        self._combo_live_strategy.setToolTip(
            "Choose a strategy from the last AI analysis, or run without one.\n"
            "Run Race Strategy Analysis on the Strategy tab to generate options."
        )
        sel_row.addWidget(self._combo_live_strategy, 1)
        self._btn_live_apply_strategy = QPushButton("Apply")
        self._btn_live_apply_strategy.setFixedHeight(26)
        self._btn_live_apply_strategy.setToolTip(
            "Load the selected strategy into the race engine.\n"
            "'No Strategy' clears the plan — only fuel tracking is active."
        )
        self._btn_live_apply_strategy.clicked.connect(self._live_apply_strategy)
        sel_row.addWidget(self._btn_live_apply_strategy)
        strat_layout.addLayout(sel_row)

        self._lbl_live_plan = QLabel(
            "No plan applied — run Race Strategy Analysis, then select and apply a strategy.")
        self._lbl_live_plan.setStyleSheet("color: #999; padding: 4px;")
        self._lbl_live_plan.setWordWrap(True)
        self._lbl_live_plan.setFont(QFont("Segoe UI", 11))
        strat_layout.addWidget(self._lbl_live_plan)
        layout.addWidget(strat_box)

        status_box = QGroupBox("Strategy Status")
        status_box.setStyleSheet(self._group_style())
        status_layout = QVBoxLayout(status_box)
        self._lbl_strategy_status = QLabel("No plan loaded")
        self._lbl_strategy_status.setStyleSheet(f"color: {_TEXT}; padding: 2px;")
        self._lbl_strategy_status.setWordWrap(True)
        self._lbl_strategy_status.setFont(QFont("Segoe UI", 10))
        status_layout.addWidget(self._lbl_strategy_status)
        self._lbl_grip_status = QLabel("")
        self._lbl_grip_status.setStyleSheet("color: #999; padding: 2px 4px; font-size: 10px;")
        self._lbl_grip_status.setWordWrap(True)
        status_layout.addWidget(self._lbl_grip_status)
        layout.addWidget(status_box)

        layout.addStretch()
        return w

    def _live_apply_strategy(self) -> None:
        """Apply the selected strategy from the Live tab combo to the race engine."""
        idx = self._combo_live_strategy.currentIndex()
        if idx == 0 or not self._strategy_options:
            self._strategy_reset_plan()
            self._update_live_plan([])
        else:
            opt_idx = idx - 1
            if opt_idx < len(self._strategy_options):
                self._apply_strategy_option(opt_idx)
                self._strategy_apply_plan()

    def _refresh_live_strategy_combo(self) -> None:
        """Rebuild the strategy selector on the Live tab after AI analysis."""
        if not hasattr(self, "_combo_live_strategy"):
            return
        current = self._combo_live_strategy.currentText()
        self._combo_live_strategy.blockSignals(True)
        self._combo_live_strategy.clear()
        self._combo_live_strategy.addItem("No Strategy (Fuel Only)")
        for i, opt in enumerate(self._strategy_options, 1):
            self._combo_live_strategy.addItem(f"Strategy {i}: {opt.name}")
        idx = self._combo_live_strategy.findText(current)
        self._combo_live_strategy.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_live_strategy.blockSignals(False)

    def _build_live_practice_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Declare which saved setup is on the car this stint. Carries into
        # Practice Review (editable there) and is passed to the AI with feedback.
        setup_box = QGroupBox("Setup Running This Stint")
        setup_box.setStyleSheet(self._group_style())
        setup_layout = QFormLayout(setup_box)
        setup_layout.setSpacing(6)
        self._live_running_setup_combo = QComboBox()
        self._live_running_setup_combo.setStyleSheet(
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; "
            "border-radius: 3px; padding: 2px 6px; }"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )
        self._live_running_setup_combo.setToolTip(
            "Manual override: tell the app which saved setup you're running this "
            "stint. Normally the Live baseline below (the setup you applied in "
            "game) is used automatically — only change this to override it.")
        self._live_running_setup_combo.currentTextChanged.connect(self._on_running_setup_changed)
        _lrs_lbl = QLabel("Override (manual):")
        _lrs_lbl.setStyleSheet(f"color: {_TEXT};")
        setup_layout.addRow(_lrs_lbl, self._live_running_setup_combo)

        # UAT Finding 1: the canonical Live baseline — the setup confirmed
        # "Applied in Game". Read-only and kept visibly separate from the manual
        # override above so unapplied recommendations never masquerade as active.
        self._live_active_setup_lbl = QLabel(
            "Live baseline: none applied yet — apply a setup in game to set the "
            "Live Race Engineer baseline.")
        self._live_active_setup_lbl.setWordWrap(True)
        self._live_active_setup_lbl.setStyleSheet(
            "color:#F0C070; font-size:10px; padding:2px 0;")
        setup_layout.addRow("", self._live_active_setup_lbl)

        layout.addWidget(setup_box)
        self._refresh_running_setup_combos()
        self._refresh_active_setup_display()

        stats_box = QGroupBox("Practice Stats")
        stats_box.setStyleSheet(self._group_style())
        s_layout = QFormLayout(stats_box)
        s_layout.setSpacing(6)
        self._lbl_prac_gap     = QLabel("—")
        self._lbl_prac_consist = QLabel("—")
        self._lbl_prac_trend   = QLabel("—")
        for lbl in (self._lbl_prac_gap, self._lbl_prac_consist, self._lbl_prac_trend):
            lbl.setFont(QFont("Segoe UI", 12))
            lbl.setStyleSheet(f"color: {_TEXT};")
        s_layout.addRow("Gap to best:", self._lbl_prac_gap)
        s_layout.addRow("Consistency (last 5):", self._lbl_prac_consist)
        s_layout.addRow("Trend:", self._lbl_prac_trend)
        layout.addWidget(stats_box)

        adv_box = QGroupBox("Driving Advice")
        adv_box.setStyleSheet(self._group_style())
        adv_layout = QVBoxLayout(adv_box)
        self._txt_practice_advice = QTextEdit()
        self._txt_practice_advice.setReadOnly(True)
        self._txt_practice_advice.setFont(QFont("Segoe UI", 11))
        self._txt_practice_advice.setStyleSheet(
            f"background:{_DARK_CARD}; color:{_TEXT}; border:none;")
        self._txt_practice_advice.setMinimumHeight(180)
        self._txt_practice_advice.setHtml(
            "<span style='color:#888;'>Complete a lap to receive driving advice.</span>")
        adv_layout.addWidget(self._txt_practice_advice)
        _voice_hint = QLabel(
            'Voice: "last lap" · "how was that"  —  "improve" · "go faster" · "coaching"  —  "setup" · "tuning"'
        )
        _voice_hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic; padding: 2px 0;")
        _voice_hint.setWordWrap(True)
        adv_layout.addWidget(_voice_hint)
        layout.addWidget(adv_box)
        layout.addStretch()
        return w

    def _build_live_qualifying_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        tgt_box = QGroupBox("Qualifying Target")
        tgt_box.setStyleSheet(self._group_style())
        tgt_row = QHBoxLayout(tgt_box)
        tgt_row.addWidget(QLabel("Target lap time:", styleSheet=f"color:{_TEXT};"))
        self._spin_qual_min = QSpinBox()
        self._spin_qual_min.setRange(0, 59)
        self._spin_qual_min.setSuffix(" m")
        self._spin_qual_min.setValue(1)
        self._spin_qual_min.setFixedWidth(70)
        self._spin_qual_sec = QDoubleSpinBox()
        self._spin_qual_sec.setRange(0.0, 59.999)
        self._spin_qual_sec.setDecimals(3)
        self._spin_qual_sec.setSuffix(" s")
        self._spin_qual_sec.setValue(45.0)
        self._spin_qual_sec.setFixedWidth(100)
        self._spin_qual_sec.setSingleStep(0.1)
        tgt_row.addWidget(self._spin_qual_min)
        tgt_row.addWidget(self._spin_qual_sec)
        tgt_row.addStretch()
        self._btn_qual_use_practice = QPushButton("Use best practice lap")
        self._lbl_qual_practice_status = QLabel("")
        self._lbl_qual_practice_status.setWordWrap(True)
        tgt_row.addWidget(self._btn_qual_use_practice)
        self._btn_qual_use_practice.clicked.connect(self._qual_use_practice_lap)
        self._spin_qual_min.valueChanged.connect(self._qual_sync_target_to_announcer)
        self._spin_qual_sec.valueChanged.connect(self._qual_sync_target_to_announcer)
        layout.addWidget(tgt_box)
        layout.addWidget(self._lbl_qual_practice_status)

        sec_box = QGroupBox("Current Lap vs Target")
        sec_box.setStyleSheet(self._group_style())
        sec_layout = QFormLayout(sec_box)
        sec_layout.setSpacing(8)
        self._lbl_qual_elapsed = QLabel("—")
        self._lbl_qual_s1      = QLabel("—")
        self._lbl_qual_s2      = QLabel("—")
        self._lbl_qual_proj    = QLabel("—")
        self._lbl_qual_last    = QLabel("—")
        for lbl in (self._lbl_qual_elapsed, self._lbl_qual_s1, self._lbl_qual_s2,
                    self._lbl_qual_proj, self._lbl_qual_last):
            lbl.setFont(QFont("Segoe UI", 12))
            lbl.setStyleSheet(f"color: {_TEXT};")
        sec_layout.addRow("Elapsed:", self._lbl_qual_elapsed)
        sec_layout.addRow("Sector 1 (0–33%):", self._lbl_qual_s1)
        sec_layout.addRow("Sector 2 (33–67%):", self._lbl_qual_s2)
        sec_layout.addRow("Projected:", self._lbl_qual_proj)
        sec_layout.addRow("Last lap:", self._lbl_qual_last)
        layout.addWidget(sec_box)
        layout.addStretch()
        return w

    def _on_live_mode_changed(self, mode: str) -> None:
        idx = {"Race": 0, "Practice": 1, "Qualifying": 2}.get(mode, 0)
        if hasattr(self, "_live_mode_stack"):
            self._live_mode_stack.setCurrentIndex(idx)
        # Entering Practice starts a fresh capture window for Practice Analysis.
        if mode == "Practice" and hasattr(self, "_reset_practice_capture"):
            self._reset_practice_capture()
        self._config.setdefault("live", {})["mode"] = mode
        self._persist_config()
        # Suppress strategy pit alerts when not in Race mode
        if self._strategy_engine is not None:
            self._strategy_engine.set_race_active(mode == "Race")
            self._strategy_engine.set_qualifying_active(mode == "Qualifying")
        # Push session type to tracker so LapRecords use the correct type
        if self._tracker is not None:
            _mode_map = {
                "Practice":   SessionType.PRACTICE,
                "Qualifying": SessionType.QUALIFYING,
                "Race":       SessionType.RACE,
            }
            self._tracker.set_session_type_override(_mode_map.get(mode))
        # Tell announcer which mode we're in (suppresses pit fuel advice in practice)
        if hasattr(self, "_announcer") and self._announcer is not None:
            self._announcer.set_session_mode(mode.lower())
        self._refresh_live_tyre_label()
        # Write live mode to the shared ref so on_packet uses the correct shift RPM threshold
        if hasattr(self, "_live_mode_ref"):
            import main
            with main._state_lock:
                self._live_mode_ref[0] = mode
                # Unify the qual/race shift-beep threshold with the live mode:
                # Qualifying -> qual RPM, Race -> race RPM. Practice is ambiguous
                # (could be qual- or race-pace running), so it leaves the finer
                # Setup Builder "Live beep uses:" selection untouched.
                if (mode in ("Race", "Qualifying")
                        and hasattr(self, "_practice_is_qual_ref")
                        and self._practice_is_qual_ref is not None):
                    self._practice_is_qual_ref[0] = (mode == "Qualifying")
        # Mirror the Setup Builder "Live beep uses:" combo so both controls agree
        # (blockSignals avoids a re-entrant _on_setup_type_changed).
        if mode in ("Race", "Qualifying") and hasattr(self, "_setup_type"):
            self._setup_type.blockSignals(True)
            self._setup_type.setCurrentText(
                "Qualifying Setup" if mode == "Qualifying" else "Race Setup")
            self._setup_type.blockSignals(False)
        # Open a new session immediately so laps (including the first outlap) are linked
        if self._db is not None and self._dispatcher is not None:
            try:
                # Legacy Fan-Out Removal Phase 5: session tagging reads the
                # canonical contexts (EventContext DB-first + StrategyContext
                # config_id) instead of the legacy fan-out. Byte-identical when
                # in sync — and since Phase 4's re-sync, always in sync.
                ev_ctx    = self._build_event_context()
                track     = ev_ctx.track
                car_name  = ev_ctx.car
                config_id = self._active_config_id()
                event_id  = int(ev_ctx.event_id or 0)
                car_id    = int(self._dispatcher._car_id_ref[0])
                _type_map = {"Practice": "practice", "Qualifying": "qualifying", "Race": "race"}
                session_type = _type_map.get(mode, "practice")
                sid = self._db.open_session(
                    car_id, track, session_type, car_name, config_id,
                    event_id=event_id,
                )
                self._dispatcher.set_session_id(sid)
                print(f"[LiveMode] session opened: id={sid} type={session_type} track={track!r}")
                # OFR-1: score any prior applied-but-unscored recs now that a
                # new session has opened and the after-session is identifiable.
                self._trigger_scoring_pass(car_id, ev_ctx.track, ev_ctx.layout_id, sid)
            except Exception as exc:
                print(f"[LiveMode] session open error: {exc}")

    def _update_live(self, p: GT7Packet) -> None:
        self._lbl_speed.set_value(f"{p.speed_kmh:.0f}")
        gear = p.current_gear
        self._lbl_gear.set_value(str(gear) if gear > 0 else "N")
        _new = f"{p.engine_rpm:.0f}"
        if self._live_label_cache.get("lbl_rpm") != _new:
            self._live_label_cache["lbl_rpm"] = _new
            self._lbl_rpm.setText(_new)

        if p.current_position > 0:
            pos_str = f"P{p.current_position}/{p.total_cars}"
        elif p.total_cars > 1:
            pos_str = f"?/{p.total_cars}"
        else:
            pos_str = "—"
        self._lbl_position.set_value(pos_str)

        cars = p.cars_in_race
        session_text = self._combo_live_mode.currentText()
        if cars > 0:
            session_text += f" ({cars} cars)"
        self._lbl_session.set_value(session_text)

        # Countdown — use tracker's recorded lap count (reliable) instead of
        # p.laps_completed (offset 116, unreliable GT7 field).
        recorded = self._tracker.laps_recorded if self._tracker is not None else 0
        if p.laps_in_race > 0:
            laps_rem = max(0, p.laps_in_race - recorded)
            self._lbl_countdown.set_value(f"{laps_rem} laps")
        else:
            rem_ms = (self._tracker.computed_remaining_ms()
                      if self._tracker is not None else -1)
            if rem_ms > 0:
                rem_s = rem_ms // 1000
                self._lbl_countdown.set_value(f"{rem_s // 60}:{rem_s % 60:02d}")
            else:
                self._lbl_countdown.set_value("—")

        # Lap times — current lap number from recorded count (1-based)
        _new = f"Lap {recorded + 1}"
        if self._live_label_cache.get("lbl_current_lap") != _new:
            self._live_label_cache["lbl_current_lap"] = _new
            self._lbl_current_lap.setText(_new)
        if p.last_lap_ms > 0:
            _new = format_laptime_display(p.last_lap_ms)
            if self._live_label_cache.get("lbl_last_lap") != _new:
                self._live_label_cache["lbl_last_lap"] = _new
                self._lbl_last_lap.setText(_new)
        if p.best_lap_ms > 0:
            _new = format_laptime_display(p.best_lap_ms)
            if self._live_label_cache.get("lbl_best_lap") != _new:
                self._live_label_cache["lbl_best_lap"] = _new
                self._lbl_best_lap.setText(_new)
        if p.last_lap_ms > 0:
            is_qual = (hasattr(self, "_combo_live_mode")
                       and self._combo_live_mode.currentText() == "Qualifying")
            if is_qual and hasattr(self, "_spin_qual_min"):
                target_ms = int(self._spin_qual_min.value() * 60_000
                                + self._spin_qual_sec.value() * 1_000)
                if target_ms > 0:
                    delta_ms = p.last_lap_ms - target_ms
                    sign = "+" if delta_ms >= 0 else ""
                    color = _ngr.WARN if delta_ms > 0 else _ACCENT
                    _dt = f"{sign}{delta_ms / 1000:.3f}s vs tgt"
                    _ds = f"color: {color};"
                    if self._live_label_cache.get("lbl_delta") != (_dt, _ds):
                        self._live_label_cache["lbl_delta"] = (_dt, _ds)
                        self._lbl_delta.setText(_dt)
                        self._lbl_delta.setStyleSheet(_ds)
            elif p.best_lap_ms > 0:
                delta_ms = p.last_lap_ms - p.best_lap_ms
                sign = "+" if delta_ms >= 0 else ""
                color = _ngr.WARN if delta_ms > 0 else _ACCENT
                _dt = f"{sign}{delta_ms / 1000:.3f}s"
                _ds = f"color: {color};"
                if self._live_label_cache.get("lbl_delta") != (_dt, _ds):
                    self._live_label_cache["lbl_delta"] = (_dt, _ds)
                    self._lbl_delta.setText(_dt)
                    self._lbl_delta.setStyleSheet(_ds)

        # Tyres — use configured thresholds from tracker if available
        thresholds = (self._tracker._thresholds if self._tracker is not None
                      else TyreThresholds())
        temps = [p.tyre_temp_fl, p.tyre_temp_fr, p.tyre_temp_rl, p.tyre_temp_rr]
        keys  = ["fl", "fr", "rl", "rr"]
        for key, temp in zip(keys, temps):
            self._tyre_widgets[key].update_tyre(temp, thresholds.classify(temp))

        # Fuel
        self._fuel_bar.update_fuel(p.fuel_level, p.fuel_capacity)

        # Mode-specific packet updates
        if hasattr(self, "_combo_live_mode") and self._combo_live_mode.currentText() == "Qualifying":
            self._update_live_qualifying(p)

        # Debug hex
        pass  # updated separately via debug slot

    def _update_live_qualifying(self, p: "GT7Packet") -> None:
        if not hasattr(self, "_spin_qual_min"):
            return

        rd = p.road_distance

        # Track maximum road_distance as a proxy for track length
        if rd > self._qual_road_dist_max:
            self._qual_road_dist_max = rd

        # Detect lap start: road_distance drops sharply from near-maximum back to ~0
        prev_rd = self._qual_prev_rd
        lap_start_detected = (
            prev_rd > max(self._qual_road_dist_max * 0.7, 200) and rd < 100
        )
        if lap_start_detected:
            self._qual_tod_at_lap_start = p.time_of_day_ms
            self._qual_s1_done = False
            self._qual_s2_done = False
            self._lbl_qual_s1.setText("—"); self._lbl_qual_s1.setStyleSheet(f"color:{_TEXT};")
            self._lbl_qual_s2.setText("—"); self._lbl_qual_s2.setStyleSheet(f"color:{_TEXT};")
            self._lbl_qual_proj.setText("—"); self._lbl_qual_proj.setStyleSheet(f"color:{_TEXT};")
        self._qual_prev_rd = rd

        target_ms = int(
            self._spin_qual_min.value() * 60_000
            + self._spin_qual_sec.value() * 1_000
        )
        if target_ms <= 0 or self._qual_tod_at_lap_start <= 0:
            return

        elapsed_ms = p.time_of_day_ms - self._qual_tod_at_lap_start
        if elapsed_ms < 0:
            return

        m = elapsed_ms // 60_000
        s = (elapsed_ms % 60_000) / 1_000
        self._lbl_qual_elapsed.setText(f"{m}:{s:06.3f}")

        lap_frac = (rd / self._qual_road_dist_max) if self._qual_road_dist_max > 10 else 0.0

        def _delta(actual_ms: int, target_frac_ms: int) -> tuple[str, str]:
            d = actual_ms - target_frac_ms
            sign = "+" if d >= 0 else ""
            col = _ngr.WARN if d > 0 else _ACCENT
            return f"{sign}{d / 1000:.3f}s", col

        if lap_frac >= 0.333 and not self._qual_s1_done:
            txt, col = _delta(elapsed_ms, int(target_ms * 0.333))
            self._lbl_qual_s1.setText(txt)
            self._lbl_qual_s1.setStyleSheet(f"color:{col};")
            self._qual_s1_done = True

        if lap_frac >= 0.667 and not self._qual_s2_done:
            txt, col = _delta(elapsed_ms, int(target_ms * 0.667))
            self._lbl_qual_s2.setText(txt)
            self._lbl_qual_s2.setStyleSheet(f"color:{col};")
            self._qual_s2_done = True

        if lap_frac > 0.05 and elapsed_ms > 0:
            proj_ms = int(elapsed_ms / lap_frac)
            delta_total = proj_ms - target_ms
            sign = "+" if delta_total >= 0 else ""
            col = _ngr.WARN if delta_total > 0 else _ACCENT
            self._lbl_qual_proj.setText(
                f"{format_laptime_display(proj_ms)} ({sign}{delta_total / 1000:.3f}s)")
            self._lbl_qual_proj.setStyleSheet(f"color:{col};")

    def _maybe_init_live_corner_tel(self) -> None:
        """Create/re-target the live per-corner telemetry aggregator for the active
        track/layout. Cheap-guarded; called throttled from _poll_ui_queue. Inert (stays
        None) when there is no active track. Rebuilds on a track/layout/car change so a
        prior track's corners never bleed into a new one."""
        try:
            ec = self._build_event_context()
            loc = str(getattr(ec, "track_location_id", "") or "").strip()
            lay = str(getattr(ec, "layout_id", "") or "").strip()
        except Exception:
            return
        if not loc or not lay:
            return
        try:
            _dt = self._setup_drivetrain.currentData() if hasattr(self, "_setup_drivetrain") else ""
        except Exception:
            _dt = ""
        key = (loc, lay, str(_dt or ""))
        if key == self._live_corner_tel_key and self._live_corner_tel is not None:
            return
        try:
            from telemetry.live_corner_telemetry import LiveCornerTelemetry
            # A per-run id makes cross-session persistence idempotent (re-saving the same
            # run replaces its row rather than double-counting).
            self._live_corner_tel = LiveCornerTelemetry(
                loc, lay, drivetrain=str(_dt or ""), run_id=int(time.time()))
            self._live_corner_tel_key = key
        except Exception:
            self._live_corner_tel = None
            self._live_corner_tel_key = None

    def _refresh_live_replan_snapshot(self) -> None:
        """Build and render a read-only, advisory-only live replan snapshot.

        Reads live race state from the tracker + last packet (read-only), compares
        it against the last-built pre-race Race Plan, and shows whether the plan is
        still viable / needs review / lacks evidence. No pit call, no setup change,
        no writes, no API key. Never raises.
        """
        label = getattr(self, "_rp_replan_status", None)
        if label is None:
            return

        pre = getattr(self, "_last_race_plan_result", None)
        if pre is None or not getattr(getattr(pre, "recommendation", None), "has_recommendation", False):
            label.setText(
                "Build a Race Plan first — then Refresh to check it against the live "
                "race state. (Advisory only; no pit call or setup change is applied.)")
            return

        try:
            from strategy.race_strategy_live_replan import (
                build_live_replan_snapshot, render_live_replan_text,
            )
            event_settings = dict(getattr(self, "_last_race_plan_inputs", {}) or {})
            track_context, live_progress = self._resolve_live_pit_lane_context()
            (live_position, reference_stations, identity_ok,
             ref_source, ref_warnings) = self._resolve_live_track_progress_context()
            lap_distance_m, road_distance, lap_length_m = \
                self._resolve_road_distance_fallback_context()
            result = build_live_replan_snapshot(
                pre_race_result=pre,
                live_source=self,                 # dashboard: reads _tracker + _last_packet
                event_settings=event_settings,
                track_context=track_context,      # Group 55: pit-lane mapping (or None)
                live_progress=live_progress,      # Group 55: explicit lap progress (or None)
                live_position=live_position,      # Group 56: live world XYZ (or None)
                reference_stations=reference_stations,  # Group 56/57: approved path (or None)
                identity_ok=identity_ok,
                reference_path_source=ref_source,       # Group 57: provenance (or "")
                reference_path_warnings=ref_warnings,   # Group 57: load warnings
                lap_distance_m=lap_distance_m,    # Group 58: fallback inputs (or None)
                road_distance=road_distance,
                lap_length_m=lap_length_m,
                stabiliser_state=self._live_progress_stabiliser(),  # Group 61: display-only
                generated_at=time.strftime("%H:%M:%S"),
            )
            label.setText(render_live_replan_text(result))
        except Exception as exc:
            label.setText(
                f"Live replan snapshot unavailable: {exc}. "
                "Advisory only; no action is applied.")

    def _live_progress_stabiliser(self):
        """Lazily create + return the display-only live-progress stabiliser state (Group 61).

        The stabiliser only annotates the rendered live-progress line (jitter / false-
        certainty guard). It never changes the reported position value, never inflates
        confidence, and never touches pit corroboration, pit count, setup, or commands.
        """
        try:
            if self._live_stabiliser_state is None:
                from data.live_progress_stabiliser import LiveProgressStabiliserState
                self._live_stabiliser_state = LiveProgressStabiliserState()
        except Exception:
            self._live_stabiliser_state = None
        return self._live_stabiliser_state

    def _resolve_live_pit_lane_context(self):
        """Resolve (track_context, live_progress) for Group 55 pit-lane corroboration.

        Read-only and defensive: returns (None, None) whenever pit-lane mapping or
        live lap-progress is unavailable, so live replan degrades to exact Group 54
        behaviour. Never raises. GT7 does not currently broadcast a normalised
        lap-progress fraction, so ``live_progress`` is typically None today.
        """
        track_context = None
        live_progress = None
        try:
            ec = self._build_event_context()
            track = str(getattr(ec, "track", "") or "").strip()
            layout_id = str(getattr(ec, "layout_id", "") or "").strip()
            if track:
                from data.track_library import load_track_pit_lane
                # Try a couple of id spellings; missing mapping → None (graceful).
                candidates = [track, track.lower().replace(" ", "_")]
                for track_id in candidates:
                    block = load_track_pit_lane(track_id, layout_id or track_id)
                    if block:
                        track_context = {
                            "track_id": track_id, "layout_id": layout_id,
                            "pit_lane": block if "segments" in block else block.get("pit_lane", block),
                        }
                        break
        except Exception:
            track_context = None
        # Live normalised lap-progress: an explicit override only (Group 56 now
        # derives progress from world position, so this is usually None).
        try:
            lp = getattr(self, "_live_lap_progress", None)
            if lp is not None:
                live_progress = float(lp)
        except Exception:
            live_progress = None
        return track_context, live_progress

    def _resolve_live_track_progress_context(self):
        """Resolve live progress inputs for Group 56/57.

        Returns ``(live_position, reference_stations, identity_ok, reference_path_source,
        reference_path_warnings)``. Read-only and defensive: discovers an APPROVED
        reference-path asset for the event's track/layout via the Group 57 loader,
        validates identity, and converts it to Group 56 stations. Returns safe empties
        when the live position or an approved path is unavailable. Never raises; runs no
        calibration workflow and mutates nothing.
        """
        live_position = None
        reference_stations = None
        identity_ok = True
        ref_source = ""
        ref_warnings: tuple = ()
        try:
            if self._tracker is not None:
                live_position = getattr(self._tracker, "live_world_position", None)
            if live_position is None:
                p = getattr(self, "_last_packet", None)
                if p is not None and all(hasattr(p, a) for a in ("pos_x", "pos_y", "pos_z")):
                    live_position = (float(p.pos_x), float(p.pos_y), float(p.pos_z),
                                     float(getattr(p, "speed_kmh", 0.0) or 0.0))
        except Exception:
            live_position = None
        try:
            ec = self._build_event_context()
            track_id = str(getattr(ec, "track_location_id", "") or "").strip()
            layout_id = str(getattr(ec, "layout_id", "") or "").strip()
            track_hint = track_id or str(getattr(ec, "track", "") or "").strip()
            if track_hint or layout_id:
                from data.reference_path_loader import (
                    load_reference_path_for_layout,
                    reference_path_to_track_stations,
                    validate_reference_path_identity,
                )
                result = load_reference_path_for_layout(track_hint, layout_id)
                if result.has_stations:
                    stations = reference_path_to_track_stations(result.asset)
                    if stations:
                        reference_stations = stations
                        ref_source = result.source
                        ref_warnings = tuple(result.warnings or ())
                        ok, msg = validate_reference_path_identity(
                            result.asset, track_hint, layout_id)
                        identity_ok = ok
                        if not ok:
                            ref_warnings = ref_warnings + (msg,)
                else:
                    ref_warnings = ("reference path has no usable stations",)
                if reference_stations is None and not ref_warnings:
                    ref_warnings = tuple(result.warnings or ())
        except Exception:
            reference_stations = None
            ref_source = ""
            ref_warnings = ()
        return live_position, reference_stations, identity_ok, ref_source, ref_warnings

    def _build_strategy_live_status_group(self) -> QGroupBox:
        status_box = QGroupBox("Live Status")
        status_layout = QVBoxLayout(status_box)
        self._lbl_strategy_status = QLabel("No plan loaded")
        self._lbl_strategy_status.setStyleSheet(f"color: {_TEXT};")
        self._lbl_strategy_status.setWordWrap(True)
        status_layout.addWidget(self._lbl_strategy_status)
        return status_box

    def _update_live_plan(self, stops_data: list[dict]) -> None:
        """Refresh the Active Race Plan label on the Live tab."""
        if not hasattr(self, "_lbl_live_plan"):
            return
        if not stops_data:
            self._lbl_live_plan.setText(
                "No plan applied — set stints on the Strategy tab and click  Apply.")
            self._lbl_live_plan.setStyleSheet("color: #999; padding: 4px;")
            return
        parts = []
        for i, s in enumerate(stops_data, 1):
            compound = s.get("compound", "?")
            laps = s.get("laps", "?")
            ref_ms = int(s.get("ref_lap_ms", 0) or 0)
            if ref_ms > 0:
                m = ref_ms // 60000
                sec = (ref_ms % 60000) / 1000.0
                ref_str = f"ref {m}:{sec:06.3f}"
            else:
                ref_str = "no ref"
            parts.append(f"Stint {i}  {compound}  {laps} laps  ({ref_str})")
        self._lbl_live_plan.setText("   |   ".join(parts))
        self._lbl_live_plan.setStyleSheet(f"color: {_TEXT}; padding: 4px;")

    def _refresh_live_tyre_label(self) -> None:
        """Update the Live tab current tyre label using the priority hierarchy."""
        if not hasattr(self, "_lbl_live_tyre_compound"):
            return
        compound = self._get_current_tyre_compound()
        self._lbl_live_tyre_compound.setText(f"Current Tyre: {compound}")
