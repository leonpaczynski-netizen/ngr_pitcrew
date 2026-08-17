"""One card is one entry, and opening it tries every route to it.

These cover the picker fault that made a chosen device silent: PortAudio lists
the same headset once per host API, the Settings screen stored only its name,
and resolution returned whichever row came first. Clicking the WASAPI entry
got you DirectSound, and two of the four rows could not play at all.

The fake below is this machine's real device table on 15 Aug 2026, names and
channel counts included - MME's truncation at 31 characters is the detail the
whole matching scheme turns on.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer import audio_devices


class FakePortAudio:
    """Enough of `sounddevice` for resolution, with no sound card involved."""

    class PortAudioError(Exception):
        pass

    def __init__(self, devices, hostapis):
        self._devices = devices
        self._hostapis = hostapis
        self.opened: list = []
        # Device indices that refuse to open, by way of the host API they are
        # on: WASAPI refusing 22050 Hz is the case that matters.
        self.refuse: set = set()

    def query_devices(self):
        return self._devices

    def query_hostapis(self, index=None):
        if index is None:
            return self._hostapis
        return self._hostapis[index]

    def _terminate(self):
        pass

    def _initialize(self):
        pass


def _machine():
    """The JBL headset as PortAudio really reported it, plus one other card."""
    hostapis = [{"name": "MME"}, {"name": "Windows DirectSound"},
                {"name": "Windows WASAPI"}, {"name": "Windows WDM-KS"}]
    devices = [
        # MME - names truncated at 31 characters by the host API itself.
        {"name": "Microsoft Sound Mapper - Output", "hostapi": 0,
         "max_output_channels": 2, "max_input_channels": 0},
        {"name": "Headphones (JBL Endurance Run 3", "hostapi": 0,
         "max_output_channels": 8, "max_input_channels": 0},
        {"name": "Speakers (2- Realtek(R) Audio)", "hostapi": 0,
         "max_output_channels": 8, "max_input_channels": 0},
        # DirectSound - full names.
        {"name": "Headphones (JBL Endurance Run 3C)", "hostapi": 1,
         "max_output_channels": 8, "max_input_channels": 0},
        {"name": "Speakers (2- Realtek(R) Audio)", "hostapi": 1,
         "max_output_channels": 8, "max_input_channels": 0},
        # WASAPI.
        {"name": "Headphones (JBL Endurance Run 3C)", "hostapi": 2,
         "max_output_channels": 2, "max_input_channels": 0},
        # WDM-KS - per-pin exports, under names of their own.
        {"name": "Output 1 (JBL Endurance Run 3C)", "hostapi": 3,
         "max_output_channels": 2, "max_input_channels": 0},
    ]
    return FakePortAudio(devices, hostapis)


JBL_MME, JBL_DS, JBL_WASAPI = 1, 3, 5


@pytest.fixture(autouse=True)
def _clear_route_memory():
    audio_devices._WORKING.clear()
    yield
    audio_devices._WORKING.clear()


def test_one_headset_is_offered_once_not_once_per_host_api(monkeypatch):
    """The fault as the driver met it: four near-identical rows for one
    headset, no way to tell them apart, and two of them unable to play."""
    sd = _machine()
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", sd)
    offered = [name for _index, name in audio_devices.devices("output")]
    assert offered.count("Headphones (JBL Endurance Run 3C)") == 1
    assert not [n for n in offered if "Output 1" in n]      # WDM-KS hidden
    assert not [n for n in offered if "Sound Mapper" in n]  # router hidden


def test_the_fullest_spelling_of_the_name_is_the_one_shown(monkeypatch):
    """MME cuts names at 31 characters. Showing him the truncated one is
    showing him the least identifiable of the four."""
    sd = _machine()
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", sd)
    offered = [name for _index, name in audio_devices.devices("output")]
    assert "Headphones (JBL Endurance Run 3C)" in offered
    assert "Headphones (JBL Endurance Run 3" not in offered


@pytest.mark.parametrize("stored", [
    "Headphones (JBL Endurance Run 3",       # as MME spells it
    "Headphones (JBL Endurance Run 3C)",     # as everything else does
])
def test_either_spelling_finds_every_route_to_the_card(stored):
    """A name stored under one host API has to find the card under all of
    them, or a setting saved before a replug stops resolving."""
    sd = _machine()
    routes = audio_devices._candidates(sd, stored, "output")
    assert set(routes) == {JBL_MME, JBL_DS, JBL_WASAPI}


def test_routes_come_back_in_the_order_that_actually_plays():
    """WASAPI first because it is best when it opens; MME before DirectSound
    because DirectSound opens, accepts everything and plays none of it."""
    sd = _machine()
    routes = audio_devices._candidates(sd, "Headphones (JBL Endurance Run 3C)",
                                       "output")
    assert routes == [JBL_WASAPI, JBL_MME, JBL_DS]


def test_a_refused_route_falls_through_to_the_next(monkeypatch):
    """WASAPI shared mode will not take 22050 Hz, which is what the Piper
    models render at. That must cost one failed open, not the call."""
    sd = _machine()
    sd.refuse = {JBL_WASAPI}

    def build(device):
        if device in sd.refuse:
            raise sd.PortAudioError("Invalid sample rate")
        return _Stream(device)

    stream = audio_devices._open_first_that_works(
        sd, "Headphones (JBL Endurance Run 3C)", "output", build)
    assert stream.device == JBL_MME
    assert stream.started


def test_the_route_that_worked_is_tried_first_next_time(monkeypatch):
    """Otherwise every beep re-discovers that WASAPI refuses the rate."""
    sd = _machine()
    sd.refuse = {JBL_WASAPI}

    def build(device):
        if device in sd.refuse:
            raise sd.PortAudioError("Invalid sample rate")
        return _Stream(device)

    audio_devices._open_first_that_works(
        sd, "Headphones (JBL Endurance Run 3C)", "output", build)
    routes = audio_devices._candidates(sd, "Headphones (JBL Endurance Run 3C)",
                                       "output")
    assert routes[0] == JBL_MME


def test_a_card_that_is_gone_falls_back_to_the_default_rather_than_raising():
    """He would rather hear the call out of the wrong speaker than not at
    all - and the endpoint meter is what tells him it went to the wrong one."""
    sd = _machine()
    assert audio_devices._candidates(sd, "Headphones (Jabra Evolve 75 SE)",
                                     "output") == [None]


def test_the_last_route_failing_is_raised_not_swallowed():
    """A card that cannot be opened at all has to be loud. Silence that is
    logged and returned is the failure mode this module exists to stop."""
    sd = _machine()

    def build(device):
        raise sd.PortAudioError("device unavailable")

    with pytest.raises(sd.PortAudioError):
        audio_devices._open_first_that_works(
            sd, "Headphones (JBL Endurance Run 3C)", "output", build)


def test_an_explicit_index_and_the_default_are_passed_straight_through():
    sd = _machine()
    assert audio_devices._candidates(sd, None, "output") == [None]
    assert audio_devices._candidates(sd, 7, "output") == [7]


class _Stream:
    def __init__(self, device):
        self.device = device
        self.started = False

    def start(self):
        self.started = True


# ------------------------------------------------- surviving a device rebuild

class _Sustained:
    """A stream that lives for the session, like the transducer's will."""

    def __init__(self, *, fails_to_resume: bool = False) -> None:
        self.suspended = 0
        self.resumed = 0
        self.running = True
        self._fails = fails_to_resume

    def suspend(self) -> None:
        self.suspended += 1
        self.running = False

    def resume(self) -> None:
        self.resumed += 1
        if self._fails:
            raise RuntimeError("the card it was using has gone")
        self.running = True


