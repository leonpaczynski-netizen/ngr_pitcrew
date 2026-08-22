"""Finding a lap in the capture without anyone typing an offset.

`tools/read_hud_wear.py` aligns video to race by taking the zero as lap 1's
crossing less lap 1's own time, and its comment admits that "ignores the
standing start and is therefore a few seconds early". If the app starts the
recording, the zero is not an estimate: both stamps come off this machine's
clock and a lap's position is a subtraction.

So the tests are about the states where it does NOT know the zero, because
those are the ones where a plausible wrong answer is worse than none.
"""
from __future__ import annotations

import datetime as dt

from pitcrew.race.video_index import build, seconds_into_lap

START = dt.datetime(2026, 8, 22, 19, 30, 0)


def a_session(**overrides) -> dict:
    base = {"video_path": "C:/caps/race.mkv",
            "video_started_at": START.isoformat(timespec="seconds")}
    base.update(overrides)
    return base


def laps_at(*offsets_s: float) -> list[dict]:
    """One lap row per crossing, the given seconds after the video started."""
    return [{"lap_num": n,
             "recorded_at": (START + dt.timedelta(seconds=off)).isoformat()}
            for n, off in enumerate(offsets_s, start=1)]


# ------------------------------------------------------------- it does align

def test_a_lap_is_where_the_clock_says_it_is():
    index = build(a_session(), laps_at(120.0, 230.0, 340.0))
    assert index.usable
    assert index.at_lap(2) == 230.0


def test_a_lap_window_runs_from_the_previous_crossing():
    index = build(a_session(), laps_at(120.0, 230.0, 340.0))
    assert index.lap_window(3) == (230.0, 340.0)


def test_the_first_lap_has_no_window_rather_than_a_window_from_zero():
    """**The recording may well have been running while the car sat in the
    box.** Calling that the lap's beginning would put every seek on lap 1
    minutes early, and quietly."""
    index = build(a_session(), laps_at(120.0, 230.0))
    assert index.lap_window(1) is None
    assert index.at_lap(1) == 120.0          # the crossing is still known


def test_it_speaks_the_timestamp_a_player_wants():
    index = build(a_session(), laps_at(120.0))
    assert index.timestamp(3725.0) == "1:02:05"
    assert index.timestamp(59.0) == "0:00:59"
    assert index.timestamp(-5.0) == "0:00:00"


# --------------------------------------------------------- it refuses to guess

def test_no_stored_zero_means_no_index():
    """A capture made by hand has no zero the app can know. The offline tool's
    `--offset` is still the way into those."""
    index = build(a_session(video_started_at=None), laps_at(120.0))
    assert not index.usable
    assert index.at_lap(1) is None
    assert index.path == "C:/caps/race.mkv"   # still says where it is


def test_an_unparseable_stamp_is_the_same_refusal():
    index = build(a_session(video_started_at="last Tuesday"), laps_at(120.0))
    assert not index.usable


def test_a_lap_before_the_recording_began_is_dropped_not_clamped():
    """The capture simply does not contain it. Placing it at second zero would
    seek to the wrong lap, silently."""
    index = build(a_session(), laps_at(-600.0, 120.0, 230.0))
    assert index.at_lap(1) is None
    assert index.at_lap(2) == 120.0


def test_a_lap_a_hair_before_zero_is_kept_at_zero():
    """The two stamps are taken microseconds apart on the same clock; a
    fraction of a second either way is not a different recording."""
    index = build(a_session(), laps_at(-0.4, 120.0))
    assert index.at_lap(1) == 0.0


def test_a_lap_with_no_stamp_is_skipped_and_the_rest_survive():
    laps = laps_at(120.0, 230.0)
    laps[0]["recorded_at"] = None
    index = build(a_session(), laps)
    assert index.at_lap(1) is None
    assert index.at_lap(2) == 230.0


def test_no_laps_at_all_is_not_usable_and_not_a_crash():
    assert not build(a_session(), []).usable


# ------------------------------------------------------------ into the lap

def test_seconds_into_a_lap_at_a_distance():
    frames = [{"lap_distance_m": d, "t_ms": i * 100}
              for i, d in enumerate(range(0, 1000, 10))]
    # 500 m is the 50th frame, 5.0 s in.
    assert seconds_into_lap(frames, 500.0) == 5.0


def test_a_distance_the_lap_never_reached_is_none():
    frames = [{"lap_distance_m": d, "t_ms": i * 100}
              for i, d in enumerate(range(0, 100, 10))]
    assert seconds_into_lap(frames, 5000.0) is None


def test_frames_without_the_channels_are_none_not_zero():
    assert seconds_into_lap([{"lap_distance_m": None, "t_ms": None}],
                            100.0) is None
    assert seconds_into_lap([], 100.0) is None
