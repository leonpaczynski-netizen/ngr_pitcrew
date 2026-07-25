"""ShiftStrategyView — per-gear shift strategy panel within the Garage tab.

Advisory-only: read-only advice. No Apply button, no Fuel-Map control, no
gearbox command, no pit command anywhere in this surface. The widget
fabricates NOTHING — every string, tone and label comes from the
ShiftStrategyVM injected via set_view().

SAFETY: This surface exposes no setup-apply controls. It is pure
presentation over ShiftStrategyVM; it never mutates a setup sheet, the
shift-beep RPM, or any game state.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QLayout, QToolButton, QButtonGroup,
    QSpinBox, QSizePolicy,
)

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading, Card
from ui.components.status import StatusPill, ConfidenceMeter
from ui.components.buttons import SecondaryActionButton
from ui.workflow_stepper_widget import WorkflowStepper
from ui.workflow_stepper import WorkflowState, WorkflowStage, StageStatus
from ui.shift_strategy_vm import ShiftStrategyVM, confidence_tone


# ---------------------------------------------------------------------------
# Stepper stage definitions for the 4-stage shift-strategy workflow
# ---------------------------------------------------------------------------
_STEPPER_STAGES = [
    "Enter gear ratios",
    "Add engine data",
    "Review profile",
    "Activate for session",
]


def _build_workflow_state(vm: ShiftStrategyVM) -> WorkflowState:
    """Map ShiftStrategyVM stepper fields to a WorkflowState for WorkflowStepper.

    stage 0..2: stages 0..stage-1 are DONE, stage is CURRENT/BLOCKED, rest PENDING
    stage 3: stages 0..2 are DONE, stage 3 is CURRENT (ready to go live)
    """
    stage = min(max(int(vm.stepper_stage), 0), 3)
    stages = []
    for idx, title in enumerate(_STEPPER_STAGES):
        if idx < stage:
            status = StageStatus.DONE
            blocker = ""
        elif idx == stage:
            status = (StageStatus.BLOCKED if vm.stepper_blocker_text
                      else StageStatus.CURRENT)
            blocker = vm.stepper_blocker_text
        else:
            status = StageStatus.PENDING
            blocker = ""
        stages.append(WorkflowStage(
            index=idx,
            key=f"shift_stage_{idx}",
            title=title,
            status=status,
            blocker=blocker,
            next_action=vm.stepper_blocker_text if idx == stage else "",
        ))

    if stage < len(_STEPPER_STAGES) and stages[stage].status is not StageStatus.DONE:
        next_action = vm.stepper_blocker_text or _STEPPER_STAGES[stage]
        next_tab = vm.stepper_go_to_tab
    else:
        next_action = "All stages complete."
        next_tab = ""

    return WorkflowState(
        stages=tuple(stages),
        current_index=stage,
        next_action=next_action,
        next_tab=next_tab,
    )


def _is_numeric_confidence(key: str) -> bool:
    """True when the confidence level has a meaningful bar fill (HIGH/MEDIUM/LOW)."""
    return key.upper() in ("HIGH", "MEDIUM", "LOW")


class ShiftStrategyView(QWidget):
    """Read-only per-gear shift strategy displayed as a Garage sub-tab.

    Single entry point: ``set_view(vm: ShiftStrategyVM)`` — the widget
    fabricates nothing; every string, tone and label comes from the VM.

    Signals
    -------
    profile_changed(str)
        Emitted when the driver toggles between "qualifying" and "race".
        Does not change which setup is active.
    engine_data_seeded(dict)
        Emitted when the driver presses "Seed provisional model".
        Payload: {peak_power_rpm, peak_torque_rpm, redline} (int each).
    recalculate_requested()
        Emitted when the driver presses "Recalculate".
    go_to_tab(str)
        Emitted when the stepper's Go button is pressed; value is
        vm.stepper_go_to_tab (e.g. "Transmission", "Shift Strategy").
    """

    profile_changed = pyqtSignal(str)
    engine_data_seeded = pyqtSignal(dict)
    recalculate_requested = pyqtSignal()
    go_to_tab = pyqtSignal(str)
    #: Phase 2 — calibrate the torque curve from recorded wide-open-throttle telemetry,
    #: lifting the strategy off manually-entered engine data.
    calibrate_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrShiftStrategyView")
        self._vm: Optional[ShiftStrategyVM] = None
        self._engine_collapsed = True

        root = QVBoxLayout(self)
        root.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        root.setSpacing(_t.SPACE_MD)
        # SetMinimumSize: the view lives inside the Garage page's existing
        # QScrollArea (_scrollable in pit_crew_shell.py). The constraint tells
        # the scroll area the correct minimum height so content never overlaps.
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self._root = root

        # ------------------------------------------------------------------ #
        # Header row                                                          #
        # ------------------------------------------------------------------ #
        header = QHBoxLayout()
        header.addWidget(SectionHeading("SHIFT STRATEGY", level=1))
        header.addSpacing(_t.SPACE_MD)
        header.addStretch(1)
        header.addWidget(
            StatusPill("Read-only · no setup changes", tone="advisory", glyph="●"))
        root.addLayout(header)

        # ------------------------------------------------------------------ #
        # Guided stepper                                                      #
        # ------------------------------------------------------------------ #
        self._stepper = WorkflowStepper()
        self._stepper.go_to_tab.connect(self.go_to_tab)
        root.addWidget(self._stepper)

        # ------------------------------------------------------------------ #
        # Summary card                                                        #
        # ------------------------------------------------------------------ #
        self._summary_card = Card()
        self._summary_card.body.setSizeConstraint(
            QLayout.SizeConstraint.SetMinimumSize)
        sc = self._summary_card.body

        # Profile toggle — QUALIFYING | RACE, exclusive, non-auto.
        # Caption makes clear this does NOT change which setup is active.
        toggle_row = QHBoxLayout()
        self._profile_group = QButtonGroup(self)
        self._profile_group.setExclusive(True)
        self._btn_qual = QToolButton()
        self._btn_qual.setText("QUALIFYING")
        self._btn_qual.setCheckable(True)
        self._btn_qual.setChecked(True)
        self._btn_qual.setMinimumHeight(_t.TOUCH_MIN_H)
        self._btn_qual.setStyleSheet(_toggle_qss())
        self._btn_qual.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_race = QToolButton()
        self._btn_race.setText("RACE")
        self._btn_race.setCheckable(True)
        self._btn_race.setMinimumHeight(_t.TOUCH_MIN_H)
        self._btn_race.setStyleSheet(_toggle_qss())
        self._btn_race.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_group.addButton(self._btn_qual)
        self._profile_group.addButton(self._btn_race)
        self._btn_qual.clicked.connect(
            lambda: self.profile_changed.emit("qualifying"))
        self._btn_race.clicked.connect(
            lambda: self.profile_changed.emit("race"))
        toggle_row.addWidget(self._btn_qual)
        toggle_row.addWidget(self._btn_race)
        toggle_row.addSpacing(_t.SPACE_SM)
        toggle_caption = QLabel(
            "Switch profile — does not change which setup is active")
        toggle_caption.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        toggle_row.addWidget(toggle_caption)
        toggle_row.addStretch(1)
        sc.addLayout(toggle_row)

        # Required / predicted saving / time cost grid
        saving_row = QHBoxLayout()
        saving_row.setSpacing(_t.SPACE_XL)
        for cap_text, cap_attr, val_attr in [
            ("Required saving",  "_lbl_req_cap",  "_lbl_req"),
            ("Predicted saving", "_lbl_pred_cap", "_lbl_pred"),
            ("Time cost",        "_lbl_tc_cap",   "_lbl_tc"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            cap = QLabel(cap_text)
            cap.setStyleSheet(
                f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
            val = QLabel("—")
            val.setWordWrap(True)
            val.setStyleSheet(
                f"color: {_t.TEXT_HI}; font-size: {_t.FS_LABEL}pt; "
                f"font-weight: 600;")
            setattr(self, cap_attr, cap)
            setattr(self, val_attr, val)
            col.addWidget(cap)
            col.addWidget(val)
            saving_row.addLayout(col)
        saving_row.addStretch(1)
        sc.addLayout(saving_row)

        # Config status pill + stale explanation + Recalculate button
        config_row = QHBoxLayout()
        self._pill_config = StatusPill("", tone="neutral")
        config_row.addWidget(self._pill_config)
        self._lbl_stale = QLabel("")
        self._lbl_stale.setWordWrap(True)
        self._lbl_stale.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        config_row.addWidget(self._lbl_stale, 1)
        self._btn_calibrate = SecondaryActionButton("Calibrate from telemetry")
        self._btn_calibrate.setToolTip(
            "Estimate the torque curve from your recorded full-throttle laps, so the "
            "shift strategy rises above the manual-entry PROVISIONAL ceiling.")
        self._btn_calibrate.clicked.connect(
            lambda: self.calibrate_requested.emit())
        config_row.addWidget(self._btn_calibrate)
        self._btn_recalculate = SecondaryActionButton("Recalculate")
        self._btn_recalculate.clicked.connect(
            lambda: self.recalculate_requested.emit())
        config_row.addWidget(self._btn_recalculate)
        sc.addLayout(config_row)

        # Calibration status line — what the last "Calibrate from telemetry" produced.
        self._lbl_calib = QLabel("")
        self._lbl_calib.setWordWrap(True)
        self._lbl_calib.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._lbl_calib.setVisible(False)
        sc.addWidget(self._lbl_calib)

        # Overall confidence — ConfidenceMeter for HIGH/MEDIUM/LOW,
        # StatusPill for PROVISIONAL/STALE/INSUFFICIENT_EVIDENCE.
        self._confidence_meter = ConfidenceMeter("unknown")
        sc.addWidget(self._confidence_meter)
        self._pill_overall = StatusPill("", tone="neutral")
        self._pill_overall.setVisible(False)
        sc.addWidget(self._pill_overall)

        # Evidence readiness / next-action text
        self._lbl_evidence = QLabel("")
        self._lbl_evidence.setWordWrap(True)
        self._lbl_evidence.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        sc.addWidget(self._lbl_evidence)

        root.addWidget(self._summary_card)

        # ------------------------------------------------------------------ #
        # Banner (conditional — shown when vm.banner_text is non-empty)      #
        # ------------------------------------------------------------------ #
        self._banner_lbl = QLabel("")
        self._banner_lbl.setWordWrap(True)
        self._banner_lbl.setVisible(False)
        root.addWidget(self._banner_lbl)

        # ------------------------------------------------------------------ #
        # Engine data card (collapsible, collapsed by default)               #
        # ------------------------------------------------------------------ #
        self._engine_card = Card()
        self._engine_card.body.setSizeConstraint(
            QLayout.SizeConstraint.SetMinimumSize)
        ec = self._engine_card.body

        eng_header = QHBoxLayout()
        self._engine_toggle = QToolButton()
        self._engine_toggle.setText("▸  Engine data (optional)")
        self._engine_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._engine_toggle.setStyleSheet(
            f"QToolButton {{ color: {_t.TEXT_DIM}; background: transparent; "
            f"border: none; font-size: {_t.FS_LABEL}pt; "
            f"text-align: left; }}"
            f"QToolButton:hover {{ color: {_t.TEXT_HI}; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
        )
        self._engine_toggle.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._engine_toggle.clicked.connect(self._toggle_engine_panel)
        eng_header.addWidget(self._engine_toggle)
        ec.addLayout(eng_header)

        self._engine_body = QWidget()
        eng_body_lay = QVBoxLayout(self._engine_body)
        eng_body_lay.setContentsMargins(0, _t.SPACE_SM, 0, 0)
        eng_body_lay.setSpacing(_t.SPACE_SM)

        for attr, label_text in [
            ("_spin_power_rpm",  "Peak power RPM"),
            ("_spin_torque_rpm", "Peak torque RPM"),
            ("_spin_redline",    "Redline (RPM)"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
            lbl.setMinimumWidth(160)
            row.addWidget(lbl)
            spin = QSpinBox()
            spin.setRange(0, 20000)
            spin.setSingleStep(100)
            spin.setSpecialValueText("Not set")
            spin.setMinimumHeight(_t.TOUCH_MIN_H)
            spin.setMaximumWidth(160)
            spin.setStyleSheet(
                f"QSpinBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
                f"border: 1px solid {_t.HAIRLINE}; "
                f"border-radius: {_t.RADIUS_SM}px; "
                f"padding: 4px 8px; font-size: {_t.FS_LABEL}pt; }}"
            )
            setattr(self, attr, spin)
            row.addWidget(spin)
            row.addStretch(1)
            eng_body_lay.addLayout(row)

        self._btn_seed = SecondaryActionButton("Seed provisional model")
        self._btn_seed.clicked.connect(self._on_seed_engine)
        eng_body_lay.addWidget(self._btn_seed)

        self._engine_body.setVisible(False)  # collapsed by default
        ec.addWidget(self._engine_body)
        root.addWidget(self._engine_card)

        # ------------------------------------------------------------------ #
        # Gear pair table — 5 columns                                        #
        # ------------------------------------------------------------------ #
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Gear pair", "Qual RPM", "Race RPM", "Δ RPM", "Confidence"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ color: {_t.TEXT_HI}; "
            f"background: {_t.CARBON_RAISED}; "
            f"alternate-background-color: {_t.CARBON}; "
            f"gridline-color: {_t.HAIRLINE_SOFT}; "
            f"border: 1px solid {_t.HAIRLINE}; "
            f"border-radius: {_t.RADIUS_SM}px; }}"
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        # Touch-friendly row height.
        self._table.verticalHeader().setDefaultSectionSize(
            max(_t.TOUCH_MIN_H, 36))
        self._table.currentCellChanged.connect(
            lambda row, _col, *_rest: self._on_row_selected(row))
        root.addWidget(self._table)

        # ------------------------------------------------------------------ #
        # Empty state (shown instead of the table when VM has no rows)       #
        # ------------------------------------------------------------------ #
        self._empty_lbl = QLabel("")
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"QLabel {{ color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt; "
            f"padding: {_t.SPACE_XL}px; border: 1px dashed {_t.HAIRLINE}; "
            f"border-radius: {_t.RADIUS_MD}px; background: {_t.CARBON}; }}"
        )
        self._empty_lbl.setVisible(False)
        root.addWidget(self._empty_lbl)

        # ------------------------------------------------------------------ #
        # Gear detail card — updated on row-select                           #
        # ------------------------------------------------------------------ #
        self._detail_card = Card()
        self._detail_card.body.setSizeConstraint(
            QLayout.SizeConstraint.SetMinimumSize)
        dc = self._detail_card.body

        detail_heading = QLabel("Selected gear detail")
        detail_heading.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-weight: 700; "
            f"font-size: {_t.FS_H3}pt;")
        dc.addWidget(detail_heading)

        detail_grid = QHBoxLayout()
        detail_grid.setSpacing(_t.SPACE_XL)
        for cap_text, cap_attr, val_attr in [
            ("Post-shift RPM", "_dlbl_post_cap", "_dlbl_post"),
            ("Fuel saving",    "_dlbl_fuel_cap", "_dlbl_fuel"),
            ("Time cost",      "_dlbl_tc_cap",   "_dlbl_tc"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            cap = QLabel(cap_text)
            cap.setStyleSheet(
                f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
            val = QLabel("—")
            val.setWordWrap(True)
            val.setStyleSheet(
                f"color: {_t.TEXT_HI}; font-size: {_t.FS_LABEL}pt; "
                f"font-weight: 600;")
            setattr(self, cap_attr, cap)
            setattr(self, val_attr, val)
            col.addWidget(cap)
            col.addWidget(val)
            detail_grid.addLayout(col)
        detail_grid.addStretch(1)
        dc.addLayout(detail_grid)

        evid_row = QHBoxLayout()
        evid_cap = QLabel("Evidence")
        evid_cap.setStyleSheet(
            f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
        evid_row.addWidget(evid_cap)
        self._detail_evid_pill = StatusPill("—", tone="neutral")
        evid_row.addWidget(self._detail_evid_pill)
        evid_row.addStretch(1)
        dc.addLayout(evid_row)

        root.addWidget(self._detail_card)
        root.addStretch(1)

    # ---------------------------------------------------------------------- #
    # Public API                                                               #
    # ---------------------------------------------------------------------- #

    def set_calibration_status(self, text: str, *, ok: bool = True) -> None:
        """Show (or clear, with "") the outcome of the last telemetry calibration."""
        text = str(text or "")
        self._lbl_calib.setText(text)
        self._lbl_calib.setStyleSheet(
            f"color: {_t.NGR_GREEN if ok else _t.WARN}; font-size: {_t.FS_CAPTION}pt;")
        self._lbl_calib.setVisible(bool(text))

    def set_view(self, vm: ShiftStrategyVM) -> None:
        """Feed a new view model. Never raises."""
        try:
            self._vm = vm
            self._render_stepper(vm)
            self._render_summary(vm)
            self._render_banner(vm)
            self._render_engine_card(vm)
            self._render_table(vm)
        except Exception as exc:  # pragma: no cover — defensive
            print(f"[ShiftStrategyView] set_view error: {exc}")

    # ---------------------------------------------------------------------- #
    # Private rendering                                                        #
    # ---------------------------------------------------------------------- #

    def _render_stepper(self, vm: ShiftStrategyVM) -> None:
        self._stepper.set_state(_build_workflow_state(vm))

    def _render_summary(self, vm: ShiftStrategyVM) -> None:
        # Profile toggle — block signals to avoid emitting profile_changed
        # when the feed updates the toggle (not a driver action).
        self._btn_qual.blockSignals(True)
        self._btn_race.blockSignals(True)
        if vm.active_profile == "race":
            self._btn_race.setChecked(True)
            self._btn_qual.setChecked(False)
        else:
            self._btn_qual.setChecked(True)
            self._btn_race.setChecked(False)
        self._btn_qual.blockSignals(False)
        self._btn_race.blockSignals(False)

        # Saving / time cost grid
        self._lbl_req.setText(vm.required_saving_text or "—")
        self._lbl_pred.setText(vm.predicted_saving_text or "—")
        self._lbl_tc.setText(vm.time_cost_text or "—")

        # Config status
        is_stale = vm.config_is_stale
        self._pill_config.set_status(
            vm.config_status_text or "—",
            tone="warn" if is_stale else "success")
        self._lbl_stale.setText(vm.stale_field_text or "")
        self._lbl_stale.setVisible(bool(vm.stale_field_text))

        # Overall confidence
        key = vm.overall_confidence_key
        if _is_numeric_confidence(key):
            self._confidence_meter.set_level(key.lower())
            self._confidence_meter.setVisible(True)
            self._pill_overall.setVisible(False)
        else:
            self._confidence_meter.setVisible(False)
            tone = confidence_tone(key)
            # Label for the pill: use the shortened key text as a status
            conf_text = {
                "PROVISIONAL":          "Provisional",
                "STALE":                "Stale",
                "INSUFFICIENT_EVIDENCE": "Needs data",
            }.get(key.upper(), key)
            self._pill_overall.set_status(
                f"Confidence: {conf_text}", tone=tone)
            self._pill_overall.setVisible(True)

        # Evidence / next-action text
        self._lbl_evidence.setText(vm.evidence_readiness_text or "")

    def _render_banner(self, vm: ShiftStrategyVM) -> None:
        if vm.banner_text:
            tone = vm.banner_tone or "advisory"
            self._banner_lbl.setText(vm.banner_text)
            self._banner_lbl.setStyleSheet(_t.banner_qss(tone))
            self._banner_lbl.setVisible(True)
        else:
            self._banner_lbl.setVisible(False)

    def _render_engine_card(self, vm: ShiftStrategyVM) -> None:
        # Seed the spinboxes from the VM's engine data — only when the
        # driver is not actively editing a field (avoids mid-type clobber).
        for attr, value in [
            ("_spin_power_rpm",  vm.engine_peak_power_rpm),
            ("_spin_torque_rpm", vm.engine_peak_torque_rpm),
            ("_spin_redline",    vm.engine_redline),
        ]:
            spin: QSpinBox = getattr(self, attr)
            if not spin.hasFocus():
                v = int(value or 0)
                spin.blockSignals(True)
                spin.setValue(v)
                spin.blockSignals(False)

    def _render_table(self, vm: ShiftStrategyVM) -> None:
        rows = vm.rows
        has_rows = bool(rows)
        self._table.setVisible(has_rows)
        self._detail_card.setVisible(has_rows)

        if not has_rows:
            self._empty_lbl.setText(
                vm.evidence_readiness_text
                or vm.banner_text
                or "Enter gear ratios in the Transmission sheet to begin.")
            self._empty_lbl.setVisible(True)
            return

        self._empty_lbl.setVisible(False)

        # Rebuild table rows
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            # Col 0 — Gear pair label (left-aligned)
            item0 = QTableWidgetItem(row.label)
            item0.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(i, 0, item0)

            # Cols 1-3 — RPM values (right-aligned)
            for col, text in enumerate(
                    [row.qualifying_rpm, row.race_rpm, row.rpm_delta], start=1):
                it = QTableWidgetItem(text)
                it.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if not row.has_data:
                    from PyQt6.QtGui import QColor
                    it.setForeground(QColor(_t.TEXT_MUTE))
                self._table.setItem(i, col, it)

            # Col 4 — Confidence as a StatusPill widget.
            # Rows without valid data show the NEEDS-DATA pill explicitly.
            pill = StatusPill(
                row.confidence_label,
                tone=confidence_tone(row.confidence_key))
            self._table.setCellWidget(i, 4, pill)

        # Auto-select first row so the detail card is never blank.
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._update_detail(0)

        # Dim the table when the configuration is stale.
        try:
            from PyQt6.QtWidgets import QGraphicsOpacityEffect
            effect = QGraphicsOpacityEffect(self._table)
            effect.setOpacity(0.45 if vm.config_is_stale else 1.0)
            self._table.setGraphicsEffect(effect)
        except Exception:
            pass  # graceful no-op if the effect is unavailable

    # ---------------------------------------------------------------------- #
    # Slots                                                                    #
    # ---------------------------------------------------------------------- #

    def _on_row_selected(self, row: int) -> None:
        if row < 0:
            return
        self._update_detail(row)

    def _update_detail(self, row: int) -> None:
        vm = self._vm
        if vm is None or row < 0 or row >= len(vm.rows):
            return
        r = vm.rows[row]
        self._dlbl_post.setText(r.post_shift_rpm)
        self._dlbl_fuel.setText(r.fuel_saving)
        self._dlbl_tc.setText(r.time_cost)
        self._detail_evid_pill.set_status(
            r.confidence_label, tone=r.evidence_tone)

    def _toggle_engine_panel(self) -> None:
        self._engine_collapsed = not self._engine_collapsed
        self._engine_body.setVisible(not self._engine_collapsed)
        arrow = "▾" if not self._engine_collapsed else "▸"
        self._engine_toggle.setText(f"{arrow}  Engine data (optional)")

    def _on_seed_engine(self) -> None:
        data = {
            "peak_power_rpm":  int(self._spin_power_rpm.value() or 0),
            "peak_torque_rpm": int(self._spin_torque_rpm.value() or 0),
            "redline":         int(self._spin_redline.value() or 0),
        }
        self.engine_data_seeded.emit(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _toggle_qss() -> str:
    """QSS for the profile QUALIFYING/RACE segmented toggle."""
    return (
        f"QToolButton {{ color: {_t.TEXT_DIM}; background: {_t.CARBON}; "
        f"border: 1px solid {_t.HAIRLINE}; padding: 5px 16px; "
        f"font-size: {_t.FS_LABEL}pt; }}"
        f"QToolButton:hover {{ color: {_t.TEXT_HI}; }}"
        f"QToolButton:checked {{ color: {_t.NGR_GREEN_INK}; "
        f"background: {_t.NGR_GREEN}; border-color: {_t.NGR_GREEN}; "
        f"font-weight: 700; }}"
        f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
    )
