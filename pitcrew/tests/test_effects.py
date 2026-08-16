"""What the driver is told, from a packet, with no rig in the room.

`test_vehicle.py` covers what the car is doing. This covers the layer that
turns that into seven amplitudes: the immersion channels, the one-shots, and
the wiring that has to keep the two lists in step.

The distinction is worth keeping because the two fail differently. A wrong
number in `vehicle` is a wrong claim about the car; a wrong number here is a
cue that is too loud, in the wrong place, or masking something better.
"""
from __future__ import annotations

import numpy as np

from pitcrew.rig import vehicle
from pitcrew.rig.effects import EffectDeriver
from pitcrew.rig.synth import PROFILE
from pitcrew.tests.test_vehicle import Frame as _CarFrame


class Frame(_CarFrame):
    """A packet as far as both layers are concerned.

    `EffectDeriver` reads a handful of fields `VehicleModel` does not - the
    flags, the revs, the world velocity vector - so this adds them to the same
    stub rather than growing a second one that could drift from it.
    """

    def __init__(self, *, rpm=6000.0, rpm_max=8000.0, on_track=True,
                 paused=False, velocity=(0.0, 0.0, 0.0), **kw):
        super().__init__(**kw)
        self.engine_rpm = rpm
        self.rpm_alert_max = rpm_max
        self.car_on_track = on_track
        self.paused = paused
        if velocity != (0.0, 0.0, 0.0):
            self.vel_x, self.vel_y, self.vel_z = velocity
        self.speed_kmh = self.speed_ms * 3.6


def _index(name: str) -> int:
    return EffectDeriver.NAMES.index(name)


def _settle(deriver: EffectDeriver, frames: int = 400, **kw) -> np.ndarray:
    out = None
    for _ in range(frames):
        out = deriver.update(Frame(**kw)).copy()
    return out


# ------------------------------------------------------------- the contract

def test_the_deriver_and_the_mix_agree_on_what_the_effects_are():
    assert EffectDeriver.NAMES == tuple(s.name for s in PROFILE)


def test_it_returns_one_value_per_effect_and_one_per_modifier():
    """The modifiers are appended after the effects. Sizing anything from the
    number of VOICES drops them silently, which is a cue that stops working
    with nothing raised anywhere."""
    deriver = EffectDeriver()
    out = deriver.update(Frame())
    assert len(out) == len(EffectDeriver.NAMES) + len(EffectDeriver.MODIFIERS)


def test_every_value_is_a_fraction():
    deriver = EffectDeriver()
    for throttle in (0.0, 0.5, 1.0):
        for brake in (0.0, 1.0):
            out = deriver.update(Frame(throttle=throttle, brake=brake,
                                       rear_slip=1.4, front_slip=0.6))
            assert np.all(out >= 0.0) and np.all(out <= 1.0), out


def test_nothing_happens_off_track():
    """A car in the garage or mid-load produces position jumps and suspension
    steps that are not events, and the driver is not in the seat to feel
    them."""
    deriver = EffectDeriver()
    _settle(deriver, throttle=0.8, rear_slip=1.03)
    out = deriver.update(Frame(on_track=False, throttle=1.0, rear_slip=1.5))
    assert float(np.max(out)) == 0.0
    paused = deriver.update(Frame(paused=True, throttle=1.0, rear_slip=1.5))
    assert float(np.max(paused)) == 0.0


# ------------------------------------------------------------------- engine

def test_revs_are_a_fraction_of_this_cars_own_limiter():
    """GT7 broadcasts the shift light and the limiter per car, so the engine
    bed needs no configuration and is right on a Gr.4 and a Gr.1 without being
    told anything about either."""
    deriver = EffectDeriver()
    low = deriver.update(Frame(rpm=2000.0, rpm_max=8000.0))[_index("engine")]
    high = deriver.update(Frame(rpm=7600.0, rpm_max=8000.0))[_index("engine")]
    assert high > low
    other_car = deriver.update(
        Frame(rpm=3800.0, rpm_max=4000.0))[_index("engine")]
    assert other_car > low, "it is reading absolute revs, not a fraction"


def test_a_car_with_no_limiter_reported_is_silent_rather_than_full():
    deriver = EffectDeriver()
    assert deriver.update(Frame(rpm=6000.0, rpm_max=0.0))[_index("engine")] == 0.0


# ---------------------------------------------------------------- driveline

