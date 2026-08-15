"""The derived vehicle states, driven with no car and no sound card.

Every test here is a driving situation described in packets. That is the only
honest way to test a model whose whole job is to tell one situation from
another: asserting that a function returns 0.7 proves the arithmetic, and the
faults this module exists to prevent were never arithmetic faults. They were a
lock detector that reported the ABS for a second in every braking zone, and a
wheelspin detector that was reading how hard he was accelerating.
"""
from __future__ import annotations

from pitcrew.rig import vehicle as V


class Frame:
    """One packet, in the fields `VehicleModel` reads.

    A stub rather than a real `GT7Packet` on purpose: a real one needs 72
    fields to say "the rear wheels are turning 8% faster than the road", and a
    test nobody can read is a test nobody maintains.
    """

    def __init__(self, *, speed=50.0, throttle=0.0, brake=0.0, yaw=0.0,
                 heading=0.0, front_slip=1.0, rear_slip=1.0, gear=4,
                 suspension=(0.280, 0.280, 0.295, 0.295), surfaces="TTTT",
                 limiter=False, radius=0.355, steering=0.0):
        self.speed_ms = speed
        self.throttle = throttle
        self.brake = brake
        self.angvel_y = yaw
        # The model reads a heading from the world velocity vector, so a test
        # states the heading and the vector follows from it. The sign of the
        # path heading against the yaw rate is measured and negative - see
        # `vehicle.HEADING_SIGN` - so a test that wants agreement writes the
        # heading advancing in the opposite sense to the yaw.
        import math
        self.vel_x = speed * math.cos(heading)
        self.vel_z = speed * math.sin(heading)
        self.vel_y = 0.0
        for name, slip in (("fl", front_slip), ("fr", front_slip),
                           ("rl", rear_slip), ("rr", rear_slip)):
            setattr(self, f"wheel_rps_{name}", slip * speed / radius)
            setattr(self, f"tyre_radius_{name}", radius)
        for name, height in zip(("fl", "fr", "rl", "rr"), suspension):
            setattr(self, f"suspension_{name}", height)
        self.current_gear = gear
        self.rev_limiter_active = limiter
        self.surface_types = tuple(surfaces)
        self.steering_norm = steering


def settle(model, *, frames=400, throttle=0.6, rear_slip=1.03, **kw):
    """Run enough ordinary driving that the learned references have a value.

    Nothing in this module reports anything until it knows what normal looks
    like, which is the design and is also the thing most likely to surprise
    someone writing a test.
    """
    state = None
    for _ in range(frames):
        state = model.update(Frame(throttle=throttle, rear_slip=rear_slip, **kw))
    return state


# --------------------------------------------------------- the learned floor

def test_it_says_it_does_not_know_before_it_has_learned_anything():
    """A number built on nothing is worse than no number. The traction state
    is UNKNOWN until a reference exists, rather than reporting the raw slip
    ratio as if it meant something."""
    model = V.VehicleModel()
    state = model.update(Frame(throttle=0.8, rear_slip=1.03))
    assert state.traction == V.UNKNOWN
    assert state.traction_confidence == V.NONE


def test_ordinary_acceleration_is_not_wheelspin():
    """**The defect this whole module was written for.**

    Measured over 278,034 frames of his own laps, the rear axle reads 1.032
    while the car is simply accelerating and never reads below 1.023 on
    throttle. The old threshold was 1.04. So the effect meant to tell him the
    rear was sliding was an amplitude-modulated readout of the throttle pedal.
    """
    model = V.VehicleModel()
    state = settle(model, throttle=0.8, rear_slip=1.032)
    assert state.traction == V.GRIPPED, (
        f"steady 3.2% rear slip at 80% throttle read as {state.traction}")
    assert state.traction_level == 0.0
    assert state.slip_reference is not None
    assert 0.02 < state.slip_reference < 0.045


def test_the_same_slip_at_a_different_throttle_is_a_different_claim():
    """Expected slip rises with the torque going through the axle - measured,
    from 0.0002 at a closed throttle to 0.0596 at 80%. A single reference
    subtracted everywhere would call ordinary full-throttle driving a slide and
    a genuine lift-off slide nothing at all."""
    model = V.VehicleModel()
    # Teach both ends of the range: heavy throttle runs 3.2% slip, trailing
    # throttle runs almost none.
    for _ in range(400):
        model.update(Frame(throttle=0.9, rear_slip=1.032))
    for _ in range(400):
        model.update(Frame(throttle=0.05, rear_slip=1.001))
    high = model.update(Frame(throttle=0.9, rear_slip=1.032))
    low = model.update(Frame(throttle=0.05, rear_slip=1.032))
    assert high.traction == V.GRIPPED
    assert low.traction_level > 0.0, (
        "3.2% slip off the throttle is the rear coming round, not driving")


