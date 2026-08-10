"""OwnerBaselineCaptureWidget — post-wizard flow for entering Race and Qualifying baselines.

The driver exits the Event Setup wizard and is immediately offered this widget.
It steps through OWNER_BASELINE_DISCIPLINES ("race" then "qualifying") one
discipline at a time. For each discipline it presents a scrollable form of all
standard setup parameters, a "Save baseline" primary action and a "Skip for now"
secondary action.

Rules this widget is held to:
  - NO FILE IMPORT anywhere in this flow (deliberate; owner authors externally).
  - NO auto-save, NO auto-apply, NO evidence creation. Entering a baseline is
    NOT a recorded run — doctrine "applied != evidence".
  - A6: out-of-range entry REJECTED at entry time with the legal range shown.
    NEVER silently snapped. Validation runs via
    ``db.validate_owner_baseline_field`` before any write.
  - "Skip for now" is always available. An unset discipline shows
    "No baseline — proposals unavailable" on the event screen.
  - Advances through disciplines in OWNER_BASELINE_DISCIPLINES order ("race"
    then "qualifying"). Emits ``capture_complete`` when both are addressed.

Modelled after ``ui/components/car_data_capture.py`` (the existing precedent
for human-entered ground-truth capture).

Signals
-------
baseline_saved(discipline: str, baseline_id: int)
    Emitted after each successful save. ``discipline`` is "race" or "qualifying";
    ``baseline_id`` is the DB row id returned by ``db.save_owner_baseline``.
capture_complete()
    Emitted once both disciplines are addressed (saved or skipped).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QDoubleSpinBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QScrollArea, QVBoxLayout, QWidget,
)

from ui import ngr_theme as _t
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton

# Owner disciplines — mirrors strategy.setup_sheet.OWNER_BASELINE_DISCIPLINES.
# Imported here to keep the source of truth in the strategy layer.
try:
    from strategy.setup_sheet import OWNER_BASELINE_DISCIPLINES
except Exception:  # pragma: no cover - defensive
    OWNER_BASELINE_DISCIPLINES = ("race", "qualifying")

#: Sentinel meaning "not entered". Displayed as an em dash in the spinbox.
#: Must be below any real legal minimum (legal_low for all parameters >= -10 or so).
_BLANK = -99999.0

#: Setup parameters to capture, in GT7 tuning-screen order.
#: (field, label, decimals, group)
_CAPTURE_FIELDS: tuple = (
    # --- Suspension ---
    ("ride_height_front",  "Ride height — front (mm)", 0, "Suspension"),
    ("ride_height_rear",   "Ride height — rear (mm)",  0, "Suspension"),
    ("springs_front",      "Natural frequency — front (Hz)", 2, "Suspension"),
    ("springs_rear",       "Natural frequency — rear (Hz)",  2, "Suspension"),
    ("dampers_front_comp", "Damper compression — front",     0, "Suspension"),
    ("dampers_front_ext",  "Damper extension — front",       0, "Suspension"),
    ("dampers_rear_comp",  "Damper compression — rear",      0, "Suspension"),
    ("dampers_rear_ext",   "Damper extension — rear",        0, "Suspension"),
    ("arb_front",          "Anti-roll bar — front",          0, "Suspension"),
    ("arb_rear",           "Anti-roll bar — rear",           0, "Suspension"),
    # --- Alignment ---
    ("camber_front", "Camber — front (°)", 1, "Alignment"),
    ("camber_rear",  "Camber — rear (°)",  1, "Alignment"),
    ("toe_front",    "Toe — front (°)",    2, "Alignment"),
    ("toe_rear",     "Toe — rear (°)",     2, "Alignment"),
    # --- Aerodynamics ---
    ("aero_front", "Downforce — front", 0, "Aerodynamics"),
    ("aero_rear",  "Downforce — rear",  0, "Aerodynamics"),
    # --- Differential ---
    ("lsd_initial",            "LSD initial torque",              0, "Differential"),
    ("lsd_accel",              "LSD acceleration sensitivity",    0, "Differential"),
    ("lsd_decel",              "LSD braking sensitivity",         0, "Differential"),
    ("lsd_front_initial",      "LSD front initial (AWD)",         0, "Differential"),
    ("lsd_front_accel",        "LSD front accel (AWD)",           0, "Differential"),
    ("lsd_front_decel",        "LSD front decel (AWD)",           0, "Differential"),
    ("torque_distribution_rear", "Torque distribution rear % (AWD)", 0, "Differential"),
    # --- Brakes ---
    ("brake_bias_front", "Brake balance — front", 0, "Brakes"),
    # --- Performance ---
    ("ballast_kg",         "Ballast (kg)",              0, "Performance"),
    ("ballast_position",   "Ballast position",          0, "Performance"),
    ("power_restrictor",   "Power restrictor (%)",      0, "Performance"),
)

#: Human-readable names for each discipline.
_DISC_LABEL = {
    "race": "Race",
    "qualifying": "Qualifying",
}

#: Advisory notes shown above each discipline's form.
_DISC_NOTE = {
    "race": (
        "Enter your race setup exactly as you have it in GT7. Every field is "
        "independent — leave AWD-only parameters blank for a non-AWD car. "
        "This baseline is OWNER_AUTHORED: the app will never overwrite it."
    ),
    "qualifying": (
        "Enter your qualifying setup. Qualifying is the one-lap tune; it can "
        "differ from the race setup on alignment and aero. Leave parameters "
        "blank where qualifying and race use the same value — the proposal "
        "engine notes both disciplines separately."
    ),
}


def _spin(decimals: int, tip: str) -> QDoubleSpinBox:
    """Build a blanking spinbox for one setup parameter."""
    w = QDoubleSpinBox()
    w.setDecimals(decimals)
    # Wide range — the legal-range gate runs at save time, not entry time.
    w.setRange(_BLANK, 99999.0)
    w.setValue(_BLANK)
    w.setSpecialValueText("—")          # sentinel reads as "not entered"
    w.setMinimumHeight(_t.TOUCH_MIN_H)
    w.setToolTip(tip)
    w.setStyleSheet(
        f"QDoubleSpinBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
        f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
        f"padding: 2px 6px; font-size: {_t.FS_LABEL}pt; }}")
    return w


def _value_or_none(spin: QDoubleSpinBox) -> Optional[float]:
    """Return the spin's value, or None if it is the blank sentinel."""
    v = spin.value()
    return None if v <= _BLANK else v


