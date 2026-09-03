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
                 limiter=False, radius=0.355, steering=0.0,
                 road_plane_y=1.0):
        self.speed_ms = speed
        # The Y component of the road-surface normal: 1.0 is level, 0.857 is
        # Daytona's 31 degrees of banking.
        self.road_plane_y = road_plane_y
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
        state = model.update(Frame(brake=1.0, front_slip=0.90, rear_slip=0.94))
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
    assert state.lock_threshold >= V.ABS_ON.lock_floor
    assert state.brake_state == V.BRAKE_LOCKED, (
        "it learned the lock and stopped reporting it")


def test_a_lock_does_not_teach_the_plateau_that_locking_is_normal():
    """The quantile converges on the quantile of the stream it is shown, and
    it was being shown its own detections. Session 39, from the seat: braking
    over the top in the first corners, then the cue "learns", then it goes
    very quiet - 3.4 s of deep braking moved the threshold up 0.05 and the
    session did not contain the ~19 s of braking needed to work it back off.
    The upward step is blanked during the event, like the slip reference."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    state = None
    for _ in range(60):
        state = model.update(Frame(brake=1.0, front_slip=0.88, rear_slip=0.95))
    before = state.lock_threshold
    for _ in range(240):                           # four seconds locked solid
        state = model.update(Frame(brake=1.0, front_slip=0.74, rear_slip=0.95))
    assert state.brake_state == V.BRAKE_LOCKED
    # One step of tolerance, and it is arithmetic rather than slack: the
    # threshold each frame is computed from the plateau as it stood BEFORE
    # that frame's update, so the last honest rise of the unlocked segment
    # lands in the first locked frame's threshold. Anything beyond one step is
    # the lock teaching the detector, which is what this test is about.
    carry = V.PLATEAU_STEP * V.PLATEAU_QUANTILE * V.PLATEAU_MARGIN
    assert state.lock_threshold <= before + carry, (
        "the lock event taught the detector to stop detecting it")


def test_deep_but_unlocked_regulation_still_raises_the_threshold():
    """Blanking must not freeze the learner. A car that regulates deeper than
    the floor teaches from the band below the threshold, so the threshold can
    still follow the car - it just cannot be taught by the locks it exists to
    catch."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    state = None
    for _ in range(300):
        state = model.update(Frame(brake=1.0, front_slip=0.88, rear_slip=0.95))
    assert state.lock_threshold > V.ABS_ON.lock_floor


def test_a_lock_up_needs_the_brake_to_be_on():
    """A wheel reading slow in the air over a kerb is not a lock-up, and the
    brake pedal is what separates the two."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    state = model.update(Frame(brake=0.0, front_slip=0.60, rear_slip=0.60))
    assert state.brake_state == V.BRAKE_FREE
    assert state.brake_level == 0.0


def test_the_rear_reading_slow_under_brakes_alone_is_not_instability():
    """**The witness this replaces was measured and retired.** A rear axle
    running a few percent slower than the front under braking is engine
    braking on the driven axle - replayed over two cars, the old wheel-bias
    state fired 108 times in a day and the chassis was rotating during 1-3%
    of its frames. With no rotation, a modest rear bias must read as braking,
    not as the rear stepping out, and nothing may reach the traction voice."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    for _ in range(8):
        state = model.update(Frame(brake=0.6, front_slip=0.94, rear_slip=0.90))
    assert state.brake_state in (V.BRAKE_STABLE_S, V.BRAKE_LIMIT_S)
    assert state.rear_unstable == 0.0
    assert state.traction_level == 0.0


