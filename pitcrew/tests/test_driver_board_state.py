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
    gap_behind: object = None
    gap_behind_name: str | None = None
    pit_loss_source: str | None = "declared"
    pit_loss_s: float | None = 19.0
    refuel_rate_lps: float | None = None    # declared on the event page
    past_box_lap: bool = False
    finished: bool = False
    _to_stop: int | None = 3

    def laps_to_stop(self):
        return self._to_stop

    def laps_of_fuel(self):
        return 9.1


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
    def __init__(self, filling=False, packet=None):
        self.last_packet = packet if packet is not None else _Packet()
        self.refuel = type("R", (), {"filling": filling})()


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
    _fill_rate = PitCrewController._fill_rate
    _release_seconds = PitCrewController._release_seconds
    _rejoin_seat = PitCrewController._rejoin_seat
    _next_stint_shape = PitCrewController._next_stint_shape
    _race_knowledge = PitCrewController._race_knowledge

    def __init__(self, *, race=None, bridge=None, target=74.0):
        self.race = race if race is not None else _Race()
        self.bridge = bridge if bridge is not None else _Bridge()
        self._target = target

    def _refuel_context(self):
        if self._target is None:
            return None
        return (self._target, self.race.state.fuel_per_lap_l, None)


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


def test_the_countdown_is_refused_where_no_fill_rate_has_been_measured_here():
    """A dash, not a figure off another circuit's pump."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.knowledge = _Knowledge(refuel_l_per_s=None)
    assert _state_for(stub).release_in_s is None


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

    stub.race.state.pit_loss_source = "declared"
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


def test_the_declared_pit_loss_is_used_where_none_was_measured_here():
    """**The board read `Knowledge.pit_loss_s` alone**, which is None at any
    circuit whose briefing names no stop - so it showed "no gap read" while
    the voice, reading `state.pit_loss_s`, happily made a rejoin call from the
    same race. One number, two sources, opposite answers (rule 12)."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.knowledge = _Knowledge(pit_loss_s=None)
    stub.race.state.gap_behind = _behind(5.0)
    assert _state_for(stub).out_position == 7


def test_no_pit_loss_from_either_source_means_no_rejoin_verdict():
    """`stop_costs_s` returns None if either half is unknown - a stop cost
    built from one of them is not a stop cost."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.knowledge = _Knowledge(pit_loss_s=None)
    stub.race.state.pit_loss_s = None
    stub.race.state.gap_behind = _behind(5.0)
    assert _state_for(stub).out_position is None


def test_the_declared_fill_rate_stands_in_where_none_was_measured():
    """And the board says which it used, because a rate measured at this pump
    and one typed on the event page are not the same claim."""
    stub = _Stub(bridge=_Bridge(filling=True))
    stub.race.knowledge = _Knowledge(refuel_l_per_s=None)
    stub.race.state.refuel_rate_lps = 1.0
    got = _state_for(stub)
    assert got.release_in_s == pytest.approx(43.0, abs=0.05)
    assert got.fill_rate_note == "declared rate"


def test_a_measured_rate_is_preferred_and_labelled():
    got = _state_for(_Stub(bridge=_Bridge(filling=True)))
    assert got.fill_rate_note == "measured here"


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
