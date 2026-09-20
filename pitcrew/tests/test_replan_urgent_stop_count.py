"""The "no plan fits the fuel" branch answers with the plan it just rejected.

Bathurst Rd 8, session 204, 20 Sep 2026. The re-planner produced exactly two
spoken strategy verdicts in 28 laps, and both came out of one branch of
`assess`:

    lap 3   {'stops': 3, 'stint_laps': [], 'next_stop_lap': 4,
             'laps_to_next_stop': None, 'why_spoken': 'first assessment'}
    lap 22  {'stops': 2, 'stint_laps': [], 'next_stop_lap': 23,
             'laps_to_next_stop': None, 'why_spoken': 'the stop count changed'}

`stops=max(1, current_stops)`, and `current_stops` is
`RaceCoordinator.stops_planned()` - **the stops still in the frozen plan**,
not the driver's completed count. So the branch that had just established
that no plan fits the fuel aboard answered "how many stops, then?" with that
same plan's residue. Lap 3 read the approved plan back to him dressed as a
recommendation; lap 22 announced "2 stops from here" with six laps left.

CLAUDE.md rule 12: where a decision is a filter over several limits, the
reported reason must come from the same expression that produced it.

And the branch returned `laps_to_next_stop=None` with a sticky `URGENT`,
which held all three exits from `materially_different` shut for eighteen
laps - the mechanical reason the driver heard nothing about the plan between
lap 3 and lap 22.
"""
from __future__ import annotations

import logging

import pytest

from pitcrew.race.replan import (NONE, URGENT, Replan, _stops_on_the_fuel,
                                 assess, materially_different)
from pitcrew.strategy.model import CompoundProfile, RaceInputs


def bathurst_inputs(*, laps: int, burn: float) -> RaceInputs:
    """The rest of the race as the model saw it at Bathurst Rd 8."""
    return RaceInputs(
        race_laps=laps, race_minutes=60.0, lap_time_ms=125_897,
        fuel_per_lap_l=burn, fuel_capacity_l=100.0,
        refuel_rate_lps=2.002, pit_loss_s=20.0, wear_per_lap=0.0508,
        available_compounds=("RS",), evidence_compound="RS",
        compound_profiles={"RS": CompoundProfile(
            "RS", 0.0, 0.0508, "measured", laps_measured=8,
            stints_measured=1, longest_stint_laps=8)})


def at_lap(lap: int, *, fuel_l: float, burn: float | None,
           current_stops: int) -> Replan:
    return assess(
        laps_done=lap, laps_total=28, fuel_l=fuel_l,
        planned_fuel_per_lap=10.625, observed_fuel_per_lap_l=burn,
        lap_time_ms=126_000, planned_lap_time_ms=125_897,
        current_stops=current_stops, fuel_capacity_l=100.0,
        inputs=bathurst_inputs(laps=28 - lap, burn=burn or 10.625))


# ------------------------------------------------------- the arithmetic alone

def test_the_stop_count_comes_from_the_fuel_and_not_from_the_plan():
    """35 L aboard at 8.4 is 4.2 laps of 20 left; a full tank is 11.9, so
    16 laps have to come out of 2 fills. Two stops, computed - whatever the
    frozen plan happens to say."""
    stops, to_next, why = _stops_on_the_fuel(
        laps_left=20, fuel_l=35.0, burn=8.4, capacity_l=100.0)
    assert stops == 2
    assert to_next == 4
    assert "a full tank is 11.9" in why


def test_a_tank_that_reaches_the_flag_is_no_stops_and_says_which_it_is():
    stops, to_next, why = _stops_on_the_fuel(
        laps_left=5, fuel_l=60.0, burn=8.4, capacity_l=100.0)
    assert stops == 0
    assert "reaches the flag" in why
    assert to_next == 7


@pytest.mark.parametrize("fuel_l,burn,capacity", [
    (35.0, None, 100.0), (35.0, 0.0, 100.0), (None, 8.4, 100.0),
    (35.0, 8.4, None), (35.0, 8.4, 0.0)])
