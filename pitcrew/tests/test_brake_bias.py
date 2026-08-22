"""The brake-bias instrument, which will be asked to settle a physics question.

`tools/` is otherwise untested here, and this one is the exception on purpose:
its output is going to be read as evidence about what a click of brake balance
does on GT7 1.71. A tool that answers a question nobody can check is worse than
no tool, so the event finder and the split are pinned.

The measurement itself: `slip_*` is wheel surface speed over car speed, so
below 1.0 is locking, and **the axle that goes lower is the one carrying more
brake than its grip supports**. Front minus rear is therefore negative when the
front locks deeper, which on the settled convention is what front bias does.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.brake_bias import (                               # noqa: E402
    BRAKE_ON_PCT,
    MIN_EVENT_FRAMES,
    MIN_SPEED_KPH,
    Stop,
    find_stops,
    trail_slip,
)


def frame(*, brake=0.0, speed=200.0, front=1.0, rear=1.0, steer=0.0) -> dict:
    return {"brake_pct": brake, "speed_kph": speed,
            "slip_fl": front, "slip_fr": front,
            "slip_rl": rear, "slip_rr": rear,
            "steering_norm": steer}


def braking(n, *, front=0.88, rear=0.92, start=250.0, end=100.0) -> list[dict]:
    """One stop, decelerating linearly, with the axles at stated slip."""
    return [frame(brake=90.0, speed=start + (end - start) * i / max(1, n - 1),
                  front=front, rear=rear) for i in range(n)]


def stops_in(frames):
    return find_stops(frames, lap_id=1, lap_num=1, schema_version=2,
                      sample_hz=60.0)


# ------------------------------------------------------------ finding a stop

def test_a_real_stop_is_found():
    got = stops_in([frame()] * 30 + braking(120) + [frame()] * 30)
    assert len(got) == 1
    assert got[0].frames == 120


def test_two_stops_on_one_lap_are_two_events():
    frames = ([frame()] * 20 + braking(90) + [frame()] * 40
              + braking(90) + [frame()] * 20)
    assert len(stops_in(frames)) == 2


def test_a_dab_is_not_a_stop():
    """A downshift stab and a trail-brake release are not braking events."""
    assert stops_in([frame()] * 20
                    + braking(MIN_EVENT_FRAMES - 5)
                    + [frame()] * 20) == []


def test_below_the_speed_floor_nothing_is_measured():
    """The slip ratio divides by car speed, so at a crawl it is arithmetic on
    a divisor that means nothing - the same floor the recorder applies before
    it stores one at all."""
    crawl = [frame(brake=90.0, speed=MIN_SPEED_KPH - 5) for _ in range(120)]
    assert stops_in(crawl) == []


def test_light_pedal_is_not_a_stop():
    light = [frame(brake=BRAKE_ON_PCT - 10, speed=200.0) for _ in range(120)]
    assert stops_in(light) == []


def test_a_stop_still_open_at_the_flag_is_still_measured():
    """A lap that ends under braking is a lap that ends under braking."""
    assert len(stops_in([frame()] * 20 + braking(120))) == 1


def test_frames_missing_a_channel_are_skipped_not_guessed():
    frames = [frame()] * 10 + braking(120)
    frames[40] = {"brake_pct": None, "speed_kph": None}
    assert len(stops_in(frames)) >= 1


# ------------------------------------------------------------- the split

def test_the_front_locking_deeper_reads_negative():
    """**The sign the whole tool turns on.** Negative split = front deeper,
    which on the settled convention is what front bias does."""
    got = stops_in([frame()] * 10 + braking(120, front=0.85, rear=0.95))
    assert got[0].split < 0


def test_the_rear_locking_deeper_reads_positive():
    got = stops_in([frame()] * 10 + braking(120, front=0.95, rear=0.85))
    assert got[0].split > 0


def test_an_even_axle_split_reads_zero():
    got = stops_in([frame()] * 10 + braking(120, front=0.90, rear=0.90))
    assert got[0].split == 0.0


def test_the_split_is_none_where_an_axle_never_read():
    """Missing is null. A slip channel the packet format did not carry must
    not become a split of zero, which would say the axles were even."""
    assert Stop(1, 1, 100, 200.0, 100.0, None, 0.9, 1.4, 2).split is None
    assert Stop(1, 1, 100, 200.0, 100.0, 0.9, None, 1.4, 2).split is None


def test_it_takes_the_minimum_of_the_event_not_the_last_frame():
    """The deepest the axle got is the measurement; where it ended up is not."""
    frames = ([frame()] * 10 + braking(60, front=0.95, rear=0.95)
              + braking(60, front=0.70, rear=0.95))
    got = stops_in(frames)
    assert got[0].front_min_slip == 0.70


# -------------------------------------------------------------- deceleration

def test_deceleration_is_measured_over_the_whole_event():
    """Mean, not peak: one frame of a 60 Hz stream is where the decode
    artefacts live."""
    got = stops_in([frame()] * 10 + braking(120, start=200.0, end=20.0))
    # 180 km/h shed over 2 s is 25 m/s^2, about 2.55 g.
    assert 2.3 < got[0].decel_g < 2.8


# ------------------------------------------------------------- trail braking

def test_the_trail_window_needs_brake_and_lock_together():
    """Braking in a straight line is not trail braking, and neither is
    steering off the brakes."""
    straight = [frame(brake=90.0, steer=0.0) for _ in range(100)]
    coasting = [frame(brake=0.0, steer=0.5) for _ in range(100)]
    assert trail_slip(straight)[2] == 0
    assert trail_slip(coasting)[2] == 0


def test_the_trail_window_counts_frames_not_corners():
    """The reason it exists: per-corner metrics carry a 2 sd of 9-11 km/h on
    minimum speed and cannot resolve a click of bias. This gives hundreds of
    samples off a single lap."""
    frames = [frame(brake=40.0, steer=0.4, front=0.96, rear=0.97)
              for _ in range(500)]
    front, rear, samples = trail_slip(frames)
    assert samples == 500
    assert front < rear
