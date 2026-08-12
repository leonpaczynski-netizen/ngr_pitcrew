"""Car — what this car will actually accept.

GT7's suspension, aero and gearing endpoints are per-car and derived from
chassis data, so "3.5 Hz" means different things on different cars and the
whole programme reasons in percent of slider range instead. Those ranges are
read off the car's own settings screen, once, and then never re-entered: this
screen is the once.

It is worth more than the setup values themselves, because it is what makes a
returned recommendation enterable without clamping. So the screen's real
subject is not the numbers — it is the difference between numbers that were
read off the car and numbers that are a typical window for its class. Measured
ranges are the driver's own mark and render in crayon; the preset that stands
in for them until he measures is struck, because it is not a value he declared.

The car's own reference facts (class, layout, stock figures) are shipped GT7
data rather than anything this app measured, so they are set as prose, not as
a value in one of the three registers.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.setup.vocabulary import GROUPS, RANGE_KEY_NAMES, keys_in_group
from pitcrew.store import catalogs
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    MarkButton,
    Picker,
    Plate,
    StencilLabel,
    struck_when_empty,
)

# Spin boxes have no null. The sentinel is the minimum of the range and renders
# as a dash, so a limit nobody entered never reads as a limit of zero - which
# on brake balance or toe is a real, wrong, enterable value.
EMPTY = -99999.0


class CarScreen(QWidget):
    """Pick a car, read its limits off its own settings screen, save them once."""

    saved = pyqtSignal(str, dict, bool)      # car, ranges, verified
    car_changed = pyqtSignal(str)

    def __init__(self, car_groups=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min_editors: dict[str, QDoubleSpinBox] = {}
        self._max_editors: dict[str, QDoubleSpinBox] = {}
        self._car_groups = (list(car_groups) if car_groups is not None
                            else list(catalogs.cars_by_category().items()))
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(StencilLabel("Car", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        header.addWidget(BodyLabel(
            "What this car will accept. Read the limits off its own settings "
            "screen once; every prompt and every export picks them up from "
            "here afterwards.", colour=theme.STENCIL_DIM))
        page.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(theme.GAP_WIDE)
        columns.addWidget(self._left_column(), 3)
        columns.addWidget(self._right_column(), 5)
        page.addLayout(columns, 1)
        page.addWidget(self._footer())

    def _left_column(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_WIDE)

        plate = Plate("Car")
        self.car_edit = Picker(placeholder="Pick a car", groups=self._car_groups)
        self.car_edit.changed.connect(self.car_changed.emit)
        plate.body.addWidget(self.car_edit)
        self.car_facts = BodyLabel("", size=14, colour=theme.STENCIL_DIM)
        plate.body.addWidget(self.car_facts)
        column.addWidget(plate)

        state = Plate("Ranges on file")
        self.state_note = BodyLabel("Pick a car.", size=14,
                                    colour=theme.STENCIL_DIM)
        state.body.addWidget(self.state_note)

        self.verified = QCheckBox(
            "These are read off this car's own in-game settings screen")
        self.verified.setToolTip(
            "Unticked means a typical window for the class, not this car's "
            "limits. The difference decides whether a returned sheet can be "
            "entered without clamping.")
        state.body.addWidget(self.verified)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        race = MarkButton("Race preset", compact=True)
        race.clicked.connect(lambda: self.load_preset("race"))
        road = MarkButton("Road preset", compact=True)
        road.clicked.connect(lambda: self.load_preset("road"))
        clear = MarkButton("Clear", compact=True)
        clear.clicked.connect(self.clear_ranges)
        for button in (race, road, clear):
            row.addWidget(button)
        row.addStretch(1)
        state.body.addLayout(row)
        state.body.addWidget(BodyLabel(
            "A preset fills the rows so a prompt is still usable — it is "
            "never saved as verified.", size=13, colour=theme.STENCIL_DIM))
        column.addWidget(state)
        column.addStretch(1)
        return holder

    def _right_column(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        rack = QVBoxLayout(inner)
        rack.setContentsMargins(0, 0, 4, 0)
        rack.setSpacing(theme.GAP_WIDE)
        per_car = set(catalogs.per_car_range_keys())
        for group in GROUPS:
            keys = [k for k in keys_in_group(group)
                    if k.key in RANGE_KEY_NAMES]
            if keys:
                rack.addWidget(self._group_plate(group, keys, per_car))
        rack.addStretch(1)
        scroller.setWidget(inner)
        column.addWidget(scroller, 1)
        return holder

    def _group_plate(self, group: str, keys, per_car: set) -> Plate:
        plate = Plate(group)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP_TIGHT)

        grid.addWidget(StencilLabel("", size=11), 0, 0)
        grid.addWidget(StencilLabel("Min", size=11, tracking=12.0), 0, 1)
        grid.addWidget(StencilLabel("Max", size=11, tracking=12.0), 0, 2)
        grid.addWidget(StencilLabel("", size=11), 0, 3)

        for row, key in enumerate(keys, start=1):
            label = catalogs.range_label(key.key) or key.label
            name = BodyLabel(label, size=14, colour=theme.STENCIL_DIM,
                             wrap=False)
            if key.key in per_car:
                name.setToolTip(
                    "Varies by car — this is one of the ones actually worth "
                    "measuring.")
            else:
                name.setToolTip("Near-universal across GT7 cars.")
            grid.addWidget(name, row, 0)
            grid.addWidget(self._bound_editor(key, self._min_editors), row, 1)
            grid.addWidget(self._bound_editor(key, self._max_editors), row, 2)
            unit = catalogs.range_unit(key.key) or key.unit
            grid.addWidget(StencilLabel(unit, size=11, colour=theme.STENCIL_DIM,
                                        tracking=8.0), row, 3)

        grid.setColumnStretch(0, 4)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)
        plate.body.addLayout(grid)
        return plate

    def _bound_editor(self, key, registry: dict) -> QDoubleSpinBox:
        editor = QDoubleSpinBox()
        editor.setRange(EMPTY, 99999.0)
        decimals = key.decimals
        step = catalogs.range_step(key.key)
        if step and step < 1:
            decimals = max(decimals, len(str(step).split(".")[-1]))
        editor.setDecimals(decimals)
        editor.setSingleStep(step or 1)
        editor.setSpecialValueText("—")
        editor.setValue(EMPTY)
        editor.setMinimumHeight(30)
        editor.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        from pitcrew.ui.widgets import block_wheel
        block_wheel(editor)
        struck_when_empty(editor)
        registry[key.key] = editor
        return editor

    def _footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(72)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, theme.GAP, 0, theme.GAP)
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)
        save = MarkButton("Save ranges", primary=True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        return bar

    # ---------------------------------------------------------------- state

    def set_car_groups(self, groups) -> None:
        self._car_groups = list(groups)
        self.car_edit.set_groups(self._car_groups)

    def current_car(self) -> str:
        return self.car_edit.currentText().strip()

    def set_car(self, car: str) -> None:
        self.car_edit.setCurrentText(car or "")

    def show_car(self, car: str, spec: dict | None, record) -> None:
        """Load a car: its reference facts, and whatever ranges are on file."""
        self.set_car(car)
        self.car_facts.setText(self._facts_text(spec))

        if record is not None and record.ranges:
            self.write_ranges(record.ranges)
            self.verified.setChecked(bool(record.verified))
            when = f" on {record.measured_date}" if record.measured_date else ""
            if record.verified:
                self.note(f"On file{when}, read off this car's own settings "
                          f"screen. Treated as hard limits everywhere.")
            else:
                self.note(f"On file{when}, but not marked as read off the "
                          f"car. Every prompt will call these estimates.",
                          warn=True)
            return

        kind = "road" if (spec or {}).get("category") in (None, "Road Car") \
            else "race"
        self.load_preset(kind)
        self.verified.setChecked(False)
        self.note("Nothing on file for this car. These are GT7 typical "
                  f"{kind}-car windows — read the real limits off the car's "
                  "settings screen and save them.", warn=True)

    def _facts_text(self, spec: dict | None) -> str:
        if not spec:
            return "No reference data for this car."
        bits = [spec.get("category"), spec.get("drivetrain"),
                spec.get("aspiration")]
        bits = [b for b in bits if b]
        line = " · ".join(bits)
        stock = []
        if spec.get("power_hp"):
            stock.append(f"{spec['power_hp']} bhp")
        if spec.get("weight_kg"):
            stock.append(f"{spec['weight_kg']} kg")
        if spec.get("pp_rating"):
            stock.append(f"PP {spec['pp_rating']}")
        if stock:
            line += ("\nStock: " if line else "Stock: ") + " / ".join(stock)
        return line or "No reference data for this car."

    def load_preset(self, kind: str) -> None:
        preset = catalogs.range_preset(kind)
        if preset:
            self.write_ranges(preset)
            self.verified.setChecked(False)

    def clear_ranges(self) -> None:
        for editor in (*self._min_editors.values(), *self._max_editors.values()):
            editor.setValue(EMPTY)

    def write_ranges(self, ranges: dict) -> None:
        for key in RANGE_KEY_NAMES:
            bounds = ranges.get(key)
            low = bounds[0] if bounds else None
            high = bounds[1] if bounds and len(bounds) > 1 else None
            self._min_editors[key].setValue(
                EMPTY if low is None else float(low))
            self._max_editors[key].setValue(
                EMPTY if high is None else float(high))

    def read_ranges(self) -> dict[str, list[float]]:
        """Only rows with both bounds. A half-entered range is not a range."""
        out: dict[str, list[float]] = {}
        for key in RANGE_KEY_NAMES:
            low = self._min_editors[key].value()
            high = self._max_editors[key].value()
            if low > EMPTY and high > EMPTY:
                out[key] = [low, high]
        return out

    def note(self, text: str, *, warn: bool = False) -> None:
        self.state_note.setText(text)
        self.state_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def footer(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};")

    # --------------------------------------------------------------- actions

    def _on_save(self) -> None:
        car = self.current_car()
        if not car:
            self.footer("Pick a car first — a range record is about one car.",
                        warn=True)
            return
        ranges = self.read_ranges()
        if not ranges:
            self.footer("Nothing to save — no row has both a min and a max.",
                        warn=True)
            return
        self.footer("")
        self.saved.emit(car, ranges, self.verified.isChecked())
