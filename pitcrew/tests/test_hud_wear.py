"""The live gauge reader, and the failures it must survive quietly."""
from __future__ import annotations

import io
import threading
import time

import numpy as np
import pytest
from PIL import Image

import sys
import types

from pitcrew.telemetry import hud
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


def test_the_constants_are_never_rescaled_onto_another_canvas():
    """The rule that has not changed: the calibrated positions are pixel
    positions and are never stretched onto a different geometry, because a
    confident reading of the wrong rectangle is the failure this module exists
    to avoid.

    **What changed is the answer when the canvas differs.** It used to refuse
    outright, which made 1720x916 a hard requirement of the whole capture
    chain - and that number is not a property of the game, it is an OBS canvas
    someone picked. The gauge is now LOCATED instead. Here it is drawn at the
    916 coordinates inside an 1080 frame, so the fixed layout would read trim;
    the locator finds the real bars and reads those.
    """
    got = read_gauge(a_canvas({"fl": 0.4, "fr": 0.2, "rl": 0.6, "rr": 0.4},
                              size=(1920, 1080)))

    assert got.ok, got.reason
    assert got.wear["rl"] > got.wear["fl"] > got.wear["fr"]


def test_a_different_canvas_with_no_gauge_is_still_refused():
    """Locating is not guessing. Nothing that looks like the gauge means no
    reading, on any canvas."""
    import numpy as np
    from PIL import Image as _Image

    blank = np.full((1080, 1920, 3), 20, dtype=np.uint8)
    buf = io.BytesIO()
    _Image.fromarray(blank).save(buf, format="PNG")

    got = read_gauge(buf.getvalue())

    assert not got.ok
    assert "could not be found" in got.reason


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


def test_the_screen_source_says_why_rather_than_raising(monkeypatch):
    """No projector open is the normal state when OBS is shut. It is a reason,
    not an exception, because the caller is a worker beside a lap handler.

    **The absence is faked, and it has to be.** This asserted against the
    developer's own desktop and so passed only where no OBS projector happened
    to be open - it began failing the moment one was, on the machine that
    actually races. A test whose verdict depends on what is on screen is not
    testing the code.
    """
    _install(monkeypatch, FakeWin32({1: ("OBS 32.2.2 - Profile", True,
                                         2560, 1369, 0, 0)}))
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


WAIT_UNDER_LOAD_S = 15.0


def test_a_fresh_set_cuts_the_series():
    """The gauge only goes backwards for one reason, and a slope fitted across
    a tyre change describes neither set."""
    worn = a_canvas({"fl": 0.6, "fr": 0.6, "rl": 0.7, "rr": 0.7})
    fresh = a_canvas({c: 0.0 for c in LAYOUT_1720x916})
    source = FakeSource((worn, None))
    sampler = LiveWearSampler(source, lambda lap, wear: None, interval_s=0.02)
    sampler.start()
    # The deadlines are how long a LOADED machine may take, not how long this
    # should take: each wait ends the moment its condition holds (~50 ms
    # alone). At 2 s it failed once under the full suite with one reading of
    # the two it wanted - the sampler thread starved, not the logic wrong.
    try:
        deadline = time.time() + WAIT_UNDER_LOAD_S
        while time.time() < deadline and len(sampler.series) < 2:
            time.sleep(0.01)
        assert len(sampler.series) >= 2
        source.results = [(fresh, None)]
        deadline = time.time() + WAIT_UNDER_LOAD_S
        # Cut on the SECOND fresh reading (7 Sep 2026): the series restarts
        # with both of them, never with one.
        while time.time() < deadline and not (
                sampler.series
                and all(v == 0.0 for v in sampler.series[0][1].values())):
            time.sleep(0.01)
    finally:
        sampler.stop()
    assert 2 <= len(sampler.series)
    assert all(v == 0.0 for _, wear in sampler.series for v in wear.values())


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


