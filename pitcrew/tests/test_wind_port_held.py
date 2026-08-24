"""The fans stopped 65 seconds into the race and never came back.

Road Atlanta, 23 Aug 2026. They ran in practice and qualifying:

    20:24:05  Lost the wind simulator on COM5: Write timeout
    20:24:06  closing COM5 did not return within 1.0s, so it has been left to
              the operating system.
    20:24:06  Could not open COM5: PermissionError(13, 'Access is denied.')
    ... and that line again every 30 seconds for the next 31 minutes.

Leaking the handle is the deliberate trade - `WindLink.close` explains why
freezing the app is worse. But nothing connected the leak to the sixty
`Access is denied` lines that followed it, so the log blamed Windows for a
port this app was holding itself.
"""
from __future__ import annotations

import threading



# ---------------------------------------------------------------------------
# The fans
# ---------------------------------------------------------------------------

class _Sim:
    """Just the helper under test, off the real class."""
    from pitcrew.rig.wind import WindSim
    _port_is_held_by_us = WindSim._port_is_held_by_us


def test_no_abandoned_close_means_the_port_is_not_ours():
    from pitcrew.rig.wind import WindLink

    WindLink._orphaned_closes.clear()
    assert _Sim()._port_is_held_by_us('COM5') is False


def test_a_running_close_means_the_port_is_still_ours():
    """The 31 minutes of `Access is denied`. The app was the one holding it."""
    from pitcrew.rig.wind import WindLink

    stop = threading.Event()
    closer = threading.Thread(target=stop.wait, daemon=True)
    closer.start()
    WindLink._orphaned_closes['COM5'] = closer
    try:
        assert _Sim()._port_is_held_by_us('COM5') is True
    finally:
        stop.set()
        closer.join(2)
        WindLink._orphaned_closes.clear()


def test_a_finished_close_is_forgotten():
    """A slow close that eventually returned must not make every later
    failure look like this one."""
    from pitcrew.rig.wind import WindLink

    closer = threading.Thread(target=lambda: None, daemon=True)
    closer.start()
    closer.join(2)
    WindLink._orphaned_closes['COM5'] = closer
    assert _Sim()._port_is_held_by_us('COM5') is False
    assert 'COM5' not in WindLink._orphaned_closes, "and cleared, not re-tested"


def test_the_abandoned_close_is_published():
    """Wiring: `close` has to record the orphan or the reopen learns nothing."""
    import inspect

    from pitcrew.rig.wind import WindLink

    body = inspect.getsource(WindLink.close)
    assert "_orphaned_closes[self.port] = closer" in body


def test_the_reopen_consults_it():
    import inspect

    from pitcrew.rig.wind import WindSim

    body = inspect.getsource(WindSim._connect)
    assert "_port_is_held_by_us" in body


def test_an_orphan_on_one_port_says_nothing_about_another():
    """**`_run` re-runs `find_port()` on every reconnect** - its own comment
    says the COM number can change across a replug. An orphan with no port
    would make an innocent failure to open COM6 report that this app was
    holding it, and send him to restart an app that a settle would have
    fixed: the same wrong-cause message from the other side."""
    import threading

    from pitcrew.rig.wind import WindLink

    stop = threading.Event()
    closer = threading.Thread(target=stop.wait, daemon=True)
    closer.start()
    WindLink._orphaned_closes.clear()
    WindLink._orphaned_closes["COM5"] = closer
    try:
        assert _Sim()._port_is_held_by_us("COM5") is True
        assert _Sim()._port_is_held_by_us("COM6") is False
    finally:
        stop.set()
        closer.join(2)
        WindLink._orphaned_closes.clear()


def test_two_abandoned_closes_do_not_overwrite_each_other():
    """One finishing must not clear the claim of the other, which would put
    the misleading message straight back."""
    import threading

    from pitcrew.rig.wind import WindLink

    stop = threading.Event()
    slow = threading.Thread(target=stop.wait, daemon=True)
    slow.start()
    quick = threading.Thread(target=lambda: None, daemon=True)
    quick.start()
    quick.join(2)
    WindLink._orphaned_closes.clear()
    WindLink._orphaned_closes.update({"COM5": slow, "COM6": quick})
    try:
        assert _Sim()._port_is_held_by_us("COM6") is False
        assert _Sim()._port_is_held_by_us("COM5") is True, (
            "COM6 finishing says nothing about COM5")
    finally:
        stop.set()
        slow.join(2)
        WindLink._orphaned_closes.clear()


def test_a_held_port_is_not_even_opened():
    """Attempting an open that cannot succeed buys nothing and costs a
    settle."""
    import inspect

    from pitcrew.rig.wind import WindSim

    body = inspect.getsource(WindSim._connect)
    held_at = body.index("_port_is_held_by_us")
    open_at = body.index("link.open(")
    assert held_at < open_at
    assert "return False" in body[held_at:open_at]


def test_pending_io_is_cancelled_before_the_close():
    """**The root cause of the 31 minutes.** `WRITE_TIMEOUT_S` is 0.25 s and
    pyserial's write timeout returns without cancelling the overlapped write
    it gave up on. `CloseHandle` then blocks on that still-outstanding I/O,
    the close never returns, and the port is abandoned still held."""
    order = []

    class _Handle:
        def cancel_write(self):
            order.append("cancel_write")

        def cancel_read(self):
            order.append("cancel_read")

        def close(self):
            order.append("close")

    from pitcrew.rig.wind import WindLink

    WindLink._close_handle(WindLink("COM5"), _Handle())
    assert order[-1] == "close", "the close must come last"
    assert "cancel_write" in order, (
        "the timed-out write is what blocks the close; not cancelling it is "
        "what cost the fans a whole race")


