"""Speed in, fan duty out.

SimHub's formula is compiled and unpublished, so none of this is a port. What
is asserted here is that the *shape* matches the driver's tuning while the
*scale* is measured - the circuit's own recorded top speed where the event has
one, the car's broadcast maximum otherwise. Which is the one thing this can do
that SimHub structurally cannot, because SimHub knows neither.
"""
from __future__ import annotations

import dataclasses

import pytest

from pitcrew.rig import wind
from pitcrew.rig.wind_curve import (
    FALLBACK_MAX_KPH,
    MOVING_KPH,
    WindCurve,
    WindProfile,
)

from .conftest import make_packet


def at(speed_kph: float, *, top_speed: int = 299, on_track: bool = True):
    return make_packet(on_track=on_track,
                       speed_ms=speed_kph / 3.6,
                       car_max_speed_raw=top_speed)


def settled(curve: WindCurve, packet, *, racing: bool = False,
            seconds: float = 6.0) -> int:
    """Run the slew limiter out to where it stops moving."""
    duty = (0,)
    for _ in range(int(seconds * 60)):
        duty = curve.update(packet, 1 / 60, racing=racing)
    return duty[0]


# ------------------------------------------------------- scale from the car

def test_the_top_of_the_curve_comes_from_the_car_not_from_tuning():
    """He spent eight days settling SimHub's `MaximumSpeed` on 281.08. GT7
    broadcasts 299 for this car in every packet."""
    curve = WindCurve()
    curve.target(at(100.0, top_speed=299), racing=False)
    assert curve.max_kph == 299.0


def test_the_same_speed_is_more_wind_in_a_slower_car():
    """A Gr.4 at 150 km/h is working harder than a Gr.1 at 150 km/h, and the
    fans should say so. This is what per-car scaling buys."""
    slow = WindCurve()
    fast = WindCurve()
    in_slow_car = slow.target(at(150.0, top_speed=200), racing=True)
    in_fast_car = fast.target(at(150.0, top_speed=340), racing=True)
    assert in_slow_car > in_fast_car


def test_a_car_that_reports_no_top_speed_falls_back_rather_than_dividing():
    curve = WindCurve()
    assert curve.target(at(150.0, top_speed=0), racing=True) > 0.0
    assert curve.max_kph == FALLBACK_MAX_KPH


# ------------------------------------------------------------- the shape

def test_the_curve_runs_from_his_floor_to_his_ceiling():
    curve = WindCurve()
    profile = curve.profile
    crawling = curve.target(at(MOVING_KPH + 1.0), racing=True)
    flat_out = curve.target(at(299.0), racing=True)
    assert crawling == pytest.approx(profile.min_gain, abs=0.02)
    assert flat_out == pytest.approx(profile.max_gain, abs=1e-6)


def test_wind_rises_with_speed():
    curve = WindCurve()
    speeds = [curve.target(at(v), racing=True) for v in (60, 120, 180, 240)]
    assert speeds == sorted(speeds)
    assert len(set(speeds)) == len(speeds)


def test_gamma_bends_the_curve_without_moving_its_ends():
    ends = []
    for gamma in (0.5, 1.0, 2.0):
        curve = WindCurve(WindProfile(gamma=gamma))
        ends.append((curve.target(at(299.0), racing=True),
                     curve.target(at(150.0), racing=True)))
    tops = {round(top, 6) for top, _ in ends}
    middles = [mid for _, mid in ends]
    assert len(tops) == 1, "gamma moved the top of the curve"
    assert middles[0] > middles[1] > middles[2], "gamma did not bend it"


# ------------------------------------------------------------ the standstill

def test_static_wind_is_suppressed_during_a_race():
    """`EnableInRace: false` in his config, and easy to misread. It means the
    32% floor exists in the menus and not on track - so static tuning done at
    a standstill is not what he feels racing."""
    curve = WindCurve()
    parked = at(0.0)
    assert curve.target(parked, racing=False) == curve.profile.static_gain
    assert curve.target(parked, racing=True) == 0.0


def test_a_parked_car_is_not_blown_at_during_a_race():
    curve = WindCurve()
    assert settled(curve, at(0.0), racing=True) == 0


def test_nothing_blows_while_the_car_is_off_track():
    curve = WindCurve()
    assert curve.target(at(200.0, on_track=False), racing=True) == 0.0


# -------------------------------------------------------------- the fans

def test_the_fans_are_slew_limited_rather_than_following_every_frame():
    """A 4000 rpm blower takes the better part of a second to settle a step.
    Sixty unsmoothed values inside that makes it hunt audibly."""
    curve = WindCurve()
    flat_out = at(299.0)
    first = curve.update(flat_out, 1 / 60, racing=True)[0]
    assert first < 60, "it went straight to full in one frame"


def test_wind_arrives_faster_than_it_leaves():
    """Wind should arrive promptly and decay gently. The reverse sounds like
    a fault."""
    rising = WindCurve()
    for _ in range(6):
        rising.update(at(299.0), 1 / 60, racing=True)
    gained = rising.level

    falling = WindCurve()
    settled(falling, at(299.0), racing=True)
    before = falling.level
    for _ in range(6):
        falling.update(at(0.0), 1 / 60, racing=True)
    lost = before - falling.level

    assert gained > lost


def test_every_channel_gets_a_value_because_the_firmware_reads_them_all():
    """The firmware reads exactly `motorCount()` raw bytes with no framing, so
    a short write leaves it waiting mid-command."""
    curve = WindCurve()
    duties = curve.update(at(200.0), 1 / 60, racing=True)
    assert len(duties) == wind.CHANNELS