def test_the_rear_coming_round_on_the_brakes_reads_in_the_tyre_voice():
    """Asked for directly (session 41): "traction loss from throttle is very
    intuitive... match the rear traction loss [on braking] to more like the
    throttle traction loss." So the rear stepping out under trail braking is
    not a brake state: the rotation witness carries it into the traction
    channel - the same voice, ramp and rhythm as a power-on slide - while the
    brake channel keeps reporting the braking itself."""
    import math
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    heading = 0.0
    for _ in range(900):                       # earn the heading check
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
        model.update(Frame(speed=55.0, yaw=0.30, heading=heading,
                           throttle=0.5, rear_slip=1.02))
    assert model.state.rotation_confidence == V.HIGH
    # Trail braking, and the chassis turns faster than the path it is on.
    for _ in range(12):
        state = model.update(Frame(speed=55.0, yaw=0.95, heading=heading,
                                   brake=0.6, throttle=0.0,
                                   front_slip=0.93, rear_slip=0.96))
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
    assert state.traction_level > 0.0, "the tyre voice must carry it"
    assert state.reasons.get("traction") == "rotation"
    assert state.rear_unstable > 0.0, "the explainer keeps the braking view"
    assert state.brake_state in (V.BRAKE_STABLE_S, V.BRAKE_LIMIT_S,
                                 V.BRAKE_INCIPIENT, V.BRAKE_LOCKED), (
        "the brake channel reports braking, not the rear")


def test_braking_at_the_optimum_is_silence_and_the_rasp_is_the_error():
    """The driver's own mapping, chosen after two other shapes: "quiet at
    optimum, grow as brake locking worsens." The boundary is marked by the
    ONSET of feedback - silence turning into anything is the change a body
    notices best - so braking done well must feel like nothing at all.

    **The slip that counts as "done well" is written from the anchors, not
    typed in.** This test used to hold 0.100 as "exactly the measured peak",
    which it was on v1.70. Re-measured on v1.71 the peak is 0.065, so 0.100
    became a tenth past it and the test failed by correctly reporting a rasp.
    Taking the number from `ABS_ON` keeps the test about the SHAPE - silence
    at the peak, growth past it - which is the part the driver chose and the
    part that has to survive every re-measurement."""
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)
    at_peak = 1.0 - (V.ABS_ON.rasp_from + 0.001)
    past_peak = 1.0 - (V.ABS_ON.rasp_from + 0.045)
    state = None
    for _ in range(60):
        state = model.update(Frame(brake=1.0, front_slip=at_peak,
                                   rear_slip=at_peak + 0.06))
    assert state.brake_state == V.BRAKE_LIMIT_S
    assert state.brake_level < 0.02, "braking done well must be silent"
    for _ in range(60):            # let it slide past the peak
        state = model.update(Frame(brake=1.0, front_slip=past_peak,
                                   rear_slip=at_peak + 0.06))
    assert state.brake_level > 0.1, "past the peak the rasp must appear"


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
    assert state.rotation_confidence == V.HIGH
    assert state.rotation in (V.ROTATION_NEUTRAL, V.ROTATION_ROTATING)
    assert abs(state.beta_deg) < V.BETA_ONSET_DEG


def test_the_rotation_cue_is_trusted_now_that_the_channel_was_checked():
    """It was capped at MEDIUM while the only available validation had to
    difference positions stored to the centimetre. `vel_x/y/z` were added to
    the recorder to settle it and one lap did: corr -0.978, slope -0.996, and
    a straight-line residual of 0.0059 rad/s p90 - which is 0.10 deg of
    sideslip over a 0.3 s slide against a 1.5 deg onset."""
    model = V.VehicleModel()
    heading = 0.0
    for _ in range(900):
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
        state = model.update(Frame(speed=55.0, yaw=0.30, heading=heading))
    assert state.rotation_confidence == V.HIGH


def test_channels_that_stop_agreeing_take_the_cue_with_them():
    """A second witness, in the same spirit as the transducer's endpoint
    meter: an output that can be confidently wrong needs one."""
    model = V.VehicleModel()
    heading = 0.0
    for _ in range(900):
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
        model.update(Frame(speed=55.0, yaw=0.30, heading=heading))
    assert model.state.rotation_confidence == V.HIGH
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
    assert model.state.rotation_confidence == V.HIGH
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