def test_a_gear_change_ticks_once_and_decays():
    deriver = EffectDeriver()
    deriver.update(Frame(gear=3))
    shifted = deriver.update(Frame(gear=4))[_index("driveline")]
    assert shifted > 0.0
    after = shifted
    for _ in range(12):
        after = deriver.update(Frame(gear=4))[_index("driveline")]
    assert after < shifted * 0.4, "the tick became a state"


def test_a_shift_at_the_limiter_is_felt_harder_than_one_at_half_revs():
    deriver = EffectDeriver()
    deriver.update(Frame(gear=3, rpm=4000.0))
    soft = deriver.update(Frame(gear=4, rpm=4000.0))[_index("driveline")]
    deriver.reset()
    deriver.update(Frame(gear=3, rpm=7600.0))
    hard = deriver.update(Frame(gear=4, rpm=7600.0))[_index("driveline")]
    assert hard > soft


def test_rolling_backwards_out_of_the_pit_box_is_not_a_gearshift():
    deriver = EffectDeriver()
    deriver.update(Frame(gear=1))
    assert deriver.update(Frame(gear=0))[_index("driveline")] == 0.0


def test_the_rev_limiter_gets_a_tick_and_it_is_on_the_edge():
    """A measured flag that was going entirely unused. Over 40 laps it is
    active on 0.08% of frames in 52 episodes of about 42 ms - rare, short and
    unambiguous, which is the profile of something worth a tick and not worth
    a state. Sitting on the limiter down a straight is already reported by the
    engine bed at full revs; what is worth saying is that it just arrived,
    because that is the moment a shift is late."""
    deriver = EffectDeriver()
    deriver.update(Frame(limiter=False))
    hit = deriver.update(Frame(limiter=True))[_index("driveline")]
    assert hit > 0.0
    held = hit
    for _ in range(20):
        held = deriver.update(Frame(limiter=True))[_index("driveline")]
    assert held < hit * 0.2, "it became a tone instead of a tick"


# --------------------------------------------------------------------- road

def test_texture_comes_from_suspension_movement_not_its_position():
    """Height alone is ride height plus load transfer. Its rate of change is
    the part that is surface."""
    deriver = EffectDeriver()
    still = (0.280, 0.280, 0.295, 0.295)
    for _ in range(5):
        flat = deriver.update(Frame(suspension=still))[_index("road")]
    # A car sitting lower but just as still is not on a rougher road.
    lower = (0.270, 0.270, 0.285, 0.285)
    for _ in range(5):
        also_flat = deriver.update(Frame(suspension=lower))[_index("road")]
    assert also_flat <= flat + 0.05

    moving = deriver.update(Frame(suspension=(0.300, 0.262, 0.310, 0.278)))
    assert moving[_index("road")] > flat


def test_the_same_bump_matters_less_at_walking_pace():
    """His SimHub rumble had `MaxEffectSpeed 130`: the suspension is moving
    less at 40 km/h, so the same reading is not the same event."""
    fast = EffectDeriver()
    fast.update(Frame(speed=40.0, suspension=(0.280, 0.280, 0.295, 0.295)))
    quick = fast.update(Frame(speed=40.0,
                              suspension=(0.300, 0.300, 0.315, 0.315)))
    slow = EffectDeriver()
    slow.update(Frame(speed=8.0, suspension=(0.280, 0.280, 0.295, 0.295)))
    crawl = slow.update(Frame(speed=8.0,
                              suspension=(0.300, 0.300, 0.315, 0.315)))
    assert quick[_index("road")] > crawl[_index("road")]


def test_a_kerb_and_the_grass_read_differently_from_tarmac():
    """Surface type is the one input in the whole file that is genuinely
    measured rather than modelled, and the one SimHub's GT7 support cannot see
    at all because it reads the base packet only."""
    deriver = EffectDeriver()
    deriver.update(Frame(surfaces="TTTT"))
    tarmac = deriver.update(Frame(surfaces="TTTT"))[_index("road")]
    deriver.reset()
    deriver.update(Frame(surfaces="TTTT"))
    kerb = deriver.update(Frame(surfaces="TTCC"))[_index("road")]
    deriver.reset()
    deriver.update(Frame(surfaces="TTTT"))
    grass = deriver.update(Frame(surfaces="GGGG"))[_index("road")]
    assert kerb > tarmac
    assert grass > tarmac


