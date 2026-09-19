"""The gauge pre-flight: can anything be captured before we go out?

**The failure this exists to stop is silent and total.** With nothing being
captured the sampler stands down about thirty seconds in and never comes back.
Session 126 lost its whole wear record that way. On 6 Sep 2026 session 133 lost
its gauge because the driver forgot to open OBS, and only found out afterwards.
GT7 broadcasts no tyre-wear channel in any packet format, so the gauge is the
only instrument that measures it.

**What the check can and cannot prove.** One grab. A grab that succeeds means
something was captured - NOT that the gauge will read. `ScreenSource` captures
the monitor rather than the window, so a covered projector returns a healthy
frame; `find_projector` matches the word "projector" in any window title; and
at the moment he presses Start he is in a GT7 menu, so `locate_gauge` would
return None anyway. The dialog says so in `GaugeCheck.caveat`, and the tests
below pin the honesty of the wording as hard as the logic.
"""
from __future__ import annotations

import pytest

from pitcrew.telemetry.hud_session import GaugeCheck, HudSession


class _Settings:
    def __init__(self, **kwargs):
        self.hud_wear_enabled = True
        self.hud_source = "screen"
        self.hud_sample_interval_s = 2.0
        self.obs_host = "127.0.0.1"
        self.obs_port = 4455
        self.obs_password = ""
        self.obs_record_sessions = False
        self.__dict__.update(kwargs)


class _Source:
    """A source that either sees something, says why not, throws, or hangs."""

    def __init__(self, frame=None, why=None, raises=None, hang_s=0.0):
        self._frame, self._why = frame, why
        self._raises, self._hang = raises, hang_s
        self.grabs = 0

    def grab(self):
        self.grabs += 1
        if self._hang:
            import time
            time.sleep(self._hang)
        if self._raises is not None:
            raise self._raises
        return self._frame, self._why


def _session(settings=None, source=None, recording=False):
    session = HudSession(settings=settings or _Settings(), store=None)
    if source is not None:
        session.build_source = lambda: source
    session._obs_recording = lambda: recording
    return session


# --- the check itself -------------------------------------------------------

def test_a_capture_that_works_is_a_pass():
    check = _session(source=_Source(frame=object())).preflight()
    assert check.ok is True and check.reason is None


def test_nothing_captured_is_a_refusal_that_carries_the_reason():
    """The reason is the whole value of the warning - it tells him what to go
    and do; a bare False does not."""
    check = _session(source=_Source(why="no program projector open")).preflight()
    assert check.ok is False
    assert check.reason == "no program projector open"


def test_a_refusal_with_no_reason_still_says_something():
    """CLAUDE.md rule 3 in the small: a missing reason is not an empty
    warning."""
    check = _session(source=_Source(why=None)).preflight()
    assert check.ok is False and check.reason


def test_a_source_that_raises_cannot_stop_the_session_starting():
    """The gauge is an instrument, not a gate."""
    check = _session(source=_Source(raises=RuntimeError("obs went away"))).preflight()
    assert check.ok is False
    assert "obs went away" in check.reason


def test_a_source_that_hangs_is_bounded_rather_than_freezing_the_app():
    """The DEFAULT source is the OBS websocket: a grab there is a connect,
    identify and whole-canvas screenshot measured at about two seconds, and
    `ObsSource._request` re-arms its receive timeout on every message - so a
    chattering socket never returns. This runs on the Qt thread inside a
    button handler."""
    import time

    session = _session(source=_Source(hang_s=5.0))
    began = time.monotonic()
    check = session.preflight(timeout_s=0.2)
    took = time.monotonic() - began
    assert took < 2.0, f"the pre-flight blocked for {took:.1f}s"
    # **A timeout does NOT claim the projector is missing.** Reported as a
    # refusal it blocked the driver three times minutes before a race, with
    # his projector open in front of him, on a message that was false.
    # CLAUDE.md rule 3: unknown is not absent, so he is not asked.
    assert check.ok is True, "a timeout must not block him"
    assert check.checked is False, "but it must not claim it checked either"
    assert "answer" in check.reason


