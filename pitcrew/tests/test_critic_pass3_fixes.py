"""The third critic pass, answered.

A reading offered twice is one reading; "same set" needs two readings like
"fresh set"; the driver's word overrules any verdict aloud and is written back
against the stop it names; a word said in the lane waits for pit exit; rig
notices are released on stop_race and at the flag, never per event.
"""
from __future__ import annotations

import pathlib

from pitcrew.race.calls import RaceState, clear_stint
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.telemetry.session_state import EventKind, SessionEvent


def _open_stop():
    state = RaceState(lap=13, laps_since_stop=13, laps_total=20,
                      wear_history=[(12, {"fr": 0.42})])
    clear_stint(state, tyres_changed=None)
    return state


def test_a_reading_offered_twice_is_one_reading():
    """The sampler holds its last good read and the controller offers it at
    every crossing: one all-zero misread must not count as two."""
    state = _open_stop()
    state.note_wear(14, {"fr": 0.0})
    state.note_wear(14, {"fr": 0.0})
    assert state.tyre_change_unconfirmed is True
    assert state.parked_wear == [(14, {"fr": 0.0})]


def test_same_set_needs_two_readings_too():
    """One stale grab of the old set at 0.40 must not latch the verdict."""
    state = _open_stop()
    state.note_wear(14, {"fr": 0.40})
    assert state.tyre_change_unconfirmed is True
    state.note_wear(15, {"fr": 0.02})
    state.note_wear(16, {"fr": 0.03})
    assert state.tyre_change_resolution == "gauge: fresh set"
    state = _open_stop()
    state.note_wear(14, {"fr": 0.40})
    state.note_wear(15, {"fr": 0.43})
    assert state.tyre_change_resolution == "gauge: same set"


def test_the_drivers_word_overrules_the_session_and_is_written_back():
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fr": 0.42})])
    clear_stint(state, tyres_changed=True)
    assert state.tyre_change_resolution == "session: swap seen"
    state.lap = 15
    state.note_tyres_word(False, lap=15)
    assert state.tyre_change_resolution == "driver: no tyres"
    assert state.tyre_change_disagreement == ("session: swap seen",
                                              "driver: no tyres")
    assert state.tyre_change_write_back == (13, False, "driver: no tyres")


def test_no_tyres_puts_the_old_set_back_under_the_projection():
    """Critic pass 4: the ledger said his word stood while the live wear
    projection still counted the set as fresh - `clear_stint(True)` had
    zeroed the count and emptied the history, and the overrule restored
    neither. The old laps and readings come back, ahead of the new ones."""
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(11, {"fr": 0.38}), (12, {"fr": 0.42})],
                      temp_history=[(12, 80.0, 84.0)])
    clear_stint(state, tyres_changed=True)
    assert state.laps_since_stop == 0 and state.wear_history == []
    # Two laps run and one reading taken on what the session thinks is a
    # fresh set.
    state.lap = 15
    state.laps_since_stop = 2
    state.note_wear(15, {"fr": 0.47})
    state.note_tyres_word(False, lap=15)
    assert state.laps_since_stop == 15, "13 before the stop plus 2 since"
    assert [lap for lap, _ in state.wear_history] == [11, 12, 15]
    assert state.temp_history == [(12, 80.0, 84.0)]
    assert state.stint_before_stop is None


def test_new_tyres_confirmed_drops_the_held_old_set():
    state = RaceState(lap=13, laps_since_stop=13,
                      wear_history=[(12, {"fr": 0.42})])
    clear_stint(state, tyres_changed=True)
    state.lap = 15
    state.note_tyres_word(True, lap=15)
    assert state.stint_before_stop is None
    assert state.wear_history == []


def test_a_driver_overrule_of_the_gauge_names_the_stop_and_the_count():
    state = _open_stop()
    state.note_wear(14, {"fr": 0.45})
    state.note_wear(15, {"fr": 0.47})
    assert state.tyre_change_resolution == "gauge: same set"
    state.note_tyres_word(True, lap=15)
    assert state.tyre_change_write_back == (13, True, "driver: new tyres")
    assert state.laps_since_stop == 2, "15 - 13, not zero"


def test_agreement_is_not_an_overrule():
    state = _open_stop()
    state.note_wear(14, {"fr": 0.0})
    state.note_wear(15, {"fr": 0.02})
    state.note_tyres_word(True, lap=15)
    assert state.tyre_change_resolution == "gauge: fresh set"
    assert state.tyre_change_disagreement is None


def test_a_word_said_in_the_lane_waits_for_pit_exit():
    plan = {"stops": 1, "stints": [
        {"laps": 12, "compound": "RS", "fuel_l": 100.0, "start_lap": 1},
        {"laps": 8, "compound": "RS", "fuel_l": 70.0, "start_lap": 13}]}
    race = RaceCoordinator(plan, fuel_per_lap_l=7.5)
    ctx = PlanContext(car="c", track="t", layout=None, race_laps=20)
    assert race.arm(ctx, ctx)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {}))
    race.state.wear_history = [(11, {"fr": 0.4})]
    race.handle(SessionEvent(EventKind.PIT_ENTRY, {"fuel": 10.0}))
    race.note_tyres_word(True)
    assert race.state.tyre_change_resolution is None, "held in the lane"
    race.handle(SessionEvent(EventKind.PIT_EXIT, {"fuel_added": 60.0,
                                                  "tyres_changed": None}))
    assert race.state.tyre_change_resolution == "driver: new tyres"
    assert race.state.tyre_change_unconfirmed is False
    assert race.state.laps_since_stop == 0


def test_rig_notices_are_released_on_stop_and_at_the_flag_only():
    source = (pathlib.Path(__file__).resolve().parents[1] / "controller.py"
              ).read_text(encoding="utf-8")
    start = source.index("    def stop_race(self)")
    end = source.index("\n    def ", start + 10)
    assert "release_notices()" in source[start:end]
    start = source.index("    def _close_out_finished_race(self)")
    end = source.index("\n    def ", start + 10)
    assert "release_notices" not in source[start:end]
