"""Six intensities out of GT7's channels.

Everything under test here is DERIVED - GT7 broadcasts no slip channel, no
road-texture channel, no impact channel and no ABS flag - so these are tests
of a model against its own stated thresholds, not of a measurement. The one
that matters most is the first: an effect reading full scale down a straight
is worse than an effect that never fires, because the driver would feel the
car doing something it is not doing and drive to it.
"""
from __future__ import annotations

import dataclasses
import struct

import numpy as np

from pitcrew.rig import effects
from pitcrew.rig.effects import EffectDeriver
from pitcrew.rig.synth import PORSCHE_RSR_17 as PORSCHE_RSR_17_SPECS

from .conftest import make_packet, rolling_wheel_rps

# Where things sit inside the 72-byte extended tail.
_ROAD_WHEEL_L = 352 - 296
_ROAD_WHEEL_R = 356 - 296
_SURFACE = 344 - 296
_WHEELBASE = 360 - 296


def racing(*, road_wheel: float = 0.0, surfaces: str = "TTTT",
           wheelbase: float = 2.516, **overrides):
    """A packet with a real extended tail, since that is where the channels
    this module leans on actually live."""
    packet = make_packet(extended=True, **overrides)
    tail = bytearray(packet.tail or bytes(72))
    struct.pack_into("<f", tail, _ROAD_WHEEL_L, road_wheel)
    struct.pack_into("<f", tail, _ROAD_WHEEL_R, road_wheel)
    struct.pack_into("<f", tail, _WHEELBASE, wheelbase)
    tail[_SURFACE:_SURFACE + 4] = surfaces.encode("ascii")
    return dataclasses.replace(packet, tail=bytes(tail))


def rolling(speed_ms: float = 59.7, **overrides):
    """A car travelling in a straight line with its wheels rolling true.

    Any wheel the caller names keeps the caller's value - that is how a single
    wheel is made to spin or lock without respecifying the other three.
    """
    rps = rolling_wheel_rps(speed_ms)
    wheels = {"wheel_rps_fl": rps, "wheel_rps_fr": rps,
              "wheel_rps_rl": rps, "wheel_rps_rr": rps}
    wheels.update(overrides)
    return racing(speed_ms=speed_ms, **wheels)


def settle(deriver: EffectDeriver, packet, frames: int = 3) -> np.ndarray:
    out = None
    for _ in range(frames):
        out = deriver.update(packet).copy()
    return out


def one(deriver: EffectDeriver, packet, name: str) -> float:
    return float(settle(deriver, packet)[deriver.NAMES.index(name)])


# ------------------------------------------------------- the straight line

def test_a_car_going_straight_reports_no_traction_loss():
    """The regression this module was built wrong for first.

    `steering` is the in-game rim and saturates at +-pi at full lock, so
    feeding it to a bicycle model overstates the angle by the whole steering
    ratio. Measured on a real packet: 0.023 rad of rim at 215 km/h implied
    0.55 rad/s of yaw - a hairpin - and this effect read 1.0 down a straight.
    The road-wheel angle for the same frame was 0.0016 rad.
    """
    packet = rolling(road_wheel=0.0016, angvel_y=0.0249)
    assert one(EffectDeriver(), packet, "traction_loss") == 0.0


def test_a_car_being_thrown_sideways_does_report_it():
    """The other half: the effect has to fire when it should."""
    packet = rolling(road_wheel=0.0, angvel_y=0.6)
    assert one(EffectDeriver(), packet, "traction_loss") > 0.8


def test_rolling_wheels_are_not_spinning_or_locking():
    assert one(EffectDeriver(), rolling(), "wheels_spin_lock") == 0.0


# ---------------------------------------------------------------- wheels

def test_wheelspin_needs_the_throttle_to_be_open():
    """A wheel reading fast in the air is not wheelspin the driver caused."""
    fast = rolling_wheel_rps(59.7) * 1.30
    on = rolling(wheel_rps_rl=fast, wheel_rps_rr=fast, throttle_raw=255)
    off = rolling(wheel_rps_rl=fast, wheel_rps_rr=fast, throttle_raw=0)
    assert one(EffectDeriver(), on, "wheels_spin_lock") > \
        one(EffectDeriver(), off, "wheels_spin_lock")


