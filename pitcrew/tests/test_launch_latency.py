"""What the launch no longer waits for, and the guarantees that replaced the wait.

Measured 19 Sep 2026, six interleaved pairs against bf83dd3: the window's
first paint went from a median 3.53 s to 1.08 s. Three things moved:

* **The speech models are not joined before the window.** `PushToTalk` takes
  the warm-up as `arriving` and installs recogniser and matcher together at
  the first press after they land. A press before then is TOLD so - never
  silence, never "speech isn't available".
* **The speech load is held until the deferred screens are warm**, and is
  started by the first press or session if nothing else has started it.
* **The voice engine is chosen on its own thread** beside the screens, and
  collected - not re-chosen - by the controller.
* **Car is built after the first paint**, like Reference and Settings.

Each test here pins one of the guarantees that made a move safe. The one that
matters most on race day is that no arrangement of timing can leave push to
talk silently dead, or answer a question with half a speech stack.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

from pitcrew.engineer import gate, ptt, voice
from pitcrew.engineer.ptt import PushToTalk


@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _pump(qt_app, turns=40):
    for _ in range(turns):
        qt_app.processEvents()


# ------------------------------------------------------------------ doubles

class Recogniser:
    name = "moonshine"

    def __init__(self, heard="how are my tyres"):
        self.heard, self.last_reason = heard, None
        self.begun = 0
        self.ended = 0

    def begin(self):
        self.begun += 1

    def end(self):
        self.ended += 1
        return self.heard


class Matcher:
    def __init__(self):
        self.asked: list[str] = []

    def match(self, heard):
        self.asked.append(heard)
        return "tyres", 0.05


def held_warm_up(recogniser=None, matcher=None):
    """A warm-up whose thread runs until `release` is set, then lands the
    pair it was given - the shape `start_warm_up` returns."""
    release = threading.Event()
    outcome: dict = {}

    def load():
        try:
            release.wait(30)
            outcome["recogniser"] = recogniser
            outcome["matcher"] = matcher
        finally:
            outcome["landed"] = True

    thread = threading.Thread(target=load, daemon=True, name="warm-speech")
    return (outcome, thread), release


def talk_with(arriving, *, toggle=True):
    said: list[str] = []
    talk = PushToTalk(snapshot=lambda: {}, speak=said.append,
                      arriving=arriving, toggle=toggle, bursts=(None, None))
    return talk, said


def wait_landed(warm, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not ptt.speech_landed(warm):
        assert time.monotonic() < deadline, "the warm-up never landed"
        time.sleep(0.005)


# ------------------------------------------------ a press before it lands

def test_a_press_before_the_models_land_is_told_so_out_loud():
    """Toggle mode, the shipped default. The radio must NOT open - there is
    no recogniser to hear him - and he must hear the reason, in the words
    `gate` owns for it."""
    real = Recogniser()
    warm, release = held_warm_up(real, Matcher())
    talk, said = talk_with(warm)
    ptt.begin_warm_up(warm)
    try:
        talk.tap()
        assert said == [gate.spoken_reason(gate.NOT_READY)]
        assert talk.recording is False
        assert real.begun == 0
        assert talk.last_reason == gate.NOT_READY
    finally:
        release.set()


def test_still_loading_is_not_reported_as_no_speech():
    """`available` False is spoken as "Speech isn't available on this
    machine" - a determined negative for a state one second from ready."""
    warm, release = held_warm_up(Recogniser(), Matcher())
    talk, _said = talk_with(warm)
    try:
        assert talk.available is True
        assert talk.speech_ready is False
    finally:
        release.set()


def test_a_hold_press_that_straddles_the_landing_is_answered_as_not_ready():
    """Begun on nothing, ended after the models landed: the question was
    never recorded, so it must not be handed to the real recogniser's
    `end()` - that would transcribe a stream that was never opened."""
    real = Recogniser()
    warm, release = held_warm_up(real, Matcher())
    talk, said = talk_with(warm, toggle=False)
    ptt.begin_warm_up(warm)
    talk.begin()
    release.set()
    wait_landed(warm)
    talk.end()
    assert said == [gate.spoken_reason(gate.NOT_READY)]
    assert real.begun == 0 and real.ended == 0


# ------------------------------------------------------- once it has landed

def test_the_first_press_after_landing_uses_the_real_pair():
    real, matcher = Recogniser(), Matcher()
    warm, release = held_warm_up(real, matcher)
    talk, said = talk_with(warm)
    ptt.begin_warm_up(warm)
    release.set()
    wait_landed(warm)

    talk.tap()                      # open
    assert talk.recording is True
    talk.tap()                      # close, transcribe, answer
    assert real.begun == 1 and real.ended == 1
    # The matcher that landed with it was the one that judged the question.
    assert matcher.asked == ["how are my tyres"]
    assert said and said[-1] != gate.spoken_reason(gate.NOT_READY)


