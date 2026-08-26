"""The offline reader: one reader, one locator, one rule about tyres.

`tools/read_hud_wear.py` reads GT7's tyre-wear gauge out of an OBS capture and
writes it into `laps`. It had drifted into being a second implementation of
`pitcrew/telemetry/hud.py` - its own copy of the calibrated layout, its own bar
classifier, no fall-through to the locator that `hud.py` gained in `55aa96e`,
and no check at all on whether what it read could have come from a tyre.

Three things followed from that, all measured on the driver's own captures on
26 Aug 2026, and each has a test here:

* **On the 1920x1080 canvas he now broadcasts at it read nothing.** Fourteen
  samples of the race he was recording that morning: the old reader found a
  gauge in none of them, the shared one in all fourteen.
* **Where it did read something it filed it whatever the numbers said.** The
  `hud-video` rows in sessions 71 and 77 contain steps no tyre can make - a
  corner recovering 24 points between two laps, another reading the same at
  lap 20 as at lap 11 on a set fitted in between.
* **A found gauge can be found in the wrong place**, and the answer that comes
  back is not blank, it is confident and wrong. That is what the locator tests
  below are about.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from pitcrew.store.db import WEAR_HUD_VIDEO, Store
from pitcrew.telemetry import hud
from pitcrew.telemetry.hud import CANVAS, LAYOUT_1720x916, read_gauge, wear_faults
from pitcrew.telemetry.session_state import Lap

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import read_hud_wear as tool                                  # noqa: E402

BROADCAST = (1920, 1080)
CORNERS = ("fl", "fr", "rl", "rr")


# --------------------------------------------------------------- canvases

def scaled_layout(size: tuple[int, int]) -> dict:
    """Where the HUD lands when GT7 draws it on a canvas of this size.

    The game's model, not the reader's: the reader is not allowed to assume it
    and has to find the bars.
    """
    sx, sy = size[0] / CANVAS[0], size[1] / CANVAS[1]
    return {corner: (round(x0 * sx), round(x1 * sx),
                     round(y0 * sy), round(y1 * sy))
            for corner, (x0, x1, y0, y1) in LAYOUT_1720x916.items()}


def a_canvas(worn: dict[str, float], *, size: tuple[int, int] = BROADCAST,
             icon: bool = True) -> bytes:
    """A frame with the gauge on it, at whatever canvas size.

    `icon` draws the grey car between the two columns of bars. It is drawn by
    default because it is always there in the game, and it can be turned off
    to make the frame that `VR_ICON_MAX_SOLID` exists to refuse.
    """
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    frame[:] = 20
    layout = scaled_layout(size)
    if icon:
        x0 = max(layout["fl"][1], layout["rl"][1]) + 4
        x1 = min(layout["fr"][0], layout["rr"][0]) - 4
        frame[layout["fl"][2]:layout["rl"][3], x0:x1] = (95, 95, 95)
    for corner, (x0, x1, y0, y1) in layout.items():
        rows = y1 - y0 + 1
        red_rows = round(worn.get(corner, 0.0) * rows)
        frame[y0:y0 + red_rows, x0:x1 + 1] = (200, 20, 20)
        frame[y0 + red_rows:y1 + 1, x0:x1 + 1] = (250, 250, 250)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")
    return buffer.getvalue()


def as_frame(png: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)


# ------------------------------------------------- there is only one reader

def test_the_offline_tool_carries_no_reader_of_its_own():
    """The duplication is the root cause, so its absence is the fix.

    Every one of these was a module-level name in the tool, and each was a
    copy of something in `hud.py` that had since been fixed without it.
    """
    for gone in ("LAYOUT_1720x916", "_read_bars", "MIN_CLASSIFIED_ROWS",
                 "FRESH_SET_DROP"):
        assert not hasattr(tool, gone), (
            f"{gone} is back in the offline tool - it belongs to hud.py")
    assert tool.read_gauge is hud.read_gauge
    assert tool.coherent is hud.coherent
    assert tool.wear_faults is hud.wear_faults


def old_cropping_reader(frame, layout: dict) -> dict:
    """The reader the tool used to carry, verbatim, as an oracle.

    Session 52's wear rate - 0.0558 and 0.0561 per lap across two independent
    stints - was measured with this code. Deduplicating must not move those
    numbers by a pixel, so the replacement is checked against it rather than
    against a fresh assertion of what the answer should be.
    """
    out = {}
    for corner, (x0, x1, y0, y1) in layout.items():
        bar = frame[y0:y1 + 1, x0:x1 + 1]
        r, g, b = bar[..., 0], bar[..., 1], bar[..., 2]
        red = (r > 110) & (r - g > 55) & (r - b > 55)
        white = (r > 150) & (g > 150) & (b > 150)
        n_red = int((red.mean(axis=1) > 0.5).sum())
        n_white = int((white.mean(axis=1) > 0.5).sum())
        total = n_red + n_white
        out[corner] = n_red / total if total >= 20 else None
    return out


@pytest.mark.parametrize("worn", [
    {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0},
    {"fl": 0.1, "fr": 0.2, "rl": 0.3, "rr": 0.4},
    {"fl": 0.55, "fr": 0.4, "rl": 0.62, "rr": 0.52},
    {"fl": 0.9, "fr": 0.9, "rl": 0.9, "rr": 0.9},
])
def test_the_calibrated_canvas_reads_what_the_old_cropping_reader_read(worn):
    """Same pixels, same arithmetic, same numbers - to the pixel."""
    png = a_canvas(worn, size=CANVAS)

    got = read_gauge(png)
    oracle = old_cropping_reader(as_frame(png), LAYOUT_1720x916)

    assert got.ok, got.reason
    assert got.wear == oracle
    assert not got.located, "the calibrated canvas must not need the locator"


# ------------------------------------- a canvas nobody calibrated is READ

def test_a_1920x1080_capture_is_read_instead_of_refused():
    """He set OBS to 1920x1080 on 25 Aug and races there now.

    The old tool cropped the 1720x916 rectangle out of it, classified whatever
    was in that rectangle, and aborted with "no readable gauge". Measured over
    fourteen samples of his 26 Aug race capture: nothing readable in any of
    them, against a gauge that is on screen in all fourteen.
    """
    got = read_gauge(a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}))

    assert got.ok, got.reason
    assert got.located, "1920x1080 is not the calibrated canvas"
    assert got.wear["rl"] == pytest.approx(0.6, abs=0.04)
    assert got.wear["rl"] > got.wear["fl"] > got.wear["fr"]


def test_a_reading_carries_the_bar_height_it_came_from():
    """One pixel of a 36 px bar is 2.8% of tyre life and one pixel of an 18 px
    bar is 5.6%. The two look identical once they are floats in a column, so
    the number that separates them travels with the reading."""
    big = read_gauge(a_canvas({c: 0.5 for c in CORNERS}, size=BROADCAST))
    calibrated = read_gauge(a_canvas({c: 0.5 for c in CORNERS}, size=CANVAS))

    assert calibrated.rows == 30, "the calibrated bar is 30 px, 3.3% a pixel"
    assert big.rows >= 34, "1080p gives about 36 rows - 2.8% a pixel"
    assert 100 / big.rows < 100 / calibrated.rows, (
        "the finer canvas must be the finer reading, and say so")


def test_the_tool_reports_the_quantisation_the_gate_will_use():
    """What the operator has to see before applying anything: how coarse the
    reading is, taken from the COARSEST bar in the run rather than the best."""
    rows = [(0.0, hud.Reading({c: 0.1 for c in CORNERS}, rows=36)),
            (15.0, hud.Reading({c: 0.2 for c in CORNERS}, rows=30))]

    bar_px, slack = tool.quantisation(rows)

    assert bar_px == 30
    assert slack == pytest.approx(1 / 30)
    assert 100 / bar_px == pytest.approx(3.33, abs=0.01)


def test_with_no_bar_height_at_all_the_slack_falls_back_and_does_not_crash():
    bar_px, slack = tool.quantisation([])

    assert bar_px is None
    assert slack == hud.GAUGE_SLACK


# --------------------------------------- the gauge is FOUND, so it can be
# --------------------------------------- found in the wrong place
#
# Both of these are real frames from real captures, reduced to their shape.
# Neither produced a blank reading: one read every corner at 0% worn and one
# read two corners at 100%, and both would have been filed.

def test_a_tight_stack_of_fragments_is_not_a_gauge():
    """The 25 Aug replay: four fragments of the track map, 3 px wide, 9 px
    tall, 10 px apart. The old rule was "the four closest together win", and
    a stack in one column beats an instrument 84 px wide every time."""
    frame = np.full((1080, 1920, 3), 20, dtype=np.uint8)
    for column, (x0, x1) in enumerate(((1740, 1742), (1750, 1752))):
        for y0 in (499, 566):
            frame[y0:y0 + 9, x0:x1 + 1] = (250, 250, 250)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")

    assert hud.locate_gauge(as_frame(buffer.getvalue())) is None
    assert not read_gauge(buffer.getvalue()).ok


def test_four_bars_with_no_car_between_them_are_not_a_gauge():
    """The VR frame at lap 5 of session 87: the located rectangle was the
    sky and the position counter, and it read 0% worn on all four corners
    with the set five laps old. A monotonicity check cannot catch that - a
    run of zeros follows a run of zeros perfectly well - so it has to be
    caught here, by what is BETWEEN the bars.

    Measured: 2.1% to 10.5% of that space classifies as red or white on four
    real gauges, and 90.3% on this one.
    """
    png = a_canvas({c: 0.0 for c in CORNERS}, icon=False)
    frame = as_frame(png)
    layout = scaled_layout(BROADCAST)
    # Sky, floodlit, where the car icon should be.
    frame[layout["fl"][2]:layout["rl"][3],
          layout["fl"][1] + 2:layout["fr"][0] - 1] = (230, 235, 245)
    buffer = io.BytesIO()
    Image.fromarray(frame.astype(np.uint8)).save(buffer, format="PNG")

    assert hud.locate_gauge(as_frame(buffer.getvalue())) is None


def test_the_real_gauge_is_still_found_with_the_car_between_the_bars():
    """The other half of the test above: the icon is why the gauge passes."""
    got = read_gauge(a_canvas({"fl": 0.3, "fr": 0.2, "rl": 0.4, "rr": 0.3}))

    assert got.ok, got.reason
    assert got.wear["rl"] == pytest.approx(0.4, abs=0.04)


def test_a_sample_that_read_a_different_sized_bar_is_not_used():
    """The gauge does not change size in a screen capture.

    Measured over the 26 Aug sweep: twelve samples found a 36 px bar, one a
    35 px one - the seam between red and white, a pixel either way - and two
    found something else entirely, at 16 px and 20 px. The 16 px one read two
    corners as 100% worn; the 20 px one read every corner as 0% and would have
    been filed as a fresh set, cutting the stint in two.
    """
    rows = [(0.0, hud.Reading({c: 0.10 for c in CORNERS}, rows=36)),
            (15.0, hud.Reading({c: 0.12 for c in CORNERS}, rows=35)),
            (30.0, hud.Reading({"fl": 0.0, "fr": 0.0, "rl": 1.0, "rr": 1.0},
                               rows=16)),
            (45.0, hud.Reading({c: 0.14 for c in CORNERS}, rows=36))]

    kept, odd, modal = tool.one_instrument(rows)

    assert modal == 36
    assert [at for at, _ in kept] == [0.0, 15.0, 45.0]
    assert [at for at, _ in odd] == [30.0]


# ----------------------------------------------------------------- the gate
#
# The acceptance test for the whole change: it has to keep the data that is
# good and refuse the data that is not, and the two are already on file.

SESSION_52 = [
    (1, 0.065, 0.000, 0.033, 0.000), (2, 0.100, 0.067, 0.100, 0.069),
    (3, 0.167, 0.069, 0.194, 0.133), (4, 0.200, 0.133, 0.207, 0.194),
    (5, 0.267, 0.167, 0.276, 0.207), (6, 0.333, 0.200, 0.333, 0.267),
    (7, 0.345, 0.233, 0.400, 0.333), (8, 0.400, 0.267, 0.467, 0.345),
    (9, 0.467, 0.300, 0.516, 0.400), (10, 0.533, 0.333, 0.552, 0.467),
    (11, 0.581, 0.387, 0.621, 0.516), (12, 0.633, 0.400, 0.667, 0.533),
    (13, 0.667, 0.414, 0.733, 0.600), (14, 0.733, 0.467, 0.800, 0.667),
    (15, 0.774, 0.500, 0.867, 0.690),
    # The stop. Every corner back to a tenth or less - a fresh set.
    (17, 0.069, 0.067, 0.100, 0.069), (18, 0.138, 0.069, 0.138, 0.133),
    (19, 0.200, 0.133, 0.200, 0.194), (20, 0.267, 0.194, 0.267, 0.207),
    (21, 0.300, 0.200, 0.333, 0.267), (22, 0.345, 0.258, 0.400, 0.333),
    (23, 0.400, 0.267, 0.467, 0.367), (24, 0.467, 0.333, 0.516, 0.414),
    (25, 0.533, 0.333, 0.567, 0.467), (26, 0.581, 0.400, 0.621, 0.533),
]

SESSION_77 = [
    (8, 0.333, 0.200, 0.300, 0.250), (9, 0.333, 0.286, 0.353, 0.444),
    (10, 0.444, 0.250, 0.350, 0.200), (11, 0.429, 0.211, 0.368, 0.200),
    # A set was fitted at lap 12 and lap 20 reads what lap 11 read.
    (20, 0.368, 0.222, 0.350, 0.200), (21, 0.368, 0.200, 0.389, 0.400),
]


def as_series(rows):
    return [(lap, dict(zip(CORNERS, values))) for lap, *values in rows]


def gate(rows, *, bar_px: int):
    """The gate exactly as `--apply` applies it."""
    return wear_faults(as_series(rows), slack=1.0 / bar_px,
                       max_rise=tool.LAP_MAX_RISE,
                       span=lambda before, after: after - before)


def test_the_race_the_wear_model_rests_on_still_passes():
    """Session 52, Monza, 18 Aug 2026 - 25 readings across two sets off a
    31 px bar. Nothing in it may be refused: this is the run that produced
    0.0558 and 0.0561 per lap, and the app's wear model is built on it."""
    assert gate(SESSION_52, bar_px=31) == []