def test_a_slide_estimate_cannot_get_stuck_after_an_excursion():
    """Reported from the seat as a constant vibration after coming off track.

    The log named it: `rear_traction 0.425@101Hz` with the car stationary and
    `rotation SEVERE_ROTATION 1.00` driving it. Sideslip is an integral, and
    the original design only pulled its reference back above 40 m/s dead
    straight - so any excursion accumulated an offset the car could never work
    off, because it never got fast and straight again. Reproduced at +136 deg
    after two seconds, and +82 deg a full minute later.

    A sideslip angle is a transient quantity. Nothing a driver needs telling
    about lasts ten seconds, so it washes out in four whatever the car is
    doing, and it can never claim more than a spin's worth in the first place.
    """
    model = V.VehicleModel()
    heading = 0.0
    for _ in range(900):
        heading += V.HEADING_SIGN * 0.02 * V.FRAME_S
        model.update(Frame(speed=60.0, yaw=0.02, heading=heading,
                           throttle=0.6, rear_slip=1.03))

    # An excursion: the car rotates hard and the path does not follow.
    for _ in range(120):
        model.update(Frame(speed=25.0, yaw=1.2, heading=heading,
                           throttle=0.0, rear_slip=1.0))
    assert abs(model.state.beta_deg) <= V.BETA_LIMIT_DEG + 1e-6, (
        f"the estimate reached {model.state.beta_deg:.0f} deg - unbounded")

    # And then he trundles back to the pits, never fast or straight enough to
    # retake the old anchor.
    for _ in range(60 * 60):
        heading += V.HEADING_SIGN * 0.05 * V.FRAME_S
        state = model.update(Frame(speed=15.0, yaw=0.05, heading=heading,
                                   throttle=0.2, rear_slip=1.01))
    assert abs(state.beta_deg) < 1.0, (
        f"a minute later it still claims {state.beta_deg:.1f} deg of slide")
    assert state.rotation_level == 0.0
    assert state.traction_level == 0.0, (
        "the rear-traction cue is still being held up by a stuck estimate")


def test_the_braking_cue_stays_quiet_until_it_has_something_to_say():
    """Reported from the seat as "intense from the moment I apply any brake".

    The level is shaped in `_braking` against the measured grip peak - light
    at and below it, climbing above - and that shaping is only worth doing if
    it survives the gain chain. It did not: `min_force` turned the bottom of
    the range into a step, so a level of 0.07 rendered at 0.273.
    """
    from pitcrew.rig.synth import PROFILE

    spec = {s.name: s for s in PROFILE}["brake_limit"]
    model = V.VehicleModel()
    settle(model, throttle=0.5, rear_slip=1.02)

    levels = {}
    for label, front in (("light", 0.945), ("optimum", 0.895),
                         ("past it", 0.855)):
        for _ in range(30):
            state = model.update(Frame(brake=1.0, front_slip=front,
                                       rear_slip=0.97))
        levels[label] = spec.shape(state.brake_level)

    assert levels["light"] < 0.12, (
        f"just touching the brakes renders {levels['light']:.3f} - that is the "
        f"whole complaint")
    assert levels["optimum"] < levels["past it"], (
        "it is no louder past the grip peak than on it, so it says nothing")
    assert levels["past it"] > levels["light"] * 2.5


# ------------------------------------- the reference that could never rise

def test_a_band_below_its_true_value_still_settles():
    """**The deadlock that made the RSR spin its wheels at 247 km/h.**

    `allow_rise=False` withholds the upward step so a stream that is nothing
    but wheelspin cannot teach the estimator that wheelspin is normal. But it
    used to return BEFORE `samples += 1`, and `settled` is a sample count.

    A band sitting below its true value therefore saw every honest sample as
    an event: rise suppressed, sample uncounted, band never settled, for ever.
    An unsettled band is read back by borrowing a neighbour, and the
    neighbours are lower throttle bands with genuinely lower slip - so full
    throttle was measured against a part-throttle reference and the excess
    became a constant. Practice, 22 Aug 2026: EXCESSIVE_WHEELSPIN at 0.54-0.58
    at every speed from 209 to 247 km/h, 56 samples against 9 GRIPPED.
    """
    from pitcrew.rig import vehicle

    q = vehicle._Quantile(vehicle.REFERENCE_QUANTILE, vehicle.REFERENCE_STEP,
                          settle_frames=100, initial=0.008)
    # Every sample above the value, every rise withheld - the locked state.
    for _ in range(500):
        q.update(0.032, allow_rise=False)
    assert q.value == 0.008, "the step was not actually withheld"
    assert q.settled, (
        "a blanked sample was not counted, so the band can never settle and "
        "will be read back by borrowing a neighbour for ever")


