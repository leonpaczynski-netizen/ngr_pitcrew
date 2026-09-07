"""What the controller hands the board, and the four things it refuses.

These call the controller's own methods against a stub `self`, because the
thing under test is the arithmetic and the refusals — not the wiring of a
`PitCrewController`, which needs a store, a bridge, a listener and a window.

Every refusal here has the same shape and the same reason: he is stationary in
the box holding the trigger, reading one number. A figure the app invented is
worse than a dash, because a dash he can see is not there.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pitcrew.controller import PitCrewController  # noqa: E402
from pitcrew.race.gaps import GapTrend  # noqa: E402


@dataclass
class _Knowledge:
    """What has been measured at this circuit.

    **No `pit_loss_source`** - and that is the point. `race/knowledge.py`
    defines `pit_loss_s` and `refuel_l_per_s` and nothing else, so the first
    version of `_rejoin_seat` read a source off this object, always got
    `None`, and could never add the 7.5 s dead time. `REJOIN_MARGIN_S` is 3 s,
    so that understated every stop by more than twice the margin that decides
    the verdict. The source lives on the race state; this class not having it
    is what keeps the test honest.
    """
    refuel_l_per_s: float | None = 1.002      # measured at Monza
    pit_loss_s: float | None = 19.0


def _behind(seconds):
    """A real `GapTrend`, because a float is not what production puts there.

    **The first version of these tests set `gap_behind` to a bare float.** The
    controller read it with `getattr(gap, "seconds", gap)`, `GapTrend` has no
    such attribute, and the fallback handed the whole object to
    `rejoin_against` - `TypeError` at the first stop of the first race, board
    dead for the night. Every rejoin test passed. A fake of the wrong type
    tests the fake.
    """
    if seconds is None:
        return None
    trend = GapTrend(side="behind")
    trend.note(12, seconds, subject="rocky")
    return trend


@dataclass
class _State:
    lap: int = 12
    position: int = 6
    in_pit: bool = False
    next_compound: str | None = "RH"
    tyre_compound: str | None = "RM"
    fuel_l: float = 31.0
    fuel_per_lap_l: float | None = 3.4
    stint_index: int = 0
    gap_ahead: object = None
    gap_ahead_name: str | None = None
    gap_behind: object = None
    gap_behind_name: str | None = None
    pit_loss_source: str | None = None
    pit_loss_s: float | None = 19.0
    # **The coordinator merges the briefing into this**, so by the time the
    # board reads it there is one rate for the screen and the voice. The stub
    # models the merged state, not the pre-merge event value - a fake that
    # kept them apart would be testing a shape production does not have.
    refuel_rate_lps: float | None = 1.002
    past_box_lap: bool = False
    stint_ends_on_lap: int | None = None
    finished: bool = False
    _to_stop: int | None = 3

    # **What the two fuel figures read, added 8 Sep 2026.** The board no
    # longer computes a fuel number of its own - it asks `race/calls.py`,
    # which is the whole point of the change: a board expression once said
    # "-7.1 laps of fuel in hand to the flag" with 84 L aboard. Those
    # functions read a real race state, so the stub carries the fields they
    # read, with the same defaults and the same meanings production has.
    # Every one of them is `None` or the neutral value here, so an existing
    # test that says nothing about fuel gets a dash and its reason rather
    # than a number nobody set up.
    laps_total: int | None = None
    laps_after_stops: int | None = None
    laps_dropped: int = 0
    laps_dropped_seen: int = 0
    crossed_in_box: bool = False
    next_stint_laps: int | None = None
    further_stop_planned: bool | None = None
    drop_stop_granted: bool | None = None
    mandatory_stops_left: int | None = None
    plan_binding_constraint: str | None = None
    fuel_capacity_l: float | None = 100.0
    fuel_sd_l: float | None = None
    fuel_reference_load_l: float | None = None
    race_minutes: float | None = None
    laps_estimate_firm: bool = False
    # The lap GT7 is showing him. `lap` counts what is behind him and these
    # are at least one apart - see `RaceState.lap_on_screen`, and the board's
    # `box_on_lap`, which used the wrong one.
    screen_lap: int | None = None

    def laps_to_stop(self):
        return self._to_stop

    def laps_of_fuel(self):
        return 9.1

    def laps_missed(self):
        return max(0, self.laps_dropped, self.laps_dropped_seen)

    def laps_remaining(self):
        if self.laps_total is None:
            return None
        return max(0, self.laps_total - (self.lap + self.laps_missed()))

    def lap_on_screen(self):
        if self.screen_lap is not None:
            return self.screen_lap
        return self.lap + self.laps_missed() + 1


@dataclass
class _Race:
    state: _State = field(default_factory=_State)
    running: bool = True
    knowledge: object = field(default_factory=_Knowledge)
    _stints: list = field(default_factory=list)


@dataclass
class _Packet:
    fuel_level: float = 31.0
    tyre_temp_fl: float = 84.0
    tyre_temp_fr: float = 86.0
    tyre_temp_rl: float = 91.0
    tyre_temp_rr: float = 93.0


class _Bridge:
    def __init__(self, filling=False, packet=None, smoothed=None):
        self.last_packet = packet if packet is not None else _Packet()
        self.refuel = type("R", (), {"filling": filling})()
        self._smoothed = smoothed

    def recent_corner_means(self):
        """The board's 3-second mean, or None to fall through to the packet.

        `None` by default so these tests go on asserting against the single
        frame they set up. The smoothing has its own tests in
        `test_tyre_split.py`; what matters here is that `_board_temps` still
        has an answer when nothing recent is on track - a car sitting in the
        box has an empty window and four real temperatures.
        """
        return self._smoothed


class _Stub:
    """Just enough controller to answer the board's questions.

    The methods under test are **bound off the real class**, not
    reimplemented: a stub that reproduced the arithmetic would pass while the
    controller was wrong, which is the whole failure mode the fake-collaborator
    note in `project_full_event_simulation_harness` is about. Only the
    collaborators are fake.
    """

    _driver_board_state = PitCrewController._driver_board_state
    _board_temps = PitCrewController._board_temps
    _gap_view = PitCrewController._gap_view
    _fill_rate = PitCrewController._fill_rate
    _release_seconds = PitCrewController._release_seconds
    _rejoin_seat = PitCrewController._rejoin_seat
    _next_stint_shape = PitCrewController._next_stint_shape
    _race_knowledge = PitCrewController._race_knowledge

    _someone_set = PitCrewController._someone_set
    _split_rates = PitCrewController._split_rates
    _board_splits = PitCrewController._board_splits
    _board_fuel = PitCrewController._board_fuel

    def __init__(self, *, race=None, bridge=None, target=74.0, event=None,
                 splits=None):
        # **Per instance, never on the class.** A `SplitHistory` shared by
        # every stub in the file would be exactly the cross-session leak the
        # real one is reset to avoid, and it would leak between tests too.
        from pitcrew.race.tyre_split import SplitHistory

        self._splits = splits if splits is not None else SplitHistory()
        # **Built in `__init__`, exactly as the controller builds it.** A
        # board fed a call from a race that is over is CLAUDE.md rule 11, and
        # the named remedy for that rule is a reset that has a caller - so a
        # stub that conjured the attribute on first read would be testing a
        # shape production does not have.
        self._board_call = None
        self.race = race if race is not None else _Race()
        self.bridge = bridge if bridge is not None else _Bridge()
        self._target = target
        # Both sources set: somebody entered both figures. Tests that care
        # about the unset case pass their own.
        self._event = {"pit_loss_source": "declared",
                       "refuel_rate_source": "declared"} if event is None \
            else event

    def _refuel_context(self):
        if self._target is None:
            return None
        return (self._target, self.race.state.fuel_per_lap_l, None)

    def active_event(self):
        """The event row, whose source columns say whether anybody typed the
        figures beside them. `pit_loss_secs` is `NOT NULL DEFAULT 20.0` and
        `refuel_rate_lps` `NOT NULL DEFAULT 2.5`, so the value alone never
        can."""
        return self._event


def _state_for(stub):
    return stub._driver_board_state()


# ------------------------------------------------------------------ on track

def test_on_track_it_shows_the_set_he_is_on_not_the_one_going_on():
    """Two different claims. The box shows the plan's next compound; out on
    track the only honest answer is what is bolted to the car."""
    got = _state_for(_Stub())
    assert got.in_box is False
    assert got.compound == "RM"
    assert got.laps_to_box == 3.0
    assert got.box_on_lap == 15


def test_on_track_none_of_the_box_figures_are_set():
    got = _state_for(_Stub())
    assert got.fuel_target_l is None
    assert got.release_in_s is None
    assert got.out_position is None
    assert got.next_stint_laps is None
    assert got.runs_to_flag is False


def test_a_race_that_is_not_running_draws_nothing():
    stub = _Stub()
    stub.race.running = False
    got = _state_for(stub)
    assert got.in_box is False and got.laps_to_box is None


def test_no_plan_leaves_laps_to_box_missing_rather_than_zero():
    """CLAUDE.md rule 3. A zero here reads as "box now"."""
    stub = _Stub()
    stub.race.state._to_stop = None
    got = _state_for(stub)
    assert got.laps_to_box is None
    assert got.box_on_lap is None


# ---------------------------------------------------------------- in the box

def test_the_tank_rising_switches_the_board_even_before_the_pit_flag():
    """Fuel never rises anywhere but the box, so it is the stronger of the two
    signals and either is enough."""
    stub = _Stub(bridge=_Bridge(filling=True))
    assert _state_for(stub).in_box is True


def test_the_pit_entry_flag_switches_it_too():
    stub = _Stub()
    stub.race.state.in_pit = True
    assert _state_for(stub).in_box is True


def test_in_the_box_it_shows_the_set_going_on():
    stub = _Stub(bridge=_Bridge(filling=True))
    assert _state_for(stub).compound == "RH"


def test_the_countdown_is_the_shortfall_over_the_measured_rate():
    """43 litres to take at 1.002 L/s. Nothing here is assumed: the rate is
    what a stop at this circuit has actually been seen to do."""
    stub = _Stub(bridge=_Bridge(filling=True))
    got = _state_for(stub)
    assert got.fuel_target_l == 74.0
    assert got.release_in_s == pytest.approx(43.0 / 1.002, abs=0.05)


def test_the_countdown_is_refused_where_there_is_no_rate_at_all():
    """A dash, not a figure off another circuit's pump.

    Clearing the briefing alone is no longer enough to reach this: the
    coordinator merges the briefing into `state.refuel_rate_lps`, so the state
    is the single rate and it has to be empty. See
    `test_a_fill_rate_nobody_entered_gives_no_countdown` for the more
    dangerous case - a rate that is present but is only the column default.
    """
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.knowledge = _Knowledge(refuel_l_per_s=None)
    stub.race.state.refuel_rate_lps = None
    assert _state_for(stub).release_in_s is None
    assert _state_for(stub).fill_rate_note is None


def test_a_tank_already_past_target_carries_the_sign_and_reads_GO():
    """**Not clamped to zero.** The clamp was rule 9 at the wrong layer: a
    negative here is a real state - he is already covered - and `format_release`
    renders it as the distinct token `GO`, which is the same answer
    `RefuelWatch.note` gives for the same input. The token is what keeps a
    zero from being mistaken for a measurement, not the clamp."""
    from pitcrew.ui.driver_view import format_release

    stub = _Stub(bridge=_Bridge(filling=True, packet=_Packet(fuel_level=80.0)))
    seconds = _state_for(stub).release_in_s
    assert seconds < 0
    assert format_release(seconds) == "GO"


def test_a_stop_nothing_could_size_carries_no_target_and_no_countdown():
    stub = _Stub(bridge=_Bridge(filling=True), target=None)
    got = _state_for(stub)
    assert got.fuel_target_l is None and got.release_in_s is None


def test_the_tank_comes_off_the_packet_not_the_lap():
    """`state.fuel_l` is written at a crossing and there are no crossings in
    the box, so a countdown fed from it would freeze at whatever it read on
    the way in - on the one number he is sitting there watching."""
    stub = _Stub(bridge=_Bridge(filling=True, packet=_Packet(fuel_level=52.0)))
    assert _state_for(stub).fuel_l == 52.0
    assert stub.race.state.fuel_l == 31.0        # untouched, and different


# ----------------------------------------------------------------- the rejoin

def test_the_gap_is_read_through_the_trend_not_as_a_number():
    """The regression. A `GapTrend` reaching `rejoin_against` raises
    `TypeError` on its first comparison, and the board is gone for the race."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.state.gap_behind = _behind(200.0)
    got = _state_for(stub)                       # must not raise
    assert got.out_position is not None


