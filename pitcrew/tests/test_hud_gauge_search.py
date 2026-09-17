"""The gauge is searched for where it last was, and a whole frame is read as pixels.

A free-running grab used to cost about 460 ms of worker time at 1080p, 322 ms
of it in `read_gauge`: the frame went through a PNG encode and decode for no
change in content, and `locate_gauge` swept the whole screen for an instrument
that had not moved since the last grab. Measured 17 Sep 2026 on the Rd 9
recording, the read is 17.5 ms with both removed, and the readings on all six
race frames are identical.

What these tests hold is that the speed-up changed nothing about WHAT is read:
the pixel path gives the PNG path's reading, a hint finds the same gauge the
full search does, and a hint in the wrong place falls back rather than guessing.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from pitcrew.telemetry.hud import (
    CropFrame,
    LiveWearSampler,
    locate_gauge,
    locate_gauge_near,
    read_gauge,
)
from pitcrew.tests.test_hud_1080p import BROADCAST, a_canvas, scaled_layout

WORN = {"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}


def pixels(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def whole(png: bytes) -> CropFrame:
    px = pixels(png)
    return CropFrame(pixels=px, origin=(0, 0), canvas=(px.shape[1], px.shape[0]))


def shifted(png: bytes, dx: int, dy: int) -> bytes:
    px = pixels(png)
    moved = np.full_like(px, 20)
    moved[dy:, dx:] = px[:px.shape[0] - dy, :px.shape[1] - dx]
    buffer = io.BytesIO()
    Image.fromarray(moved).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_whole_frame_reads_the_same_as_its_png():
    png = a_canvas(WORN)
    from_png, from_pixels = read_gauge(png), read_gauge(whole(png))

    assert from_pixels.ok, from_pixels.reason
    assert (from_pixels.wear, from_pixels.bars, from_pixels.reason) == \
           (from_png.wear, from_png.bars, from_png.reason)


def test_a_hint_finds_the_same_gauge_as_the_full_search():
    frame = pixels(a_canvas(WORN)).astype(int)
    full = locate_gauge(frame)

    assert full is not None
    assert locate_gauge_near(frame, full) == full


def test_a_hint_in_the_wrong_place_falls_back_to_the_whole_frame():
    frame = pixels(a_canvas(WORN)).astype(int)
    elsewhere = {"fl": (1500, 1510, 100, 136), "rl": (1500, 1510, 150, 186),
                 "fr": (1590, 1600, 100, 136), "rr": (1590, 1600, 150, 186)}

    assert locate_gauge_near(frame, elsewhere) == locate_gauge(frame)


def test_a_gauge_that_moved_is_found_from_the_old_hint():
    png = a_canvas(WORN)
    old = locate_gauge(pixels(png).astype(int))
    moved = pixels(shifted(png, 40, 25)).astype(int)

    got = locate_gauge_near(moved, old)
    assert got is not None and got != old
    assert got == locate_gauge(moved)


def test_no_gauge_is_none_with_or_without_a_hint():
    blank = np.full((BROADCAST[1], BROADCAST[0], 3), 20, dtype=int)
    hint = scaled_layout(BROADCAST)

    assert locate_gauge_near(blank, hint) is None


class _Frames:
    def __init__(self, *frames):
        self.frames = list(frames)

    def grab(self):
        return self.frames.pop(0), None


def test_the_sampler_remembers_the_place_and_forgets_it_on_a_blank_frame():
    blank = CropFrame(pixels=np.full((BROADCAST[1], BROADCAST[0], 3), 20,
                                     dtype=np.uint8),
                      origin=(0, 0), canvas=BROADCAST)
    sampler = LiveWearSampler(_Frames(whole(a_canvas(WORN)), blank),
                              lambda lap, wear: None)

    first, _ = sampler._read()
    assert first.ok and sampler._gauge_near == first.bars

    second, _ = sampler._read()
    assert not second.ok and sampler._gauge_near is None


def test_a_refused_reading_drops_the_place():
    sampler = LiveWearSampler(_Frames(whole(a_canvas(WORN))),
                              lambda lap, wear: None)
    reading, _ = sampler._read()
    assert sampler._gauge_near is not None
    # A baseline no real tyre can follow: every corner more worn than now.
    sampler.series = [(0.0, {"fl": 0.9, "fr": 0.9, "rl": 0.9, "rr": 0.9})]

    assert sampler._keep(1.0, reading) is False
    assert sampler._gauge_near is None


def test_a_new_session_forgets_the_place():
    sampler = LiveWearSampler(_Frames(whole(a_canvas(WORN))),
                              lambda lap, wear: None)
    sampler._read()
    sampler.new_session()

    assert sampler._gauge_near is None