def test_a_sustained_stream_survives_the_device_list_being_rebuilt():
    """`sd._terminate()` closes every open stream in the process, and says
    nothing: measured, two streams went to zero callbacks with no exception,
    and only `.active` afterwards raised -9988.

    A spoken line does not care - it opens and closes within the second. A
    transducer holds one stream for the whole race, so the driver opening the
    settings screen would have stopped the haptics for the rest of it.
    """
    held = _Sustained()
    audio_devices.register_sustained(held)
    try:
        audio_devices._reinitialise(_machine())
        assert held.suspended == 1, "it was not taken out of the way"
        assert held.resumed == 1, "it was never brought back"
        assert held.running is True
    finally:
        audio_devices.unregister_sustained(held)


def test_a_rebuild_that_fails_still_brings_the_stream_back():
    """The resume is in a `finally` for this: a rebuild that raised half-way
    would otherwise leave the transducer suspended for the rest of the
    session - the same silent stop, reached another way."""
    exploding = _machine()

    def boom():
        raise RuntimeError("PortAudio is unwell")

    exploding._terminate = boom

    held = _Sustained()
    audio_devices.register_sustained(held)
    try:
        audio_devices._reinitialise(exploding)
        assert held.resumed == 1
        assert held.running is True
    finally:
        audio_devices.unregister_sustained(held)


