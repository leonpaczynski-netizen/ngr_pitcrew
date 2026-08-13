"""Event setup — preparing the set.

Two columns. The left is the event as it will be raced: what track, what
format, what the regulations allow. The right is the sheet that will be in the
car, pasted from the knowledge base and then editable, because a value you
changed in the garage after the paste has to be correctable without starting
over.

Everything in here is declared by the driver, so everything in here is crayon.
The screen has no measured values on it at all - that is what makes the
Practice screen's stencil white mean something when you get there.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pitcrew.setup.parse import parse_sheet
from pitcrew.setup.vocabulary import GROUPS, SETUP_KEYS, keys_in_group
from pitcrew.store import catalogs
from pitcrew.store.tyres import ALL_COMPOUNDS
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    CompoundBand,
    Field,
    MarkButton,
    Picker,
    Plate,
    StencilLabel,
    struck_when_empty,
)

WEATHER = ("Dry", "Damp", "Wet", "Changeable")
MULTIPLIERS = ("Off",) + tuple(f"{n}x" for n in range(1, 11))
ABS_SETTINGS = ("Off", "Weak", "Default")
START_TYPES = ("Rolling", "Standing", "Grid - no track limit")
TIMES_OF_DAY = ("Fixed day", "Fixed night", "Day to night transition")
# What this round is being tuned for. Declared once, on the event, because it
# is a property of the round rather than of a session.
PRIORITIES = (
    "Balanced - quali grid and race pace",
    "Qualifying - track position is everything here",
    "Race pace and tyre life",
    "Fuel economy / strategy",
    "Drivability - I need to finish",
)

# Spin boxes have no null. This sentinel is the minimum of the range and
# renders as a dash, so a setting nobody entered never reads as zero.
EMPTY = -9999.0


class CompoundChip(CompoundBand):
    """A band you can select. Clicking marks the compound as available."""

    toggled = pyqtSignal(str, bool)

    def __init__(self, code: str, parent: QWidget | None = None) -> None:
        super().__init__(code, parent=parent, animate=False)
        self._selected = False
        self.setFixedSize(CompoundBand.WIDTH, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStruck(True)
        self.setToolTip(code)

    def isSelected(self) -> bool:  # noqa: N802 - Qt naming
        return self._selected

    def setSelected(self, selected: bool) -> None:  # noqa: N802 - Qt naming
        self._selected = selected
        self.setStruck(not selected)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.setSelected(not self._selected)
        self.toggled.emit(self.code() or "", self._selected)


class EventScreen(QWidget):
    """Create or edit the event, and the sheet that will be in the car."""

    saved = pyqtSignal(dict)
    discarded = pyqtSignal()
    catalog_extended = pyqtSignal(str, str)    # kind, name

    def __init__(self, tracks=None, car_groups=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_editors: dict[str, QDoubleSpinBox] = {}
        self._compound_chips: dict[str, CompoundChip] = {}
        self._tracks = (list(tracks) if tracks is not None
                        else list(catalogs.track_bases()))
        self._car_groups = (list(car_groups) if car_groups is not None
                            else list(catalogs.cars_by_category().items()))
        self._build()

    def set_catalogs(self, tracks, car_groups) -> None:  # noqa: N802 - Qt naming
        self._tracks = list(tracks)
        self._car_groups = list(car_groups)
        self.track_edit.set_items(self._tracks)
        self.car_edit.set_groups(self._car_groups)

    def _on_track_changed(self, track: str) -> None:
        """Layouts belong to their track, so the list follows the choice."""
        layouts = catalogs.layouts_for(track) if track else ()
        chosen = self.layout_edit.currentText()
        self.layout_edit.set_items(layouts)
        self.layout_edit.setEnabledState(bool(layouts))
        if chosen in layouts:
            self.layout_edit.setCurrentText(chosen)

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        page.addLayout(self._header())

        columns = QHBoxLayout()
        columns.setSpacing(theme.GAP_WIDE)
        columns.addWidget(self._left_column(), 4)
        columns.addWidget(self._right_column(), 5)
        page.addLayout(columns, 1)

        page.addWidget(self._footer())

    def _header(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(2)
        title = StencilLabel("Event", size=theme.TITLE_PX, colour=theme.STENCIL,
                             tracking=6.0)
        column.addWidget(title)
        column.addWidget(BodyLabel(
            "What is being raced, and what is in the car.",
            colour=theme.STENCIL_DIM))
        return column

    # ----------------------------------------------------------- left column

    def _left_column(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_WIDE)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        inner = QWidget()
        stack = QVBoxLayout(inner)
        stack.setContentsMargins(0, 0, 4, 0)
        stack.setSpacing(theme.GAP_WIDE)
        stack.addWidget(self._identity_plate())
        stack.addWidget(self._format_plate())
        stack.addWidget(self._regulations_plate())
        stack.addWidget(self._compounds_plate())
        stack.addWidget(self._context_plate())
        stack.addStretch(1)
        scroller.setWidget(inner)

        column.addWidget(scroller, 1)
        return holder

    def _identity_plate(self) -> Plate:
        plate = Plate("Event")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Round 4 - Fuji")

        self.track_edit = Picker(self._tracks, placeholder="Pick a track")
        self.track_edit.changed.connect(self._on_track_changed)
        self.layout_edit = Picker(placeholder="—")
        self.car_edit = Picker(placeholder="Pick a car", groups=self._car_groups)

        # GT7 rewrote its physics, tyre model and geometry in 1.49 and again in
        # 1.55, so a measurement without the version it was taken under cannot
        # be compared with the next one. The export refuses without it.
        self.game_version = QLineEdit()
        self.game_version.setPlaceholderText("1.70")
        self.game_version.setToolTip(
            "The GT7 version this event is run under. Every measurement is "
            "filed against it, and the export refuses without it - the physics "
            "have been rewritten twice in two updates.")

        grid.addWidget(Field("Name", self.name_edit), 0, 0, 1, 2)
        grid.addWidget(Field("Track", self.track_edit), 1, 0)
        grid.addWidget(Field("Layout", self.layout_edit,
                             hint="Set by the track"), 1, 1)
        grid.addWidget(Field("Car", self.car_edit), 2, 0)
        grid.addWidget(Field("GT7 version", self.game_version,
                             hint="Filed with every measurement"), 2, 1)
        # Without this the hint under Track widens its column and squeezes
        # Layout down to a few characters.
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        plate.body.addLayout(grid)
        return plate

    def _format_plate(self) -> Plate:
        plate = Plate("Format")
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)

        self.race_type = QComboBox()
        self.race_type.addItems(("Laps", "Timed"))
        self.race_length = QSpinBox()
        self.race_length.setRange(1, 999)
        self.race_length.setValue(20)
        self.weather = QComboBox()
        self.weather.addItems(WEATHER)

        self._length_unit = StencilLabel("LAPS", size=11, colour=theme.STENCIL_DIM,
                                         tracking=8.0)
        self._length_field = Field("Length", self.race_length,
                                   suffix_widget=self._length_unit)
        self.race_type.currentTextChanged.connect(self._on_race_type_changed)

        # Timed races only. The flag falls at the first line crossing after
        # the clock expires, so the race can run past its limit by one lap -
        # or by this, whichever is shorter. Without it the app cannot say how
        # long the race can possibly last, and a plan that overruns reads as a
        # slow plan rather than an impossible one.
        self.extra_time = QDoubleSpinBox()
        self.extra_time.setRange(EMPTY, 3600.0)
        self.extra_time.setDecimals(0)
        self.extra_time.setSingleStep(30.0)
        self.extra_time.setValue(EMPTY)
        struck_when_empty(self.extra_time)
        self.extra_time.setToolTip(
            "Timed races: what GT7 allows for finishing the lap the clock ran "
            "out on. Blank means one full lap, which is the usual case.")
        self._extra_time_field = Field("Extra time", self.extra_time,
                                       suffix="SEC")

        row.addWidget(Field("Run to", self.race_type), 1)
        row.addWidget(self._length_field, 1)
        row.addWidget(self._extra_time_field, 1)
        row.addWidget(Field("Weather", self.weather), 1)
        plate.body.addLayout(row)

        # Declared here rather than asked for again when a prompt is written.
        # Every one of these was a form field in the tool this replaced, and
        # every re-entry was a chance to get it wrong.
        second = QHBoxLayout()
        second.setSpacing(theme.GAP)
        self.start_type = QComboBox()
        self.start_type.addItems(START_TYPES)
        self.time_of_day = QComboBox()
        self.time_of_day.addItems(TIMES_OF_DAY)
        second.addWidget(Field("Start", self.start_type), 1)
        second.addWidget(Field("Time of day", self.time_of_day), 1)
        plate.body.addLayout(second)
        return plate

    def _on_race_type_changed(self, kind: str) -> None:
        timed = kind == "Timed"
        self._length_unit.setText("MINUTES" if timed else "LAPS")
        self.race_length.setValue(45 if timed else 20)
        # A lap race has no clock to run past, so the field would be a question
        # with no answer.
        self._extra_time_field.setVisible(timed)

    def _regulations_plate(self) -> Plate:
        plate = Plate("Regulations")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.tyre_mult = QComboBox()
        self.tyre_mult.addItems(MULTIPLIERS)
        self.tyre_mult.setCurrentText("4x")
        self.fuel_mult = QComboBox()
        self.fuel_mult.addItems(MULTIPLIERS)
        self.fuel_mult.setCurrentText("2x")

        self.refuel_rate = QDoubleSpinBox()
        self.refuel_rate.setRange(0.1, 20.0)
        self.refuel_rate.setSingleStep(0.1)
        self.refuel_rate.setValue(2.5)

        self.pit_loss = QDoubleSpinBox()
        self.pit_loss.setRange(0.0, 120.0)
        self.pit_loss.setSingleStep(0.5)
        self.pit_loss.setValue(20.0)

        self.mandatory_stops = QSpinBox()
        self.mandatory_stops.setRange(0, 10)

        self.abs_setting = QComboBox()
        self.abs_setting.addItems(ABS_SETTINGS)
        self.abs_setting.setCurrentText("Weak")
        self.tcs = QSpinBox()
        self.tcs.setRange(0, 5)
        self.countersteer = QComboBox()
        self.countersteer.addItems(("Off", "On"))

        self.pp_cap = QDoubleSpinBox()
        self.pp_cap.setRange(EMPTY, 2000.0)
        self.pp_cap.setDecimals(2)
        self.pp_cap.setSpecialValueText("—")
        self.pp_cap.setValue(EMPTY)
        struck_when_empty(self.pp_cap)

        grid.addWidget(Field("Tyre wear", self.tyre_mult), 0, 0)
        grid.addWidget(Field("Fuel use", self.fuel_mult), 0, 1)
        grid.addWidget(Field("Refuel rate", self.refuel_rate, suffix="L/S",
                             hint="From the event regulations"), 1, 0)
        grid.addWidget(Field("Pit loss", self.pit_loss, suffix="SEC",
                             hint="A track constant - measure once"), 1, 1)
        grid.addWidget(Field("Mandatory stops", self.mandatory_stops), 2, 0)
        grid.addWidget(Field("PP cap", self.pp_cap,
                             hint="Blank when the league sets none"), 2, 1)
        grid.addWidget(Field("ABS", self.abs_setting), 3, 0)
        grid.addWidget(Field("TCS", self.tcs), 3, 1)
        grid.addWidget(Field("Countersteer assist", self.countersteer), 4, 0)
        plate.body.addLayout(grid)
        return plate

    def _context_plate(self) -> Plate:
        plate = Plate("This round")
        self.priority = QComboBox()
        self.priority.addItems(PRIORITIES)
        plate.body.addWidget(Field(
            "Priority", self.priority,
            hint="What the sheets should be biased toward"))
        self.event_notes = QPlainTextEdit()
        self.event_notes.setPlaceholderText(
            "League rules, a problem you want solved, anything carried over "
            "from the last round.")
        self.event_notes.setFixedHeight(72)
        plate.body.addWidget(self.event_notes)
        return plate

    def _compounds_plate(self) -> Plate:
        plate = Plate("Compounds allowed")
        plate.body.addWidget(BodyLabel(
            "Mark the sets the regulations allow. Unmarked compounds cannot "
            "appear in a strategy.", colour=theme.STENCIL_DIM))

        rack = QHBoxLayout()
        rack.setSpacing(5)
        for compound in ALL_COMPOUNDS:
            chip = CompoundChip(compound.code)
            chip.setToolTip(compound.name)
            self._compound_chips[compound.code] = chip
            rack.addWidget(chip)
        rack.addStretch(1)
        plate.body.addLayout(rack)

        for code in ("RH", "RM", "RS"):
            self._compound_chips[code].setSelected(True)
        return plate

    # ---------------------------------------------------------- right column

    def _right_column(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_WIDE)

        column.addWidget(self._paste_plate())

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroller.setWidget(self._sheet_form())
        column.addWidget(scroller, 1)
        return holder

    def _paste_plate(self) -> Plate:
        plate = Plate("Sheet from the knowledge base")
        self.paste_box = QPlainTextEdit()
        self.paste_box.setPlaceholderText(
            "Paste the sheet here - JSON, key: value lines, or a table.")
        self.paste_box.setFixedHeight(96)
        plate.body.addWidget(self.paste_box)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.paste_status = BodyLabel("Nothing read yet.", size=13,
                                      colour=theme.STENCIL_DIM)
        read_button = MarkButton("Read sheet")
        read_button.clicked.connect(self._on_read_sheet)
        row.addWidget(self.paste_status, 1)
        row.addWidget(read_button)
        plate.body.addLayout(row)
        return plate

    def _sheet_form(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(theme.GAP_WIDE)

        self.sheet_name = QLineEdit()
        self.sheet_name.setPlaceholderText("Fuji race v2")
        naming = Plate("Sheet")
        naming.body.addWidget(Field("Name", self.sheet_name))
        column.addWidget(naming)

        for group in GROUPS:
            column.addWidget(self._group_plate(group))

        column.addWidget(self._gears_plate())
        column.addWidget(self._build_plate())
        column.addStretch(1)
        return holder

    def _build_plate(self) -> Plate:
        """The car as raced, not as it left the showroom.

        These are the export contract's `setup.build` and `setup.performance`,
        and they are what makes a brief say "525 bhp at 1300 kg" instead of
        quoting stock figures for a car that is nothing like stock.
        """
        plate = Plate("Build as raced")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP_TIGHT)

        self._build_editors: dict[str, QDoubleSpinBox] = {}
        fields = (
            ("build", "bhp", "Power", "BHP", 0),
            ("build", "weightKg", "Weight", "KG", 0),
            ("build", "pp", "PP", "", 2),
            ("performance", "powerRestrictor", "Power restrictor", "%", 0),
            ("performance", "ecuOutput", "ECU output", "%", 0),
            ("performance", "ballastKg", "Ballast", "KG", 0),
            ("performance", "ballastPosition", "Ballast position", "", 0),
        )
        for index, (section, key, label, unit, decimals) in enumerate(fields):
            editor = QDoubleSpinBox()
            editor.setRange(EMPTY, 99999.0)
            editor.setDecimals(decimals)
            editor.setSpecialValueText("—")
            editor.setValue(EMPTY)
            struck_when_empty(editor)
            self._build_editors[f"{section}.{key}"] = editor
            grid.addWidget(Field(label, editor, suffix=unit),
                           index // 2, index % 2)
        plate.body.addLayout(grid)
        return plate

    def _group_plate(self, group: str) -> Plate:
        plate = Plate(group)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP_TIGHT)

        for index, key in enumerate(keys_in_group(group)):
            editor = QDoubleSpinBox()
            editor.setRange(EMPTY, 9999.0)
            editor.setDecimals(key.decimals)
            editor.setSingleStep(10 ** -key.decimals if key.decimals else 1)
            # A setting nobody entered must not read as zero: the spin box
            # shows a dash until it holds a real value.
            editor.setSpecialValueText("—")
            editor.setValue(EMPTY)
            struck_when_empty(editor)
            self._setup_editors[key.key] = editor
            grid.addWidget(Field(key.label, editor, suffix=key.unit,
                                 hint=key.note),
                           index // 2, index % 2)
        plate.body.addLayout(grid)
        return plate

    def _gears_plate(self) -> Plate:
        plate = Plate("Gear ratios")
        self.gear_edit = QLineEdit()
        self.gear_edit.setPlaceholderText("3.10  2.28  1.79  1.46  1.22  1.04")
        plate.body.addWidget(Field(
            "1st to top", self.gear_edit,
            hint="Longest first. An ascending pair means the sheet was "
                 "transcribed out of order."))
        return plate

    # ---------------------------------------------------------------- footer

    def _footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(72)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, theme.GAP, 0, theme.GAP)
        row.setSpacing(theme.GAP)

        self.footer_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)
        # Wired, at last. This button was constructed, laid out and
        # connected to nothing for the life of the screen - the one control
        # in the app that did not do what it said.
        discard = MarkButton("Discard")
        discard.setToolTip(
            "Throw away unsaved edits and reload the event as it is stored.")
        discard.clicked.connect(self.discarded.emit)
        row.addWidget(discard)
        save = MarkButton("Save event", primary=True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        return bar

    # --------------------------------------------------------------- actions

    def _on_read_sheet(self) -> None:
        result = parse_sheet(self.paste_box.toPlainText())
        if result.matched_count == 0 and not result.gears:
            self.paste_status.setText(
                "Nothing recognised. Fill the form below instead.")
            self.paste_status.setStyleSheet(f"color: {theme.WARNING};")
            return

        for key, value in result.values.items():
            editor = self._setup_editors.get(key)
            if editor is not None:
                editor.setValue(value)
        if result.gears:
            self.gear_edit.setText("  ".join(f"{g:g}" for g in result.gears))
        if result.sheet_name:
            self.sheet_name.setText(result.sheet_name)

        self.paste_status.setText(f"Read {result.summary()}.")
        colour = theme.WARNING if result.unmatched else theme.CHALK
        self.paste_status.setStyleSheet(f"color: {colour};")
        if result.unmatched:
            self.paste_status.setToolTip(
                "Not recognised:\n" + "\n".join(result.unmatched[:12]))

    def load(self, event: dict | None, sheet=None) -> None:
        """Populate from a stored event and its fitted sheet."""
        if event:
            self.name_edit.setText(event.get("name") or "")
            self.track_edit.setCurrentText(event.get("track") or "")
            self._on_track_changed(event.get("track") or "")
            self.layout_edit.setCurrentText(event.get("layout") or "")
            self.car_edit.setCurrentText(event.get("car_name") or "")
            self.race_type.setCurrentText(
                "Timed" if event.get("race_type") == "time" else "Laps")
            self.race_length.setValue(int(event.get("race_laps") or 20))
            self.weather.setCurrentText((event.get("weather") or "dry").title())
            self.tyre_mult.setCurrentText(event.get("tyre_wear_mult") or "Off")
            self.fuel_mult.setCurrentText(event.get("fuel_mult") or "Off")
            self.refuel_rate.setValue(float(event.get("refuel_rate_lps") or 2.5))
            self.pit_loss.setValue(float(event.get("pit_loss_secs") or 20.0))
            self.mandatory_stops.setValue(int(event.get("mandatory_stops") or 0))
            if event.get("abs_setting"):
                self.abs_setting.setCurrentText(event["abs_setting"])
            self.tcs.setValue(int(event.get("tcs") or 0))
            self.countersteer.setCurrentText(
                "On" if event.get("countersteer") else "Off")
            cap = event.get("pp_cap")
            self.pp_cap.setValue(EMPTY if cap is None else float(cap))
            if event.get("start_type"):
                self.start_type.setCurrentText(event["start_type"])
            if event.get("time_of_day"):
                self.time_of_day.setCurrentText(event["time_of_day"])
            if event.get("priority"):
                self.priority.setCurrentText(event["priority"])
            self.event_notes.setPlainText(event.get("notes") or "")
            self.game_version.setText(event.get("game_version") or "")
            extra = event.get("extra_time_s")
            self.extra_time.setValue(EMPTY if extra is None else float(extra))

            allowed = set(event.get("available_compounds") or [])
            for code, chip in self._compound_chips.items():
                chip.setSelected(code in allowed)

        if sheet is not None:
            self.sheet_name.setText(sheet.sheet_name)
            for key, editor in self._setup_editors.items():
                value = sheet.values.get(key)
                editor.setValue(EMPTY if value is None else float(value))
            if sheet.gears:
                self.gear_edit.setText("  ".join(f"{g:g}" for g in sheet.gears))
            for name, editor in self._build_editors.items():
                section, _, key = name.partition(".")
                stored = (sheet.build if section == "build"
                          else sheet.performance).get(key)
                editor.setValue(EMPTY if stored is None else float(stored))

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};")

    def values(self) -> dict:
        """Everything the driver declared on this screen."""
        setup_values = {}
        for key, editor in self._setup_editors.items():
            if editor.value() > EMPTY:
                setup_values[key] = editor.value()

        build: dict[str, float] = {}
        performance: dict[str, float] = {}
        for name, editor in self._build_editors.items():
            if editor.value() <= EMPTY:
                continue
            section, _, key = name.partition(".")
            (build if section == "build" else performance)[key] = editor.value()

        return {
            "name": self.name_edit.text().strip(),
            "track": self.track_edit.currentText().strip(),
            "layout": self.layout_edit.currentText() or None,
            "car_name": self.car_edit.currentText().strip(),
            "race_type": "laps" if self.race_type.currentText() == "Laps" else "time",
            "race_laps": self.race_length.value(),
            "weather": self.weather.currentText().lower(),
            "tyre_wear_mult": self.tyre_mult.currentText(),
            "fuel_mult": self.fuel_mult.currentText(),
            "refuel_rate_lps": self.refuel_rate.value(),
            "pit_loss_secs": self.pit_loss.value(),
            "mandatory_stops": self.mandatory_stops.value(),
            "abs_setting": self.abs_setting.currentText(),
            "tcs": self.tcs.value(),
            "countersteer": 1 if self.countersteer.currentText() == "On" else 0,
            # Blank is blank: a league with no PP cap is not a league with a
            # cap of zero.
            "pp_cap": (None if self.pp_cap.value() <= EMPTY
                       else self.pp_cap.value()),
            "start_type": self.start_type.currentText(),
            "time_of_day": self.time_of_day.currentText(),
            "priority": self.priority.currentText(),
            "notes": self.event_notes.toPlainText().strip() or None,
            "game_version": self.game_version.text().strip() or None,
            # Blank is blank: no allowance declared is not an allowance of
            # zero, which would end the race on the stroke of the clock.
            "extra_time_s": (None if self.extra_time.value() <= EMPTY
                             else self.extra_time.value()),
            "available_compounds": [code for code, chip
                                    in self._compound_chips.items()
                                    if chip.isSelected()],
            "sheet_name": self.sheet_name.text().strip(),
            "setup_values": setup_values,
            "gear_text": self.gear_edit.text().strip(),
            "build": build,
            "performance": performance,
        }

    def _on_save(self) -> None:
        data = self.values()
        missing = [name for name, value in
                   (("a name", data["name"]), ("a track", data["track"]),
                    ("a car", data["car_name"])) if not value]
        if missing:
            self.footer_note.setText(f"Needs {', '.join(missing)}.")
            self.footer_note.setStyleSheet(f"color: {theme.WARNING};")
            return
        self.footer_note.setText("")
        self.saved.emit(data)