def test_the_reference_does_not_learn_the_wheelspin():
    """A mean would. Hold the rear at 12% slip for ten seconds and an averaging
    reference climbs to meet it, so the cue fades exactly where it should be
    loudest. A low quantile cannot be dragged up by the tail it is measuring."""
    model = V.VehicleModel()
    settle(model, throttle=0.8, rear_slip=1.032)
    before = model.state.slip_reference
    for _ in range(600):
        state = model.update(Frame(throttle=0.8, rear_slip=1.12))
    assert state.traction_level > 0.5, "it stopped reporting a ten-second slide"
    assert model.state.slip_reference is not None
    assert model.state.slip_reference < before + 0.01


# ------------------------------------------------------------ rear traction

def test_wheelspin_climbs_through_its_states():
    model = V.VehicleModel()
    settle(model, throttle=0.8, rear_slip=1.032)
    seen = []
    for slip in (1.032, 1.05, 1.07, 1.10, 1.20):
        for _ in range(10):
            state = model.update(Frame(throttle=0.9, rear_slip=slip))
        seen.append(state.traction)
    assert seen[0] == V.GRIPPED
    assert V.EXCESSIVE_WHEELSPIN in seen
    assert seen[-1] == V.SEVERE_TRACTION_LOSS
    # And it is monotonic in level, which is what makes it learnable.
    order = [V.GRIPPED, V.APPROACHING_SLIP, V.USEFUL_SLIP,
             V.EXCESSIVE_WHEELSPIN, V.SEVERE_TRACTION_LOSS]
    ranks = [order.index(name) for name in seen]
    assert ranks == sorted(ranks), seen


def test_a_gearshift_is_not_wheelspin():
    """The driveline steps when the gear does and the wheel rate steps with
    it. A rear that is genuinely spinning is still spinning 50 ms later, so
    blanking the shift costs nothing real."""
    model = V.VehicleModel()
    settle(model, throttle=0.8, rear_slip=1.032, gear=4)
    spike = model.update(Frame(throttle=0.8, rear_slip=1.25, gear=5))
    assert spike.traction_level == 0.0
    assert spike.shifted is True


def test_a_single_frame_of_noise_does_not_become_a_state():
    """Two frames to confirm. One frame is 17 ms, which is below anything the
    body reads as an event and well inside what one bad packet can produce."""
    model = V.VehicleModel()
    settle(model, throttle=0.8, rear_slip=1.032)
    model.update(Frame(throttle=0.8, rear_slip=1.30))
    assert model.state.traction != V.SEVERE_TRACTION_LOSS
    model.update(Frame(throttle=0.8, rear_slip=1.30))
    assert model.state.traction == V.SEVERE_TRACTION_LOSS


def test_a_slide_is_reported_the_frame_it_starts_and_lets_go_slowly():
    """Attack and release are different questions. A limit cue that arrives
    late is not a warning; one that stops the instant the wheel does chatters
    at its own threshold."""
    model = V.VehicleModel()
    settle(model, throttle=0.8, rear_slip=1.032)
    first = model.update(Frame(throttle=0.9, rear_slip=1.14))
    assert first.traction_level > 0.4, "the slide was not reported immediately"
    back = model.update(Frame(throttle=0.9, rear_slip=1.032))
    assert back.traction_level > 0.2, "it cut out the moment the wheel gripped"


def test_nothing_is_reported_below_walking_pace():
    """The ratio divides by a speed that means nothing and the velocity
    heading is noise."""
    model = V.VehicleModel()
    settle(model, throttle=0.8, rear_slip=1.032)
    state = model.update(Frame(speed=2.0, throttle=1.0, rear_slip=2.0))
    assert state.traction_level == 0.0
    assert state.brake_level == 0.0


# ----------------------------------------------------------------- braking

def test_the_abs_regulating_is_reported_as_the_limit_and_not_as_a_lock():
    """**The other defect this module was written for.**

    Measured: GT7's ABS holds the front axle at 7-15% slip for a median of
    1292 ms at a time, 204 times over 40 laps. The detector this replaces had
    its threshold at 10% and a 220 ms attack added to reject a pulse train
    that does not exist - so it reported a full lock-up through most of every
    braking zone. Reported from the seat as "ABS is way too strong".
    """
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    for _ in range(120):                       # two seconds of hard braking
        state = model.update(Frame(brake=1.0, front_slip=0.87, rear_slip=0.94))
    assert state.brake_state == V.BRAKE_LIMIT_S
    assert state.brake_level < 0.55, (
        "the regulator working is information, not an alarm")
    assert state.brake_level > 0.0, "and it is worth feeling"