def test_the_gauge_switched_off_passes_but_says_so():
    """Turning it off is a choice and not a nag - but it IS the other way to
    end a session with no wear record, so it is not invisible either."""
    check = _session(settings=_Settings(hud_wear_enabled=False),
                     source=_Source(why="no projector")).preflight()
    assert check.ok is True
    assert check.enabled is False


def test_it_checks_the_source_the_sampler_will_actually_use():
    """A pre-flight on a different source would say "the gauge can see" about
    a path nothing reads from - worse than no check at all."""
    from pitcrew.telemetry.hud import ObsSource, ScreenSource
    assert isinstance(_session(_Settings(hud_source="screen")).build_source(),
                      ScreenSource)
    assert isinstance(_session(_Settings(hud_source="obs")).build_source(),
                      ObsSource)


def test_a_settings_change_rebuilds_the_cached_sampler():
    """The sampler is built once and only `shutdown` stops it, and
    `save_settings` REBINDS settings without touching it - so switching source
    left the old sampler reading the path he had just abandoned while the
    pre-flight checked the new one and passed. Found by a critic."""
    settings = _Settings(hud_source="screen")
    session = HudSession(settings=lambda: settings, store=None)
    first = session._source_key()
    settings.hud_source = "obs"
    assert session._source_key() != first, "a source change is invisible"
    settings.hud_source = "screen"
    settings.obs_port = 4456
    assert session._source_key() != first, "a port change is invisible"


def test_a_refusal_carries_whether_obs_is_recording():
    """Pinned separately because the tests above stub `_obs_recording`, so
    nothing else notices `preflight` hardcoding it - and this value decides
    whether the driver is told the wear is lost or merely deferred."""
    for state in (True, False, None):
        session = HudSession(settings=_Settings(), store=None)
        session.build_source = lambda: _Source(why="nothing there")
        asked = []
        session._obs_recording = lambda: asked.append(1) or state
        check = session.preflight()
        assert asked, "preflight never asked whether OBS was recording"
        assert check.recording is state


class _FakeObs:
    """Stands in for `ObsSource` so no test here touches a live OBS.

    **These tests used to ask the real websocket on 127.0.0.1:4455** and assume
    nothing answered. On 14 Sep 2026, with OBS open and idle, it answered False
    - a correct live reading that failed the suite. A test whose verdict
    depends on what else is running on the machine is testing the machine
    (CLAUDE.md §7).
    """

    answer: tuple = (None, "ConnectionRefusedError")
    release = None
    built: list = []

    def __init__(self, host, port, password):
        _FakeObs.built.append((host, port, password))

    def recording(self):
        if _FakeObs.release is not None:
            _FakeObs.release.wait(timeout=10.0)
        return _FakeObs.answer


@pytest.fixture
def fake_obs(monkeypatch):
    from pitcrew.telemetry import hud

    _FakeObs.answer = (None, "ConnectionRefusedError")
    _FakeObs.release = None
    _FakeObs.built = []
    monkeypatch.setattr(hud, "ObsSource", _FakeObs)
    yield _FakeObs
    if _FakeObs.release is not None:
        _FakeObs.release.set()


@pytest.mark.parametrize("obs_says, expected", [
    ((None, "ConnectionRefusedError"), None),   # unreachable: cannot tell
    ((True, None), True),                       # he started it himself
    ((False, None), False),                     # OBS itself says idle
])
def test_the_app_not_driving_the_recording_is_not_proof_obs_is_idle(
        fake_obs, obs_says, expected):
    """`obs_record_sessions` means "the APP drives the recording", not "OBS is
    recording" - he may have started it himself. Reading it as the second told
    him "OBS is not recording either, so there would be nothing to transcribe",
    which is the sentence most likely to make him abort a race he did not need
    to abort. CLAUDE.md rule 3: unknown is not False. A critic found it.

    **The answer is OBS's, never the flag's.** With the flag off: an
    unreachable OBS is None, not False; a recording he started is True; and
    False is said only when OBS itself reports it."""
    fake_obs.answer = obs_says
    settings = _Settings(obs_record_sessions=False, obs_host="10.0.0.9",
                         obs_port=4460, obs_password="pw")
    session = HudSession(settings=settings, store=None)
    assert session._obs_recording() is expected
    assert fake_obs.built == [("10.0.0.9", 4460, "pw")], \
        "the flag was read instead of OBS being asked"


