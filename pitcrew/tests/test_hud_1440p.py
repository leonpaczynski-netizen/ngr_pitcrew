"""The live sampler at the driver's actual resolution.

He moved to 2560x1440 on 2 Sep 2026. `read_gauge` had already grown a locate
path for a non-calibrated canvas and `bar_height_bounds` already scaled with
it — but `ScreenSource.grab` still refused any client area that was not exactly
1720x916, so the live wear channel went silent at the resolution he actually
races at.

Silent, not wrong, which is the better of the two failures — and still bad: a
channel that returns a reason every lap looks identical to one nobody checked.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from pitcrew.telemetry.hud import (
    CANVAS,
    FLAT_BAR_ROWS,
    LAYOUT_1720x916,
    CropFrame,
    bar_height_bounds,
    read_gauge,
)

QHD = (2560, 1440)


def _scaled(size):
    sx, sy = size[0] / CANVAS[0], size[1] / CANVAS[1]
    return {corner: (round(x0 * sx), round(x1 * sx),
                     round(y0 * sy), round(y1 * sy))
            for corner, (x0, x1, y0, y1) in LAYOUT_1720x916.items()}


def _pixels(worn, size=QHD):
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    frame[:] = 20
    for corner, (x0, x1, y0, y1) in _scaled(size).items():
        rows = y1 - y0 + 1
        red = round(worn.get(corner, 0.0) * rows)
        frame[y0:y0 + red, x0:x1 + 1] = (200, 20, 20)
        frame[y0 + red:y1 + 1, x0:x1 + 1] = (250, 250, 250)
    return frame


def _png(worn, size=QHD):
    buffer = io.BytesIO()
    Image.fromarray(_pixels(worn, size)).save(buffer, format="PNG")
    return buffer.getvalue()


WORN = {"fl": 0.40, "fr": 0.20, "rl": 0.60, "rr": 0.40}


def test_a_1440p_bar_is_inside_candidacy():
    """GT7 draws the flat bar at canvas_height / 30, so 48 px at 1440p. A
    fixed cap of 40 excluded it and the locator returned 16 px fragments
    reading 0.000 on all four corners."""
    low, high = bar_height_bounds(QHD[1])
    assert low <= QHD[1] / FLAT_BAR_ROWS <= high


def test_the_gauge_is_read_at_1440p_from_a_png():
    got = read_gauge(_png(WORN))
    assert got.ok, got.reason
    assert set(got.wear) == {"fl", "fr", "rl", "rr"}


def test_a_full_canvas_grab_is_read_rather_than_refused():
    """The fix. `ScreenSource` now hands over the whole client area when the
    window is not the calibrated canvas, so the locator has somewhere to look;
    a `CropFrame` covering the entire canvas is not a crop."""
    whole = CropFrame(pixels=_pixels(WORN), origin=(0, 0), canvas=QHD)
    got = read_gauge(whole)
    assert got.ok, got.reason
    assert set(got.wear) == {"fl", "fr", "rl", "rr"}


def test_a_located_read_is_honest_about_being_one():
    """It classifies on the looser thresholds the locator found the bars with,
    so it must never be confused with the fixed-layout read the 0.5%
    verification was taken on."""
    got = read_gauge(CropFrame(pixels=_pixels(WORN), origin=(0, 0), canvas=QHD))
    assert got.ok
    assert got.located


def test_the_readings_are_in_the_right_order_at_1440p():
    got = read_gauge(_png(WORN))
    assert got.wear["rl"] > got.wear["fl"] > got.wear["fr"]
    assert got.wear["fl"] == pytest.approx(0.40, abs=0.05)


def test_a_genuine_crop_of_the_wrong_canvas_is_still_refused():
    """The relaxation is only for a whole canvas. A real crop is a bet that
    the gauge did not move, and on the wrong canvas that bet is lost."""
    pixels = _pixels(WORN)[100:400, 100:400]
    got = read_gauge(CropFrame(pixels=pixels, origin=(100, 100), canvas=QHD))
    assert not got.ok
    assert "calibrated" in got.reason or "not contain" in got.reason


def test_a_full_canvas_with_no_gauge_in_it_is_refused_not_guessed():
    blank = np.full((QHD[1], QHD[0], 3), 20, dtype=np.uint8)
    got = read_gauge(CropFrame(pixels=blank, origin=(0, 0), canvas=QHD))
    assert not got.ok
    assert got.wear is None


def test_the_calibrated_canvas_still_takes_the_fixed_layout_path():
    """1720x916 must keep the verified read, not fall into the locator."""
    got = read_gauge(_png(WORN, size=CANVAS), )
    assert got.ok, got.reason
    assert not got.located
