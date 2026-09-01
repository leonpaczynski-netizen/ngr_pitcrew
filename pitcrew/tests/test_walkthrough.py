"""Talking one lap through — the claims it may and may not make.

Per-lap, per-corner INPUT coaching is refuted by the driver's own data. What
survives is a description of one lap against his own others, and the tests
here guard the line between the two.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.corner_model import Corner, CornerModel
from pitcrew.analysis.corners import CountedLap
from pitcrew.analysis.walkthrough import (
    MIN_REFERENCE_LAPS,
    NOTABLE_SIGMA,
    walk,
)

MODEL = CornerModel(
    model_id="test", version=1, source="auto-segment", lap_length_m=1000.0,
    corners=(Corner(id="T1", name="Turn 1", start_m=100.0, apex_m=150.0, end_m=200.0),
             Corner(id="T2", name="Turn 2", start_m=500.0, apex_m=550.0, end_m=600.0)))


def _lap(number: int, *, t1_frames: int = 60, t2_frames: int = 60,
         t1_gear: int = 2, t2_gear: int = 3) -> CountedLap:
    """A lap that spends a chosen number of frames in each corner window."""
    frames = []
    metre = 0.0
    for _ in range(60):                       # approach
        frames.append({"lap_distance_m": metre, "speed_kph": 200.0, "gear": 5})
        metre += 1.5
    for i in range(t1_frames):                # T1: 100 - 200 m
        frames.append({"lap_distance_m": 100.0 + i * (100.0 / t1_frames),
                       "speed_kph": 90.0 + i * 0.1, "gear": t1_gear})
    for _ in range(60):
        frames.append({"lap_distance_m": 300.0, "speed_kph": 200.0, "gear": 5})
    for i in range(t2_frames):                # T2: 500 - 600 m
        frames.append({"lap_distance_m": 500.0 + i * (100.0 / t2_frames),
                       "speed_kph": 120.0 + i * 0.1, "gear": t2_gear})
    return CountedLap(lap=number, frames=frames, sample_hz=60.0)


def _others(count: int, **kw):
    return [(_lap(i + 2, **kw), 100_000) for i in range(count)]


def test_the_subject_is_held_out_of_its_own_reference():
    """A lap compared against a set it belongs to is compared partly against
    itself, and the pull is largest exactly when the sample is smallest."""
    subject = (_lap(1, t1_frames=30), 99_000)
    result = walk(MODEL, subject, _others(8, t1_frames=60))
    assert result.reference_laps == 8
    t1 = next(s for s in result.segments if s.corner_id == "T1")
    # The median is the others' 60 frames, untouched by the subject's 30.
    assert t1.median_seconds == pytest.approx(59 / 60.0, abs=0.001)
    assert t1.seconds == pytest.approx(29 / 60.0, abs=0.001)


def test_the_remainder_is_reported_and_the_arithmetic_closes():
    """Corner windows cover a fraction of the lap. A decomposition that
    silently swallows the rest credits the corners with time won elsewhere."""
    subject = (_lap(1, t1_frames=30), 98_000)
    result = walk(MODEL, subject, _others(8))
    assert result.delta_ms == -2000
    assert result.unaccounted_s is not None
    assert (result.accounted_s + result.unaccounted_s ==
            pytest.approx(result.delta_ms / 1000.0, abs=1e-9))
    # The corners cannot explain two seconds of a lap this shape.
    assert abs(result.accounted_s) < abs(result.delta_ms / 1000.0)


def test_a_corner_inside_the_driver_s_own_scatter_is_not_a_finding():
    """That is exactly what cannot be told apart from an ordinary lap."""
    others = [(_lap(i + 2, t1_frames=60 + (i % 3)), 100_000) for i in range(9)]
    result = walk(MODEL, (_lap(1, t1_frames=61), 100_000), others)
    t1 = next(s for s in result.segments if s.corner_id == "T1")
    assert t1.sigma is not None
    assert abs(t1.sigma) < NOTABLE_SIGMA
    assert not t1.notable
    assert t1 not in result.notable


def test_a_corner_well_outside_it_is():
    others = [(_lap(i + 2, t1_frames=60 + (i % 3)), 100_000) for i in range(9)]
    result = walk(MODEL, (_lap(1, t1_frames=40), 100_000), others)
    t1 = next(s for s in result.segments if s.corner_id == "T1")
    assert t1.notable
    assert t1.delta < 0            # fewer frames in the window is quicker
    assert abs(t1.sigma) >= NOTABLE_SIGMA


def test_too_few_reference_laps_is_described_and_not_judged():
    result = walk(MODEL, (_lap(1), 100_000), _others(MIN_REFERENCE_LAPS - 1))
    t1 = next(s for s in result.segments if s.corner_id == "T1")
    assert t1.median_seconds is None
    assert t1.delta is None and t1.sigma is None
    assert not t1.notable
    assert any(str(MIN_REFERENCE_LAPS) in line for line in result.silences)


def test_no_other_lap_at_all_leaves_the_lap_undelta_d():
    result = walk(MODEL, (_lap(1), 100_000), [])
    assert result.reference_ms is None
    assert result.delta_ms is None
    assert result.unaccounted_s is None
    assert not result.notable


def test_the_usual_gear_is_the_one_he_uses_most_not_the_one_on_this_lap():
    others = [(_lap(i + 2, t1_gear=2), 100_000) for i in range(8)]
    result = walk(MODEL, (_lap(1, t1_gear=3), 100_000), others)
    t1 = next(s for s in result.segments if s.corner_id == "T1")
    assert t1.gear == 3
    assert t1.usual_gear == 2
    assert t1.gear_differs


def test_a_gear_he_always_uses_is_not_flagged_as_different():
    result = walk(MODEL, (_lap(1), 100_000), _others(8))
    assert not any(s.gear_differs for s in result.segments)


def test_a_single_reference_lap_has_no_spread_rather_than_a_spread_of_zero():
    """CLAUDE.md rule 3 — 0.0 would make every difference infinitely
    significant."""
    others = [(_lap(2), 100_000)] * 1
    result = walk(MODEL, (_lap(1, t1_frames=30), 100_000), others)
    t1 = next(s for s in result.segments if s.corner_id == "T1")
    assert t1.sd_seconds is None
    assert t1.sigma is None
    assert not t1.notable