def test_a_gap_bigger_than_the_stop_keeps_the_place():
    """He was 200 s back; the stop costs about 62. We stay ahead."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.state.gap_behind = _behind(200.0)
    stub.race.state.gap_behind_name = "Rocky"
    got = _state_for(stub)
    assert got.out_position == 6
    assert got.out_behind == "Rocky"


def test_a_gap_smaller_than_the_stop_loses_one():
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.state.gap_behind = _behind(5.0)
    got = _state_for(stub)
    assert got.out_position == 7


def test_an_unread_gap_gives_no_position_at_all():
    """The expected state: the gap boxes have never returned a number in a
    real race."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.state.gap_behind = None
    assert _state_for(stub).out_position is None


def test_a_trend_that_has_read_nothing_yet_gives_no_position():
    """A `GapTrend` exists from the first crossing whether or not the reader
    ever got a number out of the screen, so an empty one is the common case."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.state.gap_behind = GapTrend(side="behind")
    assert _state_for(stub).out_position is None


def test_the_dead_time_is_added_to_a_measured_pit_loss():
    """`stop_costs_s` adds `PIT_DEAD_TIME_S` only when the source says the
    loss was measured here, and the source lives on the state - reading it
    off `Knowledge`, which has no such field, silently never added it."""
    from pitcrew.race.gaps import PIT_LOSS_MEASURED

    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.state.pit_loss_source = PIT_LOSS_MEASURED
    # 43 L at 1.002 plus a 19 s lane is 61.9; the dead time makes it 69.4.
    stub.race.state.gap_behind = _behind(65.0)
    assert _state_for(stub).out_position == 7        # loses it, with the 7.5 s

    stub.race.state.pit_loss_source = None
    assert _state_for(stub).out_position == 6        # holds it, without


def test_a_car_arriving_with_more_than_it_needs_is_refused_not_clamped():
    """CLAUDE.md rule 9. `max(0, target - fuel)` turned "this arithmetic does
    not describe the stop" into a confident lane-only cost, and made
    `stop_costs_s`'s own `litres < 0` refusal unreachable."""
    stub = _Stub(bridge=_Bridge(filling=True,
                                packet=_Packet(fuel_level=90.0)), target=55.0)
    stub.race.state.gap_behind = _behind(30.0)
    assert _state_for(stub).out_position is None