def test_the_road_atlanta_race_is_refused_and_says_which_laps():
    """Session 77, 23 Aug 2026, off a 20 px bar. Two steps in it are not
    possible on one set of tyres, and the operator is told which."""
    faults = gate(SESSION_77, bar_px=20)

    assert faults, "this series was written to the archive as measured wear"
    named = {(fault.before, fault.after): fault for fault in faults}
    assert (9, 10) in named, "RR recovered 24 points between two laps"
    assert "rr" in named[(9, 10)].corners
    assert (11, 20) in named, "lap 20 reads what lap 11 read on the old set"
    assert "fl" in named[(11, 20)].corners
    # Every fault says which laps and which corners, in the message itself.
    for fault in faults:
        text = str(fault)
        assert str(fault.before) in text and str(fault.after) in text
        assert any(corner.upper() in text for corner in fault.corners)


def test_a_fresh_set_is_not_a_fault():
    """The stop in session 52: 87% to 10% on every corner in one step."""
    assert gate([(15, 0.774, 0.500, 0.867, 0.690),
                 (17, 0.069, 0.067, 0.100, 0.069)], bar_px=31) == []


def test_a_drop_onto_a_set_too_worn_to_be_new_is_a_fault():
    """The other side of it, and the reason the fresh-set test is not just
    "everything fell": all four fell and it still reads 42% worst."""
    faults = gate([(4, 0.63, 0.37, 0.68, 0.55),
                   (5, 0.42, 0.25, 0.39, 0.23)], bar_px=31)

    assert len(faults) == 1
    assert "too worn for a fresh set" in faults[0].why