# --------------------------------------------------------------- coherence
#
# The pit-lane gauge, 24 Aug 2026. GT7 moves the tyre gauge to the bottom
# left of the screen while the car is in the pits, so the calibrated
# rectangle reads whatever the HUD put in its place. What comes back is
# plausible one corner at a time and impossible taken together.


def _kept(sampler, wear):
    """Offer a reading to the series. True if it was filed."""
    return sampler._keep(0.0, Reading(dict(wear)))


def a_sampler():
    return LiveWearSampler(FakeSource((None, "unused")),
                           lambda lap, wear: None)


def test_a_reading_that_moves_both_ways_is_refused():
    """Three corners fell and one rose. No tyre does that.

    This is the pit lap of session 78 verbatim, against the lap before it.
    """
    sampler = a_sampler()
    assert _kept(sampler, {"fl": 0.63, "fr": 0.37, "rl": 0.68, "rr": 0.55})
    assert not _kept(sampler, {"fl": 0.45, "fr": 0.45,
                               "rl": 0.32, "rr": 0.50})
    # **And the refusal did not become the baseline.** If it had, every
    # later reading would be judged against the relocated gauge and the
    # rest of the stint would read as incoherent too.
    assert sampler.series[-1][1]["rl"] == 0.68
    assert _kept(sampler, {"fl": 0.68, "fr": 0.39, "rl": 0.73, "rr": 0.58})


def test_every_corner_dropping_onto_a_worn_set_is_refused():
    """The crash lap: all four fell, and it still reads 42% worst.

    Too worn to be a fresh set, too low to follow the last reading. The
    worst-corner test could not tell this from a tyre change.
    """
    sampler = a_sampler()
    assert _kept(sampler, {"fl": 0.63, "fr": 0.37, "rl": 0.68, "rr": 0.55})
    assert not _kept(sampler, {"fl": 0.42, "fr": 0.25,
                               "rl": 0.39, "rr": 0.23})
    assert len(sampler.series) == 1


def test_a_real_tyre_change_still_cuts_the_series():
    """Session 52's stop: every corner back to a tenth or less."""
    sampler = a_sampler()
    assert _kept(sampler, {"fl": 0.77, "fr": 0.50, "rl": 0.87, "rr": 0.69})
    # The first fresh-shaped reading is held (an all-four-corners zero is a
    # documented locator failure); the second cuts the series, and both
    # readings start the new set.
    assert not _kept(sampler, {"fl": 0.07, "fr": 0.07, "rl": 0.10, "rr": 0.07})
    assert sampler._held_last
    assert len(sampler.series) == 1, "held, not cut - the old set stands"
    assert _kept(sampler, {"fl": 0.14, "fr": 0.07, "rl": 0.14, "rr": 0.13})
    assert len(sampler.series) == 2, "the series should have been cut"
    assert sampler.series[0][1]["fl"] == 0.07


def test_quantisation_alone_never_refuses_a_reading():
    """One gauge row is 3.3% of tyre life and a corner can sit either side.

    Session 78 lap 14 read FR one row BELOW lap 13 while the other three
    rose. That is the bar, not the tyre, and it must still be filed.
    """
    sampler = a_sampler()
    assert _kept(sampler, {"fl": 0.55, "fr": 0.38, "rl": 0.62, "rr": 0.52})
    assert _kept(sampler, {"fl": 0.63, "fr": 0.37, "rl": 0.68, "rr": 0.55})
    assert len(sampler.series) == 2


