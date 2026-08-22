"""The measured wear call - the one the app exists to be able to make.

`CLAUDE.md` 3.3 calls the absent wear channel the single most consequential
fact in the document. The HUD gauge is the game's own readout of it, so this is
the first wear call in the app that names a number without a model underneath.

Which means the tests that matter here are not "does it fire". They are: does
it stay quiet when the gauge has not said enough, and does it never once
present the projection as the measurement.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.wear import STINT_SAFETY_FACTOR
from pitcrew.race.calls import (
    HIGH,
    MEDIUM,
    WEAR,
    WEAR_STINT_LIMIT,
    RaceState,
    _wear,
    _wear_rate,
    clear_stint,
    next_call,
)


def a_stint(start: float = 0.40, rate: float = 0.055, laps: int = 4,
            first_lap: int = 6) -> list[tuple[int, dict]]:
    """Readings whose worst corner is RL, wearing at a stated rate a lap."""
    out = []
    for step in range(laps):
        worst = start + rate * step
        out.append((first_lap + step, {
            "fl": worst - 0.10, "fr": worst - 0.12,
            "rl": worst, "rr": worst - 0.05}))
    return out


def state_with(readings, *, lap: int, fuel_l: float = 60.0,
               fuel_per_lap_l: float = 5.0) -> RaceState:
    state = RaceState(lap=lap, fuel_l=fuel_l, fuel_per_lap_l=fuel_per_lap_l)
    for at, wear in readings:
        state.note_wear(at, wear)
    return state


# ------------------------------------------------------------ staying quiet

def test_two_readings_are_not_a_rate():
    """Two points and a quantum of noise is a rate of anything you like."""
    assert _wear(state_with(a_stint(laps=2), lap=8)) is None


def test_a_gauge_that_has_barely_moved_says_nothing():
    """One pixel is 3.3% of tyre life. A span inside two of them is the bar
    crossing a boundary, not the tyre wearing."""
    flat = a_stint(start=0.40, rate=0.01, laps=4)
    assert _wear(state_with(flat, lap=10)) is None


def test_a_gauge_that_stopped_reading_stops_the_call():
    """A projection from a reading five laps old is about a tyre he was on."""
    assert _wear(state_with(a_stint(), lap=9)) is not None
    assert _wear(state_with(a_stint(), lap=15)) is None


def test_wear_going_backwards_is_a_reading_problem_not_a_finding():
    """A tyre does not repair itself. A negative fit is refused, never
    reported as a tyre that has stopped wearing."""
    backwards = [(lap, wear) for lap, wear in
                 zip([6, 7, 8, 9],
                     [w for _, w in reversed(a_stint())])]
    assert _wear_rate(state_with(backwards, lap=10)) is None


def test_nothing_is_said_in_the_pits_or_after_the_flag():
    for field in ("in_pit", "finished"):
        state = state_with(a_stint(), lap=10)
        setattr(state, field, True)
        assert _wear(state) is None


# --------------------------------------------------- measured vs projected

def test_the_number_spoken_is_the_reading_and_never_the_projection():
    """**The defect this guards is one this call shipped with in draft.**

    The decision is taken on the carry-forward - reading plus the fitted rate
    across the laps since - because that is where the tyre actually is. But
    CLAUDE.md 4.5 forbids presenting anything derived as measured, and the
    draft said "RL measured at 99 percent" off a gauge that read 88.
    """
    readings = a_stint(start=0.60, rate=0.09, laps=4)   # ends at 0.87 on lap 9
    state = state_with(readings, lap=11)                # two laps of carry
    call = _wear(state)
    assert call is not None
    assert "87 percent" in call.reason
    assert "measured" in call.reason
    # ...and the projection, which is past the limit, is what made it a box
    # call rather than a note.
    assert call.call.startswith("Box")


def test_the_limit_matches_the_offline_one():
    """Two numbers that must agree and cannot see each other is how they come
    to disagree. `analysis/wear.py` owns the figure; this restates it."""
    assert WEAR_STINT_LIMIT == STINT_SAFETY_FACTOR


# ------------------------------------------------------------- the occasions

def test_the_tyres_being_the_constraint_is_the_call_measurement_buys():
    """Every box call above this reasons about fuel. Without a measured wear
    figure a tyre-limited stint is run to a fuel-limited schedule."""
    state = state_with(a_stint(), lap=10, fuel_l=90.0, fuel_per_lap_l=5.0)
    call = _wear(state)
    assert call is not None and call.kind == WEAR
    assert "Tyres are the constraint" in call.call
    assert call.confidence == MEDIUM      # it rests on a fitted rate


def test_it_stays_quiet_when_the_fuel_runs_out_first():
    """Then the box calls own the decision and this has nothing to add."""
    state = state_with(a_stint(), lap=10, fuel_l=15.0, fuel_per_lap_l=5.0)
    assert _wear(state) is None


def test_inside_a_lap_of_each_other_the_ordering_is_noise():
    """A fitted gauge slope against a fuel burn. Calling it that close would
    have him stopping early on the strength of arithmetic."""
    laps_left = _wear_laps(state_with(a_stint(), lap=10))
    tight = state_with(a_stint(), lap=10,
                       fuel_l=(laps_left + 0.5) * 5.0, fuel_per_lap_l=5.0)
    call = _wear(tight)
    assert call is None or "constraint" not in call.call


def _wear_laps(state) -> float:
    from pitcrew.race.calls import _wear_laps_left
    return _wear_laps_left(state)[0]


def test_past_the_limit_is_an_instruction_at_high_confidence():
    readings = a_stint(start=0.70, rate=0.08, laps=4)
    call = _wear(state_with(readings, lap=10))
    assert call is not None
    assert call.call == "Box this lap."
    assert call.confidence == HIGH


def test_a_corner_going_first_is_a_balance_call_not_a_pit_call():
    """The gauge is per corner, and brake balance is adjustable mid-race.
    Axle-asymmetric wear cannot be solved with strategy (CLAUDE.md 5.4)."""
    readings = [(6, {"fl": 0.20, "fr": 0.19, "rl": 0.34, "rr": 0.22}),
                (7, {"fl": 0.23, "fr": 0.22, "rl": 0.41, "rr": 0.25}),
                (8, {"fl": 0.26, "fr": 0.25, "rl": 0.48, "rr": 0.28})]
    state = state_with(readings, lap=9, fuel_l=200.0)
    state.wear_said.add("limited")        # so the balance call is what is left
    call = _wear(state)
    assert call is not None
    assert "rearward" in call.call
    assert "RL" in call.reason


def test_the_balance_call_never_asks_for_forward_bias():
    """A standing refusal of his. A front corner going first is still worth
    naming - it is just not an instruction he takes."""
    readings = [(6, {"fl": 0.34, "fr": 0.20, "rl": 0.19, "rr": 0.22}),
                (7, {"fl": 0.41, "fr": 0.23, "rl": 0.22, "rr": 0.25}),
                (8, {"fl": 0.48, "fr": 0.26, "rl": 0.25, "rr": 0.28})]
    state = state_with(readings, lap=9, fuel_l=200.0)
    state.wear_said.add("limited")
    call = _wear(state)
    assert call is not None
    assert "forward" not in call.call
    assert call.call == "FL is going first."


def test_an_occasion_repeats_until_it_is_actually_said():
    """**The defect this replaced.** `wear_said` was marked inside the function
    that BUILDS the call, and `next_call` builds every candidate and then
    ranks - so a wear finding that lost one crossing to a box call marked
    itself said and was never spoken again. Only the call actually made may
    record that it was made."""
    state = state_with(a_stint(), lap=10, fuel_l=200.0)
    first = _wear(state)
    assert first is not None and first.tag == "limited"
    # Not spoken, so still offered.
    assert _wear(state).tag == "limited"
    state.record(first)
    assert _wear(state) is None


# ----------------------------------------------------------------- the stint

def test_a_fresh_set_throws_the_readings_away():
    """A rate fitted across a stop describes neither set - the gauge snaps
    back to white, and a line through that discontinuity reports a tyre that
    repairs itself."""
    state = state_with(a_stint(), lap=10)
    clear_stint(state, tyres_changed=True)
    assert state.wear_history == []
    assert state.wear_said == set()
    assert _wear(state) is None


def test_a_stop_that_kept_the_tyres_keeps_the_readings():
    """GT7 lets you take fuel without taking tyres, and the wear carries on."""
    state = state_with(a_stint(), lap=10)
    clear_stint(state, tyres_changed=False)
    assert len(state.wear_history) == 4


def test_a_repeated_lap_is_not_a_second_point():
    """With the sampler free-running the same held reading can be offered at
    two crossings. Counted twice it flattens the rate - a tyre that has
    stopped wearing, the one direction this must never err in."""
    state = state_with(a_stint(), lap=10)
    before = list(state.wear_history)
    state.note_wear(state.wear_history[-1][0], {"rl": 0.99})
    assert state.wear_history == before


def test_an_empty_reading_files_nothing():
    """All four corners unreadable is not a reading of zero."""
    state = RaceState(lap=5)
    state.note_wear(5, {"fl": None, "fr": None, "rl": None, "rr": None})
    state.note_wear(5, None)
    assert state.wear_history == []


# ------------------------------------------------------------ in the ranking

def test_fuel_still_outranks_it():
    """A car out of fuel stops on the circuit; a car on worn tyres is still
    moving. `_wear` sits below the box calls deliberately."""
    state = state_with(a_stint(), lap=10, fuel_l=4.0, fuel_per_lap_l=5.0)
    state.laps_total = 20
    state.stint_ends_on_lap = 10
    call = next_call(state)
    assert call is None or call.kind != WEAR


def test_it_reaches_the_ranking_at_all():
    """The retired `_tyre` was left out of `_candidates`; this replaced it,
    and a call nobody calls is the same as no call."""
    # Fuel comfortable and the race short, so nothing above it has anything
    # to say and the ranking is what decides.
    state = state_with(a_stint(), lap=10, fuel_l=70.0, fuel_per_lap_l=5.0)
    state.laps_total = 22
    call = next_call(state)
    assert call is not None and call.kind == WEAR