def test_the_pair_is_installed_together_or_not_at_all():
    """Free dictation with `matcher=None` skips all five stages of the gate.
    So a recogniser must never be visible before its matcher is."""
    real, matcher = Recogniser(), Matcher()
    warm, release = held_warm_up(real, matcher)
    talk, _said = talk_with(warm)
    ptt.begin_warm_up(warm)
    assert talk._recogniser is None and talk._matcher is None
    release.set()
    wait_landed(warm)
    assert talk.speech_ready is True
    assert talk._recogniser is real and talk._matcher is matcher


def test_a_barren_landing_is_the_same_none_the_inline_build_gives():
    """Nothing loaded: exactly the un-warmed behaviour, including its words."""
    warm, release = held_warm_up(None, None)
    talk, said = talk_with(warm)
    ptt.begin_warm_up(warm)
    release.set()
    wait_landed(warm)
    assert talk.speech_ready is True
    assert talk.available is False
    talk.begin()
    talk.end()
    assert said == ["Speech isn't available on this machine."]


# ------------------------------------------------ nothing can stay held back

def test_the_first_press_starts_a_load_nobody_released():
    """The launch holds the load until the screens are warm. If that never
    happens, the button must not be dead for the session."""
    real = Recogniser()
    outcome: dict = {}
    started = threading.Event()

    def load():
        started.set()
        outcome.update(recogniser=real, matcher=Matcher(), landed=True)

    thread = threading.Thread(target=load, daemon=True)
    talk, said = talk_with((outcome, thread))
    talk.tap()
    assert started.wait(5), "the press did not start the held load"


def test_arming_for_a_session_starts_a_load_nobody_released(caplog):
    outcome: dict = {}
    thread = threading.Thread(
        target=lambda: outcome.update(recogniser=None, matcher=None,
                                      landed=True), daemon=True)
    talk, _said = talk_with((outcome, thread))
    with caplog.at_level("WARNING"):
        talk.start()                  # no listener: arms nothing but this
    thread.join(5)
    assert thread.ident is not None
    assert any("had not been started" in r.getMessage()
               for r in caplog.records)


def test_begin_warm_up_starts_once_and_only_once():
    outcome: dict = {}
    runs: list[int] = []
    thread = threading.Thread(target=lambda: runs.append(1), daemon=True)
    assert ptt.begin_warm_up((outcome, thread)) is True
    assert ptt.begin_warm_up((outcome, thread)) is False   # no RuntimeError
    thread.join(5)
    assert runs == [1]


def test_a_dead_thread_is_landed_even_without_the_flag():
    """A reference that nothing can retire is a latch (CLAUDE.md rule 10):
    waiting on a thread that has ended would say "still starting up" for
    the rest of the session."""
    thread = threading.Thread(target=lambda: None)
    thread.start()
    thread.join()
    assert ptt.speech_landed(({}, thread)) is True


def test_an_unstarted_warm_up_is_not_landed():
    thread = threading.Thread(target=lambda: None)
    assert ptt.speech_landed(({}, thread)) is False


def test_start_false_builds_the_thread_without_running_it(monkeypatch):
    monkeypatch.setattr(ptt, "best_recogniser_for",
                        lambda backend, phrases=None: "recogniser")
    monkeypatch.setattr(ptt, "matcher_for", lambda recogniser: "matcher")
    outcome, thread = ptt.start_warm_up("moonshine", start=False)
    assert thread.ident is None and not outcome
    ptt.begin_warm_up((outcome, thread))
    thread.join(10)
    assert outcome == {"recogniser": "recogniser", "matcher": "matcher",
                       "landed": True}