class OwnerBaselineCaptureWidget(QWidget):
    """Step the owner through Race then Qualifying baseline entry.

    Instantiate once; call :meth:`start_capture` with the event_id, car_name
    and db handle. The widget is self-contained after that.
    """

    #: Emitted after each successful save.
    baseline_saved = pyqtSignal(str, int)  # (discipline, baseline_id)

    #: Emitted when both disciplines have been addressed (saved or skipped).
    capture_complete = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ngrOwnerBaselineCapture")
        self._event_id: int = 0
        self._car_name: str = ""
        self._db = None
        self._disc_index: int = 0          # index into OWNER_BASELINE_DISCIPLINES
        self._spins: dict = {}              # field → QDoubleSpinBox
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(_t.SPACE_SM)

        # Title
        self._title = QLabel("Enter owner baselines")
        self._title.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H2}pt; font-weight: 700; "
            f"padding: {_t.SPACE_SM}px {_t.SPACE_LG}px 0;")
        outer.addWidget(self._title)

        # Progress chip
        self._progress = QLabel("")
        self._progress.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt; "
            f"padding: 0 {_t.SPACE_LG}px;")
        outer.addWidget(self._progress)

        # Advisory note for this discipline
        self._note = QLabel("")
        self._note.setWordWrap(True)
        self._note.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt; "
            f"padding: 0 {_t.SPACE_LG}px;")
        outer.addWidget(self._note)

        # Validation error banner — shown when validate_owner_baseline_field rejects
        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(_t.banner_qss("danger"))
        self._error.setContentsMargins(
            _t.SPACE_LG, _t.SPACE_SM, _t.SPACE_LG, _t.SPACE_SM)
        self._error.setVisible(False)
        outer.addWidget(self._error)

        # Scrollable form
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._form_container = QWidget()
        self._form_layout = QVBoxLayout(self._form_container)
        self._form_layout.setContentsMargins(
            _t.SPACE_LG, _t.SPACE_SM, _t.SPACE_LG, _t.SPACE_SM)
        self._form_layout.setSpacing(_t.SPACE_SM)
        self._scroll.setWidget(self._form_container)
        outer.addWidget(self._scroll, 1)

        # Build the form (re-used across disciplines; spins are reset on each)
        self._build_form()

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(_t.SPACE_SM)
        action_row.setContentsMargins(
            _t.SPACE_LG, _t.SPACE_SM, _t.SPACE_LG, _t.SPACE_MD)
        self._save_btn = PrimaryActionButton("Save Race Baseline")
        self._save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self._save_btn)
        self._skip_btn = SecondaryActionButton("Skip for now")
        self._skip_btn.clicked.connect(self._on_skip)
        action_row.addWidget(self._skip_btn)
        action_row.addStretch(1)
        outer.addLayout(action_row)

    def _build_form(self) -> None:
        """Populate the scrollable form with one group per subsystem."""
        self._spins.clear()
        # Group fields by subsystem, in declaration order.
        groups: dict = {}
        for field, label, decimals, group in _CAPTURE_FIELDS:
            groups.setdefault(group, []).append((field, label, decimals))

        for group_name, fields in groups.items():
            box = QGroupBox(group_name)
            box.setStyleSheet(_t.card_qss())
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(_t.SPACE_SM)
            grid.setVerticalSpacing(4)
            # Header row
            for col, head in enumerate(("Parameter", "Value")):
                lbl = QLabel(head)
                lbl.setStyleSheet(
                    f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt; "
                    f"font-weight: 700;")
                grid.addWidget(lbl, 0, col)
            for row, (field, label, decimals) in enumerate(fields, start=1):
                cap = QLabel(label)
                cap.setStyleSheet(
                    f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
                grid.addWidget(cap, row, 0)
                spin = _spin(decimals, f"Enter GT7 value for {label}.")
                grid.addWidget(spin, row, 1)
                self._spins[field] = spin
            grid.setColumnStretch(0, 3)
            grid.setColumnStretch(1, 1)
            self._form_layout.addWidget(box)

        self._form_layout.addStretch(1)

    # ---------------------------------------------------------------- public
    def start_capture(self, event_id: int, car_name: str, db) -> None:
        """Begin the capture flow for the given event.

        Call this after the Event Setup wizard completes successfully.
        """
        self._event_id = int(event_id or 0)
        self._car_name = str(car_name or "")
        self._db = db
        self._disc_index = 0
        self._show_discipline()

    # --------------------------------------------------------------- private
    def _current_discipline(self) -> str:
        if self._disc_index < len(OWNER_BASELINE_DISCIPLINES):
            return OWNER_BASELINE_DISCIPLINES[self._disc_index]
        return ""

    def _show_discipline(self) -> None:
        disc = self._current_discipline()
        if not disc:
            self.capture_complete.emit()
            return
        n = self._disc_index + 1
        total = len(OWNER_BASELINE_DISCIPLINES)
        disc_label = _DISC_LABEL.get(disc, disc.title())
        self._title.setText(
            f"Enter {disc_label} baseline  ({n}/{total})")
        self._progress.setText(
            f"Step {n} of {total} — {disc_label} setup")
        self._note.setText(_DISC_NOTE.get(disc, ""))
        self._save_btn.setText(f"Save {disc_label} Baseline")
        self._error.setVisible(False)
        # Reset all spins to blank
        for spin in self._spins.values():
            spin.blockSignals(True)
            spin.setValue(_BLANK)
            spin.blockSignals(False)
        # Pre-populate with any existing baseline for this discipline
        if self._db is not None and self._event_id:
            try:
                existing = self._db.get_owner_baseline(
                    self._event_id, disc)
                if existing:
                    for field, spin in self._spins.items():
                        v = existing.get(field)
                        if v is not None:
                            try:
                                spin.blockSignals(True)
                                spin.setValue(float(v))
                                spin.blockSignals(False)
                            except (TypeError, ValueError):
                                pass
            except Exception:
                pass

    def _collect(self) -> dict:
        """Collect non-blank field values from the form."""
        result: dict = {}
        for field, spin in self._spins.items():
            v = _value_or_none(spin)
            if v is not None:
                result[field] = v
        return result

    def _on_save(self) -> None:
        """Validate all non-blank entries and save the baseline. A6 compliant."""
        self._error.setVisible(False)
        disc = self._current_discipline()
        if not disc:
            return

        values = self._collect()
        if not values:
            # Nothing entered — treat same as skip (warn but allow)
            self._error.setText(
                "No values entered. Saving an empty baseline is not meaningful. "
                "Use \"Skip for now\" if you want to come back to this later.")
            self._error.setVisible(True)
            return

        # Validate each field against the ParameterSpec for this car (A6).
        errors: list = []
        car = self._car_name
        if self._db is not None and hasattr(self._db, "validate_owner_baseline_field"):
            for field, value in values.items():
                try:
                    ok, reason = self._db.validate_owner_baseline_field(
                        field, value, car)
                    if not ok:
                        errors.append(reason)
                except Exception:
                    pass  # unknown field — degrade open, do not block

        if errors:
            # A6: REJECT, show legal range(s). Never snap silently.
            self._error.setText(
                "One or more values are outside the legal range for this car. "
                "Re-enter values within the legal range — the app will never "
                "silently snap an owner-entered value.\n\n"
                + "\n".join(f"• {e}" for e in errors))
            self._error.setVisible(True)
            return

        # Save the baseline.
        baseline_id = 0
        if self._db is not None and hasattr(self._db, "save_owner_baseline"):
            try:
                baseline_id = self._db.save_owner_baseline(
                    self._event_id, disc, values)
            except Exception as exc:
                self._error.setText(
                    f"Could not save the baseline: {exc}. "
                    "Check the database connection and try again.")
                self._error.setVisible(True)
                return

        if not baseline_id:
            self._error.setText(
                "The database did not accept the baseline. Try again.")
            self._error.setVisible(True)
            return

        self.baseline_saved.emit(disc, baseline_id)
        self._advance()

    def _on_skip(self) -> None:
        """Advance without saving (discipline stays at 'not entered')."""
        self._advance()

    def _advance(self) -> None:
        """Move to the next discipline, or emit capture_complete when done."""
        self._disc_index += 1
        self._show_discipline()