def test_a_kerb_is_not_scaled_down_just_because_the_corner_is_slow():
    """A kerb is a kerb - the wheel is on a different surface. Scaling that by
    speed is what made ripple strips feel soft in the hairpins, which is where
    they matter most."""
    deriver = EffectDeriver()
    deriver.update(Frame(speed=10.0, surfaces="TTTT"))
    slow_kerb = deriver.update(Frame(speed=10.0, surfaces="TTCC"))[_index("road")]
    assert slow_kerb > 0.0


# ------------------------------------------------------------------ impacts

def test_arriving_on_a_kerb_thumps_once():
    """A real ripple strip is a thud with a rattle on top. The rattle rides
    the road bed; this is the thud, and it fires on the EDGE because the edge
    is what reads as sharp."""
    deriver = EffectDeriver()
    deriver.update(Frame(surfaces="TTTT"))
    strike = deriver.update(Frame(surfaces="TTCT"))[_index("impact")]
    assert strike > 0.5
    held = strike
    for _ in range(20):
        held = deriver.update(Frame(surfaces="TTCT"))[_index("impact")]
    assert held < strike * 0.2, (
        "sitting on a kerb through a chicane became one long impact")


def test_a_step_in_world_velocity_is_an_impact():
    deriver = EffectDeriver()
    deriver.update(Frame(velocity=(50.0, 0.0, 0.0)))
    hit = deriver.update(Frame(velocity=(46.0, 0.0, 0.0)))[_index("impact")]
    assert hit > 0.5


def test_ordinary_braking_is_not_an_impact():
    """2 g is a heavy stop and it is 0.33 m/s in a frame, well under the
    threshold. His SimHub impact effect ran a threshold of 55 where the others
    were 8 to 28, which is him saying this should fire rarely."""
    deriver = EffectDeriver()
    deriver.update(Frame(velocity=(50.0, 0.0, 0.0)))
    braking = deriver.update(Frame(velocity=(49.67, 0.0, 0.0)))[_index("impact")]
    assert braking == 0.0


def test_a_sausage_kerb_is_a_hit_even_when_the_surface_never_says_kerb():
    """A sausage clipped at speed is under the wheel for less than one frame,
    so the surface char can miss it entirely - and one mounted behind a ripple
    strip is C-to-C, which the edge trigger rejects on purpose. The spring
    stays compressed for frames afterwards, and that step is the witness:
    30 mm into one wheel in one frame is 1.8 m/s, above everything eight laps
    of tarmac and kerb-riding produced."""
    deriver = EffectDeriver()
    rest = (0.280, 0.280, 0.295, 0.295)
    deriver.update(Frame(speed=45.0, suspension=rest))
    deriver.update(Frame(speed=45.0, suspension=rest))
    hit = deriver.update(Frame(
        speed=45.0, suspension=(0.310, 0.280, 0.295, 0.295)))[_index("impact")]
    assert hit >= 0.7
    held = hit
    for _ in range(25):
        held = deriver.update(Frame(
            speed=45.0, suspension=(0.310, 0.280, 0.295, 0.295)))[_index("impact")]
    assert held < hit * 0.3, "a single clip became one long impact"


def test_a_kerb_boost_needs_the_car_to_be_moving():
    """Session 41: a spin left the car crawling back across kerb and grass at
    14-31 km/h, and the surface boosts - added after the texture's own speed
    scaling, so with no floor under them - held the road bed at 0.15-0.49 for
    four seconds. Reported as "prolonged rumble after going off track". At
    speed a kerb is a kerb; at a crawl it is nothing."""
    deriver = EffectDeriver()
    deriver.update(Frame(speed=45.0, surfaces="CCTT"))       # 162 km/h
    riding = deriver.update(Frame(speed=45.0, surfaces="CCTT"))[_index("road")]
    assert riding >= 0.14, "a kerb at speed must keep its boost"
    deriver.reset()
    deriver.update(Frame(speed=4.0, surfaces="CCTT"))        # 14 km/h crawl
    crawl = deriver.update(Frame(speed=4.0, surfaces="CCTT"))[_index("road")]
    assert crawl < 0.05, f"a kerb at walking pace rumbled at {crawl:.2f}"