def test_a_real_lock_goes_past_the_regulated_plateau_and_says_so():
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    for _ in range(60):
        model.update(Frame(brake=1.0, front_slip=0.88, rear_slip=0.95))
    for _ in range(6):
        state = model.update(Frame(brake=1.0, front_slip=0.76, rear_slip=0.95))
    assert state.brake_state == V.BRAKE_LOCKED
    assert state.brake_level > 0.6
    assert state.brake_axle == "front"


def test_the_lock_threshold_can_never_be_learned_away():
    """The plateau is learned so the model works with the assist off as well
    as on. A learner that could only make the system less sensitive would be a
    learner that could switch it off, so it is floored."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    for _ in range(3000):     # fifty seconds of the deepest braking there is
        state = model.update(Frame(brake=1.0, front_slip=0.75, rear_slip=0.95))
    assert state.lock_threshold >= V.LOCK_FLOOR
    assert state.brake_state == V.BRAKE_LOCKED, (
        "it learned the lock and stopped reporting it")


def test_a_lock_up_needs_the_brake_to_be_on():
    """A wheel reading slow in the air over a kerb is not a lock-up, and the
    brake pedal is what separates the two."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    state = model.update(Frame(brake=0.0, front_slip=0.60, rear_slip=0.60))
    assert state.brake_state == V.BRAKE_FREE
    assert state.brake_level == 0.0


def test_the_rear_locking_harder_than_the_front_is_its_own_state():
    """Rare and sharp: measured, the front locks more on 97% of braking
    frames. The rear going first under trail braking is the one that spins the
    car, and it is a different correction from a front lock."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    for _ in range(8):
        state = model.update(Frame(brake=0.6, front_slip=0.94, rear_slip=0.90))
    assert state.brake_state == V.BRAKE_REAR_UNSTABLE
    assert state.brake_axle == "rear"


def test_an_unloaded_wheel_under_braking_is_not_called_a_lock():
    """It slows because nothing is holding it down. Worth knowing; not the
    same claim, and not worth full authority."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02,
           suspension=(0.280, 0.280, 0.295, 0.295))
    light = (0.255, 0.255, 0.270, 0.270)
    for _ in range(10):
        state = model.update(Frame(brake=1.0, front_slip=0.70, rear_slip=0.95,
                                   suspension=light))
    assert state.unload > 0.4
    assert state.brake_state == V.BRAKE_INCIPIENT
    assert state.reasons.get("brake") == "wheel unloaded"


# ---------------------------------------------------------------- rotation

def test_rotation_is_unknown_until_the_two_channels_have_been_checked():
    """The sideslip model rests on a sign measured on recorded laps. A sign
    that silently flipped would turn an oversteer warning into a reward for
    it, so the cue is withheld until yaw and the velocity heading have been
    shown to agree."""
    model = V.VehicleModel()
    state = model.update(Frame(speed=60.0))
    assert state.rotation == V.UNKNOWN
    assert state.rotation_confidence == V.NONE


def test_a_car_going_where_it_points_is_not_rotating():
    model = V.VehicleModel()
    heading = 0.0
    yaw = 0.30
    state = None
    for _ in range(900):
        heading += V.HEADING_SIGN * yaw * V.FRAME_S
        state = model.update(Frame(speed=55.0, yaw=yaw, heading=heading))
    assert state.rotation_confidence == V.MEDIUM
    assert state.rotation in (V.ROTATION_NEUTRAL, V.ROTATION_ROTATING)
    assert abs(state.beta_deg) < V.BETA_ONSET_DEG


def test_the_rotation_cue_never_claims_more_than_medium_confidence():
    """It was validated against a path heading reconstructed from positions
    stored to the centimetre, which puts its own noise floor at 0.06 deg
    against 0.18 deg of real sideslip at the limit. Live it should be far
    better, because the velocity vector needs no differencing - but that has
    not been recorded yet, and until it has, the number is not promoted."""
    model = V.VehicleModel()
    heading = 0.0
    for _ in range(900):
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
        state = model.update(Frame(speed=55.0, yaw=0.30, heading=heading))
    assert state.rotation_confidence != V.HIGH


def test_channels_that_stop_agreeing_take_the_cue_with_them():
    """A second witness, in the same spirit as the transducer's endpoint
    meter: an output that can be confidently wrong needs one."""
    model = V.VehicleModel()
    heading = 0.0
    for _ in range(900):
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
        model.update(Frame(speed=55.0, yaw=0.30, heading=heading))
    assert model.state.rotation_confidence == V.MEDIUM
    # Now the heading stops tracking the yaw entirely.
    import math
    for index in range(900):
        state = model.update(Frame(speed=55.0, yaw=0.30,
                                   heading=math.sin(index * 0.7)))
    assert state.rotation == V.UNKNOWN
    assert state.rotation_level == 0.0


