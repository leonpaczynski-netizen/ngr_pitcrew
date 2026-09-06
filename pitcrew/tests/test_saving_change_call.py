"""When the frames say the driver stopped saving, George says so once.

The Deep Forest fill was sized on a stint driven lift-and-coasting; the stint
after it was not; nothing in the car could see either.
"""
from __future__ import annotations

from pitcrew.analysis.driving import DrivingRead
from pitcrew.race.calls import SAVING_CHANGE, RaceState, _saving_change
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


def _read(coast, upshift):
    return DrivingRead(coast_pct=coast, full_throttle_pct=60.0,
                       upshift_rpm=upshift, upshifts=12, frames=5000)


def _race():
    plan = {"stops": 1, "stints": [
        {"laps": 12, "compound": "RS", "fuel_l": 100.0, "start_lap": 1},
        {"laps": 8, "compound": "RS", "fuel_l": 70.0, "start_lap": 13}]}
    race = RaceCoordinator(plan, fuel_per_lap_l=7.5)
    ctx = PlanContext(car="c", track="t", layout=None, race_laps=20)
    assert race.arm(ctx, ctx)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {}))
    return race


def _lap(n):
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=n, lap_time_ms=88_000, best_lap_ms=88_000, delta_ms=0,
        fuel_start=100 - 7.5 * (n - 1), fuel_end=100 - 7.5 * n,
        fuel_used=7.5, position=3, is_pit_lap=False, is_out_lap=False)})


def test_the_step_is_composed_and_said_once():
    race = _race()
    for n, coast, up in ((1, 8.3, 8300), (2, 8.1, 8300), (3, 8.5, 8300),
                         (4, 5.9, 8300), (5, 6.0, 8300)):
        race.handle(_lap(n))
        race.note_driving(n, _read(coast, up))
    note = race.state.saving_change_note
    assert note is not None
    assert note.startswith("You've stopped lift-and-coasting since lap 4")
    call = _saving_change(race.state)
    assert call is not None and call.kind == SAVING_CHANGE
    race.state.record(call)
    assert _saving_change(race.state) is None, "once"


def test_a_short_shift_step_names_the_rpm():
    race = _race()
    for n, coast, up in ((1, 7.0, 8300), (2, 7.0, 8300), (3, 7.0, 8300),
                         (4, 7.0, 8650), (5, 7.0, 8700)):
        race.handle(_lap(n))
        race.note_driving(n, _read(coast, up))
    assert "stopped short-shifting since lap 4" in race.state.saving_change_note
    assert "8300 before" in race.state.saving_change_note


def test_a_stop_restarts_the_history():
    race = _race()
    for n, coast, up in ((1, 8.3, 8300), (2, 8.1, 8300), (3, 8.5, 8300)):
        race.handle(_lap(n))
        race.note_driving(n, _read(coast, up))
    race.handle(SessionEvent(EventKind.PIT_ENTRY, {"fuel": 70.0}))
    race.handle(SessionEvent(EventKind.PIT_EXIT, {"fuel_added": 30.0,
                                                  "tyres_changed": True}))
    assert race._driving == []
    for n, coast, up in ((5, 5.9, 8300), (6, 6.0, 8300)):
        race.note_driving(n, _read(coast, up))
    assert race.state.saving_change_note is None, "two laps cannot say it"


def test_nothing_is_said_without_a_note():
    state = RaceState(lap=5, laps_total=20)
    assert _saving_change(state) is None
