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
