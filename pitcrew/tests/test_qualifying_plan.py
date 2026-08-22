"""The qualifying plan: how much fuel, and how many runs.

The driver's question, in his words: *"is it one and done, or a timed
qualifying with fuel burn to lighten the car?"*

The fuel half is arithmetic on a measured burn and the plan is entitled to be
firm about it. Everything else is a refusal or an assumption, said out loud -
so most of these tests are about what it declines to claim.
"""
from __future__ import annotations

import pytest

from pitcrew.race.qualifying_plan import (
    DEFAULT_CAPACITY_L,
    KG_PER_L,
    MARGIN_LAPS,
    QualifyingInputs,
    build,
)


def an_input(**overrides) -> QualifyingInputs:
    base = dict(lap_time_ms=110_000, fuel_per_lap_l=5.5,
                fuel_capacity_l=100.0, laps_to_window=2, session_minutes=15)
    base.update(overrides)
    return QualifyingInputs(**base)


# ------------------------------------------------------------- the arithmetic

def test_it_fuels_the_laps_it_will_actually_drive():
    """Two out laps, a flyer and an in lap is four laps, plus the margin."""
    plan = build(an_input())
    assert plan.usable
    assert plan.total_laps == 4
    assert plan.fuel_l == pytest.approx((4 + MARGIN_LAPS) * 5.5)


def test_the_weight_saved_is_a_measurement_and_the_seconds_are_not():
    """CLAUDE.md §5.3: the fuel-weight coefficient is derived, must be flagged,
    and must be overwritable. The litres and the kilograms are measured."""
    plan = build(an_input())
    assert plan.weight_saved_kg == pytest.approx(
        (DEFAULT_CAPACITY_L - plan.fuel_l) * KG_PER_L)
    assert plan.estimated_gain_s is not None
    assert any("DERIVED" in note for note in plan.assumptions)
    assert any("ESTIMATED" in line for line in plan.as_text())


def test_the_coefficient_can_be_overwritten():
    doubled = build(an_input(fuel_weight_s_per_l_per_lap=0.006))
    assert doubled.estimated_gain_s == pytest.approx(
        2 * build(an_input()).estimated_gain_s)


def test_a_zero_coefficient_claims_no_seconds_at_all():
    plan = build(an_input(fuel_weight_s_per_l_per_lap=0.0))
    assert plan.estimated_gain_s is None
    assert plan.weight_saved_kg is not None      # the kilograms still stand


# --------------------------------------------------------------- refusals

def test_no_measured_burn_is_a_refusal_and_not_a_guess():
    plan = build(an_input(fuel_per_lap_l=None))
    assert not plan.usable
    assert "invented" in plan.as_text()[0]


def test_a_zero_litre_tank_is_a_real_reading():
    """**The trap CLAUDE.md §3.4 names, and this shipped with it in draft.**
    Capacity is 100 L for almost every car, 5 L for karts and **0 for electric
    ones**. Written `inputs.fuel_capacity_l or DEFAULT_CAPACITY_L`, a 0 was
    falsy and became a 100 L tank - and the plan congratulated the driver on
    saving 57 kg of fuel he was never carrying."""
    plan = build(an_input(fuel_capacity_l=0.0))
    assert not plan.usable
    assert "carries no fuel" in plan.as_text()[0]


def test_capacity_unknown_falls_back_but_zero_does_not():
    """None is "nobody said" and takes the default. Zero is a measurement."""
    assert build(an_input(fuel_capacity_l=None)).usable
    assert not build(an_input(fuel_capacity_l=0.0)).usable


# ------------------------------------------------------------- assumptions

def test_a_measured_warm_up_is_used_and_named():
    plan = build(an_input(laps_to_window=3))
    assert plan.total_laps == 5                  # 3 out + flyer + in
    assert any("measured" in note for note in plan.assumptions)


def test_no_measured_warm_up_says_so_rather_than_inventing_one():
    """There is no number for how long a set takes to come up. One out lap is
    priced because the car has to leave the pits, and the plan says that is
    the whole of the reasoning."""
    plan = build(an_input(laps_to_window=None))
    # Per RUN, not in total: a shorter warm-up shortens every run, so more of
    # them fit the same fifteen minutes and the total goes UP.
    assert all(run.out_laps == 1 for run in plan.runs)
    assert plan.runs[0].laps == 3                # 1 out + flyer + in
    assert any("no measured warm-up" in note for note in plan.assumptions)


def test_an_unknown_session_length_plans_one_run_and_says_so():
    """A lobby that does not say how long qualifying is is a real state."""
    plan = build(an_input(session_minutes=None))
    assert len(plan.runs) == 1
    assert any("session length unknown" in note for note in plan.assumptions)


def test_a_long_session_fits_more_runs_and_leaves_the_choice_open():
    """It reports what fits. Whether to take the second run is the driver's:
    the circuit rubbers in, which nothing in the feed measures."""
    plan = build(an_input(session_minutes=45, laps_to_window=1))
    assert len(plan.runs) > 1
    assert any("yours" in note for note in plan.assumptions)


def test_a_short_session_is_one_and_done():
    plan = build(an_input(session_minutes=8))
    assert len(plan.runs) == 1
    assert any("one and done" in note for note in plan.assumptions)


# ------------------------------------------------------------- the tank cap

def test_it_never_asks_for_more_than_the_tank_holds():
    """The strategy audit found this app proposing "Fuel to 510 litres" into a
    100 L tank."""
    plan = build(an_input(fuel_capacity_l=12.0, session_minutes=45,
                          laps_to_window=1))
    assert plan.fuel_l <= 12.0


def test_a_plan_that_does_not_fit_the_tank_says_it_is_short():
    """**Capping quietly is worse than not capping.** It turns "this needs 8.4
    litres" into "fuel to 5 litres", which reads as a plan that fits and is a
    plan that runs out on the flyer."""
    plan = build(QualifyingInputs(lap_time_ms=60_000, fuel_per_lap_l=1.2,
                                  fuel_capacity_l=5.0, session_minutes=10))
    assert plan.fuel_l == pytest.approx(5.0)
    assert any("SHORT" in note for note in plan.assumptions)


def test_a_plan_that_fits_says_nothing_about_being_short():
    assert not any("SHORT" in note for note in build(an_input()).assumptions)
