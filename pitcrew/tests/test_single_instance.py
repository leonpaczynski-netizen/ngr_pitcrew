"""One rig, one *live* app - and the difference between live and merely there.

Two copies of Pit Crew cannot share the hardware. 22 Aug 2026, mid-race: an
instance was left running and a second was started. Between them they held
COM5 against each other - `PermissionError(13, 'Access is denied.')` in the
log - rendered two haptic streams into one endpoint until it degraded back to
30664 Hz nineteen seconds after launch, and thrashed the recovery ladder until
PortAudio was terminated over an open stream and took the process down. The
driver lost the app entirely, mid-race. That is what the guard is for and it
must never stop working.

**But the guard that fixed it then caused a worse failure two days later.** It
asked whether a named mutex existed, and a mutex exists for as long as its
process does. The CH340 wind controller stops answering, `CloseHandle` on its
port blocks inside the driver, and the process is left with one thread parked
in a kernel call that nothing can retire - PID 15644 on 24 Aug survived
`TerminateProcess`. The name outlived it and the app refused to start at
09:54, 12:05, 12:13 and 12:42. Only a reboot cleared it.

A process with one thread and no processor time is not a copy of Pit Crew
fighting for the rig. It renders nothing and answers nothing. Measured on the
day: it held COM5 and *nothing else* - both UDP ports were free.

So these cover two things that pull against each other:

* a copy that is **running** is still refused, exactly as on 22 Aug;
* a copy that has **stopped** is not, and neither is a holder we cannot
  identify at all - because this is race-night software and failing to start
  is the worst outcome there is.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

from pitcrew import app

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(app.__file__))))


def _drop_claim() -> None:
    """Let go of the claim as thoroughly as ending the process would.

    **Closing the handle is the whole job, and clearing the variable is not
    it.** A Windows named mutex lives as long as any handle to it is open, so
    a test that only set `_INSTANCE_MUTEX = None` would leak the handle and
    leave the name taken for every test after it - which is exactly what it
    did, and the failure looked like the guard being broken rather than the
    test being untidy.
    """
    app._release_sole_instance()


def _mutex_exists(name: str) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    kernel32.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                    wintypes.LPCWSTR)
    handle = kernel32.OpenMutexW(0x00100000, False, name)   # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


@pytest.fixture(autouse=True)
def _private_name(monkeypatch, tmp_path):
    """A mutex name and a claim record of this test run's own.

    **The suite must be runnable while Pit Crew is open**, which on this rig
    is most of the time. Using the real name meant a live app held the mutex
    and four of these failed for a reason the code did not cause - and a
    suite that fails for environmental reasons is a suite that stops being
    read. Caught exactly that way: they passed, the driver started the app,
    and they failed.

    The claim record is redirected for the same reason in the other
    direction: a suite run must not overwrite the record the running app
    wrote about itself.
    """
    # Built by extending the real name rather than spelling a new one, so
    # there is no backslash to escape and no way for the two to drift apart.
    monkeypatch.setattr(app, "_INSTANCE_NAME",
                        f"{app._INSTANCE_NAME}.test.{os.getpid()}")
    monkeypatch.setattr(app, "_record_path",
                        lambda: tmp_path / app._INSTANCE_RECORD)
    _drop_claim()
    yield
    _drop_claim()


# ------------------------------------------------------------ the easy cases

def test_the_first_instance_is_allowed():
    assert app._claim_sole_instance().allowed is True


def test_asking_twice_does_not_refuse_us_our_own_claim():
    """**`CreateMutexW` reports ERROR_ALREADY_EXISTS for a name that exists
    whoever created it - including this process.**

    So a second ask without the held-handle check would have the app refuse
    ITSELF. `main` asks once today, which is why this was not visible; a
    restart-in-place, or a test, would have found it the hard way.
    """
    assert app._claim_sole_instance().allowed is True
    assert app._claim_sole_instance().allowed is True, (
        "the app refused its own claim")


def test_the_override_lets_a_second_copy_run(monkeypatch):
    """For a developer running a second copy against another database on
    purpose, and for the driver through the force-start shortcut when
    everything else has gone wrong. Deliberately an environment variable and
    not a setting: a setting lives in the database the second copy would be
    sharing."""
    assert app._claim_sole_instance().allowed is True
    monkeypatch.setenv("PITCREW_ALLOW_MULTIPLE", "1")
    _drop_claim()                               # as a fresh process is
    assert app._claim_sole_instance().allowed is True


# ------------------------------------------------------- giving the name back

@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="the guard is a Windows named mutex")
def test_a_clean_exit_gives_the_name_back():
    """**The regression test for the whole defect.**

    The old code held the mutex for the life of the process and let the
    process's death release it, on the stated grounds that a named mutex
    "cannot be left stale by a crash the way a lock file can". That is true
    only of a process that can die. Releasing it on the way out is what makes
    the next launch work whether or not this one manages to exit.
    """
    assert app._claim_sole_instance().allowed is True
    assert _mutex_exists(app._INSTANCE_NAME), "the claim was never taken"
    app._release_sole_instance()
    assert not _mutex_exists(app._INSTANCE_NAME), (
        "the name survived a clean exit - the next launch would be refused")


def test_releasing_clears_the_claim_record():
    app._claim_sole_instance()
    assert app._record_path().exists()
    app._release_sole_instance()
    assert not app._record_path().exists()


def test_releasing_twice_is_harmless():
    """`main` puts this in a `finally`; nothing may explode on a second pass."""
    app._claim_sole_instance()
    app._release_sole_instance()
    app._release_sole_instance()


# ------------------------------------------------------------- the verdicts

def _someone_else_holds_it(monkeypatch, *, wedged: bool, pid: int = 4242):
    """Make the claim look taken by another process, without being one."""
    app._claim_sole_instance()                  # take the name for real
    monkeypatch.setattr(app, "_INSTANCE_MUTEX", None)   # now be a newcomer
    monkeypatch.setattr(app, "_read_claim_record", lambda: (pid, 1))
    monkeypatch.setattr(app, "_holder_is_wedged", lambda _pid: wedged)


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="the guard is a Windows named mutex")
def test_a_running_holder_is_refused(monkeypatch):
    """22 Aug, and the one verdict that does not bend."""
    _someone_else_holds_it(monkeypatch, wedged=False)
    claim = app._claim_sole_instance()
    assert claim.allowed is False
    assert "already running" in claim.message
    assert "transducer" in claim.message, (
        "the refusal must say why two copies are dangerous, not just that "
        "it will not start")
    assert claim.holder == 4242


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="the guard is a Windows named mutex")
def test_a_wedged_holder_does_not_stop_the_app_starting(monkeypatch):
    """The four refused launches of 24 Aug, and what should have happened."""
    _someone_else_holds_it(monkeypatch, wedged=True)
    claim = app._claim_sole_instance()
    assert claim.allowed is True
    assert claim.holder == 4242
    assert claim.message, "starting degraded must never be silent"


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="the guard is a Windows named mutex")
def test_the_wedged_message_says_what_is_lost_and_does_not_say_restart(
        monkeypatch):
    """He reads this with a headset on, about to race.

    The old text ended "the machine needs restarting", which was a guess and
    is now wrong - the app has started. It has to say what does not work
    instead, because he will wonder mid-race why the fans are dead.
    """
    _someone_else_holds_it(monkeypatch, wedged=True)
    message = app._claim_sole_instance().message
    assert "fans will not work" in message
    assert "restart" not in message.lower(), (
        "the app has started; telling him to restart the machine is the "
        "advice that cost four launches")


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="the guard is a Windows named mutex")
def test_a_holder_we_cannot_identify_starts_anyway(monkeypatch):
    """Cannot tell is not the same as yes.

    A claim record deleted by hand, a half-written line, a pid that has since
    been reused - all arrive here, and all of them start. Refusing on an
    absence is what turned a dead fan into a lost evening.
    """
    app._claim_sole_instance()
    monkeypatch.setattr(app, "_INSTANCE_MUTEX", None)
    monkeypatch.setattr(app, "_read_claim_record", lambda: None)
    claim = app._claim_sole_instance()
    assert claim.allowed is True
    assert claim.message, "starting on an unknown holder must be logged"


# ------------------------------------------------------------- the probe

@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="reads Windows process times")
def test_a_busy_process_is_never_called_wedged():
    """The false positive that would put two live copies on one rig."""
    child = subprocess.Popen(
        [sys.executable, "-c", "\nwhile True: pass\n"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert app._holder_is_wedged(child.pid) is False
    finally:
        child.kill()
        child.wait(timeout=30)


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="reads Windows process times")
def test_a_pid_that_has_gone_is_wedged_not_alive():
    """A holder that died between the mutex check and the probe."""
    child = subprocess.Popen([sys.executable, "-c", "pass"],
                             stdout=subprocess.DEVNULL)
    child.wait(timeout=30)
    time.sleep(0.2)
    assert app._holder_is_wedged(child.pid) is True


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="reads Windows process times")
def test_this_process_has_more_threads_than_a_corpse():
    """Anchors `_WEDGED_THREADS` to something real rather than to taste.

    A Python process running a test suite already carries more threads than
    the threshold; a Qt app with a listener, a wind link and a transducer
    carries far more. PID 15644 carried one.
    """
    count = app._thread_count(os.getpid())
    assert count is not None
    assert count > app._WEDGED_THREADS


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="reads Windows process times")
def test_a_recycled_pid_is_not_mistaken_for_the_holder(monkeypatch, tmp_path):
    """The record names a pid AND when that process started.

    Windows reuses pids. Without the creation time, a fresh process wearing a
    dead app's number would be probed as though it were the holder - and if
    it happened to be busy, the app would refuse to start because of a
    stranger.
    """
    app._record_path().write_text(f"{os.getpid()} 1\n", encoding="utf-8")
    monkeypatch.setattr(app, "_process_facts", lambda pid: (999, 0.0))
    assert app._read_claim_record() is None


def test_our_own_pid_in_the_record_is_not_another_copy():
    """A record left by this very process is not evidence of a second one."""
    app._record_path().write_text(f"{os.getpid()} 0\n", encoding="utf-8")
    assert app._read_claim_record() is None


@pytest.mark.parametrize("junk", ["", "not a pid", "12", "1 2 3", "x y"])
def test_a_garbled_record_never_raises(junk):
    """It is a hint, not the lock. Every failure has to arrive as None."""
    app._record_path().write_text(junk, encoding="utf-8")
    assert app._read_claim_record() is None


# ----------------------------------------------------- the honest end to end

@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="the guard is a Windows named mutex")
def test_a_genuinely_separate_live_process_is_refused():
    """**The 22 Aug protection, and the one that must never go yellow.**

    A real second process, holding the claim and burning processor time,
    while this one tries to start. Nothing is faked: the mutex is real, the
    claim record is real, and the verdict comes from the child's own
    process times and thread count.
    """
    # **The same record path the parent will read**, or the parent falls
    # through to "cannot identify the holder" and starts - which is the right
    # behaviour there and would make this test silently prove nothing.
    record = app._record_path()
    child_source = textwrap.dedent(f"""
        import sys, threading
        sys.path.insert(0, {REPO!r})
        from pathlib import Path
        from pitcrew import app
        app._INSTANCE_NAME = {app._INSTANCE_NAME!r}
        app._record_path = lambda: Path({str(record)!r})
        assert app._claim_sole_instance().allowed
        # Look like a running app: several threads, and never still.
        for _ in range(4):
            threading.Thread(target=lambda: [x * x for x in range(10 ** 9)],
                             daemon=True).start()
        print("HELD", flush=True)
        while True:
            pass
        """)
    child = subprocess.Popen([sys.executable, "-c", child_source],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        assert child.stdout.readline().strip() == "HELD", (
            f"the child never took the claim: {child.stderr.read()[:400]!r}")
        claim = app._claim_sole_instance()
        assert claim.allowed is False, (
            "a second LIVE process was allowed to start - this is the 22 Aug "
            "defect, and it damaged the transducer")
        assert claim.holder == child.pid
    finally:
        child.kill()
        child.wait(timeout=30)


# ---------------------------------------------------------------- the override

def test_the_force_flag_starts_regardless(monkeypatch):
    """The shortcut's door, and it must not need an environment variable.

    24 Aug 2026: the app refused four launches and the only recovery anyone
    had was a reboot. `PITCREW_ALLOW_MULTIPLE` already existed and was no use
    to the driver - setting an environment variable is not something he can
    do from a taskbar at five to eight on a race night.
    """
    app._claim_sole_instance()
    monkeypatch.setattr(app, "_INSTANCE_MUTEX", None)
    monkeypatch.setattr(app, "_read_claim_record", lambda: (4242, 1))
    monkeypatch.setattr(app, "_holder_is_wedged", lambda _pid: False)
    assert app._claim_sole_instance().allowed is False, (
        "without the flag this is a refusal, or the test proves nothing")

    monkeypatch.setattr(app, "_INSTANCE_MUTEX", None)
    monkeypatch.setattr(sys, "argv", ["pitcrew", "--force"])
    assert app._claim_sole_instance().allowed is True


def test_the_flag_is_only_read_from_arguments_not_from_the_program_name():
    """`sys.argv[0]` is a path, and a checkout living under a folder with
    "--force" in its name is absurd - but slicing it off costs nothing and
    the alternative is a bug nobody would ever guess at."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(sys, "argv", ["C:/--force/pitcrew.py"])
        assert app._forced() is False
    finally:
        monkeypatch.undo()