def test_a_cancel_that_raises_still_reaches_the_close():
    """A surprise-removed device can fail either cancel. Getting to the close
    still matters."""
    closed = []

    class _Handle:
        def cancel_write(self):
            raise OSError("device gone")

        def cancel_read(self):
            raise OSError("device gone")

        def close(self):
            closed.append(True)

    from pitcrew.rig.wind import WindLink

    WindLink._close_handle(WindLink("COM5"), _Handle())
    assert closed == [True]


def test_a_handle_without_cancel_is_still_closed():
    """Not every pyserial backend exposes them."""
    closed = []

    class _Handle:
        def close(self):
            closed.append(True)

    from pitcrew.rig.wind import WindLink

    WindLink._close_handle(WindLink("COM5"), _Handle())
    assert closed == [True]


# ---------------------------------------------------------------------------
# The fans, again - 24 Aug 2026
#
#     14:04:40  wind simulator ready on COM5
#     14:07:20  Lost the wind simulator on COM5: Write timeout
#     14:07:21  closing COM5 did not return within 1.0s
#     14:07:22  COM5 cannot be reopened because this app is still holding it
#
# Two minutes forty into the first of four back-to-back test stints, and the
# fans stayed off for the rest of the afternoon. The cancel-before-close fix
# was already in - it did not get the port back. So the link must stop being
# dropped for a single timeout in the first place: a fan value is idempotent
# and resent every 250 ms against a 1000 ms deadman, and nothing about the
# next frame is worse for the last one having been abandoned.
# ---------------------------------------------------------------------------

class _Handle:
    """A port that refuses writes for a while and then takes them again."""

    def __init__(self, refusals: int) -> None:
        self.refusals = refusals
        self.written: list[bytes] = []
        self.purges = 0
        self.cancels = 0
        self.is_open = True
        self.in_waiting = 0

    def write(self, data: bytes) -> None:
        import serial
        if self.refusals > 0:
            self.refusals -= 1
            raise serial.SerialTimeoutException("Write timeout")
        self.written.append(data)

    def read(self, n: int = 1) -> bytes:
        from pitcrew.rig import arq
        return bytes([arq.REPLY_ACK, 0]) [:n]

    def reset_output_buffer(self) -> None:
        self.purges += 1

    def reset_input_buffer(self) -> None:
        pass

    def cancel_write(self) -> None:
        self.cancels += 1

    def close(self) -> None:
        self.is_open = False


def _link(handle):
    from pitcrew.rig.wind import WindLink
    link = WindLink('COM5')
    link._serial = handle
    return link


def test_one_write_timeout_is_ridden_out_rather_than_ending_the_link():
    handle = _Handle(refusals=1)
    link = _link(handle)

    assert link.send((0, 0, 0, 0)) is True
    assert link.write_timeouts == 1
    assert link.consecutive_write_timeouts == 1
    # The frame that stuck was cancelled and the buffer purged, or the next
    # write inherits it.
    assert handle.purges >= 1 and handle.cancels >= 1


def test_the_stuck_write_is_forgotten_once_a_frame_gets_through():
    handle = _Handle(refusals=1)
    link = _link(handle)

    link.send((0, 0, 0, 0))
    assert link.send((0, 0, 0, 0)) is True
    assert link.consecutive_write_timeouts == 0
    assert link.write_timeouts == 1
    assert len(handle.written) == 1


def test_a_run_of_timeouts_still_gives_up():
    """Riding one out is right; riding out a device that has gone is not."""
    import pytest
    from pitcrew.rig.wind import WRITE_TIMEOUT_LIMIT

    handle = _Handle(refusals=WRITE_TIMEOUT_LIMIT + 5)
    link = _link(handle)

    for _ in range(WRITE_TIMEOUT_LIMIT - 1):
        assert link.send((0, 0, 0, 0)) is True
    with pytest.raises(Exception):
        link.send((0, 0, 0, 0))


def test_a_link_that_has_really_gone_is_not_ridden_out():
    """Only a write timeout is survivable. A dead port is still dead."""
    import pytest
    import serial

    class _Gone(_Handle):
        def write(self, data: bytes) -> None:
            raise serial.SerialException("ClearCommError failed")

    link = _link(_Gone(refusals=0))
    with pytest.raises(serial.SerialException):
        link.send((0, 0, 0, 0))
    assert link.write_timeouts == 0


def test_the_output_buffer_is_purged_before_the_close():
    """`CancelIoEx` alone did not get COM5 back on 24 Aug. PurgeComm is the
    documented way to abandon a write stuck in the driver, and it goes first."""
    order: list[str] = []

    class _Recorder(_Handle):
        def reset_output_buffer(self) -> None:
            order.append('purge')

        def cancel_write(self) -> None:
            order.append('cancel_write')

        def cancel_read(self) -> None:
            order.append('cancel_read')

        def close(self) -> None:
            order.append('close')

    link = _link(_Recorder(refusals=0))
    link._close_handle(link._serial)
    assert order[0] == 'purge'
    assert order[-1] == 'close'
