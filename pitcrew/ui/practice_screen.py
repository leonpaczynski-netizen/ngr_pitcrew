"""Practice — the rack.

He is in a headset while driving and cannot see this screen at all, so nothing
here is designed to be read at speed. This is the surface he comes back to
between stints: mark up what was just run, strike out what does not count,
enter what the gauge said, and send it to the knowledge base.

One row per lap. The compound band runs the full height of the row down its
left edge, so tagging a session paints the rack and the stint structure becomes
visible without reading a number. Measured values are stencil white; everything
the driver marks is crayon; an excluded lap is struck through and its band
loses its voice while keeping its identity.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QFrame,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.analysis.gameclock import clock
from pitcrew.analysis.runs import (
    FOR_QUALIFYING,
    FOR_RACE,
    LOBBY,
    TIME_TRIAL,
    split_runs,
    starts_run,
)
from pitcrew.store.tyres import ALL_COMPOUNDS
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    EmptyState,
    block_wheel,
    mark_unset,
    CompoundBand,
    Declared,
    Field,
    MarkButton,
    Measured,
    Plate,
    SpecLine,
    StencilLabel,
    StrikeRow,
    TyreGauge,
    TyreGaugeSet,
)

ROW_HEIGHT = 54
# A stint-end row is taller because it carries the four-corner gauge, which is
# two gauges deep. The rack is read between runs, not at speed, so the extra
# height costs nothing and the taller row is itself the signal that this is
# where a set came off.
STINT_ROW_HEIGHT = TyreGauge.HEIGHT * 2 + 4 + 12
UNTAGGED = "—"

# Column widths, shared by the heads and the rows so the two never drift.
W_LAP = 34
W_TIME = 132
W_DELTA = 78
W_FUEL = 76
W_MARKER = 84
W_COMPOUND = 104
# Wide enough for "Carried over" without clipping - a picker that silently
# truncates its longest option is how a driver ends up reading the wrong state.
W_SET_ON = 118
W_WEAR = TyreGauge.WIDTH * 2 + 4      # two gauges wide, plus the gap between
W_ACTION = 104
HEAD_HEIGHT = 30
# Everything from the compound picker rightward, so the strike can stop before
# it: three controls, two gaps between them, and the row's right margin.
CONTROLS_WIDTH = (W_COMPOUND + W_SET_ON + W_WEAR + W_ACTION
                  + theme.GAP * 3 + 16)


# The three states of the fresh-set picker. `None` is not `False`: "he has
# not said" and "the set carried over" are different claims, and only one of
# them is evidence.
SET_UNDECLARED = "—"
SET_FRESH = "New set"
SET_CARRIED = "Carried over"
SET_STATES: tuple[tuple[str, bool | None], ...] = (
    (SET_UNDECLARED, None), (SET_FRESH, True), (SET_CARRIED, False))


@dataclass
class LapRow:
    """What the rack shows for one lap."""
    lap_id: int
    lap_num: int
    lap_time_ms: int
    fuel_used: float
    # The tank at both ends of the lap, which is what says where one run stops
    # and the next starts. Display never shows them; the rack needs them to
    # know which rows can carry a fresh-set declaration, and it has to reach
    # that answer by the same rule the export does.
    fuel_start: float = 0.0
    fuel_end: float = 0.0
    # The driver's declaration that this lap went out on a fresh set. Tri-state
    # all the way to the export: None means he has not said.
    tyres_fresh: bool | None = None
    # What the stop before this lap did to the tyres, observed in the stream.
    # None where no stop was captured. The rack needs it because it is what
    # opens a run, and the run boundary is where a fresh set is declared.
    tyres_changed: bool | None = None
    compound: str | None = None
    is_out_lap: bool = False
    is_pit_lap: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None
    wear_fl: float | None = None
    wear_fr: float | None = None
    wear_rl: float | None = None
    wear_rr: float | None = None
    # Which recorded session this lap came from, so the rack can show where
    # one day's running ended and the next began. Display-only.
    session_id: int | None = None
    session_started: str | None = None
    # Where the car started this session: `lobby` or `time-trial`. It decides
    # whether the session's opening lap is an out-lap, which is the one thing
    # about a session GT7 cannot tell us.
    practice_mode: str | None = None
    # This lap's number within its own session, as opposed to the display
    # number that runs through the whole event.
    lap_num_in_session: int = 0
    # Something happened on this lap and the frames say what. Out of the pace
    # and fuel numbers, kept for the corner aggregates — the car is what spun.
    incident: bool = False
    incident_note: str | None = None
    crawl_s: float | None = None
    off_track_s: float | None = None
    spin_s: float | None = None
    # GT7's own clock at the ends of this lap. What the stint header shows as
    # the hours it was driven through, which is the conditions the stint
    # belongs to - GT7 broadcasts no track or air temperature, so this is the
    # only channel that says whether a stint was run in daylight.
    tod_start_ms: int | None = None
    tod_end_ms: int | None = None

    @property
    def counted(self) -> bool:
        return not (self.excluded or self.is_out_lap or self.is_pit_lap)

    def structural_reason(self) -> str | None:
        if self.is_out_lap:
            return "out-lap"
        if self.is_pit_lap:
            return "in-lap"
        if self.incident:
            return "incident"
        return None

    @property
    def is_first_of_session(self) -> bool:
        return self.lap_num_in_session == 1

    @property
    def wear(self) -> dict[str, float | None]:
        return {"fl": self.wear_fl, "fr": self.wear_fr,
                "rl": self.wear_rl, "rr": self.wear_rr}

    def set_wear(self, values: dict[str, float | None]) -> None:
        self.wear_fl = values.get("fl")
        self.wear_fr = values.get("fr")
        self.wear_rl = values.get("rl")
        self.wear_rr = values.get("rr")

    @property
    def worst_wear(self) -> float | None:
        read = [v for v in self.wear.values() if v is not None]
        return max(read) if read else None

    @property
    def worst_corner(self) -> str | None:
        read = {k: v for k, v in self.wear.items() if v is not None}
        return max(read, key=read.__getitem__) if read else None


def run_start_ids(rows: list[LapRow]) -> set[int]:
    """Which laps begin a tank, and so can carry a fresh-set declaration.

    The mirror of `stint_end_ids`: that marks where a set came off and is worth
    a gauge reading, this marks where one may have gone on. Both are the only
    rows that get the control, for the same reason - a screen he visits between
    runs should not ask him the same question on every row.

    The rule itself lives in `analysis.runs` and is shared with the export, so
    a declaration can never land on a lap the export does not treat as a run
    start. Struck laps are included: an out-lap after a stop is struck by
    definition, and it is exactly where a new set goes on.
    """
    if not rows:
        return set()
    starts = {rows[0].lap_id}
    for previous, row in zip(rows, rows[1:]):
        if starts_run(previous, row):
            starts.add(row.lap_id)
    # A declaration already made keeps its control even if the boundary moved -
    # hiding it would hide something he said that is still stored.
    starts.update(row.lap_id for row in rows if row.tyres_fresh is not None)
    return starts


def stint_end_ids(rows: list[LapRow]) -> set[int]:
    """Which laps end a stint, and so are worth a gauge reading.

    A stint ends where the set comes off or stops being used:

    * an in-lap - he came in, so whatever the gauge said is the set's final
      state;
    * the last lap before the compound changes - a different set from here on;
    * the last lap on the rack, because the run stopped there.

    Everything else gets no gauge. A reading taken mid-stint tells the model
    nothing the end-of-stint one does not, and four more controls per row is
    four more things asking to be filled in on a screen he only visits between
    runs.

    Struck laps are skipped when looking ahead, so striking the final lap of a
    stint moves the gauge back to the last lap that still counts rather than
    losing it entirely.
    """
    ends: set[int] = set()
    live = [row for row in rows if row.counted or row.is_pit_lap]
    for index, row in enumerate(live):
        if row.is_pit_lap:
            ends.add(row.lap_id)
            continue
        following = live[index + 1] if index + 1 < len(live) else None
        if following is None:
            ends.add(row.lap_id)
        elif row.compound and following.compound and \
                following.compound != row.compound:
            ends.add(row.lap_id)
    # A reading already entered keeps its gauge even if the lap stopped being
    # a stint end - hiding the control would hide data that is still stored.
    ends.update(row.lap_id for row in rows if row.worst_wear is not None)
    return ends


def format_lap_time(ms: int) -> str:
    if ms <= 0:
        return "--:--.---"
    minutes, remainder = divmod(ms, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def format_delta(ms: int) -> str:
    if ms == 0:
        return "—"
    return f"{'+' if ms > 0 else '−'}{abs(ms) / 1000:.3f}"


class SessionBreak(QWidget):
    """Where one day's running stopped and the next started.

    Laps at an event accumulate across every session, which is what makes
    coming back tomorrow work at all - but without a break in the rack, three
    evenings of running read as one continuous run, and the tyre stint
    structure looks like it spans days.
    """

    HEIGHT = 30

    def __init__(self, started_at: str | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(CompoundBand.WIDTH + 8, 0, 16, 0)
        row.setSpacing(theme.GAP)

        when = "New run"
        if started_at:
            # Stored as an ISO timestamp; the date and the hour are what
            # matter, the seconds are noise.
            when = started_at[:16].replace("T", " ")
        label = StencilLabel(when, size=10, colour=theme.STENCIL_DIM,
                             tracking=14.0)
        row.addWidget(label)

        rule = QWidget()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {theme.TREAD};")
        row.addWidget(rule, 1)


class StintHeader(QWidget):
    """What one stint did, above the laps that did it.

    The same three statistics as the session total below the title - best,
    median, fuel per lap - so the two read as comparable rather than as
    different measurements. A stint is the unit a race is planned in; a
    session is just when he happened to be sitting down.

    It also carries the **game clock**, which costs nothing because
    `time_of_day_ms` is captured on every frame and stored at both ends of
    every lap. GT7 broadcasts neither track nor air temperature, so the hour
    is the only channel that says which conditions a stint's numbers belong
    to - and a race that runs into the dark is not described by a stint driven
    at four in the afternoon.

    Counted laps only, for every figure. An out-lap in the median would make
    every stint look slower than it was, which is the whole reason they are
    struck.
    """

    HEIGHT = 34

    def __init__(self, number: int, rows: list, *, started_at: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        line = QHBoxLayout(self)
        line.setContentsMargins(CompoundBand.WIDTH + 8, 0, 16, 0)
        line.setSpacing(0)

        counted = [row for row in rows if row.counted]
        times = sorted(row.lap_time_ms for row in counted if row.lap_time_ms > 0)
        burns = sorted(row.fuel_used for row in counted if row.fuel_used > 0)

        spec = SpecLine()
        compound = {row.compound for row in rows if row.compound}
        spec.add(f"Stint {number}",
                 compound.pop() if len(compound) == 1 else "—", emphasis=True)
        spec.add("Laps", f"{len(counted)}/{len(rows)}")
        if times:
            spec.add("Best", format_lap_time(times[0]), emphasis=True)
            spec.add("Median", format_lap_time(times[len(times) // 2]))
        if burns:
            spec.add("Fuel", f"{burns[len(burns) // 2]:.2f} L/lap")
        span = game_clock_span(rows)
        if span:
            # Derived ink: it is GT7's clock, not the wall clock, and the two
            # are not the same thing at a time multiplier.
            spec.add("Game", span, derived=True)
        if started_at:
            spec.add("Started", started_at[:16].replace("T", " "), derived=True)
        spec.finish()
        line.addWidget(spec)

        rule = QWidget()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {theme.TREAD};")
        line.addWidget(rule, 1)


def game_clock_span(rows: list) -> str | None:
    """The game hours this stint was driven through, as `16:12 - 18:50`.

    None where no lap of it carried GT7's clock: the channel is absent from
    the packet formats below `~`, and a stint with no clock has nothing to say
    about conditions rather than having been driven at midnight.
    """
    starts = [row.tod_start_ms for row in rows if row.tod_start_ms is not None]
    ends = [row.tod_end_ms for row in rows if row.tod_end_ms is not None]
    if not starts or not ends:
        return None
    first, last = clock(starts[0] / 3_600_000.0), clock(ends[-1] / 3_600_000.0)
    return first if first == last else f"{first} - {last}"


class RackRow(QWidget):
    """One lap in the rack."""

    changed = pyqtSignal(int)
    # Emitted when the edit changes *which* laps end a stint, and so which
    # rows should carry a gauge. Kept apart from `changed` because rebuilding
    # the rack under a drag would pull the gauge out from under the cursor
    # mid-gesture.
    restructured = pyqtSignal(int)

    def __init__(self, row: LapRow, best_ms: int, *, stint_end: bool = False,
                 run_start: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.row = row
        self._stint_end = stint_end
        self._run_start = run_start
        self.setFixedHeight(STINT_ROW_HEIGHT if stint_end else ROW_HEIGHT)

        shell = QHBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.frame = StrikeRow()
        self.frame.setStrikeRight(CONTROLS_WIDTH + theme.GAP)
        shell.addWidget(self.frame)

        line = QHBoxLayout(self.frame)
        line.setContentsMargins(0, 0, 16, 0)
        line.setSpacing(theme.GAP)

        self.band = CompoundBand(row.compound)
        self.band.setFixedWidth(CompoundBand.WIDTH)
        line.addWidget(self.band)

        self.lap_label = Measured(f"{row.lap_num:>2}", colour=theme.STENCIL_DIM)
        self.lap_label.setFixedWidth(W_LAP)
        line.addWidget(self.lap_label)

        self.time_label = Measured(format_lap_time(row.lap_time_ms),
                                   size=theme.DATA_LARGE_PX, bold=True)
        self.time_label.setFixedWidth(W_TIME)
        line.addWidget(self.time_label)

        delta = row.lap_time_ms - best_ms if best_ms else 0
        self.delta_label = Measured(
            format_delta(delta), colour=theme.STENCIL_DIM)
        self.delta_label.setFixedWidth(W_DELTA)
        line.addWidget(self.delta_label)

        self.fuel_label = Measured(f"{row.fuel_used:.2f} L",
                                   colour=theme.STENCIL_DIM)
        self.fuel_label.setFixedWidth(W_FUEL)
        line.addWidget(self.fuel_label)

        marker = self.row.structural_reason()
        self.marker_label = StencilLabel(marker or "", size=11,
                                         colour=theme.STENCIL_DIM, tracking=10.0)
        if self.row.incident_note:
            self.marker_label.setToolTip(self.row.incident_note)
        self.marker_label.setFixedWidth(W_MARKER)
        line.addWidget(self.marker_label)

        line.addStretch(1)

        self.compound_picker = QComboBox()
        self.compound_picker.addItem(UNTAGGED, None)
        for compound in ALL_COMPOUNDS:
            self.compound_picker.addItem(compound.code, compound.code)
        if row.compound:
            self.compound_picker.setCurrentText(row.compound)
        self.compound_picker.setFixedWidth(W_COMPOUND)
        self.compound_picker.currentIndexChanged.connect(self._on_compound)
        self.compound_picker.setToolTip("Which compound this lap ran on")
        block_wheel(self.compound_picker)
        # Untagged reads struck, not crayon: an unset field must never look
        # like a value the driver declared.
        mark_unset(self.compound_picker)
        line.addWidget(self.compound_picker)

        # Only where a set can have gone on: the first lap of a tank. GT7
        # broadcasts no tyre-change event, so this is the only place the fact
        # can enter the app at all - and without it every wear rate rests on
        # assuming the set was fresh at the run's first lap.
        self.set_picker: QComboBox | None = None
        if self._run_start:
            self.set_picker = QComboBox()
            for label, value in SET_STATES:
                self.set_picker.addItem(label, value)
            self.set_picker.setCurrentIndex(
                next(index for index, (_, value) in enumerate(SET_STATES)
                     if value is self.row.tyres_fresh))
            self.set_picker.setFixedWidth(W_SET_ON)
            self.set_picker.currentIndexChanged.connect(self._on_set)
            self.set_picker.setToolTip(
                "Did this run go out on a fresh set?\n\n"
                "GT7 sends no tyre-change event, so nothing else can tell. "
                "Left unsaid, the wear rate still has to assume the set went "
                "on here, and the export says it assumed it. Say so and the "
                "rate is measured.")
            block_wheel(self.set_picker)
            mark_unset(self.set_picker)
            line.addWidget(self.set_picker)
        else:
            spacer = QWidget()
            spacer.setFixedWidth(W_SET_ON)
            line.addWidget(spacer)

        # The gauge only appears where a reading is worth taking. On every
        # other row the column holds its width so the rack stays in line, but
        # holds nothing to fill in.
        self.gauges: TyreGaugeSet | None = None
        if self._stint_end:
            self.gauges = TyreGaugeSet()
            self.gauges.setValues(self.row.wear)
            self.gauges.changed.connect(self._on_wear)
            line.addWidget(self.gauges)
        else:
            spacer = QWidget()
            spacer.setFixedWidth(W_WEAR)
            line.addWidget(spacer)

        self.exclude_button = MarkButton("Strike", parent=self)
        self.exclude_button.setFixedWidth(W_ACTION)
        keep = self.exclude_button.sizePolicy()
        keep.setRetainSizeWhenHidden(True)
        self.exclude_button.setSizePolicy(keep)
        # 34, the floor this app sets for itself everywhere else. This is
        # the most-used control on the busiest screen, once per lap row.
        self.exclude_button.setMinimumHeight(34)
        self.exclude_button.setFont(theme.stencil_font(12, tracking=6.0))
        self.exclude_button.clicked.connect(self._on_exclude)
        line.addWidget(self.exclude_button)

        self._sync()

    # --------------------------------------------------------------- actions

    def _on_compound(self) -> None:
        self.row.compound = self.compound_picker.currentData()
        self.band.setCode(self.row.compound)
        self.changed.emit(self.row.lap_id)
        self.restructured.emit(self.row.lap_id)

    def _on_set(self) -> None:
        if self.set_picker is None:
            return
        self.row.tyres_fresh = self.set_picker.currentData()
        self.changed.emit(self.row.lap_id)

    def _on_wear(self) -> None:
        if self.gauges is None:
            return
        self.row.set_wear(self.gauges.values())
        self.changed.emit(self.row.lap_id)

    def _on_exclude(self) -> None:
        if self.row.structural_reason():
            return
        self.row.excluded = not self.row.excluded
        self._sync()
        self.changed.emit(self.row.lap_id)
        self.restructured.emit(self.row.lap_id)

    def _sync(self) -> None:
        # **A structural lap is dimmed, not ruled through.** Striking says
        # "this did not happen"; an out-lap very much happened and its time is
        # evidence about how long the tyres take to come in and what a stop
        # costs. It is out of the *counted* set, which the dimming and the
        # OUT-LAP marker both say, and it stays legible on the rack rather
        # than being crossed out - which is what he asked for, and the reason
        # he was crossing them out by hand in the first place.
        struck = self.row.excluded and not self.row.structural_reason()
        uncounted = not self.row.counted
        self.frame.setStruck(struck)
        self.band.setStruck(uncounted)

        ink = theme.STENCIL_DIM if uncounted else theme.STENCIL
        self.time_label.setStyleSheet(f"color: {ink}; background: transparent;")

        if self.row.structural_reason():
            # An out-lap, in-lap or incident is structurally uncounted; there
            # is nothing to toggle, and the reason already reads in the marker
            # column. Hidden rather than emptied: a bordered button with no
            # label is a control that looks broken instead of absent. Its
            # space is kept, because a hidden widget surrenders its width to
            # the stretch beside it and every control on the row slides right
            # - so a rack with one out-lap in it has one row out of line with
            # the rest.
            self.exclude_button.setVisible(False)
        else:
            # Labelled with what pressing it does, not with what the lap
            # currently is. "Count" on a lap that was already counted reads as
            # a state, and pressing it does the opposite of what it says.
            self.exclude_button.setVisible(True)
            self.exclude_button.setText(
                "Restore" if self.row.excluded else "Strike")


class PracticeScreen(QWidget):
    """The rack, its spec line, and the export that ends the session."""

    export_requested = pyqtSignal()
    lap_changed = pyqtSignal(int)
    recording_toggled = pyqtSignal(bool)
    practice_mode_changed = pyqtSignal(str)
    practice_intent_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[LapRow] = []
        self._row_widgets: list[RackRow] = []
        self._rendered_ends: set[int] = set()
        self._recording = False
        self._build()

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 24)
        page.setSpacing(theme.GAP_WIDE)

        header = QHBoxLayout()
        header.setSpacing(theme.GAP)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(StencilLabel("Practice", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        self.subtitle = BodyLabel("Waiting for the car to go out.",
                                  colour=theme.STENCIL_DIM)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)

        # Where the car will be when the session starts, which is the one
        # thing about a session the stream cannot tell us and which decides
        # whether its opening lap is an out-lap. Asked here, next to the
        # button, because it is the last thing true before he goes out.
        self.mode_picker = QComboBox()
        self.mode_picker.addItem("Lobby - out of the pits", LOBBY)
        self.mode_picker.addItem("Time trial - on track", TIME_TRIAL)
        self.mode_picker.setToolTip(
            "In a lobby the car starts in the pit box, so the first lap is an "
            "out-lap and the app strikes it for you. "
            "In a time trial it starts on the track ahead of the line, so the "
            "first lap is timed like any other - and it is the fastest lap of "
            "the session more often than not.")
        block_wheel(self.mode_picker)
        self.mode_picker.currentIndexChanged.connect(
            lambda: self.practice_mode_changed.emit(self.practice_mode()))
        header.addWidget(Field("Starting", self.mode_picker), 0,
                         Qt.AlignmentFlag.AlignBottom)

        # What the session is for. It changes nothing about which laps
        # count and everything about what the numbers mean: a qualifying
        # run is one lap on low fuel and fresh rubber, where degradation
        # is noise, and race running is the opposite - the single fastest
        # lap is the noise and the shape of the stint is the measurement.
        self.intent_picker = QComboBox()
        self.intent_picker.addItem("Race running", FOR_RACE)
        self.intent_picker.addItem("Qualifying", FOR_QUALIFYING)
        self.intent_picker.setToolTip(
            "Race running reports the stint: consistency, degradation, "
            "fuel per lap and what the out-lap cost.\n"
            "Qualifying reports the one lap: the best, how close the rest "
            "came, and the fuel it was set on.")
        block_wheel(self.intent_picker)
        self.intent_picker.currentIndexChanged.connect(
            lambda: self.practice_intent_changed.emit(self.practice_intent()))
        header.addWidget(Field("Practising", self.intent_picker), 0,
                         Qt.AlignmentFlag.AlignBottom)

        # Secondary. The run *ends* on the primary, and this screen shipped
        # two crayon fills - one at the top to start and one at the bottom to
        # export. Starting a session is the beginning of the work; the export
        # is what it was all for.
        self.record_button = MarkButton("Start practice")
        self.record_button.clicked.connect(self._toggle_recording)
        header.addWidget(self.record_button, 0, Qt.AlignmentFlag.AlignBottom)
        page.addLayout(header)

        self.spec = SpecLine()
        page.addWidget(self.spec)

        page.addWidget(self._rack_plate(), 1)
        page.addLayout(self._footer())
        self.refresh()

    def _rack_plate(self) -> Plate:
        plate = Plate("Laps")
        plate.body.setContentsMargins(1, 26, 1, 1)
        plate.body.setSpacing(0)

        # The heads ride in their own viewport, scrolled sideways in step with
        # the rows below and never vertically. They used to sit outside the
        # scroll area entirely, which is why the rack refused a horizontal
        # scrollbar: a bar would have slid the rows out from under their own
        # headings. That refusal was safe only while the claim below it held.
        self.head_view = QScrollArea()
        self.head_view.setWidgetResizable(True)
        self.head_view.setFrameShape(QFrame.Shape.NoFrame)
        self.head_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.head_view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.head_view.setWidget(self._column_heads())
        self.head_view.setFixedHeight(HEAD_HEIGHT)

        # The rows lose the width of a vertical scrollbar and the heads do
        # not, so without this the two viewports measure differently and the
        # headings stop a dozen pixels short of their own columns at the far
        # right of a sideways scroll. Reserved rather than measured, and the
        # rows' bar is held on so the reservation is always right: a rack with
        # two laps in it showing a disabled scrollbar is a smaller cost than
        # headings that drift out of line with the columns under them.
        heads = QWidget()
        heads_row = QHBoxLayout(heads)
        heads_row.setContentsMargins(0, 0, 0, 0)
        heads_row.setSpacing(0)
        heads_row.addWidget(self.head_view, 1)
        gutter = QWidget()
        gutter.setFixedWidth(theme.SCROLLBAR_WIDTH)
        gutter.setStyleSheet(f"background: {theme.SHOULDER};")
        heads_row.addWidget(gutter)
        plate.body.addWidget(heads)

        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        # **AsNeeded, not AlwaysOff.** The comment that used to sit here said
        # the rack's fixed columns set the window's own minimum "so it can
        # never be given less than it needs anyway". The window was resized to
        # 1600x1000 unconditionally, and one of this driver's displays gives
        # 1280x752 -- so it was given less than it needed on every single
        # session, and with the bar switched off there was no way to reach the
        # part that had been cut off.
        self.scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroller.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroller.horizontalScrollBar().valueChanged.connect(
            self.head_view.horizontalScrollBar().setValue)

        self.rack = QWidget()
        self.rack_layout = QVBoxLayout(self.rack)
        self.rack_layout.setContentsMargins(0, 0, 0, 0)
        self.rack_layout.setSpacing(0)
        # What the plate says with nothing in it. Practice is the screen he
        # returns to between every stint and the first with any real content,
        # and on a fresh event it was a titled rectangle with column heads
        # over an empty well - the exact thing `EmptyState` was written for,
        # on the one screen that never got one.
        self.rack_empty = EmptyState(
            "No laps yet. Recording a session needs:",
            ("an event, saved on the Event screen",
             "the feed connected — test it in Settings",
             "Start practice, then go out"))
        self.rack_layout.addWidget(self.rack_empty)
        self.rack_layout.addStretch(1)
        self.scroller.setWidget(self.rack)

        plate.body.addWidget(self.scroller, 1)
        return plate

    def _column_heads(self) -> QWidget:
        head = QWidget()
        head.setFixedHeight(HEAD_HEIGHT)
        head.setStyleSheet(f"background: {theme.SHOULDER};")
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 16, 0)
        row.setSpacing(theme.GAP)

        def cap(text: str, width: int) -> StencilLabel:
            label = StencilLabel(text, size=10, colour=theme.STENCIL_DIM,
                                 tracking=14.0)
            label.setFixedWidth(width)
            return label

        row.addWidget(cap("SET", CompoundBand.WIDTH))
        row.addWidget(cap("LAP", W_LAP))
        row.addWidget(cap("TIME", W_TIME))
        row.addWidget(cap("DELTA", W_DELTA))
        row.addWidget(cap("FUEL", W_FUEL))
        row.addWidget(cap("", W_MARKER))
        row.addStretch(1)
        row.addWidget(cap("COMPOUND", W_COMPOUND))
        row.addWidget(cap("SET ON", W_SET_ON))
        row.addWidget(cap("SET OFF", W_WEAR))
        row.addWidget(cap("", W_ACTION))
        return head

    def _footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel(
            "Tag a compound on every counted lap before exporting - fuel and "
            "wear evidence is grouped by compound.",
            size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)

        self.export_button = MarkButton("Export for the knowledge base",
                                        primary=True)
        self.export_button.setToolTip(
            "Copies the gt7-pitcrew payload to the clipboard and writes it "
            "to exports/. The Race Engineer screen embeds the same payload in "
            "a prompt for you; this is for pasting it anywhere else.")
        self.export_button.clicked.connect(self.export_requested.emit)
        row.addWidget(self.export_button)
        return row

    # ------------------------------------------------------------------ data

    def set_laps(self, rows: list[LapRow]) -> None:
        self._rows = list(rows)
        self._rebuild_rack()
        self.refresh()

    def add_lap(self, row: LapRow) -> None:
        self._rows.append(row)
        self._rebuild_rack()
        self.refresh()

    def rows(self) -> list[LapRow]:
        return list(self._rows)

    def _rebuild_rack(self) -> None:
        while self.rack_layout.count():
            item = self.rack_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row_widgets.clear()

        best = self._best_ms()
        ends = stint_end_ids(self._rows)
        starts = run_start_ids(self._rows)
        self._rendered_ends = ends
        # A header per stint rather than a rule per session. A stint is the
        # unit a race is planned in, and a session that goes out three times
        # on three sets is three stints - which the old rule drew as one
        # continuous run of laps.
        self.rack_empty.setVisible(not self._rows)
        if not self._rows:
            self.rack_layout.insertWidget(0, self.rack_empty)
        stints = {run.first_lap: (number, list(run.laps))
                  for number, run in enumerate(split_runs(self._rows), start=1)}
        seen_session: int | None = None
        for row in self._rows:
            new_session = (row.session_id is not None
                           and row.session_id != seen_session)
            if new_session:
                seen_session = row.session_id
            stint = stints.get(row.lap_num)
            if stint is not None:
                number, laps = stint
                self.rack_layout.addWidget(StintHeader(
                    number, laps,
                    # The wall clock only where the sitting changed, so three
                    # stints in one evening do not repeat the same timestamp.
                    started_at=row.session_started if new_session else None))

            widget = RackRow(row, best, stint_end=row.lap_id in ends,
                             run_start=row.lap_id in starts)
            widget.changed.connect(self._on_row_changed)
            widget.restructured.connect(self._on_row_restructured)
            self.rack_layout.addWidget(widget)
            self._row_widgets.append(widget)
        self.rack_layout.addStretch(1)

    def _on_row_changed(self, lap_id: int) -> None:
        self.refresh()
        self.lap_changed.emit(lap_id)

    def _on_row_restructured(self, lap_id: int) -> None:
        """The stint boundaries moved, so the gauges belong on other rows."""
        if stint_end_ids(self._rows) != self._rendered_ends:
            self._rebuild_rack()
            self.refresh()

    def repaint_rows(self) -> None:
        """Redraw the rack against rows something else has already changed.

        Tagging one lap writes the whole stint - that is the point of the
        carry - but the controller mutates the same `LapRow` objects these
        widgets hold, and nothing told the widgets. Four laps went RM in the
        database with their bands still grey, and the footer could read
        "every counted lap is marked" over five visibly unmarked rows.
        """
        self._rebuild_rack()
        self.refresh()

    def _best_ms(self) -> int:
        times = [r.lap_time_ms for r in self._rows if r.counted and r.lap_time_ms > 0]
        return min(times) if times else 0

    def refresh(self) -> None:
        counted = [r for r in self._rows if r.counted]
        times = sorted(r.lap_time_ms for r in counted if r.lap_time_ms > 0)
        burns = [r.fuel_used for r in counted if r.fuel_used > 0]

        self.spec.clear()
        self.spec.add("Counted", f"{len(counted)}/{len(self._rows)}")
        if times:
            self.spec.add("Best", format_lap_time(times[0]), emphasis=True)
        if self.practice_intent() == FOR_QUALIFYING:
            # One lap is the whole measurement here, so what matters is
            # how repeatable it was, not what the middle of the run did.
            # A median over a qualifying run describes laps he was not
            # trying to set a time on.
            if len(times) > 1:
                self.spec.add("2nd best", format_lap_time(times[1]))
                self.spec.add("Spread",
                              f"{(times[1] - times[0]) / 1000:.3f} s",
                              derived=True)
            if counted:
                best_lap = min(counted, key=lambda row: row.lap_time_ms)
                self.spec.add("On", f"{best_lap.fuel_start:.1f} L")
        else:
            if times:
                self.spec.add("Median",
                              format_lap_time(times[len(times) // 2]))
            if burns:
                self.spec.add("Fuel",
                              f"{sorted(burns)[len(burns) // 2]:.2f} L/lap")
        untagged = [r for r in counted if not r.compound]
        if untagged:
            self.spec.add("Untagged", str(len(untagged)), derived=True)
        self.spec.finish()

        # The subtitle belongs to the controller: it carries connection and
        # session state, which refresh() has no way of knowing. Lap counts are
        # already in the spec line.
        if untagged:
            self.footer_note.setText(
                f"{len(untagged)} counted "
                f"{'lap has' if len(untagged) == 1 else 'laps have'} no "
                "compound. Fuel and wear evidence is grouped by compound.")
            self.footer_note.setStyleSheet(f"color: {theme.WARNING};")
        elif counted:
            self.footer_note.setText("Every counted lap is marked.")
            self.footer_note.setStyleSheet(f"color: {theme.STENCIL_DIM};")
        else:
            self.footer_note.setText("Nothing to export yet.")
            self.footer_note.setStyleSheet(f"color: {theme.STENCIL_DIM};")

    def practice_mode(self) -> str:
        return self.mode_picker.currentData()

    def practice_intent(self) -> str:
        return self.intent_picker.currentData()

    def set_practice_intent(self, intent: str | None) -> None:  # noqa: N802
        index = self.intent_picker.findData(intent or FOR_RACE)
        if index >= 0:
            self.intent_picker.blockSignals(True)
            self.intent_picker.setCurrentIndex(index)
            self.intent_picker.blockSignals(False)
            self.refresh()

    def set_practice_mode(self, mode: str | None) -> None:  # noqa: N802 - Qt naming
        index = self.mode_picker.findData(mode or LOBBY)
        if index >= 0:
            self.mode_picker.blockSignals(True)
            self.mode_picker.setCurrentIndex(index)
            self.mode_picker.blockSignals(False)

    def _toggle_recording(self) -> None:
        self.recording_toggled.emit(not self._recording)

    def set_recording(self, recording: bool) -> None:  # noqa: N802 - Qt naming
        """Reflect what the controller actually managed to do, not the click."""
        self._recording = recording
        self.record_button.setText(
            "Stop practice" if recording else "Start practice")

    def set_status(self, text: str, *, warn: bool = False) -> None:  # noqa: N802
        self.subtitle.setText(text)
        self.subtitle.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.STENCIL_DIM};"
            f"background: transparent;")

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};")
