"""The live gauge reader, and the failures it must survive quietly."""
from __future__ import annotations

import io
import threading
import time

import numpy as np
import pytest
from PIL import Image

from pitcrew.telemetry.hud import (
    CANVAS,
    LAYOUT_1720x916,
    LiveWearSampler,
    Reading,
    read_gauge,
)


def a_canvas(worn: dict[str, float], *, dim: float = 1.0,
             size: tuple[int, int] = CANVAS) -> bytes:
    """A synthetic canvas with the gauge drawn at the calibrated coordinates.

    `dim` scales every channel, which is what GT7's pause overlay does - it is
    the difference between a frame that can be read and one that must not be.
    """
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    frame[:] = 20
    for corner, (x0, x1, y0, y1) in LAYOUT_1720x916.items():
        rows = y1 - y0 + 1
        red_rows = round(worn.get(corner, 0.0) * rows)
        frame[y0:y0 + red_rows, x0:x1 + 1] = (200, 20, 20)
        frame[y0 + red_rows:y1 + 1, x0:x1 + 1] = (250, 250, 250)
    frame = (frame * dim).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")
    return buffer.getvalue()


def test_it_reads_the_four_bars():
    got = read_gauge(a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}))
    assert got.ok
    # The bar is 30 px, so a reading is quantised to thirtieths - about 3.3
    # points. Anything tighter than that would be reading noise.
    assert got.wear["rl"] == pytest.approx(0.6, abs=0.034)
    assert got.wear["fr"] == pytest.approx(0.2, abs=0.034)
    assert got.wear["rl"] > got.wear["fl"] > got.wear["fr"]


def test_a_dimmed_frame_is_refused_rather_than_read():
    """The measured failure: a pause menu dims by ~45% and every bar peaks at
    137, where the reader needs 150 for white and 110 for red.

    It must refuse. Relaxing the thresholds to meet a dimmed frame would let
    one produce a number, and a wrong wear figure is far worse than a missing
    one.
    """
    got = read_gauge(a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4},
                              dim=0.54))
    assert not got.ok
    assert got.wear is None
    assert "dimmed" in got.reason


def test_a_fresh_set_reads_zero_and_not_null():
    """Zero worn is a real reading. Null is the absence of one."""
    got = read_gauge(a_canvas({c: 0.0 for c in LAYOUT_1720x916}))
    assert got.ok
    assert all(v == 0.0 for v in got.wear.values())


def test_the_wrong_canvas_is_refused_not_rescaled():
    """The constants are pixel positions; on another geometry they point
    somewhere else, and a confident reading of the wrong rectangle is exactly
    the failure this module exists to avoid."""
    got = read_gauge(a_canvas({"fl": 0.4}, size=(1920, 1080)))
    assert not got.ok and "1920x1080" in got.reason


def test_rubbish_bytes_do_not_raise():
    """The caller is a lap handler. The lap matters more than the gauge."""
    got = read_gauge(b"not a png")
    assert not got.ok and "decoded" in got.reason


# ------------------------------------------------------------- the sampler

class FakeSource:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0
        self.gate = threading.Event()
        self.gate.set()

    def grab(self):
        self.gate.wait(timeout=2.0)
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def drain(sampler, written, expected, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline and len(written) < expected:
        time.sleep(0.01)
    return written


def test_a_reading_reaches_the_store_off_the_calling_thread():
    written = []
    png = a_canvas({"fl": 0.3, "fr": 0.3, "rl": 0.5, "rr": 0.4})
    sampler = LiveWearSampler(FakeSource((png, None)),
                              lambda lap, wear: written.append((lap, wear)))
    sampler.start()
    try:
        sampler.request(7)
        drain(sampler, written, 1)
    finally:
        sampler.stop()
    assert len(written) == 1
    lap, wear = written[0]
    assert lap == 7 and wear["rl"] > wear["fl"]


def test_the_queue_holds_one_lap_and_drops_the_older_request():
    """A wear figure filed against the wrong lap is worse than a gap."""
    png = a_canvas({"fl": 0.3, "fr": 0.3, "rl": 0.5, "rr": 0.4})
    source = FakeSource((png, None))
    source.gate.clear()                      # hold the first grab open
    written = []
    sampler = LiveWearSampler(source, lambda lap, wear: written.append(lap))
    sampler.start()
    try:
        for lap in (1, 2, 3, 4):
            sampler.request(lap)
        source.gate.set()
        drain(sampler, written, 2)
        time.sleep(0.2)
    finally:
        sampler.stop()
    # One in flight plus at most one queued - never all four.
    assert len(written) <= 2
    assert 4 in written or written == [1]


def test_it_stands_down_rather_than_complain_every_lap():
    written = []
    sampler = LiveWearSampler(FakeSource((None, "OBS is not running")),
                              lambda lap, wear: written.append(lap))
    sampler.start()
    try:
        for lap in range(1, 9):
            sampler.request(lap)
            time.sleep(0.05)
        deadline = time.time() + 3.0
        while time.time() < deadline and not sampler.stood_down:
            time.sleep(0.02)
    finally:
        sampler.stop()
    assert sampler.stood_down
    assert not written


def test_a_dimmed_frame_does_not_count_toward_standing_down():
    """A paused game is normal. It is not a broken connection."""
    dim = a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}, dim=0.54)
    sampler = LiveWearSampler(FakeSource((dim, None)), lambda lap, wear: None)
    sampler.start()
    try:
        for lap in range(1, 9):
            sampler.request(lap)
            time.sleep(0.05)
        time.sleep(0.3)
    finally:
        sampler.stop()
    assert not sampler.stood_down


def test_requests_before_start_are_ignored_rather_than_queued():
    sampler = LiveWearSampler(FakeSource((None, "x")), lambda lap, wear: None)
    sampler.request(1)                       # must not raise
    sampler.stop()                           # nor must this