def test_landed_is_set_even_when_the_load_raises(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("no model")

    monkeypatch.setattr(ptt, "best_recogniser_for", boom)
    monkeypatch.setattr(ptt, "matcher_for", boom)
    outcome, thread = ptt.start_warm_up("moonshine")
    thread.join(10)
    assert outcome["landed"] is True
    assert outcome["recogniser"] is None and outcome["matcher"] is None


def test_a_barren_warm_up_tries_again_on_its_own_thread(monkeypatch):
    """`speech_from` retried a barren warm-up inline on the Qt thread. With
    no join there, the retry moved here - it must still happen."""
    calls: list[str] = []

    def recogniser_for(backend, phrases=None):
        calls.append(threading.current_thread().name)
        return None

    monkeypatch.setattr(ptt, "best_recogniser_for", recogniser_for)
    monkeypatch.setattr(ptt, "_under_pytest", lambda: False)
    outcome, thread = ptt.start_warm_up("moonshine")
    thread.join(10)
    assert calls == ["warm-speech", "warm-speech"]
    assert outcome["landed"] is True


# ----------------------------------------------------- the controller's side

def test_the_controller_does_not_wait_for_the_models(qt_app, store):
    """The join this whole change removes. The warm-up here would block for
    thirty seconds; the controller must be built long before that."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    warm, release = held_warm_up(Recogniser(), Matcher())
    ptt.begin_warm_up(warm)
    started = time.perf_counter()
    try:
        controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                       warm=warm)
        took = time.perf_counter() - started
        assert took < 10, f"the controller waited {took:.1f}s"
        assert controller.ptt._arriving is warm
        assert controller.ptt.speech_ready is False
        controller.shutdown()
    finally:
        release.set()


# --------------------------------------------------------- the voice engine

def test_no_build_means_choose_inline_exactly_as_before():
    assert voice.engine_from(None) is voice.AUTO


def test_the_built_engine_is_the_one_voice_gets(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(voice, "_best_engine", lambda: sentinel)
    build = voice.start_engine_build()
    assert build[1].name == "voice-engine" and build[1].daemon
    assert voice.engine_from(build) is sentinel


def test_no_engine_on_the_machine_is_an_answer_not_a_retry(monkeypatch):
    calls: list[int] = []

    def best():
        calls.append(1)
        return None

    monkeypatch.setattr(voice, "_best_engine", best)
    assert voice.engine_from(voice.start_engine_build()) is None
    assert calls == [1]
    assert voice.Voice(None).enabled is False


def test_a_build_that_raised_falls_back_to_the_inline_choice(monkeypatch,
                                                             caplog):
    def boom():
        raise RuntimeError("import exploded")

    monkeypatch.setattr(voice, "_best_engine", boom)
    with caplog.at_level("ERROR"):
        chosen = voice.engine_from(voice.start_engine_build())
    assert chosen is voice.AUTO
    assert any("did not build off the Qt thread" in r.getMessage()
               for r in caplog.records)


# --------------------------------------------------------------- the window

def test_warming_the_screens_releases_the_speech_load(qt_app, store):
    from pitcrew.app import PitCrewWindow

    warm, release = held_warm_up(Recogniser(), Matcher())
    window = PitCrewWindow(store, warm=warm)
    try:
        assert warm[1].ident is None, "started before the screens"
        window.warm_screens()
        _pump(qt_app)
        assert warm[1].ident is not None, "never released"
        assert window.car_screen is not None
        # Released once: a second end of the chain is a no-op, not a
        # RuntimeError from starting a thread twice.
        window.release_speech()
    finally:
        release.set()
        window.controller.shutdown()


def test_a_screen_that_will_not_build_still_releases_the_speech_load(
        qt_app, store, monkeypatch):
    from pitcrew.app import PitCrewWindow

    warm, release = held_warm_up(Recogniser(), Matcher())
    window = PitCrewWindow(store, warm=warm)

    def boom(**_kwargs):
        raise RuntimeError("this screen will not build")

    monkeypatch.setitem(window.LATE_SCREENS, 1,
                        ("car_screen", boom, "attach_car_screen"))
    try:
        window.warm_screens()
        _pump(qt_app)
        assert warm[1].ident is not None
    finally:
        release.set()
        window.controller.shutdown()


def test_after_first_paint_runs_once_even_with_no_paint(qt_app, store,
                                                        monkeypatch):
    """Offscreen never paints a hidden window, which is exactly the case
    the backstop is for: minimised at launch must still warm."""
    import pitcrew.app as app_module
    from pitcrew.app import PitCrewWindow

    monkeypatch.setattr(app_module, "FIRST_PAINT_BACKSTOP_MS", 1)
    window = PitCrewWindow(store)
    ran: list[int] = []
    try:
        window.after_first_paint(lambda: ran.append(1))
        deadline = time.monotonic() + 5
        while not ran and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.005)
        _pump(qt_app)
        assert ran == [1]
    finally:
        window.controller.shutdown()


def test_the_first_frame_starts_the_speech_load_before_any_late_screen(
        qt_app, store, monkeypatch):
    """Speech first, then the screens - and every screen still built."""
    from pitcrew.app import PitCrewWindow

    warm, release = held_warm_up(Recogniser(), Matcher())
    window = PitCrewWindow(store, warm=warm)
    started_before: list[bool] = []
    factory = window.LATE_SCREENS[1][1]

    def spy(**kwargs):
        started_before.append(warm[1].ident is not None)
        return factory(**kwargs)

    monkeypatch.setitem(window.LATE_SCREENS, 1,
                        (window.LATE_SCREENS[1][0], spy,
                         window.LATE_SCREENS[1][2]))
    try:
        window.after_launch_paint()
        _pump(qt_app)
        assert started_before == [True]
        assert window.car_screen is not None
        assert window.reference_screen is not None
        assert window.settings_screen is not None
    finally:
        release.set()
        window.controller.shutdown()


def test_the_launch_hangs_the_speech_load_on_the_first_frame():
    """`main` is not run by the suite (it opens the real database), so the
    wiring is pinned by its text: the first-paint hook is the one that
    starts speech, and the backstop still finishes the launch."""
    import inspect

    import pitcrew.app as app_module

    source = inspect.getsource(app_module.main)
    assert "window.after_first_paint(window.after_launch_paint)" in source
    assert ("QTimer.singleShot(SPEECH_BACKSTOP_MS, window.finish_launch)"
            in source)


def test_the_car_screen_is_not_on_the_path_to_the_window(qt_app, store):
    from pitcrew.app import PitCrewWindow

    window = PitCrewWindow(store)
    try:
        assert window.car_screen is None
        assert window.controller.car_screen is None
    finally:
        window.controller.shutdown()


def test_a_late_car_screen_gets_the_catalogue_and_the_active_car(qt_app,
                                                                 store):
    """Everything the eager path pushed into it at launch: the car groups
    `refresh_catalogs` built, and the active event's car."""
    from pitcrew.app import PitCrewWindow
    from pitcrew.store import catalogs

    car = next(iter(catalogs.cars_by_category().values()))[0]
    event_id = store.create_event(name="Latency", track="Suzuka",
                                  car_name=car)
    store.set_state("active_event_id", event_id)
    window = PitCrewWindow(store)
    try:
        window.rail.select(1)
        screen = window.car_screen
        assert screen is not None
        assert screen.current_car() == car
        assert screen.car_edit.combo.count() > 1
        # Wired once, and to the controller.
        assert screen.receivers(screen.saved) == 1
        assert screen.receivers(screen.car_changed) == 1
    finally:
        window.controller.shutdown()


# ------------------------------------------------ one calendar read per paint

@pytest.fixture()
def counted_hub(monkeypatch):
    """The hub replaced by one that counts its reads."""
    import pitcrew.hub.calendar as calendar
    import pitcrew.hub.read as read

    reads: list[int] = []

    class Hub:
        available = True

        def close(self):
            pass

    def upcoming(hub, *, me=None, now=None, stored_events=None):
        reads.append(len(stored_events or []))
        return []

    monkeypatch.setattr(read, "Hub", Hub)
    monkeypatch.setattr(calendar, "upcoming", upcoming)
    return reads


def _controller(store):
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    return PitCrewController(store, EventScreen(), PracticeScreen())


def test_the_first_paint_reads_the_calendar_once(qt_app, store, counted_hub):
    """Three questions, one read: it was three ~30 ms reads, all in front
    of the window's first frame."""
    controller = _controller(store)
    asked: list[int] = []
    real = controller.hub_proposals

    def counting():
        asked.append(1)
        return real()

    controller.hub_proposals = counting
    try:
        store.set_state("active_event_id",
                        store.create_event(name="Memo", track="Suzuka"))
        counted_hub.clear()
        controller._first_paint_done = False
        controller._first_paint_work()
        assert len(asked) >= 2, "the premise: it is asked more than once"
        assert len(counted_hub) == 1
        # And the memo does not outlive the call.
        assert controller._hub_memo is None
    finally:
        controller.shutdown()


def test_a_round_written_in_between_is_read_afresh(qt_app, store,
                                                   counted_hub):
    """The memo is keyed on the events it was read against, so a round
    linked or created mid-way is never answered from before the write."""
    controller = _controller(store)
    try:
        counted_hub.clear()
        controller._hub_memo = {}
        controller.hub_proposals()
        controller.hub_proposals()
        assert len(counted_hub) == 1
        store.create_event(name="Created mid-way", track="Suzuka")
        controller.hub_proposals()
        assert len(counted_hub) == 2
        assert counted_hub[-1] == counted_hub[0] + 1
    finally:
        controller._hub_memo = None
        controller.shutdown()


def test_outside_the_first_paint_every_call_reads(qt_app, store, counted_hub):
    """No cache across calls - the reason `hub_proposals` gives for having
    none still holds everywhere but that one synchronous call."""
    controller = _controller(store)
    try:
        counted_hub.clear()
        controller.hub_proposals()
        controller.hub_proposals()
        assert len(counted_hub) == 2
    finally:
        controller.shutdown()
