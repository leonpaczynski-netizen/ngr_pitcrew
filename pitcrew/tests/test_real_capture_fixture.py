"""One real recorded lap, aggregated end to end.

CLAUDE.md §7 asks for a recorded session checked in as *the* fixture, so every
aggregation change is re-run against real telemetry rather than against numbers
a test author chose.  There was not one: all 245 files in `captures/` are
byte-identical copies of a single synthetic packet with every angular velocity
at 0.0, so nothing in the suite had ever seen the shape of real data — which is
how a channel holding the roll rate under the name `yaw_rate`, and a slip ratio
2*pi too large, both survived to a pre-UAT review.

`watkins_glen_lap.bin` is the frame blob of lap 79 exactly as the recorder
wrote it: a 1:43.623 on Racing Softs in the Huracán GT3 round the Long Course,
6,211 frames at 60 Hz.  It is a v1 blob, recorded before the channel repairs,
which is the point — it exercises `repair_frames` as well as the aggregation.

The assertions are physics, not golden values.  A lap of a closed circuit turns
through one revolution; a wheel rolling true reads 1.0; a GT3 car pulls 2-3 g.
Those hold whatever the detectors are retuned to, and each one is a defect this
fixture would have caught.
"""
from __future__ import annotations

import json
import math
import pathlib

import pytest

from pitcrew.telemetry.recorder import decode_frames, repair_frames

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def real_lap() -> list[dict]:
    return repair_frames(decode_frames(
        (FIXTURES / "watkins_glen_lap.bin").read_bytes()))


@pytest.fixture(scope="module")
def meta() -> dict:
    return json.loads((FIXTURES / "watkins_glen_lap.json").read_text(encoding="utf-8"))


def test_the_fixture_is_the_lap_it_says_it_is(real_lap, meta):
    assert len(real_lap) == meta["frame_count"] == 6211
    assert meta["lap_time_ms"] == 103623
    assert meta["track"] == "Watkins Glen International"


def test_a_lap_of_a_closed_circuit_turns_through_one_revolution(real_lap):
    """The check that would have caught the yaw axis.

    `yaw_rate` held `angvel_z`, the roll rate, which oscillates about zero and
    integrated to -1.6 degrees over a lap.  Yaw cannot: the car comes back to
    where it started, pointing the way it started.
    """
    turned = 0.0
    for before, after in zip(real_lap, real_lap[1:]):
        if before["yaw_rate"] is None or after["yaw_rate"] is None:
            continue
        span = after["t_ms"] - before["t_ms"]
        turned += 0.5 * (before["yaw_rate"] + after["yaw_rate"]) * span / 1000.0
    assert 300.0 <= abs(math.degrees(turned)) <= 420.0


def test_a_wheel_rolling_true_reads_one(real_lap):
    """The check that would have caught the 2*pi slip error.

    GT7 broadcasts wheel speed in rad/s and the parser multiplied by 2*pi
    again, so a rolling wheel read 6.2832 — and `wheelspin` fired on 99.7% of
    throttle frames while `lockup` could not fire at all.
    """
    coasting = sorted(
        frame["slip_fl"] for frame in real_lap
        if frame.get("slip_fl") is not None
        and (frame.get("speed_kph") or 0) > 80
        and (frame.get("throttle_pct") or 0) < 5
        and (frame.get("brake_pct") or 0) < 5)
    assert len(coasting) > 100, "fixture no longer contains a coasting stretch"
    assert 0.95 <= coasting[len(coasting) // 2] <= 1.05


def test_lateral_acceleration_is_possible_for_a_road_car(real_lap):
    """`lat_g` is speed x yaw and the formula was always right; taken against
    the roll rate it peaked at 8.46 g, which no car generates."""
    peak = max(abs(f["lat_g"]) for f in real_lap if f.get("lat_g") is not None)
    assert 1.0 < peak < 4.0


def test_every_channel_the_aggregators_read_is_present(real_lap):
    frame = real_lap[0]
    for channel in ("speed_kph", "throttle_pct", "brake_pct", "steering_deg",
                    "lap_distance_m", "t_ms", "fuel_l", "gear", "rpm",
                    "susp_mm_fl", "temp_fl", "surf_fl", "pos_x", "pos_z",
                    "yaw_rate", "slip_fl"):
        assert channel in frame, channel


def test_pedals_and_speed_stay_inside_their_range(real_lap):
    for frame in real_lap:
        assert 0.0 <= frame["throttle_pct"] <= 100.0
        assert 0.0 <= frame["brake_pct"] <= 100.0
        assert 0.0 <= (frame.get("speed_kph") or 0.0) < 400.0


def test_the_lap_segments_into_a_believable_number_of_corners(real_lap):
    """The whole point of a fixture: aggregation runs against real data.

    Re-aggregating a stored session after a corner-detection change is what
    CLAUDE.md §6 says separates one evening of work from re-running every test.
    """
    from pitcrew.analysis.corner_model import detect_corners

    model = detect_corners(real_lap, "watkins-glen-long")
    assert model is not None
    # A detector returning dozens has found speed wobbles, not corners.
    assert 4 <= len(model.corners) <= 16