def test_an_unsettled_band_learns_whatever_the_caller_says():
    """The blanking guards a reference that already knows what normal is. A
    band that does not yet know must be free to find its level, or it starts
    low, reads every honest sample as an event, and stays low."""
    from pitcrew.rig import vehicle

    ref = vehicle._SlipReference()
    # Full throttle, true slip well above where the band starts, and the
    # caller withholding the rise on every single sample.
    for _ in range(vehicle.REFERENCE_SETTLE_FRAMES * 3):
        ref.observe(1.0, 0.032, allow_rise=False)

    learned = ref.value(1.0)
    assert learned is not None, "the full-throttle band never settled"
    assert learned > 0.02, (
        f"the band stayed at {learned:.4f} against a true 0.032 - it could "
        f"not climb, so normal driving reads as wheelspin")


def test_a_settled_band_is_still_protected_from_the_event():
    """The other half must still hold: once a band knows what normal is, ten
    seconds of held wheelspin must not move it. That is what the blanking is
    for and it is why the cue survives being used at the limit."""
    from pitcrew.rig import vehicle

    ref = vehicle._SlipReference()
    for _ in range(vehicle.REFERENCE_SETTLE_FRAMES * 2):
        ref.observe(1.0, 0.030)
    settled = ref.value(1.0)
    assert settled is not None

    for _ in range(600):                       # ten seconds of a held slide
        ref.observe(1.0, 0.200, allow_rise=False)
    after = ref.value(1.0)
    assert after <= settled + 1e-9, (
        f"the reference learned the event: {settled:.4f} -> {after:.4f}")


# ------------------------------------------- the band that could never fall

def test_a_band_seeded_by_a_pit_exit_snatch_does_not_stay_there_for_ever():
    """**The trapdoor `e132b7b` did not close, replayed from sessions 65/66.**

    `_Quantile` takes its first sample as its estimate, and the first
    full-throttle sample of a session is pit exit at ~18 km/h in first gear,
    where the driveline snatches and the rear axle reads 0.90 one frame and
    1.25 the next. Session 65 seeded band 3 at -0.099.

    Everything after that is above it, so the caller withholds every rise;
    nothing is ever below it, so it never steps down. The band sat at -0.075
    for the whole session while reporting itself settled - measured under
    current code, EXCESSIVE_WHEELSPIN on 94.3% of frames from 209-247 km/h,
    against 5.2% GRIPPED, with the beds ducked 41% underneath it.
    """
    from pitcrew.rig import vehicle

    ref = vehicle._SlipReference()
    ref.observe(1.0, -0.099)                   # the snatch, first sample seen
    band = ref._bands[-1]
    assert band.value != -0.099, (
        "one frame of pit exit became the estimate of normal for the session")
    assert band.value == vehicle.REFERENCE_PRIOR[-1] - vehicle.REFERENCE_STEP * (
        1.0 - vehicle.REFERENCE_QUANTILE), (
        "the snatch should move the seeded band by one ordinary step, no more")

    # A whole pit exit of it, and the band is still on the right side of zero:
    # the seed is what it walks away from, so a snatch costs steps, not the
    # estimate. Below zero is where the trapdoor lived - the caller withholds
    # every rise once the gap exceeds SLIP_USEFUL, and nothing is ever lower.
    for _ in range(vehicle.REFERENCE_SETTLE_FRAMES):
        ref.observe(1.0, -0.099)
    assert band.value > 0.0, f"the band reached {band.value:.4f}"


def test_a_long_slide_never_puts_the_reference_onto_the_event():
    """The regression the first attempt at this introduced, pinned.

    Releasing a long-blanked band by discarding it re-seeded the band from a
    sample taken DURING the event, so the reference landed on the slide and
    the cue read GRIPPED through it - a silent false negative on a CRITICAL
    cue, which is worse than the loud false positive it replaced. However long
    the caller blanks for, the reference must stay where it was.
    """
    from pitcrew.rig import vehicle

    ref = vehicle._SlipReference()
    for _ in range(vehicle.REFERENCE_SETTLE_FRAMES * 2):
        ref.observe(1.0, 0.030)
    honest = ref.value(1.0)

    # A full minute of held 0.120 slide, every frame blanked by the caller.
    for _ in range(3600):
        ref.observe(1.0, 0.120, allow_rise=False)

    after = ref.value(1.0)
    assert after is not None, "the reference was discarded mid-slide"
    assert after <= honest + 1e-9, (
        f"the reference learned the event: {honest:.4f} -> {after:.4f}")
    assert 0.120 - after > vehicle.SLIP_USEFUL, (
        f"the excess fell to {0.120 - after:.4f}, so the slide has gone quiet")