def test_one_pixel_of_quantisation_either_way_is_not_a_fault():
    """A 31 px bar puts a corner 3.2 points either side of where it sits, and
    a gate that refuses that throws away the only measured wear the app has.

    Session 78 lap 14 read FR one row BELOW lap 13 while the other three rose.
    That is the bar, not the tyre.
    """
    assert gate([(13, 0.550, 0.381, 0.619, 0.524),
                 (14, 0.632, 0.368, 0.684, 0.550)], bar_px=23) == []


def test_a_corner_going_backwards_on_its_own_is_a_fault():
    """Session 71, laps 9 to 10: FR falls 6 points while nothing else moves.

    `hud.coherent` accepts this on the race path - it is tuned to keep
    sampling, and the next sample is two seconds away. A batch write is the
    opposite trade, so the gate is stricter here and says so.
    """
    step = [(9, 0.389, 0.312, 0.312, 0.211), (10, 0.400, 0.250, 0.333, 0.200)]

    assert hud.coherent(as_series(step)[0][1], as_series(step)[1][1],
                        slack=1 / 19)[0] is True
    faults = gate(step, bar_px=19)
    assert len(faults) == 1
    assert faults[0].corners == ("fr",)
    assert "backwards" in faults[0].why


def test_a_lap_of_RS_wear_is_not_treated_as_a_leap():
    """The live ceiling is 15 points between readings SECONDS apart. A lap is
    not seconds: measured across the archive, the largest honest per-lap rises
    are 16.7, 15.4, 15.0 and 14.1 points, all on RS, all in series that never
    go backwards. Session 81, laps 3 and 4, is the largest of them."""
    assert gate([(3, 0.389, 0.263, 0.412, 0.333),
                 (4, 0.500, 0.316, 0.579, 0.474)], bar_px=19) == []