def test_crawling_across_grass_after_an_off_is_quiet():
    """The other half of the same incident: two wheels on grass at crawling
    speed took the off-surface boost at full."""
    deriver = EffectDeriver()
    deriver.update(Frame(speed=5.0, surfaces="GTGT"))        # 18 km/h
    crawl = deriver.update(Frame(speed=5.0, surfaces="GTGT"))[_index("road")]
    assert crawl < 0.08, f"grass at walking pace rumbled at {crawl:.2f}"
    deriver.reset()
    deriver.update(Frame(speed=30.0, surfaces="GTGT"))       # 108 km/h
    fast = deriver.update(Frame(speed=30.0, surfaces="GTGT"))[_index("road")]
    assert fast >= 0.2, "running wide at speed must still read as off"


def test_a_sausage_inside_a_ripple_strip_is_not_swallowed_by_the_edge_thump():
    """T7, measured: the strike fired at 0.77 in the same frames the strip's
    edge thump held the channel at 0.87-1.00, and max() never let the sausage
    win a frame - so the driver felt the strip and no sausage, twice. While a
    strike runs, it owns the channel: hit, gap, hit. The gap punched into the
    thump's ring is the part nothing else in the mix can produce."""
    deriver = EffectDeriver()
    rest = (0.280, 0.280, 0.295, 0.295)
    deriver.update(Frame(speed=30.0, surfaces="TTTT", suspension=rest))
    # Arrive on the strip: the edge thump fires and rings.
    deriver.update(Frame(speed=30.0, surfaces="CCTT", suspension=rest))
    # Clip the sausage while the thump is still loud.
    spiked = (0.315, 0.280, 0.295, 0.295)
    hit = deriver.update(Frame(
        speed=30.0, surfaces="CCTT", suspension=spiked))[_index("impact")]
    assert hit >= 0.7
    levels = [deriver.update(Frame(
        speed=30.0, surfaces="CCTT", suspension=spiked))[_index("impact")]
        for _ in range(12)]
    assert min(levels) < 0.05, (
        f"no gap - the strike drowned in the edge thump: {levels}")
    assert max(levels) > 0.4, f"no second tap: {levels}"


def test_riding_a_ripple_strip_is_not_a_sausage_strike():
    """Kerb-riding oscillation measured p99 1.39 m/s over eight laps; the
    strike onset sits above it so the strip keeps its texture-and-edge feel
    rather than machine-gunning thumps."""
    deriver = EffectDeriver()
    low = (0.280, 0.280, 0.295, 0.295)
    high = (0.288, 0.288, 0.295, 0.295)      # 8 mm = 0.48 m/s, strip motion
    deriver.update(Frame(speed=20.0, surfaces="CCTT", suspension=low))
    ride = 0.0
    for _ in range(30):
        ride = max(ride, deriver.update(Frame(
            speed=20.0, surfaces="CCTT", suspension=high))[_index("impact")])
        ride = max(ride, deriver.update(Frame(
            speed=20.0, surfaces="CCTT", suspension=low))[_index("impact")])
    assert ride < 0.1, ride


def test_bouncing_across_grass_is_not_a_sausage_strike():
    """Off the racing surface this exact signature is the ground being rough,
    not an event; the load model already holds its peace there and so does
    the strike."""
    deriver = EffectDeriver()
    rest = (0.280, 0.280, 0.295, 0.295)
    deriver.update(Frame(speed=30.0, surfaces="GGGG", suspension=rest))
    bounce = deriver.update(Frame(
        speed=30.0, surfaces="GGGG",
        suspension=(0.315, 0.280, 0.295, 0.295)))[_index("impact")]
    assert bounce == 0.0


# ------------------------------------------------------------- chassis load

def test_load_is_in_g_so_it_means_the_same_in_every_car():
    """The model this replaced compared measured yaw against the yaw a
    neutral-steer car would have done, which is only valid in the tyres'
    linear range: measured over a real lap it correlated 0.991 with steering
    times speed - it was a steering meter - and sat at full scale for 34-53%
    of every lap. A signal that saturates cannot be used to judge how much
    speed to carry, which is what he wanted it for."""
    deriver = EffectDeriver()
    index = _index("chassis_load")
    gentle = deriver.update(Frame(speed=50.0, yaw=0.10))[index]   # 0.51 g
    hard = deriver.update(Frame(speed=50.0, yaw=0.30))[index]     # 1.53 g
    limit = deriver.update(Frame(speed=50.0, yaw=0.40))[index]    # 2.04 g
    assert 0.0 < gentle < hard < limit < 1.0, (gentle, hard, limit)


