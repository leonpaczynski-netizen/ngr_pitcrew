"""Turning GT7's channels into six numbers between nought and one.

This is the layer where honesty costs something, so it is worth being plain
about what it is: **everything here is derived.** GT7 broadcasts no slip
channel, no ABS flag, no road-texture channel and no impact channel. Every
intensity below is a model with a threshold, and CLAUDE.md 4 rule 5 says such
things go under a `derived` heading with the threshold stated rather than
being presented as measurements. The constants in this module are those
thresholds, and each one says what it is for.

Two limits bound the whole exercise and neither can be engineered away:

**60 Hz means a 30 Hz Nyquist**, and the band the transducer works in is
25-160 Hz. They barely overlap. So road texture cannot be reproduced from
telemetry - only *modulated*. What the driver feels as surface is generated
locally; what the telemetry does is say how rough it should be. Anything
claiming to render real road detail from this feed would be false.

**Some effects have no input at all.** GT7 sends no ABS-active flag, so an ABS
effect can only be inferred from a periodic modulation of slip under braking.
The driver had that effect disabled in SimHub, and it stays disabled here
rather than being invented.

The six are his: the ones he had enabled after eight days of tuning. The
twenty he left off are left off.
"""
from __future__ import annotations

import numpy as np

from pitcrew.telemetry.packet import GT7Packet
from pitcrew.telemetry.recorder import _slip_ratios

# ---------------------------------------------------------------- thresholds
#
# Each of these is the point at which an effect starts to be felt, and each is
# a claim about the car rather than about the signal. They are the numbers to
# argue with when something feels wrong.

# Slip ratio is surface speed over road speed: 1.0 is rolling true, above is
# spinning, below is locking. Onset is set close to true rolling because the
# transducer is telling him something is happening, not diagnosing it - the
# analysis layer has its own, stricter trips.
SPIN_ONSET = 0.04          # 4% faster than the road
SPIN_FULL = 0.25           # 25% and it is a full-scale event
LOCK_ONSET = 0.10
LOCK_FULL = 0.40
# **How long a wheel must stay slow before it counts as locked.**
#
# Reported from the seat as "ABS is way too strong" - which is worth reading
# carefully, because there IS no ABS effect. GT7 broadcasts no ABS flag and
# none was built. What he was feeling is the lock half of `wheels_spin_lock`
# firing on the ABS itself: the system pulses the brakes at something like
# 10-15 Hz, every pulse drops the wheel speed below the road speed, and a
# detector with no memory sees a lock-up on each one. On a driver whose whole
# technique is trail-braking deep that is most of every corner.
#
# The distinction that matters is duration, not depth. An ABS cycle is tens of
# milliseconds; a genuine lock persists. So the lock signal is given an attack
# slow enough that a pulse cannot climb it and a real lock can, and a quick
# release so the effect still stops when the wheel does.
LOCK_ATTACK_S = 0.22
LOCK_RELEASE_S = 0.08
# Below this the ratio is arithmetic on a divisor that means nothing.
SLIP_MIN_SPEED_MS = 3.0

# **A pedal fraction, 0-1, not a percentage.** `GT7Packet.throttle` and
# `.brake` divide the raw byte by 255 and hand back 0.0-1.0; it is the
# recorder that converts to the 0-100 CLAUDE.md 3.4 asks to be stored. The
# first version of this module gated on `< 2.0` in the belief they were
# percentages, which is true of every reading either channel can produce - so
# wheelspin was permanently halved and lock-up could never fire at all.
#
# Worth recording because it is the second time this exact shape of mistake
# has been made against these channels: `recorder._slip_ratios` carries the
# account of a factor of 2pi that meant a driver whose whole technique is
# trail-braking deep had never once been shown a lockup.
PEDAL_ON = 0.02

# Road texture, from how fast the suspension is moving rather than where it
# is. Height alone is ride height plus load transfer; its rate of change is
# the surface. Metres per second, per wheel, averaged.
TEXTURE_FULL_MS = 0.35
# His SimHub rumble had `MaxEffectSpeed 130`, so the effect reaches full
# authority at 130 km/h and is scaled below it: the same bump at 40 km/h is
# not the same event.
TEXTURE_FULL_SPEED_KPH = 130.0