def test_a_gap_too_close_to_call_is_not_reported_as_a_place():
    """`Rejoin.too_close` is a real answer rather than a missing one, and
    rounding it into a position would invent certainty."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.state.gap_behind = _behind(43.0 / 1.002 + 19.0)
    assert _state_for(stub).out_position is None


def test_a_declared_pit_loss_is_used_where_the_briefing_names_none():
    """**The board read `Knowledge.pit_loss_s` alone**, which is None at any
    circuit whose briefing names no stop - so it showed "no gap read" while
    the voice, reading `state.pit_loss_s`, happily made a rejoin call from the
    same race. One number, two sources, opposite answers (rule 12)."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.knowledge = _Knowledge(pit_loss_s=None)
    stub.race.state.gap_behind = _behind(5.0)
    assert _state_for(stub).out_position == 7


def test_a_pit_loss_nobody_entered_is_refused_not_priced():
    """**`events.pit_loss_secs` is `REAL NOT NULL DEFAULT 20.0`**, so a value
    with no source beside it is the schema's, not the driver's. Pricing a stop
    from it puts `P7 / behind Rocky` on the board with no provenance at all -
    rules 3 and 5 - and event 10, the current one, is exactly this case."""
    stub = _Stub(bridge=_Bridge(filling=True),
                 event={"pit_loss_source": None,
                        "refuel_rate_source": "declared"})
    stub.race.knowledge = _Knowledge(pit_loss_s=None)
    stub.race.state.gap_behind = _behind(5.0)
    assert _state_for(stub).out_position is None


