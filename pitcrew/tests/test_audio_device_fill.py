"""Filling the sound-device pickers when the screen is opened, not at launch.

Enumerating devices runs `sd._terminate()` + `sd._initialize()` - a full
PortAudio teardown and rebuild - twice. It cost ~330 ms of every launch to
populate two combo boxes on a screen the driver opens about once a month.

The hazard this pins is **rule 3 wearing a hat**: `load()` runs before the
fill and cannot find a device that is not in the list yet, so it falls back to
index 0. Left there, `values()` would report `audio_output_device=""` -
"System default" - for a headset the driver had actually chosen, and the app
would speak into the wrong device while showing the right settings.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.settings import Settings                   # noqa: E402
from pitcrew.ui import settings_screen as module        # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def screen(qt_app, monkeypatch):
    monkeypatch.setattr(module.audio_devices, "devices",
                        lambda kind: [(0, "JBL Endurance Run 3C"),
                                      (1, "Some Other Card")])
    return module.SettingsScreen()


def test_nothing_is_enumerated_while_the_screen_is_only_built(qt_app,
                                                              monkeypatch):
    """The saving itself. A device call during construction is the defect."""
    monkeypatch.setattr(
        module.audio_devices, "devices",
        lambda kind: pytest.fail("PortAudio was rebuilt at construction"))
    made = module.SettingsScreen()
    assert made.audio_output.count() == 1      # "System default" only
    assert made.audio_input.count() == 1


def test_opening_the_screen_fills_the_lists(screen):
    screen._fill_audio_devices()
    assert screen.audio_output.count() == 3
    assert screen.audio_output.itemData(1) == "JBL Endurance Run 3C"


def test_a_configured_device_survives_the_late_fill(screen):
    """`load` ran first and could not find it. The fill must put it back, or
    the setting is silently replaced by the default."""
    screen.load(Settings(audio_output_device="Some Other Card",
                         audio_input_device="JBL Endurance Run 3C"))
    # Before the fill, the combo genuinely cannot hold it.
    assert screen.audio_output.currentData() == ""

    screen._fill_audio_devices()
    assert screen.audio_output.currentData() == "Some Other Card"
    assert screen.values().audio_output_device == "Some Other Card"
    assert screen.values().audio_input_device == "JBL Endurance Run 3C"


def test_a_device_that_is_gone_does_not_become_a_silent_default(screen):
    """A configured device that is no longer plugged in is a real state. It
    must not read as a deliberate "System default"."""
    screen.load(Settings(audio_output_device="A Headset Not Here"))
    screen._fill_audio_devices()
    # It is not in the list, so the combo cannot show it - but the stored
    # setting is what `load` was given, and nothing here has overwritten it.
    assert screen._loaded.audio_output_device == "A Headset Not Here"


def test_the_fill_happens_once(screen):
    screen._fill_audio_devices()
    screen._fill_audio_devices()
    assert screen.audio_output.count() == 3


def test_it_does_not_rebuild_portaudio_during_a_session(qt_app, monkeypatch):
    """Twelve seconds of frozen window and a dropped transducer, mid-race, to
    refresh a list. A stale list that says it is stale is the better failure.
    """
    called: list[str] = []
    monkeypatch.setattr(module.audio_devices, "devices",
                        lambda kind: called.append(kind) or [])
    made = module.SettingsScreen()
    made.set_session_open(True)
    made._fill_audio_devices()
    assert called == [], "PortAudio was rebuilt while a session was open"

    made.set_session_open(False)
    made._fill_audio_devices()
    assert called == ["output", "input"]