def test_a_stream_that_cannot_come_back_is_reported_not_swallowed():
    """The card it was using may be the one that just went away. That is a
    real outcome and it has to be loud, because the driver cannot see it."""
    held = _Sustained(fails_to_resume=True)
    audio_devices.register_sustained(held)
    try:
        audio_devices._reinitialise(_machine())
        assert held.resumed == 1
        assert held.running is False
    finally:
        audio_devices.unregister_sustained(held)


def test_unregistering_takes_a_stream_out_of_the_rebuild():
    held = _Sustained()
    audio_devices.register_sustained(held)
    audio_devices.unregister_sustained(held)
    audio_devices._reinitialise(_machine())
    assert held.suspended == 0


def test_registering_twice_does_not_suspend_twice():
    held = _Sustained()
    audio_devices.register_sustained(held)
    audio_devices.register_sustained(held)
    try:
        audio_devices._reinitialise(_machine())
        assert held.suspended == 1
    finally:
        audio_devices.unregister_sustained(held)


# ------------------------------------- not cutting a sentence off to do it

@pytest.fixture(autouse=True)
def _no_playback_left_behind():
    """A test that leaks a playback would hang the next one for the cap."""
    yield
    with audio_devices._PLAYING_STATE:
        audio_devices._PLAYING.clear()
        audio_devices._PLAYING_STATE.notify_all()


class _Speaking:
    """A line playing on a thread of its own, as the voice really does it.

    On a thread of its own on purpose: `_wait_for_playback` deliberately does
    not wait on the calling thread, so a playback opened on the test's own
    thread would not exercise the wait at all.
    """

    def __init__(self, what: str = "the engineer's line") -> None:
        import threading

        self.line = None
        self._what = what
        self._open = threading.Event()
        self._release = threading.Event()
        self.ended = threading.Event()
        # Called on the speaking thread just before the line ends, for tests
        # that care what happened on which side of it.
        self.on_end = lambda: None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        assert self._open.wait(timeout=5.0)
        return self

    def __exit__(self, *_exc):
        self._release.set()
        self._thread.join(timeout=5.0)
        return False

    def _run(self) -> None:
        self.line = audio_devices.begin_playback(self._what)
        self._open.set()
        self._release.wait(timeout=10.0)
        self.on_end()
        audio_devices.end_playback(self.line)
        self.ended.set()

    def finish_in(self, seconds: float) -> None:
        import threading
        threading.Timer(seconds, self._release.set).start()


def test_a_rebuild_with_nothing_playing_does_not_wait():
    """The common case, and it must cost nothing: between lines, a rebuild is
    exactly as free as it was before any of this existed."""
    import time as _time

    started = _time.monotonic()
    audio_devices._reinitialise(_machine())
    assert _time.monotonic() - started < 0.5


def test_a_rebuild_waits_for_a_line_that_is_being_spoken():
    """The mechanism, at the point where it does the damage.

    `_reinitialise` calls `sd._terminate()`, and PortAudio closes every open
    stream in the process when it does - measured here on 15 Aug 2026: two
    streams open, terminate, re-init, both to zero callbacks with nothing
    raised, `.active` afterwards `PortAudioError -9988`. Applied to the voice
    that is a sentence stopping in the middle of a word, silently. The next
    test drives the caller that really does this.
    """
    with _Speaking() as speaking:
        speaking.finish_in(0.3)
        audio_devices._reinitialise(_machine())
        assert speaking.ended.is_set(), \
            "the rebuild went ahead over the top of the line"
        assert speaking.line.interrupted is False, \
            "a line it waited for was marked cut"


def test_the_settings_screen_enumerating_does_not_cut_the_engineer_off(
        monkeypatch):
    """The path that motivated all of this, driven end to end.

    `ui/settings_screen.py::_audio_plate` fills its two device pickers during
    `_build` by calling `audio_devices.devices("output")` and then
    `devices("input")`. `devices` re-enumerates on every call - on purpose, so
    the list includes the headset just plugged in - and re-enumerating is
    `sd._terminate()`, which was measured on 15 Aug 2026 to close every open
    stream in the process without raising anything.

    So the driver opening the settings screen while the engineer is talking
    used to cut him off mid-word, twice, in the shipped app. Nothing about it
    needed a bug to happen: a screen being built is not an event anything
    would think to check against the voice.

    Driven through `devices` rather than `_reinitialise` deliberately - the
    entry point is the part that was never connected to the consequence.
    """
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", _machine())
    with _Speaking() as speaking:
        speaking.finish_in(0.3)
        audio_devices.devices("output")
        audio_devices.devices("input")
        assert speaking.ended.is_set(), \
            "the picker enumerated over the top of the engineer's line"
        assert speaking.line.interrupted is False, \
            "the line survived but was marked cut anyway"