def _drive(ref, throttle, slip, frames):
    """Feed a reference the way `VehicleModel._traction` actually feeds it.

    The caller decides the blanking from the reference it just read - `quiet`
    is `(difference - reference) < SLIP_USEFUL` - so a test that hard-codes
    `allow_rise=False` is describing a caller that does not exist. It also
    hides the interlock that makes the guard work: the caller only withholds
    when the gap is wide, and a wide gap is exactly what leaves a band not yet
    arrived, so a band below the stream is never blanked into staying there.
    """
    for _ in range(frames):
        reference = ref.value(throttle)
        quiet = reference is None or (slip - reference) < V.SLIP_USEFUL
        ref.observe(throttle, slip, allow_rise=quiet)


def test_a_band_below_the_stream_climbs_out_however_it_got_there():
    """The trapdoor closed at the cause, not patched at the symptom.

    Put a band where session 65's was - below the whole stream, with the
    caller withholding every rise - and it must still reach the truth. It can,
    because the guard is armed by ARRIVAL and this band has never arrived: it
    has not once seen a sample within SLIP_USEFUL of itself, so it is still
    learning freely and the caller's blanking does not apply to it.
    """
    from pitcrew.rig import vehicle

    ref = vehicle._SlipReference()
    band = ref._bands[-1]
    band.reset(-0.075)                         # the state session 65 sat in

    _drive(ref, 1.0, 0.013, 4000)
    assert abs(band.value - 0.013) < 0.002, (
        f"the band is at {band.value:.4f} against a true 0.013")


def test_a_car_far_above_the_seed_still_reaches_its_own_value():
    """**The cliff a sample-count gate left behind.** Arming on `settled` gave
    a band 240 samples of free learning, which is 0.0168 of travel - so from
    the 0.0321 seed anything above 0.0489 + SLIP_USEFUL = 0.079 armed the
    guard while still below the stream and stuck there for the session. The
    measured span across three cars is 0.013 to 0.060; that is 1.32x of
    margin, and a high-torque RWD road car is not an exotic way to spend it.

    Arrival is proof rather than elapsed time, so there is no cliff."""
    from pitcrew.rig import vehicle

    for true_value in (0.013, 0.060, 0.079, 0.120, 0.250):
        ref = vehicle._SlipReference()
        _drive(ref, 1.0, true_value, 8000)
        landed = ref._bands[-1].value
        assert abs(landed - true_value) < 0.002, (
            f"a car whose driven axle sits at {true_value} was measured "
            f"against {landed:.4f}, so ordinary throttle reads as wheelspin")


# ------------------------------------------------------ the car underneath

def _packet(*, car_id):
    """A frame that also says which car it came from.

    `Frame` deliberately carries only the fields the model reads to derive a
    state; `car_id` is identity rather than physics, which is why it is added
    here rather than to the stub every other test builds.
    """
    frame = Frame()
    frame.car_id = car_id
    return frame


def test_changing_car_drops_what_was_learned_about_the_last_one():
    """`reset()` runs between SESSIONS. A garage visit inside one session
    swaps the car and leaves the previous car's references in place, and they
    are then read back as if they described this one. Measured across three
    cars in three days, the band-3 slip reference spans 0.013 to 0.060."""
    from pitcrew.rig import vehicle

    model = vehicle.VehicleModel()
    for _ in range(vehicle.REFERENCE_SETTLE_FRAMES * 2):
        model._slip_ref.observe(1.0, 0.060)
    assert model._slip_ref.value(1.0) is not None

    model._note_car(_packet(car_id=3311))      # the RSR, first seen
    assert model._slip_ref.value(1.0) is not None, "first sight is not a change"
    assert not model.car_changed

    model._note_car(_packet(car_id=3391))      # the Shelby
    assert model.car_changed, "the car change was not published"
    assert model._slip_ref.value(1.0) is None, (
        "the Shelby is being told about the Porsche's driven axle")


