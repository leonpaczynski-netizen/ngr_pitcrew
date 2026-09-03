"""The channel count comes from the board, is never trusted into a narrower
frame, and a reply marker is never read as a number.

Measured on the rig on 3 Sep 2026, and both facts changed this module:

- The two bytes after a count query were `08 6a`. The first version read
  the `0x08` value marker as a count of eight, and the board then
  acknowledged 26,875 eight-wide frames in a row with the fans running
  normally. So an acknowledgement proves a frame was accepted and nothing
  about its width: the firmware's packet layer discards the bytes a command
  does not read.
- Those bytes are `Command_Hello`'s reply - a value packet carrying the
  version letter 'j' - arriving a few milliseconds after its
  acknowledgement, which is why the old drain never caught it and the next
  read always did.

So: the hello's tail is read to its own length; a marker at the head of a
reply is a marker; and the frame is never narrower than the count on file,
because wider is harmless and narrower cannot be proved safe.
"""
from __future__ import annotations

import logging

import pytest

from pitcrew.rig import arq, wind
from pitcrew.tests.test_wind import FakeSerial, link_onto

pytest.importorskip("serial")


# ------------------------------------------------------------------ parsing

def test_a_value_packet_carries_the_count():
    assert arq.parse_motors_count(bytes([arq.REPLY_VALUE, 4])) == 4
    assert arq.parse_motors_count(bytes([arq.REPLY_VALUE, 2]) + b"PWM") == 2


def test_the_bytes_the_board_actually_sent_are_not_a_count():
    """`08 6a` read as eight is the defect this file exists for."""
    assert arq.parse_motors_count(b"\x08\x6a") is None


def test_a_bare_marker_is_never_a_count():
    assert arq.parse_motors_count(bytes([arq.REPLY_VALUE])) is None
    assert arq.parse_motors_count(bytes([arq.REPLY_ACK, 4])) is None
    assert arq.parse_motors_count(bytes([arq.REPLY_NACK, 4, 5])) is None
    assert arq.parse_motors_count(bytes([arq.REPLY_STRING]) + b"x") is None


def test_an_ascii_digit_count_is_read():
    assert arq.parse_motors_count(b"4\nAdafruit") == 4
    assert arq.parse_motors_count(b"2") == 2


def test_nothing_is_none_not_zero():
    assert arq.parse_motors_count(b"") is None


def test_an_implausible_count_is_refused():
    assert arq.parse_motors_count(b"A") is None          # 0x41 = 65
    assert arq.parse_motors_count(bytes([arq.REPLY_VALUE, arq.MAX_CHANNELS + 1])) is None
    assert arq.parse_motors_count(bytes([arq.REPLY_VALUE, arq.MAX_CHANNELS])) == arq.MAX_CHANNELS


# ------------------------------------------------------------- a fake board

class MeasuredBoard(FakeSerial):
    """The board as measured on 3 Sep 2026.

    Acknowledges any well-formed frame whatever its width. Answers a hello
    with an acknowledgement and then the value packet `08 6a`. Answers a
    count query with an acknowledgement and then `count_bytes`, which on the
    real board is nothing at all.
    """

    def __init__(self, *, count_bytes: bytes = b"",
                 hello_tail: bytes = b"\x08\x6a") -> None:
        super().__init__(speaks=arq.DEFAULT_CRC)
        self.count_bytes = count_bytes
        self.hello_tail = hello_tail

    def write(self, data: bytes) -> int:
        result = super().write(data)
        payload = data[4:-1]
        if payload == arq.hello_payload():
            self._pending += self.hello_tail
        elif payload == arq.motors_count_payload():
            self._pending += self.count_bytes
        return result

    def set_frames(self) -> list[bytes]:
        return [f for f in self.written
                if f[4:7] == bytes([arq.MESSAGE_HEADER]) + b"VS"]


# --------------------------------------------------------------- the hello

def test_the_hello_tail_is_read_as_the_version_and_not_left_for_the_next_read():
    board = MeasuredBoard()
    link = link_onto(board)
    assert link.handshake() is True
    assert link.firmware == "j"
    # Nothing left over: the next read sees only its own reply.
    assert board.read(64) == b""


