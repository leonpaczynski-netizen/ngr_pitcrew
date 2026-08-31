"""Fuel burn as a function of load, and the guarantee that it changes nothing
until a load is actually known.

The measurement behind these numbers is in `strategy/fuel_model.py`: Spa race,
31 Aug 2026, 17 green laps, +0.00610 L burned per litre aboard, t +4.54.
"""
from __future__ import annotations

import pytest

from pitcrew.strategy.fuel_model import (
    DEFAULT_BUFFER_L,
    LOAD_SLOPE_L_PER_L,
    burn_at_load_l,
    fill_for_l,
    fit_load_slope,
    stint_burn_l,
)

# The race this was fitted on: base burn and the mean load it was taken at.
RACE_BASE_L = 8.060
RACE_REF_LOAD_L = 44.3


# --------------------------------------------------------------- the no-op

def test_unknown_reference_load_is_the_old_arithmetic_exactly():
    """**The guarantee that lets this ship.** No load, no change."""
    assert stint_burn_l(8.264, 10, 100.0, reference_load_l=None) == \
        pytest.approx(82.64)
    assert stint_burn_l(8.264, 10, None, reference_load_l=44.0) == \
        pytest.approx(82.64)
    assert fill_for_l(8.264, 10, reference_load_l=None, buffer_l=3.2) == \
        pytest.approx(10 * 8.264 + 3.2)
    assert burn_at_load_l(8.264, 100.0, reference_load_l=None) == 8.264


def test_zero_slope_is_the_old_arithmetic_exactly():
    assert stint_burn_l(8.0, 10, 90.0, reference_load_l=44.0, slope=0.0) == \
        pytest.approx(80.0)
    assert fill_for_l(8.0, 10, reference_load_l=44.0, slope=0.0,
                      buffer_l=1.0) == pytest.approx(81.0)


def test_a_zero_reference_load_is_a_real_value_not_a_missing_one():
    """Zero litres aboard is a fuel load. It must not read as 'unknown'."""
    corrected = burn_at_load_l(8.0, 50.0, reference_load_l=0.0)
    assert corrected > 8.0
    assert corrected == pytest.approx(8.0 + 50.0 * LOAD_SLOPE_L_PER_L)


# ------------------------------------------------------------ the physics

def test_burn_rises_with_what_is_in_the_tank():
    heavy = burn_at_load_l(RACE_BASE_L, 100.0, reference_load_l=RACE_REF_LOAD_L)
    light = burn_at_load_l(RACE_BASE_L, 0.0, reference_load_l=RACE_REF_LOAD_L)
    assert heavy > light
    # 0.61 L/lap between a full tank and an empty one, as measured.
    assert heavy - light == pytest.approx(0.610, abs=0.005)


def test_a_stint_that_starts_lighter_burns_less():
    heavy = stint_burn_l(RACE_BASE_L, 10, 95.0, reference_load_l=RACE_REF_LOAD_L)
    light = stint_burn_l(RACE_BASE_L, 10, 65.0, reference_load_l=RACE_REF_LOAD_L)
    assert heavy > light
    # Driver's observation, 1 Sep 2026, and the size of it.
    assert heavy - light == pytest.approx(1.78, abs=0.15)


def test_fill_is_solved_not_multiplied():
    """The fuel is its own weight, so the fill has to be solved for."""
    flat = 10 * RACE_BASE_L + DEFAULT_BUFFER_L
    solved = fill_for_l(RACE_BASE_L, 10, reference_load_l=RACE_REF_LOAD_L)
    assert solved != pytest.approx(flat)


@pytest.mark.parametrize("laps", [1, 5, 9, 10, 14, 20])
def test_fill_for_l_inverts_stint_burn_l(laps):
    """Whatever the fill says, running it must leave exactly the buffer."""
    fill = fill_for_l(RACE_BASE_L, laps, reference_load_l=RACE_REF_LOAD_L,
                      buffer_l=1.0)
    left = fill - stint_burn_l(RACE_BASE_L, laps, fill,
                               reference_load_l=RACE_REF_LOAD_L)
    assert left == pytest.approx(1.0, abs=0.01)


def test_the_buffer_is_honoured_not_approximated():
    for buffer_l in (0.0, 1.0, 3.2, 8.0):
        fill = fill_for_l(RACE_BASE_L, 10, reference_load_l=RACE_REF_LOAD_L,
                          buffer_l=buffer_l)
        left = fill - stint_burn_l(RACE_BASE_L, 10, fill,
                                   reference_load_l=RACE_REF_LOAD_L)
        assert left == pytest.approx(buffer_l, abs=0.01)