def test_the_not_loaded_yet_sentinel_is_not_a_car():
    """`car_id` 0 arrives during loading screens. Treating it as a car would
    reset the model twice on every garage visit - the same guard the
    controller applies before it announces a car."""
    from pitcrew.rig import vehicle

    model = vehicle.VehicleModel()
    model._note_car(_packet(car_id=3311))
    for _ in range(vehicle.REFERENCE_SETTLE_FRAMES * 2):
        model._slip_ref.observe(1.0, 0.030)

    model._note_car(_packet(car_id=0))
    assert not model.car_changed, "the sentinel was taken for a car"
    assert model._slip_ref.value(1.0) is not None, "the reference was dropped"


# ------------------------------------------------- the assist in the car

def test_the_brake_scale_follows_the_assist_the_regulations_put_in_the_car():
    """ABS is a property of the event, not of the car or the driver. With a
    regulator the cue is grading distance past a measured grip peak; without
    one there is no peak in the data at all, so it grades distance to the
    lock instead - a different sentence on the same ramp."""
    model = V.VehicleModel()
    model.set_abs("Weak")
    assert model._anchors.rasp_means == "past-peak"
    assert model._anchors.plateau_learned

    model.set_abs("Off")
    assert model._anchors.rasp_means == "approaching-lock"
    assert not model._anchors.plateau_learned, (
        "a q0.85 of an unregulated stream is a quantile of his own pedal")


def test_abs_off_still_speaks_before_the_lock():
    """**The regression the first attempt shipped.** Rendering silence up to
    the lock because no grip peak resolves cut the cue on his current series
    from 1.5 audible episodes a lap to 0.6, with a 99th percentile of exactly
    zero - shipped to a driver whose standing complaint is that braking feels
    numb. There is no peak to claim, but there is a measured threshold to be
    approaching, and that is a sentence the data supports."""
    model = V.VehicleModel()
    model.set_abs("Off")
    settle(model, throttle=0.5, rear_slip=1.02)
    approaching = 1.0 - (model._anchors.rasp_from
                         + (model._anchors.lock_floor
                            - model._anchors.rasp_from) * 0.6)
    state = None
    for _ in range(60):
        state = model.update(Frame(brake=1.0, front_slip=approaching,
                                   rear_slip=0.98))
    assert state.brake_state == V.BRAKE_LIMIT_S
    assert state.brake_level > 0.0, (
        "with ABS off, the approach to a lock is the only warning there is")


def test_a_borrowed_brake_scale_says_that_it_is_borrowed():
    """An assist nobody has measured gets a cue rather than a silence - a
    silent false negative on a CRITICAL cue is the wrong direction to be wrong
    in - but it must never claim the scale was measured on it."""
    model = V.VehicleModel()
    model.set_abs("Off")
    assert model._anchors.confidence == V.LOW, (
        "the ABS-off scale is v1.70 numbers from one car on one circuit")

    model.set_abs("something GT7 has never sent")
    assert model._anchors is V.ABS_ON, "an unknown assist still gets a cue"
    settle(model, throttle=0.5, rear_slip=1.02)
    state = model.update(Frame(brake=1.0, front_slip=0.80, rear_slip=0.95))
    assert state.brake_confidence == V.LOW
    assert state.brake_level > 0.0, "an unknown assist must not go silent"


def test_a_session_boundary_does_not_forget_which_assist_is_fitted():
    """`reset()` runs on a session boundary, a car change and a watchdog
    recovery. Clearing the assist there would drop a live race onto the
    borrowed scale mid-stint with nothing saying so."""
    model = V.VehicleModel()
    model.set_abs("Off")
    model.reset()
    assert model._abs == "Off"
    assert model._anchors.rasp_means == "approaching-lock"