# Anything that is not tarmac is a surface event in its own right. GT7 sends
# a character per wheel - the one channel here that is genuinely measured
# rather than modelled, and the one SimHub's GT7 support cannot see at all,
# because it reads the base packet format only.
KERB_BOOST = 0.70
OFF_SURFACE_BOOST = 0.30

# **A kerb also gets a thump, separate from the rattle.**
#
# A real ripple strip is a thud with a rattle on top. The rattle rides on the
# rumble effect; this is the thud - a short pulse into `wheels_impact`, fired
# on the EDGE of touching the kerb rather than for as long as the wheel is on
# it, because the edge is what reads as sharp. Sitting on a kerb through a
# chicane stays a texture.
#
# It was first placed at 28-38 Hz on the reasoning that lower is more felt.
# The measured response says otherwise - see `transducer.FELT_RESPONSE` - so
# `wheels_impact` now sits at 40-52 Hz, the strongest region this rig has, and
# the thump is felt as a thump rather than as a distant thud.
KERB_THUMP = 0.85
KERB_THUMP_DECAY_S = 0.12

# **Lateral acceleration, in g.** Speed times yaw rate over 9.81 - the
# standard derivation, and the same one `recorder.py` already computes for the
# export, so the two agree by construction.
#
# This replaced a neutral-steer yaw-error model, and the reason is worth
# keeping. That model compared the yaw the car was doing against the yaw
# `speed * steering / wheelbase` predicted, which is only valid while the
# tyres are in their linear range. Measured over a real lap: it correlated
# **0.991 with steering angle times speed** - it was a steering meter - and
# over-predicted the real yaw rate by 3.67x, reaching 2.87 rad/s on a car
# whose yaw never exceeded 0.70. It therefore sat at FULL SCALE for 34-53% of
# every lap.
#
# The driver found it valuable anyway, because cornering load is worth
# feeling, and said he wanted to use it to judge how much speed he could carry
# before the tyres let go. That is exactly what a saturating signal cannot do:
# it reads maximum in a corner taken well within the limit and feels identical
# to one on the edge.
#
# Lateral g does the job it was being trusted with. It has resolution all the
# way to the limit, and it means something absolute - 1.2 g is 1.2 g in every
# corner and every car, so what he learns in one place transfers.
#
# Two further gains, both accidental and both real: it takes `abs()`, so it
# does not depend on the sign of `angvel_y` - which `recorder.py:333-336`
# records as still unverified - and it needs no steering angle, so unlike the
# model it replaces it keeps working on packet formats A and B.
#
# The range is a claim about the car, not about the signal. A GT3 on slicks
# holds somewhere near 2 g sustained; a measured lap ran a median of 1.05 g
# and a 90th percentile of 2.04 g. The ceiling sits above that so the top of
# the scale still has resolution where it matters - at the limit.
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
    """Six intensities per packet, and the state that needs remembering.

    Called on the telemetry thread, once per frame, so it holds no lock and
    allocates one small array. Order matches `synth.PORSCHE_RSR_17`.
    """

    NAMES = ("wheels_spin_lock", "gear", "wheels_rumble", "lateral_load",
             "wheels_impact", "rpm")

    def __init__(self) -> None:
        self._out = np.zeros(len(self.NAMES), dtype=np.float32)
        self._prev_suspension: tuple[float, ...] | None = None
        self._prev_gear: int | None = None
        self._prev_velocity: tuple[float, float, float] | None = None
        self._gear_pulse = 0.0
        self._impact_pulse = 0.0
        self._lock_level = 0.0
        self._prev_surfaces: tuple[str, ...] | None = None
        self._kerb_pulse = 0.0

    def reset(self) -> None:
        """Between sessions. Stale state across a garage visit is a phantom
        impact the moment the car reappears somewhere else on the map."""
        self._prev_suspension = None
        self._prev_gear = None
        self._prev_velocity = None
        self._gear_pulse = 0.0
        self._impact_pulse = 0.0
        self._lock_level = 0.0
        self._prev_surfaces = None
        self._kerb_pulse = 0.0

    def update(self, packet: GT7Packet, dt: float = FRAME_S) -> np.ndarray:
        """The six intensities for this frame."""
        out = self._out
        out[:] = 0.0

        # Nothing at all off track. A car in the garage or mid-load produces
        # position jumps and suspension steps that are not events, and the
        # driver is not in the seat to feel them anyway.
        if not packet.car_on_track or packet.paused:
            self.reset()
            return out

        out[0] = self._spin_lock(packet, dt)
        out[1] = self._gear(packet, dt)
        out[2] = self._rumble(packet, dt)
        out[3] = self._lateral_load(packet)
        out[4] = max(self._impact(packet, dt), self._kerb_thump(packet, dt))
        out[5] = self._rpm(packet)
        return out

    # ---------------------------------------------------------------- wheels

    def _spin_lock(self, p: GT7Packet, dt: float) -> float:
        """Wheelspin and lock-up, from surface speed against road speed.

        One effect for both because that is how he had it: a wheel doing
        something other than rolling is one message, and which end it is at is
        not something a single piston can say anyway.
        """
        if p.speed_ms < SLIP_MIN_SPEED_MS:
            return 0.0
        ratios = [r for r in _slip_ratios(p) if r is not None]
        if not ratios:
            return 0.0
        spin = _ramp(max(ratios) - 1.0, SPIN_ONSET, SPIN_FULL)
        lock = _ramp(1.0 - min(ratios), LOCK_ONSET, LOCK_FULL)
        # Gated on what the driver is asking for. A wheel reading slow in the
        # air over a kerb is not a lock-up, and the brake pedal is what
        # separates the two.
        if p.brake < PEDAL_ON:
            lock = 0.0
        if p.throttle < PEDAL_ON:
            spin *= 0.5

        # Lock has to hold before it is believed - see `LOCK_ATTACK_S`. ABS
        # pulses the brakes faster than this can climb, so the effect stops
        # reporting the assist and starts reporting the wheel.
        tau = LOCK_ATTACK_S if lock > self._lock_level else LOCK_RELEASE_S
        self._lock_level += (lock - self._lock_level) * min(1.0, dt / tau)
        return max(spin, self._lock_level)

    def _rumble(self, p: GT7Packet, dt: float) -> float:
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
        texture = _ramp(speed, 0.0, TEXTURE_FULL_MS)

        # **The speed scaling belongs to the texture, not to the surface.**
        #
        # His SimHub rumble had `MaxEffectSpeed 130`, and a bump at 40 km/h
        # genuinely is not the bump it is at 130 - the suspension is moving
        # less. But a kerb is a kerb: the wheel is on a different surface, and
        # scaling that down because the corner happens to be slow is what made
        # ripple strips feel soft. Reported from the seat as "not sharp enough
        # or strong enough", and the hairpins are exactly where kerbs matter
        # most.
        texture *= min(1.0, p.speed_kmh / TEXTURE_FULL_SPEED_KPH)

        # Surface type is the one input here that is measured rather than
        # modelled. SimHub's GT7 support cannot see it - it reads the base
        # packet only - which is why its kerb effects have to be inferred from
        # suspension and ours do not. Added after the speed scaling so it
        # arrives at full strength wherever it happens.
        surfaces = p.surface_types
        if surfaces:
            if any(s == "C" for s in surfaces):
                texture = min(1.0, texture + KERB_BOOST)
            elif any(s in ("D", "G", "S", "s") for s in surfaces):
                texture = min(1.0, texture + OFF_SURFACE_BOOST)
        return texture

    # --------------------------------------------------------------- chassis

    def _lateral_load(self, p: GT7Packet) -> float:
        """How hard the car is leaning on its tyres, in g.

        `speed * yaw_rate / 9.81` - the standard derivation, and the one
        `recorder._slip_ratios`' neighbour already uses for the export, so the
        haptic and the recorded figure cannot disagree.

        **This is load, not grip, and the distinction is the point.** It says
        how hard the tyres are working, which is what a driver judging corner
        entry speed wants; it does not say how much is left. Nothing in GT7's
        feed says how much is left - there is no slip-angle channel and no
        grip channel - so a cue claiming to would be inventing one.

        What makes it usable where the model it replaced was not: it does not
        saturate. A corner taken at 1.2 g feels different from the same corner
        at 1.9 g, and the difference is the information.
        """
        if p.speed_ms < SLIP_MIN_SPEED_MS:
            return 0.0
        lateral_g = abs(p.speed_ms * p.angvel_y) / 9.81
        return _ramp(lateral_g, LAT_G_ONSET, LAT_G_FULL)

    def _impact(self, p: GT7Packet, dt: float) -> float:
        """A step in world velocity no engine or brake could have produced.

        Deliberately blunt, and gated hard - his SimHub impact effect ran a
        threshold of 55 where the others were 8 to 28, which is him saying
        this should fire rarely. A track reload or a garage exit produces a
        colossal false step, which is why `update` resets the state whenever
        the car is not on track.
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

    def _kerb_thump(self, p: GT7Packet, dt: float) -> float:
        """The low half of a ripple strip, fired on the edge of touching it.

        Deliberately an onset rather than a state. A wheel sitting on a kerb
        through a whole chicane is a texture, which the rumble effect already
        carries; what makes a kerb feel sharp is the moment of arriving on it.
        """
        surfaces = p.surface_types
        previous, self._prev_surfaces = self._prev_surfaces, surfaces
        self._kerb_pulse *= float(np.exp(-dt / KERB_THUMP_DECAY_S))
        if not surfaces or not previous:
            return self._kerb_pulse
        # **From tarmac only.** `car_on_track` is GT7's flags bit 0, which
        # means "in a session" rather than "on the racing surface", so a run
        # wide and a scrabble back over the kerb used to fire a full-strength
        # apex hit. A kerb arrived at from grass or dirt is the driver
        # recovering, and it is the rumble bed's business.
        arrived = any(now == "C" and was == "T"
                      for now, was in zip(surfaces, previous))
        if arrived:
            self._kerb_pulse = max(self._kerb_pulse, KERB_THUMP)
        return self._kerb_pulse

    # ---------------------------------------------------------------- engine

    def _gear(self, p: GT7Packet, dt: float) -> float:
        """A thump on the shift itself, not a state that lingers.

        Scaled by rpm between 50% and 90%, as his profile did, so a shift at
        the limiter is felt harder than one at half revs. Neutral and reverse
        are ignored: rolling into the pit box backwards is not a gearshift he
        wants reported.
        """
        gear = p.current_gear
        previous, self._prev_gear = self._prev_gear, gear
        self._gear_pulse *= float(np.exp(-dt / GEAR_DECAY_S))
        if previous is not None and gear != previous and gear > 0 and previous > 0:
            fraction = self._rpm_fraction(p)
            scale = _ramp(fraction, GEAR_RPM_MIN, GEAR_RPM_MAX)
            self._gear_pulse = max(self._gear_pulse, 0.35 + 0.65 * scale)
        return self._gear_pulse

    def _rpm(self, p: GT7Packet) -> float:
        """His hand-drawn curve, sorted, and normalised to its own top.

        The curve peaks at 63%, not 100 - together with a gain of 9.5 this is
        by far his quietest channel, which is a deliberate choice about a
        continuous bed sitting under everything else rather than an oversight.
        """
        fraction = self._rpm_fraction(p) * 100.0
        xs = [x for x, _ in RPM_CURVE]
        ys = [y for _, y in RPM_CURVE]
        return float(np.interp(fraction, xs, ys)) / 100.0

    @staticmethod
    def _rpm_fraction(p: GT7Packet) -> float:
        """Revs as a fraction of this car's own usable range.

        `rpm_alert_min` is the car's shift light and `rpm_alert_max` its
        limiter, both broadcast per car - so this needs no configuration and
        is correct on a Gr.4 and a Gr.1 without being told anything.
        """
        top = float(p.rpm_alert_max or 0.0)
        if top <= 0.0:
            return 0.0
        return float(np.clip(p.engine_rpm / top, 0.0, 1.0))