def test_a_fill_rate_nobody_entered_gives_no_countdown():
    """`refuel_rate_lps` is `NOT NULL DEFAULT 2.5`. A countdown priced from
    that on a pump running at 1.0 is two and a half times short, on the one
    number he is holding the trigger against."""
    stub = _Stub(bridge=_Bridge(filling=True),
                 event={"pit_loss_source": "declared",
                        "refuel_rate_source": None})
    stub.race.knowledge = _Knowledge(refuel_l_per_s=None)
    got = _state_for(stub)
    assert got.release_in_s is None
    assert got.fill_rate_note is None


def test_a_declared_rate_is_used_and_labelled_where_nothing_was_briefed():
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.knowledge = _Knowledge(refuel_l_per_s=None)
    stub.race.state.refuel_rate_lps = 1.0
    got = _state_for(stub)
    assert got.release_in_s == pytest.approx(43.0, abs=0.05)
    assert got.fill_rate_note == "declared rate"


def test_a_briefed_rate_is_never_labelled_measured():
    """`race/knowledge.py` says of itself "none of them measured here" and
    exports as "race-engineer, declared". The first version of this label read
    "measured here", which puts a desk figure in the measured register on the
    screen whose whole ink system exists to keep those apart."""
    got = _state_for(_Stub(bridge=_Bridge(filling=True)))
    assert got.fill_rate_note == "briefing"
    assert "measur" not in (got.fill_rate_note or "")


# ------------------------------------------------------------- the next stint

def test_the_last_stint_of_a_plan_runs_to_the_flag():
    """The ordinary 1-stop: two stints, he is in the box after the first.

    **This is the branch a real race takes**, and the first version of this
    test did not exercise it - it set `stint_index` to 1 on a two-stint plan,
    which is the plan-exhausted branch below wearing this test's name.
    """
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race._stints = [{"laps": 12}, {"laps": 14}]
    stub.race.state.stint_index = 0
    got = _state_for(stub)
    assert got.runs_to_flag is True


def test_a_stop_the_plan_never_planned_does_not_claim_to_reach_the_flag():
    """An unplanned second stop - damage, a neutralisation, a replan that has
    not landed - runs off the end of the stint list. Saying "FLAG, this stint
    runs to the end" there is a claim about fuel nothing has checked against
    the remaining distance, and it is the dangerous half of rule 13."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race._stints = [{"laps": 12}, {"laps": 14}]
    stub.race.state.stint_index = 1              # already on the last stint
    got = _state_for(stub)
    assert got.runs_to_flag is False
    assert got.next_stint_laps is None
    assert got.past_the_plan is True


def test_a_stint_with_another_stop_after_it_carries_its_length():
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race._stints = [{"laps": 12}, {"laps": 14}, {"laps": 11}]
    stub.race.state.stint_index = 0
    got = _state_for(stub)
    assert got.next_stint_laps == 14
    assert got.runs_to_flag is False


def test_no_plan_at_all_is_not_reported_as_running_to_the_flag():
    """The two reach the board the same way and only one of them means the
    race ends on this set."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race._stints = []
    got = _state_for(stub)
    assert got.runs_to_flag is False and got.next_stint_laps is None


def test_a_finished_race_stops_showing_a_next_stop():
    """**The flag is not a teardown.** `_close_out_finished_race` deliberately
    leaves the race running - the slow-down lap is still being recorded - so
    without a guard the board goes on ticking a laps-to-box and a box-on-lap
    for a race that is over, four times a second, until he presses Stop."""
    stub = _Stub()
    stub.race.state.finished = True
    got = _state_for(stub)
    assert got.laps_to_box is None
    assert got.box_on_lap is None
    assert got.in_box is False
    # The temperatures are still worth having on the slow-down lap.
    assert got.temps_c is not None


# ------------------------------------------- the neighbours, and their words

def _trend(side, readings, subject=7):
    from pitcrew.race.gaps import GapTrend
    trend = GapTrend(side=side)
    for lap, gap in readings:
        trend.note(lap, gap, subject=subject)
    return trend


def _closing(side):
    """Five consecutive laps of a gap shrinking by a second a lap."""
    return _trend(side, [(4, 9.0), (5, 8.0), (6, 7.0), (7, 6.0), (8, 5.0)])


def _opening(side):
    return _trend(side, [(4, 5.0), (5, 6.0), (6, 7.0), (7, 8.0), (8, 9.0)])


def _gap(stub, side):
    return stub._gap_view(side)


def test_catching_the_car_ahead_is_good_news_and_not_urgent():
    stub = _Stub()
    stub.race.state.gap_ahead = _closing("ahead")
    stub.race.state.gap_ahead_name = "Rocky"
    got = _gap(stub, "ahead")
    assert got.seconds == 5.0
    assert "catching" in got.note and "Rocky" in got.note
    assert got.urgent is False