def test_the_lock_scale_is_re_seeded_when_the_assist_changes():
    """The plateau's seed is a property of the scale. Leaving the previous
    assist's floor in the learner keeps the old regulation's threshold alive
    into the first minutes of the new one."""
    model = V.VehicleModel()
    model.set_abs("Weak")
    seeded_on = model._plateau.value
    model.set_abs("Off")
    assert model._plateau.value != seeded_on
    assert model._plateau.value == V.ABS_OFF.lock_floor / V.PLATEAU_MARGIN


# --------------------------------------------------- which axle is locking

def test_a_locking_rear_is_not_hidden_behind_a_locking_front():
    """**The regression this whole axle split is about.**

    `max(front_lock, rear_lock)` rendered one scalar with no axle in it.
    Measured over his own laps, 67% of the RSR's rear-lock episodes were
    hidden in EVERY frame behind a larger front value, and on the Shelby with
    ABS off the rear is the worse axle on 34.6% of braking frames.

    The front is the axle the wheel already reports - 18 Nm of it, straight
    into his hands. The rear is the one thing under braking that only the seat
    can say, and it was the one being thrown away.
    """
    model = V.VehicleModel()
    model.set_abs("Off")
    settle(model, throttle=0.5, rear_slip=1.02)
    state = None
    for _ in range(30):                    # front deeper than the rear, both locked
        state = model.update(Frame(brake=1.0, front_slip=0.70, rear_slip=0.78))
    assert state.brake_state == V.BRAKE_LOCKED_REAR, (
        "the deeper front swallowed the rear, which is what max() did")
    assert state.brake_axle == "rear"
    assert state.brake_level > 0.6, "a rear lock is still an alarm"


def test_the_rear_reads_slow_under_engine_braking_without_becoming_a_lock():
    """**The guard on the witness that was retired.** That one was a BIAS -
    the rear reading slower than the front by any margin - and 97-99% of its
    episodes turned out to be engine braking, because the driven axle reads a
    few percent slow the moment the throttle closes.

    This one is an absolute depth. The drag is held just UNDER the floor and
    the value is derived from the floor rather than typed in, so the test
    fails if anyone lowers it - a fixed 4% would have passed even at half the
    threshold, which pins nothing.

    Sited against the band that can actually reach the latch: pedal-off frames
    early-return and were never candidates, so the number that matters is the
    light-pedal band, where the worst of five datasets reaches p99.9 0.2013.
    The separation is real but it is narrower than the pedal-off figure of
    0.061 suggests, and the floor is deliberately kept low anyway to preserve
    the driver-confirmed rear lock on downshifts."""
    model = V.VehicleModel()
    model.set_abs("Off")
    settle(model, throttle=0.5, rear_slip=1.02)
    # Halfway to the floor, once the learned rear offset is allowed for -
    # the guard below keeps that honest rather than assuming it.
    just_under = 1.0 - V.ABS_OFF.lock_floor * 0.5
    state = None
    for _ in range(120):        # trailing the brake, rear dragging beneath it
        state = model.update(Frame(brake=0.30, front_slip=0.99,
                                   rear_slip=just_under, throttle=0.0))
    assert state.rear_lock < V.ABS_OFF.lock_floor, "the test drove past the floor"
    assert state.brake_state != V.BRAKE_LOCKED_REAR, (
        "engine braking is being reported as a rear lock again")


def test_a_rear_lock_on_a_downshift_still_reaches_the_driver():
    """Driver-confirmed: the Shelby's downshifts genuinely lock the rears, and
    the rear is deliberately not shift-blinded because of it. Measured at 344
    episodes with a median peak of 0.127, which is why the floor stays where
    it is rather than being tidied upward."""
    model = V.VehicleModel()
    model.set_abs("Off")
    settle(model, throttle=0.5, rear_slip=1.02, gear=4)
    for _ in range(10):         # on the brakes, still in fourth
        model.update(Frame(brake=1.0, front_slip=0.99, rear_slip=0.99, gear=4))
    state = None
    for _ in range(4):          # the downshift itself, and the rear steps down
        state = model.update(Frame(brake=1.0, front_slip=0.95,
                                   rear_slip=0.74, gear=3))
    assert state.brake_state == V.BRAKE_LOCKED_REAR, (
        "a blind here hides a real event exactly where his trail-braking is - "
        "and asserting thirty frames later would not notice one, because "
        "SHIFT_BLIND_S is shorter than that")


