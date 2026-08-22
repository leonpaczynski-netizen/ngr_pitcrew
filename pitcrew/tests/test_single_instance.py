"""One rig, one app.

Two copies of Pit Crew cannot share the hardware. 22 Aug 2026, mid-race: an
instance was left running and a second was started. Between them they held
COM5 against each other - `PermissionError(13, 'Access is denied.')` in the
log - rendered two haptic streams into one endpoint until it degraded back to
30664 Hz nineteen seconds after launch, and thrashed the recovery ladder until
PortAudio was terminated over an open stream and took the process down. The
driver lost the app entirely, mid-race.

The wind controller, the transducer and the microphone are single-owner
devices. Nothing about this app is safe to run twice.
"""
from __future__ import annotations

import os
import sys

import pytest

from pitcrew import app


def _drop_claim() -> None:
    """Let go of the claim as thoroughly as ending the process would.

    **Closing the handle is the whole job, and clearing the variable is not
    it.** A Windows named mutex lives as long as any handle to it is open, so
    a test that only set `_INSTANCE_MUTEX = None` would leak the handle and
    leave the name taken for every test after it - which is exactly what it
    did, and the failure looked like the guard being broken rather than the
    test being untidy.
    """
    handle, app._INSTANCE_MUTEX = app._INSTANCE_MUTEX, None
    if handle:
        try:
            import ctypes

            ctypes.WinDLL("kernel32").CloseHandle(handle)
        except Exception:                                    # noqa: BLE001
            pass


@pytest.fixture(autouse=True)
def _private_name(monkeypatch):
    """A mutex name of this test run's own, and nothing owning it.

    **The suite must be runnable while Pit Crew is open**, which on this rig
    is most of the time. Using the real name meant a live app held the mutex
    and four of these failed for a reason the code did not cause - and a
    suite that fails for environmental reasons is a suite that stops being
    read. Caught exactly that way: they passed, the driver started the app,
    and they failed.

    The process id keeps parallel runs apart as well.
    """
    # Built by extending the real name rather than spelling a new one, so
    # there is no backslash to escape and no way for the two to drift apart.
    monkeypatch.setattr(app, "_INSTANCE_NAME",
                        f"{app._INSTANCE_NAME}.test.{os.getpid()}")
    _drop_claim()
    yield
    _drop_claim()


def test_the_first_instance_is_allowed():
    assert app._claim_sole_instance() is None


def test_asking_twice_does_not_refuse_us_our_own_claim():
    """**`CreateMutexW` reports ERROR_ALREADY_EXISTS for a name that exists
    whoever created it - including this process.**

    So a second ask without the held-handle check would have the app refuse
    ITSELF. `main` asks once today, which is why this was not visible; a
    restart-in-place, or a test, would have found it the hard way.
    """
    assert app._claim_sole_instance() is None
    assert app._claim_sole_instance() is None, "the app refused its own claim"


def test_the_override_lets_a_second_copy_run(monkeypatch):
    """For a developer running a second copy against another database on
    purpose. Deliberately an environment variable and not a setting: a
    setting lives in the database the second copy would be sharing."""
    assert app._claim_sole_instance() is None
    monkeypatch.setenv("PITCREW_ALLOW_MULTIPLE", "1")
    _drop_claim()                               # as a fresh process is
    assert app._claim_sole_instance() is None


def test_the_refusal_says_what_to_do_about_it():
    """He reads this mid-session with a headset on. It has to name the cause
    and the action, including the case where there is no window to close -
    which is what actually happened: the first copy was wedged in a driver
    call, unkillable, and only a restart cleared it."""
    app._claim_sole_instance()
    # The second copy is a different process, so it holds no handle of its
    # own - but the name is still taken by the first, which is the whole
    # point. The first handle is kept in hand rather than dropped: a named
    # mutex lives while ANY handle to it is open, so losing the reference
    # would leak the name into every test after this one.
    first = app._INSTANCE_MUTEX
    app._INSTANCE_MUTEX = None
    message = app._claim_sole_instance()
    _drop_claim()                               # the second copy's handle
    app._INSTANCE_MUTEX = first
    _drop_claim()                               # and the first's
    if message is None:
        pytest.skip("no named-mutex support on this platform")
    assert "already running" in message
    assert "Close the other window" in message
    assert "restarting" in message, (
        "a stuck first copy cannot be closed, and that is the case the "
        "driver will actually hit")


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="the guard is a Windows named mutex")
def test_a_genuinely_separate_process_is_refused():
    """The one that matters, and the only way to test it honestly: a real
    second process, while this one holds the claim."""
    import subprocess
    import textwrap

    assert app._claim_sole_instance() is None
    # The child must claim the SAME private name, or it proves nothing.
    probe = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, %r)
        from pitcrew import app
        app._INSTANCE_NAME = %r
        print("REFUSED" if app._claim_sole_instance() else "ALLOWED")
        """ % (os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(app.__file__)))), app._INSTANCE_NAME))
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, timeout=120)
    assert out.stdout.strip() == "REFUSED", (
        f"a second process was allowed to start: {out.stdout!r} "
        f"{out.stderr[:300]!r}")