def test_the_same_closing_gap_behind_is_bad_news_and_is_urgent():
    """**The rule-13 trap.** One signed rate, opposite meanings: `GapTrend`
    says "the gap is closing" on both sides, and on the car behind that is him
    catching us. The two sentences must not be interchangeable."""
    stub = _Stub()
    stub.race.state.gap_behind = _closing("behind")
    got = _gap(stub, "behind")
    assert "he is catching" in got.note
    assert got.urgent is True


def test_losing_ground_to_the_car_ahead_is_the_urgent_one():
    stub = _Stub()
    stub.race.state.gap_ahead = _opening("ahead")
    got = _gap(stub, "ahead")
    assert "losing" in got.note and got.urgent is True


def test_pulling_away_from_the_car_behind_is_not(): 
    stub = _Stub()
    stub.race.state.gap_behind = _opening("behind")
    got = _gap(stub, "behind")
    assert "pulling away" in got.note and got.urgent is False


def test_a_trend_inside_the_noise_reads_steady_and_quotes_no_rate():
    """`TREND_WORTH_SAYING_S` is set from the measured scatter of a gap
    series, which is a random walk - a slope over five samples has a standard
    deviation near 0.5 s a lap. Reporting noise is how a driver learns to
    distrust the tool."""
    stub = _Stub()
    stub.race.state.gap_ahead = _trend(
        "ahead", [(4, 9.0), (5, 8.9), (6, 9.1), (7, 8.95), (8, 9.05)])
    got = _gap(stub, "ahead")
    assert got.note.startswith("steady")
    assert "s a lap" not in got.note


def test_too_few_consecutive_laps_is_steady_rather_than_a_slope():
    """A slope through three points is not a trend - rule 4, and the count
    travels with the rate for exactly this."""
    stub = _Stub()
    stub.race.state.gap_ahead = _trend("ahead", [(7, 9.0), (8, 5.0)])
    assert _gap(stub, "ahead").note.startswith("steady")


def test_a_gap_that_was_never_read_gives_no_view_at_all():
    stub = _Stub()
    assert _gap(stub, "ahead") is None
    stub.race.state.gap_behind = _trend("behind", [])
    assert _gap(stub, "behind") is None


def test_both_neighbours_reach_the_board_while_running():
    stub = _Stub()
    stub.race.state.gap_ahead = _closing("ahead")
    stub.race.state.gap_behind = _opening("behind")
    got = _state_for(stub)
    assert got.ahead is not None and got.behind is not None
    assert got.ahead.note != got.behind.note


def test_the_board_prefers_the_smoothed_reading_over_the_frame_in_hand():
    """**What the driver reads.** The board's own docstring claimed a smoothed
    temperature and `_board_temps` returned a single packet, so four numbers
    jittered at 60 Hz against a per-lap signal of about 10 °C."""
    smoothed = {"fl": 81.0, "fr": 82.0, "rl": 88.0, "rr": 99.0}
    stub = _Stub(bridge=_Bridge(smoothed=smoothed))
    assert _state_for(stub).temps_c == smoothed


def test_an_empty_window_still_has_an_answer():
    """A car stationary in the box has no recent on-track frame and four
    perfectly real temperatures. A dash there would be wrong."""
    stub = _Stub(bridge=_Bridge(smoothed=None))
    temps = _state_for(stub).temps_c
    assert temps is not None
    assert set(temps) == {"fl", "fr", "rl", "rr"}


# --- the board's temperature window, and the two threads on it -------------

def test_the_temperature_window_survives_the_telemetry_thread():
    """The crash that took the board off the screen mid-race, 6 Sep 2026.

    `on_packet` appends at 60 Hz on the telemetry thread while the board timer
    reads at 4 Hz on the main thread, and iterating a deque another thread is
    appending to raises `RuntimeError: deque mutated during iteration`. It did,
    105 seconds into a race, and the board did not come back.
    """
    import threading

    from pitcrew.controller import TelemetryBridge, new_temp_window

    bridge = TelemetryBridge.__new__(TelemetryBridge)
    bridge._temp_window, bridge._temp_lock = new_temp_window()

    stop = threading.Event()
    raised: list[BaseException] = []

    def writer():
        from pitcrew.controller import _monotonic
        while not stop.is_set():
            with bridge._temp_lock:
                bridge._temp_window.append(
                    (_monotonic(), (80.0, 81.0, 82.0, 83.0)))

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        for _ in range(400):
            try:
                TelemetryBridge.recent_corner_means(bridge)
            except BaseException as exc:            # noqa: BLE001
                raised.append(exc)
                break
    finally:
        stop.set()
        thread.join(timeout=2.0)

    assert not raised, f"reader raised {raised[0]!r}"


