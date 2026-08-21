"""Only speak where he can listen.

*"Agree data should come on straights not corners."* - the driver, 22 Aug.

**Throttle alone does not find a straight.** Run over a clean 109-second Monza
race lap it finds nineteen windows, broken by upshifts rather than by corners,
several of them under heavy lateral load - one at 2.78 g. Speaking at 2.78 g is
worse than speaking in a braking zone.

Adding the lateral gate gives eight, every one at or under 0.30 g, the longest
being 8.9 s from the start/finish line down the main straight.
"""
from __future__ import annotations

from pitcrew.race.straight import Straight, lateral_g, windows


def frames(spec):
    """`(throttle, lat_g)` repeated n times, as `(throttle, lat_g, n)`."""
    out = []
    for throttle, g, count in spec:
        out.extend([{"throttle_pct": throttle, "lat_g": g}] * count)
    return out


def test_a_real_straight_is_found():
    got = windows(frames([(20, 1.2, 60), (100, 0.05, 300), (30, 1.4, 60)]))
    assert len(got) == 1
    assert got[0][2] == 5.0


def test_a_fast_corner_taken_flat_is_not_a_straight():
    """**The failure the measurement found.** Full throttle through Curva
    Grande is full throttle and it is not somewhere to talk."""
    assert windows(frames([(100, 1.9, 300)])) == []


def test_a_brief_straightening_mid_corner_is_not_a_straight():
    assert windows(frames([(100, 1.5, 60), (100, 0.1, 30),
                           (100, 1.5, 60)])) == []


def test_lifting_ends_it():
    got = windows(frames([(100, 0.05, 200), (60, 0.05, 60),
                          (100, 0.05, 200)]))
    assert len(got) == 2


def test_a_straight_running_to_the_end_of_the_lap_still_counts():
    assert len(windows(frames([(40, 1.0, 60), (100, 0.05, 200)]))) == 1


def test_missing_channels_are_not_a_straight():
    """Null is not zero lateral load."""
    assert windows([{"throttle_pct": 100, "lat_g": None}] * 300) == []
    assert windows([{"throttle_pct": None, "lat_g": 0.0}] * 300) == []


# ------------------------------------------------------------------- live

def test_the_live_form_waits_for_the_hold_then_stays_true():
    """It stays true for the rest of the straight, so a caller with something
    to say does not have to catch one particular frame."""
    live = Straight()
    assert not live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.0,
                           now=0.0)
    assert not live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.0,
                           now=1.0)
    assert live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.0, now=2.5)
    assert live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.0, now=6.0)


def test_a_corner_resets_the_hold():
    live = Straight()
    live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.0, now=0.0)
    live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.0, now=3.0)
    assert live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.0, now=3.1)
    # Turn in: 70 m/s at 0.3 rad/s is over 2 g.
    assert not live.update(throttle_pct=100, speed_ms=70.0, yaw_rate=0.3,
                           now=3.2)
    assert live.held_s == 0.0


def test_the_lateral_term_is_the_one_the_recorder_already_derives():
    """`v * yaw` is what `telemetry/recorder` computes `lat_g` from, so the
    live figure and the stored one are the same quantity."""
    assert lateral_g(70.0, 0.3) == abs(70.0 * 0.3) / 9.81
    assert lateral_g(None, 0.3) is None
    assert lateral_g(70.0, None) is None