def test_it_reproduces_the_stint_it_was_fitted_from():
    """Spa race stint 2: 10 laps from 82.842 L, actually burned 79.93 L."""
    burned = stint_burn_l(RACE_BASE_L, 10, 82.842,
                          reference_load_l=RACE_REF_LOAD_L)
    assert burned == pytest.approx(79.93, abs=1.0)


def test_the_fill_is_not_clamped_to_the_tank():
    """An impossible requirement is reported, never quietly shrunk.

    Clamping once made an impossible plan look cheap - see `model.build_plan`.
    """
    fill = fill_for_l(RACE_BASE_L, 30, reference_load_l=RACE_REF_LOAD_L,
                      capacity_l=100.0)
    assert fill > 100.0


# ---------------------------------------------------------------- the fit

def test_fit_refuses_too_few_samples():
    """Two predictors and an intercept cannot be fitted from three points."""
    assert fit_load_slope([(8.0, 50.0, 7250)] * 3) is None
    assert fit_load_slope([]) is None


def test_fit_recovers_a_slope_it_was_given():
    base, per_litre, per_krpm = 5.0, 0.006, 1.94
    samples = []
    for load in (90.0, 70.0, 50.0, 30.0, 10.0):
        for rpm in (7000, 7600):
            used = base + per_litre * load + per_krpm * rpm / 1000.0
            samples.append((used, load, rpm))
    slope, krpm, intercept, n = fit_load_slope(samples)
    assert n == 10
    assert slope == pytest.approx(per_litre, abs=1e-6)
    assert krpm == pytest.approx(per_krpm, abs=1e-5)
    assert intercept == pytest.approx(base, abs=1e-5)


def test_the_load_effect_hides_without_the_rpm_term():
    """**Why the rpm term is not optional.**

    One lap at high rpm placed at the lowest fuel load cancels the load slope
    exactly - which is what happened in the race this came from, where load
    alone fitted t +0.19 and load-with-rpm fitted t +4.54 on the same laps.
    """
    base, per_litre, per_krpm = 5.0, 0.006, 1.94
    samples = []
    for load in (90.0, 70.0, 50.0, 30.0):
        samples.append((base + per_litre * load + per_krpm * 7.25, load, 7250))
    # The confounded lap: lightest tank, highest rpm.
    samples.append((base + per_litre * 10.0 + per_krpm * 7.9, 10.0, 7900))

    with_rpm = fit_load_slope(samples)
    assert with_rpm[0] == pytest.approx(per_litre, abs=1e-6)

    # Same data, load only: a simple regression now reads the wrong sign.
    xs = [load for _, load, _ in samples]
    ys = [used for used, _, _ in samples]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    naive = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
             / sum((x - mx) ** 2 for x in xs))
    assert naive < 0 < per_litre


# ------------------------------------------- the load a burn was measured at

def test_a_qualifying_run_is_not_fuelled_at_the_practice_median():
    """**Practice runs a race-ish tank; a flyer carries nothing.**

    Burn falls with what is aboard, so multiplying the practice median by the
    lap count over-fuels the one lap of the weekend whose entire purpose is to
    carry no fuel. Driver, 1 Sep 2026: *"quali will always start with a
    reduced fuel load, a race will always start with a full fuel load."*
    """
    from pitcrew.race.quali_fuel import qualifying_fuel

    flat = qualifying_fuel(fuel_per_lap_l=8.074, fuel_capacity_l=100.0)
    corrected = qualifying_fuel(fuel_per_lap_l=8.074, fuel_capacity_l=100.0,
                                fuel_reference_load_l=66.5)
    assert corrected.litres < flat.litres


def test_quali_fuel_is_unchanged_when_the_load_is_unknown():
    """The no-op guarantee reaches the qualifying path too."""
    from pitcrew.race.quali_fuel import MARGIN_L, qualifying_fuel

    got = qualifying_fuel(fuel_per_lap_l=6.0, fuel_capacity_l=100.0)
    assert got.litres == pytest.approx(round(3 * 6.0 + MARGIN_L, 1))


def test_a_burn_measured_light_asks_for_more_fuel_in_a_race():
    """The dangerous direction, and the one that must not fail silently.

    A practice programme run on half tanks produces a light-car median. A race
    starts full, so the same laps cost MORE than that median says - and a plan
    that misses it under-fuels the race.
    """
    light_reference = 20.0
    race_stint_mean_load = 59.0
    burn_in_race = burn_at_load_l(8.0, race_stint_mean_load,
                                  reference_load_l=light_reference)
    assert burn_in_race > 8.0
    fill = fill_for_l(8.0, 10, reference_load_l=light_reference, buffer_l=1.0)
    assert fill > 10 * 8.0 + 1.0
