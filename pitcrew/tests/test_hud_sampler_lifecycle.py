"""Stopping the gauge reader must actually stop it, and starting must not undo that.

30 Aug 2026, practice at the Red Bull Ring. The app died with a Windows access
violation and **13 live `hud-wear` threads**, one built at every lap crossing,
because `HudSession.sampler` cached to `self._sampler` and read back
`getattr(self, "_hud", None)` - a name that never existed, so the `getattr`
default returned None instead of raising and every crossing built a new reader.
The haptics frame clock, which is a GIL-starvation proxy, held 48000 Hz flat to
seven threads and collapsed to 29987 Hz at thirteen.

That was one bug. **This file covers the second one underneath it**, which the
first had kept unreachable by never calling `stop` at all:

    def stop(self):
        self._stop.set()
        thread, self._thread = self._thread, None   # dropped either way
        thread.join(timeout=2.0)                    # an OBS grab is ~2050 ms

    def start(self):
        if self._thread is not None: return         # now None, so carry on
        self._stop.clear()                          # <- un-kills the survivor

A join that timed out dropped a thread that was still running, and the next
`start` cleared the very flag that thread was about to read. One live reader
became two, sharing one unlocked `series` and `_latest`. Same failure as the
crash, arriving one session boundary at a time rather than one lap at a time -
practice then a race is all it takes.

The fix is an event per thread, so nothing `start` does can reach a departing
one.
"""
from __future__ import annotations

import pytest

from pitcrew.telemetry import hud
from pitcrew.telemetry.hud import LiveWearSampler

from .test_hud_wear import FakeSource, a_canvas


@pytest.fixture
def impatient(monkeypatch):
    """Time the join out in a tenth of a second instead of two."""
    monkeypatch.setattr(hud, "STOP_JOIN_S", 0.1, raising=False)


def held_open(*results):
    source = FakeSource(*results)
    source.gate.clear()
    return source


def test_a_stop_that_times_out_does_not_leave_a_thread_that_start_revives(impatient):
    source = held_open((None, "unused"))
    sampler = LiveWearSampler(source, lambda lap, wear: None)
    sampler.start()
    first = sampler._thread
    try:
        sampler.request(1)
        assert source.entered.wait(timeout=5.0), (
            "the reader never reached the grab, so nothing was in flight and "
            "this test would prove nothing")

        # It is inside a grab it cannot leave, so it cannot have stopped.
        stopped = sampler.stop()

        sampler.start()
        second = sampler._thread
        assert second is not first, "start reused the thread it had released"

        source.gate.set()                        # let the held grab return
        first.join(timeout=5.0)
        assert not first.is_alive(), (
            "the reader `stop` gave up on was brought back to life by the "
            "next `start`, which cleared the stop flag out from under it. "
            "Two readers now share one unlocked `series` and `_latest` - the "
            "30 Aug crash, one session boundary at a time.")
        assert second.is_alive(), "the replacement reader is not running"
        # And `stop` must not have claimed a success it did not achieve.
        assert stopped is False
    finally:
        source.gate.set()
        sampler.stop()


def test_a_reader_stopped_mid_grab_files_nothing(impatient):
    """A grab that outlived its session may not be written against a lap.

    `_read` blocks about two seconds on OBS, so a reader asked to stop part way
    through still comes back holding a frame - of the session that has just
    ended. Filing it is the stale-state failure CLAUDE.md rule 11 exists for,
    and the one that put practice's tyres into the Fuji race.
    """
    png = a_canvas({"fl": 0.3, "fr": 0.3, "rl": 0.5, "rr": 0.4})
    source = held_open((png, None))
    written = []
    sampler = LiveWearSampler(source, lambda lap, wear: written.append(lap))
    sampler.start()
    worker = sampler._thread
    try:
        sampler.request(1)
        assert source.entered.wait(timeout=5.0)
        stopped = sampler.stop()

        source.gate.set()                        # the frame arrives too late
        worker.join(timeout=5.0)
        assert not worker.is_alive()
        assert written == [], (
            f"lap {written} was filed by a reader that had already been "
            "stopped, so a reading belongs to the session before this one")
        assert stopped is False
    finally:
        source.gate.set()
        sampler.stop()


def test_repeated_stop_and_start_does_not_accumulate_readers(impatient):
    """The shape of the crash: threads that outlive every attempt to stop them."""
    source = held_open((None, "unused"))
    sampler = LiveWearSampler(source, lambda lap, wear: None)
    survivors = []
    try:
        for _ in range(5):
            sampler.start()
            survivors.append(sampler._thread)
            sampler.request(1)
            assert source.entered.wait(timeout=5.0)
            source.entered.clear()
            sampler.stop()
    finally:
        source.gate.set()
        sampler.stop()
    for thread in survivors:
        thread.join(timeout=5.0)
    alive = [t for t in survivors if t.is_alive()]
    assert not alive, (
        f"{len(alive)} of {len(survivors)} readers were still running after "
        "being stopped; this is how 13 of them were alive at the crash")


def test_stop_reports_success_when_the_reader_really_did_stop():
    """The False above has to mean something, so the True has to be reachable."""
    sampler = LiveWearSampler(FakeSource((None, "unused")),
                              lambda lap, wear: None)
    sampler.start()
    assert sampler.stop() is True
    assert sampler.stop() is True, "stopping an already-stopped reader is fine"
