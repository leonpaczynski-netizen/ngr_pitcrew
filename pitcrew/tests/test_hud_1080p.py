"""The gauge is read at 1920x1080, which is what the PS5 actually outputs.

`read_gauge` refused any canvas that was not 1720x916, on the correct grounds
that the calibrated constants are pixel positions and may not be scaled. The
refusal was right and the conclusion was wrong: **1720x916 is not a property of
the game.** It is an OBS canvas someone chose, and it is not even 16:9 - 1.878
against 1.778 - so it is a window size rather than a scale of the console's own
output.

Forcing it costs twice. The 1080p source is downscaled before it is read, which
makes the bar SHORTER - about 30 px instead of 35, so 3.3% of tyre life per
pixel instead of 2.9% - and it puts the capture at odds with the resolution the
driver broadcasts at. He set OBS to 1920x1080 on 25 Aug 2026 for a broadcast and
wants to keep it there, which is the right call for both reasons.

`locate_gauge` already existed for a harder version of this problem: in VR the
HUD is drawn on the car's dashboard in 3D and moves with head position. A
different canvas is strictly easier - the gauge is in screen space, it is simply
not where 1720x916 put it.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from pitcrew.telemetry.hud import (
    CANVAS,
    LAYOUT_1720x916,
    VR_BAR_MAX_H,
    VR_BAR_MIN_H,
    VR_BAR_MIN_W,
    read_gauge,
)

BROADCAST = (1920, 1080)


def scaled_layout(size: tuple[int, int]) -> dict:
    """Where the HUD lands when GT7 draws it on a bigger screen.

    The game draws its HUD at a fixed proportion of the frame, so the gauge
    scales with the canvas. This is the test's model of the game, NOT the
    reader's - the reader is not allowed to assume it and has to find the bars.
    """
    sx, sy = size[0] / CANVAS[0], size[1] / CANVAS[1]
    return {corner: (round(x0 * sx), round(x1 * sx),
                     round(y0 * sy), round(y1 * sy))
            for corner, (x0, x1, y0, y1) in LAYOUT_1720x916.items()}


def a_canvas(worn: dict[str, float], *, size: tuple[int, int] = BROADCAST,
             dim: float = 1.0) -> bytes:
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    frame[:] = 20
    for corner, (x0, x1, y0, y1) in scaled_layout(size).items():
        rows = y1 - y0 + 1
        red_rows = round(worn.get(corner, 0.0) * rows)
        frame[y0:y0 + red_rows, x0:x1 + 1] = (200, 20, 20)
        frame[y0 + red_rows:y1 + 1, x0:x1 + 1] = (250, 250, 250)
    frame = (frame * dim).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------------------------------------- it reads at 1080p

def test_the_gauge_is_read_at_the_broadcast_resolution():
    got = read_gauge(a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}))

    assert got.ok, got.reason
    assert set(got.wear) == {"fl", "fr", "rl", "rr"}


def test_the_readings_are_right_and_ordered():
    got = read_gauge(a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}))

    # A located read is quantised to the bar it found - about 35 rows at this
    # canvas, so a shade finer than the 3.3 points of the calibrated one.
    assert got.wear["rl"] == pytest.approx(0.6, abs=0.04)
    assert got.wear["fr"] == pytest.approx(0.2, abs=0.04)
    assert got.wear["rl"] > got.wear["fl"] > got.wear["fr"]


def test_a_fresh_set_reads_near_zero_at_1080p():
    got = read_gauge(a_canvas({c: 0.0 for c in LAYOUT_1720x916}))

    assert got.ok, got.reason
    assert max(got.wear.values()) < 0.05


def test_a_worn_set_reads_high_at_1080p():
    got = read_gauge(a_canvas({c: 0.9 for c in LAYOUT_1720x916}))

    assert got.ok, got.reason
    assert min(got.wear.values()) > 0.85


# --------------------------------------------------- the bar is BIGGER here

def test_the_bar_is_taller_at_1080p_than_at_the_old_canvas():
    """The whole reason the old canvas was a cost, not just an inconvenience:
    downscaling to 916 lines threw away gauge resolution."""
    at_916 = LAYOUT_1720x916["fl"]
    at_1080 = scaled_layout(BROADCAST)["fl"]

    rows_916 = at_916[3] - at_916[2] + 1
    rows_1080 = at_1080[3] - at_1080[2] + 1

    assert rows_1080 > rows_916
    # And the extra rows are finer quantisation, which is the point.
    assert 1.0 / rows_1080 < 1.0 / rows_916


def test_the_located_bar_fits_inside_the_locator_s_bounds():
    """If 1080p pushed the bar outside these the locator would never find it,
    and the fallback would be silently useless."""
    at_1080 = scaled_layout(BROADCAST)["fl"]
    rows = at_1080[3] - at_1080[2] + 1
    cols = at_1080[1] - at_1080[0] + 1

    assert VR_BAR_MIN_H <= rows <= VR_BAR_MAX_H
    assert cols >= VR_BAR_MIN_W


# ------------------------------------------------ and it still fails loudly

def test_a_canvas_with_no_gauge_in_it_is_refused_not_guessed():
    frame = np.full((1080, 1920, 3), 20, dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")

    got = read_gauge(buffer.getvalue())

    assert not got.ok
    assert "could not be found" in got.reason


def test_the_calibrated_canvas_still_uses_the_calibrated_layout():
    """The 0.5% verification was taken on the fixed layout at 1720x916. That
    path must not be quietly replaced by the looser located one."""
    at_916 = a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}, size=CANVAS)

    got = read_gauge(at_916)

    assert got.ok, got.reason
    assert got.wear["rl"] == pytest.approx(0.6, abs=0.034)


def test_a_dimmed_1080p_frame_is_still_refused():
    """A pause overlay must not become a reading just because the canvas
    changed - the dim rule is about what the frame IS, not where it is."""
    got = read_gauge(a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4},
                              dim=0.45))

    assert not got.ok, got.wear
