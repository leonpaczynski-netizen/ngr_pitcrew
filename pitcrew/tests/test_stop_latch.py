"""The cancelled stop, latched (carried from row 1.10, plan §9a).

"The retirement of a cancelled stop has no latch, so a burn median that
moves back across the margin makes the countdown vanish and return - rule
10's shape." `laps_to_stop()` returned None whenever `stop_still_needed` was
false, re-evaluated on every read, so the driver who had heard "You're
fuelled to the flag. No more stops on fuel." could watch the countdown come
back on the next lap's burn and go again on the one after.

Rule 10 asks for two guards and this has both: a single contrary reading
does not bring the stop back (the latch), and a SUSTAINED run of them does,
because a retirement everything since disagrees with is the thing that is
wrong. And the reinstatement is said - he was told the stop was off, so it
coming back silently is the contradiction the retirement call was written
to prevent.

Unreachable on every plan on file today (all grant `fuel_long` recost or
report, never `drop_stop`), which is why it came after the voice pack.
"""
from __future__ import annotations

from pitcrew.race.calls import (STOP_BACK, STOP_BACK_LAPS, STOPS_OFF,
                                RaceState, next_call)


def _fuelled(**over) -> RaceState:
    """A fuel-bound one-stop, drop granted, carrying enough to the flag."""
    fields = dict(lap=8, laps_total=20, stint_ends_on_lap=10, fuel_l=60.0,
                  fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                  plan_binding_constraint="fuel", mandatory_stops_left=0,
                  drop_stop_granted=True)
    fields.update(over)
    return RaceState(**fields)


def _tell(state):
    call = next_call(state)
    assert call is not None and call.kind == STOPS_OFF, call
    state.record(call)
    return call


def test_the_stop_retires_when_he_is_told_and_stays_retired():
    state = _fuelled()
    _tell(state)
    assert state.laps_to_stop() is None
    # One lap's burn moves the median back across the margin.
    state.fuel_per_lap_l = 6.0
    state.note_stop_need()
    assert state.laps_to_stop() is None, "one contrary lap is not a reversal"


def test_a_sustained_reversal_brings_the_stop_back_and_says_so():
    state = _fuelled()
    _tell(state)
    state.fuel_per_lap_l = 6.0
    for _ in range(STOP_BACK_LAPS):
        state.note_stop_need()
    assert state.laps_to_stop() == 2
    call = next_call(state)
    assert call is not None and call.kind == STOP_BACK
    assert call.call.startswith("The stop is back on.")
    assert "Fuel won't reach the flag." in call.reason
    state.record(call)
    # Said once.
    again = next_call(state)
    assert again is None or again.kind != STOP_BACK


def test_a_reversal_that_does_not_last_resets_the_count():
    state = _fuelled()
    _tell(state)
    state.fuel_per_lap_l = 6.0
    state.note_stop_need()
    state.fuel_per_lap_l = 3.0
    state.note_stop_need()
    state.fuel_per_lap_l = 6.0
    state.note_stop_need()
    assert state.laps_to_stop() is None, "the run has to be consecutive"


def test_a_stop_the_desk_did_not_let_him_drop_never_latches():
    """The rail withholds `drop_stop` and he hears the report form - the stop
    stands, so nothing is retired and nothing can come back."""
    state = _fuelled(drop_stop_granted=False)
    call = next_call(state)
    if call is not None and call.kind == STOPS_OFF:
        state.record(call)
    assert state.laps_to_stop() == 2


def test_a_stop_taken_clears_the_latch_for_the_next_one():
    """The latch belongs to the stop it retired. Carried across a stop, it
    would silence the NEXT stop's countdown from its first lap - rule 11's
    shape, state outliving its subject."""
    from pitcrew.race.coordinator import RaceCoordinator

    plan = {"stints": [{"laps": 7, "start_lap": 1},
                       {"laps": 7, "start_lap": 8},
                       {"laps": 6, "start_lap": 15}],
            "binding_constraint": "fuel"}
    race = RaceCoordinator(plan, fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=3.0,
                           planned_lap_time_ms=90_000, mandatory_stops=0)
    race.state.stop_retired = True
    race.state.stop_back_laps = 1
    race.state.stop_back_due = True
    race._apply_stint(1, over_a_stop=True)
    assert race.state.stop_retired is False
    assert race.state.stop_back_laps == 0
    assert race.state.stop_back_due is False
    assert race.state.stint_ends_on_lap == 14


def test_a_retired_stop_can_retire_again_after_it_came_back():
    state = _fuelled()
    _tell(state)
    state.fuel_per_lap_l = 6.0
    for _ in range(STOP_BACK_LAPS):
        state.note_stop_need()
    state.record(next_call(state))                  # "The stop is back on."
    state.fuel_per_lap_l = 3.0
    state.note_stop_need()
    call = next_call(state)
    assert call is not None and call.kind == STOPS_OFF, (
        "told it was back on, he must be told again when it is off")