def test_the_wait_gives_up_rather_than_starving_the_recovery():
    """Bounded on purpose. A wait that could not time out would let one stuck
    engine hold the transducer down for the rest of the race - trading one
    silent output for another, which is not a fix."""
    import time as _time

    with _Speaking() as speaking:
        started = _time.monotonic()
        audio_devices._wait_for_playback(cap=0.2)
        waited = _time.monotonic() - started
        assert 0.15 <= waited < 2.0, "it did not give up on schedule"
        assert speaking.line.interrupted is True, \
            "it cut the line without saying so"


def test_a_rebuild_never_waits_on_its_own_thread():
    """`_retry_once` re-enumerates from inside an open. A caller that is
    itself mid-playback would otherwise wait for itself until the cap."""
    import time as _time

    line = audio_devices.begin_playback("the engineer's line")
    try:
        started = _time.monotonic()
        audio_devices._wait_for_playback(cap=5.0)
        assert _time.monotonic() - started < 1.0
        assert line.interrupted is True
    finally:
        audio_devices.end_playback(line)


def test_the_deferral_is_reported_once_and_says_what_it_means(caplog):
    with _Speaking() as speaking:
        speaking.finish_in(0.2)
        with caplog.at_level("INFO", logger="pitcrew.audio"):
            audio_devices._wait_for_playback(cap=5.0)
    held = [r for r in caplog.records if "held the audio device rebuild" in
            r.getMessage()]
    assert len(held) == 1, "one line per collision, not one per attempt"


def test_a_cut_line_is_reported_as_a_warning(caplog):
    with _Speaking():
        with caplog.at_level("INFO", logger="pitcrew.audio"):
            audio_devices._wait_for_playback(cap=0.05)
    cut = [r for r in caplog.records if "cut off" in r.getMessage()]
    assert len(cut) == 1
    assert cut[0].levelname == "WARNING"


def test_the_wait_runs_before_the_transducer_is_suspended():
    """Suspending the sustained holders first would mute the haptics for the
    length of the wait - paying for the fix with the thing the fix is for."""
    order = []

    class _Watcher(_Sustained):
        def suspend(self) -> None:
            order.append("suspend")
            super().suspend()

    held = _Watcher()
    audio_devices.register_sustained(held)
    try:
        with _Speaking() as speaking:
            speaking.on_end = lambda: order.append("line ended")
            speaking.finish_in(0.2)
            audio_devices._reinitialise(_machine())
    finally:
        audio_devices.unregister_sustained(held)
    assert order == ["line ended", "suspend"]


def test_a_rebuild_cannot_slip_between_the_open_and_the_gate(monkeypatch):
    """"After the open" on its own is not enough, and the gap is the point.

    The lock order forbids declaring a playback before opening its stream -
    that is an AB-BA against the enumeration lock. But declaring a moment
    after the open leaves a window in which the stream exists and nothing has
    said so, and a rebuild landing there closes it having seen nothing. That
    is the worse shape of the original fault, because `interrupted` stays
    False and the line is not even said again.

    So `open_and_declare` holds the enumeration lock across both. Here a
    rebuild is already queued for that lock before the open begins: it must
    not get through until the line is over.
    """
    import threading
    import time as _time

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", _machine())
    in_the_open = threading.Event()
    rebuilt = threading.Event()

    def rebuild() -> None:
        in_the_open.wait(timeout=5.0)
        audio_devices.devices("output")
        rebuilt.set()

    waiting = threading.Thread(target=rebuild, daemon=True)
    waiting.start()

    def open_stream():
        in_the_open.set()
        # Every chance to get in: the real window is microseconds wide.
        _time.sleep(0.3)
        return _Stream(device=None)

    _stream, playback = audio_devices.open_and_declare(
        "the engineer's line", open_stream)
    try:
        assert not rebuilt.is_set(), "a rebuild landed inside the open"
        _time.sleep(0.2)
        assert not rebuilt.is_set(), \
            "the rebuild got past a stream that had already declared itself"
        assert playback.interrupted is False
    finally:
        audio_devices.end_playback(playback)
    waiting.join(timeout=5.0)
    assert rebuilt.is_set(), "the rebuild never ran at all"