def test_both_fans_get_the_same_value():
    """SimHub has a left/right differential and how it is driven is
    undocumented - the community explanation is "lateral forces" with nothing
    behind it. Inventing one and calling it a port of his setup would be
    inventing a preference he never expressed."""
    curve = WindCurve()
    duties = curve.update(at(200.0), 1 / 60, racing=True)
    assert len(set(duties)) == 1


def test_a_duty_the_fan_cannot_act_on_becomes_off():
    """1 and 2 energise a motor that cannot turn: current, heat, no air."""
    curve = WindCurve()
    curve._level = 0.004                     # under 2/255
    duties = curve.update(at(0.0), 1 / 60, racing=True)
    assert duties[0] == 0


def test_a_profile_with_impossible_gains_is_refused():
    with pytest.raises(ValueError):
        WindProfile(min_gain=0.8, max_gain=0.2)
    with pytest.raises(ValueError):
        WindProfile(gamma=0.0)


def test_the_description_says_what_the_fans_are_doing():
    curve = WindCurve()
    settled(curve, at(299.0), racing=True)
    text = curve.describe()
    assert "299" in text and "%" in text


# ------------------------------------------------ wired into the packet path

def _bridge():
    from pitcrew.controller import TelemetryBridge
    return TelemetryBridge()


def _encoded() -> bytes:
    from .test_direct_feed import a_car_on_track, encrypted
    return encrypted(a_car_on_track())


def test_the_fans_are_off_until_they_are_switched_on():
    from pitcrew.settings import Settings

    assert Settings().wind_enabled is False


def test_a_packet_reaches_the_fans():
    bridge = _bridge()
    seen = []

    class Sink:
        def set_output(self, values, context=None):
            seen.append(tuple(values))

    bridge.wind = Sink()
    assert bridge.on_packet(_encoded()) is True
    assert len(seen) == 1
    assert len(seen[0]) == wind.CHANNELS


def test_a_wind_sim_that_raises_cannot_cost_him_the_session():
    """The app observes and advises. An output must never be able to stop a
    lap being recorded - and this one talks to a serial port, which is the
    subsystem that wedged SimHub."""
    bridge = _bridge()

    class Broken:
        def set_output(self, values, context=None):
            raise RuntimeError("COM5 stopped functioning")

    bridge.wind = Broken()
    assert bridge.on_packet(_encoded()) is True
    assert bridge.wind is None, "a broken output stayed wired in"
    assert bridge.recorder.frame_count >= 1


def test_a_race_suppresses_the_static_floor_and_practice_does_not():
    """`EnableInRace: false`, honoured at the boundary where the app already
    knows which kind of session this is."""
    bridge = _bridge()
    bridge.reset(race=True)
    assert bridge.racing is True
    bridge.reset(race=False)
    assert bridge.racing is False


def test_a_session_boundary_clears_the_smoothing():
    """Otherwise the fans resume a lap later at the speed the last one ended
    on, which is wind for a corner he is not in."""
    bridge = _bridge()

    class Sink:
        def set_output(self, values, context=None):
            pass

    bridge.wind = Sink()
    for _ in range(120):
        bridge.on_packet(_encoded())
    assert bridge.wind_curve.level > 0.0
    bridge.reset()
    assert bridge.wind_curve.level == 0.0


def test_flat_out_asks_for_everything_the_fans_have():
    """The 0.80 cap is gone, and the history is the point.

    It was added while the fans were stopping mid-lap, on the theory that two
    4000 RPM blowers at full were browning out the supply or cooking the
    shield's drivers. Wrong theory: they stopped at 33 seconds at 100% duty
    and at 33 seconds again at 80%, and identical timing under two different
    loads cannot be thermal or current, because both scale with load. It was
    the packet id wrapping at frame 128.

    With that fixed the cap protects against nothing, so top speed gets the
    top of the range.
    """
    curve = WindCurve()
    assert settled(curve, at(299.0), racing=True) == 255


def test_a_smaller_rig_can_still_be_given_a_ceiling():
    """The field stays even though this rig does not need it - a supply that
    genuinely cannot do both fans at full should not mean editing the curve."""
    curve = WindCurve(WindProfile(max_duty=0.5))
    assert settled(curve, at(299.0), racing=True) <= 128


# ------------------------------------------------- scaled to the circuit


def test_the_scale_is_the_circuits_top_speed_where_the_event_has_one():
    """`car_max_speed_raw` is the CAR's top speed and the circuit is always
    slower. The Huracan broadcasts 299 and the quickest frame of the whole
    Watkins race was 273.5, so the top 6% of the fan range could never be
    reached - measured over that race's 113k green-lap frames, duty peaked at
    240 of 255 and sat above 200 for 29.5% of the lap.
    """
    curve = WindCurve()
    curve.observed_top_kph = 273.5
    assert curve.target(at(273.5), racing=True) == pytest.approx(1.0)
    # Against the car's 299 the same frame falls short of full.
    car_scaled = WindCurve()
    assert car_scaled.target(at(273.5), racing=True) < 0.95


def test_without_a_recorded_top_speed_the_car_still_sets_the_scale():
    """Missing is not zero, and it is not another circuit's figure either."""
    curve = WindCurve()
    curve.target(at(200.0), racing=True)
    assert curve.observed_top_kph is None
    assert curve.scale_kph == 299
    assert "no recorded top speed" in curve.describe()


def test_a_recorded_top_speed_above_the_car_is_a_bad_reading():
    """Not a faster car. Clamped, so one spiked frame cannot put the fans at
    full halfway down the straight for every session that follows."""
    curve = WindCurve()
    curve.observed_top_kph = 480.0
    curve.target(at(200.0), racing=True)
    assert curve.scale_kph == 299
