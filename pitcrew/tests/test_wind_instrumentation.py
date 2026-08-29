"""What the wind layer can now say about itself, and what it still may not.

The driver reports fans that drop and come back on their own. Every counter
the app kept was compatible with that and said nothing: `frames_sent` counted
a write that timed out, `connected` only went False on a teardown, and
nothing anywhere had ever counted an acknowledgement. Twenty write timeouts
is **10.2 seconds**, about 8.75 of them with the fans zeroed by the firmware's
deadman, and the log said `connected: True` throughout.

These pin the instrumentation that closes that gap - and, just as hard, the
one claim it must never make. An acknowledgement proves the firmware parsed a
frame. There is no tachometer, no current sense and no back-channel from the
motor shield, so it proves nothing whatsoever about a motor turning. The
inference runs one way only.
"""
from __future__ import annotations

import time

import pytest

from pitcrew.rig import wind


class FakeReply:
    def __init__(self, acknowledged: bool) -> None:
        self.acknowledged = acknowledged

    def describe(self) -> str:
        return "rejected"


def a_link(monkeypatch, outcome="acked"):
    """A link whose write and read are stubbed to a chosen outcome."""
    link = wind.WindLink("COM-TEST")

    def write(_payload):
        if outcome == "timeout":
            raise _timeout()

    def read_reply():
        if outcome == "silent":
            return None
        return FakeReply(outcome != "rejected")

    monkeypatch.setattr(link, "_write", write)
    monkeypatch.setattr(link, "_read_reply", read_reply)
    monkeypatch.setattr(link, "_drain", lambda: 0)
    monkeypatch.setattr(link, "_abandon_stuck_write", lambda: None)
    return link


def _timeout():
    import serial

    return serial.SerialTimeoutException("Write timeout")


pytest.importorskip("serial")


# ------------------------------------------------------- the ACK accounting

def test_an_accepted_frame_is_counted_and_timed(monkeypatch):
    link = a_link(monkeypatch, "acked")
    assert link.acks == 0 and link.last_ack_at is None
    link.send((10, 10, 0, 0))
    assert link.acks == 1
    assert link.last_ack_at is not None
    assert link.last_outcome == "acked"


@pytest.mark.parametrize("outcome", ["timeout", "silent", "rejected"])
def test_a_frame_that_was_not_accepted_is_not_counted(monkeypatch, outcome):
    """Only an acknowledgement moves the counter the deadman is judged on."""
    link = a_link(monkeypatch, outcome)
    link.send((10, 10, 0, 0))
    assert link.acks == 0
    assert link.last_ack_at is None
    assert link.last_outcome == outcome


def test_a_timed_out_write_is_not_a_frame_sent(monkeypatch):
    """`frames_sent` read as delivery and measured intent - rule 3, in the
    counter the health report leads with."""
    sim = wind.WindSim()
    link = a_link(monkeypatch, "timeout")
    sim._link = link
    assert sim._send_once() is True          # a hiccup, link kept
    assert sim.state.frames_sent == 0
    assert sim.state.write_timeouts == 1


def test_an_accepted_frame_is_a_frame_sent(monkeypatch):
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    assert sim._send_once() is True
    assert sim.state.frames_sent == 1
    assert sim.state.frames_accepted == 1


# --------------------------------------------------- what it may NOT claim

def test_the_gap_is_none_before_the_first_acknowledgement():
    """Not 0.0. A zero would read as "answered just now", which is the exact
    opposite of "has never answered" - rule 3."""
    state = wind.WindState()
    assert state.deadman_gap_s() is None


def test_the_gap_is_measured_against_the_deadman():
    state = wind.WindState()
    state.last_ack_at = time.monotonic() - 2.5
    gap = state.deadman_gap_s()
    assert gap is not None and 2.4 < gap < 3.0
    assert gap > wind.DEADMAN_S


def test_nothing_claims_the_fans_are_running(monkeypatch):
    """**The condition the critic set.** Nothing on this side observes a fan.
    A healthy link is compatible with two dead fans, and the description must
    never say otherwise."""
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    sim.state.connected = True
    sim.state.port = "COM-TEST"
    sim._send_once()
    said = sim.state.describe().lower()
    for forbidden in ("fans are on", "fans are running", "fans live",
                      "fans turning", "fans are turning"):
        assert forbidden not in said, f"describe() claimed {forbidden!r}"
    assert "accepted" in said


def test_a_long_gap_is_reported_as_the_firmware_zeroing_the_fans():
    """The inference that IS sound, and the line that has been missing from
    every fan report the driver has made."""
    state = wind.WindState(connected=True, port="COM-TEST")
    state.max_ack_gap_s = 3.24
    said = state.describe()
    assert "3.2s without an acknowledgement" in said
    # 3.24 - 1.0 deadman = 2.24 s of dead fans, stated as such.
    assert "2.2s" in said


# ----------------------------------------------------------- the frame log

def test_every_frame_is_logged_with_its_outcome(monkeypatch, caplog):
    """Continuous, not a ring buffer dumped on an adverse event: the fault
    this exists to catch produces no adverse event at all."""
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    sim.set_output((120, 120, 0, 0),
                   context={"speed_kmh": 64.4, "on_track": True,
                            "paused": False})
    with caplog.at_level("INFO", logger="pitcrew.wind.frames"):
        sim._send_once()
    rows = [r.getMessage() for r in caplog.records]
    assert len(rows) == 1
    assert "duty=120,120,0,0" in rows[0]
    assert "outcome=acked" in rows[0]
    assert "speed=64.4" in rows[0]
    assert "on_track=True" in rows[0]


def test_an_unknown_speed_is_not_logged_as_zero(monkeypatch, caplog):
    """A stopped car and an unknown one need opposite readings."""
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    sim.set_output((120, 120, 0, 0))          # bench path: no car to describe
    with caplog.at_level("INFO", logger="pitcrew.wind.frames"):
        sim._send_once()
    said = caplog.records[0].getMessage()
    assert "speed=?" in said
    assert "speed=0" not in said


def test_the_frame_log_does_not_reach_the_main_log(tmp_path):
    """Four lines a second would roll `pitcrew.log` past its backups in an
    evening, and that history is what made this fault investigable."""
    from pitcrew import diagnostics

    frames = diagnostics.log("wind.frames")
    diagnostics._install_frame_log(tmp_path)
    try:
        assert frames.propagate is False
    finally:
        for handler in list(frames.handlers):
            frames.removeHandler(handler)
            handler.close()


# --------------------------------------------------------------- the marker

def test_a_driver_marker_lands_on_the_next_frame(monkeypatch, caplog):
    """The only channel carrying what no instrument here can see."""
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    sim.set_output((120, 120, 0, 0))
    sim.mark("ptt")
    with caplog.at_level("INFO", logger="pitcrew.wind.frames"):
        sim._send_once()
    assert "MARK=ptt" in caplog.records[0].getMessage()


def test_a_marker_is_stamped_once_and_not_repeated(monkeypatch, caplog):
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    sim.set_output((120, 120, 0, 0))
    sim.mark("ptt")
    with caplog.at_level("INFO", logger="pitcrew.wind.frames"):
        sim._send_once()
        sim._send_once()
    said = [r.getMessage() for r in caplog.records]
    assert "MARK=ptt" in said[0]
    assert "MARK" not in said[1]


def test_marking_needs_no_context(monkeypatch, caplog):
    """He can tap the button in the pits, in a menu, or mid-race."""
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    sim.mark("ptt")
    with caplog.at_level("INFO", logger="pitcrew.wind.frames"):
        sim._send_once()
    assert "MARK=ptt" in caplog.records[0].getMessage()
