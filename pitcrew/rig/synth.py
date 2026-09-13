"""Making the signal the transducer feels.

The whole of this module is arithmetic on arrays. It opens no device, holds no
lock and knows nothing about telemetry - which is deliberate, because it is the
part that has to be right at 48,000 samples a second inside an audio callback,
and the only way to be confident of that is to be able to run it a thousand
times in a test with no hardware attached.

Four rules shape everything here, and each one is a fault that has actually
happened to somebody:

**Two clocks, never one.** The control values arrive at 60 Hz from GT7 and the
carrier is rendered at 48 kHz. Those are different rates by a factor of 800 and
must never be conflated. In particular the telemetry is NOT the signal: at
60 Hz its Nyquist is 30 Hz, which is below the usable band entirely, so
resampling suspension travel up to audio rate produces aliased mush and not
road texture. Telemetry modulates locally generated sound. Nothing else.

**Phase is state, never recomputed.** An oscillator whose phase is derived from
an absolute sample index clicks every time its frequency changes, because the
waveform jumps rather than bends. Each voice here carries its phase forward and
advances it; changing the frequency then changes the slope, which is inaudible.

**Every parameter ramps across the block.** A gain that steps between blocks is
a discontinuity, and a discontinuity at 150 W is a thump. Intensities are
interpolated from where they were to where they are over the length of each
block.

**Nothing allocates in the hot path.** Buffers are made once at construction and
written into with `out=`. The rules are Bencina's and the sounddevice docs
restate them: no allocation, no logging, no locks, no I/O inside a callback.
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field

import numpy as np

from pitcrew.rig import transducer

# Below this an effect is off and its oscillator is left alone. Not a
# threshold on what the driver can feel - that is the effect's own business -
# but a way of not spending arithmetic on silence.
SILENT = 1e-4

# How quickly a control value is allowed to move, as a time constant. Slow
# enough that 60 Hz steps are inaudible as steps, fast enough that a kerb does
# not arrive late.
SMOOTH_S = 0.02

# DC blocker corner. Well below the amp's own 25 Hz low-cut so it removes any
# offset without touching the band.
#
# The pole is computed rather than copied. The `R = 0.995` seen in most
# published DC blockers puts -3 dB near 35 Hz at 48 kHz, which would eat the
# bottom third of everything this rig can produce.
DC_BLOCK_HZ = 5.0

# **The four priority classes, and what they buy.**
#
# One piston sums everything, so the only way an important cue stays legible is
# for the unimportant ones to get out of its way. Human-factors work on
# vibrotactile displays puts the number of concurrently attendable streams at
# one body site at about two; beyond that they merge into a texture. This
# system has seven voices, so it can only work if at any instant there is ONE
# foreground and ONE background.
#
# That is what these classes enforce. Everything in STATE and BED is background
# and ducks; everything in CRITICAL and TRANSIENT is foreground and does not.
CRITICAL = 0     # the car is at or past a limit; never ducked by anything
TRANSIENT = 1    # a discrete event, brief, allowed past the sustained ceiling
STATE = 2        # what the car is doing, continuously
BED = 3          # immersion; the sound of the car being alive


@dataclass(frozen=True)
class EffectSpec:
    """One effect, in the terms the driver already tuned it in.

    Gains and frequencies come straight from his SimHub profile so the port
    starts from eight days of his tuning rather than from defaults. `gain` is
    0-100 as SimHub stores it; the mix scales it against a reference level the
    driver has actually felt - see `transducer.CALIBRATION_AMPLITUDE`.
    """
    name: str
    gain: float
    freq_lo: float
    freq_hi: float = 0.0
    noise: float = 0.0
    # **His gamma filter, and the reason the first build felt weak.**
    #
    # `threshold` cuts below a level and `min_force` is applied after it, so an
    # effect that fires at all starts at 12-28% rather than creeping up from
    # nothing. Leaving these out - as the first version did - turns every
    # ordinary event into a whisper, because the raw intensities that come out
    # of `effects` sit low most of the time and a linear map keeps them there.
    # He set these values on the rig over eight days; they are not decoration.
    #
    # `gamma` above 1 makes the effect more sensitive - it lifts the small end
    # without moving the top - which is why it is applied as a 1/gamma
    # exponent. `input_gain` above 100 lets an effect saturate before its input
    # does; only wheelspin uses it, at 115.
    threshold: float = 0.0
    min_force: float = 0.0
    gamma: float = 1.0
    input_gain: float = 100.0
    # **A correction for where an effect sits in the rig's response.**
    #
    # SimHub's gains are not comparable across frequencies, because this rig
    # does not deliver them equally - see `transducer.FELT_RESPONSE`, measured
    # in the seat. An effect on the 40-55 Hz peak carries much further than the
    # same amplitude in the 70 Hz null.
    #
    # His gain stays exactly as he tuned it - that is the provenance and it is
    # worth keeping visible - and this carries the correction, so "gear is too
    # strong" has one number to change and it is obvious which.
    #
    # Three earlier trims were sized against a 1/f-squared model that the
    # measurement has since refuted, which is why gear went from too strong to
    # imperceptible without passing through right. Size these against the
    # curve now, not against arithmetic.
    felt_trim: float = 1.0
    # **A correction ACROSS the effect's own band, which is a different
    # question from the one `felt_trim` answers.**
    #
    # `felt_trim` is a static number for where the effect sits. It cannot
    # help an effect that MOVES: chassis load spans 56-66 Hz, and the rig
    # delivers 2.4 at the bottom of that and 1.4 at the top, so as the driver
    # loads the car harder the effect rises in amplitude and falls in
    # delivery. The same fault was found and fixed once before by narrowing a
    # band away from the 70 Hz null; this fixes the general case instead.
    #
    # When set, the rendered amplitude is divided by the response at the
    # frequency being played and multiplied by the response at the band's
    # centre, so climbing the band changes pitch and not felt strength. It is
    # normalised to the centre precisely so it does NOT double-count the
    # driver's own gain, which was tuned with the effect somewhere in the
    # middle of its range.
    band_compensate: bool = False
    # **Amplitude modulation: the pulse rate, in hertz, at the bottom and top
    # of the effect's severity.** Zero means an unmodulated tone.
    #
    # This is the second axis of the tactile vocabulary and the one the rig
    # had no use of at all. See `transducer.AM_RANGE_HZ`.
    am_lo: float = 0.0
    am_hi: float = 0.0
    am_depth: float = 0.0
    # **Priority, which decides what gets out of whose way.** Lower is more
    # important. The mixer reads only this - `transient` below is kept because
    # it is the word the rest of the code and the tests use for class 1.
    #
    #   0 CRITICAL   the car is at or past a limit
    #   1 TRANSIENT  a discrete event that just happened
    #   2 STATE      what the car is doing, continuously
    #   3 BED        immersion; the sound of the car being alive
    priority: int = 3
    # How fast the level is allowed to move, up and down, as time constants.
    # Separate because they are separate questions: a limit cue must arrive
    # the frame it is true, and must not chatter when it stops. Zero means
    # "use the module default", which is what every immersion effect wants.
    attack_s: float = 0.0
    release_s: float = 0.0

    @property
    def transient(self) -> bool:
        """Class 1: a discrete event, allowed past the sustained ceiling."""
        return self.priority == TRANSIENT

    @property
    def centre_hz(self) -> float:
        return (self.freq_lo + (self.freq_hi or self.freq_lo)) / 2.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.gain <= 100.0:
            raise ValueError(f"{self.name}: gain {self.gain} is not 0-100")
        if not 0.0 <= self.noise <= 100.0:
            raise ValueError(f"{self.name}: noise {self.noise} is not 0-100")
        top = self.freq_hi or self.freq_lo
        if self.freq_lo < transducer.BAND_LOW_HZ or top > transducer.BAND_HIGH_HZ:
            raise ValueError(
                f"{self.name}: {self.freq_lo:.0f}-{top:.0f} Hz falls outside "
                f"the {transducer.BAND_LOW_HZ:.0f}-{transducer.BAND_HIGH_HZ:.0f} "
                f"Hz this amplifier passes. Below the low-cut is excursion "
                f"spent for no output, and excursion is what bottoms a piston.")
        if self.gamma <= 0.0:
            raise ValueError(f"{self.name}: gamma {self.gamma} is not positive")
        if not 0.0 <= self.min_force <= 100.0:
            raise ValueError(
                f"{self.name}: minimum force {self.min_force} is not 0-100")
        if not 0.0 < self.felt_trim <= 4.0:
            raise ValueError(
                f"{self.name}: felt trim {self.felt_trim} is not 0-4")
        if not 0.0 <= self.am_depth <= transducer.AM_MAX_DEPTH:
            raise ValueError(
                f"{self.name}: modulation depth {self.am_depth} is not "
                f"0-{transducer.AM_MAX_DEPTH}. Deeper than that and the effect "
                f"spends more time off than on, which reads as a stutter "
                f"rather than as a rate.")
        low, high = transducer.AM_RANGE_HZ
        for rate in (self.am_lo, self.am_hi):
            if rate and not low <= rate <= high:
                raise ValueError(
                    f"{self.name}: modulation at {rate} Hz is outside the "
                    f"{low}-{high} Hz the body reads as a rate. Below it the "
                    f"pulses are separate events; above it the modulation "
                    f"fuses with the carrier and stops being a rate at all.")
        if self.priority not in (CRITICAL, TRANSIENT, STATE, BED):
            raise ValueError(f"{self.name}: unknown priority {self.priority}")

    def shape(self, intensity: float) -> float:
        """The driver's own gain chain: threshold, gamma, then minimum force.

        Order matters and is SimHub's: the threshold decides whether the effect
        happens at all, and the minimum force decides how hard it starts once
        it does. Applying the floor first would make the threshold meaningless,
        because everything would arrive already lifted.
        """
        value = intensity * (self.input_gain / 100.0)
        if value <= 0.0:
            return 0.0
        floor = self.threshold / 100.0
        if value <= floor:
            return 0.0
        if floor < 1.0:
            value = (value - floor) / (1.0 - floor)
        value = min(1.0, value) ** (1.0 / self.gamma)
        minimum = self.min_force / 100.0
        return minimum + (1.0 - minimum) * value


# How far the background gets out of the way, and how quickly.
#
# 0.70 is about 10 dB at full - and a kerb thump does not shape to full, so the
# bed measured over his laps drops by nearer 7, which is what turns a gear
# shift from 8.5 dB under the road into 4 above it.
# The trial tunes in the order they were built. Each carries everything the
# one before it settled unless it says otherwise, so a feature switches on
# "from" a revision rather than being listed against every letter by hand.
REVISIONS = "ABCDEFG"


def revision_at_least(first: str) -> bool:
    """True when the selected trial tune is `first` or a later one."""
    current = rig_revision()
    return bool(current) and REVISIONS.index(current) >= REVISIONS.index(first)


def rig_revision() -> str:
    """Which trial tune is selected: a letter of REVISIONS, or "" for the default.

    `PITCREW_RIG_REV` names it; `PITCREW_RIG_REV_A=1` is kept because the Rev A
    test protocol and a test still use it. Read here, above the duck constants,
    because both the duck and the profile depend on it and they must never
    disagree - they did once, and a half-applied Rev A nearly went out as the
    real thing (see `HapticsEngine.__init__`).
    """
    named = os.environ.get("PITCREW_RIG_REV", "").strip().upper()
    # One letter, and a letter of REVISIONS. `"" in "ABCDEFG"` is True, so a
    # bare membership test returned early on an unset variable and silently
    # stopped honouring PITCREW_RIG_REV_A - caught by its own test.
    if len(named) == 1 and named in REVISIONS:
        return named
    if os.environ.get("PITCREW_RIG_REV_A"):
        return "A"
    return ""


# Rev D goes deeper again, chosen on the bench over a louder gear change: with
# the engine raised, "less feel of the gear thud", and a 0.92 duck gave the thud
# back without making it blunter (a louder thud had been "too big and blunt").
DUCK_DEPTH = (0.92 if revision_at_least("D")
              else 0.80 if revision_at_least("A") else 0.70)
# A limit cue gets more, because it lasts longer and matters more: 0.82 is
# about 15 dB. The point is not to make the cue loud - it is to make it the
# only thing happening, which is a different and much cheaper way to be
# noticed.
DUCK_CRITICAL = 0.88 if revision_at_least("A") else 0.82
DUCK_ATTACK_S = 0.02
DUCK_RELEASE_S = 0.18

# **When the car goes light, the rig goes quiet.**
#
# Unloading is the one vehicle state that must NOT be reported by adding
# energy, and the reason is that a real car does the opposite: over a crest the
# tyres stop transmitting and the seat goes still. Reproducing that costs no
# bandwidth at all and needs no band of its own - the background is simply
# attenuated in proportion, and the body reads the absence.
#
# It is also the only cue here that cannot be masked, because it is not a
# signal.
UNLOAD_DUCK = 0.75
UNLOAD_ATTACK_S = 0.05
UNLOAD_RELEASE_S = 0.12

# **Two limit cues at once.** Measured over 40 laps, the braking cue and the
# traction cue are both above their confirmed level on 0.14% of frames - rare,
# but it is corner exit onto a kerb and a trail-braked entry that steps out,
# which are not moments to hand the driver two overlapping rasps. The lesser of
# the two is attenuated to well under half so that one of them is clearly the
# message and the other is context.
ARBITRATE_ABOVE = 0.35
ARBITRATE_DUCK = 0.45

# **A cue has to mean it before the bed moves for it.**
#
# Reported from the seat as "a constant on and off hum that I couldn't work
# out what it was meant to represent", and the log agrees: the background duck
# read -5%, -25%, -59%, -8% on successive samples. Low-level flickers of the
# critical cues - a brake at its quiet floor, a traction level of 0.1 - were
# grabbing up to 15 dB of duck and handing it back, so the thing the driver
# felt was not the cues, it was the BED breathing around them.
#
# Below this level a cue rides on top of the bed without moving it; above, the
# duck scales from zero. The cue itself is unaffected - this gates what the
# background does, not what the foreground says.
#
# **The gate reads the cue's strength above its own floor, not the shaped
# level.** `min_force` lifts a cue's output the moment it fires at all -
# rear_traction's floor is 0.20, which sits above this gate by construction,
# so gating on the shaped level made the gate unreachable for exactly the
# channel it was built to filter. Reported from the seat, second time round,
# as "a little bit of the ducking issue still": a slip of 0.17 shaped to 0.245
# and moved the bed 15%, and without the floor it would have shaped to 0.056 -
# under the gate, no duck at all. The floor is a claim about perceptibility
# (anything the piston renders should be feelable), not about significance,
# so it is stripped back off before the bed decides whether to move.
DUCK_GATE = 0.15

# **The profile, and what survived from his own tuning.**
#
# The six effects here were his, ported from eight days of SimHub tuning, and
# four of them survive with his gain untouched. What changed is what feeds them
# and where they sit, and one thing is worth saying plainly: **his shaping
# constants for the two limit cues no longer mean what they meant.**
#
# `threshold=14` on wheel-spin was tuned against an input that read 0.037 while
# the car was simply accelerating - see the account in `vehicle.py`. Against an
# input that now reads zero unless the rear is genuinely doing something, the
# same 14 would cut most of the range it exists to report. Carrying it over
# unchanged would have been faithful to the number and unfaithful to the
# intention. His GAIN is the part that carries the intention - how loud this
# effect should be relative to the others - and that is kept exactly.
#
# Listed in band order, which is also roughly the order of how much of a lap
# each one is present for.
PROFILE = (
    # **The engine bed, moved down off the strong region.** His RPM effect sat
    # at 34-42 Hz, which straddles the 40 Hz peak - the single most efficient
    # frequency this rig has - for the least informative thing in the mix. It
    # now sits at 28-34, where the rig delivers 1.8-2.4 rather than 2.4-3.0,
    # and the space it vacated goes to the braking cue.
    #
    # His curve is hand-drawn in `effects.RPM_CURVE` and arrives here already
    # shaped, so it takes no gamma of its own. Worth knowing before asking for
    # more: the curve spans 36.91 to 63.06 across the revs actually used, so
    # this channel has **4.6 dB of range in a whole lap** however loud it is
    # made. It is a bed that firms up with revs, not a tachometer. Making it
    # one means redrawing the curve, which is his to draw.
    EffectSpec("engine", 9.52, 28.0, 34.0, noise=3.0,
               priority=BED, felt_trim=2.50),
    # **Road texture, moved out of the high region entirely.**
    #
    # This is the change that matters most in the whole file. His band was
    # 112-152 Hz, which the measured response rates 0.9 of 3; it was moved to
    # 86-104 to get it onto the upper peak, and that put the bed the driver is
    # inside for 95% of a lap directly on top of the wheel-spin cue at 82-108.
    # Two continuous rasps, same twelve hertz, one piston. The traction cue
    # could not be heard over the road for the whole of every lap, and that is
    # not a gain problem.
    #
    # 34-41 Hz puts it in the low region where road rumble belongs physically -
    # a real chassis passes surface noise through at 20-80 Hz - and leaves the
    # entire 80-115 region to the tyres.
    EffectSpec("road", 37.62, 34.0, 41.0, noise=12.0, threshold=8.0,
               min_force=28.0, gamma=1.60, priority=BED, felt_trim=0.80,
               band_compensate=True),
    # **The braking cue, and it is new.**
    #
    # There was no braking cue. There was a lock detector sharing a channel
    # with wheel-spin, reporting the ABS for over a second in every braking
    # zone - see `vehicle.py` for the measurement. This replaces it with two
    # states on one voice: the regulator working, at a level he can brake to,
    # and a genuine lock above it.
    #
    # It gets 40-50 Hz, the strongest ten hertz this rig has, because it is the
    # highest-value cue in the system for a driver whose stated weakness is
    # trail-braking depth. It pulses, at 7 Hz where the regulator has just
    # started and 16 Hz at a lock, because that is both what a locking tyre
    # feels like and the axis the body reads best at this carrier frequency.
    #
    # The gain matches wheel-spin's 70 - his loudest - and the felt trim takes
    # it back down, because 40-50 Hz delivers 3.0 against the high region's
    # 2.0. Equal number, equal felt authority, which is the intention.
    # **-3.5 dB, and the shape changed with it.** Reported from the seat after
    # the first drive as "too heavy and loud... quite extreme". Both are true
    # and they had different causes: the level, which this trim fixes, and the
    # shape, which `vehicle.BRAKE_OPTIMUM` fixes by anchoring the climb on the
    # slip where GT7 stops giving more braking force rather than on the whole
    # regulated plateau.
    #
    # It stays a CRITICAL cue at the strongest frequency on the rig, because
    # the measurement says the information is worth real time: past the peak
    # he gives up 12.4% of braking force, and 68% of his heavy braking is
    # spent there. Quieter, and now loudest where it is telling him something
    # he can act on.
    # **No minimum force, and no gamma. Both were defeating the shape.**
    #
    # Reported from the seat: "intense from the moment I apply any brake". The
    # log named it - `brake STABLE 0.07` rendering at 0.087 amplitude, where
    # STABLE is meant to be almost nothing.
    #
    # `min_force` exists so that an effect which fires at all is felt rather
    # than creeping up from nothing, and it is right for a kerb strike or a
    # shift. It is wrong here, because it turns the bottom of a continuously
    # varying cue into a step: a level of 0.07 came out shaped at 0.273, four
    # times what was asked for, the instant the brake was touched. The gentle
    # presence designed below `BRAKE_OPTIMUM` could not survive it, and nor
    # could `STABLE`.
    #
    # `gamma` of 1.25 was making it worse from the other side - it lifts the
    # small end by design, which is the opposite of what this cue wants. This
    # is the one effect in the set whose bottom end must stay quiet, because
    # the bottom end is where he spends every braking zone.
    #
    # So the level computed in `vehicle._braking` is now rendered as it was
    # computed. That is the whole point of having shaped it there.
    # **0.85, up from 0.42 - three cuts were made and never summed.**
    #
    # "Braking felt numb, no increase in feedback felt braking hard or soft."
    # Correct: the trim went 0.62 to 0.42, `min_force` 18 to 0 and the
    # below-optimum floor 0.18 to 0.06 in successive fixes, each right alone,
    # together about 13 dB - and the felt table then read road bed 0.54
    # against brake 0.28 at p99. The highest-value cue in the system was
    # losing to an immersion bed by half, which is the exact inversion the
    # priority classes exist to prevent. The SHAPE stays as it is - quiet
    # floor, step at the optimum - and the authority comes back.
    EffectSpec("brake_limit", 70.00, 40.0, 50.0, noise=4.0, min_force=0.0,
               gamma=1.0, priority=CRITICAL, felt_trim=0.85,
               am_lo=7.0, am_hi=16.0, am_depth=0.55,
               attack_s=0.006, release_s=0.05),
    # His gear thump, renamed for what it carries: a shift, and the rev
    # limiter. A single confirming tick at the strongest frequency on the rig.
    #
    # 0.55 was arrived at by measurement rather than taste. Replayed over eight
    # real laps it fired at -26.8 dBFS, 8.5 dB BELOW the road bed - "gear shift
    # can't feel", and arithmetic rather than opinion. Parity with the bed
    # would be 0.065 of his gain; a transient should stand above the bed rather
    # than sit level with it, and the ducking below gives it another 7 dB for
    # the length of the thump.
    # **+4.7 dB in total, from 0.55 to 0.95.** Asked for twice: "gears could
    # still come up slightly" after the first lift already took it from 2.37x
    # to 3.21x the road bed it lands on.
    #
    # 0.95 puts it near 4.1x, which is at the top of the 1.5x-4x range this
    # was last argued over - and that range is worth re-reading rather than
    # treating as a fence. It was established when the shift sat at 48 Hz
    # against a road bed at 86-104 Hz that was in the wrong place, ducked less
    # hard, and shared no band with it. The bed has since moved to 34-41 Hz,
    # the duck went from 10 dB to 15 for a critical cue, and a transient now
    # lands on a background that is genuinely out of the way. The old ceiling
    # was a statement about a different mix.
    EffectSpec("driveline", 39.87, 50.0, priority=TRANSIENT, felt_trim=0.95),
    # Impacts: a kerb strike, a landing, a compression the suspension has not
    # seen before, a collision. Raised off 28-38 Hz - where the kerb thump was
    # a third of the test tone and could not be felt - and now clear of the
    # braking cue below it rather than sitting inside it.
    #
    # His threshold of 55 was set for genuine impacts, which are rare. The
    # channel now also carries kerb strikes and landings, which are not, so it
    # comes down to 25 - otherwise a landing would have to be an accident
    # before it was felt.
    # **+4.8 dB and compensated across its band.** "Initial kerb strike is
    # non-existent, but running on them feels real" - so the texture bed is
    # doing its job and the strike is not.
    #
    # The log has the numbers. A strike fired at `impact 0.167@58Hz` against a
    # shift tick at `0.2705@50Hz` that he called perfect. This rig delivers
    # 3.0 at 50 Hz and 2.11 at 58, so the strike was arriving at 43% of the
    # tick's felt strength - half of the thing he called right, which is about
    # where "non-existent" lives.
    #
    # And it got weaker as it got harder, which is the fault `band_compensate`
    # exists for: the band runs 52-60 Hz and the pitch follows severity, so a
    # big hit climbed toward the 70 Hz null while a light one stayed on the
    # peak. The harder the kerb, the less of it arrived.
    #
    # 3.80 is close to the ceiling of 4.0, and that is worth saying rather
    # than hiding. His gain of 12.31 was set for genuine collisions, which are
    # rare; this channel's day job is now kerbs, which are not. If it ever
    # needs more than the trim can give, the GAIN is the thing to revisit - a
    # trim is meant to carry a correction, not a change of purpose.
    # **18.0, and it is the one gain in this file that is no longer his.**
    #
    # 12.31 was set in SimHub for genuine collisions, which are rare; this
    # channel's day job is now kerb strikes and landings, which are not, and
    # after two rounds of "kerb strikes not felt" the trim was at 3.8 of a
    # maximum 4 with nothing left. A trim is meant to carry a correction, not
    # a change of purpose - the purpose changed, so the gain does, recorded
    # here rather than smuggled. 18/70 at trim 3.8 puts the scale at 0.489,
    # just under the calibrated ceiling.
    EffectSpec("impact", 18.00, 52.0, 60.0, noise=3.0, priority=TRANSIENT,
               threshold=25.0, min_force=20.0, gamma=1.20, felt_trim=3.80,
               band_compensate=True),
    # His `TractionLossContainer`, renamed to what it actually carries: how
    # hard the car is leaning on its tyres, in g. The gain, noise and filter
    # are still his; the input changed from a saturating yaw-error model to
    # lateral g, and the band from 52-70 - which ended exactly on the null - to
    # 56-66 with the response compensated across it, so loading the car harder
    # now means feeling more all the way up instead of the signal partly
    # cancelling itself at the moment it mattered.
    EffectSpec("chassis_load", 35.19, 56.0, 66.0, noise=6.0, threshold=9.0,
               min_force=12.0, gamma=1.40, priority=STATE, felt_trim=0.85,
               band_compensate=True),
    # **The tyres, with the whole high region to themselves.**
    #
    # His band, his gain, his noise. What changed is that nothing else is in
    # here any more, and that the input is now slip above a learned reference
    # rather than slip above 1.04 - which, measured, was ordinary acceleration
    # for most of every lap.
    #
    # It rasps rather than pulses: 5 Hz where the rear has just started
    # working, 14 Hz when it is away. Shallower modulation than the braking cue
    # because a slide is a continuous thing and a lock is not.
    # **The threshold is 15 and it is doing real work.** Replayed over his own
    # laps without one, this channel was live for 84% of the lap at a median
    # of -20 dBFS - which is not a limit cue, it is a second bed, and a bed in
    # the one band reserved for limit cues. The state model reports the rear
    # working from the 72nd percentile upward because that is true and the
    # diagnostics want it; the driver is only TOLD from the point where it is
    # worth a correction. Live 12% of the lap, which is about four seconds a
    # lap and matches where the wheels are genuinely past their reference.
    EffectSpec("rear_traction", 70.00, 86.0, 104.0, noise=9.0, threshold=15.0,
               min_force=20.0, gamma=1.30, priority=CRITICAL, felt_trim=1.00,
               am_lo=5.0, am_hi=14.0, am_depth=0.45,
               attack_s=0.006, release_s=0.05, band_compensate=True),
)

# The name it had while there were six effects and they were all his. Kept so
# nothing that imports it breaks; it is the same object.
PORSCHE_RSR_17 = PROFILE

# **Rev A - the first tune built from measurement rather than from feel.**
#
# Measured 12 Sep 2026 (`docs/RIG-SWEEP_2026-09-12.md`): the knock ceiling and
# the driver's perception floor, by frequency. Laying every effect's real
# in-car level against both - replayed over twelve of his own laps - says
# something nobody had seen, because until now only one of the two curves
# existed:
#
#     amp 35        level   vs FLOOR   vs KNOCK
#     engine        -28.4     -3.4      -24.5      inaudible
#     road          -25.8     -0.8      -15.6      inaudible
#     chassis_load  -26.1     +8.7       -9.0
#     brake_limit   -10.4    +17.1       -1.4      no margin
#     driveline     -11.4    +18.6       -5.4
#     impact         -6.2    +26.8       +7.0      KNOCKS
#     rear_traction  -6.0    +22.4        0.0      ON the limit
#
# **The beds are not quiet, they are absent** - below the level at which he can
# detect them at all - while the two events run past the point where the
# transducer runs out of travel. The rig's whole dynamic range is allocated to
# one end. At amp 29 it is worse: engine -9.4 and road -6.8 below the floor.
#
# So Rev A brings the offenders DOWN and the beds UP, and keeps amp 35, which
# is the only position where the beds get close to audible at all.
#
# Every number below is one of those two measured curves, not a preference:
#
#   * `impact` -9 dB     -> 2 dB inside the knock threshold, still +17.8 over
#                           the floor. It stays at 52-60 Hz ON PURPOSE: 60 Hz
#                           is the most SENSITIVE frequency on the rig, moving
#                           it down to 30-42 costs ~10 dB the trim cannot buy
#                           back inside the ceiling, and moving it up to
#                           120-140 was tried in the seat and read as "more
#                           like ABS or traction control".
#   * `rear_traction` -4 dB -> off the limit it was sitting exactly on.
#   * `brake_limit` -3 dB   -> from 1.4 dB of margin to 4.4.
#   * `driveline` -2 dB     -> sits with the other two transients.
#   * `road` +7 dB       -> +6.2 over the floor. Audible for the first time.
#   * `chassis_load` +3 dB
#   * `engine` +6 dB     -> only +2.6 over the floor, deliberately the quietest
#                           thing here. It is the LOWEST band and it is always
#                           on, and salience is set by the ratio to the lowest
#                           component present (Le et al. 2023) - an always-on
#                           bed at the bottom anchors everything above it.
#
# **The duck has to deepen with them.** Raising a bed raises what every event
# must beat, and that is exactly how the kerb thump came to fire 11.3 dB BELOW
# the road bed once before. See `DUCK_DEPTH` / `DUCK_CRITICAL`.
#
# Opt in with `PITCREW_RIG_REV_A=1`. Not the default until it has run laps.
_REV_A_TRIM = {
    # +4.1 dB, and it wanted +6.0. **`felt_trim` is capped at 4 and the cap
    # binds here** - engine's own gain is 9.52, the lowest in the profile by a
    # factor of four, so no trim inside the allowed range lifts it clear of the
    # floor. It lands about +0.7 dB over, i.e. right ON the threshold. Raising
    # it further means raising the GAIN, which is the driver's number, not a
    # correction - so it is left for him to decide after he has felt this.
    "engine": 4.000,
    "road": 1.792,            # +7.0 dB
    "brake_limit": 0.601,     # -3.0 dB
    "driveline": 0.755,       # -2.0 dB
    "impact": 1.349,          # -9.0 dB
    "chassis_load": 1.200,    # +3.0 dB
    "rear_traction": 0.631,   # -4.0 dB
}
PORSCHE_RSR_17_REV_A = tuple(
    dataclasses.replace(spec, felt_trim=_REV_A_TRIM[spec.name])
    if spec.name in _REV_A_TRIM else spec
    for spec in PROFILE)


# **Rev B - Rev A with `chassis_load` OFF. One variable.**
#
# Rev A was rejected in the seat on 13 Sep 2026 (session 163): "too much
# constant vibration ... rear traction not strong or maybe buried under constant
# vibration on turning ... no ripple strip feeling", and the gear change was
# not felt either. The mix log put the constant vibration on `chassis_load`:
# live in every corner at 59-65 Hz, the most SENSITIVE band on the rig, and at
# the one moment traction loss fired it was louder than the cue (0.198@64Hz
# against rear_traction 0.140@94Hz) with the critical duck taking only 16%.
#
# The plan was to drive that one change. It was replayed instead, because the
# masking check in `tools/rig_levels.py` - written the same night - reproduced
# the driver's Rev A report from telemetry alone before grading anything new
# (session 163: traction buried 67% of its live time, 79% under chassis_load;
# gear change 58%; chassis_load over his floor 74% of the time). Over all 21
# laps he drove that night in this car, race included, share of each cue's
# live time something else is stronger:
#
#                     default   Rev A   A minus chassis_load
#     rear_traction     42%      69%          24%
#     driveline         37%      49%          38%
#     impact            12%      53%          25%
#     brake_limit       33%      41%          32%
#
# Two things out of that. His EVERYDAY profile already buries traction 42% of
# the time, 91% of it under chassis_load - Rev A did not create the problem, it
# deepened it. And removing chassis_load alone only moves the masker onto
# `road`, which Rev A raised 7 dB and which he did not feel on the straights
# anyway; it then takes 86% of the kerb strike's burial.
#
# So Rev B is built on that, not driven blind:
#
#   * `chassis_load` OFF. "Off" is a trim of 0.01 (-41.6 dB against Rev A):
#     the spec guard requires a trim above zero, and removing the effect would
#     misalign the intensity array the deriver fills by position.
#   * `road`, `engine`, `driveline` back to DEFAULT. Rev A's lifts were not felt
#     as beds and became the next masker; the gear change was lost under them.
#   * `impact`, `rear_traction`, `brake_limit` stay at REV A - the levels bench-
#     checked at amp 35 on 13 Sep: kerb "no knock, still a kerb strike",
#     traction "no knock, feels good". The old kerb was "way too hard".
#   * Duck stays at Rev A's 0.80 / 0.82->0.88: deeper ducking only ever helps a
#     cue against a bed.
_DEFAULT_TRIM = {spec.name: spec.felt_trim for spec in PROFILE}
_REV_B_TRIM = {
    "engine": _DEFAULT_TRIM["engine"],
    "road": _DEFAULT_TRIM["road"],
    "driveline": _DEFAULT_TRIM["driveline"],
    "impact": _REV_A_TRIM["impact"],
    "rear_traction": _REV_A_TRIM["rear_traction"],
    "brake_limit": _REV_A_TRIM["brake_limit"],
    "chassis_load": 0.010,
}
PORSCHE_RSR_17_REV_B = tuple(
    dataclasses.replace(spec, felt_trim=_REV_B_TRIM[spec.name])
    if spec.name in _REV_B_TRIM else spec
    for spec in PROFILE)


# **Rev C - Rev B, turned up where the driver asked.**
#
# Rev B in the seat, 14 Sep 2026 (session 167): "Overall much better just think
# everything could go up a bit but especially rear traction loss and kerb
# strikes". Traction "can feel slightly"; kerb strikes "could be stronger",
# ripple strips OK; gear change "there but could be stronger"; engine rumble
# missing; no knock.
#
# Each lift is sized against the peak the real mix renders for that effect at
# full intensity, measured per effect, against the knock onset at its top pitch:
#
#                    B peak   onset   margin    C lift
#     rear_traction  -10.5    -5.4    +5.1      +6 dB   his first ask
#     impact         -15.3   -18.0    -2.8      +3 dB   his second ask
#     driveline      -11.1    -6.0    +5.1       0 dB   (+7 blunt, +3 worse)
#     brake_limit    -10.7    -6.0    +4.7      +3 dB   (+5 knocked)
#     engine         -14.7    -6.6    +8.1      +4 dB   (chosen in the seat)
#     road           -13.5   -11.4    +2.1      +3 dB
#
# `impact` reads as already over, and it was clean on the bench and on track.
# The knock curve was taken with a MICROPHONE detector that called 60 Hz knock
# about 6 dB below where the driver's ear did, so for a brief transient it is
# conservative; the 40 Hz entry, meanwhile, came from a bench tool driving both
# channels at full (6 dB hotter than the app's per-channel 0.5), so it is
# conservative the other way. Neither is trusted alone: Rev C goes to the
# bench at full intensity before a lap.
#
# Engine was first put back to Rev A's 4.0 because its rumble was missed, and
# the masking replay refused it: the always-on lowest band became the masker of
# the gear change and the brake cue (each buried 33% of its live time, engine a
# third of that), undoing the one thing he also asked for - a stronger gear
# change. So engine takes +2 dB only, and the gear change and brake cue take
# +7 and +5 instead of +4 and +3, inside their headroom by ear - and the
# brake cue then knocked very slightly at +5 on the bench, so it takes +3. Road gets a
# modest +3: its "bumps" were checked in the stored laps first - 21 laps that
# night, worst tarmac hit 0.62 m/s and the hits did NOT recur at the same lap
# position (0% above 0.3 m/s), so there are no discrete bumps in this channel
# to render there, only the bed.
# **The traction shaping was tested and kept.** The driver asked, from the
# bench, that the cue "rise with the actual amount of wheelspin ... not just oh
# traction broke full vibration". Traced: the deriver's input IS graded
# (vehicle.ramp of slip excess, SLIP_ONSET 0.012 to SLIP_FULL 0.150), and the
# shaping (threshold 15, min_force 20, gamma 1.3) leaves useful slip silent and
# packs excessive-to-full into 6.7 dB. A dB-even proposal (threshold 8,
# min_force 10, gamma 0.75: -18.5/-11.3/-6.3/-2.8/0 dB across the five slip
# levels) was played as a staircase A/B against it, 14 Sep, seated: "first one
# is better" - the CURRENT shaping, "better and more realistic, steps were
# good". And the complaint itself came from the BENCH: the first check played
# the cue at one constant full level, which is the "full vibration" he meant.
# There was no in-car defect to chase. Lesson: judge a graded cue on the bench
# as a graded input, never as a single held level.
_REV_C_TRIM = dict(
    _REV_B_TRIM,
    rear_traction=round(_REV_B_TRIM["rear_traction"] * 10 ** (6.0 / 20), 3),
    impact=round(_REV_B_TRIM["impact"] * 10 ** (3.0 / 20), 3),
    # Bench, 14 Sep, amp 35 seated, a two-gear pull through the real mix
    # (revs on the app's own RPM_CURVE, the app's own shift pulse): +7 was
    # "too big and blunt", +3 still lost to Rev B's level. It stays at B.
    driveline=_REV_B_TRIM["driveline"],
    # +5 dB knocked very slightly on the bench at full (14 Sep, amp 35,
    # seated) - its top pitch is 50 Hz, nearer the resonance than traction's
    # 94-104 - so it takes +3.
    brake_limit=round(_REV_B_TRIM["brake_limit"] * 10 ** (3.0 / 20), 3),
    # Same pulls: +2 "felt the same, possibly a bit more"; +4 chosen, and
    # confirmed in combination with the gear change at B's level ("yes that's
    # good"), because a louder engine can flatten the same shift thump.
    engine=round(_REV_B_TRIM["engine"] * 10 ** (4.0 / 20), 3),
    road=round(_REV_B_TRIM["road"] * 10 ** (3.0 / 20), 3),
)
PORSCHE_RSR_17_REV_C = tuple(
    dataclasses.replace(spec, felt_trim=_REV_C_TRIM[spec.name])
    if spec.name in _REV_C_TRIM else spec
    for spec in PROFILE)


# **Rev D - Rev C with the driver's engine, road and duck.**
#
# Rev C in the seat, 14 Sep 2026 (session 168, a different car - 2177 - from
# the laps the replays were run on): "traction is great, gear changes great,
# engine rumble needs to be stronger, road texture still seems to lack a bit,
# kerbs are great".
#
#   * engine +4 dB over Rev C. Chosen from three two-gear pulls (C, +2, +4):
#     "3", no knock on any. The trim was already at its 0-4 guard, so the lift
#     is on the GAIN, 9.52 -> 14.946 - his SimHub number, changed because he
#     asked for more. The trim guard is left alone on purpose.
#   * DUCK_DEPTH 0.92: the louder engine gave "less feel of the gear thud", and
#     a harder engine dip under the shift was preferred to a louder thud (B
#     over A). It applies to every transient, so kerbs and bumps duck the beds
#     a little more too.
#   * road +3 dB over Rev C, from a cruise A/B: "feels ok can definitely feel
#     road and bumps but it's hard to know without driving it".
_REV_D_TRIM = dict(_REV_C_TRIM,
                   engine=4.000,
                   road=round(_REV_C_TRIM["road"] * 10 ** (3.0 / 20), 3))
_REV_D_GAIN = {"engine": 14.946}
PORSCHE_RSR_17_REV_D = tuple(
    dataclasses.replace(spec, felt_trim=_REV_D_TRIM[spec.name],
                        gain=_REV_D_GAIN.get(spec.name, spec.gain))
    for spec in PROFILE)


# **Rev E - Rev D with the engine up 2 dB more.**
#
# Rev D in the seat, 14 Sep 2026 (session 169): "road texture seems ok,
# everything else is perfect except engine rumble needs to come up a bit". So
# one change: engine gain 14.946 -> 18.816 (+2 dB), trim still at its guard.
_REV_E_GAIN = {"engine": round(14.946 * 10 ** (2.0 / 20), 3)}
PORSCHE_RSR_17_REV_E = tuple(
    dataclasses.replace(spec, gain=_REV_E_GAIN.get(spec.name, spec.gain))
    for spec in PORSCHE_RSR_17_REV_D)


# **Rev F - the engine moved up out of the basement and made to climb.**
#
# Rev E's +2 dB pull, 14 Sep: "I don't think engine rumble should be that
# deep?" He was right, and more gain had been the wrong lever all along. The
# engine voice sat at 28-34 Hz, just above the amp's 25 Hz low-cut, and its
# pitch follows its own intensity - which RPM_CURVE tops out at 0.63 at the
# limiter - so across the whole rev range it swept 28 -> 31.8 Hz: a fixed deep
# boom that more gain only made boomier. A real engine's vibration is far above
# it (a four-cylinder at 8,600 rpm fires near 290 Hz; crank rotation is 143 Hz).
#
# Three pulls A/B'd: the deep one, 66->86 Hz at the limiter, and 36->50 Hz.
# He chose 66->86 as the most like an engine; it climbs with the revs; the gear
# thud stays clear; the 36->50 one KNOCKED (the rig has least room near 50 Hz).
# freq_hi is set so the pitch reaches 86 Hz at intensity 0.63. It sits in the
# region chassis_load vacated and clear of the 60 Hz resonance, where he feels
# about 6 dB more easily than at 31 Hz - so the gain comes DOWN to 9.43.
_ENGINE_TOP_INTENSITY = 0.63            # RPM_CURVE at the limiter
_REV_F_ENGINE = dict(freq_lo=66.0,
                     freq_hi=round(66.0 + (86.0 - 66.0) / _ENGINE_TOP_INTENSITY, 1),
                     gain=9.43)
PORSCHE_RSR_17_REV_F = tuple(
    dataclasses.replace(spec, **_REV_F_ENGINE) if spec.name == "engine" else spec
    for spec in PORSCHE_RSR_17_REV_E)


# **Rev G - the engine climbs audibly, and kerbs are graded (effects.py).**
#
# Rev F in the seat, 14 Sep 2026 (session 170): "engine could climb more but
# other than that way better; kerb strikes need improving, link to suspension
# maybe, as a small kerb and big kerb hit the same".
#
# Engine: 66->86 Hz was spread over RPM_CURVE intensity 0..0.63, but a real pull
# lives between ~45% and 95% of the revs, where the curve gives 0.166..0.599 -
# so on track it swept ~71->85 Hz, a 20% change, right at the tactile pitch JND
# (15-30%). Re-spread so that same pull sweeps 66->100 Hz (+52%). Below 60 Hz
# it only ever sounds at idle-level intensity, where knock is not in reach.
_REV_G_PULL = ((0.166, 66.0), (0.599, 100.0))     # (intensity, Hz) at 45% / 95% revs
_G_SLOPE = (_REV_G_PULL[1][1] - _REV_G_PULL[0][1]) / (_REV_G_PULL[1][0] - _REV_G_PULL[0][0])
_REV_G_ENGINE = dict(freq_lo=round(_REV_G_PULL[0][1] - _REV_G_PULL[0][0] * _G_SLOPE, 1),
                     freq_hi=round(_REV_G_PULL[0][1] + (1.0 - _REV_G_PULL[0][0]) * _G_SLOPE, 1))
PORSCHE_RSR_17_REV_G = tuple(
    dataclasses.replace(spec, **_REV_G_ENGINE) if spec.name == "engine" else spec
    for spec in PORSCHE_RSR_17_REV_F)


def default_profile():
    """The profile a `HapticMix` uses when none is named."""
    revision = rig_revision()
    if revision == "G":
        return PORSCHE_RSR_17_REV_G
    if revision == "F":
        return PORSCHE_RSR_17_REV_F
    if revision == "E":
        return PORSCHE_RSR_17_REV_E
    if revision == "D":
        return PORSCHE_RSR_17_REV_D
    if revision == "C":
        return PORSCHE_RSR_17_REV_C
    if revision == "B":
        return PORSCHE_RSR_17_REV_B
    if revision == "A":
        return PORSCHE_RSR_17_REV_A
    return PORSCHE_RSR_17


def profile_name(specs) -> str:
    """"REV A", "REV B" or "default" - for the log line that says which tune ran."""
    specs = tuple(specs)
    if specs == tuple(PORSCHE_RSR_17_REV_G):
        return "REV G"
    if specs == tuple(PORSCHE_RSR_17_REV_F):
        return "REV F"
    if specs == tuple(PORSCHE_RSR_17_REV_E):
        return "REV E"
    if specs == tuple(PORSCHE_RSR_17_REV_D):
        return "REV D"
    if specs == tuple(PORSCHE_RSR_17_REV_C):
        return "REV C"
    if specs == tuple(PORSCHE_RSR_17_REV_B):
        return "REV B"
    if specs == tuple(PORSCHE_RSR_17_REV_A):
        return "REV A"
    if specs == tuple(PORSCHE_RSR_17):
        return "default"
    return "custom"

# Values that arrive alongside the effects and render nothing. See
# `HapticMix.render` and `effects.EffectDeriver.MODIFIERS` - the two lists have
# to agree, and a test says so.
MODIFIERS = ("unload",)

class _Voice:
    """One effect's oscillator, its noise, and the state both carry forward."""

    def __init__(self, spec: EffectSpec, rate: int, block: int) -> None:
        self.spec = spec
        self._rate = float(rate)
        self._phase = 0.0
        self._level = 0.0
        # Where in its band the effect currently sits, 0-1. Kept apart from
        # the level - see `render`.
        self._pitch = 0.0
        # Bandpass state for the noise, a two-pole state-variable filter. It
        # is unconditionally stable at these frequencies - 25-160 Hz against a
        # 48 kHz rate is an f/fs of a few thousandths.
        self._bp_low = 0.0
        self._bp_band = 0.0
        self._rng = np.random.default_rng(abs(hash(spec.name)) % (2 ** 32))
        # Everything the render path writes into, made once. `_idx` is 1..N
        # held rather than rebuilt: `np.arange` allocates and has no `out`,
        # and allocating inside an audio callback is the thing not to do.
        self._buf = np.zeros(block, dtype=np.float32)
        self._ramp = np.zeros(block, dtype=np.float32)
        self._noise = np.zeros(block, dtype=np.float32)
        self._am = np.zeros(block, dtype=np.float32)
        # The modulator's own phase, carried forward for exactly the reason the
        # carrier's is: a pulse rate that changes with severity would click at
        # every change if the phase were recomputed from a sample index.
        self._am_phase = 0.0
        self._idx = np.arange(1, block + 1, dtype=np.float32)
        # Carried across blocks so the interpolated noise does not restart
        # from zero at every boundary, which would be a click per block.
        self._noise_tail = 0.0

    @property
    def level(self) -> float:
        return self._level

    @property
    def frequency(self) -> float:
        """Where in its band this voice last played, for the explainer."""
        spec = self.spec
        if not spec.freq_hi:
            return spec.freq_lo
        return spec.freq_lo + (spec.freq_hi - spec.freq_lo) * self._pitch

    def render(self, out: np.ndarray, intensity: float, pitch: float,
               n: int) -> None:
        """Add this effect's contribution for `n` samples into `out`.

        `intensity` is 0-1, the effect's own idea of how hard it is happening.
        `intensity` is the amplitude to render at - gain, felt trim and
        master already applied. `pitch` is the effect's own 0-1 intensity
        BEFORE any of that, and is what walks the frequency up its band.

        **They have to be two numbers.** They used to be one, and it made the
        pitch of every effect a function of its volume: an effect with a small
        gain could never climb out of the bottom of its own band, and turning
        the master up transposed the entire rig. Lateral load used a quarter
        of its range and the kerb thump a twelfth.
        """
        spec = self.spec
        target = float(np.clip(intensity, 0.0, 1.0))
        # **The band compensation scales the TARGET, never the ramp.**
        #
        # It was applied to the interpolated ramp after it was built, which
        # rescaled the ramp's STARTING point too - so whenever the correction
        # changed between blocks, this block began somewhere the last one did
        # not end. A discontinuity at every boundary, in proportion to the
        # amplitude: measured at 0.105 against an in-block step of 0.007 once
        # the impact channel got loud enough to show it. Folding it into the
        # target keeps the level continuous, at the cost of the correction
        # lagging by one block - about 11 ms on a value that follows the
        # pitch smoothing, which is far slower than that anyway.
        if spec.band_compensate:
            here = transducer.felt_response(self.frequency)
            centre = transducer.felt_response(spec.centre_hz)
            if here > 1e-6:
                target = min(1.0, target * min(1.8, max(0.6, centre / here)))
        if target < SILENT and self._level < SILENT:
            # Nothing here and nothing decaying. Leave the phase where it is:
            # it costs nothing to keep and means the next onset starts from a
            # continuous waveform rather than wherever zero happened to be.
            self._level = 0.0
            return

        buf = self._buf[:n]
        ramp = self._ramp[:n]

        # Interpolate the level across the block rather than stepping it.
        #
        # **Attack and release are separate**, and for the limit cues they are
        # very different. A single 20 ms constant is 20 ms of latency on a
        # wheel-lock warning, which is a fifth of the reaction time the warning
        # exists to buy; the same 20 ms on the way down is too fast and makes
        # the cue chatter at its own threshold. Immersion effects leave both at
        # zero and get the module default, which is what they want.
        rising = target >= self._level
        tau = spec.attack_s if rising else spec.release_s
        alpha = 1.0 - np.exp(-1.0 / (max(tau or SMOOTH_S, 1e-4) * self._rate))
        np.multiply(self._idx[:n], alpha, out=ramp)
        np.clip(ramp, 0.0, 1.0, out=ramp)
        start = self._level
        np.multiply(ramp, (target - start), out=ramp)
        np.add(ramp, start, out=ramp)
        self._level = float(ramp[-1])

        # Frequency follows the effect's own intensity when a range was
        # given. `freq_hi` of 0 means a single tone, which is how SimHub
        # stores the gear effect.
        #
        # Smoothed the same way the level is, and over the same time constant,
        # so a step in intensity bends the pitch rather than stepping it - a
        # pitch jump is heard as a click even when the phase is continuous.
        if spec.freq_hi:
            aim = float(np.clip(pitch, 0.0, 1.0))
            self._pitch += (aim - self._pitch) * float(ramp[-1])
            freq = spec.freq_lo + (spec.freq_hi - spec.freq_lo) * self._pitch
        else:
            freq = spec.freq_lo

        # Phase carried forward, so a frequency change bends the wave instead
        # of jumping it.
        step = 2.0 * np.pi * freq / self._rate
        np.multiply(self._idx[:n], step, out=buf)
        np.add(buf, self._phase, out=buf)
        self._phase = float((self._phase + step * n) % (2.0 * np.pi))
        np.sin(buf, out=buf)

        if spec.noise:
            self._add_noise(buf, freq, n, spec.noise / 100.0)

        if spec.am_depth and spec.am_lo:
            self._modulate(buf, n, spec)

        np.multiply(buf, ramp, out=buf)
        np.add(out[:n], buf, out=out[:n])

    def _modulate(self, buf: np.ndarray, n: int, spec: EffectSpec) -> None:
        """Pulse the carrier, at a rate that rises with severity.

        The second axis of the tactile vocabulary, and the cheap one. At a
        40-100 Hz carrier the receptors integrate rather than resolve, so two
        effects eight hertz apart feel like one effect at two strengths;
        flutter between about 5 and 20 Hz is discriminated well, and it is also
        what the events being reported actually feel like in a car - a locking
        tyre judders, a spinning one rasps.

        The envelope is `1 - d + d * (0.5 + 0.5 sin)`, so it swings between
        `1 - d` and 1 and never inverts the carrier. Depth is capped in
        `EffectSpec.__post_init__`: deeper than 0.6 and the effect spends more
        time off than on, which reads as a stutter rather than as a rate.
        """
        rate = spec.am_lo + (spec.am_hi - spec.am_lo) * self._pitch
        step = 2.0 * np.pi * rate / self._rate
        am = self._am[:n]
        np.multiply(self._idx[:n], step, out=am)
        np.add(am, self._am_phase, out=am)
        self._am_phase = float((self._am_phase + step * n) % (2.0 * np.pi))
        np.sin(am, out=am)
        depth = spec.am_depth
        np.multiply(am, 0.5 * depth, out=am)
        np.add(am, 1.0 - 0.5 * depth, out=am)
        np.multiply(buf, am, out=buf)

    def _add_noise(self, buf: np.ndarray, freq: float, n: int,
                   ratio: float) -> None:
        """Blend band-limited noise in, to roughen a tone that is too pure.

        A bare sine reads as a test tone rather than as a road. SimHub's
        `WhiteNoise` does the same job and the driver had it on every effect
        but the gear thump - 12 on the road rumble, which is the roughest
        thing he runs.

        The noise is band-limited by **generating it slowly and interpolating
        up**, rather than by generating it at 48 kHz and filtering back down.
        Random values a few per cycle of the effect's own frequency, joined by
        straight lines, have their energy concentrated in and just below that
        band by construction - which is where it is wanted, and it costs one
        `interp` instead of a per-sample filter loop.

        That matters more than it looks. The first version of this ran a
        two-pole filter in a Python `for` over every sample of every voice:
        correct, and about six thousand interpreted iterations per block
        inside an audio callback, which is the one place the sounddevice docs
        say not to do anything slow.
        """
        white = self._noise[:n]
        # Four points per cycle: enough to describe the band, few enough that
        # the interpolation is doing the band-limiting.
        low_rate = max(2, int(n * (freq * 4.0) / self._rate) + 2)
        points = self._rng.standard_normal(low_rate)
        points[0] = self._noise_tail
        self._noise_tail = float(points[-1])
        white[:] = np.interp(np.linspace(0.0, low_rate - 1.0, n),
                             np.arange(low_rate, dtype=np.float64), points)
        # **A fixed divisor, never the block's own peak.** Normalising each
        # block by its loudest sample rescales the value shared with the
        # previous block, so the one sample that was carried across for
        # continuity lands somewhere else - a step at every boundary, which
        # is a click, which at 150 W is a thump. Measured before this was
        # fixed: 0.0146 at the seam against a 0.0022 step inside the block.
        #
        # Three sigma covers a normal distribution well enough that the rare
        # excursion is caught by the limiter downstream, and being a constant
        # it cannot break the seam.
        np.multiply(white, 1.0 / 3.0, out=white)
        np.clip(white, -1.0, 1.0, out=white)
        np.multiply(buf, 1.0 - ratio, out=buf)
        np.multiply(white, ratio, out=white)
        np.add(buf, white, out=buf)


