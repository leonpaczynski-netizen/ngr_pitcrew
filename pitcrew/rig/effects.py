"""Turning what the car is doing into seven numbers between nought and one.

The layer above this one - `vehicle.py` - decides what the car is doing. This
one decides what the driver is told about it, and the two are deliberately
separate, because they fail in different ways and are argued about with
different evidence. A wrong threshold in `vehicle` is a wrong claim about the
car. A wrong number here is a cue that is too loud, in the wrong place, or
masking something better.

Two limits bound the whole exercise and neither can be engineered away.

**60 Hz means a 30 Hz Nyquist**, and the band the transducer works in is
25-160 Hz. They barely overlap. So road texture cannot be reproduced from
telemetry - only *modulated*. What the driver feels as surface is generated
locally; what the telemetry does is say how rough it should be. Anything
claiming to render real road detail from this feed would be false.

**There is one piston.** Everything sums into one signal, so an effect is only
legible if the others get out of its way. That is `synth`'s business, but it
is the reason this module returns seven numbers and not twenty: a cue that
cannot be told apart from another cue is not a cue, it is loading.

What each of the seven is for, in the order the mixer takes them:

    engine         immersion. Revs, on his own hand-drawn curve.
    road           immersion and surface. How rough it is under the tyres.
    brake_limit    CRITICAL. The regulator working, and a genuine lock.
    driveline      a tick on a shift, and on the limiter.
    impact         a kerb strike, a landing, a compression, a hit.
    chassis_load   how hard the car is leaning on its tyres, in g.
    rear_traction  CRITICAL. The rear working, sliding, or gone.

and one modifier, which renders nothing:

    unload         how light the car is. The background ducks under it.

**The two effects that used to be here and are not any more.** `wheels_spin_lock`
combined wheelspin and lock-up on one channel because that is how he had it in
SimHub, on the reasoning that "a wheel doing something other than rolling is
one message, and which end it is at is not something a single piston can say
anyway". Measured, that turned out to be wrong twice over: the two events
occupy different parts of the lap - braking and exit almost never overlap, at
1.5% of frames - and the piston can say which, because it has two usable
regions of response and they are an octave apart. Splitting them costs nothing
and buys the difference between "something is wrong at the front" and
"something is wrong at the back", which are opposite corrections.
"""
from __future__ import annotations

import numpy as np

from pitcrew.rig import vehicle
from pitcrew.telemetry.packet import GT7Packet

# ---------------------------------------------------------------- thresholds
#
# Each of these is a claim about what should be felt rather than about what is
# happening - the claims about the car live in `vehicle.py`. They are the
# numbers to argue with when something feels wrong rather than reads wrong.

# Road texture, from how fast the suspension is moving rather than where it
# is. Height alone is ride height plus load transfer; its rate of change is
# the surface. Metres per second, per wheel, averaged.
#
# **Both numbers are measured**, over 278,034 frames of his own laps, and the
# distributions are split by what is under the wheel because that turned out
# to matter:
#
#     on tarmac   p10 0.0061  p50 0.0142  p90 0.0401  p99 0.1284
#     on a kerb   p10 0.0178  p50 0.0824  p90 0.3181  p99 0.6518
#
# The first version of this had full scale at 0.35 m/s - above the 99th
# percentile of everything - so real tarmac texture never registered and the
# channel only spoke when a kerb shoved it over in one step. Reported from the
# seat as "road rumble, not sure what this is showing": it was showing kerbs,
# in binary.
#
# The fix for that put full scale at 0.060, which cured the tarmac end and
# created the opposite fault at the other: a kerb reads 0.0824 at its MEDIAN,
# so half of all time on a kerb was pinned at full scale and the difference
# between brushing one and climbing one was thrown away. 0.090 keeps the
# tarmac range - median 0.07, p90 0.40 - and leaves a kerb climbing from 0.8
# rather than arriving already clipped.
TEXTURE_ONSET_MS = 0.008
TEXTURE_FULL_MS = 0.090
# His SimHub rumble had `MaxEffectSpeed 130`, so the effect reaches full
# authority at 130 km/h and is scaled below it: the same bump at 40 km/h is
# not the same event.
TEXTURE_FULL_SPEED_KPH = 130.0
# Anything that is not tarmac is a surface event in its own right. GT7 sends a
# character per wheel - the one input in this whole file that is genuinely
# measured rather than modelled, and the one SimHub's GT7 support cannot see
# at all, because it reads the base packet format only.
#
# Both boosts are much smaller than they were. A kerb now gets its own strike
# on the impact channel and its own reading on the texture curve above; adding
# 0.70 on top of that was not making kerbs strong, it was pinning the channel
# and throwing away the difference between clipping one and climbing one.
KERB_BOOST = 0.15
OFF_SURFACE_BOOST = 0.25

