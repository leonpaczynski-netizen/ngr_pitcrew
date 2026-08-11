"""Event setup — preparing the set.

Two columns. The left is the event as it will be raced: what track, what
format, what the regulations allow. The right is the sheet that will be in the
car, pasted from the tune builder and then editable, because a value you
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
    Plate,
    StencilLabel,
)

WEATHER = ("Dry", "Damp", "Wet", "Changeable")
MULTIPLIERS = ("Off", "1x", "2x", "3x", "4x", "5x", "6x", "8x", "10x")
ABS_SETTINGS = ("Off", "Weak", "Default")


def _suggesting_combo(items, placeholder: str) -> QComboBox:
    """An editable combo that suggests without dictating its own width.

    Left to itself a combo sizes to its longest entry, and one 60-character
    track name would swallow the column and squeeze its neighbour to a few
    characters.
    """
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(items)
    combo.setCurrentText("")
    combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(12)
    combo.lineEdit().setPlaceholderText(placeholder)
    return combo


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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_editors: dict[str, QDoubleSpinBox] = {}
        self._compound_chips: dict[str, CompoundChip] = {}
        self._build()

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

        column.addWidget(self._identity_plate())
        column.addWidget(self._format_plate())
        column.addWidget(self._regulations_plate())
        column.addWidget(self._compounds_plate())
        column.addStretch(1)
        return holder

    def _identity_plate(self) -> Plate:
        plate = Plate("Event")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Round 4 - Fuji")

        self.track_edit = _suggesting_combo(catalogs.track_names(),
                                           "Fuji Speedway")
        self.layout_edit = QLineEdit()
        self.layout_edit.setPlaceholderText("Full")
        self.car_edit = _suggesting_combo(catalogs.car_names(),
                                          "Porsche 911 RSR (991) '17")

        grid.addWidget(Field("Name", self.name_edit), 0, 0, 1, 2)
        grid.addWidget(Field("Track", self.track_edit,
                             hint="Suggestions only - type anything"), 1, 0)
        grid.addWidget(Field("Layout", self.layout_edit,
                             hint="Full, East, No Chicane"), 1, 1)
        grid.addWidget(Field("Car", self.car_edit), 2, 0, 1, 2)
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

        self._length_unit = StencilLabel("LAPS", size=11, colour=theme.STRUCK,
                                         tracking=8.0)
        self._length_field = Field("Length", self.race_length,
                                   suffix_widget=self._length_unit)
        self.race_type.currentTextChanged.connect(self._on_race_type_changed)

        row.addWidget(Field("Run to", self.race_type), 1)
        row.addWidget(self._length_field, 1)
        row.addWidget(Field("Weather", self.weather), 1)
        plate.body.addLayout(row)
        return plate

    def _on_race_type_changed(self, kind: str) -> None:
        timed = kind == "Timed"
        self._length_unit.setText("MINUTES" if timed else "LAPS")
        self.race_length.setValue(45 if timed else 20)

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

        grid.addWidget(Field("Tyre wear", self.tyre_mult), 0, 0)
        grid.addWidget(Field("Fuel use", self.fuel_mult), 0, 1)
        grid.addWidget(Field("Refuel rate", self.refuel_rate, suffix="L/S",
                             hint="From the event regulations"), 1, 0)
        grid.addWidget(Field("Pit loss", self.pit_loss, suffix="SEC",
                             hint="A track constant - measure once"), 1, 1)
        grid.addWidget(Field("Mandatory stops", self.mandatory_stops), 2, 0)
        grid.addWidget(Field("ABS", self.abs_setting), 2, 1)
        grid.addWidget(Field("TCS", self.tcs), 3, 0)
        plate.body.addLayout(grid)
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
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(self._sheet_form())
        column.addWidget(scroller, 1)
        return holder

    def _paste_plate(self) -> Plate:
        plate = Plate("Sheet from the tune builder")
        self.paste_box = QPlainTextEdit()
        self.paste_box.setPlaceholderText(
            "Paste the sheet here - JSON, key: value lines, or a table.")
        self.paste_box.setFixedHeight(96)
        plate.body.addWidget(self.paste_box)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.paste_status = BodyLabel("Nothing read yet.", size=13,
                                      colour=theme.STRUCK)
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
        column.addStretch(1)
        return holder

    def _group_plate(self, group: str) -> Plate:
        plate = Plate(group)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP_TIGHT)

        for index, key in enumerate(keys_in_group(group)):
            editor = QDoubleSpinBox()
            editor.setRange(-9999.0, 9999.0)
            editor.setDecimals(key.decimals)
            editor.setSingleStep(10 ** -key.decimals if key.decimals else 1)
            # A setting nobody entered must not read as zero: the spin box
            # shows a dash until it holds a real value.
            editor.setSpecialValueText("—")
            editor.setMinimum(-9999.0)
            editor.setValue(-9999.0)
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

        self.footer_note = BodyLabel("", size=13, colour=theme.STRUCK)
        row.addWidget(self.footer_note, 1)
        row.addWidget(MarkButton("Discard"))
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

    def values(self) -> dict:
        """Everything the driver declared on this screen."""
        setup_values = {}
        for key, editor in self._setup_editors.items():
            if editor.value() > -9999.0:
                setup_values[key] = editor.value()

        return {
            "name": self.name_edit.text().strip(),
            "track": self.track_edit.currentText().strip(),
            "layout": self.layout_edit.text().strip() or None,
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
            "available_compounds": [code for code, chip
                                    in self._compound_chips.items()
                                    if chip.isSelected()],
            "sheet_name": self.sheet_name.text().strip(),
            "setup_values": setup_values,
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