def test_asking_obs_whether_it_records_cannot_hang_the_button(
        fake_obs, monkeypatch):
    """It goes down `ObsSource._request`, whose receive timeout re-arms on
    every message - the same unbounded path the grab is wrapped for. Bounding
    one of the two doors is not bounding the room."""
    import threading
    import time

    from pitcrew.telemetry import hud_session

    fake_obs.answer = (True, None)
    fake_obs.release = threading.Event()        # an OBS that never answers
    monkeypatch.setattr(hud_session, "PREFLIGHT_TIMEOUT_S", 0.2)
    session = HudSession(settings=_Settings(), store=None)
    began = time.monotonic()
    state = session._obs_recording()
    assert time.monotonic() - began < 2.0, "the recording query blocked"
    # CLAUDE.md rule 3: a query that did not answer is unknown, not idle.
    assert state is None


def test_the_check_costs_exactly_one_grab():
    source = _Source(frame=object())
    _session(source=source).preflight()
    assert source.grabs == 1


# --- the wording, which is where this went wrong twice ----------------------

def test_it_names_the_thing_he_has_to_go_and_fix():
    """The DEFAULT `hud_source` is the OBS websocket, where there is no
    projector in the loop at all. The first version said "OBS is not showing a
    projector" for every failure including websocket ones - the same error
    `find_projector` records as having cost a whole race night."""
    assert "projector" in GaugeCheck(ok=False, source="projector").headline
    assert "projector" not in GaugeCheck(ok=False, source="OBS").headline


def test_it_does_not_claim_the_wear_is_lost_when_obs_is_recording():
    """`tools/read_hud_wear.py` transcribes this gauge off a recording, and
    `LiveWearSampler` already tells him to use it. Saying "this cannot be
    recovered" would either abort a session he did not need to abort, or stop
    him running the recovery pass on one he did."""
    recovery = GaugeCheck(ok=False, recording=True).recovery
    assert "read_hud_wear" in recovery
    assert "no wear evidence" not in recovery


def test_it_does_say_the_wear_is_lost_when_nothing_is_recording():
    recovery = GaugeCheck(ok=False, recording=False).recovery
    assert "nothing" in recovery and "no wear evidence" in recovery


def test_not_knowing_whether_obs_records_is_said_and_not_guessed():
    """CLAUDE.md rule 3: unknown is not False."""
    recovery = GaugeCheck(ok=False, recording=None).recovery
    assert "could not tell" in recovery


def test_the_dialog_admits_what_the_check_cannot_prove():
    """One grab proves something was captured, not that the gauge will read.
    Overclaiming to the driver is the failure mode here."""
    caveat = GaugeCheck(ok=False).caveat
    assert "cannot check the gauge" in caveat.lower()


# --- the gate the driver actually meets -------------------------------------

class _Controller:
    def __init__(self, hud, answer):
        self.hud = hud
        self._answer = answer
        self.asked: list = []

    def confirm_without_gauge(self, what, check):
        self.asked.append((what, check))
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer

    from pitcrew.controller import PitCrewController as _real
    gauge_preflight_ok = _real.gauge_preflight_ok


@pytest.mark.parametrize("answer, expected", [(True, True), (False, False)])
def test_the_driver_decides_and_the_app_does_not(answer, expected):
    app = _Controller(_session(source=_Source(why="no projector")), answer)
    assert app.gauge_preflight_ok("this race") is expected
    assert app.asked[0][0] == "this race"
    assert app.asked[0][1].reason == "no projector"