def test_a_corner_that_jumps_half_the_bar_in_one_lap_is_still_a_fault():
    """Raising the ceiling for a lap is not removing it."""
    faults = gate([(3, 0.20, 0.20, 0.20, 0.20),
                   (4, 0.25, 0.24, 0.75, 0.22)], bar_px=31)

    assert len(faults) == 1
    assert faults[0].corners == ("rl",)


def test_a_step_over_many_laps_is_allowed_many_laps_of_wear():
    """A VR capture reads a handful of crossings, so two readings can be five
    laps apart. Five laps of RS is 60 points and it is not a misread."""
    assert gate([(3, 0.10, 0.10, 0.10, 0.10),
                 (8, 0.70, 0.68, 0.72, 0.70)], bar_px=31) == []


# ------------------------------------------------- and it refuses to WRITE

def a_session_of_laps(store: Store, event_id: int, count: int) -> list[dict]:
    session_id = store.start_session(event_id, "race")
    for lap_num in range(1, count + 1):
        store.add_lap(session_id, Lap(
            lap_num=lap_num, lap_time_ms=94_000, best_lap_ms=93_000,
            delta_ms=1_000, fuel_start=100.0 - 3.4 * (lap_num - 1),
            fuel_end=100.0 - 3.4 * lap_num, fuel_used=3.4, position=3,
            is_pit_lap=False, is_out_lap=False))
    return session_id, store.list_laps(session_id)


