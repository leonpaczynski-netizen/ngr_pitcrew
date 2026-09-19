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
    QFrame,
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
        """The screen, top-down: every container is attached before it is
        filled.

        **Measured 19 Sep 2026: half the build.** Under the app-wide style
        sheet every label carries its own sheet, and moving a finished
        subtree under a new parent re-polishes every one of them again -
        once per level it is moved up. Built bottom-up, each plate was made
        whole and then moved into the rack, the rack into its scroller, the
        column into the page: 50-64 ms. Built top-down, a widget is polished
        where it will live: 18. The layout - header, columns, footer - is
        unchanged.
        """
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        header = QVBoxLayout()
        header.setSpacing(2)
        page.addLayout(header)
        header.addWidget(StencilLabel("Car", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        header.addWidget(BodyLabel(
            "What this car will accept. Read the limits off its own settings "
            "screen once; every prompt and every export picks them up from "
            "here afterwards.", colour=theme.STENCIL_DIM))

        columns = QHBoxLayout()
        columns.setSpacing(theme.GAP_WIDE)
        page.addLayout(columns, 1)
        page.addWidget(self._footer())
        self._left_column(columns)
        self._right_column(columns)

    def _left_column(self, columns) -> QWidget:
        # Scrolled, like the right one. The right column got a scroller and
        # the left did not, so on a narrow window ~400 px of it was clipped -
        # and what is clipped is the preset buttons and the verified
        # checkbox, which is how ranges get onto this screen in the first
        # place.
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        columns.addWidget(outer, 3)

        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_WIDE)
        outer.setWidget(holder)

        plate = Plate("Car")
        column.addWidget(plate)
        self.car_edit = Picker(placeholder="Pick a car", groups=self._car_groups)
        self.car_edit.changed.connect(self.car_changed.emit)
        plate.body.addWidget(self.car_edit)
        self.car_facts = BodyLabel("", size=14, colour=theme.STENCIL_DIM)
        plate.body.addWidget(self.car_facts)

        state = Plate("Ranges on file")
        column.addWidget(state)
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
        state.body.addLayout(row)
        race = MarkButton("Race preset", compact=True)
        race.clicked.connect(lambda: self.load_preset("race"))
        road = MarkButton("Road preset", compact=True)
        road.clicked.connect(lambda: self.load_preset("road"))
        # Danger, and a two-click confirm. It sits in a row with two
        # non-destructive preset buttons, drawn identically, and empties every
        # min and max on the screen - including figures read off the car by
        # hand, one at a time, which is the most expensive data in the app to
        # re-enter. `MarkButton` has shipped a danger variant since it was
        # written and nothing had ever used it.
        clear = MarkButton("Clear", compact=True, danger=True)
        self._clear_armed = False
        clear.clicked.connect(lambda: self._on_clear(clear))
        for button in (race, road, clear):
            row.addWidget(button)
        row.addStretch(1)
        state.body.addWidget(BodyLabel(
            "A preset fills the rows so a prompt is still usable — it is "
            "never saved as verified.", size=13, colour=theme.STENCIL_DIM))
        column.addStretch(1)
        return outer

    def _right_column(self, columns):
        """The rack of range plates, one per group."""
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        columns.addWidget(holder, 5)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        column.addWidget(scroller, 1)

        inner = QWidget()
        rack = QVBoxLayout(inner)
        rack.setContentsMargins(0, 0, 4, 0)
        rack.setSpacing(theme.GAP_WIDE)
        scroller.setWidget(inner)
        per_car = set(catalogs.per_car_range_keys())
        label_width = self._label_column_width()
        for group in GROUPS:
            keys = [k for k in keys_in_group(group)
                    if k.key in RANGE_KEY_NAMES]
            if keys:
                self._group_plate(rack, group, keys, per_car, label_width)
        rack.addStretch(1)

    def _label_column_width(self) -> int:
        """One width for the name column across all four plates.

        Each plate laid out its own grid, so each sized column 0 to its own
        longest label - "Ride height" in one, "Damper compression" in the next
        - and the Min and Max columns stepped about 8px further right down the
        screen. They are one table read as four; measure them once.
        """
        widest = 0
        # A parentless label built only to measure text. Kept because
        # `fontMetrics()` needs a widget carrying the real face, but it is
        # never laid out - which is why it is named for what it does.
        probe = BodyLabel("", size=14, wrap=False)
        for key in (k for group in GROUPS for k in keys_in_group(group)
                    if k.key in RANGE_KEY_NAMES):
            label = catalogs.range_label(key.key) or key.label
            widest = max(widest, probe.fontMetrics().horizontalAdvance(label))
        return widest + theme.GAP

    def _group_plate(self, rack, group: str, keys, per_car: set,
                     label_width: int) -> Plate:
        plate = Plate(group)
        rack.addWidget(plate)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP_TIGHT)
        grid.setColumnMinimumWidth(0, label_width)
        # Attached before it is filled - see `_build`.
        plate.body.addLayout(grid)

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

        # Column 0 is pinned to one measured width, so the Min and Max
        # columns start at the same x on every plate.
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)
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
        editor.setMinimumHeight(34)
        # A min/max bound is three or four characters. Left to
        # itself the box asks for 143px and four of them set the
        # width of the whole screen.
        editor.setMinimumWidth(64)
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

    def _on_clear(self, button) -> None:
        """First press arms, second press wipes.

        The same two-click pattern the Event screen uses to guard switching
        away from unsaved work - a confirmation that needs no modal and no
        second widget, and that says what it is about to destroy.
        """
        if not self._clear_armed and self._has_values():
            self._clear_armed = True
            button.setText("Clear — sure?")
            self.note("Press Clear again to empty every range on this screen. "
                      "Measured figures go too.", warn=True)
            return
        self._clear_armed = False
        button.setText("Clear")
        self.clear_ranges()

    def _has_values(self) -> bool:
        return any(editor.value() > editor.minimum()
                   for editor in (*self._min_editors.values(),
                                  *self._max_editors.values()))

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
        return self._pairs()[0]

    def inverted_ranges(self) -> list[str]:
        """Rows where the max is below the min, in the driver's own labels."""
        return self._pairs()[1]

    def _pairs(self) -> tuple[dict[str, list[float]], list[str]]:
        """Split the entered rows into usable ranges and transposed ones.

        **A max below its min is refused, not stored.** This screen exists to
        copy 22 pairs of numbers off the car's own settings screen by hand,
        which is exactly the place a pair gets transposed - and the record it
        writes is a hard slider limit. `fraction_of_range` (setup/ranges.py)
        and `prompts/build.py:113` both divide by `high - low` and both guard
        only `high == low`, so 200/50 makes every percentage quoted against
        that key come out negative, on the axis the whole programme reasons in
        (CLAUDE.md §4.6). Equal bounds are kept: a setting with one legal value
        is a real range, and both consumers already return "—" for it.
        """
        out: dict[str, list[float]] = {}
        inverted: list[str] = []
        for key in RANGE_KEY_NAMES:
            low = self._min_editors[key].value()
            high = self._max_editors[key].value()
            if not (low > EMPTY and high > EMPTY):
                continue
            if high < low:
                inverted.append(catalogs.range_label(key) or key)
                continue
            out[key] = [low, high]
        return out, inverted

    def note(self, text: str, *, warn: bool = False) -> None:
        self.state_note.setText(text)
        self.state_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def footer(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.set_ink(theme.WARNING if warn else theme.CHALK)

    # --------------------------------------------------------------- actions

    def _on_save(self) -> None:
        car = self.current_car()
        if not car:
            self.footer("Pick a car first — a range record is about one car.",
                        warn=True)
            return
        ranges, inverted = self._pairs()
        if inverted:
            # Named rather than silently dropped: he read them off the car and
            # they are on the screen, so "nothing saved" with no reason is the
            # one response that looks like the app losing his work.
            self.footer(
                f"Max is below min on {', '.join(inverted)}. Swap them — a "
                f"range that runs backwards makes every percentage quoted "
                f"against it negative.", warn=True)
            return
        if not ranges:
            self.footer("Nothing to save — no row has both a min and a max.",
                        warn=True)
            return
        self.footer("")
        self.saved.emit(car, ranges, self.verified.isChecked())
