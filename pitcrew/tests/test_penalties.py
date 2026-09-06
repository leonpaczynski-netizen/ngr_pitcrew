"""Track-limit penalties served, read off the frames (plan 1.11, G27).

Verified against the archive with `tools/find_penalties.py`: the six laps the
driver named from the 4 Sep 2026 Daytona A/B runs (sessions 121 laps 3 and
6, 122 lap 5, 123 lap 4, 124 laps 2 and 6) are found at 5,194-5,218 m, and
the Bus Stop brake at 3,650-3,720 m on every lap of every session is not -
nor is anything in the twenty-lap race that followed. That run is not a
test because it needs the live file; this file holds the shape of it.
"""
from __future__ import annotations

from pitcrew.analysis.penalties import (APPROACH_M, MAX_LAT_G, read_rows)

# Daytona's model: T5 (the Bus Stop) starts at 3,775.8 m.
CORNERS = [{"id": "T1", "start_m": 394.8, "end_m": 496.9},
           {"id": "T5", "start_m": 3775.8, "end_m": 3950.8}]


def _lap(*, brakes, length_m=5692.5, hz=60, lat_g=0.1):
    """Frames at 60 Hz round the lap at 250 km/h, with hard brakes at the
    given (start_m, seconds, speed_to) - the car slows through the brake and
    recovers over the next few seconds."""
    frames = []
    v = 250.0
    m = 0.0
    t = 0
    pending = sorted(brakes)
    braking_until = None
    target = None
    while m < length_m:
        brake = 0.0
        if pending and m >= pending[0][0] and braking_until is None:
            _, secs, speed_to = pending.pop(0)
            braking_until = t + int(secs * hz)
            target = speed_to
        if braking_until is not None:
            if t < braking_until:
                brake = 100.0
                v = max(target, v - (250.0 - target) / (braking_until - t + 1))
            else:
                braking_until = None
        elif v < 250.0:
            v = min(250.0, v + 0.8)          # recovering
        frames.append({"lap_distance_m": m, "speed_kph": v,
                       "brake_pct": brake, "lat_g": lat_g})
        m += v / 3.6 / hz
        t += 1
    return frames


def test_a_brake_at_speed_on_the_banking_is_a_penalty():
    served = read_rows(_lap(brakes=[(5200.0, 0.9, 195.0)]), CORNERS)
    assert served is not None and len(served) == 1
    p = served[0]
    assert 5190 <= p.at_m <= 5230
    assert 245.0 <= p.speed_from_kph <= 250.0 and p.speed_to_kph == 195.0
    assert 0.8 <= p.brake_s <= 1.0
    assert p.lost_s > 0.2, "derived, and it is not nothing"


def test_the_bus_stop_brake_is_a_corner_not_a_penalty():
    """The same shape of brake 100 m before T5's start is the corner."""
    served = read_rows(_lap(brakes=[(3775.8 - 100.0, 0.9, 120.0)]), CORNERS)
    assert served == []


def test_the_approach_window_is_the_line():
    just_inside = 3775.8 - APPROACH_M + 5.0
    just_outside = 3775.8 - APPROACH_M - 60.0
    assert read_rows(_lap(brakes=[(just_inside, 0.9, 150.0)]), CORNERS) == []
    assert len(read_rows(_lap(brakes=[(just_outside, 0.9, 150.0)]),
                         CORNERS)) == 1


def test_a_cornering_brake_is_not_a_penalty():
    """Lateral g above the bound means the car is turning: not a zone."""
    frames = _lap(brakes=[(5200.0, 0.9, 195.0)], lat_g=MAX_LAT_G + 0.3)
    assert read_rows(frames, CORNERS) == []


def test_a_dab_is_not_a_penalty():
    assert read_rows(_lap(brakes=[(5200.0, 0.2, 230.0)]), CORNERS) == []


def test_no_frames_is_none_not_zero():
    assert read_rows([], CORNERS) is None
    assert read_rows(None, CORNERS) is None


def test_no_corner_model_is_still_readable_but_the_tool_refuses():
    """With no model every brake on a straight is a candidate; the module
    reads it, and `tools/find_penalties.py` refuses to run without one."""
    served = read_rows(_lap(brakes=[(5200.0, 0.9, 195.0)]), [])
    assert len(served) == 1
