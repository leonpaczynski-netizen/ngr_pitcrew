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