def run_apply(monkeypatch, store, session_id, laps, readings, tmp_path):
    """Drive `main()` over a set of readings, with the video faked out."""
    video = tmp_path / "capture.mp4"
    video.write_bytes(b"not really a video")
    monkeypatch.setattr(tool, "probe", lambda path: (600.0, (1920, 1080)))
    monkeypatch.setattr(tool, "sample",
                        lambda *args, **kwargs: list(readings))
    # One crossing per lap, ten seconds apart, so each reading lands on the
    # lap it was taken during.
    monkeypatch.setattr(tool, "_crossings", lambda *a, **k: [
        (10.0 * lap["lap_num"], lap) for lap in laps])
    monkeypatch.setattr(sys, "argv", [
        "read_hud_wear.py", "--db", str(store.path),
        "--session", str(session_id), "--video", str(video), "--apply"])
    return tool.main()


def test_apply_writes_nothing_when_the_series_could_not_have_happened(
        store: Store, event_id: int, monkeypatch, tmp_path):
    """**Refused, not filed.** These rows go into `laps` under a source that
    says they were measured, and the wear model divides consumed life by laps
    run - so one impossible step becomes a stint length a race gets planned
    around."""
    session_id, laps = a_session_of_laps(store, event_id, 3)
    readings = [
        (10.0, hud.Reading({"fl": 0.20, "fr": 0.20, "rl": 0.20, "rr": 0.20},
                           rows=36)),
        (20.0, hud.Reading({"fl": 0.26, "fr": 0.26, "rl": 0.26, "rr": 0.26},
                           rows=36)),
        # RR recovers 20 points, which is session 77's shape exactly.
        (30.0, hud.Reading({"fl": 0.32, "fr": 0.32, "rl": 0.32, "rr": 0.06},
                           rows=36)),
    ]

    assert run_apply(monkeypatch, store, session_id, laps, readings,
                     tmp_path) == 2
    after = store.list_laps(session_id)
    assert all(lap["wear_source"] is None for lap in after)
    assert all(lap["wear_fl"] is None for lap in after), (
        "a refused run must leave the laps unmeasured, not zeroed")


def test_apply_writes_a_series_that_could_have_happened(
        store: Store, event_id: int, monkeypatch, tmp_path):
    """The gate has to keep the good data as well as refuse the bad."""
    session_id, laps = a_session_of_laps(store, event_id, 3)
    readings = [
        (10.0, hud.Reading({"fl": 0.20, "fr": 0.17, "rl": 0.22, "rr": 0.19},
                           rows=36)),
        (20.0, hud.Reading({"fl": 0.26, "fr": 0.22, "rl": 0.28, "rr": 0.25},
                           rows=36)),
        (30.0, hud.Reading({"fl": 0.32, "fr": 0.28, "rl": 0.36, "rr": 0.31},
                           rows=36)),
    ]

    assert run_apply(monkeypatch, store, session_id, laps, readings,
                     tmp_path) == 0
    after = {lap["lap_num"]: lap for lap in store.list_laps(session_id)}
    assert after[3]["wear_source"] == WEAR_HUD_VIDEO
    assert after[3]["wear_rl"] == pytest.approx(0.36)
