"""A driver fault is ridden out on the same handle, not answered with a hello.

Six times in the twenty-minute session of 3 Sep 2026 the CH340 driver failed
a `WriteFile` or `ReadFile` outright, and each one cost a teardown: purge,
cancel, close, reopen, hello, count query - about half a second with no
frame reaching the board, and a hello the board had to answer whose effect
on the outputs is not known from source. Every one reopened on the same port
within 0.3 s, so the handle was never dead. The driver reports drops that
"happen and restore quickly, very noticeable on a straight".

These pin the new behaviour: a fault is purged and the next frame goes on
the same handle; five in a row is a link that has gone; and the counters
say how many were ridden out.
"""
from __future__ import annotations

import logging

import pytest

from pitcrew.rig import arq, wind
from pitcrew.tests.test_wind import FakeSerial, link_onto

serial = pytest.importorskip("serial")


class FaultyBoard(FakeSerial):
    """Acknowledges everything, except that the Nth writes fail the way the
    CH340 driver fails them."""

    def __init__(self, *, fail_writes: set[int] = frozenset(),
                 fail_reads: set[int] = frozenset(),
                 message: str = "WriteFile failed (OSError(22, 'This operation "
                                "returned because the timeout period expired.', "
                                "None, 1460))") -> None:
        super().__init__(speaks=arq.DEFAULT_CRC)
        self.fail_writes = set(fail_writes)
        self.fail_reads = set(fail_reads)
        self.message = message
        self.writes = 0
        self.reads = 0
        self.purges = 0

    def write(self, data: bytes) -> int:
        self.writes += 1
        if self.writes in self.fail_writes:
            raise serial.SerialException(self.message)
        return super().write(data)

    def read(self, size: int = 1) -> bytes:
        self.reads += 1
        if self.reads in self.fail_reads:
            raise serial.SerialException(
                "ReadFile failed (OSError(22, 'The operation completed "
                "successfully.', None, 0))")
        return super().read(size)

    def reset_output_buffer(self) -> None:
        self.purges += 1


def test_the_driver_errors_seen_on_the_rig_are_faults_not_deaths():
    for text in ("WriteFile failed (OSError(22, 'The operation completed "
                 "successfully.', None, 0))",
                 "WriteFile failed (OSError(22, 'This operation returned "
                 "because the timeout period expired.', None, 1460))",
                 "ReadFile failed (OSError(22, 'The operation completed "
                 "successfully.', None, 0))"):
        assert wind._is_driver_fault(serial.SerialException(text)) is True
    assert wind._is_driver_fault(serial.SerialTimeoutException("Write timeout")) is False
    assert wind._is_driver_fault(serial.SerialException(
        "ClearCommError failed (PermissionError(13, 'Access is denied.'))")) is False
    assert wind._is_driver_fault(OSError("the port is not open")) is False


def test_a_write_fault_is_ridden_out_on_the_same_handle(caplog):
    board = FaultyBoard(fail_writes={2})
    link = link_onto(board)
    assert link.send((100, 100, 0, 0)) is True
    with caplog.at_level(logging.INFO, logger="pitcrew.wind"):
        assert link.send((100, 100, 0, 0)) is True       # the fault
    assert link.last_outcome == "driver-fault"
    assert link.driver_faults == 1
    assert board.purges == 1
    assert board.closed is False                           # no teardown
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "driver fault on write (1 in a row" in said
    assert "1460" in said
    # The next frame goes on the same handle and is acknowledged.
    assert link.send((100, 100, 0, 0)) is True
    assert link.last_outcome == "acked"
    assert link.consecutive_driver_faults == 0


def test_a_read_fault_is_ridden_out_too():
    board = FaultyBoard(fail_reads={3})       # the second frame's reply
    link = link_onto(board)
    assert link.send((100, 100, 0, 0)) is True
    assert link.send((100, 100, 0, 0)) is True
    assert link.last_outcome == "driver-fault"
    assert link.send((100, 100, 0, 0)) is True
    assert link.last_outcome == "acked"


def test_five_in_a_row_is_a_link_that_has_gone():
    board = FaultyBoard(fail_writes=set(range(1, 20)))
    link = link_onto(board)
    for _ in range(wind.DRIVER_FAULT_LIMIT - 1):
        assert link.send((0, 0, 0, 0)) is True
    with pytest.raises(serial.SerialException):
        link.send((0, 0, 0, 0))


def test_the_sim_counts_faults_and_keeps_the_link(monkeypatch):
    board = FaultyBoard(fail_writes={2, 4})
    sim = wind.WindSim()
    sim._link = link_onto(board)
    sim.state.connected = True
    for _ in range(5):
        assert sim._send_once() is True
    assert sim.state.driver_faults == 2
    assert sim.state.write_failures == 0
    assert sim.state.disconnects == 0
    # A faulted frame did not go anywhere and is not counted as sent.
    assert sim.state.frames_sent == 3
    assert sim.state.frames_accepted == 3