def test_a_working_capture_asks_him_nothing():
    app = _Controller(_session(source=_Source(frame=object())), False)
    assert app.gauge_preflight_ok("this practice session") is True
    assert app.asked == [], "he was interrupted for nothing"


def test_a_dialog_that_raises_does_not_abort_the_app():
    """These are Qt slots and PyQt aborts the process after `sys.excepthook`
    returns, so an unwrapped dialog failure would kill the app at the moment
    he arms the race. An instrument that cannot be asked about is not a
    reason to stop him driving."""
    app = _Controller(_session(source=_Source(why="no projector")),
                      RuntimeError("no QApplication"))
    assert app.gauge_preflight_ok("this race") is True


# --- the callers, because this codebase keeps building both ends ------------
#
# Removing the gate from `start_race` left every test above green on the first
# pass, so these pin the wiring itself.

class _Screen:
    def __init__(self):
        self.status: list[tuple[str, bool]] = []
        self.recording: list[bool] = []

    def set_status(self, text, warn=False):
        self.status.append((text, warn))

    def set_recording(self, on):
        self.recording.append(on)

    def rehearsal(self):
        return False

    def engineer_speaks(self):
        return False

    def use_plan(self):
        return False


def _stub_controller(answer: bool):
    from pitcrew.controller import PitCrewController

    app = PitCrewController.__new__(PitCrewController)
    app.session_id = None
    # **The production shape.** `__init__` always sets `race`, and on this
    # half-built QObject an attribute nobody set raises RuntimeError rather
    # than AttributeError - so `start_race`'s first line, which now asks
    # whether the race on the board is over, fell over on the stub alone.
    app.race = None
    # The same, for what every start now stands down first (and a refused
    # start lets resume) - the frame prefetch and the last run's debrief.
    app._prewarmed = False
    app._frame_prefetch = None
    app._debrief_stop = None
    app.hud = _session(source=_Source(why="no program projector open"))
    app.confirm_without_gauge = lambda what, check: answer
    app.practice = _Screen()
    app.race_screen = _Screen()
    app.opened = False

    def open_practice_session():
        app.opened = True
        return None
    app.open_practice_session = open_practice_session
    app.active_event = lambda: {"id": 12, "name": "test"}
    return app


def test_start_practice_asks_before_it_opens_a_session():
    """Asked BEFORE the session row exists, so going to set OBS up leaves
    nothing behind - no half-open session, no orphan listener."""
    from pitcrew.controller import PitCrewController

    app = _stub_controller(answer=False)
    PitCrewController.start_practice(app)
    assert app.opened is False, "a session was opened despite him saying no"
    assert app.practice.status, "he was told nothing"
    assert app.practice.status[-1][1] is True, "the warning was not a warning"


def test_start_practice_goes_ahead_when_he_says_go_anyway():
    from pitcrew.controller import PitCrewController

    app = _stub_controller(answer=True)
    PitCrewController.start_practice(app)
    assert app.opened is True, "his answer was ignored"


def test_start_race_refuses_to_arm_when_he_goes_to_fix_obs():
    from pitcrew.controller import PitCrewController

    app = _stub_controller(answer=False)
    assert PitCrewController.start_race(app) is False
    assert app.race_screen.status[-1][1] is True


def test_a_working_gauge_lets_the_race_arm_past_this_gate():
    """The gate must not be a wall: with a capture up, `start_race` gets past
    it and on to its own business."""
    from pitcrew.controller import PitCrewController

    app = _stub_controller(answer=False)
    source = _Source(frame=object())
    app.hud = _session(source=source)
    called = []
    app.confirm_without_gauge = lambda what, check: called.append(1) or True
    try:
        PitCrewController.start_race(app)
    except Exception:               # noqa: BLE001 - it goes on to arm, which
        pass                        # needs far more of a controller than this
    # **Both assertions, because `not called` alone cannot tell "reached the
    # gate and passed" from "raised before the gate".** The grab count pins
    # that the gate actually ran.
    assert source.grabs == 1, "the gate did not run"
    assert not called, "he was asked despite the capture being up"
