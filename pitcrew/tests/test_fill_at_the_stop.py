"""The fill at the LAST stop is sized by the flag, never by the plan's stint.

Deep Forest, 6 Sep 2026, race_run 16. Plan: 11 + 10 on a 21-lap estimate of a
30-minute race. The stop came on lap 13; the clock had 7 laps left. With the
hose in George said "Fuel to 76 litres. 10 laps at this race's burn." - the
plan's second stint - and `fuel_target_l` had taken `max(next_stint_laps,
laps_after_this_stop)`, which can only RAISE the plan's figure. 70 L went in,
55-63 were needed, 19.73 L crossed the line: 9.9 s standing at 2 L/s, against
an 8 s gap to P2.

A `min()` would have been wrong the other way - an EARLY last stop has more
laps left than the stint says, and a stint-sized fill sends him out to run
dry. The rule is not a max or a min: with no further stop planned, the laps
still to run once the car leaves the box are the whole answer.
"""
from __future__ import annotations

import math

import pytest

from pitcrew.race.calls import (RaceState, _fuel_instruction, fuel_target_basis,
                                fuel_target_l)
from pitcrew.race.refuel import RefuelAdviser, RefuelWatch, TARGET


def deep_forest(**over):
    """Lap 13, in the box. The plan said 11 + 10; the clock says 7 to go."""
    fields = dict(lap=12, laps_total=20, fuel_per_lap_l=7.35, fuel_sd_l=0.25,
                  fuel_l=5.08, fuel_capacity_l=100.0,
                  next_stint_laps=10, further_stop_planned=False,
                  stint_ends_on_lap=11, laps_after_stops=8,
                  race_minutes=30.0, laps_estimate_firm=True, in_pit=True)
    fields.update(over)
    return RaceState(**fields)


def _laps(state: RaceState) -> float:
    return fuel_target_l(state) / state.fuel_per_lap_l


# ------------------------------------------------------------ the last stop

def test_a_late_last_stop_is_sized_by_the_laps_left_not_the_plan():
    """The P2 defect. 8 on the clock minus the lap in progress = 7 to run."""
    state = deep_forest()

    litres = fuel_target_l(state)

    assert litres is not None
    # Seven laps plus a margin - never the plan's ten.
    assert 7 * 7.35 <= litres < 8.5 * 7.35
    assert fuel_target_basis(state) == "7 laps to the flag"


def test_an_early_last_stop_is_sized_by_the_laps_left_too():
    """Lap 9 of a 20-lap race with an 11 + 9 plan: 11 laps left, not 9."""
    state = deep_forest(lap=8, next_stint_laps=9, stint_ends_on_lap=11,
                        laps_after_stops=12, race_minutes=None)

    assert _laps(state) >= 11
    assert fuel_target_basis(state) == "11 laps to the flag"


def test_a_plan_longer_than_the_race_cannot_size_the_fill():
    """21-lap plan, 20-lap race: the stint says 10, the clock says 7."""
    state = deep_forest(next_stint_laps=10, laps_after_stops=8)

    assert _laps(state) < 9
    assert "to the flag" in fuel_target_basis(state)


def test_the_stint_still_sizes_an_intermediate_stop():
    """Stop 1 of a two-stop: the next stint, not the flag - a tankful nobody
    needs is the other failure, and it is why the plan's stint exists."""
    state = deep_forest(lap=6, next_stint_laps=7, further_stop_planned=True,
                        laps_after_stops=15)

    assert 7 * 7.35 <= fuel_target_l(state) < 8.5 * 7.35
    assert fuel_target_basis(state) == "the next 7-lap stint"


def test_a_hand_built_state_takes_the_plan_at_its_word():
    """`further_stop_planned` None is 'nobody said' - the old behaviour."""
    state = deep_forest(further_stop_planned=None, laps_after_stops=8)

    assert _laps(state) >= 10
    assert fuel_target_basis(state) == "the next 10-lap stint"


def test_no_stint_and_no_plan_falls_back_to_the_laps_remaining():
    state = deep_forest(next_stint_laps=None, stint_ends_on_lap=None,
                        laps_after_stops=None)

    laps_left = state.laps_remaining() - 1  # the lap the stop is on
    assert math.isclose(_laps(state), laps_left, abs_tol=1.5)
    assert fuel_target_basis(state) == f"{laps_left} laps to the flag"


def test_the_box_call_names_the_bound_behind_the_litres():
    late = deep_forest()
    early = deep_forest(lap=8, next_stint_laps=9, laps_after_stops=12,
                        race_minutes=None)
    middle = deep_forest(lap=6, next_stint_laps=7, further_stop_planned=True,
                         laps_after_stops=15)

    assert _fuel_instruction(late).endswith("- 7 laps to the flag.")
    assert _fuel_instruction(early).endswith("- 11 laps to the flag.")
    assert _fuel_instruction(middle).endswith("- the next 7-lap stint.")


# --------------------------------------------------------- with the hose in

def _fill(watch: RefuelWatch, *, target, basis):
    """Three rising frames past the arming threshold, then the target call."""
    said = []
    for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
        call = watch.note(fuel, speed_kph=0.0, target_l=target,
                          fuel_per_lap_l=7.35, basis=basis)
        if call is not None:
            said.append(call)
    return said


def test_the_in_box_sentence_carries_the_same_bound():
    said = _fill(RefuelWatch(), target=63.0, basis="7 laps to the flag")

    assert [c.kind for c in said] == [TARGET]
    assert said[0].call == "Fuel to 63 litres."
    assert said[0].reason.startswith("7 laps to the flag, at this race's burn.")


def test_without_a_basis_the_old_lap_count_is_still_said():
    said = _fill(RefuelWatch(), target=63.0, basis=None)

    assert said[0].reason.startswith("9 laps at this race's burn.")


def test_the_adviser_accepts_a_three_value_context_and_a_four_value_one():
    spoken = []
    for context in (lambda: (63.0, 7.35, None),
                    lambda: (63.0, 7.35, None, "7 laps to the flag")):
        adviser = RefuelAdviser(context=context, speak=spoken.append)
        for fuel in (5.0, 5.0, 5.4, 5.8, 6.3, 6.9):
            adviser.note_frame(fuel, 0.0)
    assert len(spoken) == 2
    assert "9 laps" in spoken[0].reason
    assert "7 laps to the flag" in spoken[1].reason


# ---------------------------------------------------- the replay of the night

@pytest.mark.parametrize("laps_after_stops, expect_low, expect_high", [
    (8, 7 * 7.35, 8.5 * 7.35),     # what the clock said on lap 13
    (9, 8 * 7.35, 9.5 * 7.35),     # a lap more on the clock
    (11, 10 * 7.35, 11.5 * 7.35),  # the plan's stint, when it is true
])
def test_the_figure_follows_the_clock_and_never_the_stale_stint(
        laps_after_stops, expect_low, expect_high):
    litres = fuel_target_l(deep_forest(laps_after_stops=laps_after_stops))
    assert expect_low <= litres < expect_high
