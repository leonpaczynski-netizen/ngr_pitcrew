"""Plan row 5.7: braking share beside full-throttle share, and rule 3 on pedals.

`read_frames` used to take `brake_pct or 0.0`, so a frame with no brake reading
counted as a released pedal - coasting, if the throttle was off too. A missing
reading is left out of that share's count now.
"""
from __future__ import annotations

from pitcrew.analysis.driving import (
    BRAKING_PCT,
    FULL_THROTTLE_PCT,
    MIN_FRAMES,
    read_frames,
)


def _frames(n, **channels):
    return [{"speed_kph": 150.0, "throttle_pct": 0.0, "brake_pct": 0.0,
             "gear": 4, "rpm": 7000, **channels} for _ in range(n)]


def test_braking_share_counts_real_pressure():
    frames = (_frames(300, brake_pct=BRAKING_PCT + 30.0)
              + _frames(300, throttle_pct=FULL_THROTTLE_PCT + 5.0)
              + _frames(400, brake_pct=BRAKING_PCT - 15.0))
    read = read_frames(frames)
    assert read.braking_pct == 30.0
    assert read.full_throttle_pct == 30.0


def test_a_missing_brake_frame_is_not_a_released_pedal():
    coasting = _frames(MIN_FRAMES)                       # off both, above 60
    unknown = _frames(MIN_FRAMES, brake_pct=None)        # brake not read
    read = read_frames(coasting + unknown)
    assert read.coast_pct == 100.0                       # only the seen frames
    assert read.braking_pct == 0.0


def test_too_few_readings_of_a_pedal_is_none_not_zero():
    frames = _frames(MIN_FRAMES, brake_pct=None)
    read = read_frames(frames)
    assert read.braking_pct is None
    assert read.coast_pct is None
    assert read.full_throttle_pct == 0.0