def test_a_hello_tail_that_is_not_a_version_packet_is_dropped(caplog):
    board = MeasuredBoard(hello_tail=b"zz")
    link = link_onto(board)
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert link.handshake() is True
    assert link.firmware is None
    assert "not a version packet" in " ".join(r.getMessage() for r in caplog.records)


# ----------------------------------------------------------- discovery

def test_the_board_as_measured_keeps_the_count_on_file(caplog):
    """No readable count came back; the frame stays four wide and the log
    says so, with the raw bytes."""
    board = MeasuredBoard()
    link = link_onto(board)
    assert link.handshake() is True
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert link.discover_channels(wind.CHANNELS) == 4
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "did not give a channel count this app can read" in said
    assert "(reply: nothing)" in said
    assert link.channels == 4
    assert link.send((120, 130, 0, 0)) is True
    assert len(board.set_frames()[-1]) == 4 + 3 + 4 + 1


def test_a_narrower_declared_count_never_narrows_the_frame(caplog):
    """The reflashed two-motor board. Four-wide frames reach it and the
    surplus is discarded; nothing here may send fewer."""
    board = MeasuredBoard(count_bytes=bytes([arq.REPLY_VALUE, 2]))
    link = link_onto(board)
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert link.discover_channels(4) == 4
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "declares 2 channels" in said
    assert "sending 4 as on file" in said
    assert link.channels == 4


def test_a_wider_declared_count_widens_the_frame(caplog):
    board = MeasuredBoard(count_bytes=bytes([arq.REPLY_VALUE, 6]))
    link = link_onto(board)
    with caplog.at_level(logging.WARNING, logger="pitcrew.wind"):
        assert link.discover_channels(4) == 6
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "more than the 4 on file" in said
    assert link.send((120, 130, 0, 0)) is True
    assert len(board.set_frames()[-1]) == 4 + 3 + 6 + 1


def test_the_stale_marker_can_no_longer_widen_the_frame(caplog):
    """The exact failure of 3 Sep: hello tail left unread, count query
    reads `08 6a`. Even with the hello tail deliberately left in the
    stream, the marker parses as nothing and the width stays four."""
    board = MeasuredBoard()
    link = link_onto(board)
    board.write(arq.build_frame(arq.BROADCAST_ID, arq.hello_payload(),
                                arq.DEFAULT_CRC))
    board.read(2)                       # the ACK; the tail `08 6a` remains
    board._pending = b""                # a drain would clear it...
    board.count_bytes = b"\x08\x6a"     # ...but let it arrive after the query
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert link.discover_channels(4) == 4
    assert "(reply: 08 6a)" in " ".join(r.getMessage() for r in caplog.records)


def test_an_acknowledged_width_is_reported_as_accepted_not_proved():
    """The bench helper measures; it does not prove. On the measured board
    every width is accepted."""
    board = MeasuredBoard()
    link = link_onto(board)
    assert all(link.accepts_width(n) for n in range(1, arq.MAX_CHANNELS + 1))


def test_fit_trims_and_pads():
    link = wind.WindLink("COM-TEST")
    link.channels = 2
    assert link.fit((1, 2, 3, 4)) == (1, 2)
    link.channels = 6
    assert link.fit((1, 2, 3, 4)) == (1, 2, 3, 4, 0, 0)


# ----------------------------------------------------- through the sim

def test_the_sim_connects_to_the_measured_board_and_reports_the_firmware(
        monkeypatch, caplog):
    board = MeasuredBoard()
    monkeypatch.setattr(wind, "find_port", lambda: "COM-TEST")
    monkeypatch.setattr(wind.WindLink, "open",
                        lambda self, settle=True: setattr(self, "_serial", board))
    sim = wind.WindSim()
    assert sim._connect(settle=False) is True
    assert sim.state.channels == 4
    assert sim.state.firmware == "j"
    sim.set_output((200, 210, 0, 0))
    with caplog.at_level(logging.INFO, logger="pitcrew.wind.frames"):
        assert sim._send_once() is True
    assert sim.state.last_values == (200, 210, 0, 0)
    frames = [r.getMessage() for r in caplog.records if "duty=" in r.getMessage()]
    assert frames and "duty=200,210,0,0 " in frames[-1]
    assert "firmware j" in sim.state.describe()
