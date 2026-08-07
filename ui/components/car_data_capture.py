"""Car data capture — record what GT7 actually says about a car (UAT 2026-08-07 A7).

The engineering brain has no real data for any car in the game. ``car_specs.json``
holds 579 cars with five facts each (category, PP, power, weight, aspiration);
``car_setup_ranges.json`` covers four cars and holds tuning PREFERENCES rather than
slider limits; nothing anywhere holds a stock ride height, a stock spring rate, a gear
count, a redline or a single GT7 slider minimum, maximum or step. Until that changes,
every setup rests on a class archetype — which is a real engineering position, but not
one derived for the car in front of you.

This panel is how that changes: the driver opens the car's tuning screen in GT7 once
and types in what it shows. It is deliberately built so a PARTIAL capture is useful —
every field is independent, and anything left blank keeps the class default and says
so. Capturing four fields for the car you actually race beats capturing nothing for
579, so the panel never asks for completeness and never blocks on it.

Writes only ``data/car_gt7_ranges.json`` via ``data.car_parameter_model``. No AI, no
network, no telemetry.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget,
)

from ui import ngr_theme as _t
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton

#: The parameters worth capturing, in the order GT7's own tuning screen lists them,
#: with the precision each needs. (field, label, decimals)
CAPTURE_FIELDS: tuple = (
    ("ride_height_front", "Ride height — front (mm)", 0),
    ("ride_height_rear", "Ride height — rear (mm)", 0),
    ("springs_front", "Natural frequency — front (Hz)", 2),
    ("springs_rear", "Natural frequency — rear (Hz)", 2),
    ("dampers_front_comp", "Damper compression — front", 0),
    ("dampers_front_ext", "Damper extension — front", 0),
    ("dampers_rear_comp", "Damper compression — rear", 0),
    ("dampers_rear_ext", "Damper extension — rear", 0),
    ("arb_front", "Anti-roll bar — front", 0),
    ("arb_rear", "Anti-roll bar — rear", 0),
    ("camber_front", "Camber — front (°)", 1),
    ("camber_rear", "Camber — rear (°)", 1),
    ("toe_front", "Toe — front (°)", 2),
    ("toe_rear", "Toe — rear (°)", 2),
    ("aero_front", "Downforce — front", 0),
    ("aero_rear", "Downforce — rear", 0),
    ("lsd_initial", "LSD initial torque", 0),
    ("lsd_accel", "LSD acceleration sensitivity", 0),
    ("lsd_decel", "LSD braking sensitivity", 0),
    ("brake_bias", "Brake balance", 0),
    ("ballast_kg", "Ballast (kg)", 0),
    ("ballast_position", "Ballast position", 0),
    ("power_restrictor", "Power restrictor (%)", 0),
)

#: Gear ratios are captured as stock values only — there is no slider range for them
#: in the sense the other fields have.
GEAR_FIELDS: tuple = tuple(f"gear_{i}" for i in range(1, 7))

_BLANK = -99999.0     # spinbox "not captured" sentinel, shown as an em dash


def _spin(decimals: int, tip: str) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setDecimals(decimals)
    w.setRange(_BLANK, 100000.0)
    w.setValue(_BLANK)
    w.setSpecialValueText("—")          # the sentinel reads as "not captured"
    w.setMinimumHeight(_t.TOUCH_MIN_H)
    w.setToolTip(tip)
    w.setStyleSheet(
        f"QDoubleSpinBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
        f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
        f"padding: 2px 6px; font-size: {_t.FS_LABEL}pt; }}")
    return w


def _value_or_none(spin: QDoubleSpinBox) -> Optional[float]:
    v = spin.value()
    return None if v <= _BLANK else v


class CarDataCapturePanel(QWidget):
    """Type in what GT7 shows for one car, once.

    ``capture_saved(car_name)`` fires after a successful write so the caller can
    re-author the setup against the new data.
    """

    capture_saved = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._car = ""
        self._rows: dict = {}          # field -> (min, max, step, stock)
        self._gears: dict = {}         # gear_N -> spin
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(_t.SPACE_SM)

        self._title = QLabel("Car data")
        self._title.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H2}pt; font-weight: 700;")
        outer.addWidget(self._title)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        outer.addWidget(self._status)

        intro = QLabel(
            "Open this car's tuning screen in GT7 and type in what it shows. Every "
            "field is independent — fill in what you can see and leave the rest blank; "
            "anything blank keeps the class default and is marked as such. Four real "
            "numbers for the car you race beat none for all 579.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setHorizontalSpacing(_t.SPACE_SM)
        grid.setVerticalSpacing(4)

        for col, head in enumerate(
                ("Parameter", "Min", "Max", "Step", "Stock", "Now using")):
            lbl = QLabel(head)
            lbl.setStyleSheet(
                f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt; font-weight: 700;")
            grid.addWidget(lbl, 0, col)

        for row, (field, label, decimals) in enumerate(CAPTURE_FIELDS, start=1):
            cap = QLabel(label)
            cap.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
            grid.addWidget(cap, row, 0)
            lo = _spin(decimals, f"Lowest value GT7 allows for {label}.")
            hi = _spin(decimals, f"Highest value GT7 allows for {label}.")
            step = _spin(max(decimals, 2), f"Smallest increment the {label} slider moves in.")
            stock = _spin(decimals, f"The car's stock (untuned) {label}.")
            for col, w in enumerate((lo, hi, step, stock), start=1):
                grid.addWidget(w, row, col)
            effective = QLabel("—")
            effective.setStyleSheet(
                f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
            grid.addWidget(effective, row, 5)
            self._rows[field] = (lo, hi, step, stock, effective)

        gear_row = len(CAPTURE_FIELDS) + 1
        gear_head = QLabel("Gearbox — stock ratios, gear count and redline")
        gear_head.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt; font-weight: 700;")
        grid.addWidget(gear_head, gear_row, 0, 1, 6)
        for i, field in enumerate(GEAR_FIELDS):
            r = gear_row + 1 + i
            cap = QLabel(f"Gear {i + 1} ratio")
            cap.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
            grid.addWidget(cap, r, 0)
            spin = _spin(3, f"Stock ratio for gear {i + 1}.")
            grid.addWidget(spin, r, 4)
            self._gears[field] = spin

        r = gear_row + 1 + len(GEAR_FIELDS)
        cap = QLabel("Number of gears")
        cap.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
        grid.addWidget(cap, r, 0)
        self._num_gears = QSpinBox()
        self._num_gears.setRange(0, 10)
        self._num_gears.setSpecialValueText("—")
        self._num_gears.setMinimumHeight(_t.TOUCH_MIN_H)
        self._num_gears.setToolTip(
            "How many forward gears this car has. Without it no gearbox is authored "
            "at all — the app says 'keep the stock gearing' instead of guessing.")
        grid.addWidget(self._num_gears, r, 4)

        cap = QLabel("Redline (rpm)")
        cap.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
        grid.addWidget(cap, r + 1, 0)
        self._redline = _spin(0, "Engine redline in rpm — sets where each ratio lands.")
        grid.addWidget(self._redline, r + 1, 4)

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(_t.SPACE_SM)
        self._save = PrimaryActionButton("Save car data")
        self._save.clicked.connect(self._on_save)
        buttons.addWidget(self._save)
        self._reload = SecondaryActionButton("Reload from library")
        self._reload.clicked.connect(lambda: self.set_car(self._car))
        buttons.addWidget(self._reload)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        self._result = QLabel("")
        self._result.setWordWrap(True)
        self._result.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        outer.addWidget(self._result)

    # ------------------------------------------------------------------- load
    def set_car(self, car_name: str) -> None:
        """Point the panel at a car and load whatever has already been captured."""
        self._car = (car_name or "").strip()
        self._title.setText(f"Car data — {self._car}" if self._car else "Car data")
        if not self._car:
            self._status.setText("No car selected — activate an event first.")
            self._set_enabled(False)
            return
        self._set_enabled(True)

        try:
            from data.car_parameter_model import resolve_parameter_model
            model = resolve_parameter_model(self._car)
        except Exception:
            self._status.setText("Could not read the car data library.")
            return

        if model.is_archetype_only:
            self._status.setText(
                f"Running on {model.archetype} class defaults — nothing has been "
                f"captured for this car yet. Every value below is a class position, "
                f"not a measurement of this car.")
        else:
            self._status.setText(
                f"{len(model.captured_fields)} field(s) captured for this car; "
                f"the rest use {model.archetype} class defaults.")

        for field, (lo, hi, step, stock, effective) in self._rows.items():
            spec = model.spec(field)
            for w in (lo, hi, step, stock):
                w.setValue(_BLANK)
            if spec is None:
                effective.setText("—")
                continue
            if spec.legal_tier == "captured":
                lo.setValue(spec.legal_low)
                hi.setValue(spec.legal_high)
            if spec.step_tier == "captured":
                step.setValue(spec.step)
            if spec.anchor_tier == "captured" and spec.anchor is not None:
                stock.setValue(spec.anchor)
            effective.setText(self._effective_text(spec))

        for field, spin in self._gears.items():
            spin.setValue(model.stock_ratios.get(field, _BLANK))
        self._num_gears.setValue(int(model.num_gears or 0))
        self._redline.setValue(
            model.redline_rpm if model.redline_rpm is not None else _BLANK)
        self._result.setText("")

    @staticmethod
    def _effective_text(spec) -> str:
        """What this field is running on right now, and where that came from."""
        tier = {"captured": "your capture", "curated": "curated for this car",
                "archetype": "class default", "generic": "generic fallback"}
        anchor = "—" if spec.anchor is None else f"{spec.anchor:g}"
        return (f"{anchor}  ({tier.get(spec.anchor_tier, spec.anchor_tier)}), "
                f"range {spec.legal_low:g}–{spec.legal_high:g} "
                f"({tier.get(spec.legal_tier, spec.legal_tier)})")

    def _set_enabled(self, on: bool) -> None:
        self._save.setEnabled(on)
        self._reload.setEnabled(on)

    # ------------------------------------------------------------------- save
    def collect(self) -> dict:
        """The capture entry for the current form state. Blank fields are omitted."""
        ranges: dict = {}
        stock: dict = {}
        for field, (lo, hi, step, stock_spin, _eff) in self._rows.items():
            bounds: dict = {}
            lo_v, hi_v, step_v = (_value_or_none(lo), _value_or_none(hi),
                                  _value_or_none(step))
            # A min without a max (or vice versa) is not a range — record neither
            # rather than half of one, which would clamp against a bound nobody gave.
            if lo_v is not None and hi_v is not None and hi_v >= lo_v:
                bounds["min"], bounds["max"] = lo_v, hi_v
            if step_v is not None and step_v > 0:
                bounds["step"] = step_v
            if bounds:
                ranges[field] = bounds
            stock_v = _value_or_none(stock_spin)
            if stock_v is not None:
                stock[field] = stock_v

        for field, spin in self._gears.items():
            v = _value_or_none(spin)
            if v is not None:
                stock[field] = v

        entry: dict = {}
        if ranges:
            entry["ranges"] = ranges
        if stock:
            entry["stock"] = stock
        gears = int(self._num_gears.value() or 0)
        if gears > 0:
            entry["num_gears"] = gears
        redline = _value_or_none(self._redline)
        if redline is not None and redline > 0:
            entry["redline_rpm"] = redline
        return entry

    def _on_save(self) -> None:
        if not self._car:
            self._result.setText("No car selected.")
            return
        entry = self.collect()
        if not entry:
            self._result.setText(
                "Nothing to save — every field is blank. That is fine; the car keeps "
                "its class defaults.")
            return
        try:
            from data.car_parameter_model import save_car_capture
            ok = save_car_capture(self._car, entry)
        except Exception as exc:
            self._result.setText(f"Could not save: {exc}")
            return
        if not ok:
            self._result.setText("Could not save — the car data library rejected it.")
            return
        n = len(entry.get("ranges") or {}) + len(entry.get("stock") or {})
        self._result.setText(
            f"Saved {n} value(s) for {self._car}. Rebuild the setup to use them.")
        self.set_car(self._car)
        self.capture_saved.emit(self._car)
