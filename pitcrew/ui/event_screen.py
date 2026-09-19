"""Event setup — the event as it will be raced.

What track, what format, what the regulations allow, and which compounds are
on the shelf. **Nothing about what is in the car.** The setup and the gearbox
are held by the tune builder and confirmed against GT7's own settings screen;
a value kept in two places becomes two values, and on this project it did,
twice, on one car.

Everything in here is declared by the driver, so everything in here is crayon.
The screen has no measured values on it at all - that is what makes the
Practice screen's stencil white mean something when you get there.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QStringListModel, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
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

from pitcrew.store import catalogs
from pitcrew.store.tyres import ALL_COMPOUNDS
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    CascadingPicker,
    CompoundBand,
    Field,
    MarkButton,
    Picker,
    Plate,
    StencilLabel,
    block_wheel,
    mark_unset,
    struck_when_empty,
)

# The picker's last row. Chosen deliberately so that the list of saved events
# and the way to start another one are the same control - a separate "New"
# button beside a picker is how you end up editing one event while believing
# you are creating the next.
NEW_EVENT = "+  New event"
# Divider row for the hub's calendar. Not selectable - a separator that could
# be chosen is a switch to nothing, and the picker's `itemData` is the whole
# vocabulary of what a selection means.
HUB_HEADING = "—  Coming up, from the hub  —"
# Fields the hub declares, the form does not edit, and a save must not lose.
# Loaded onto the screen and echoed back out of `values()` untouched: without
# this, opening a hub-sourced event and pressing Save silently dropped the
# round it belongs to and the compounds the league requires.
#
# **And the regulations the form has no box for** (the critic on row 2.7,
# BLOCKER): an Enduro round arrives incomplete - the hub gives no legal
# compounds - so it goes pick -> fill the compounds -> Save, and that save
# dropped BoP and the power and weight limits on the floor. The Fuji event
# would have been created with `bop_enabled` NULL, "ask him", after the hub
# had said yes.
CARRIED = ("hub_round_id", "required_compounds", "bop_enabled",
           "tuning_allowed", "power_limit_bhp", "weight_limit_kg")
# Sentinel for "no switch is pending". `None` cannot do this job: it is the
# picker's value for New event, and a real target.
_UNSET = object()

WEATHER = ("Dry", "Damp", "Wet", "Changeable")
# How the league sets weather. Fixed means the round runs one setting whatever
# the circuit offers - the V8 rounds do - and it makes every circuit's rain
# irrelevant. Random hands the decision to the circuit.
WEATHER_RULES = ("Random", "Fixed")
# Whether the circuit can produce rain. Declared, never measured: GT7
# broadcasts no weather channel at all. "Ask me" is the honest default and the
# app seeds the answer from a community list that is four years old.
RAIN_ANSWERS = ("Not answered", "Can rain", "Cannot rain")
MULTIPLIERS = ("Off",) + tuple(f"{n}x" for n in range(1, 11))
ABS_SETTINGS = ("Off", "Weak", "Default")
# **Which wheels are driven, and it has to be declared because GT7 broadcasts
# no drivetrain channel in any packet format.** Without it `wheelspin` watches
# all four wheels, so a front wheel lifted over a kerb under throttle reads as
# wheelspin on a rear-driven car - at Watkins T2 that was 15 laps of 17 with a
# kerb strike on all 17. The torque-vector channels that might have inferred
# it read zero on this stream.
#
# "—" is a real answer and the honest default: it means nobody has said, and
# the detector goes on watching all four and disclosing that it does.
DRIVETRAINS = ("—", "FF", "FR", "MR", "RR", "4WD")
# The fuel map the car ran. GT7 broadcasts no fuel-map channel either, and the
# whole fuel model is expressed per map. 1 is the richest - sources that
# number them 1-5, or invert the direction, are wrong.
FUEL_MAPS = ("—", "1", "2", "3", "4", "5", "6")
START_TYPES = ("Rolling", "Standing", "Grid - no track limit")
# GT7's own lobby vocabulary. A lobby offers **names, not hours**, and what
# hour each name means differs by circuit - so the app does not interpret them,
# it measures what one did off the game clock the first time it is run and
# keeps the answer against the circuit (`analysis/gameclock.py`).
#
# The list is community-sourced and the community's lists are from 2022 and
# disagree in the details, so the picker is **editable**: a name GT7 offers and
# this list has missed is typed in, and the measurement is unaffected either
# way. Being over-inclusive costs nothing - a preset this circuit does not have
# simply cannot be selected in the game - while being short of one would stop
# the driver recording what he actually ran.
TIMES_OF_DAY = (
    "Early Dawn", "Dawn", "Sunrise", "Early Morning", "Late Morning",
    "Noon", "Afternoon", "Evening", "Sunset", "Twilight", "Night",
    "Midnight", "Fixed - no time progression",
)
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
        self.setToolTip(f"{code} — space or enter toggles")
        # Eleven controls, mouse-only, in an app whose suite already carries a
        # test called "the nav rail is reachable without a mouse" because the
        # whole of its navigation once was not. This is the regulation for
        # which compounds may appear in a strategy.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{code} allowed")

    def isSelected(self) -> bool:  # noqa: N802 - Qt naming
        return self._selected

    def setSelected(self, selected: bool) -> None:  # noqa: N802 - Qt naming
        self._selected = selected
        self.setStruck(not selected)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._toggle()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return,
                           Qt.Key.Key_Enter):
            self._toggle()
            return
        super().keyPressEvent(event)

    def _toggle(self) -> None:
        self.setSelected(not self._selected)
        self.toggled.emit(self.code() or "", self._selected)


def _rain_value(label: str) -> int | None:
    """Tri-state: unanswered is not "cannot rain"."""
    return {"Can rain": 1, "Cannot rain": 0}.get(label)


def _rain_label(value) -> str:
    if value is None:
        return RAIN_ANSWERS[0]
    return RAIN_ANSWERS[1] if value else RAIN_ANSWERS[2]


class EventScreen(QWidget):
    """Create or edit the event that everything else is filed against."""

    saved = pyqtSignal(dict)
    discarded = pyqtSignal()
    switched = pyqtSignal(object)              # event id, or None for a new one

    def __init__(self, tracks=None, car_groups=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._compound_chips: dict[str, CompoundChip] = {}
        # The identity of what is on the form. Everything the screen saves is
        # written against this id, never against the name - a name is
        # something the driver can change, and matching on it meant renaming
        # an event orphaned every session recorded under the old name.
        self._event_id: int | None = None
        self._events: list[dict] = []
        # Hub rounds with no event row yet, offered under the stored ones.
        self._upcoming: list = []
        self._carried: dict = {}
        # Which calendar round the form is composing, when it is composing one.
        # `_event_id` cannot answer this - a proposal has no event id until it
        # is saved - and without it `_restore_picker` dropped the selection
        # back onto New event the moment the form was filled.
        self._on_round: str | None = None
        # What was loaded, to compare against for unsaved edits.
        self._clean: dict | None = None
        self._pending_switch = _UNSET
        self._tracks = (list(tracks) if tracks is not None
                        else list(catalogs.track_bases()))
        self._car_groups = (list(car_groups) if car_groups is not None
                            else list(
                                catalogs.cars_by_category_and_maker().items()))
        self._build()

    def _known_series(self) -> list[str]:
        """League names already on an event.

        Taken from what the screen has loaded rather than from a store of its
        own - this widget is given its catalogues and does not open the
        archive, and the leagues are already in the events it was handed.
        """
        return sorted({(event.get("series") or "").strip()
                       for event in self._events} - {""})

    def _refresh_series_completer(self) -> None:
        completer = getattr(self, "_series_completer", None)
        if completer is None:
            return
        completer.setModel(QStringListModel(self._known_series()))

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
        elif len(layouts) == 1:
            # Yas Marina has one layout and GT7 calls it Full Course. Leaving
            # it blank would file the event with no layout, which is what the
            # station map and the rain list both key on.
            self.layout_edit.setCurrentText(layouts[0])

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # **Containers before contents** (19 Sep 2026). Under the app-wide
        # style sheet every label carries its own sheet, and moving a
        # finished subtree under a new parent re-polishes all of them again,
        # once per level. The plates used to be built, then moved into the
        # rack, the rack into its scroller, the scroller into the column and
        # the column into the page - four more polishes of every label on
        # the first screen, on the path to the window. Now the scroller is
        # in the page before a plate exists, and each plate moves once.
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        header = QHBoxLayout()
        page.addLayout(header)
        holder = QWidget()
        page.addWidget(holder, 1)
        page.addWidget(self._footer())
        self._header(header)
        self._left_column(holder)

    def _header(self, row: QHBoxLayout) -> QHBoxLayout:
        row.setSpacing(theme.GAP_WIDE)

        column = QVBoxLayout()
        column.setSpacing(2)
        title = StencilLabel("Event", size=theme.TITLE_PX, colour=theme.STENCIL,
                             tracking=6.0)
        column.addWidget(title)
        column.addWidget(BodyLabel(
            "What is being raced, and what is in the car.",
            colour=theme.STENCIL_DIM))
        row.addLayout(column, 1)
        row.addWidget(self._picker_block(), 0,
                      Qt.AlignmentFlag.AlignBottom)
        return row

    def _picker_block(self) -> QWidget:
        """Which event the whole app is working on.

        Every screen behind this one - practice, strategy, race, the prompts -
        reads the active event, so this control is the only thing that decides
        which set of laps you are looking at. It sits in the header rather
        than on a plate for that reason: it is not one more event field, it is
        the thing the fields belong to.
        """
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        box.addWidget(StencilLabel("Working on", size=11,
                                   colour=theme.STENCIL_DIM, tracking=5.0))

        self.event_picker = QComboBox()
        self.event_picker.setMinimumHeight(34)
        self.event_picker.setMinimumWidth(300)
        self.event_picker.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self.event_picker.setToolTip(
            "Switch between the events you are practising for. Each one keeps "
            "its own sessions, laps and strategies - switching loads "
            "them, it never merges them.")
        block_wheel(self.event_picker)
        # `activated` fires only for a choice the driver made. Repopulating
        # the list must not read as a switch.
        self.event_picker.activated.connect(self._on_picker_activated)
        box.addWidget(self.event_picker)

        self.set_events([], None)
        return holder

    # ------------------------------------------------------------- switching

    def set_events(self, events, active_id=None, upcoming=()) -> None:
        """Fill the picker from the store, and from the league calendar.

        `upcoming` is `hub.calendar.Proposal` objects for rounds that have no
        event row yet. They are offered **below** the stored events and under a
        heading, because the two are different kinds of thing: one is a round
        with sessions and laps filed against it, the other is an offer that has
        never been written down. Selecting one fills the form and saves
        nothing until the driver does.

        Never emits `switched`.
        """
        self._events = [dict(event) for event in events]
        self._upcoming = list(upcoming or ())
        # A league typed on one event completes on the next.
        self._refresh_series_completer()
        picker = self.event_picker
        picker.blockSignals(True)
        picker.clear()
        for event in self._events:
            picker.addItem(self._event_label(event), event["id"])
        if self._upcoming:
            # `""` and not `None`: `None` is New event's data and a real
            # target. Empty string can be neither an event id (an int) nor a
            # round id (a cuid), so it can only ever mean the heading.
            picker.addItem(HUB_HEADING, "")
            model = picker.model()
            row = (model.item(picker.count() - 1)
                   if hasattr(model, "item") else None)
            if row is not None:
                row.setEnabled(False)
            for proposal in self._upcoming:
                picker.addItem(self._round_label(proposal), proposal.round_id)
        picker.addItem(NEW_EVENT, None)
        index = -1 if active_id is None else picker.findData(active_id)
        # Last row is New event, and it is where an unsaved event belongs.
        picker.setCurrentIndex(index if index >= 0 else picker.count() - 1)
        picker.blockSignals(False)
        self._pending_switch = _UNSET

    @staticmethod
    def _round_label(proposal) -> str:
        """A calendar row: when it is, then what it is.

        The date leads because this list is ordered by it and the driver is
        reading it to find tonight - a name-first label makes him scan the
        second column to answer the first question he has.
        """
        when = (f"{proposal.scheduled_at:%a %d %b}"
                if proposal.scheduled_at else "date unknown")
        track = (proposal.track or "circuit unmatched").strip()
        return f"{when}  —  {proposal.name}  —  {track}"

    @staticmethod
    def _event_label(event: dict) -> str:
        name = (event.get("name") or "").strip() or f"Event {event.get('id')}"
        track = (event.get("track") or "").strip()
        return f"{name}  —  {track}" if track else name

    def is_dirty(self) -> bool:
        """Has the form been edited since it was loaded?

        Compared against a snapshot rather than tracked per widget: a widget
        wired up today and forgotten tomorrow would silently stop counting as
        an edit, and the cost of that is losing work on a switch.
        """
        return self._clean is not None and self.values() != self._clean

    def _has_content(self) -> bool:
        """Is there anything on this form worth losing?"""
        values = self.values()
        return any(values.get(key)
                   for key in ("name", "track", "car_name", "notes"))

    def _mark_clean(self) -> None:
        self._clean = self.values()

    def _restore_picker(self) -> None:
        picker = self.event_picker
        if self._event_id is None and self._on_round:
            index = picker.findData(self._on_round)
        else:
            index = (-1 if self._event_id is None
                     else picker.findData(self._event_id))
        picker.blockSignals(True)
        picker.setCurrentIndex(index if index >= 0 else picker.count() - 1)
        picker.blockSignals(False)

    def _on_picker_activated(self, index: int) -> None:
        target = self.event_picker.itemData(index)
        if target == "":
            # The calendar heading. Disabled in the list, but keyboard
            # navigation reaches disabled rows under some styles, and a switch
            # to nothing would blank the screen.
            self._restore_picker()
            return
        if target is not None and target == self._on_round:
            self._pending_switch = _UNSET
            return
        if target is not None and target == self._event_id:
            self._pending_switch = _UNSET
            return

        # Unsaved work is not thrown away on one click of a dropdown, and it
        # is not defended with a modal either - the second choice is the
        # confirmation. Nothing here is destructive until it is repeated.
        # **By value, not by identity.** `itemData` round-trips through a C++
        # QVariant and hands back a fresh Python int every call, so `is not`
        # held only while CPython's small-int cache made two 2s the same
        # object. Above id 256 the guard never released: every click re-armed
        # it, the picker snapped back, and an event with unsaved edits on
        # screen could not be reached at all. Event ids are sqlite rowids and
        # are never reused, so this arrives after 256 events over the app's
        # life. `_UNSET` stays a sentinel compared by identity - `None` is a
        # real target here.
        armed = (self._pending_switch is not _UNSET
                 and self._pending_switch == target)
        if self.is_dirty() and not armed:
            self._pending_switch = target
            here = self.name_edit.text().strip() or "this event"
            self.note(f"Unsaved changes to {here}. Save them first, or pick "
                      f"{self.event_picker.itemText(index)} again to discard "
                      f"them.", warn=True)
            self._restore_picker()
            return

        self._pending_switch = _UNSET
        self.switched.emit(target)

    # ----------------------------------------------------------- left column

    def _left_column(self, holder: QWidget) -> QWidget:
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_WIDE)

        scroller = QScrollArea()
        self.left_scroller = scroller
        scroller.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        column.addWidget(scroller, 1)

        inner = QWidget()
        stack = QVBoxLayout(inner)
        stack.setContentsMargins(0, 0, 4, 0)
        stack.setSpacing(theme.GAP_WIDE)
        scroller.setWidget(inner)
        stack.addWidget(self._identity_plate())
        stack.addWidget(self._format_plate())
        stack.addWidget(self._regulations_plate())
        stack.addWidget(self._compounds_plate())
        stack.addWidget(self._context_plate())
        stack.addStretch(1)
        return holder

    def _identity_plate(self) -> Plate:
        plate = Plate("Event")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Round 4 - Fuji")

        # **Which league this round belongs to.** He races more than one at a
        # time with a different team mate in each, and rival evidence is scoped
        # by it - a burn rate from one league's car says nothing about
        # another's. A free line with a completer rather than a picker: a new
        # league has to be typeable the first time it exists, and after that it
        # completes.
        self.series_edit = QLineEdit()
        self.series_edit.setPlaceholderText("GT3 League")
        self._series_completer = QCompleter(self._known_series())
        self._series_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.series_edit.setCompleter(self._series_completer)

        self.track_edit = Picker(self._tracks, placeholder="Pick a track")
        self.track_edit.changed.connect(self._on_track_changed)
        self.layout_edit = Picker(placeholder="—")
        # Class, then maker, then car. A flat `Picker` over 608 cars - 369 of
        # them road cars under one heading - is a scroll, not a choice.
        self.car_edit = CascadingPicker(self._car_groups,
                                        placeholder="Pick a car")

        # GT7 rewrote its physics, tyre model and geometry in 1.49 and again in
        # 1.55, so a measurement without the version it was taken under cannot
        # be compared with the next one, and the export refuses a payload with
        # no version on it.
        #
        # **It is not asked for here any more.** One console runs one version,
        # and asking per event meant an event created without it produced an
        # export that was refused outright with no obvious connection between
        # the empty box and the failure. It lives on the Settings screen and
        # is set once. The field survives, hidden, so an event that already
        # carries a version - a measurement taken under one no longer
        # installed - keeps it and still overrides the app's.
        self.game_version = QLineEdit()
        self.game_version.setVisible(False)

        grid.addWidget(Field("Name", self.name_edit), 0, 0)
        grid.addWidget(Field("Series", self.series_edit,
                             hint="Which league"), 0, 1)
        grid.addWidget(Field("Track", self.track_edit), 1, 0)
        grid.addWidget(Field("Layout", self.layout_edit,
                             hint="Set by the track"), 1, 1)
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
        # `EMPTY` is the range minimum, and without this it renders as
        # "-9999". Every other spin box on this screen says "—"; three did
        # not, on the screen whose whole claim is that a setting nobody
        # entered never reads as a number.
        self.extra_time.setSpecialValueText("—")
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
        # The signal is connected but never fired at build time, so on a
        # fresh screen - which defaults to a lap race - the field the comment
        # below calls "a question with no answer" was the first thing on the
        # Format plate, showing its empty sentinel.
        self._extra_time_field.setVisible(False)
        row.addWidget(Field("Weather", self.weather), 1)
        plate.body.addLayout(row)

        weather_row = QHBoxLayout()
        weather_row.setSpacing(theme.GAP)
        self.weather_rule = QComboBox()
        self.weather_rule.addItems(WEATHER_RULES)
        self.weather_rule.setToolTip(
            "How the league sets weather. Fixed means the round runs one "
            "setting whatever the circuit offers, which makes rain impossible "
            "and wet tyres irrelevant. Random hands it to the circuit.")
        self.rain_possible = QComboBox()
        self.rain_possible.addItems(RAIN_ANSWERS)
        # "Not answered" is a real third state - it is explicitly not "cannot
        # rain" - and it was rendering in crayon, the ink that means he
        # answered. It reads struck until he does.
        mark_unset(self.rain_possible, unset_index=0)
        self.rain_possible.setToolTip(
            "Can this circuit produce rain at all? Most cannot. GT7 broadcasts "
            "no weather channel, so this is the one thing here the app cannot "
            "measure or check - it needs your answer.")
        weather_row.addWidget(Field("Weather rule", self.weather_rule), 1)
        weather_row.addWidget(Field("Rain here", self.rain_possible), 1)
        weather_row.addStretch(1)
        plate.body.addLayout(weather_row)

        # Declared here rather than asked for again when a prompt is written.
        # Every one of these was a form field in the tool this replaced, and
        # every re-entry was a chance to get it wrong.
        second = QHBoxLayout()
        second.setSpacing(theme.GAP)
        self.start_type = QComboBox()
        self.start_type.addItems(START_TYPES)
        self.time_of_day = QComboBox()
        self.time_of_day.addItems(TIMES_OF_DAY)
        # Editable: GT7's per-circuit lists differ and no published table of
        # them is trustworthy. What the setting *does* is measured, not looked
        # up, so an unfamiliar name costs nothing.
        self.time_of_day.setEditable(True)
        self.time_of_day.setToolTip(
            "The lobby's time-of-day setting, in GT7's own words. What hour it "
            "means at this circuit is measured off the game clock the first "
            "time you run it - you do not have to know.")
        block_wheel(self.time_of_day)
        # The in-game clock, numerically. The description above says what it
        # looks like; these say where in the day the race actually runs and
        # how fast GT7's clock moves through it - which is what decides
        # whether practice has ever driven the race's conditions. A 2-hour
        # race at x12 covers a full day and night.
        self.start_hour = QDoubleSpinBox()
        self.start_hour.setSpecialValueText("—")
        self.start_hour.setRange(EMPTY, 23.99)
        self.start_hour.setDecimals(2)
        self.start_hour.setSingleStep(0.5)
        self.start_hour.setValue(EMPTY)
        struck_when_empty(self.start_hour)
        self.start_hour.setToolTip(
            "The in-game hour the race starts, 0-24. 15.5 is half past three "
            "in the afternoon.")

        self.time_multiplier = QDoubleSpinBox()
        self.time_multiplier.setSpecialValueText("—")
        self.time_multiplier.setRange(EMPTY, 100.0)
        self.time_multiplier.setDecimals(1)
        self.time_multiplier.setValue(EMPTY)
        struck_when_empty(self.time_multiplier)
        self.time_multiplier.setToolTip(
            "How fast GT7's clock runs against the real one. At x12 a "
            "two-hour race covers a full day and night, and the track cools "
            "through it.")

        second.addWidget(Field("Start", self.start_type), 1)
        second.addWidget(Field("Time of day", self.time_of_day), 1)
        second.addWidget(Field("Start hour", self.start_hour), 1)
        second.addWidget(Field("Time x", self.time_multiplier), 1)
        plate.body.addLayout(second)
        return plate

    def _on_race_type_changed(self, kind: str) -> None:
        timed = kind == "Timed"
        self._length_unit.setText("MINUTES" if timed else "LAPS")
        # Only when the box still holds the other mode's default. He types
        # 32 laps, flips to Timed to read the extra-time field, flips back -
        # and a declared value had been replaced by a default with nothing
        # saying so, on the screen where everything is his own mark.
        if self.race_length.value() in (20, 45):
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

        # **Both empty until he says otherwise.** They shipped holding 2.5 L/s
        # and 20 s, painted in crayon, and reached `evidence.py` as DECLARED -
        # so the one surface whose whole job is separating measurements from
        # guesses captioned two app defaults "entered". Refuel rate decides
        # the stop count and pit loss decides what a stop costs; on the
        # measured Monza figure of ~1 L/s the 2.5 default is a 2.5x error.
        # Every other optional box on this screen already reads as absent.
        self.refuel_rate = QDoubleSpinBox()
        self.refuel_rate.setRange(EMPTY, 20.0)
        self.refuel_rate.setSingleStep(0.1)
        self.refuel_rate.setSpecialValueText("—")
        self.refuel_rate.setValue(EMPTY)
        struck_when_empty(self.refuel_rate)

        self.pit_loss = QDoubleSpinBox()
        self.pit_loss.setRange(EMPTY, 120.0)
        self.pit_loss.setSingleStep(0.5)
        self.pit_loss.setSpecialValueText("—")
        self.pit_loss.setValue(EMPTY)
        struck_when_empty(self.pit_loss)

        self.mandatory_stops = QSpinBox()
        self.mandatory_stops.setRange(0, 10)

        self.abs_setting = QComboBox()
        self.abs_setting.addItems(ABS_SETTINGS)
        self.abs_setting.setCurrentText("Weak")
        self.tcs = QSpinBox()
        self.tcs.setRange(0, 5)
        self.countersteer = QComboBox()
        self.countersteer.addItems(("Off", "On"))
        self.drivetrain = QComboBox()
        self.drivetrain.addItems(DRIVETRAINS)
        self.fuel_map = QComboBox()
        self.fuel_map.addItems(FUEL_MAPS)

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
        grid.addWidget(Field(
            "Drivetrain", self.drivetrain,
            hint="GT7 sends none - wheelspin watches all four until told"),
            4, 1)
        grid.addWidget(Field(
            "Fuel map", self.fuel_map,
            hint="1 is richest. GT7 sends none, so it is declared"), 5, 0)
        plate.body.addLayout(grid)
        return plate

    def _context_plate(self) -> Plate:
        plate = Plate("This round")
        self.priority = QComboBox()
        self.priority.addItems(PRIORITIES)
        plate.body.addWidget(Field(
            "Priority", self.priority,
            hint="What this round is being prepared for"))
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
        self.discard_button = discard
        self._discard_armed = False
        discard.clicked.connect(self._on_discard)
        row.addWidget(discard)
        save = MarkButton("Save event", primary=True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        return bar

    # --------------------------------------------------------------- actions

    def _reset(self) -> None:
        """Put every field back to the state a fresh screen starts in.

        `load` calls this first, so loading is a replacement rather than an
        overlay. Without it, switching from one event to another would leave
        the first one's declarations on screen - and the next save would file
        them against the second event.
        """
        self.name_edit.clear()
        self.track_edit.setCurrentText("")
        self._on_track_changed("")
        self.layout_edit.setCurrentText("")
        self.car_edit.setCurrentText("")
        self.game_version.clear()

        self.race_type.setCurrentText("Laps")
        self.race_length.setValue(20)
        self.extra_time.setValue(EMPTY)
        self.weather.setCurrentIndex(0)
        self.weather_rule.setCurrentIndex(0)
        self.rain_possible.setCurrentText(RAIN_ANSWERS[0])
        self.start_type.setCurrentIndex(0)
        self.time_of_day.setCurrentIndex(0)
        self.start_hour.setValue(EMPTY)
        self.time_multiplier.setValue(EMPTY)

        self.tyre_mult.setCurrentText("4x")
        self.fuel_mult.setCurrentText("2x")
        self.refuel_rate.setValue(EMPTY)
        self.pit_loss.setValue(EMPTY)
        self.mandatory_stops.setValue(0)
        self.abs_setting.setCurrentText("Weak")
        self.tcs.setValue(0)
        self.countersteer.setCurrentText("Off")
        # Both back to "nobody has said" rather than to a plausible value: a
        # drivetrain carried over from the last event would silence a
        # disclosure the payload currently makes honestly.
        self.drivetrain.setCurrentText("—")
        self.fuel_map.setCurrentText("—")
        self.pp_cap.setValue(EMPTY)

        self.priority.setCurrentIndex(0)
        self.event_notes.clear()

        for code, chip in self._compound_chips.items():
            chip.setSelected(code in ("RH", "RM", "RS"))

    def clear(self) -> None:
        """Blank the form for an event that does not exist yet."""
        self._reset()
        self._event_id = None
        self._on_round = None
        self._carried = {}
        self._restore_picker()
        self._mark_clean()

    def load_proposal(self, proposal) -> None:
        """Compose an event from a hub round, without storing anything.

        A proposal is shaped like an event row precisely so that this can go
        through `load()` rather than through a second, parallel filler that
        would drift from it. `_event_id` stays `None`, so the first Save is a
        create - the hub has proposed and nothing is written until the driver
        accepts.
        """
        self.load(proposal.event_fields())
        self._on_round = proposal.round_id
        self._restore_picker()
        self._mark_clean()

    def load(self, event: dict | None) -> None:
        """Populate from a stored event."""
        self._reset()
        self._event_id = event.get("id") if event else None
        # A stored event is not a calendar proposal. `load_proposal` sets this
        # again immediately after calling us; every other caller means it to be
        # cleared, or the picker would stay parked on the round.
        self._on_round = None
        self._carried = {key: event.get(key) for key in CARRIED
                         if event and event.get(key) is not None}
        if event:
            self.name_edit.setText(event.get("name") or "")
            self.series_edit.setText(event.get("series") or "")
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
            for widget, key in ((self.refuel_rate, "refuel_rate_lps"),
                                (self.pit_loss, "pit_loss_secs")):
                stored = event.get(key)
                widget.setValue(EMPTY if stored is None else float(stored))
            self.mandatory_stops.setValue(int(event.get("mandatory_stops") or 0))
            if event.get("abs_setting"):
                self.abs_setting.setCurrentText(event["abs_setting"])
            if event.get("drivetrain"):
                self.drivetrain.setCurrentText(event["drivetrain"])
            if event.get("fuel_map"):
                self.fuel_map.setCurrentText(str(event["fuel_map"]))
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
            if event.get("weather_rule"):
                self.weather_rule.setCurrentText(event["weather_rule"])
            self.rain_possible.setCurrentText(
                _rain_label(event.get("rain_possible")))
            for widget, key in ((self.start_hour, "start_hour"),
                                (self.time_multiplier, "time_multiplier")):
                value = event.get(key)
                widget.setValue(EMPTY if value is None else float(value))

            allowed = set(event.get("available_compounds") or [])
            for code, chip in self._compound_chips.items():
                chip.setSelected(code in allowed)

        self._restore_picker()
        self._mark_clean()

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.set_ink(theme.WARNING if warn else theme.CHALK)

    def values(self) -> dict:
        """Everything the driver declared on this screen."""
        return {
            # **What the hub declared and this form cannot edit.** First, so
            # that a field the screen genuinely owns always wins over a stale
            # carried copy of the same name.
            **self._carried,
            # Null for an event that has never been saved. The store decides
            # what a null id means; the screen only reports what it loaded.
            "id": self._event_id,
            "name": self.name_edit.text().strip(),
            # Null rather than "", so an unlabelled event reads as one from
            # before there was more than one league rather than as a league
            # called nothing.
            "series": self.series_edit.text().strip() or None,
            "track": self.track_edit.currentText().strip(),
            "layout": self.layout_edit.currentText() or None,
            "car_name": self.car_edit.currentText().strip(),
            "race_type": "laps" if self.race_type.currentText() == "Laps" else "time",
            "race_laps": self.race_length.value(),
            "weather": self.weather.currentText().lower(),
            "tyre_wear_mult": self.tyre_mult.currentText(),
            "fuel_mult": self.fuel_mult.currentText(),
            # Null, never a plausible-looking number. Both of these are what
            # a stop costs, and a guess wearing the shape of a measurement is
            # how the stop count comes out wrong with nothing saying so.
            "refuel_rate_lps": (None if self.refuel_rate.value() <= EMPTY
                                else self.refuel_rate.value()),
            "pit_loss_secs": (None if self.pit_loss.value() <= EMPTY
                              else self.pit_loss.value()),
            "mandatory_stops": self.mandatory_stops.value(),
            "abs_setting": self.abs_setting.currentText(),
            # "—" is nobody has said, and it stays NULL rather than becoming a
            # plausible default. A drivetrain the app guessed would silence a
            # disclosure the payload currently makes honestly.
            "drivetrain": (self.drivetrain.currentText()
                           if self.drivetrain.currentText() != "—" else None),
            "fuel_map": (int(self.fuel_map.currentText())
                         if self.fuel_map.currentText() != "—" else None),
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
            "weather_rule": self.weather_rule.currentText(),
            "rain_possible": _rain_value(self.rain_possible.currentText()),
            "start_hour": (None if self.start_hour.value() <= EMPTY
                           else self.start_hour.value()),
            "time_multiplier": (None if self.time_multiplier.value() <= EMPTY
                                else self.time_multiplier.value()),
            "available_compounds": [code for code, chip
                                    in self._compound_chips.items()
                                    if chip.isSelected()],
        }

    def _on_discard(self) -> None:
        """Guarded the same way switching events is, and it was not.

        Switching the picker with a dirty form refuses the first click and
        asks for a second - a good, modal-free confirmation. Discard loses the
        *same* unsaved work on one click, on a screen holding a whole event,
        a build block and a gearbox. The less deliberate gesture was protected
        and the more deliberate one was not.
        """
        # `is_dirty` compares against a *loaded* event, so a screen that has
        # never loaded one reads clean however much has been typed into it -
        # correct for the switch guard, wrong here. What Discard throws away
        # is whatever is on the form.
        if not (self.is_dirty() or self._has_content()):
            self.note("Nothing to discard.")
            return
        if not self._discard_armed:
            self._discard_armed = True
            self.discard_button.setText("Discard — sure?")
            name = self.name_edit.text().strip() or "this event"
            self.note(f"Press Discard again to throw away unsaved edits to "
                      f"{name}.", warn=True)
            return
        self._discard_armed = False
        self.discard_button.setText("Discard")
        self.discarded.emit()

    def _on_save(self) -> None:
        data = self.values()
        checks = (("a name", data["name"], self.name_edit),
                  ("a track", data["track"], self.track_edit),
                  ("a car", data["car_name"], self.car_edit))
        missing = [(name, editor) for name, value, editor in checks if not value]
        if missing:
            self.footer_note.setText(
                f"Needs {', '.join(name for name, _ in missing)}.")
            self.footer_note.set_ink(theme.WARNING)
            # **And go there.** The note sits at the bottom of a screen with
            # two independently scrolling columns; the three fields it names
            # are at the top of the left one, which may be scrolled anywhere.
            # No screen in this app marked a field as the source of an error,
            # so the message named the problem and left him to hunt for it.
            first = missing[0][1]
            first.setFocus(Qt.FocusReason.OtherFocusReason)
            self.left_scroller.ensureWidgetVisible(first)
            return
        self.footer_note.setText("")
        self.saved.emit(data)