def test_the_rear_coming_round_off_the_throttle_still_reaches_the_driver():
    """The case a wheel-speed model is blind to. Lift-off and trail-braking
    oversteer produce no wheelspin at all, and they are the ones that cost him
    most - so the traction cue takes the larger of two witnesses rather than
    trusting the wheels alone."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    heading = 0.0
    for _ in range(900):                       # earn the heading check
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
        model.update(Frame(speed=55.0, yaw=0.30, heading=heading,
                           throttle=0.5, rear_slip=1.02))
    assert model.state.rotation_confidence == V.MEDIUM
    # The chassis now turns faster than the path it is on: the rear is going,
    # and no wheel is spinning.
    for _ in range(12):
        state = model.update(Frame(speed=55.0, yaw=0.95, heading=heading,
                                   throttle=0.0, rear_slip=1.00))
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
    assert state.rotation_level > 0.0
    assert state.traction_level > 0.0
    assert state.reasons.get("traction") == "rotation"


# -------------------------------------------------------------------- load

def test_bigger_suspension_numbers_mean_more_load():
    """Measured, not assumed, because the sign decides whether a crest reads
    as unloading or as bottoming: the front reads 290.2 mm under heavy braking
    against 284.7 cruising, and the rear 279.9 against 301.5."""
    model = V.VehicleModel()
    settle(model, frames=600, throttle=0.4, rear_slip=1.01)
    loaded = model.update(Frame(throttle=0.4, rear_slip=1.01,
                                suspension=(0.300, 0.300, 0.315, 0.315)))
    assert loaded.load_front > 0.0
    assert loaded.unload == 0.0


def test_a_crest_reads_as_the_car_going_light():
    model = V.VehicleModel()
    settle(model, frames=600, throttle=0.4, rear_slip=1.01)
    for _ in range(6):
        state = model.update(Frame(throttle=0.4, rear_slip=1.01,
                                   suspension=(0.255, 0.255, 0.270, 0.270)))
    assert state.unload > 0.5
    assert state.load_front == 0.0


def test_a_landing_is_the_return_and_not_the_flight():
    """A car that has been light and then compresses hard has landed; the same
    compression without the lightness before it is a dip in the road."""
    model = V.VehicleModel()
    settle(model, frames=600, throttle=0.4, rear_slip=1.01)
    for _ in range(10):
        model.update(Frame(throttle=0.4, rear_slip=1.01,
                           suspension=(0.250, 0.250, 0.265, 0.265)))
    landed = 0.0
    for _ in range(6):
        state = model.update(Frame(throttle=0.4, rear_slip=1.01,
                                   suspension=(0.320, 0.320, 0.335, 0.335)))
        landed = max(landed, state.landed)
    assert landed > 0.0

    fresh = V.VehicleModel()
    settle(fresh, frames=600, throttle=0.4, rear_slip=1.01)
    without = 0.0
    for _ in range(6):
        state = fresh.update(Frame(throttle=0.4, rear_slip=1.01,
                                   suspension=(0.320, 0.320, 0.335, 0.335)))
        without = max(without, state.landed)
    assert without == 0.0, "a compression with no flight before it is a bump"


# ----------------------------------------------------------------- surface

def test_arriving_on_a_kerb_from_tarmac_is_a_strike():
    model = V.VehicleModel()
    model.update(Frame(surfaces="TTTT"))
    state = model.update(Frame(surfaces="TTCT"))
    assert state.kerb_strike == 1.0
    assert state.on_kerb is True


def test_scrabbling_back_over_a_kerb_from_the_grass_is_not_a_strike():
    """`car_on_track` is GT7's flags bit 0 and means "in a session" rather than
    "on the racing surface", so a run wide used to fire a full-strength apex
    hit on the way back."""
    model = V.VehicleModel()
    model.update(Frame(surfaces="GGGG"))
    state = model.update(Frame(surfaces="CCGG"))
    assert state.kerb_strike == 0.0
    assert state.off_surface is True


def test_a_packet_without_surface_types_reports_no_surface_rather_than_tarmac():
    """Formats A and B carry no surface channel. Missing is not "on tarmac"."""
    model = V.VehicleModel()
    frame = Frame()
    frame.surface_types = None
    state = model.update(frame)
    assert state.on_kerb is False
    assert state.off_surface is False
    assert state.kerb_strike == 0.0


# ------------------------------------------------------------------ hygiene

def test_a_session_boundary_forgets_everything_learned():
    """A garage visit teleports the car, which makes every differenced channel
    produce an event that never happened."""
    model = V.VehicleModel()
    settle(model, throttle=0.8, rear_slip=1.032)
    assert model.state.slip_reference is not None
    model.reset()
    assert model.update(Frame(throttle=0.8, rear_slip=1.032)).traction == V.UNKNOWN
