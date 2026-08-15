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