def test_a_missing_term_gives_no_count_rather_than_a_guess(fuel_l, burn,
                                                           capacity):
    """Rule 3: missing is None. `Replan.call` already says "The plan needs a
    look." for a verdict with no stop count, which is honest and vaguer -
    never a confidently wrong number."""
    stops, _to_next, why = _stops_on_the_fuel(
        laps_left=20, fuel_l=fuel_l, burn=burn, capacity_l=capacity)
    assert stops is None
    assert why, "and it says which term it was missing"


# ------------------------------------------------------- through `assess`

def test_nothing_runnable_reports_the_fuel_and_opens_the_stop_lap_door():
    """The branch itself: a tank that cannot reach any plan's first stop.

    Two laps of fuel, 20 laps to go and a plan of record claiming three stops
    remain. Before this fix the answer was "3 stops from here" with
    `laps_to_next_stop=None`; now both figures come off the tank.
    """
    verdict = at_lap(8, fuel_l=17.0, burn=8.4, current_stops=3)
    assert verdict.verdict == URGENT
    assert verdict.stops != 3, "the frozen plan's residue, echoed"
    assert verdict.laps_to_next_stop is not None, (
        "a None here holds the stop-lap door in `materially_different` shut")
    assert "a full tank is" in verdict.reason


def test_the_stop_lap_door_can_now_open():
    """`materially_different` cannot compare a stop that has no laps to it.

    With both sides carrying a figure the third exit from silence works: an
    18-lap stretch of URGENT-to-URGENT with a moving stop is news.
    """
    told = Replan(URGENT, "no plan reaches the next stop on the fuel aboard",
                  stops=2, laps_to_next_stop=9, next_stop_lap=12)
    now = Replan(URGENT, "no plan reaches the next stop on the fuel aboard",
                 stops=2, laps_to_next_stop=2, next_stop_lap=15)
    speak, why = materially_different(now, told)
    assert speak and "moved" in why
    # And the old shape, which could not:
    mute, _ = materially_different(
        Replan(URGENT, "x", stops=2, laps_to_next_stop=None), told)
    assert mute is False


def test_the_fuel_is_not_blamed_when_the_fuel_is_not_what_bound_it(
        monkeypatch):
    """Rule 12 the other way round, and it is the half that is easy to miss.

    Every shape can be refused for reasons that are not fuel - the split
    policy front-loading a distance race, `_worth_stopping` on a short
    remainder. When the tank plainly reaches the flag, the branch may not
    reach for the fuel sentence just because that is the sentence it has.
    The stop count is then honestly unknown, which `Replan.call` already says
    as "The plan needs a look."
    """
    from pitcrew.race import replan as R

    class _Stint:
        laps = 50
        compound = "RS"

    class _Plan:
        stops = 1
        stints = (_Stint(), _Stint())
        total_time_s = 1000.0

    monkeypatch.setattr(R, "recommend", lambda *a, **k: [_Plan()])
    verdict = at_lap(20, fuel_l=90.0, burn=8.4, current_stops=1)
    assert verdict.verdict == URGENT
    assert verdict.stops is None, "no count, rather than a wrong one"
    assert verdict.call() == "The plan needs a look."
    assert "no plan reaches the next stop on the fuel aboard" not in \
        verdict.reason
    assert "reaches the flag" in verdict.reason


# ------------------------------------------------------------------ the log

def test_every_re_plan_leaves_a_line(caplog):
    """`grep -c replan logs/pitcrew.log` returned 0 for the whole race."""
    caplog.set_level(logging.INFO, logger="pitcrew.race")
    at_lap(8, fuel_l=17.0, burn=8.4, current_stops=3)
    at_lap(20, fuel_l=90.0, burn=8.4, current_stops=1)
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("re-plan on lap ")]
    assert len(lines) == 2
    assert "re-plan on lap 8: urgent" in lines[0]
    assert "next stop in" in lines[0]


def test_a_race_that_is_over_is_logged_too():
    """Not only the interesting branches: a silent answer is a decision and
    the log has to be able to prove the engineer was thinking."""
    verdict = assess(laps_done=28, laps_total=28, fuel_l=1.5,
                     planned_fuel_per_lap=10.625,
                     observed_fuel_per_lap_l=8.4, lap_time_ms=126_000,
                     planned_lap_time_ms=125_897, current_stops=0)
    assert verdict.verdict == NONE
