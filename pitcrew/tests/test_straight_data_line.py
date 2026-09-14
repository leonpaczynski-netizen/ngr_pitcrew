"""The straight's data line: only onto a clear radio, only where it fits.

Bathurst, 14 Sep 2026: the straight edge fired a second into the 5.5 s
heartbeat and the number queued behind it, reaching the driver 4.8-7.0 s late
in the braking zone for Hell Corner. And half the straights there had 1.5 s
or less left when the edge fired, so even a clear radio was no promise of a
straight long enough to finish on.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer.voice import Voice
from pitcrew.race import straight
from pitcrew.race.calls import STATUS

from .test_controller import qt_app  # noqa: F401
from .test_controller_wiring import on_a_straight
from .test_race_wiring import green, raced, voice  # noqa: F401


# --------------------------------------------------------------- straights

def test_a_closed_straight_fits_nothing():
    assert not straight.fits(straight.Window(held_s=1.0), 0.5)
    assert not straight.fits(None, 0.5)


def test_without_a_model_the_straight_has_to_prove_itself():
    early = straight.Window(held_s=straight.MIN_HELD_S + 0.1)
    proved = straight.Window(held_s=straight.UNMODELLED_HOLD_S)
    assert not straight.fits(early, 1.0)
    assert straight.fits(proved, 5.5), "news is judged by the hold alone"
    assert straight.fits(proved, 2.0, strict=True)
    assert not straight.fits(proved, 4.8, strict=True), (
        "a fuel figure is too long for a straight nobody has measured")


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


# ------------------------------------------------- the straight's data line

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
    on_a_straight(controller)
    monkeypatch.setattr(Voice, "busy", property(lambda _self: True))
    controller._on_straight_reached()
    assert asked == [], "composed onto a busy radio"


def test_on_an_unproved_straight_it_looks_again_rather_than_speaking(
        chatty_lap):
    controller, asked = chatty_lap
    on_a_straight(controller, held_s=straight.MIN_HELD_S + 0.1)
    controller._on_straight_reached()
    assert asked == [], "spoke at the edge of a straight nobody measured"
    on_a_straight(controller, held_s=straight.UNMODELLED_HOLD_S + 0.5)
    controller._on_straight_reached(recheck=True)
    assert len(asked) == 1


def test_the_data_line_is_offered_only_what_fits(chatty_lap):
    controller, asked = chatty_lap
    on_a_straight(controller, held_s=6.0)
    controller._on_straight_reached()
    fits = asked[0]["fits"]
    assert fits("RR 19 percent.")
    assert not fits("1.9 laps of fuel in hand to the stop. And then some "
                    "more words that make it long.")