def test_a_lock_up_needs_the_brake_to_be_on():
    """A wheel reading slow over a kerb is not a lock-up, and the pedal is
    what separates the two. He trail-brakes deep by design, so this effect
    firing on lifts would be constant.

    Settled over a longer window than most of these, because a lock is no
    longer believed on sight: it has to hold for `LOCK_ATTACK_S` before it is
    reported, which is what stops ABS pulsing being read as a lock-up. Three
    frames only reaches about 0.2 of the way there now.
    """
    slow = rolling_wheel_rps(59.7) * 0.60
    braking = rolling(wheel_rps_fl=slow, wheel_rps_fr=slow, brake_raw=200)
    coasting = rolling(wheel_rps_fl=slow, wheel_rps_fr=slow, brake_raw=0)
    held = settle(EffectDeriver(), braking, frames=60)
    assert float(held[0]) > 0.5
    assert one(EffectDeriver(), coasting, "wheels_spin_lock") == 0.0


def test_slip_is_not_computed_from_a_divisor_that_means_nothing():
    """Below walking pace the ratio is arithmetic on nearly zero."""
    crawling = racing(speed_ms=1.0, wheel_rps_fl=50.0)
    assert one(EffectDeriver(), crawling, "wheels_spin_lock") == 0.0


# ---------------------------------------------------------------- surface

def test_a_kerb_is_felt_because_gt7_says_it_is_a_kerb():
    """The one input here that is measured rather than modelled - and the one
    SimHub's GT7 support cannot see, because it reads the base packet format
    only and so has to infer kerbs from suspension."""
    tarmac = one(EffectDeriver(), rolling(surfaces="TTTT"), "wheels_rumble")
    kerb = one(EffectDeriver(), rolling(surfaces="TTCC"), "wheels_rumble")
    assert kerb > tarmac + 0.3


def test_grass_and_dirt_are_felt_but_less_than_a_kerb():
    grass = one(EffectDeriver(), rolling(surfaces="GGGG"), "wheels_rumble")
    kerb = one(EffectDeriver(), rolling(surfaces="CCCC"), "wheels_rumble")
    assert 0.0 < grass < kerb


def _over_bumps(speed_ms: float) -> float:
    """Rumble from a road that is actually moving the suspension."""
    deriver = EffectDeriver()
    value = 0.0
    for frame in range(12):
        height = 0.08 + (0.006 if frame % 2 else -0.006)
        value = float(deriver.update(rolling(
            speed_ms=speed_ms,
            suspension_fl=height, suspension_fr=height,
            suspension_rl=height, suspension_rr=height))[2])
    return value


def test_the_same_bump_matters_less_at_walking_pace():
    """His SimHub rumble scaled to `MaxEffectSpeed 130`.

    Tested on tarmac with the suspension genuinely moving, because the speed
    scaling now applies to the TEXTURE only. A kerb is deliberately exempt -
    see below.
    """
    assert _over_bumps(40.0) > _over_bumps(5.0)


def test_a_kerb_is_not_scaled_down_just_because_the_corner_is_slow():
    """The change that came out of "ripple strips don't feel sharp enough".

    A bump at 40 km/h genuinely is not the bump it is at 130 - the suspension
    moves less. But a kerb is a kerb: the wheel is on a different surface, and
    hairpins are exactly where kerbs matter most.
    """
    fast = one(EffectDeriver(), rolling(speed_ms=40.0, surfaces="CCCC"),
               "wheels_rumble")
    slow = one(EffectDeriver(), rolling(speed_ms=5.0, surfaces="CCCC"),
               "wheels_rumble")
    assert fast == slow
    # float32, so a hair under the constant.
    assert slow >= effects.KERB_BOOST - 1e-6


def test_arriving_on_a_kerb_fires_a_low_thump():
    """The rumble band's frequency follows its intensity, so a kerb drives the
    HIGHEST frequency in it - and piston excursion falls as 1/f-squared, so
    the hardest hit is the least felt. Measured: ordinary road 135 Hz, kerb
    149 Hz, four-fifths the excursion. It gets buzzier, not sharper.

    A real ripple strip is a thud with a rattle on top. This is the thud.
    """
    deriver = EffectDeriver()
    for _ in range(4):
        deriver.update(rolling(surfaces="TTTT"))
    on_kerb = float(deriver.update(rolling(surfaces="TTCC"))[4])
    assert on_kerb >= effects.KERB_THUMP