# **A kerb also gets a thump, separate from the rattle.**
#
# A real ripple strip is a thud with a rattle on top. The rattle rides on the
# road bed; this is the thud - a short pulse into `impact`, fired on the EDGE
# of touching the kerb rather than for as long as the wheel is on it, because
# the edge is what reads as sharp. Sitting on a kerb through a chicane stays a
# texture.
KERB_THUMP = 0.85
KERB_THUMP_DECAY_S = 0.12

# **Lateral acceleration, in g.** Speed times yaw rate over 9.81 - the standard
# derivation, and the same one `recorder.py` computes for the export, so the
# two agree by construction.
#
# This replaced a neutral-steer yaw-error model, and the reason is worth
# keeping. That model compared the yaw the car was doing against the yaw
# `speed * steering / wheelbase` predicted, which is only valid while the tyres
# are in their linear range. Measured over a real lap it correlated **0.991
# with steering angle times speed** - it was a steering meter - and
# over-predicted the real yaw rate by 3.67x. It sat at FULL SCALE for 34-53% of
# every lap.
#
# The driver found it valuable anyway, because cornering load is worth feeling,
# and said he wanted to use it to judge how much speed he could carry before
# the tyres let go. That is exactly what a saturating signal cannot do: it
# reads maximum in a corner taken well within the limit and feels identical to
# one on the edge.
#
# Lateral g does the job it was being trusted with. It has resolution all the
# way to the limit and it means something absolute - 1.2 g is 1.2 g in every
# corner and every car - so what he learns in one place transfers.
#
# The range is a claim about the car, not about the signal. Measured over 40
# laps: median 0.22 g, p75 1.16, p90 1.50, p99 1.80. The ceiling at 2.20 sits
# above the 99th so the top of the scale still has resolution at the limit.
LAT_G_ONSET = 0.20
LAT_G_FULL = 2.20

# An impact is a step in world velocity that no engine could produce. Metres
# per second per frame - at 60 Hz, 1.5 m/s in one frame is 90 m/s^2.
IMPACT_ONSET_MS = 0.8
IMPACT_FULL_MS = 3.0

# How quickly a one-shot decays. The gear thump in his profile was an 80 ms
# pulse; impacts ring a little longer.
GEAR_DECAY_S = 0.09
IMPACT_DECAY_S = 0.18
# The rev limiter is a MEASURED flag - GT7's flags bit 5 - and it was not being
# used at all. Measured over 40 laps it is active on 0.08% of frames in 52
# episodes averaging 42 ms, which is exactly the profile of something worth a
# tick and not worth a state: rare, short, and unambiguous. It rides the
# driveline channel because that is where a shift already lives, and hitting
# the limiter is the same message as needing to shift.
LIMITER_PULSE = 0.55
LIMITER_DECAY_S = 0.07

# His gear effect modulated its gain by rpm between these two, so a shift at
# the limiter is felt harder than one at half revs.
GEAR_RPM_MIN = 0.50
GEAR_RPM_MAX = 0.90