def test_the_front_plateau_is_never_taught_by_the_rear_axle():
    """The plateau models the ABS REGULATOR, which is a front-axle quantity.
    It was fed `max(front, rear)` - already the front on 97-98.8% of frames,
    and rear data on the rest."""
    model = V.VehicleModel()
    model.set_abs("Weak")
    settle(model, throttle=0.5, rear_slip=1.02)
    for _ in range(60):
        state = model.update(Frame(brake=1.0, front_slip=0.95, rear_slip=0.95))
    before = state.lock_threshold
    for _ in range(300):        # rear deep, front barely working
        state = model.update(Frame(brake=1.0, front_slip=0.99, rear_slip=0.72))
    assert state.lock_threshold <= before + 1e-9, (
        "the rear axle moved a threshold that describes the front regulator")


# --- banked track ----------------------------------------------------------

def _settled(model, *, plane=1.0, frames=900, yaw=0.30):
    """Run until the heading witness trusts itself, on the given road plane."""
    heading = 0.0
    state = None
    for _ in range(frames):
        heading += V.HEADING_SIGN * yaw * V.FRAME_S
        state = model.update(Frame(speed=55.0, yaw=yaw, heading=heading,
                                   road_plane_y=plane))
    return state


def test_the_rotation_witness_refuses_on_a_banked_track():
    """**The Daytona rumble, and the driver found it.** The witness integrates
    `angvel_y - path_yaw`, and those are in different frames: one is the
    world-VERTICAL component of the car's rotation, the other the curvature of
    its path in the world-HORIZONTAL plane. Level, they agree and the
    difference is sideslip. Tilt the car and they disagree by construction -
    and the difference is INTEGRATED, so it accumulates rather than averaging
    out.

    Measured on Daytona: mean `beta_rate` 0.319 rad/s on the banking against
    0.089 on the flat, sustained, with the anchor unable to leak it because
    `straight` needs `abs(yaw) < ANCHOR_YAW` and a banked turn never gives it.
    Through the real derivers the traction cue - the max of this witness and
    the wheel-speed one - sat at FULL SCALE for 88% of the banking.

    His words are what identified it, after five other channels had been
    measured and cleared: "as soon as the car levels out and I'm still on full
    throttle the rumble stops."
    """
    model = V.VehicleModel()
    state = _settled(model, plane=0.857)          # Daytona, 31 degrees
    assert state.rotation == V.UNKNOWN
    assert state.rotation_level == 0.0
    assert state.rotation_confidence == V.NONE


def test_ordinary_camber_is_not_banking():
    """Road camber reaches 10.5 degrees at Spa and 10.1 at Road Atlanta, and
    0.0% of frames at any road circuit on file fall below the threshold. A cue
    that went quiet on camber would be silent through most of a lap."""
    model = V.VehicleModel()
    state = _settled(model, plane=0.983)          # Spa's worst, 10.5 degrees
    assert state.rotation != V.UNKNOWN
    assert state.rotation_confidence == V.HIGH


def test_leaving_the_banking_does_not_fire_a_phantom():
    """Suppressing only the OUTPUT would leave the bias accumulating unseen,
    and the cue would fire at full scale on the exit - the moment the car
    levels out and the witness starts believing itself again, which is the
    worst possible moment for a phantom."""
    model = V.VehicleModel()
    _settled(model, plane=1.0)                    # trusted, on the level
    _settled(model, plane=0.857, frames=600)      # a long banked turn
    heading = 0.0
    for _ in range(30):                           # and back onto the flat
        heading += V.HEADING_SIGN * 0.30 * V.FRAME_S
        state = model.update(Frame(speed=55.0, yaw=0.30, heading=heading))
    assert state.rotation_level < 0.25


def test_a_packet_without_a_road_plane_is_treated_as_level():
    """Formats `A` and `B` carry no road plane. Absent is not banked - the
    cue behaves exactly as it did before this existed."""
    model = V.VehicleModel()
    state = _settled(model, plane=None)
    assert state.rotation_confidence == V.HIGH