def test_sitting_on_a_kerb_is_a_texture_rather_than_a_repeated_thump():
    """It is the EDGE that reads as sharp. A wheel resting on a kerb through
    a whole chicane is what the rumble effect is for."""
    deriver = EffectDeriver()
    deriver.update(rolling(surfaces="TTTT"))
    first = float(deriver.update(rolling(surfaces="TTCC"))[4])
    for _ in range(30):
        later = float(deriver.update(rolling(surfaces="TTCC"))[4])
    assert later < first * 0.2, "it kept thumping while the wheel sat there"


def test_texture_comes_from_suspension_movement_not_its_position():
    """Height alone is ride height plus load transfer. A car sitting at a
    constant, unusual height is not on a rough surface."""
    deriver = EffectDeriver()
    still = rolling(suspension_fl=0.09, suspension_fr=0.09,
                    suspension_rl=0.09, suspension_rr=0.09)
    assert one(deriver, still, "wheels_rumble") == 0.0


# ------------------------------------------------------------------ engine

def test_a_gear_change_thumps_once_and_decays():
    deriver = EffectDeriver()
    fourth = rolling(gear_raw=0x04, engine_rpm=8000.0,
                     rpm_alert_min=8500, rpm_alert_max=9000)
    fifth = dataclasses.replace(fourth, gear_raw=0x05)
    deriver.update(fourth)
    at_shift = float(deriver.update(fifth)[1])
    assert at_shift > 0.3, "the shift was not felt"
    for _ in range(30):
        after = float(deriver.update(fifth)[1])
    assert after < at_shift * 0.2, "the thump did not decay"


def test_a_shift_at_the_limiter_is_felt_harder_than_one_at_half_revs():
    """His profile modulated the gear gain by rpm between 50% and 90%."""
    def shift(rpm: float) -> float:
        deriver = EffectDeriver()
        low = rolling(gear_raw=0x03, engine_rpm=rpm, rpm_alert_max=9000)
        deriver.update(low)
        return float(deriver.update(dataclasses.replace(low, gear_raw=0x04))[1])

    assert shift(8600.0) > shift(4000.0)


def test_rolling_backwards_out_of_the_box_is_not_a_gearshift():
    deriver = EffectDeriver()
    neutral = rolling(gear_raw=0x00)
    first = dataclasses.replace(neutral, gear_raw=0x01)
    deriver.update(neutral)
    assert float(deriver.update(first)[1]) == 0.0


def test_the_rpm_curve_is_his_and_is_read_in_ascending_order():
    """SimHub stores his control points with the last one sorting fourth, and
    sorts them on load. Read top to bottom the curve is a different shape."""
    xs = [x for x, _ in effects.RPM_CURVE]
    assert xs == sorted(xs)
    assert effects.RPM_CURVE[-1] == (100.0, 63.06), "it tops out at 63%, not 100"


def test_revs_are_a_fraction_of_this_cars_own_limiter():
    """`rpm_alert_max` is broadcast per car, so this needs no configuration
    and is right on a Gr.4 and a Gr.1 without being told anything."""
    high = one(EffectDeriver(), rolling(engine_rpm=8800.0, rpm_alert_max=9000),
               "rpm")
    low = one(EffectDeriver(), rolling(engine_rpm=8800.0, rpm_alert_max=18000),
              "rpm")
    assert high > low


# ------------------------------------------------------------------ impacts

def test_a_step_in_velocity_no_engine_could_produce_is_an_impact():
    deriver = EffectDeriver()
    cruising = rolling(vel_x=59.7, vel_y=0.0, vel_z=0.0)
    deriver.update(cruising)
    hit = dataclasses.replace(cruising, vel_x=55.0)
    assert float(deriver.update(hit)[4]) > 0.5


def test_ordinary_braking_is_not_an_impact():
    deriver = EffectDeriver()
    cruising = rolling(vel_x=59.7)
    deriver.update(cruising)
    slowing = dataclasses.replace(cruising, vel_x=59.4)
    assert float(deriver.update(slowing)[4]) == 0.0


# -------------------------------------------------------------- off track

def test_nothing_fires_while_the_car_is_not_on_track():
    """A garage visit produces position jumps and suspension steps that are
    not events, and he is not in the seat to feel them anyway."""
    deriver = EffectDeriver()
    out = deriver.update(make_packet(extended=True, on_track=False,
                                     engine_rpm=8000.0, rpm_alert_max=9000))
    assert float(np.max(out)) == 0.0


def test_coming_back_on_track_does_not_fire_a_phantom_impact():
    """The car reappears somewhere else on the map with a different velocity.
    Carrying the old one across the gap would be a collision that never
    happened, at full scale, the instant he rejoins."""
    deriver = EffectDeriver()
    deriver.update(rolling(vel_x=59.7))
    deriver.update(make_packet(extended=True, on_track=False))
    rejoined = rolling(vel_x=-30.0)
    assert float(deriver.update(rejoined)[4]) == 0.0