def test_the_known_good_race_is_accepted_end_to_end():
    """Session 52, all 25 readings, one stop. Nothing may be refused.

    The rule earns its place by rejecting two readings in a session where
    the driver could name what went wrong. It keeps it by touching nothing
    in the race that produced the wear rate the model still rests on.
    """
    stint = [(0.06, 0.00, 0.03, 0.00), (0.10, 0.07, 0.10, 0.07),
             (0.17, 0.07, 0.19, 0.13), (0.20, 0.13, 0.21, 0.19),
             (0.27, 0.17, 0.28, 0.21), (0.33, 0.20, 0.33, 0.27),
             (0.34, 0.23, 0.40, 0.33), (0.40, 0.27, 0.47, 0.34),
             (0.47, 0.30, 0.52, 0.40), (0.53, 0.33, 0.55, 0.47),
             (0.58, 0.39, 0.62, 0.52), (0.63, 0.40, 0.67, 0.53),
             (0.67, 0.41, 0.73, 0.60), (0.73, 0.47, 0.80, 0.67),
             (0.77, 0.50, 0.87, 0.69)]
    after = [(0.07, 0.07, 0.10, 0.07), (0.14, 0.07, 0.14, 0.13),
             (0.20, 0.13, 0.20, 0.19), (0.27, 0.19, 0.27, 0.21),
             (0.30, 0.20, 0.33, 0.27), (0.34, 0.26, 0.40, 0.33),
             (0.40, 0.27, 0.47, 0.37), (0.47, 0.33, 0.52, 0.41),
             (0.53, 0.33, 0.57, 0.47), (0.58, 0.40, 0.62, 0.53)]
    sampler = a_sampler()
    for fl, fr, rl, rr in stint + after:
        kept = _kept(sampler, {"fl": fl, "fr": fr, "rl": rl, "rr": rr})
        # The first reading after the stop is held for its second, which is
        # not a refusal: nothing is lost from the series.
        assert kept or sampler._held_last, (
            f"refused a reading from the race the model rests on: {fl, fr, rl, rr}")
    # The stop cut the series, so only the second stint is left in it - all
    # of it, the held reading included.
    assert len(sampler.series) == len(after)


# ------------------------------------------------------- sizing the projector
#
# `ScreenSource` refuses a projector that is not the canvas to the pixel, and
# a projector does not survive a restart - so sizing one is a job for before
# every session, against a figure the driver cannot see while he drags. These
# drive the win32 calls through a fake, because the imports are function-local.


class FakeWin32:
    """Just enough of win32gui to place, measure and resize a window."""

    def __init__(self, windows, chrome=(16, 39), resizable=True):
        # windows: {hwnd: (title, visible, client_w, client_h, x, y)}
        self.windows = dict(windows)
        self.chrome = chrome
        self.resizable = resizable
        self.calls = []
        self.topmost = False

    def EnumWindows(self, visit, _):
        for hwnd in list(self.windows):
            visit(hwnd, None)

    def IsWindowVisible(self, hwnd):
        return self.windows[hwnd][1]

    def GetWindowText(self, hwnd):
        return self.windows[hwnd][0]

    def GetClientRect(self, hwnd):
        _, _, w, h, _, _ = self.windows[hwnd]
        return (0, 0, w, h)

    def GetWindowRect(self, hwnd):
        _, _, w, h, x, y = self.windows[hwnd]
        cw, ch = self.chrome
        return (x, y, x + w + cw, y + h + ch)

    def ClientToScreen(self, hwnd, point):
        _, _, _, _, x, y = self.windows[hwnd]
        return (x + point[0], y + point[1])

    def SetWindowPos(self, hwnd, z, x, y, w, h, _flags):
        self.calls.append((x, y, w, h))
        if z == -1:                              # HWND_TOPMOST
            self.topmost = True
        if not self.resizable:
            return
        title, vis, _, _, _, _ = self.windows[hwnd]
        cw, ch = self.chrome
        self.windows[hwnd] = (title, vis, w - cw, h - ch, x, y)


def _install(monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "win32gui", fake)
    monkeypatch.setitem(sys.modules, "win32con", types.SimpleNamespace(
        SWP_NOZORDER=4, SWP_NOACTIVATE=16, SWP_NOMOVE=2, SWP_NOSIZE=1,
        HWND_TOPMOST=-1))


def test_the_program_projector_wins_when_both_are_open(monkeypatch):
    """A preview projector can be showing a different scene entirely."""
    fake = FakeWin32({1: ("Projector - Preview", True, 480, 270, 0, 0),
                      2: ("Windowed Projector (Program)", True, 480, 270, 0, 0)})
    _install(monkeypatch, fake)
    found, why = hud.find_projector()
    assert why is None
    assert found[1] == "Windowed Projector (Program)"