def test_the_temperature_window_cannot_grow_without_bound():
    """Nothing trims it unless somebody reads it, so with the board closed it
    grew for the whole race - 60 Hz for half an hour is 108,000 tuples."""
    from pitcrew.controller import (
        BOARD_SMOOTHING_S, TelemetryBridge, new_temp_window)

    bridge = TelemetryBridge.__new__(TelemetryBridge)
    bridge._temp_window, bridge._temp_lock = new_temp_window()
    for _ in range(50_000):
        bridge._temp_window.append((0.0, (80.0, 80.0, 80.0, 80.0)))
    # Pinned against what the window is FOR, not against the expression that
    # built it - asserting `len <= int(BOARD_SMOOTHING_S * 240)` restates the
    # constructor and cannot fail for any cap, including a wrong one.
    assert bridge._temp_window.maxlen is not None, "unbounded"
    assert len(bridge._temp_window) < 5_000, "half an hour of 60 Hz got in"
    # ...and it can never truncate a real window: 60 Hz for BOARD_SMOOTHING_S
    # is the most a reader will ever ask for, with headroom above it.
    assert bridge._temp_window.maxlen >= BOARD_SMOOTHING_S * 60 * 2


# --- one bad frame is not a broken board -----------------------------------

class _Board:
    """Just enough board to raise on demand and be closed."""

    def __init__(self, fail_for: int):
        self.left = fail_for
        self.closed = False
        self.drawn = 0

    def update_state(self, _state):
        if self.left > 0:
            self.left -= 1
            raise RuntimeError("deque mutated during iteration")
        self.drawn += 1

    def close(self):
        self.closed = True

    def geometry_text(self):
        return "0,0,100,100"

    # Enough of a QWidget for `_open_driver_board` to put it back on screen.
    def show(self):
        self.shown = True

    def raise_(self):
        pass

    def restore_geometry(self, _geometry):
        pass


class _Timer:
    def __init__(self):
        self.running = True

    def stop(self):
        self.running = False


def _board_harness(fail_for: int):
    from pitcrew.controller import PitCrewController

    app = PitCrewController.__new__(PitCrewController)
    app.driver_board = _Board(fail_for)
    app._board_failures = 0
    app._board_failures_total = 0
    app._board_timer = _Timer()
    app.store = None
    app.settings = type("S", (), {"driver_board_geometry": ""})()
    # The real one needs a whole live race; the board's own raise is what is
    # under test here, and it is raised inside the same `try`.
    app._driver_board_state = lambda: None
    return app


def test_a_transient_does_not_cost_him_the_board_for_the_race():
    """6 Sep 2026: one data race tore the board down 105 s into the race and
    it never came back. He noticed and reported it."""
    from pitcrew.controller import (
        BOARD_FAILURES_BEFORE_TEARDOWN, PitCrewController)

    app = _board_harness(fail_for=BOARD_FAILURES_BEFORE_TEARDOWN - 1)
    for _ in range(BOARD_FAILURES_BEFORE_TEARDOWN + 2):
        PitCrewController._push_driver_board(app)
    assert app.driver_board is not None, "the board was torn down"
    assert not app.driver_board.closed
    assert app._board_timer.running
    assert app.driver_board.drawn >= 1
    # A frame that drew clears the run, so the next transient starts again.
    assert app._board_failures == 0


def test_a_board_that_never_draws_still_comes_down():
    """The teardown is right for a board that cannot draw at all: a frozen
    always-on-top panel over the game, looking live, is worse than none."""
    from pitcrew.controller import (
        BOARD_FAILURES_BEFORE_TEARDOWN, PitCrewController)

    app = _board_harness(fail_for=10_000)
    for _ in range(BOARD_FAILURES_BEFORE_TEARDOWN):
        PitCrewController._push_driver_board(app)
    assert app.driver_board is None
    assert not app._board_timer.running