def test_a_car_going_straight_is_not_loaded():
    deriver = EffectDeriver()
    assert deriver.update(Frame(speed=70.0, yaw=0.0))[_index("chassis_load")] == 0.0


def test_load_does_not_depend_on_the_sign_of_a_channel_nobody_verified():
    """`recorder.py` records `angvel_y`'s sign as still unverified. Taking the
    magnitude means a left-hander and a right-hander feel the same, which is
    correct, and means a sign convention that flipped would change nothing."""
    deriver = EffectDeriver()
    index = _index("chassis_load")
    left = deriver.update(Frame(speed=50.0, yaw=0.30))[index]
    right = deriver.update(Frame(speed=50.0, yaw=-0.30))[index]
    assert left == right


def test_a_stationary_car_is_not_loaded_however_it_is_spinning():
    deriver = EffectDeriver()
    assert deriver.update(Frame(speed=1.0, yaw=3.0))[_index("chassis_load")] == 0.0


# ---------------------------------------------------- the two critical cues

def test_ordinary_acceleration_does_not_reach_the_traction_channel():
    """The defect the whole rebuild was for, checked where the driver feels
    it rather than where the model computes it."""
    deriver = EffectDeriver()
    out = _settle(deriver, throttle=0.8, rear_slip=1.032)
    assert out[_index("rear_traction")] == 0.0


def test_a_genuine_slide_does_reach_it():
    deriver = EffectDeriver()
    _settle(deriver, throttle=0.8, rear_slip=1.032)
    for _ in range(6):
        out = deriver.update(Frame(throttle=0.9, rear_slip=1.16))
    assert out[_index("rear_traction")] > 0.5


def test_the_abs_working_reaches_the_brake_channel_but_not_at_alarm_level():
    deriver = EffectDeriver()
    _settle(deriver, throttle=0.5, rear_slip=1.02)
    for _ in range(60):
        out = deriver.update(Frame(brake=1.0, front_slip=0.87, rear_slip=0.94))
    level = out[_index("brake_limit")]
    assert 0.0 < level < 0.6
    assert deriver.state.brake_state == vehicle.BRAKE_LIMIT_S


def test_the_two_critical_channels_stay_separate():
    """One reports the front axle under braking and the other the rear under
    power. They used to be the same channel, on the reasoning that a piston
    cannot say which end - which turned out to be wrong twice over, because
    the events barely overlap in time and the rig has two usable regions an
    octave apart."""
    deriver = EffectDeriver()
    _settle(deriver, throttle=0.5, rear_slip=1.02)
    for _ in range(8):
        braking = deriver.update(Frame(brake=1.0, front_slip=0.74,
                                       rear_slip=0.95))
    assert braking[_index("brake_limit")] > 0.5
    assert braking[_index("rear_traction")] == 0.0


# ---------------------------------------------------------------- modifiers

def test_going_light_is_reported_as_a_modifier_and_not_as_an_effect():
    """It must not add energy. A real car goes quiet over a crest, and
    reproducing that costs no band at all."""
    deriver = EffectDeriver()
    _settle(deriver, frames=600, throttle=0.4, rear_slip=1.01)
    for _ in range(6):
        out = deriver.update(Frame(throttle=0.4, rear_slip=1.01,
                                   suspension=(0.255, 0.255, 0.270, 0.270)))
    unload = len(EffectDeriver.NAMES) + EffectDeriver.MODIFIERS.index("unload")
    assert out[unload] > 0.5


# ------------------------------------------------------------ observability

def test_it_can_say_what_it_just_decided():
    """"What exactly caused that vibration" is asked an hour after the
    session, and can only be answered if the numbers were kept at the time."""
    deriver = EffectDeriver()
    _settle(deriver, throttle=0.8, rear_slip=1.032)
    report = deriver.explain()
    assert set(report) == {"traction", "brake", "rotation", "load", "surface",
                           "inputs"}
    assert report["traction"]["state"] in (
        vehicle.GRIPPED, vehicle.APPROACHING_SLIP, vehicle.USEFUL_SLIP)
    assert report["traction"]["reference"] is not None
    assert report["inputs"]["throttle"] == 0.8


def test_a_session_boundary_clears_everything_behind_the_effects():
    deriver = EffectDeriver()
    _settle(deriver, throttle=0.8, rear_slip=1.032)
    assert deriver.state.slip_reference is not None
    deriver.reset()
    assert deriver.state.slip_reference is None