class HapticMix:
    """Every effect, summed into the one signal a single piston can make.

    Not thread-safe, and not meant to be: `render` is called only from the
    audio callback. Intensities cross the thread boundary as a plain array
    written by the telemetry side and read here, which is safe because a
    partially-updated intensity is merely a value one frame stale and the
    smoothing above swallows it.
    """

    def __init__(self, specs=None, *,
                 rate: int = transducer.SAMPLE_RATE,
                 block: int = 2048, master: float = 1.0) -> None:
        self.specs = tuple(specs if specs is not None else default_profile())
        # One number over the whole mix, for the driver to turn.
        #
        # The relative balance between effects is his, tuned over eight days,
        # and should be changed by editing an effect rather than by leaning on
        # this. The limiter still holds the peak whatever this is set to - but
        # NOT the duty cycle, which is what an amplifier's protection responds
        # to, so this is not a free control. Measured on a real lap: a master
        # of 2.5 puts 31.5% of blocks into the limiter and holds the mix at
        # -9.1 dBFS sustained, against 0.05% and -16.4 dBFS at 1.0.
        #
        # The amplifier's own knob is the better answer to "not strong
        # enough": it is at 35 of 50, so there is 3 dB sitting unused, and
        # turning it up changes neither the duty cycle nor the mix.
        self.master = max(0.0, min(4.0, float(master)))
        self._rate = rate
        self._block = block
        self._voices = [_Voice(spec, rate, block) for spec in self.specs]
        self._out = np.zeros(block, dtype=np.float32)
        # Per-effect scale: SimHub's 0-100 gain against the reference level
        # the driver actually felt. A transient may reach past the sustained
        # ceiling into the headroom above it.
        # **Relative to the loudest effect, not to an abstract 100.**
        #
        # SimHub's gains are weights inside its own chain - his sat under a
        # profile gain of 49.8 and a global of 100 - so reading them as
        # fractions of full scale here made even the strongest effect peak at
        # 0.35 against a reference of 0.5 that he had described as "very
        # strong", and the quiet ones vanished. Reported from the seat as
        # "worked fine, just very weak".
        #
        # Normalising by the largest gain keeps the balance he tuned - which
        # is the part worth eight days - while letting the mix reach the level
        # the amplifier was actually calibrated against. His loudest is
        # wheelspin at 70; that one now reaches the ceiling and everything
        # else sits below it in the proportions he chose.
        # **One ceiling for every effect, and the headroom is the limiter's
        # business alone.**
        #
        # This used to scale transients by `TRANSIENT_CEILING` and everything
        # else by `SUSTAINED_CEILING`, which quietly rewrote the driver's
        # balance: his gear effect is 39.87 and his road rumble 37.62 - within
        # 6% of each other - and the split ceilings turned that into 0.404
        # against 0.269, half again as loud. Reported from the seat as "gear
        # changes still feel overpowered", which is exactly right and was not
        # a taste question at all.
        #
        # The headroom above the sustained ceiling still exists and transients
        # still reach into it, but by being brief and landing on top of the
        # bed rather than by carrying a larger gain. That is the difference
        # between a peak that stands out and an effect that is simply louder.
        loudest = max(spec.gain for spec in self.specs) or 100.0
        self._scale = np.array(
            [spec.gain / loudest * transducer.SUSTAINED_CEILING
             * spec.felt_trim
             for spec in self.specs], dtype=np.float32)
        # **And then capped by what the rig can deliver THERE without knock.**
        #
        # `SUSTAINED_CEILING` is one number for the whole band, and since the
        # remount the real ceiling moves by 15 dB across it - the reaction mass
        # sits off-centre under gravity and reaches its stop at 60 Hz some
        # 12 dB earlier than at 120. Replayed over twelve of his own laps the
        # flat ceiling put `impact` at 0.489 at 56 Hz, about 13 dB past where
        # that frequency runs out of travel, on every kerb strike of every lap.
        # The limiter never saw a problem because it was measuring the one
        # thing that was in budget.
        #
        # This is a CAP, never a boost: an effect already inside its ceiling is
        # untouched, and his gains and trims keep deciding the balance
        # everywhere the hardware can honour them.
        #
        # **OFF by default, and it must stay off until it is calibrated.** Two
        # reasons, both found in the seat on 12 Sep 2026:
        #
        # 1. **It caps the wrong quantity.** `_scale` is a gain coefficient,
        #    not the emitted amplitude - measured, the rendered peak runs about
        #    HALF the scale (scale 0.4886 -> peak 0.2306; scale 0.0891 -> peak
        #    0.0500). So capping the scale at the knock amplitude lands about
        #    6 dB below what the constraint actually requires. The cap has to
        #    be derived from the peak an effect really emits, which depends on
        #    its own shaping (gamma, threshold, min_force, noise, AM) and is
        #    not knowable from the spec alone.
        # 2. **Correct or not, it broke the cue.** At the capped level the
        #    driver's verdict on the kerb strike was "didn't feel like a kerb
        #    strike". Relocating it to 120-140 Hz - where the ceiling is high
        #    enough to need no cap at all - failed differently: "no way, it's
        #    more like ABS or traction control". **Frequency carries learned
        #    meaning**, so the spectral plan is constrained by what a band
        #    MEANS to him and not only by what the rig can deliver there.
        #
        # Enabling this before it is calibrated trades a mechanical problem for
        # a driver who cannot read his own kerbs, which is the worse of the two.
        if os.environ.get("PITCREW_KNOCK_CEILING"):
            for i, spec in enumerate(self.specs):
                ceiling = transducer.knock_ceiling_for_band(
                    spec.freq_lo, spec.freq_hi)
                if self._scale[i] > ceiling:
                    self._scale[i] = np.float32(ceiling)
        # **How far the bed gets out of the way when an event fires.**
        #
        # With one piston every effect sums into one signal, so an event is
        # only legible if it stands above whatever else is playing. Measured
        # over eight of his laps, it did the opposite: the kerb thump fired
        # 11.3 dB BELOW the road bed and 7.6 dB below lateral load - which
        # occupies the same region of the response - and the gear thump 8.5 dB
        # below the bed. Reported as "kerb thump I can't feel" and "gear shift
        # can't feel", and no amount of gain on the events alone fixes it,
        # because raising them raises what they have to beat as well when the
        # limiter closes.
        #
        # So the sustained effects duck. Fast enough to be out of the way
        # before a 90 ms thump has peaked, slow enough coming back that the
        # recovery is not itself an event.
        self._duck = 1.0
        self._unload_duck = 1.0
        # The per-voice `min_force` floors, stripped back off when the duck
        # decides - see DUCK_GATE - with the buffer preallocated because
        # `render` is the callback and the callback must not allocate.
        self._floors = np.array([spec.min_force / 100.0
                                 for spec in self.specs], dtype=np.float32)
        self._floor_span = np.maximum(np.float32(1e-6), 1.0 - self._floors)
        self._strength = np.zeros(len(self.specs), dtype=np.float32)
        self._priority = np.array([spec.priority for spec in self.specs],
                                  dtype=np.int8)
        self._transient = self._priority == TRANSIENT
        self._critical = self._priority == CRITICAL
        # Background is everything that is allowed to get out of the way.
        self._background = self._priority >= STATE
        # **The explainer's storage, made once.**
        #
        # "What exactly caused that vibration" is a question the driver will
        # ask an hour after the session, and it can only be answered if the
        # numbers were kept at the time. They are kept in preallocated arrays
        # rather than dictionaries because this runs inside the audio callback,
        # where allocating is the one thing not to do; `explain()` builds the
        # readable form later, on whatever thread asks.
        count = len(self.specs)
        self._last_raw = np.zeros(count, dtype=np.float32)
        self._last_shaped = np.zeros(count, dtype=np.float32)
        self._last_level = np.zeros(count, dtype=np.float32)
        self._last_duck = np.ones(count, dtype=np.float32)
        self._last_freq = np.zeros(count, dtype=np.float32)
        self._dc_y = 0.0
        # Held rather than rebuilt: the DC correction is ramped across each
        # block, and `linspace` in a callback allocates.
        self._ramp01 = np.linspace(0.0, 1.0, block, dtype=np.float32)
        self._corr = np.zeros(block, dtype=np.float32)
        self.limited_blocks = 0
        # The loudest sample rendered since anyone last asked. Read and reset
        # by the health check, which needs to know whether we were producing
        # anything before it can call the card silent.
        self._recent_peak = 0.0

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    def render(self, intensities: np.ndarray, n: int) -> np.ndarray:
        """One block of mono signal. The returned view is reused - copy it if
        it has to outlive the call.

        `intensities` carries one value per effect, and may carry one more:
        the **unload modifier**, which is not an effect and renders nothing.
        A shorter array is read as an unload of zero, so anything written
        against the old length still works.
        """
        out = self._out[:n]
        out[:] = 0.0
        count = len(self._voices)
        raw = self._last_raw
        for index in range(count):
            raw[index] = float(intensities[index])
        unload = (float(intensities[count])
                  if len(intensities) > count else 0.0)
        shaped = self._last_shaped
        for index, voice in enumerate(self._voices):
            shaped[index] = voice.spec.shape(float(raw[index]))

        seconds = n / float(self._rate)

        # **Arbitration between the two limit cues.** They coincide on 0.14% of
        # measured frames, which is rare and is exactly the moment not to hand
        # the driver two overlapping rasps: the lesser is attenuated so one of
        # them is clearly the message and the other is context.
        if self._critical.any():
            levels = shaped[self._critical]
            if levels.size > 1:
                order = np.argsort(levels)[::-1]
                if levels[order[0]] > ARBITRATE_ABOVE and levels[order[1]] > ARBITRATE_ABOVE:
                    indices = np.flatnonzero(self._critical)
                    for rank in order[1:]:
                        shaped[indices[rank]] *= ARBITRATE_DUCK

        # How far the background steps aside, and for what. One duck for the
        # whole background rather than one per pair: the driver feels the sum,
        # not the effects.
        #
        # The duck decides on the cue's strength above its own `min_force`
        # floor - see DUCK_GATE for why gating on the lifted level made the
        # gate unreachable for exactly the channel it was built to filter.
        strength = self._strength
        np.subtract(shaped, self._floors, out=strength)
        strength /= self._floor_span
        np.maximum(strength, 0.0, out=strength)
        event = (float(strength[self._transient].max())
                 if self._transient.any() else 0.0)
        critical_s = (float(strength[self._critical].max())
                      if self._critical.any() else 0.0)
        # Gated, then rescaled so a full-scale cue still earns its full duck.
        event = max(0.0, event - DUCK_GATE) / (1.0 - DUCK_GATE)
        critical_g = max(0.0, critical_s - DUCK_GATE) / (1.0 - DUCK_GATE)
        aim = 1.0 - max(DUCK_DEPTH * event, DUCK_CRITICAL * critical_g)
        tau = DUCK_ATTACK_S if aim < self._duck else DUCK_RELEASE_S
        self._duck += (aim - self._duck) * min(1.0, seconds / tau)

        # **The absence cue.** When the car goes light the background is pulled
        # down rather than anything being added, because that is what a real
        # car does over a crest and because it is the one message on this rig
        # that nothing can mask.
        want = 1.0 - UNLOAD_DUCK * min(1.0, max(0.0, unload))
        tau = UNLOAD_ATTACK_S if want < self._unload_duck else UNLOAD_RELEASE_S
        self._unload_duck += (want - self._unload_duck) * min(1.0, seconds / tau)

        for index, voice in enumerate(self._voices):
            duck = (self._duck * self._unload_duck
                    if self._background[index] else 1.0)
            level = float(shaped[index]) * self._scale[index] * self.master * duck
            self._last_duck[index] = duck
            self._last_level[index] = level
            voice.render(out, level, float(shaped[index]), n)
            self._last_freq[index] = voice.frequency
        self._block_dc(out, n)
        self._limit(out, n)
        if n:
            self._recent_peak = max(self._recent_peak,
                                    float(np.max(np.abs(out[:n]))))
        return out

    def explain(self) -> list[dict]:
        """Every number behind the last block, per effect.

        The whole answer to "what exactly caused that vibration". Built here
        rather than in the callback: dictionaries allocate, and the callback
        must not.
        """
        rows = []
        for index, spec in enumerate(self.specs):
            rows.append({
                "effect": spec.name,
                "priority": spec.priority,
                "raw": round(float(self._last_raw[index]), 4),
                "shaped": round(float(self._last_shaped[index]), 4),
                "base_gain": round(float(self._scale[index]), 4),
                "ducked_by": round(1.0 - float(self._last_duck[index]), 4),
                "final": round(float(self._last_level[index]), 4),
                "hz": round(float(self._last_freq[index]), 1),
                "felt": round(transducer.felt_response(
                    float(self._last_freq[index]) or spec.centre_hz), 2),
            })
        return rows

    @property
    def duck(self) -> float:
        """What the background is currently multiplied by, all causes."""
        return self._duck * self._unload_duck

    def take_recent_peak(self) -> float:
        """The loudest thing rendered since this was last called."""
        peak, self._recent_peak = self._recent_peak, 0.0
        return peak

    def _block_dc(self, out: np.ndarray, n: int) -> None:
        """Remove any standing offset. A sustained one is excursion that never
        comes back - it holds the piston off centre and makes it bottom on the
        next transient rather than on a loud one.

        **Tracked per block, not per sample.** The textbook
        `y[n] = x[n] - x[n-1] + R*y[n-1]` is a per-sample recurrence, and
        running that in Python inside the callback costs more than everything
        else here put together. At a 5 Hz corner the filter moves so slowly
        that a block of 21 ms is well inside its time constant, so following
        the mean at block rate and subtracting it is the same answer to the
        precision that matters.

        Every source in this module is zero-mean by construction anyway -
        sines and zero-mean interpolated noise - so this is a guard against
        arithmetic drift rather than a shaping filter. If it ever has real
        work to do, something upstream is wrong.
        """
        mean = float(out[:n].mean())
        blocks_per_second = self._rate / max(1, n)
        alpha = min(1.0, 2.0 * np.pi * DC_BLOCK_HZ / blocks_per_second)
        previous = self._dc_y
        self._dc_y = previous + (mean - previous) * alpha
        if abs(previous) < SILENT and abs(self._dc_y) < SILENT:
            return
        # **Ramped from the old correction to the new one, not stepped.**
        # Subtracting a per-block constant that changes each block is itself a
        # discontinuity at every boundary - the exact fault this function
        # exists to avoid, built into the fix for it. Measured before this was
        # ramped: 0.0176 at the seam against a 0.0024 step inside the block.
        correction = self._corr[:n]
        np.multiply(self._ramp01[:n], (self._dc_y - previous), out=correction)
        np.add(correction, previous, out=correction)
        np.subtract(out[:n], correction, out=out[:n])

    def _limit(self, out: np.ndarray, n: int) -> None:
        """Soft knee, then a hard ceiling.

        Not to protect the transducer from damage - the amp has a thermal
        cutout for that - but because the BKA-PRO's DC-protect trips on
        excessive input and **stops the unit until it is reset**. A limiter
        here is the difference between a loud moment and no haptics for the
        rest of the race.

        Reaching the limiter routinely means the mix is wrong, not that the
        limiter is working, so it is counted.
        """
        # **The knee is the transient ceiling, not the sustained one.**
        #
        # It used to soft-clip at `SUSTAINED_CEILING`, which defeated the whole
        # reason the headroom above it exists: a gear shift or a kerb is
        # allowed past the bed precisely so it reads as an event, and clamping
        # the summed output at the bed's own ceiling made that impossible.
        # Measured, driving a plausible lap: the peak sat pinned at 0.499 at
        # every master gain from 1 to 4, while 71% of blocks were being
        # compressed at 4. The driver was hearing a compressor rather than a
        # mix - which is why turning it up added fullness but no impact.
        #
        # It is also the likeliest reason the transducer went quiet mid-corner.
        # The BKA-PRO's 150 W rating assumes a one-third duty cycle and its
        # DC-protect trips on sustained excessive input; 71% of blocks held
        # near full scale is exactly that.
        # **The knee is applied to every block, not only the loud ones.**
        #
        # It used to be conditional on the block's own peak, which made the
        # limiter itself a discontinuity generator: with the mix sitting near
        # the ceiling, alternate blocks got the tanh curve and their
        # neighbours did not, and the boundary between a compressed sample and
        # an uncompressed one is a step. Measured at 0.085 across a seam
        # against 0.007 inside the block - at 150 W, a click per block.
        #
        # tanh is memoryless and identical everywhere, so applied always it
        # cannot disagree with itself at a boundary. The cost is about 2% of
        # gentle compression at half scale, which is beneath anything the
        # driver can feel; the count still marks only the blocks that were
        # genuinely into the knee, because that is the signal that the mix is
        # running too hot.
        peak = float(np.max(np.abs(out[:n]))) if n else 0.0
        if n:
            np.tanh(out[:n] / transducer.TRANSIENT_CEILING, out=out[:n])
            np.multiply(out[:n], transducer.TRANSIENT_CEILING, out=out[:n])
        if peak > transducer.TRANSIENT_CEILING:
            self.limited_blocks += 1
        if peak > transducer.HARD_LIMIT:
            np.clip(out[:n], -transducer.HARD_LIMIT, transducer.HARD_LIMIT,
                    out=out[:n])


def to_stereo(mono: np.ndarray, out: np.ndarray, n: int) -> None:
    """Spread the mix across both channels at half amplitude each.

    Measured on this rig: both channels reach the piston and they SUM, so the
    same signal at full scale on both would spend 6 dB on the doubling. Half
    on each sums back to the equivalent of one channel at full, and a channel
    failing then costs 6 dB rather than everything.
    """
    scaled = mono[:n] * transducer.PER_CHANNEL_SCALE
    out[:n, 0] = scaled
    out[:n, 1] = scaled