# The RPM curve he drew by hand in SimHub, as (rpm %, output %). Stored there
# out of ascending order - the last point sorts fourth - and SimHub sorts on
# load, so reading the file top to bottom gives the wrong shape. Sorted here.
# Note it tops out at 63%, not 100: RPM is by far his quietest channel.
RPM_CURVE = ((5.21, 0.0), (20.71, 2.99), (42.84, 14.13),
             (63.08, 36.91), (77.40, 48.56), (100.0, 63.06))

FRAME_S = 1.0 / 60.0


def _ramp(value: float, onset: float, full: float) -> float:
    """0 below `onset`, 1 at `full`, straight line between."""
    if value <= onset:
        return 0.0
    return min(1.0, (value - onset) / (full - onset))


class EffectDeriver:
    """Seven intensities and one modifier per packet, and the state between.

    Called on the telemetry thread, once per frame, so it holds no lock and
    allocates one small array. Order matches `synth.PROFILE`; the modifier is
    appended after the effects, which is why the array is one longer than the
    number of voices.
    """

    NAMES = ("engine", "road", "brake_limit", "driveline", "impact",
             "chassis_load", "rear_traction")
    # Not effects. They render nothing and change what the effects do - see
    # `synth.HapticMix.render`.
    MODIFIERS = ("unload",)

    def __init__(self, model: vehicle.VehicleModel | None = None) -> None:
        self.model = model or vehicle.VehicleModel()
        self._out = np.zeros(len(self.NAMES) + len(self.MODIFIERS),
                             dtype=np.float32)
        self._prev_suspension: tuple[float, ...] | None = None
        self._prev_gear: int | None = None
        self._prev_velocity: tuple[float, float, float] | None = None
        self._gear_pulse = 0.0
        self._impact_pulse = 0.0
        self._kerb_pulse = 0.0
        self._limiter_pulse = 0.0
        self._prev_limiter = False
        self.state = vehicle.VehicleState()

    def reset(self) -> None:
        """Between sessions. Stale state across a garage visit is a phantom
        impact the moment the car reappears somewhere else on the map."""
        self.model.reset()
        self._prev_suspension = None
        self._prev_gear = None
        self._prev_velocity = None
        self._gear_pulse = 0.0
        self._impact_pulse = 0.0
        self._kerb_pulse = 0.0
        self._limiter_pulse = 0.0
        self._prev_limiter = False
        self.state = vehicle.VehicleState()

    def update(self, packet: GT7Packet, dt: float = FRAME_S) -> np.ndarray:
        """The seven intensities and the modifier for this frame."""
        out = self._out
        out[:] = 0.0

        # Nothing at all off track. A car in the garage or mid-load produces
        # position jumps and suspension steps that are not events, and the
        # driver is not in the seat to feel them anyway.
        if not packet.car_on_track or packet.paused:
            self.reset()
            return out

        state = self.model.update(packet, dt)
        self.state = state

        out[0] = self._engine(packet)
        out[1] = self._road(packet, state, dt)
        out[2] = state.brake_level
        out[3] = max(self._driveline(packet, state, dt),
                     self._limiter(state, dt))
        out[4] = max(self._impact(packet, dt), self._kerb_thump(state, dt),
                     state.landed, state.compression)
        out[5] = self._chassis_load(state)
        out[6] = state.traction_level
        out[7] = state.unload
        return out

    # ------------------------------------------------------------- immersion

    def _road(self, p: GT7Packet, s: vehicle.VehicleState, dt: float) -> float:
        """Road texture, and the honest account of what this is.

        Suspension **velocity**, not height: height is ride height plus load
        transfer, and its rate of change is the part that is surface. Even
        then, at 60 Hz this is an envelope and nothing more - it says how
        rough, while the roughness itself is generated in `synth`. Calling it
        road texture is a description of what it is for, not a claim about
        where the waveform came from.
        """
        heights = (p.suspension_fl, p.suspension_fr,
                   p.suspension_rl, p.suspension_rr)
        previous, self._prev_suspension = self._prev_suspension, heights
        if previous is None or dt <= 0:
            return 0.0
        speed = sum(abs(h - q) for h, q in zip(heights, previous)) / (4.0 * dt)
        texture = _ramp(speed, TEXTURE_ONSET_MS, TEXTURE_FULL_MS)

        # **The speed scaling belongs to the texture, not to the surface.**
        #
        # A bump at 40 km/h genuinely is not the bump it is at 130 - the
        # suspension is moving less. But a kerb is a kerb: the wheel is on a
        # different surface, and scaling that down because the corner happens
        # to be slow is what made ripple strips feel soft in the hairpins,
        # which is where kerbs matter most.
        texture *= min(1.0, p.speed_kmh / TEXTURE_FULL_SPEED_KPH)
        if s.on_kerb:
            texture = min(1.0, texture + KERB_BOOST)
        elif s.off_surface:
            texture = min(1.0, texture + OFF_SURFACE_BOOST)
        return texture

    def _engine(self, p: GT7Packet) -> float:
        """His hand-drawn curve, sorted, and normalised to its own top."""
        fraction = self._rpm_fraction(p) * 100.0
        xs = [x for x, _ in RPM_CURVE]
        ys = [y for _, y in RPM_CURVE]
        return float(np.interp(fraction, xs, ys)) / 100.0

    # --------------------------------------------------------------- chassis

    def _chassis_load(self, s: vehicle.VehicleState) -> float:
        """How hard the car is leaning on its tyres, in g.

        **This is load, not grip, and the distinction is the point.** It says
        how hard the tyres are working, which is what a driver judging corner
        entry speed wants; it does not say how much is left. Nothing in GT7's
        feed says how much is left - there is no slip-angle channel and no grip
        channel - so a cue claiming to would be inventing one.
        """
        if s.speed_ms < vehicle.MIN_SPEED_MS:
            return 0.0
        return _ramp(s.lateral_g, LAT_G_ONSET, LAT_G_FULL)

    def _impact(self, p: GT7Packet, dt: float) -> float:
        """A step in world velocity no engine or brake could have produced.

        Deliberately blunt, and gated hard - his SimHub impact effect ran a
        threshold of 55 where the others were 8 to 28, which is him saying this
        should fire rarely. A track reload or a garage exit produces a colossal
        false step, which is why `update` resets the state whenever the car is
        not on track.
        """
        velocity = (p.vel_x, p.vel_y, p.vel_z)
        previous, self._prev_velocity = self._prev_velocity, velocity
        self._impact_pulse *= float(np.exp(-dt / IMPACT_DECAY_S))
        if previous is not None:
            step = float(np.sqrt(sum((a - b) ** 2
                                     for a, b in zip(velocity, previous))))
            hit = _ramp(step, IMPACT_ONSET_MS, IMPACT_FULL_MS)
            self._impact_pulse = max(self._impact_pulse, hit)
        return self._impact_pulse

    def _kerb_thump(self, s: vehicle.VehicleState, dt: float) -> float:
        """The low half of a ripple strip, fired on the edge of touching it.

        Deliberately an onset rather than a state. A wheel sitting on a kerb
        through a whole chicane is a texture, which the road bed already
        carries; what makes a kerb feel sharp is the moment of arriving on it.
        The tarmac-only guard lives in `vehicle._surfaces`.
        """
        self._kerb_pulse *= float(np.exp(-dt / KERB_THUMP_DECAY_S))
        if s.kerb_strike:
            self._kerb_pulse = max(self._kerb_pulse, KERB_THUMP)
        return self._kerb_pulse

    # ---------------------------------------------------------------- engine

    def _driveline(self, p: GT7Packet, s: vehicle.VehicleState,
                   dt: float) -> float:
        """A thump on the shift itself, not a state that lingers.

        Scaled by rpm between 50% and 90%, as his profile did, so a shift at
        the limiter is felt harder than one at half revs. Neutral and reverse
        are ignored: rolling into the pit box backwards is not a gearshift he
        wants reported.
        """
        gear = p.current_gear
        previous, self._prev_gear = self._prev_gear, gear
        self._gear_pulse *= float(np.exp(-dt / GEAR_DECAY_S))
        if (previous is not None and gear != previous
                and gear > 0 and previous > 0):
            fraction = self._rpm_fraction(p)
            scale = _ramp(fraction, GEAR_RPM_MIN, GEAR_RPM_MAX)
            self._gear_pulse = max(self._gear_pulse, 0.35 + 0.65 * scale)
        return self._gear_pulse

    def _limiter(self, s: vehicle.VehicleState, dt: float) -> float:
        """A tick when the limiter comes in, on its EDGE.

        The flag is measured and was going unused. Fired on the edge rather
        than held, because sitting on the limiter down a straight is a state
        the engine bed already reports at full revs - what is worth a separate
        tick is the moment it arrives, which is the moment a shift is late.
        """
        previous, self._prev_limiter = self._prev_limiter, s.limiter
        self._limiter_pulse *= float(np.exp(-dt / LIMITER_DECAY_S))
        if s.limiter and not previous:
            self._limiter_pulse = max(self._limiter_pulse, LIMITER_PULSE)
        return self._limiter_pulse

    @staticmethod
    def _rpm_fraction(p: GT7Packet) -> float:
        """Revs as a fraction of this car's own usable range.

        `rpm_alert_min` is the car's shift light and `rpm_alert_max` its
        limiter, both broadcast per car - so this needs no configuration and is
        correct on a Gr.4 and a Gr.1 without being told anything.
        """
        top = float(p.rpm_alert_max or 0.0)
        if top <= 0.0:
            return 0.0
        return float(np.clip(p.engine_rpm / top, 0.0, 1.0))

    # --------------------------------------------------------- observability

    def explain(self) -> dict:
        """What the last frame decided, and why.

        Half of the answer to "what exactly caused that vibration" - this half
        is the car, and `synth.HapticMix.explain` is the other half, the mix.
        Together they cover raw channel to final amplitude.
        """
        s = self.state
        return {
            "traction": {
                "state": s.traction, "level": round(s.traction_level, 3),
                "confidence": s.traction_confidence,
                "slip_excess": round(s.slip_excess, 4),
                "reference": (None if s.slip_reference is None
                              else round(s.slip_reference, 4)),
                "witness": s.reasons.get("traction"),
            },
            "brake": {
                "state": s.brake_state, "level": round(s.brake_level, 3),
                "axle": s.brake_axle,
                "front_lock": round(s.front_lock, 4),
                "rear_lock": round(s.rear_lock, 4),
                "lock_threshold": round(s.lock_threshold, 4),
                "rear_unstable": round(s.rear_unstable, 3),
                "note": s.reasons.get("brake"),
            },
            "rotation": {
                "state": s.rotation, "level": round(s.rotation_level, 3),
                "confidence": s.rotation_confidence,
                "beta_deg": round(s.beta_deg, 2),
                "beta_rate": round(s.beta_rate, 3),
                "heading_correlation": round(s.heading_correlation, 3),
            },
            "load": {
                "front": round(s.load_front, 2), "rear": round(s.load_rear, 2),
                "unload": round(s.unload, 3),
                "compression": round(s.compression, 3),
                "landed": round(s.landed, 3),
            },
            "surface": {
                "kerb": s.on_kerb, "off": s.off_surface,
                "strike": round(s.kerb_strike, 2),
            },
            "inputs": {
                "speed_ms": round(s.speed_ms, 1),
                "throttle": round(s.throttle, 3),
                "brake": round(s.brake, 3),
                "lateral_g": round(s.lateral_g, 2),
                "long_g": round(s.long_g, 2),
                "limiter": s.limiter,
            },
        }