def test_no_projector_says_how_to_open_one(monkeypatch):
    """The message has to name the menu item, not just the fault."""
    _install(monkeypatch, FakeWin32({1: ("OBS 32.2.2 - Profile", True,
                                         2560, 1369, 0, 0)}))
    found, why = hud.find_projector()
    assert found is None
    assert "Windowed Projector" in why
    # **The size named is the one the sizer would set** - the console's own
    # 1080p, not the calibrated canvas. Telling him to make a 1720x916 window
    # is telling him to make the one that read nothing all night.
    assert f"{hud.SNAP_CANVAS[0]}x{hud.SNAP_CANVAS[1]}" in why


def test_snap_sizes_the_client_area_and_leaves_it_where_it_was(monkeypatch):
    """The chrome is measured, not assumed, and the position is not ours."""
    fake = FakeWin32({1: ("Projector - Preview", True, 1184, 661, 2668, 51)},
                     chrome=(16, 39))
    _install(monkeypatch, fake)
    ok, said = hud.snap_projector()
    assert ok, said
    # Outer size asked for = canvas + the chrome this window actually has.
    assert fake.calls == [(2668, 51, hud.SNAP_CANVAS[0] + 16,
                           hud.SNAP_CANVAS[1] + 39)]
    assert fake.GetClientRect(1)[2:] == hud.SNAP_CANVAS
    assert "1184x661" in said and "left where it was" in said


def test_snap_is_idempotent_and_says_so(monkeypatch):
    """Pressing it twice must not read as having done something twice."""
    fake = FakeWin32({1: ("Projector - Preview", True,
                          hud.SNAP_CANVAS[0], hud.SNAP_CANVAS[1], 0, 0)})
    _install(monkeypatch, fake)
    ok, said = hud.snap_projector()
    assert ok
    assert "already" in said
    # **It is still raised.** The stint that went dark had a correctly sized
    # projector the whole time and was simply underneath something, so
    # "already the right size" must not mean "nothing to do".
    assert fake.calls == [(0, 0, 0, 0)], (
        "an already-sized projector must still be brought to the front")


def test_a_projector_that_will_not_resize_is_reported_not_assumed(monkeypatch):
    """A fullscreen projector ignores SetWindowPos. Saying 'done' would lie.

    This is the exact case that turned up in the field: the driver opened a
    Fullscreen Projector, it took the whole 2560x1440 monitor, and the reader
    refused every grab.
    """
    fake = FakeWin32({1: ("Projector - Preview", True, 2560, 1440, 0, 0)},
                     resizable=False)
    _install(monkeypatch, fake)
    ok, said = hud.snap_projector()
    assert not ok
    assert "2560x1440" in said
    assert "Windowed Projector" in said


def test_the_reader_and_the_sizer_agree_on_which_window(monkeypatch):
    """One matcher. Two would drift the next time OBS renames them."""
    fake = FakeWin32({1: ("Projector - Preview", True, 480, 270, 0, 0)})
    _install(monkeypatch, fake)
    assert hud.ScreenSource()._window()[0] == hud.find_projector()[0]


def test_the_projector_is_brought_to_the_front(monkeypatch):
    """Sizing it correctly and leaving it buried is no better than not
    opening it.

    24 Aug 2026: a six-minute stint sampled every two seconds and every
    single grab came back dark. The projector was the right size the whole
    time - it was behind another window, and this source reads what the
    MONITOR shows, so the capture was of that other window. The log could
    only say "the frame is dimmed".
    """
    fake = FakeWin32({1: ("Projector - Preview", True, 1184, 661, 0, 0)})
    _install(monkeypatch, fake)
    ok, said = hud.snap_projector()
    assert ok
    assert "cover" in said, "the message must say why it is in front"
    assert fake.topmost, "the projector was resized but left where it could be buried"
