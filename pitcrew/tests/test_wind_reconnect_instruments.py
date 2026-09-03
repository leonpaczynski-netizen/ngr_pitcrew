"""What the wind layer says across a reconnect, which is where it was blind.

Between 30 Aug and 3 Sep 2026 the CH340 link was torn down and rebuilt 106
times. Every counter the health line reported was copied from the current
link, so it restarted at zero each time and read `resyncs 1 · stale 3 ·
timeouts 0` through all of them. The acknowledgement gap was copied from the
link and then measured, so an acknowledged frame always read as a gap of
nothing and the new link's `None` erased the old link's last acknowledgement:
the one interval that could have zeroed the fans - the reconnect - was the
one interval it could not see. And whether a reconnect beat the firmware's
deadman had to be recovered afterwards by subtracting timestamps by hand.

These pin the three repairs. Nothing here claims a fan turned.
"""
from __future__ import annotations

import logging
import time

import pytest

from pitcrew.rig import wind
from pitcrew.tests.test_wind_instrumentation import a_link

pytest.importorskip("serial")


def _sim_with_acked_link(monkeypatch):
    sim = wind.WindSim()
    sim._link = a_link(monkeypatch, "acked")
    sim.state.connected = True
    sim.state.port = "COM-TEST"
    return sim


def test_counters_accumulate_across_a_reconnect(monkeypatch):
    sim = _sim_with_acked_link(monkeypatch)
    assert sim._send_once() is True
    assert sim._send_once() is True
    sim._link.resyncs = 1
    sim._link.write_timeouts = 2
    sim._link.stale_bytes = 3
    assert sim._send_once() is True
    assert sim.state.frames_accepted == 3

    sim._drop_link(graceful=False)
    sim._link = a_link(monkeypatch, "acked")
    assert sim._send_once() is True

    # The session, not the newest link: three acks then one, not one.
    assert sim.state.frames_accepted == 4
    assert sim.state.resyncs == 1
    assert sim.state.write_timeouts == 2
    assert sim.state.stale_bytes == 3


def test_the_gap_spans_the_reconnect(monkeypatch, caplog):
    """The old link's last acknowledgement is the reference until the new
    link produces one, and the interval that closes is what is reported."""
    sim = _sim_with_acked_link(monkeypatch)
    assert sim._send_once() is True
    # Pretend the last acknowledgement was 2.5 s ago, then lose the link.
    sim.state.last_ack_at = time.monotonic() - 2.5
    sim._drop_link(graceful=False)
    sim._link = a_link(monkeypatch, "acked")

    with caplog.at_level(logging.WARNING, logger="pitcrew.wind"):
        assert sim._send_once() is True

    assert 2.4 < sim.state.max_ack_gap_s < 3.5
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "between acknowledgements" in said
    assert "zeroed the fans" in said


def test_an_acknowledged_frame_measures_the_interval_it_closes(monkeypatch):
    """Not zero. Copying the link's timestamp before measuring made every
    acknowledged frame read as a gap of nothing."""
    sim = _sim_with_acked_link(monkeypatch)
    assert sim._send_once() is True
    first = sim.state.last_ack_at
    time.sleep(0.05)
    assert sim._send_once() is True
    assert sim.state.last_ack_at > first
    assert 0.04 < sim.state.max_ack_gap_s < 1.0


def test_no_gap_before_the_first_acknowledgement_of_a_session(monkeypatch):
    sim = _sim_with_acked_link(monkeypatch)
    assert sim.state.last_ack_at is None
    assert sim._send_once() is True
    # The first acknowledgement has nothing to measure against.
    assert sim.state.max_ack_gap_s == 0.0


def _stub_discovery(monkeypatch):
    """Drive `_connect` past discovery and handshake without a port.

    The class stays the class: `_port_is_held_by_us` reads a class attribute
    off `WindLink`, so replacing it with a factory breaks the connect path
    this exists to test.
    """
    monkeypatch.setattr(wind, "find_port", lambda: "COM-TEST")
    monkeypatch.setattr(wind.WindLink, "open", lambda self, settle=True: None)
    monkeypatch.setattr(wind.WindLink, "handshake", lambda self: True)
    # The count query is a real exchange with the board and has its own
    # tests; here there is no port for it.
    monkeypatch.setattr(wind.WindLink, "discover_channels",
                        lambda self, default: default)


def _reconnect(monkeypatch, sim, down_s):
    _stub_discovery(monkeypatch)
    sim.state.last_drop_at = time.monotonic() - down_s
    return sim._connect(settle=False)


def test_a_quick_reconnect_is_said_to_be_inside_the_deadman(monkeypatch, caplog):
    sim = wind.WindSim()
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert _reconnect(monkeypatch, sim, down_s=0.13) is True
    said = [r for r in caplog.records if "back on COM-TEST" in r.getMessage()]
    assert len(said) == 1
    assert said[0].levelno == logging.INFO
    assert "inside the firmware's 1.0s deadman" in said[0].getMessage()


def test_a_slow_reconnect_says_how_long_the_fans_were_zeroed(monkeypatch, caplog):
    sim = wind.WindSim()
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert _reconnect(monkeypatch, sim, down_s=1.74) is True
    said = [r for r in caplog.records if "back on COM-TEST" in r.getMessage()]
    assert len(said) == 1
    assert said[0].levelno == logging.WARNING
    assert "at least 0.7" in said[0].getMessage()


def test_a_first_connect_is_not_a_reconnect(monkeypatch, caplog):
    sim = wind.WindSim()
    _stub_discovery(monkeypatch)
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert sim._connect(settle=False) is True
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "wind simulator ready on COM-TEST" in said
    assert "back on" not in said


def test_the_rate_is_twenty_hertz():
    """60 Hz cost 106 hard link losses in 4.2 running hours against one in
    the 10.3 before it. This is the number the prediction is made against."""
    assert wind.SEND_INTERVAL_S == pytest.approx(0.05)


def test_the_frame_log_holds_a_session():
    """At the main log's 2 MB the frame log rolled every five minutes and had
    lost the evening's drops before it was opened."""
    from pitcrew import diagnostics

    hours = diagnostics.FRAME_MAX_BYTES * (diagnostics.FRAME_BACKUPS + 1)
    hours /= 115 * 20 * 3600            # ~115 bytes a line at 20 Hz
    assert hours > 6.0
