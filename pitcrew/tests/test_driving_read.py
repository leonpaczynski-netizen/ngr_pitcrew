"""Lift-and-coast and upshift rpm are measured off the frames, per lap.

`laps.short_shift_rpm` read 0.0 on all twenty Deep Forest laps while the driver
short-shifted by hand for twelve; the debrief read the zero as evidence.
`tools/driving_style.py --session 138 --stints` now reproduces the decomposition
off the archive: stint 1 upshifts at 8298, stint 2 stepping to ~8670 on lap 17.
"""
from __future__ import annotations

from pitcrew.analysis.driving import (COAST_MIN_KPH, LOOKBACK, MIN_FRAMES,
                                      DrivingRead, read_frames, read_rows,
                                      saving_change)


def _frames(n=MIN_FRAMES, *, coast_every=None, shifts=(), speed=150.0):
    """`n` frames at speed on full throttle, with optional coasting spells and
    upshifts at given (frame, rpm) under power."""
    out = []
    for i in range(n):
        out.append({"speed_kph": speed, "throttle_pct": 100.0,
                    "brake_pct": 0.0, "gear": 3, "rpm": 7000.0})
    if coast_every:
        for i in range(0, n, coast_every):
            for j in range(i, min(n, i + 10)):
                out[j] = {**out[j], "throttle_pct": 0.0, "brake_pct": 0.0}
    for at, rpm in shifts:
        out[at - 1] = {**out[at - 1], "rpm": rpm, "throttle_pct": 40.0}
        for j in range(at, n):
            out[j] = {**out[j], "gear": 4}
    return out


def test_coast_share_counts_frames_off_both_pedals_at_speed():
    read = read_frames(_frames(coast_every=100))
    assert read.coast_pct == 10.0
    assert read.full_throttle_pct == 90.0


def test_a_lift_with_the_brake_on_is_a_corner_not_a_coast():
    frames = _frames()
    for j in range(0, 60):
        frames[j] = {**frames[j], "throttle_pct": 0.0, "brake_pct": 40.0}
    assert read_frames(frames).coast_pct == 0.0


def test_the_pit_lane_and_the_grid_do_not_count_as_coasting():
    frames = _frames(speed=COAST_MIN_KPH - 1)
    for f in frames:
        f["throttle_pct"] = 0.0
    assert read_frames(frames).coast_pct == 0.0


def test_the_upshift_rpm_is_read_before_the_lift_for_the_shift():
    """The frame before a shift reads 40% - he lifts to shift. The gate reads
    LOOKBACK frames earlier, where he was flat."""
    read = read_frames(_frames(shifts=((300, 8300.0),)))
    assert read.upshifts == 1
    assert read.upshift_rpm == 8300


def test_an_upshift_off_the_throttle_is_not_under_power():
    frames = _frames(shifts=((300, 8300.0),))
    for j in range(300 - LOOKBACK - 5, 300):
        frames[j] = {**frames[j], "throttle_pct": 10.0}
    read = read_frames(frames)
    assert read.upshifts == 0
    assert read.upshift_rpm is None, "None, never zero"


def test_too_few_frames_is_none_not_zero():
    read = read_frames(_frames(n=100))
    assert read.coast_pct is None and read.upshift_rpm is None


def test_read_rows_takes_the_recorders_column_order():
    fields = ("t_ms", "speed_kph", "throttle_pct", "brake_pct", "gear", "rpm")
    rows = [[i, 150.0, 100.0 if i % 100 else 0.0, 0.0, 3, 7000.0]
            for i in range(MIN_FRAMES)]
    read = read_rows(rows, fields)
    assert read.frames == MIN_FRAMES
    assert read.coast_pct == 1.0


# ------------------------------------------------------------- the step

def _history(pairs):
    return [(lap, DrivingRead(coast_pct=c, full_throttle_pct=60.0,
                              upshift_rpm=u, upshifts=12, frames=5000))
            for lap, c, u in pairs]


def test_the_deep_forest_short_shift_step_is_found_on_lap_17():
    """Off the archive (tools/driving_style.py --session 138):
    upshift 8307 / 8280 / 8314 / 8653 / 8690 on laps 14-18."""
    history = _history([(14, 6.5, 8307), (15, 7.0, 8280), (16, 9.6, 8314),
                        (17, 4.9, 8653), (18, 7.8, 8690)])
    change = saving_change(history)
    assert change is not None
    assert change.what == "short-shift"
    assert change.lap == 17
    assert change.before == 8307 and change.after == 8671.5


def test_stopping_the_lift_and_coast_is_found_first():
    history = _history([(2, 8.3, 8300), (3, 8.1, 8300), (4, 8.5, 8300),
                        (5, 5.9, 8300), (6, 6.0, 8300)])
    change = saving_change(history)
    assert change is not None and change.what == "lift-and-coast"
    assert change.lap == 5


def test_one_flat_out_lap_in_two_is_not_a_change():
    history = _history([(2, 8.3, 8300), (3, 8.1, 8300), (4, 8.5, 8300),
                        (5, 2.0, 8300), (6, 8.4, 8300)])
    assert saving_change(history) is None


def test_a_short_stint_says_nothing():
    assert saving_change(_history([(2, 8.0, 8300), (3, 5.0, 8300),
                                   (4, 5.0, 8300)])) is None
