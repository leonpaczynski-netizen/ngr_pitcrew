"""The data line: once a lap, onto the first clear radio - not onto a straight.

Bathurst, 14 Sep 2026: the straight edge fired a second into the 5.5 s
heartbeat and the number queued behind it, reaching the driver 4.8-7.0 s
late. That made the line wait for a clear radio AND a straight it fitted -
held 4 s on a circuit with no model, capped at 2.8 s, no fuel figure.

15 Sep 2026, the driver: *"George can speak at anytime."* The straight no
longer decides anything: the race asks twice a second whether the radio is
clear, and the first clear moment after the crossing's speech carries the
number, whatever its length. The straight models stay (`race/straight.py`)
and are tested there; `fits` is kept as a pure function and pinned below.
"""
from __future__ import annotations

import inspect

import pytest

from pitcrew.engineer.voice import Voice
from pitcrew.race import straight
from pitcrew.race.calls import STATUS
from pitcrew.race.colour import CHATTY, ColourCalls

from .test_controller import qt_app  # noqa: F401
from .test_race_wiring import green, raced, voice  # noqa: F401


# ------------------------------------------- the straight's pure functions

def test_a_closed_straight_fits_nothing():
    assert not straight.fits(straight.Window(held_s=1.0), 0.5)
    assert not straight.fits(None, 0.5)


def test_without_a_model_fits_still_asks_the_straight_to_prove_itself():
    """Kept for the models another pass is deriving - no speech asks it."""
    early = straight.Window(held_s=straight.MIN_HELD_S + 0.1)
    proved = straight.Window(held_s=straight.UNMODELLED_HOLD_S)
    assert not straight.fits(early, 1.0)
    assert straight.fits(proved, 5.5)
    assert straight.fits(proved, 2.0, strict=True)
    assert not straight.fits(proved, 4.8, strict=True)


def test_with_a_model_the_clip_has_to_fit_what_is_left():
    window = straight.Window(held_s=2.1, remaining_s=4.0)
    assert straight.fits(window, 3.5, strict=True)
    assert not straight.fits(window, 3.6, strict=True)


def test_a_detector_that_stopped_being_fed_is_not_a_straight():
    detector = straight.Straight()
    for at in (100.0, 106.0):
        detector.update(throttle_pct=100.0, speed_ms=60.0, yaw_rate=0.0,
                        now=at)
    assert detector.window(106.1).held_s == pytest.approx(6.1)
    assert not detector.window(106.0 + straight.FRESH_S + 0.1).open
    detector.update(throttle_pct=40.0, speed_ms=60.0, yaw_rate=0.0, now=106.2)
    assert not detector.window(106.2).open


# ------------------------------------------------------------ the data line

@pytest.fixture()
def chatty_lap(raced):  # noqa: F811
    from dataclasses import replace

    from pitcrew.race.calls import Call

    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    state = controller.race.state
    state.lap = 4
    state.record(Call(STATUS, 4, "Lap 4. 16 laps to go. P4.", ""))
    controller.settings = replace(controller.settings, colour_calls="chatty")
    asked: list = []
    controller._colour.data_line = (
        lambda **kwargs: asked.append(kwargs) or None)
    return controller, asked


def test_the_data_line_is_not_queued_behind_a_busy_voice(chatty_lap,
                                                         monkeypatch):
    controller, asked = chatty_lap
    monkeypatch.setattr(Voice, "busy", property(lambda _self: True))
    controller._on_straight_reached()
    assert asked == [], "composed onto a busy radio"


def test_a_clear_radio_carries_it_with_no_straight_anywhere(chatty_lap):
    """The detector has never been fed: no straight, no window, no model.
    The radio is clear, so the number is composed - and nothing is asked
    about where the car is or how long the line is."""
    controller, asked = chatty_lap
    controller.bridge.straight.reset()
    assert not controller.bridge.straight.window(0.0).open
    controller._on_straight_reached()
    assert len(asked) == 1
    assert "fits" not in asked[0]


def test_it_asks_again_once_the_crossings_speech_has_finished(chatty_lap,
                                                             monkeypatch):
    controller, asked = chatty_lap
    radio = {"busy": True}
    monkeypatch.setattr(Voice, "busy",
                        property(lambda _self: radio["busy"]))
    controller._on_straight_reached()                 # the heartbeat plays
    assert asked == []
    radio["busy"] = False                             # ...and ends
    controller._on_straight_reached()
    assert len(asked) == 1


def test_arming_a_speaking_race_starts_the_clear_radio_ask(raced):  # noqa: F811
    controller, _, _, _ = raced
    controller.start_race()
    timer = controller._data_line_timer
    assert timer.isActive()
    assert timer.interval() == controller.DATA_LINE_ASK_MS <= 1000
    controller.stop_race()
    controller._on_straight_reached()
    assert not timer.isActive(), "still asking after the race was stopped"


def test_the_data_line_takes_no_fit_and_reads_the_fuel_figure_mid_lap():
    """The 2.8 s cap and the no-fuel-figure-without-a-model rule existed only
    for the straight gate; both are gone with it."""
    assert "fits" not in inspect.signature(ColourCalls.data_line).parameters
    colour = ColourCalls(level=CHATTY)
    call = colour.data_line(lap=4, fuel_laps_in_hand=1.9,
                            fuel_reference="to the stop")
    assert call is not None
    assert call.spoken() == "1.9 laps of fuel in hand to the stop."
