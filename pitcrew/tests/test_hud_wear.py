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
    CropFrame,
    LiveWearSampler,
    Reading,
    ScreenSource,
    layout_bounds,
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
        # Set the moment `grab` is entered, BEFORE it waits on the gate. A
        # test that wants a grab held open has to know one has actually
        # started, or it is racing the worker thread rather than controlling
        # it - see `test_the_queue_holds_one_lap_and_drops_the_older_request`.
        self.entered = threading.Event()

    def grab(self):
        self.entered.set()
        # Generous rather than tight: this is a fake, so the bound only has to
        # stop a genuinely broken test hanging for ever. At two seconds it was
        # short enough that a loaded machine could time it out and let a grab
        # through that the test believed it was holding.
        self.gate.wait(timeout=30.0)
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
    """A wear figure filed against the wrong lap is worse than a gap.

    **Made deterministic 23 Aug 2026.** It used to request all four laps and
    then accept either outcome - `4 in written or written == [1]` - because
    which of them happened depended on whether the worker had picked up the
    first lap before the rest were queued. That is a disjunction over timing,
    not an assertion, and it failed once under full-suite load having passed
    twenty isolated runs and twelve under twelve-way CPU load. A test whose
    answer depends on the scheduler cannot be debugged, only re-run.

    The order is now imposed rather than hoped for: the first lap is
    requested, the worker is WAITED FOR until it is actually inside `grab`,
    and only then do the other three queue behind it. The contract being
    tested is unchanged - one in flight, at most one queued, and the one kept
    is the NEWEST - but there is now exactly one thing that can happen.
    """
    png = a_canvas({"fl": 0.3, "fr": 0.3, "rl": 0.5, "rr": 0.4})
    source = FakeSource((png, None))
    source.gate.clear()                      # hold the first grab open
    written = []
    sampler = LiveWearSampler(source, lambda lap, wear: written.append(lap))
    sampler.start()
    try:
        sampler.request(1)
        assert source.entered.wait(timeout=5.0), (
            "the worker never reached the first grab, so nothing was in "
            "flight and this test would prove nothing")
        # Now these three can only queue behind the one being held.
        for lap in (2, 3, 4):
            sampler.request(lap)
        source.gate.set()
        drain(sampler, written, 2)
        time.sleep(0.2)
    finally:
        sampler.stop()
    # One in flight, then the NEWEST of the three that queued behind it -
    # never 2, never 3, never all four.
    assert written == [1, 4], (
        f"expected the held lap and then the newest queued one, got {written}")


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


# --------------------------------------------------- the gauge that moves

def a_moved_canvas(worn: dict[str, float], at: tuple[int, int],
                   bar: tuple[int, int] = (9, 18)) -> bytes:
    """The VR case: the same four bars, somewhere else, and smaller.

    GT7 draws the HUD on the car's dashboard in 3D there, so it translates with
    head position - measured at about 200 px across one recording - and the
    bars are 18-20 px rather than 30.
    """
    import io

    import numpy as np
    from PIL import Image

    frame = np.zeros((CANVAS[1], CANVAS[0], 3), dtype=np.uint8)
    frame[:] = 18
    width, height = bar
    x, y = at
    for index, corner in enumerate(("fl", "rl", "fr", "rr")):
        bx = x + (0 if corner in ("fl", "rl") else 60)
        by = y + (0 if corner in ("fl", "fr") else height + 8)
        red_rows = round(worn.get(corner, 0.0) * height)
        frame[by:by + red_rows, bx:bx + width] = (170, 25, 25)
        frame[by + red_rows:by + height, bx:bx + width] = (215, 215, 215)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_gauge_that_moved_is_found_and_read():
    """Measured on the real recording: 21% of VR driving frames read. That is
    low and it is enough - the design fits a slope across a stint rather than
    trusting any single reading, and a missed frame costs one screenshot."""
    got = read_gauge(a_moved_canvas(
        {"fl": 0.35, "fr": 0.22, "rl": 0.5, "rr": 0.3}, at=(1380, 400)))
    assert got.ok
    assert got.wear["rl"] > got.wear["fl"] > got.wear["fr"]


def test_the_same_gauge_is_found_somewhere_else_entirely():
    """The whole point: a fixed rectangle tracks nothing when the panel moves
    with his head."""
    first = read_gauge(a_moved_canvas({"fl": 0.4, "fr": 0.4, "rl": 0.4,
                                       "rr": 0.4}, at=(1240, 360)))
    second = read_gauge(a_moved_canvas({"fl": 0.4, "fr": 0.4, "rl": 0.4,
                                        "rr": 0.4}, at=(1450, 455)))
    assert first.ok and second.ok
    assert first.wear["fl"] == pytest.approx(second.wear["fl"], abs=0.06)


