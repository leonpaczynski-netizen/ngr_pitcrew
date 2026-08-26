"""Two ways the gauge reader lies, both found by adversarial review.

One writes fabricated zeros into the archive under a source tag that says
they were measured; the other throws a whole race away for reading a tyre
change correctly. They pull in opposite directions and both are guarded here,
because a gate tuned only against the failure you have seen is a gate tuned
against one session.
"""
from __future__ import annotations

from pitcrew.telemetry.hud import (
    FRESH_SET_MAX,
    bar_height_bounds,
    flat_series_fault,
    wear_faults,
)

CORNERS = ("fl", "fr", "rl", "rr")


def all_corners(value: float | None) -> dict:
    return {corner: value for corner in CORNERS}


def by_lap(a, b):
    return b - a


# ------------------------------------------------- the bar is a fraction

def test_the_real_bar_is_never_excluded_at_any_canvas_size():
    """GT7 draws the flat bar at `canvas_height / 30`. A fixed 40 px cap
    excluded it above ~1200 rows, and the locator then picked something else
    - which at 1440p read 0.000 on every corner with nothing objecting."""
    for height in (720, 916, 1080, 1440, 2160):
        low, high = bar_height_bounds(height)
        real = height / 30
        assert low <= real <= high, (height, real, low, high)


def test_the_calibrated_canvas_keeps_exactly_the_bounds_it_had():
    """The VR gauge is 8-20 px against 30 flat, so the bounds may widen with
    the canvas but must not move on the geometry already in service."""
    assert bar_height_bounds(916) == (8, 40)


def test_a_bigger_canvas_only_ever_widens_the_search():
    previous = bar_height_bounds(720)
    for height in (916, 1080, 1440, 2160):
        current = bar_height_bounds(height)
        assert current[1] >= previous[1]
        assert current[0] <= 8
        previous = current


# ------------------------------------------- tyres wear, so a flat run lies

def test_a_run_of_zeros_is_refused():
    """57 of 60 frames at 2560x1440 read exactly this, with zero step faults."""
    series = [(lap, all_corners(0.0)) for lap in range(1, 12)]
    assert wear_faults(series, slack=0.028, span=by_lap) == []
    fault = flat_series_fault(series, slack=0.028)
    assert fault is not None
    assert "0.00" in fault and "tyres wear" in fault


def test_a_run_that_never_moves_is_refused_even_above_zero():
    series = [(lap, all_corners(0.42)) for lap in range(1, 8)]
    assert flat_series_fault(series, slack=0.028) is not None


def test_a_run_that_wears_is_not_refused():
    series = [(lap, all_corners(0.05 * lap)) for lap in range(1, 8)]
    assert flat_series_fault(series, slack=0.028) is None


def test_a_single_reading_is_not_a_flat_run():
    """One crossing answered in a session is honest, not a false quad."""
    assert flat_series_fault([(1, all_corners(0.0))], slack=0.028) is None


def test_movement_inside_one_pixel_is_not_movement():
    """Two readings a pixel apart are the same reading twice."""
    series = [(1, all_corners(0.30)), (2, all_corners(0.32))]
    assert flat_series_fault(series, slack=0.033) is not None
    assert flat_series_fault(series, slack=0.010) is None


# -------------------------------------- a fresh set has run some of its life

def test_a_fresh_set_that_has_run_two_laps_is_still_a_fresh_set():
    """The live ceiling asks a new set to read under 15% on the NEXT sample,
    and the next sample is seconds away there and a LAP away here. On RS at
    the rates measured in this archive - 14.1%/lap, 16.7%/lap - a set that has
    done an out-lap and a flying lap reads 25-30%, every corner has correctly
    fallen, and the unscaled test refused the step. The gate is all-or-nothing,
    so that refusal discards the whole race."""
    for rate in (0.056, 0.120, 0.141, 0.167):
        series = [(10, all_corners(0.75)), (12, all_corners(rate * 1.8))]
        assert wear_faults(series, slack=0.032, span=by_lap) == [], rate


def test_a_set_too_worn_to_be_fresh_is_still_refused():
    """The budget is what the set could have consumed since it went on, not
    an open door: every corner falling to 60% one lap later is not a change."""
    series = [(10, all_corners(0.90)), (11, all_corners(0.60))]
    assert wear_faults(series, slack=0.032, span=by_lap) != []


def test_the_fresh_set_ceiling_is_named_in_the_refusal():
    """Rule 10: the number setting the bar has to appear, or a ratchet is
    invisible for a whole race."""
    series = [(10, all_corners(0.90)), (11, all_corners(0.60))]
    why = wear_faults(series, slack=0.032, span=by_lap)[0].why
    assert "ceiling" in why


def test_a_lone_corner_going_backwards_is_still_a_fault():
    """Session 77, lap 11 -> 20: FL falls, FR rises, RR holds. Not a change of
    set at all - one of the two readings is not of the gauge."""
    series = [(11, {"fl": 0.429, "fr": 0.211, "rl": 0.368, "rr": 0.200}),
              (20, {"fl": 0.368, "fr": 0.222, "rl": 0.350, "rr": 0.200})]
    assert wear_faults(series, slack=0.050, span=by_lap) != []


def test_the_live_default_is_unchanged():
    """`coherent` still serves the race path with the constant it always had;
    only the batch form spans it."""
    series = [(1, all_corners(0.75)), (2, all_corners(0.14))]
    assert wear_faults(series, slack=0.032) == []          # no span: 1 lap
    assert FRESH_SET_MAX == 0.15