def test_every_intensity_stays_between_nought_and_one():
    deriver = EffectDeriver()
    for packet in (rolling(), rolling(surfaces="CCCC", angvel_y=3.0),
                   rolling(wheel_rps_fl=400.0, throttle_raw=255),
                   rolling(speed_ms=0.5)):
        out = settle(deriver, packet)
        assert float(np.min(out)) >= 0.0
        assert float(np.max(out)) <= 1.0


# --------------------------------------------------------------- the ABS

def test_abs_pulsing_is_not_reported_as_a_lock_up():
    """Reported from the seat as "ABS is way too strong", which is worth
    reading carefully: there IS no ABS effect and none was built, because GT7
    broadcasts no ABS flag.

    What he felt was the lock half of `wheels_spin_lock` firing on the assist
    itself - ABS pulses the brakes at 10-15 Hz, every pulse drops wheel speed
    below road speed, and a detector with no memory calls each one a lock-up.
    On a driver whose technique is trail-braking deep that is most of every
    corner. The distinction is duration, not depth.
    """
    deriver = EffectDeriver()
    slow = rolling_wheel_rps(59.7) * 0.55
    locked = rolling(wheel_rps_fl=slow, wheel_rps_fr=slow, brake_raw=220)
    free = rolling(brake_raw=220)

    peak = 0.0
    for frame in range(120):                       # two seconds of ABS
        pulsing = locked if (frame // 3) % 2 == 0 else free
        peak = max(peak, float(deriver.update(pulsing)[0]))
    assert peak < 0.6, f"the assist still dominates, reaching {peak:.2f}"


def test_a_lock_that_is_actually_held_still_comes_through():
    """The other half. Slowing the attack must not deafen a real lock."""
    deriver = EffectDeriver()
    slow = rolling_wheel_rps(59.7) * 0.55
    locked = rolling(wheel_rps_fl=slow, wheel_rps_fr=slow, brake_raw=220)
    for _ in range(120):
        value = float(deriver.update(locked)[0])
    assert value > 0.9, f"a held lock only reached {value:.2f}"


def test_the_lock_lets_go_quickly_when_the_wheel_does():
    """Slow to believe, quick to forget - otherwise it rings on past the
    corner it belonged to."""
    deriver = EffectDeriver()
    slow = rolling_wheel_rps(59.7) * 0.55
    locked = rolling(wheel_rps_fl=slow, wheel_rps_fr=slow, brake_raw=220)
    for _ in range(120):
        deriver.update(locked)
    for _ in range(20):
        value = float(deriver.update(rolling(brake_raw=0))[0])
    assert value < 0.1, f"still ringing at {value:.2f}"


def test_scrabbling_back_over_a_kerb_from_the_grass_is_not_an_apex_hit():
    """`car_on_track` is GT7's flags bit 0 - "in a session", not "on the
    racing surface" - so nothing upstream distinguishes a clean apex from a
    recovery. Two such transitions occurred on one real lap."""
    deriver = EffectDeriver()
    deriver.update(rolling(surfaces="GGGG"))
    from_grass = float(deriver.update(rolling(surfaces="GGCC"))[4])
    assert from_grass == 0.0

    clean = EffectDeriver()
    clean.update(rolling(surfaces="TTTT"))
    from_tarmac = float(clean.update(rolling(surfaces="TTCC"))[4])
    assert from_tarmac >= effects.KERB_THUMP


def test_the_kerb_thump_owns_a_channel_the_driver_tuned_to_fire_rarely():
    """Worth asserting because it is a change he did not ask for and has not
    been told about.

    He set `wheels_impact` threshold to 55 where his others were 8-28, which
    reads as "this should fire almost never" - a 12 g velocity step, i.e. a
    crash. The kerb thump clears that gate comfortably, so on a real lap 100%
    of that channel's output is now kerbs, 44 times a lap. The masking is
    narrow but real: a genuine impact in the 0.55-0.75 band landing during a
    kerb strike is swallowed by the `max()`.
    """
    impact = {s.name: s for s in PORSCHE_RSR_17_SPECS}["wheels_impact"]
    assert impact.threshold == 55.0
    assert impact.shape(effects.KERB_THUMP) > 0.0, (
        "the kerb thump no longer reaches the channel it was routed into")