class _SumsThatPause(dict):
    """A sums dict that stops inside the producer's critical section.

    `self._corner_sums[corner] += value` calls `__setitem__`, which happens
    INSIDE `note_corner_temps`'s lock. Pausing there puts the producer exactly
    where the reader must not be able to reach it.
    """

    def __init__(self, *args, inside=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inside = inside
        self.paused_once = False

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self.inside is not None and not self.paused_once:
            self.paused_once = True
            self.inside()


def test_the_producer_holds_the_lock_across_the_whole_update():
    """Deterministic, because the race itself is not.

    Running a producer and a reader flat out for thousands of iterations did
    NOT catch the lock being deleted - the critical section is four lines and
    the interleaving that corrupts it is rare. A test that only sometimes
    fails is a test that will be believed when it passes, so this forces the
    interleaving instead of hoping for it: the producer is stopped inside its
    own critical section and the lock is then asked whether anyone else could
    get in.

    An unlocked producer lets the reader in mid-update, which is how
    `_corner_frames` gets resurrected against zeroed sums.
    """
    import threading

    from pitcrew.controller import TelemetryBridge, new_temp_window

    bridge = TelemetryBridge.__new__(TelemetryBridge)
    bridge._temp_window, bridge._temp_lock = new_temp_window()
    bridge._corner_frames = 0

    inside = threading.Event()
    may_finish = threading.Event()

    def pause_inside():
        inside.set()
        may_finish.wait(timeout=5.0)

    bridge._corner_sums = _SumsThatPause(
        {c: 0.0 for c in ("fl", "fr", "rl", "rr")}, inside=pause_inside)

    thread = threading.Thread(
        target=TelemetryBridge.note_corner_temps,
        args=(bridge, (80.0, 81.0, 82.0, 83.0)), daemon=True)
    thread.start()
    try:
        assert inside.wait(timeout=5.0), "the producer never reached the sums"
        # The whole property, in one line: while the producer is part-way
        # through, nobody else can be.
        got_in = bridge._temp_lock.acquire(blocking=False)
        if got_in:
            bridge._temp_lock.release()
        assert not got_in, (
            "the reader could enter mid-update - the producer is not holding "
            "the lock across the accumulator")
    finally:
        may_finish.set()
        thread.join(timeout=5.0)


def test_the_producer_side_is_locked_too_and_the_test_drives_it():
    """The reader's lock alone is only half of it.

    The first version of this test had its writer thread take the lock itself,
    so deleting the lock from the producer left the suite green - and the
    producer is the thread the whole fix is about. A critic found that, and a
    mutation run confirmed it. This drives `note_corner_temps`, the real
    producer, so removing its lock is now a failing mutation.

    It asserts on the WHOLE-LAP accumulator rather than the window, because
    that is where an unlocked producer fabricates a number instead of raising:
    a clear landing inside `_corner_frames += 1` leaves one frame divided by a
    resurrected count, and a tyre temperature near zero reads like a
    measurement. CLAUDE.md rule 3.
    """
    import threading

    from pitcrew.controller import TelemetryBridge, new_temp_window

    bridge = TelemetryBridge.__new__(TelemetryBridge)
    bridge._temp_window, bridge._temp_lock = new_temp_window()
    bridge._corner_sums = {c: 0.0 for c in ("fl", "fr", "rl", "rr")}
    bridge._corner_frames = 0

    stop = threading.Event()
    trouble: list[str] = []

    def producer():
        while not stop.is_set():
            TelemetryBridge.note_corner_temps(bridge, (80.0, 81.0, 82.0, 83.0))

    thread = threading.Thread(target=producer, daemon=True)
    thread.start()
    try:
        for _ in range(3000):
            try:
                means = TelemetryBridge.take_corner_means(bridge)
            except BaseException as exc:            # noqa: BLE001
                trouble.append(f"raised {exc!r}")
                break
            if means is None:
                continue
            # Every frame carries 80-83 degC, so any mean outside that band is
            # a torn read - and a LOW one is the fabricated near-zero.
            if not all(79.0 <= v <= 84.0 for v in means.values()):
                trouble.append(f"fabricated a mean: {means}")
                break
    finally:
        stop.set()
        thread.join(timeout=2.0)

    assert not trouble, trouble[0]


def test_a_board_that_fails_more_often_than_it_draws_still_stands_down():
    """The hole in a consecutive-only count, found by a critic.

    Eleven failures then a draw, repeating for ever, never reaches the
    consecutive limit - so the panel stays up redrawing once every three
    seconds while looking live, which is the frozen board the teardown exists
    to prevent. The total ceiling is what closes it, and a success does not
    clear that one.
    """
    from pitcrew.controller import (
        BOARD_FAILURES_BEFORE_STANDING_DOWN,
        BOARD_FAILURES_BEFORE_TEARDOWN,
        PitCrewController,
    )

    app = _board_harness(fail_for=0)
    board = app.driver_board
    for _ in range(BOARD_FAILURES_BEFORE_STANDING_DOWN * 2):
        if app.driver_board is None:
            break
        # Eleven raises, then one that draws - for ever.
        board.left = BOARD_FAILURES_BEFORE_TEARDOWN - 1
        for _ in range(BOARD_FAILURES_BEFORE_TEARDOWN):
            if app.driver_board is None:
                break
            PitCrewController._push_driver_board(app)
    assert app.driver_board is None, "it never stood down"
    assert board.drawn > 0, "the pattern never actually drew"


def test_the_failure_counts_belong_to_one_race():
    """CLAUDE.md rule 11. A race that ends on eleven consecutive failures must
    not destroy the next race's board on its first bad frame."""
    from pitcrew.controller import (
        BOARD_FAILURES_BEFORE_TEARDOWN, PitCrewController)

    app = _board_harness(fail_for=BOARD_FAILURES_BEFORE_TEARDOWN - 1)
    for _ in range(BOARD_FAILURES_BEFORE_TEARDOWN - 1):
        PitCrewController._push_driver_board(app)
    assert app._board_failures == BOARD_FAILURES_BEFORE_TEARDOWN - 1

    app.settings.driver_board_enabled = True
    app.driver_board = _Board(fail_for=0)
    app._board_timer.start = lambda _ms: None
    app._push_driver_board = lambda: None
    PitCrewController._open_driver_board(app)
    assert app._board_failures == 0
    assert app._board_failures_total == 0


# ------------------------------------- row 1.8: what the board could not say

def test_the_box_lap_is_the_number_on_his_hud_not_the_apps_count():
    """**They are at least one apart, and further after a lost crossing.**
    `state.lap` counts what is behind him; GT7 shows the lap in progress. Road
    Atlanta ran +1 on lap 1 and +2 by lap 20, so a board saying "plan: lap 11"
    named a lap his screen would never read. `RaceState.lap_on_screen` settles
    it: under a helmet the screen wins.
    """
    stub = _Stub()
    stub.race.state.lap = 8
    stub.race.state._to_stop = 3
    # No crossing lost: the lap in progress is 9, so he boxes at the end of
    # screen lap 11.
    assert _state_for(stub).box_on_lap == 11

    # Two crossings lost in the pit lane. The app still counts 8, GT7 counts
    # 10, and the box lap on his screen is 13.
    stub.race.state.laps_dropped = 2
    assert _state_for(stub).box_on_lap == 13


def test_the_position_and_the_field_reach_the_board():
    """`P8` and `P8 of 9` are different pieces of news, and the second is the
    one he can act on. `cars_in_race` decodes and nothing read it."""
    stub = _Stub()
    stub.race.state.position = 3
    stub.race.state.field_size = 12
    got = _state_for(stub)
    assert got.position == 3 and got.field_size == 12


def test_a_position_nobody_read_arrives_as_none_and_never_as_zero():
    """Rule 3: a zero that means "not measured" gets read as a real value,
    and P0 is not a place anyone finished in."""
    stub = _Stub()
    stub.race.state.position = None
    stub.race.state.field_size = None
    got = _state_for(stub)
    assert got.position is None and got.field_size is None


def test_both_tyre_splits_reach_the_board_with_their_lap_count():
    """The axle gap had no implementation at all before row 1.8 - the module's
    `PAIRS` is left-right only - and the rear pair was invisible in practice,
    because the board only drew a per-corner figure past 10 degC and the
    measured stint reached +4.0."""
    from pitcrew.race.tyre_split import SplitHistory

    history = SplitHistory()
    for lap in range(6):
        history.note_lap({"fl": 62.0, "fr": 62.0,
                          "rl": 70.0, "rr": 70.0 + 2.0 * lap})
    stub = _Stub(splits=history)
    got = _state_for(stub)
    # Rears run 70.0 and 80.0 on the last lap: axle mean 75.0 against 62.0.
    assert got.axle_split_c == pytest.approx(13.0)
    assert got.split_laps == 6
    assert got.rear_pair_hotter == "rr"
    assert got.rear_pair_split_c == pytest.approx(10.0)
    assert got.rear_pair_rate is not None and got.rear_pair_rate > 0


def test_a_split_with_nothing_behind_it_is_absent_rather_than_zero():
    """A missing key is no claim and a zero is "it has settled"; those are
    different things to tell a driver about a tyre."""
    got = _state_for(_Stub())
    assert got.axle_split_c is None
    assert got.axle_split_rate is None
    assert got.rear_pair_hotter is None
    assert got.split_laps == 0


def test_the_two_fuel_figures_reach_the_board_from_the_calls_module():
    """The board computes no fuel number of its own. It asked for one once
    and said "-7.1 laps of fuel in hand to the flag" with 84 L aboard."""
    stub = _Stub()
    state = stub.race.state
    state.lap = 2
    state.laps_total = 20
    state.fuel_l = 84.0
    state.fuel_per_lap_l = 4.19
    state.stint_ends_on_lap = 11
    state.further_stop_planned = False
    state.mandatory_stops_left = 1
    got = _state_for(stub)
    assert got.fuel_to_stop is not None and got.fuel_to_stop_why is None
    assert got.fuel_to_flag is not None and got.fuel_to_flag_why is None
    assert got.fuel_to_flag > 0


def test_a_fuel_figure_that_cannot_be_made_carries_its_reason():
    """Every dash on this board says why. An empty box he cannot account for
    is one he would stop trusting the rest of the screen over."""
    got = _state_for(_Stub())
    assert got.fuel_to_stop is None and got.fuel_to_stop_why
    assert got.fuel_to_flag is None and got.fuel_to_flag_why


def test_the_last_call_is_none_until_something_is_said():
    """And it is built in `__init__`, not conjured on first read: a reset
    with no caller is the shape of rule 11's defect, not the fix for it."""
    stub = _Stub()
    assert stub._board_call is None
    assert _state_for(stub).last_call is None


def test_the_last_call_carries_its_mark_and_the_lap_on_his_screen():
    """Rule 12: the printed mark is `Call.mark()`, the same expression
    `Call.spoken()` builds its suffix from. And the lap is GT7's, because
    `Call.lap` is laps completed and he never saw that number."""
    from pitcrew.controller import PitCrewController
    from pitcrew.race.calls import BOX_NOW, Call

    stub = _Stub()
    stub.race.state.lap = 10
    call = Call(BOX_NOW, 10, "Box this lap.", "Fuel to 63.")
    PitCrewController._note_board_call(
        stub, call.spoken(), call.mark(),
        PitCrewController._screen_lap(stub))
    got = _state_for(stub).last_call
    assert got.text == "Box this lap. Fuel to 63."
    assert got.mark == "instruction"
    assert got.lap == 11


def test_the_flag_keeps_the_result_and_the_tyres_and_drops_the_plan():
    """Position at the chequer is the number he wants; there is no next stop
    to describe, so the fuel and box figures stay blank."""
    from pitcrew.controller import PitCrewController
    from pitcrew.race.tyre_split import SplitHistory

    history = SplitHistory()
    for _ in range(6):
        history.note_lap({"fl": 62.0, "fr": 62.0, "rl": 70.0, "rr": 74.0})
    stub = _Stub(splits=history)
    stub.race.state.finished = True
    stub.race.state.position = 2
    stub.race.state.field_size = 12
    PitCrewController._note_board_call(stub, "Chequered flag.", "instruction",
                                       20)
    got = _state_for(stub)
    assert got.finished is True
    assert got.position == 2 and got.field_size == 12
    assert got.last_call is not None and got.last_call.lap == 20
    assert got.axle_split_c == pytest.approx(10.0)
    assert got.laps_to_box is None
    assert got.fuel_to_stop is None and got.fuel_to_flag is None
