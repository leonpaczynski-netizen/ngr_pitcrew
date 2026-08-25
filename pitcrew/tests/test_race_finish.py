"""The Fuji race never ended, and nothing noticed.

`race_runs.finished_at` stayed null. No chequered flag was called. No export
was generated for the event at all - `prompt_issues` holds nothing for it, so
job 3, the app's most important output, did not run for the race it exists to
describe. The session closed on shutdown **16 minutes 48 seconds** after the
last crossing.

Two causes, one on top of the other:

1. `SessionState` raises RACE_FINISHED when `laps_in_race` minus the number of
   lap ROWS it filed reaches zero. A crossing inside GT7's pit sequence never
   reaches the app, so it filed 19 rows for 20 laps and the count stopped one
   short. The correction already existed one layer up - `RaceState`
   `laps_remaining()` counts `lap + laps_missed()` - and nothing read it as a
   finish.
2. Nothing closed the run except `stop_race`, and `stop_race` is a button.
"""
from __future__ import annotations

import pytest

from pitcrew.race.coordinator import RaceCoordinator, RacePhase
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


def a_lap(num: int, *, position: int = 5) -> Lap:
    return Lap(lap_num=num, lap_time_ms=99_000, best_lap_ms=98_500,
               delta_ms=500, fuel_start=90.0, fuel_end=84.0, fuel_used=6.0,
               position=position, is_pit_lap=False, is_out_lap=False)


def a_race(*, laps_total: int = 20) -> RaceCoordinator:
    race = RaceCoordinator(None)
    race.phase = RacePhase.RUNNING
    race.state.laps_total = laps_total
    race.state.race_minutes = None
    return race


def cross(race: RaceCoordinator, num: int, **over):
    return race.handle(SessionEvent(EventKind.LAP_COMPLETED,
                                    {"lap": a_lap(num, **over)}))


# ------------------------------------------------------- the flag falls

def test_a_lap_race_finishes_on_its_last_crossing():
    race = a_race()

    for num in range(1, 20):
        cross(race, num)
        assert race.phase is RacePhase.RUNNING, f"finished early on lap {num}"

    cross(race, 20)

    assert race.phase is RacePhase.FINISHED
    assert race.state.finished is True


def test_the_fuji_case_a_dropped_crossing_still_finishes():
    """19 rows for 20 laps. The app must not sit waiting for a lap that was
    already driven - which is exactly what it did on 24 Aug."""
    race = a_race()
    for num in range(1, 19):
        cross(race, num)
    # The crossing inside GT7's pit sequence never reached the app, and the
    # clock detected it.
    race.state.laps_dropped = 1

    cross(race, 19)

    assert race.phase is RacePhase.FINISHED, (
        "the race ended a lap ago and the app is still running it")


def test_the_finish_carries_the_position():
    race = a_race()
    for num in range(1, 20):
        cross(race, num)

    cross(race, 20, position=5)

    assert race.state.position == 5


def test_it_cannot_fire_before_the_distance_is_run():
    """`laps_missed` only ever grows the count by a crossing the GAME counted
    and the app did not, so an early finish needs the game to be wrong."""
    race = a_race()

    for num in range(1, 20):
        cross(race, num)

    assert race.phase is RacePhase.RUNNING


def test_a_timed_race_is_untouched_by_this_path():
    """Its distance is an output of the plan, and the clock owns the flag."""
    race = a_race()
    race.state.race_minutes = 30.0
    race.state.laps_total = 20

    for num in range(1, 25):
        cross(race, num)

    assert race.phase is RacePhase.RUNNING


def test_crossings_after_the_flag_do_not_re_finish():
    race = a_race()
    for num in range(1, 21):
        cross(race, num)
    assert race.phase is RacePhase.FINISHED

    cross(race, 21)

    assert race.phase is RacePhase.FINISHED


# --------------------------------------------- the run is closed at the flag

def test_the_run_is_closed_at_the_flag_and_not_at_shutdown(store, monkeypatch):
    """`finish_race_run` ran only from `stop_race`, and `stop_race` is a
    button. A driver who watches the replay or closes the app loses the
    export for a race that is already over."""
    from pitcrew.controller import PitCrewController

    closed: list[int] = []

    controller = PitCrewController.__new__(PitCrewController)
    controller.race = a_race()
    controller.race.state.finished = True
    controller.race.state.lap = 20
    controller.race_run_id = 7
    controller.store = type("S", (), {
        "finish_race_run": lambda _self, run_id: closed.append(run_id)})()

    controller._close_out_finished_race()

    assert closed == [7]
    assert controller.race_run_id is None, "a second crossing must not re-close"


def test_closing_out_is_idempotent():
    from pitcrew.controller import PitCrewController

    closed: list[int] = []
    controller = PitCrewController.__new__(PitCrewController)
    controller.race = a_race()
    controller.race.state.finished = True
    controller.race.state.lap = 20
    controller.race_run_id = 7
    controller.store = type("S", (), {
        "finish_race_run": lambda _self, run_id: closed.append(run_id)})()

    controller._close_out_finished_race()
    controller._close_out_finished_race()

    assert closed == [7]


def test_an_unfinished_race_is_left_open():
    from pitcrew.controller import PitCrewController

    closed: list[int] = []
    controller = PitCrewController.__new__(PitCrewController)
    controller.race = a_race()
    controller.race.state.finished = False
    controller.race_run_id = 7
    controller.store = type("S", (), {
        "finish_race_run": lambda _self, run_id: closed.append(run_id)})()

    controller._close_out_finished_race()

    assert closed == []
    assert controller.race_run_id == 7


def test_a_ledger_failure_never_reaches_the_driver():
    """He has just taken the flag. The app falling over on a write would be
    the last thing he sees of the race."""
    from pitcrew.controller import PitCrewController

    def boom(_self, _run_id):
        raise RuntimeError("disk full")

    controller = PitCrewController.__new__(PitCrewController)
    controller.race = a_race()
    controller.race.state.finished = True
    controller.race.state.lap = 20
    controller.race_run_id = 7
    controller.store = type("S", (), {"finish_race_run": boom})()

    controller._close_out_finished_race()      # must not raise
