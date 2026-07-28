"""SetupWorkspace — the single focused Garage setup surface (F2).

Replaces the old side-by-side Base/Qualifying/Race scrolling maze with ONE
workspace and a discipline selector. It renders a ``SetupRecommendationVM`` (the
canonical recommendation model) and applies it through ``applied_field_values()``
so what the driver sees is exactly what gets applied (F2.2).

It renders and signals only — it performs no engineering. ``apply_requested`` hands
the caller the exact field→value dict to write via the canonical apply/clamp path;
``discipline_changed`` asks the caller to rebuild for another discipline.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget, QScrollArea, QFrame, QComboBox,
)

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading
from ui.components.status import StatusPill
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton
from ui.components.gt7_settings_sheet import GT7SettingsSheet
from ui.components.setup_lineage import SetupLineageTree, LineageNode
from ui.components.setup_comparison import SetupComparison
from ui.setup_recommendation_vm import SetupRecommendationVM, build_recommendation_vm
from ui.setup_transcribe_view import gt7_field_rank

try:
    from strategy.gearbox_objectives import gearbox_headline, gearbox_objectives
except Exception:  # pragma: no cover - defensive
    def gearbox_headline(_d):
        return ""
    def gearbox_objectives(_d):
        return ()


#: The two sheets the domain actually has. There is no third "Base" sheet — the
#: baseline build FILLS these two, so a Base tab could only ever mirror the Race one.
#: It is an ACTION ("Build initial setup"), not a discipline.
DISCIPLINES = (("race", "Race"), ("qualifying", "Qualifying"))


class SetupDisciplineSelector(QWidget):
    """Segmented Base | Qualifying | Race selector (one focused discipline)."""

    discipline_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for key, label in DISCIPLINES:
            b = QToolButton(self)
            b.setText(label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(_t.TOUCH_MIN_H)
            b.setStyleSheet(self._qss())
            b.clicked.connect(lambda _=False, k=key: self._on_click(k))
            self._group.addButton(b)
            self._buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)
        self._current = "race"
        self.set_discipline("race")

    def _on_click(self, key: str) -> None:
        self._current = key
        self.discipline_changed.emit(key)

    def set_discipline(self, key: str) -> None:
        b = self._buttons.get(key)
        if b is not None:
            self._current = key
            b.setChecked(True)

    def current(self) -> str:
        return self._current

    @staticmethod
    def _qss() -> str:
        return (
            f"QToolButton {{ color: {_t.TEXT_DIM}; background: {_t.CARBON}; "
            f"border: 1px solid {_t.HAIRLINE}; padding: 5px 16px; "
            f"font-size: {_t.FS_LABEL}pt; }}"
            f"QToolButton:hover {{ color: {_t.TEXT_HI}; }}"
            f"QToolButton:checked {{ color: {_t.NGR_GREEN_INK}; background: {_t.NGR_GREEN}; "
            f"border-color: {_t.NGR_GREEN}; font-weight: 700; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
        )


#: What each discipline IS, in the driver's words — shown under the selector so the
#: three tabs are never three identical-looking sheets with no explanation.
DISCIPLINE_NOTE = {
    "qualifying": ("Qualifying is the one-lap tune: peak grip for a single hot lap, "
                   "tyre life and fuel are not the priority."),
    "race": ("Race is the stint tune: consistent pace over a full stint, tyre life and "
             "fuel efficiency matter more than a single hot lap."),
}

#: Why Analyse is unavailable, in the driver's terms. Analysing a setup nobody has
#: driven has nothing to analyse — the run comes first, then the analysis of it.
ANALYSE_BLOCKED_NOTE = (
    "Analyse becomes available once you have driven and recorded a practice run on this "
    "setup — it analyses how the setup actually behaved, so it needs a run first.")


class SetupWorkspace(QWidget):
    apply_requested = pyqtSignal(dict)     # {field: value} from applied_field_values()
    discipline_changed = pyqtSignal(str)
    revert_requested = pyqtSignal(str)     # lineage node_id to revert to
    analyse_requested = pyqtSignal()       # run the setup brain on the current setup
    baseline_requested = pyqtSignal(str)   # author the initial setup for BOTH sheets
    applied_in_game_confirmed = pyqtSignal(str)  # driver entered this sheet into GT7
    tyre_change_requested = pyqtSignal(str)      # compound code to put on the car
    track_wet_changed = pyqtSignal(bool)         # driver toggled "track is wet" (rain)
    shift_rpm_changed = pyqtSignal(int)          # driver set the upshift point for this sheet
    shift_rpm_recommend_requested = pyqtSignal()  # derive the upshift point from the car
    lock_requested = pyqtSignal(str, bool)       # (discipline, lock?) — lock or reopen the setup
    car_ranges_requested = pyqtSignal()          # open the per-car min/max ranges editor
    gearing_changed = pyqtSignal(dict)           # {gear_ratios, final_drive, transmission_max_speed_kmh}
    ballast_changed = pyqtSignal(dict)           # {ballast_kg, ballast_position}
    regulation_changed = pyqtSignal(dict)        # {weight_kg, power_hp} — series BOP override

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrSetupWorkspace")
        self._vm: SetupRecommendationVM = build_recommendation_vm({})
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)

        # Title + discipline selector + active setup
        top = QHBoxLayout()
        top.addWidget(SectionHeading("GARAGE", level=1))
        top.addSpacing(_t.SPACE_LG)
        self._selector = SetupDisciplineSelector()
        self._selector.discipline_changed.connect(self.discipline_changed)
        top.addWidget(self._selector)
        top.addStretch(1)
        self._active = QLabel("")
        self._active.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        top.addWidget(self._active)
        lay.addLayout(top)

        # Tyre compound — the one setup field GT7 exposes that the Garage had no control
        # for at all, so a two-hour race could not be moved off Medium onto Hard.
        tyre_row = QHBoxLayout()
        tyre_row.setSpacing(_t.SPACE_SM)
        tyre_cap = QLabel("Tyre compound")
        tyre_cap.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        tyre_row.addWidget(tyre_cap)
        self._tyre = QComboBox()
        self._tyre.setMinimumWidth(260)
        self._tyre.setMinimumHeight(_t.TOUCH_MIN_H)
        self._tyre.setStyleSheet(
            f"QComboBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
            f"padding: 4px 10px; font-size: {_t.FS_LABEL}pt; }}")
        self._tyre.activated.connect(self._on_tyre_picked)
        tyre_row.addWidget(self._tyre)
        # "Track is wet" — GT7 broadcasts no rain, so this is the driver's signal that the
        # track is wet (for Random Weather or a track that changes). It flips qualifying
        # onto the rain tyre; qualifying always runs the softest compound for the conditions.
        from PyQt6.QtWidgets import QCheckBox
        self._wet = QCheckBox("Track is wet (rain)")
        self._wet.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wet.setToolTip(
            "GT7 doesn't report rain — tick this when the track is wet so qualifying "
            "fits the rain tyre instead of the softest slick.")
        self._wet.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        self._wet.toggled.connect(self._on_wet_toggled)
        tyre_row.addWidget(self._wet)
        self._tyre_note = QLabel("")
        self._tyre_note.setWordWrap(True)
        self._tyre_note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        tyre_row.addWidget(self._tyre_note, 1)
        lay.addLayout(tyre_row)
        self._tyre_codes: tuple = ()

        # Shift beep (RPM) — part of the CAR SETUP, per discipline, not a global setting.
        # The race sheet may short-shift where qualifying runs to the indicator, and the
        # live beep uses whichever discipline's setup matches the session being driven.
        from PyQt6.QtWidgets import QSpinBox
        shift_row = QHBoxLayout()
        shift_row.setSpacing(_t.SPACE_SM)
        shift_cap = QLabel("Shift beep (RPM)")
        shift_cap.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        shift_row.addWidget(shift_cap)
        self._shift_rpm = QSpinBox()
        self._shift_rpm.setRange(0, 20000)
        self._shift_rpm.setSingleStep(100)
        self._shift_rpm.setSuffix(" RPM")
        self._shift_rpm.setSpecialValueText("Not set")   # value 0
        self._shift_rpm.setMinimumHeight(_t.TOUCH_MIN_H)
        self._shift_rpm.setMaximumWidth(150)
        self._shift_rpm.setStyleSheet(
            f"QSpinBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
            f"padding: 4px 8px; font-size: {_t.FS_LABEL}pt; }}")
        # editingFinished (not valueChanged) so we emit once the driver settles on a
        # value, not on every spin tick.
        self._shift_rpm.editingFinished.connect(self._on_shift_rpm_edited)
        shift_row.addWidget(self._shift_rpm)
        self._shift_recommend = SecondaryActionButton("Recommend from car")
        self._shift_recommend.clicked.connect(
            lambda: self.shift_rpm_recommend_requested.emit())
        shift_row.addWidget(self._shift_recommend)
        self._shift_note = QLabel("")
        self._shift_note.setWordWrap(True)
        self._shift_note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        shift_row.addWidget(self._shift_note, 1)
        lay.addLayout(shift_row)
        self._shift_rpm_value = 0

        # Status pills
        status_row = QHBoxLayout()
        status_row.setSpacing(_t.SPACE_SM)
        self._pill_saved = StatusPill("Not saved", tone="neutral")
        self._pill_applied = StatusPill("Not applied", tone="neutral")
        self._pill_valid = StatusPill("Not validated", tone="neutral")
        for p in (self._pill_saved, self._pill_applied, self._pill_valid):
            status_row.addWidget(p)
        status_row.addStretch(1)
        # Lock — the explicit "this setup is final for the event" confirmation. It only
        # appears once the setup has converged (the engineer says lock-ready); the
        # guidance CTA "Lock the base setup" pointed here but there was nothing to click.
        self._pill_locked = StatusPill("", tone="neutral")
        self._pill_locked.setVisible(False)
        status_row.addWidget(self._pill_locked)
        self._lock_btn = SecondaryActionButton("Lock this setup")
        self._lock_btn.clicked.connect(self._on_lock_clicked)
        self._lock_btn.setVisible(False)
        status_row.addWidget(self._lock_btn)
        lay.addLayout(status_row)
        self._lock_state = (False, False)   # (lockable, locked) for the current discipline

        self._lock_hint = QLabel("")
        self._lock_hint.setWordWrap(True)
        self._lock_hint.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._lock_hint.setVisible(False)
        lay.addWidget(self._lock_hint)

        # What this discipline is, plus any transient status ("Analysing setup…").
        self._note = QLabel("")
        self._note.setWordWrap(True)
        self._note.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        lay.addWidget(self._note)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {_t.NGR_GREEN}; font-size: {_t.FS_LABEL}pt; font-weight: 600;")
        self._status.setVisible(False)
        lay.addWidget(self._status)

        # Changed-fields table
        self._primary_issue = QLabel("")
        self._primary_issue.setWordWrap(True)
        self._primary_issue.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
        lay.addWidget(self._primary_issue)

        # View toggle: Changed fields | Full setup sheet (GT7-style)
        view_row = QHBoxLayout()
        view_row.setSpacing(2)
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._btn_changed = QToolButton()
        self._btn_changed.setText("Changed fields")
        self._btn_full = QToolButton()
        self._btn_full.setText("Full setup sheet")
        self._btn_lineage = QToolButton()
        self._btn_lineage.setText("Lineage")
        self._btn_compare = QToolButton()
        self._btn_compare.setText("Compare")
        self._btn_shift_strategy = QToolButton()
        self._btn_shift_strategy.setText("Shift Strategy")
        for b in (self._btn_changed, self._btn_full, self._btn_lineage,
                  self._btn_compare, self._btn_shift_strategy):
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(SetupDisciplineSelector._qss())
            self._view_group.addButton(b)
            view_row.addWidget(b)
        view_row.addStretch(1)
        self._btn_changed.setChecked(True)
        self._btn_changed.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        self._btn_full.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        self._btn_lineage.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        self._btn_compare.clicked.connect(lambda: self._stack.setCurrentIndex(3))
        self._btn_shift_strategy.clicked.connect(
            lambda: self._stack.setCurrentIndex(4))
        lay.addLayout(view_row)

        self._stack = QStackedWidget()

        # Page 0 — changed fields
        changed_page = QWidget()
        cp = QVBoxLayout(changed_page)
        cp.setContentsMargins(0, 0, 0, 0)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Setting", "Current", "Recommended", "Δ", "Confidence"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ color: {_t.TEXT_HI}; background: {_t.CARBON_RAISED}; "
            f"alternate-background-color: {_t.CARBON}; gridline-color: {_t.HAIRLINE_SOFT}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; }}"
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        cp.addWidget(self._table, 1)

        self._empty = QLabel("No recommendation yet. Run an analysis to get setup guidance.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        cp.addWidget(self._empty)
        self._stack.addWidget(changed_page)

        # Page 1 — full GT7-style settings sheet (scrollable)
        self._sheet = GT7SettingsSheet()
        sheet_scroll = QScrollArea()
        sheet_scroll.setWidgetResizable(True)
        sheet_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sheet_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sheet_scroll.setWidget(self._sheet)
        self._stack.addWidget(sheet_scroll)

        # Page 2 — vertical setup lineage
        self._lineage = SetupLineageTree()
        self._lineage.revert_requested.connect(self.revert_requested)
        lineage_scroll = QScrollArea()
        lineage_scroll.setWidgetResizable(True)
        lineage_scroll.setFrameShape(QFrame.Shape.NoFrame)
        lineage_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lineage_scroll.setWidget(self._lineage)
        self._stack.addWidget(lineage_scroll)

        # Page 3 — setup comparison
        self._compare = SetupComparison()
        self._stack.addWidget(self._compare)

        # Page 4 — per-gear shift strategy (advisory-only, no setup-apply controls)
        from ui.components.shift_strategy_view import ShiftStrategyView
        self.shift_strategy_view = ShiftStrategyView()
        self._stack.addWidget(self.shift_strategy_view)

        # NOTE: The Transmission entry (gear ratios, final drive, top speed) is now
        # embedded in the Full setup sheet (page 1) as an editable section in the right
        # column of GT7SettingsSheet, so the driver can enter gear values without
        # switching to a separate tab. show_transmission_group() goes to page 1.
        # Bubble gearing_changed from the sheet up through the workspace so the bridge
        # wiring (which connects to garage_page.gearing_changed) still works unchanged.
        self._sheet.gearing_changed.connect(self.gearing_changed)
        self._sheet.ballast_changed.connect(self.ballast_changed)
        self._sheet.regulation_changed.connect(self.regulation_changed)

        lay.addWidget(self._stack, 1)

        # Actions
        act = QHBoxLayout()
        # The first thing a new event needs: a setup to drive. One press authors BOTH
        # sheets from the car ranges + driving profile.
        self._baseline = PrimaryActionButton("Build initial setup")
        self._baseline.clicked.connect(
            lambda: self.baseline_requested.emit(self._selector.current()))
        act.addWidget(self._baseline)
        self._analyse = SecondaryActionButton("Analyse setup")
        self._analyse.clicked.connect(lambda: self.analyse_requested.emit())
        act.addWidget(self._analyse)
        self._apply = PrimaryActionButton()
        self._apply.clicked.connect(self._on_apply)
        # Applying writes the values onto the sheet; GT7 itself can only be updated by
        # the driver typing them in. This is the explicit confirmation that they did —
        # it is what registers an ACTIVE setup for the event (nothing else can know).
        self._applied_in_game = SecondaryActionButton("I've entered this in GT7")
        self._applied_in_game.clicked.connect(
            lambda: self.applied_in_game_confirmed.emit(self._selector.current()))
        self._explain = SecondaryActionButton("Why these changes")
        self._explain.setCheckable(True)
        self._explain.toggled.connect(self._on_explain)
        self._gearbox_btn = SecondaryActionButton("Gearbox objectives")
        self._gearbox_btn.setCheckable(True)
        self._gearbox_btn.toggled.connect(self._on_gearbox)
        act.addWidget(self._apply)
        act.addWidget(self._applied_in_game)
        act.addWidget(self._explain)
        act.addWidget(self._gearbox_btn)
        self._ranges_btn = SecondaryActionButton("Set car min/max ranges…")
        self._ranges_btn.clicked.connect(lambda: self.car_ranges_requested.emit())
        act.addWidget(self._ranges_btn)
        act.addStretch(1)
        lay.addLayout(act)

        self._why = QLabel("")
        self._why.setWordWrap(True)
        self._why.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._why.setVisible(False)
        lay.addWidget(self._why)

        self._gearbox = QLabel("")
        self._gearbox.setWordWrap(True)
        self._gearbox.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._gearbox.setVisible(False)
        lay.addWidget(self._gearbox)

        self.set_recommendation(self._vm)

    # ---- population -------------------------------------------------------
    def set_recommendation(
        self, vm: SetupRecommendationVM, *, discipline: str = "race",
        active_setup: str = "", saved: bool = False, applied: bool = False,
        validated: bool = False, setup_values: Optional[dict] = None,
        lineage_nodes=None, comparisons=None, has_recorded_run: bool = True,
    ) -> None:
        if not isinstance(vm, SetupRecommendationVM):
            vm = build_recommendation_vm({})
        discipline = (discipline or "race").lower()
        if discipline not in {k for k, _ in DISCIPLINES}:
            discipline = "race"

        # Skip an identical re-render. The Garage feed repaints this panel every 750 ms
        # with the SAME recommendation; re-mutating every pill/tooltip/table cell on each
        # tick made a native tooltip window flash and follow the mouse (UAT: "flashing box
        # on the race setup"). Only render when something the driver would see changed.
        try:
            _rows_fp = tuple((r.field, r.current_value, r.recommended_value, r.delta,
                              r.confidence) for r in vm.proposed_rows())
        except Exception:
            _rows_fp = ()
        fingerprint = (
            discipline, active_setup, bool(saved), bool(applied), bool(validated),
            bool(has_recorded_run), getattr(vm.header, "primary_issue", ""),
            len(getattr(vm, "why_cards", ()) or ()),
            tuple(sorted((setup_values or {}).keys())), _rows_fp,
            tuple(str(n) for n in (lineage_nodes or ())),
            tuple(str(c) for c in (comparisons or ())),
        )
        if fingerprint == getattr(self, "_last_reco_fp", None):
            return
        self._last_reco_fp = fingerprint

        self._vm = vm
        self._lineage.set_nodes(lineage_nodes or ())
        self._compare.set_comparisons(comparisons or ())
        self._selector.set_discipline(discipline)
        self._note.setText(DISCIPLINE_NOTE.get(discipline, ""))
        self._active.setText(f"Active setup: {active_setup}" if active_setup else "Active setup: —")

        self._pill_saved.set_status("Saved" if saved else "Not saved",
                                    tone="success" if saved else "neutral",
                                    glyph="✓" if saved else "")
        self._pill_applied.set_status("Applied in GT7" if applied else "Not applied",
                                      tone="success" if applied else "neutral",
                                      glyph="✓" if applied else "")
        # "Not validated" is the single most misread state in the Garage: applying a setup
        # is not evidence for it. Validation only ever comes from a RECORDED run, so the
        # pill says which one instead of leaving the driver to guess what is missing.
        self._pill_valid.set_status(
            "Validated by a run" if validated else "No run recorded yet",
            tone="success" if validated else "neutral",
            glyph="✓" if validated else "")
        self._pill_valid.setToolTip(
            "" if validated else
            "A setup is validated by driving it and recording the run in Practice — "
            "applying it to the car is not evidence on its own.")

        self._primary_issue.setText(
            f"Primary issue: {vm.header.primary_issue}" if vm.header.primary_issue else "")
        self._primary_issue.setVisible(bool(vm.header.primary_issue))

        # GT7 tuning-menu order: the driver transcribes these into GT7 top-to-bottom,
        # so the table must read in the same order as the in-game menu.
        rows = sorted(vm.proposed_rows(), key=lambda r: gt7_field_rank(r.field))
        self._displayed_fields = tuple(r.field for r in rows)
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(r.setting))
            self._table.setItem(i, 1, QTableWidgetItem(r.current_value))
            self._table.setItem(i, 2, QTableWidgetItem(r.recommended_value))
            self._table.setItem(i, 3, QTableWidgetItem(r.delta))
            self._table.setItem(i, 4, QTableWidgetItem(r.confidence or "—"))
        self._table.setVisible(bool(rows))
        self._empty.setVisible(not rows)

        self._apply.set_action("Apply recommendation", enabled=bool(rows))
        self._explain.setVisible(bool(vm.why_cards))

        # Analyse comes AFTER a run: it analyses how the setup behaved, so with no
        # recorded run there is nothing for it to read. Build initial setup leads until
        # a setup exists; then the driver runs it; then Analyse is the next step.
        self._analyse.setEnabled(bool(has_recorded_run))
        self._analyse.setToolTip("" if has_recorded_run else ANALYSE_BLOCKED_NOTE)
        has_setup = bool(setup_values)
        self._baseline.setText("Rebuild initial setup" if has_setup else "Build initial setup")
        self._baseline.setToolTip(
            "Authors a complete setup for BOTH the Race and Qualifying sheets from the "
            "car's ranges and your driving profile.")
        if not rows:
            if not has_setup:
                self._empty.setText(
                    "No setup yet — press “Build initial setup” to author the Race and "
                    "Qualifying sheets, then drive a practice run.")
            elif not has_recorded_run:
                self._empty.setText("No recommendation yet. " + ANALYSE_BLOCKED_NOTE)
            else:
                self._empty.setText(
                    "No recommendation yet. Press “Analyse setup” to read the run you "
                    "recorded and get the next change.")

        # Compose the engineering explanation (progressive disclosure).
        if vm.why_cards:
            parts = []
            for c in vm.why_cards:
                bits = [f"• {c.setting}: {c.rationale}" if c.rationale else f"• {c.setting}"]
                if c.symptom:
                    bits.append(f"(addresses: {c.symptom})")
                parts.append(" ".join(bits))
            self._why.setText("\n".join(parts))
        else:
            self._why.setText("")

        # Discipline-specific gearbox/RPM objectives (never silently identical).
        head = gearbox_headline(discipline)
        bullets = gearbox_objectives(discipline)
        self._gearbox.setText(
            (head + "\n" if head else "") + "\n".join(f"• {b}" for b in bullets))

        # Full GT7-style settings sheet — the changed fields are highlighted.
        changed = {r.field for r in vm.proposed_rows() if r.field}
        self._sheet.set_setup(setup_values, changed_fields=changed)
        # Load the current ballast into the editable ballast entry (values live in the
        # setup dict; a scalar or [value] shape is accepted).
        sv = setup_values or {}

        def _scalar(v):
            return (v[0] if isinstance(v, (list, tuple)) and v else v) or 0

        try:
            if hasattr(self._sheet, "set_ballast"):
                self._sheet.set_ballast(
                    ballast_kg=float(_scalar(sv.get("ballast_kg")) or 0.0),
                    ballast_position=int(_scalar(sv.get("ballast_position")) or 0))
            if hasattr(self._sheet, "set_regulation"):
                self._sheet.set_regulation(
                    weight_kg=float(_scalar(sv.get("weight_kg")) or 0.0),
                    power_hp=float(_scalar(sv.get("power_hp")) or 0.0))
        except Exception:
            pass
        self._btn_full.setEnabled(bool(setup_values))
        if not setup_values:
            self._btn_changed.setChecked(True)
            self._stack.setCurrentIndex(0)

    def set_tyre_choice(self, choice, current_code: str = "") -> None:
        """Render the compounds this event allows, with the current one selected.

        Selecting is a real setup change, so it is written through the same apply path
        as everything else — the combo only reports the driver's choice.
        """
        try:
            options = tuple(getattr(choice, "options", ()) or ())
            new_codes = tuple(o.code for o in options)
            # The 750 ms feed calls this every tick. Never rebuild the combo while the
            # driver is interacting with it — clearing an open popup snaps it shut and
            # resets the selection ("dropdown glitch"). And when the option set is
            # unchanged, only move the selection index, never clear()/re-add — the churn
            # is what closed the popup and reset the choice.
            interacting = self._tyre.hasFocus() or self._tyre.view().isVisible()
            if new_codes == self._tyre_codes:
                if interacting:
                    return
                if current_code in self._tyre_codes:
                    idx = self._tyre_codes.index(current_code)
                    if self._tyre.currentIndex() != idx:
                        self._tyre.blockSignals(True)
                        self._tyre.setCurrentIndex(idx)
                        self._tyre.blockSignals(False)
            else:
                if interacting:
                    # Options genuinely changed but the driver is mid-interaction; defer
                    # the rebuild to the next feed rather than yanking the popup away.
                    return
                self._tyre_codes = new_codes
                self._tyre.blockSignals(True)
                self._tyre.clear()
                for o in options:
                    self._tyre.addItem(o.label)
                if current_code in self._tyre_codes:
                    self._tyre.setCurrentIndex(self._tyre_codes.index(current_code))
                self._tyre.blockSignals(False)
            self._tyre.setVisible(bool(options))

            note = str(getattr(choice, "guidance", "") or "")
            rec = str(getattr(choice, "recommended_code", "") or "")
            if rec and rec != current_code:
                reason = str(getattr(choice, "recommendation_reason", "") or "")
                note = f"→ {choice.name_for(rec)}. {reason}" if reason else note
            if not getattr(choice, "restricted", False) and options:
                note += "  (no compound restriction on this event)"
            self._tyre_note.setText(note)
        except Exception:  # pragma: no cover - defensive
            pass

    def _on_tyre_picked(self, index: int) -> None:
        if 0 <= index < len(self._tyre_codes):
            self.tyre_change_requested.emit(self._tyre_codes[index])

    def _on_wet_toggled(self, checked: bool) -> None:
        self.track_wet_changed.emit(bool(checked))

    def set_track_wet(self, wet: bool, enabled: bool = True) -> None:
        """Reflect the effective wet state without re-emitting (the caller drives it).

        ``enabled`` is False for a FIXED-weather event: the condition is decided by the
        event, so the box shows it but the driver cannot override it. Only Random Weather
        leaves the toggle live. Skipped while the driver has the box focused, so the 750 ms
        feed never flips a tick the driver just made.
        """
        try:
            if self._wet.isEnabled() != bool(enabled):
                self._wet.setEnabled(bool(enabled))
                self._wet.setText("Track is wet (rain)" if enabled
                                  else "Track is wet (rain) — set by event weather")
            if self._wet.hasFocus():
                return
            if self._wet.isChecked() != bool(wet):
                self._wet.blockSignals(True)
                self._wet.setChecked(bool(wet))
                self._wet.blockSignals(False)
        except Exception:  # pragma: no cover - defensive
            pass

    def set_shift_rpm(self, value: int = 0, note: str = "") -> None:
        """Show the upshift point for the current discipline's sheet.

        Setting the spin box must not re-emit ``shift_rpm_changed`` — that would echo a
        value the caller just fed back as though the driver had typed it. And while the
        driver is actually EDITING the field, the periodic 750 ms feed must not overwrite
        it — that clobbered the value mid-type and it "changed straight back".
        """
        try:
            v = max(0, int(value or 0))
        except (TypeError, ValueError):
            v = 0
        if self._shift_rpm.hasFocus():
            # Keep the note fresh but leave the value the driver is typing alone.
            self._shift_note.setText(str(note or ""))
            self._shift_note.setVisible(bool(note))
            return
        self._shift_rpm_value = v
        self._shift_rpm.blockSignals(True)
        self._shift_rpm.setValue(v)
        self._shift_rpm.blockSignals(False)
        self._shift_note.setText(str(note or ""))
        self._shift_note.setVisible(bool(note))

    def _on_shift_rpm_edited(self) -> None:
        v = int(self._shift_rpm.value())
        if v == self._shift_rpm_value:
            return                      # editingFinished fires even when nothing changed
        self._shift_rpm_value = v
        self.shift_rpm_changed.emit(v)

    def set_lock_state(self, lockable: bool = False, locked: bool = False,
                       hint: str = "", discipline: str = "", lock_label: str = "") -> None:
        """Show the lock control for a discipline.

        ``lockable`` is whether the setup has converged enough for the engineer to permit
        a lock; ``locked`` is whether the driver has already confirmed it. ``discipline``
        is what gets locked — it may differ from the selected tab (the engineer can
        nominate "base", which underlies both sheets and has no tab of its own), so the
        button carries an explicit label. Locking is never inferred.
        """
        self._lock_state = (bool(lockable), bool(locked))
        self._lock_target = str(discipline or self._selector.current())
        self._pill_locked.setVisible(bool(locked))
        if locked:
            self._pill_locked.set_status("Locked", tone="success", glyph="🔒")
        self._lock_btn.setVisible(bool(lockable) or bool(locked))
        self._lock_btn.setText("Reopen setup" if locked
                               else (lock_label or "Lock this setup"))
        self._lock_hint.setText(str(hint or ""))
        # Show the hint whenever there is one — including when the setup is NOT yet lockable,
        # so the driver is told why the Lock button isn't there and how to reach it, instead
        # of the "Confirm and protect" objective pointing at a control that's hidden.
        self._lock_hint.setVisible(bool(hint))

    def _on_lock_clicked(self) -> None:
        _lockable, locked = self._lock_state
        # Clicking toggles: lock when open, reopen when locked. The target is what the
        # feed nominated, not necessarily the selected tab.
        target = getattr(self, "_lock_target", "") or self._selector.current()
        self.lock_requested.emit(target, not locked)

    def set_status(self, text: str) -> None:
        """Show (or clear, with "") a transient status line — e.g. "Analysing setup…".

        The workspace performs no engineering; the caller that actually starts the
        work reports its progress here so a pressed button is never silent.
        """
        text = str(text or "")
        self._status.setText(text)
        self._status.setVisible(bool(text))

    def current_discipline(self) -> str:
        return self._selector.current()

    def set_discipline(self, key: str) -> None:
        """Select a discipline tab programmatically (e.g. when Begin Qualifying is pressed).

        Reflects the choice in the segmented control without re-emitting
        ``discipline_changed`` — the caller is the one driving the switch, so echoing the
        signal back would re-enter the same handler.
        """
        self._selector.set_discipline(key)

    def displayed_fields(self) -> tuple:
        """The changed-field keys in the order the table shows them (GT7 menu order)."""
        return getattr(self, "_displayed_fields", ())

    # ---- signals ----------------------------------------------------------
    def _on_apply(self):
        # Shown == applied: the applied dict comes from the SAME rows displayed.
        self.apply_requested.emit(self._vm.applied_field_values())

    def _on_explain(self, checked: bool):
        self._why.setVisible(bool(checked))

    def _on_gearbox(self, checked: bool):
        self._gearbox.setVisible(bool(checked))

    def show_shift_strategy_tab(self) -> None:
        """Switch the Garage view to the Shift Strategy sub-tab."""
        self._btn_shift_strategy.setChecked(True)
        self._stack.setCurrentIndex(4)

    def show_transmission_group(self) -> None:
        """Switch to the Full setup sheet (where Transmission entry is embedded).

        Called by the bridge when the Shift Strategy stepper's "Enter gear ratios" step
        is pressed — the driver lands on the full setup page where the editable
        Transmission section is in the right column, instead of the old separate tab.
        """
        self._btn_full.setChecked(True)
        self._stack.setCurrentIndex(1)
        spins = getattr(self._sheet, "_gear_spins", [])
        if spins:
            spins[0].setFocus()

    def set_gearing(self, gear_ratios=(), final_drive: float = 0.0,
                    transmission_max_speed_kmh: float = 0.0) -> None:
        """Load the discipline's gearing values into the Transmission spins.

        Delegates to GT7SettingsSheet.set_gearing which owns the spins (FIX 4: gearing
        entry moved into the full setup page). Focus guard and blockSignals are handled
        there, matching the same pattern as set_shift_rpm.
        """
        if hasattr(self._sheet, "set_gearing"):
            self._sheet.set_gearing(
                gear_ratios=gear_ratios,
                final_drive=final_drive,
                transmission_max_speed_kmh=transmission_max_speed_kmh)
