"""The channel count comes from the board, is confirmed before it is used,
and never becomes a guess.

The reflash in `docs/WIND-SKETCH-REFLASH_2026-09-03.md` makes the board
declare two motors instead of four. The firmware reads exactly as many bytes
as it declared with no framing: a frame one byte too long leaves a byte over
that corrupts the next, one too short leaves the firmware waiting
mid-command, and both end with the deadman zeroing the fans - silently,
because the first frame of the wrong width is acknowledged. So the count is
asked for, parsed without trusting the parse, proved by three acknowledged
zero frames, and every vector sent is fitted to the width that was proved.

The reply format for the count query is not known from source. These pin the
parser's tolerance and, more importantly, that nothing acts on it unproved.
"""
from __future__ import annotations

import logging

import pytest

from pitcrew.rig import arq, wind
from pitcrew.tests.test_wind import FakeSerial, link_onto

pytest.importorskip("serial")


# ------------------------------------------------------------------ parsing

def test_a_raw_byte_count_is_read():
    assert arq.parse_motors_count(b"\x04Adafruit Motor Shield V2\n") == 4
    assert arq.parse_motors_count(b"\x02PWM fans") == 2


def test_an_ascii_digit_count_is_read():
    assert arq.parse_motors_count(b"4\nAdafruit") == 4
    assert arq.parse_motors_count(b"2") == 2


def test_nothing_is_none_not_zero():
    assert arq.parse_motors_count(b"") is None


def test_an_implausible_count_is_refused():
    """A byte over `MAX_CHANNELS` is the wrong byte, not a big rig."""
    assert arq.parse_motors_count(b"A") is None          # 0x41 = 65
    assert arq.parse_motors_count(bytes([arq.MAX_CHANNELS + 1])) is None
    assert arq.parse_motors_count(bytes([arq.MAX_CHANNELS])) == arq.MAX_CHANNELS


# ------------------------------------------------------------- a fake board

class CountingBoard(FakeSerial):
    """A board with a fixed motor count that behaves like the firmware:
    it acknowledges any well-formed frame, answers the count query with a
    raw byte and a name, and - the important part - reads exactly `motors`
    bytes from a set command, so a frame of the wrong width breaks the
    frame after it rather than itself."""

    def __init__(self, motors: int, *, answers_count: bool = True,
                 count_bytes: bytes | None = None) -> None:
        super().__init__(speaks=arq.DEFAULT_CRC)
        self.motors = motors
        self.answers_count = answers_count
        self.count_bytes = count_bytes
        self._leftover = 0          # bytes a too-long frame left behind
        self._starved = 0           # bytes a too-short frame still owes

    def write(self, data: bytes) -> int:
        # A previous frame of the wrong width poisons this one.
        if self._leftover or self._starved:
            self._leftover = self._starved = 0
            self.written.append(data)
            self._pending = bytes([arq.REPLY_NACK, data[2], 5])
            return len(data)
        result = super().write(data)
        payload = data[4:-1]
        if payload[:2] == bytes([arq.MESSAGE_HEADER]) + arq.CMD_MOTORS[0:1]:
            if payload[2:3] == arq.MOTORS_COUNT:
                if self.answers_count:
                    self._pending += (self.count_bytes
                                      if self.count_bytes is not None
                                      else bytes([self.motors]) + b"Fake board\n")
            elif payload[2:3] == arq.MOTORS_SET:
                sent = len(payload) - 3
                if sent > self.motors:
                    self._leftover = sent - self.motors
                elif sent < self.motors:
                    self._starved = self.motors - sent
        return result

    def set_frames(self) -> list[bytes]:
        return [f for f in self.written
                if f[4:7] == bytes([arq.MESSAGE_HEADER]) + b"VS"]


# ----------------------------------------------------------- discovery

def test_a_two_channel_board_is_discovered_and_sent_two_bytes(caplog):
    board = CountingBoard(2)
    link = link_onto(board)
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert link.discover_channels(wind.CHANNELS) == 2
    assert link.channels == 2
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "declares 2 channels" in said
    assert "not the 4 on file" in said
    # The app's four-wide vector is fitted, and the board acknowledges it.
    assert link.send((120, 130, 0, 0)) is True
    assert link.last_outcome == "acked"
    assert board.set_frames()[-1][7:9] == bytes([120, 130])
    assert len(board.set_frames()[-1]) == 4 + 3 + 2 + 1


def test_the_four_channel_board_on_the_rig_still_gets_four():
    board = CountingBoard(4)
    link = link_onto(board)
    assert link.discover_channels(wind.CHANNELS) == 4
    assert link.send((120, 130, 0, 0)) is True
    assert len(board.set_frames()[-1]) == 4 + 3 + 4 + 1


def test_a_declared_count_is_not_believed_until_proved(caplog):
    """The board says 3 and drives 2. Three zero frames at width 3 poison
    each other, the declared count fails, and the default is tried."""
    board = CountingBoard(2, count_bytes=b"\x03Liar\n")
    board.motors = 2
    link = link_onto(board)
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        # Default 2 here so the fallback is the truth.
        assert link.discover_channels(2) == 2
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "did not acknowledge three zero frames of width 3" in said


def test_an_unreadable_reply_falls_back_to_the_count_on_file(caplog):
    board = CountingBoard(4, count_bytes=b"Adafruit Motor Shield V2\n")
    link = link_onto(board)
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert link.discover_channels(4) == 4
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "did not give a channel count this app can read" in said
    # The raw bytes are in the log: that is the measurement.
    assert "41 64 61" in said


def test_a_board_that_confirms_nothing_is_said_to_be_assumed(caplog):
    """Not silently four. The word is in the log, and the send path will
    report every rejection from here."""
    board = CountingBoard(3, answers_count=False)
    link = link_onto(board)
    with caplog.at_level(logging.WARNING, logger="pitcrew.wind"):
        assert link.discover_channels(4) == 4
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "assumed" in said


def test_fit_trims_and_pads():
    link = wind.WindLink("COM-TEST")
    link.channels = 2
    assert link.fit((1, 2, 3, 4)) == (1, 2)
    link.channels = 4
    assert link.fit((1, 2)) == (1, 2, 0, 0)


# ----------------------------------------------------- through the sim

def test_the_sim_logs_what_the_board_was_sent(monkeypatch, caplog):
    board = CountingBoard(2)
    monkeypatch.setattr(wind, "find_port", lambda: "COM-TEST")
    monkeypatch.setattr(wind.WindLink, "open",
                        lambda self, settle=True: setattr(self, "_serial", board))
    sim = wind.WindSim()
    assert sim._connect(settle=False) is True
    assert sim.state.channels == 2
    sim.set_output((200, 210, 0, 0))
    with caplog.at_level(logging.INFO, logger="pitcrew.wind.frames"):
        assert sim._send_once() is True
    assert sim.state.last_values == (200, 210)
    frames = [r.getMessage() for r in caplog.records if "duty=" in r.getMessage()]
    assert frames and "duty=200,210 " in frames[-1]