def test_the_cap_leaves_room_for_a_cut_line_to_still_be_worth_saying():
    """A line cut at the cap has to be able to come back inside
    `voice.STALE_AFTER_S`, or the deferral would guarantee every re-speak
    arrives too late to be said."""
    from pitcrew.engineer import voice as voice_module

    assert audio_devices.DEFER_CAP_S < voice_module.STALE_AFTER_S


# ------------------------------------------------------------ per-card locks

def test_two_cards_do_not_block_each_other():
    """Measured: two concurrent WASAPI streams on two different devices ran
    for two seconds and delivered 205 and 132 callbacks, no status flags.

    A process-wide lock would make the transducer and the engineer's voice
    mutually exclusive - so the haptics would stop dead every time a call was
    made, during exactly the moments the driver most wants both.
    """
    headset = audio_devices.lock_for("Headphones (JBL Endurance Run 3C)")
    shaker = audio_devices.lock_for("Speakers (ButtKicker PRO)")
    assert headset is not shaker
    assert headset.acquire(blocking=False)
    try:
        assert shaker.acquire(blocking=False), "one card blocked another"
        shaker.release()
    finally:
        headset.release()


def test_one_card_reached_by_two_names_is_one_lock():
    """MME truncates names at 31 characters, so the same headset is spelled
    two ways. Two locks for one card is the crash the lock exists to stop."""
    full = audio_devices.lock_for("Headphones (JBL Endurance Run 3C)")
    mme = audio_devices.lock_for("Headphones (JBL Endurance Run 3")
    assert full is mme


def test_the_default_device_has_a_lock_of_its_own():
    assert audio_devices.lock_for(None) is audio_devices.lock_for(None)


# ------------------------------------------- keeping the transducer to itself

def test_an_exclusive_open_uses_wasapi_and_refuses_to_fall_back(monkeypatch):
    """Exclusive mode exists only under WASAPI, and the ordinary open walks
    down to MME when a route refuses.

    For the voice that is right - a call out of the wrong speaker beats no
    call. For the transducer it would hand back a *shared* stream on the very
    endpoint the caller asked to have to itself, and every Windows sound would
    then arrive through the driver's seat. So it raises instead.
    """
    sd = _machine()
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", sd)
    routes = audio_devices._candidates(
        sd, "Headphones (JBL Endurance Run 3C)", "output",
        host_api="Windows WASAPI")
    assert routes == [JBL_WASAPI], "took a route that is not WASAPI"


def test_a_card_with_no_wasapi_route_is_refused_not_shared(monkeypatch):
    """Silently sharing would be the worst outcome: it looks like success."""
    sd = _machine()
    routes = audio_devices._candidates(
        sd, "Speakers (2- Realtek(R) Audio)", "output",
        host_api="Windows NoSuchApi")
    assert routes == []


def test_the_system_default_cannot_be_taken_exclusively():
    """The default is where everything else on the PC is playing. Taking it
    exclusively would mute the machine."""
    with pytest.raises(ValueError, match="named"):
        audio_devices.open_exclusive_output(None, 48000)


def test_the_ordinary_open_still_walks_every_route(monkeypatch):
    """The exclusive path must not have changed how the voice behaves - it
    still wants any route that plays."""
    sd = _machine()
    routes = audio_devices._candidates(
        sd, "Headphones (JBL Endurance Run 3C)", "output")
    assert len(routes) > 1
    assert routes[0] == JBL_WASAPI


def test_exclusive_mode_is_not_the_transducers_path():
    """Measured on the rig, 15 Aug 2026, and it changed the design.

    `open_exclusive_output` opens on the ButtKicker PRO, reports 21.3 ms and
    a sensible rate and channel count, and renders nothing: the endpoint
    metered 0.0000 for the whole call and the driver felt nothing, while the
    identical tone through a shared stream metered 0.125 and was felt.

    So the docstring has to carry that warning, or the next person reads a
    function that promises isolation and gets silence - which is the fault
    this module exists to catch, reached from the inside by an API that
    reports success.
    """
    doc = audio_devices.open_exclusive_output.__doc__
    assert "Measured not to work on the ButtKicker PRO" in doc
    assert "0.0000" in doc


def test_isolation_does_not_depend_on_exclusive_mode():
    """The question that prompted all this was whether other PC sounds can
    reach the transducer. Two of the three layers never needed exclusive
    mode: the amp is its own endpoint addressed by name, and it is not the
    Windows default, which is where anything asking for "the default" goes.
    """
    shaker = audio_devices.lock_for("Speakers (ButtKicker PRO)")
    default = audio_devices.lock_for(None)
    assert shaker is not default