def test_a_located_reading_says_how_coarse_it_is():
    """One pixel of an 18 px bar is 5.6% of tyre life - about a lap at Monza.
    A number that coarse must not travel without saying so."""
    got = read_gauge(a_moved_canvas(
        {"fl": 0.35, "fr": 0.22, "rl": 0.5, "rr": 0.3}, at=(1380, 400)))
    assert got.ok and got.reason
    assert "one pixel is" in got.reason and "slope" in got.reason


def test_an_empty_frame_still_reports_dimmed_rather_than_locating_noise():
    """The locator must not turn a dark frame into a reading."""
    import io

    import numpy as np
    from PIL import Image

    frame = np.zeros((CANVAS[1], CANVAS[0], 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")
    got = read_gauge(buffer.getvalue())
    assert not got.ok and "dimmed" in got.reason


# ------------------------------------------------- the screen source, cropped
#
# The cheap path: `mss` copies only the gauge rectangle off an OBS projector
# window, so there is no canvas to count pixels of. The geometry is therefore
# verified where it is cut - the source measures the projector client area and
# carries it - and these are the tests that the refusal survived the move.


def a_crop(worn: dict[str, float], *, dim: float = 1.0,
           canvas: tuple[int, int] = CANVAS,
           pad: int = 0) -> CropFrame:
    """The gauge rectangle alone, as a source that cropped at capture returns."""
    x0, y0, x1, y1 = layout_bounds(LAYOUT_1720x916)
    x0, y0 = x0 - pad, y0 - pad
    frame = np.zeros((y1 - y0 + 1, x1 - x0 + 1, 3), dtype=np.uint8)
    frame[:] = 20
    for corner, (bx0, bx1, by0, by1) in LAYOUT_1720x916.items():
        rows = by1 - by0 + 1
        red_rows = round(worn.get(corner, 0.0) * rows)
        frame[by0 - y0:by0 - y0 + red_rows, bx0 - x0:bx1 - x0 + 1] = (200, 20, 20)
        frame[by0 - y0 + red_rows:by1 - y0 + 1, bx0 - x0:bx1 - x0 + 1] = (250,) * 3
    return CropFrame(pixels=(frame * dim).astype(np.uint8),
                     origin=(x0, y0), canvas=canvas)


def test_a_crop_reads_the_same_numbers_as_the_whole_canvas():
    """The point of the cheap path: identical transcription, 1/500th the cost.

    If these ever diverge the saving is worthless, because the verified figure
    is the one the full canvas produced.
    """
    worn = {"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}
    whole = read_gauge(a_canvas(worn))
    cropped = read_gauge(a_crop(worn))
    assert cropped.ok
    assert cropped.wear == whole.wear


def test_a_crop_from_the_wrong_canvas_is_refused():
    """Same refusal as a full frame of the wrong size, made one step earlier:
    a projector at another scale moves every calibrated pixel."""
    got = read_gauge(a_crop({"fl": 0.4}, canvas=(1920, 1080)))
    assert not got.ok and "1920x1080" in got.reason


def test_a_crop_that_misses_the_gauge_is_refused_not_read_partially():
    """A bar clipped at the edge reads as a bar short of white - which is a
    confident wrong number, the one failure mode that matters."""
    good = a_crop({"fl": 0.4})
    short = CropFrame(pixels=good.pixels[:, :10], origin=good.origin,
                      canvas=good.canvas)
    got = read_gauge(short)
    assert not got.ok and "does not contain the gauge" in got.reason


def test_a_crop_offset_by_padding_still_reads():
    """The origin is what translates the layout, so a source that grabbed a
    looser rectangle is still read correctly."""
    got = read_gauge(a_crop({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4}, pad=6))
    assert got.ok
    assert got.wear["rl"] == pytest.approx(0.6, abs=0.034)


def test_a_dimmed_crop_is_refused_and_not_searched():
    """The VR locator needs a whole canvas. On a crop there is nowhere to look,
    so the dim verdict must stand rather than the locator finding noise."""
    got = read_gauge(a_crop({"fl": 0.4}, dim=0.54))
    assert not got.ok and "dimmed" in got.reason


def test_the_screen_source_says_why_rather_than_raising():
    """No projector open is the normal state when OBS is shut. It is a reason,
    not an exception, because the caller is a worker beside a lap handler."""
    frame, why = ScreenSource().grab()
    assert frame is None
    assert why and isinstance(why, str)


# ---------------------------------------------------------- free-running
#
# With a cheap source the worker samples between crossings, and a crossing
# files the last reading taken before it - the rule `read_hud_wear.py::attach`
# already applies to a recorded race.


def test_a_crossing_files_the_held_reading_without_grabbing_again():
    written = []
    png = a_canvas({"fl": 0.3, "fr": 0.3, "rl": 0.5, "rr": 0.4})
    source = FakeSource((png, None))
    sampler = LiveWearSampler(source, lambda lap, wear: written.append((lap, wear)),
                              interval_s=0.05)
    sampler.start()
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and not sampler.series:
            time.sleep(0.01)
        assert sampler.series, "the worker never sampled on its own"
        before = source.calls
        sampler.request(11)
        drain(sampler, written, 1)
    finally:
        sampler.stop()
    assert len(written) == 1 and written[0][0] == 11
    # The crossing itself grabbed nothing: the held reading was the lap's.
    assert source.calls == before


def test_a_dimmed_frame_at_the_crossing_no_longer_costs_the_lap():
    """The reason for free-running at all. A pause or a transition on the line
    used to lose the reading; now the sample from a moment earlier stands."""
    written = []
    good = a_canvas({"fl": 0.3, "fr": 0.3, "rl": 0.5, "rr": 0.4})
    source = FakeSource((good, None))
    sampler = LiveWearSampler(source, lambda lap, wear: written.append((lap, wear)),
                              interval_s=0.05)
    sampler.start()
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and not sampler.series:
            time.sleep(0.01)
        # Everything from here on is dimmed and unreadable.
        source.results = [(a_canvas({"fl": 0.3}, dim=0.54), None)]
        source.calls = 0
        sampler.request(12)
        drain(sampler, written, 1)
    finally:
        sampler.stop()
    assert len(written) == 1
    assert written[0][1]["rl"] == pytest.approx(0.5, abs=0.034)


def test_free_run_failures_do_not_stand_the_session_down():
    """A projector shut for a minute is not the same event as the gauge being
    unreadable at the line, and only the second should end the session."""
    sampler = LiveWearSampler(FakeSource((None, "no projector window is open")),
                              lambda lap, wear: None, interval_s=0.01)
    sampler.start()
    try:
        time.sleep(0.4)          # dozens of free-run attempts
        assert not sampler.stood_down
    finally:
        sampler.stop()


def test_a_crossing_failure_still_stands_the_session_down():
    sampler = LiveWearSampler(FakeSource((None, "no projector window is open")),
                              lambda lap, wear: None, interval_s=0.01)
    sampler.start()
    try:
        for lap in range(8):
            sampler.request(lap)
            time.sleep(0.05)
        deadline = time.time() + 2.0
        while time.time() < deadline and not sampler.stood_down:
            time.sleep(0.01)
    finally:
        sampler.stop()
    assert sampler.stood_down


def test_a_fresh_set_cuts_the_series():
    """The gauge only goes backwards for one reason, and a slope fitted across
    a tyre change describes neither set."""
    worn = a_canvas({"fl": 0.6, "fr": 0.6, "rl": 0.7, "rr": 0.7})
    fresh = a_canvas({c: 0.0 for c in LAYOUT_1720x916})
    source = FakeSource((worn, None))
    sampler = LiveWearSampler(source, lambda lap, wear: None, interval_s=0.02)
    sampler.start()
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and len(sampler.series) < 2:
            time.sleep(0.01)
        assert len(sampler.series) >= 2
        source.results = [(fresh, None)]
        deadline = time.time() + 2.0
        while time.time() < deadline and len(sampler.series) != 1:
            time.sleep(0.01)
    finally:
        sampler.stop()
    assert len(sampler.series) == 1
    assert all(v == 0.0 for v in sampler.series[0][1].values())


def test_interval_zero_keeps_the_original_behaviour():
    """Nothing is sampled until a crossing asks. The default, and the one the
    OBS source must keep: a free-running websocket grab is unaffordable."""
    source = FakeSource((a_canvas({"fl": 0.3}), None))
    sampler = LiveWearSampler(source, lambda lap, wear: None)
    sampler.start()
    try:
        time.sleep(0.3)
        assert source.calls == 0
        assert sampler.series == []
    finally:
        sampler.stop()
