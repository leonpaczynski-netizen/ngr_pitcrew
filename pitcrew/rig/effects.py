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

from pitcrew.rig import synth, vehicle
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
# **And both are now a starting prior, not the answer, because they are one
# car's numbers on one circuit.** Replayed 23 Aug: tarmac texture speed runs a
# median of 0.0144 m/s for the RSR at Monza - the same quantity as the 0.0142
# above, re-measured over a different lap selection - and 0.0463 for the
# Shelby at Road Atlanta. 3.2x, so a full-scale point fitted on the first pins
# solid on the second. Measured on his laps this morning: the road bed was
# audible on 92.3% of frames, sat at full scale for the top decile, and won
# the mix on 74.9% of them, against a brake cue that won 0.31%. Reported from
# the seat as "lots of low vibrations but not a lot that means anything".
#
# So the SCALE is learned per car and per circuit, and what is kept fixed is
# the SHAPE he tuned - where tarmac sits inside the range, so that a kerb still
# has somewhere above it to go. The two anchors below are read straight off the
# numbers in the block above: at 0.008/0.090, tarmac's median lands at 0.076 of
# full scale and its p90 at 0.391. Fitting a line through those two quantiles
# of whatever the car is actually driving over reproduces 0.0080 and 0.0901 on
# the RSR at Monza - the hand-tuned pair, to three decimals - and moves on a
# car or a surface that is genuinely rougher.
#
# **This is a bed, and a bed is the one thing that SHOULD self-normalise.** A
# limit cue must not: a threshold set at a quantile of his own driving fires at
# a fixed rate for ever and reports "unusual for Leon" while claiming "past the
# limit". Immersion is the opposite case - the road should use the range
# available on every car and every circuit, which is exactly what a
# self-normalising scale gives it.
TEXTURE_AT_TARMAC_P50 = 0.0756
TEXTURE_AT_TARMAC_P90 = 0.3910
# Learned off tarmac frames only - kerbs and grass are the events this scale
# exists to leave headroom for, so teaching it with them defeats it - and above
# a crawl, so a pit lane at walking pace does not set the scale for a lap.
TEXTURE_LEARN_MIN_KPH = 18.0
TEXTURE_LEARN_STEP = 2.0e-4

# **The ceiling, learned from KERBS, and it is a different question from the
# onset.** The tarmac-only guard above is right about where the bed STARTS -
# it exists so a kerb cannot teach the road that rumble is normal. But it also
# set where the bed TOPS OUT, and that number then had no relationship to how
# big a kerb can be.
#
# Measured 1 Sep 2026 on 10 Daytona laps against 5 Spa sessions, same car:
#
#     learned scale top    Daytona 0.150 m/s   Spa 0.127
#     kerb velocity p50            0.098             0.053
#     kerb velocity p99            0.466             0.323
#     KERB FRAMES PINNED AT 1.0      30.5%            13.7%
#
# Daytona's kerbs are 1.9x Spa's at the median and reach 3.1x the top of the
# scale, so a third of the time he is on one the channel is flat out with
# nothing left - every kerb rendering identically and maximally, through the
# 34-41 Hz bed that sits on the rig's strongest response. Reported from the
# seat as "the ButtKicker goes berserk on the banked kerb", and it is literal
# saturation rather than a spurious trigger.
# **Ten times the tarmac step, because it has a hundredth of the samples.** A
# lap is mostly road and barely any kerb: 2,655 kerb frames across three
# Daytona sessions against 63,785 of tarmac. At the tarmac step this tracker
# reached 0.2008 by the end of the archive against a true kerb p90 of 0.2418 -
# converging, but not within a race, which for a ceiling means it spends the
# race too low and pins anyway. A ceiling is not a measurement and a little
# jitter in it costs nothing; arriving late costs the whole effect.
KERB_LEARN_STEP = 2.5e-3
# **Measured, not estimated, and the estimate was wrong.** Kerb frames are
# 2.2-2.8% of a Daytona lap, so 400 of them is four to five minutes of driving,
# not "a lap and a half of kerb contact" - and a short session never reaches
# them at all (113: 323 frames over the whole session). The gate is gone; this
# is kept only because `_kerb_p90` is still bounded by `_shape`.
KERB_SETTLE_FRAMES = 400
# **And there is no settle gate, because the seeding below removes the need
# for one.** Both trackers start exactly where the pair above puts them, so
# the fit returns that pair at frame 0 and walks continuously from it. A gate
# would only reintroduce the discontinuity it was meant to hide: measured on
# the Shelby stream, holding the prior until sample 6000 and then switching
# dropped the bed from 0.467 to 0.072 for its own median texture **in a single
# frame**, 100 seconds into every session - and the size of that step is
# proportional to how far the car is from the prior, so it is invisible on the
# RSR and worst on exactly the cars this exists for.
#
# Ungated, the largest single-frame change in bed level over the same stream
# is 0.0024, and it is converged in about 20 seconds rather than 100.
# Whatever is learned, the channel keeps a usable range: a degenerate fit - a
# billiard-smooth circuit where the two quantiles nearly coincide - must not
# collapse the ramp into a step.
TEXTURE_FULL_MIN_MS = 0.020
TEXTURE_FULL_MAX_MS = 1.000


def _seed_at(place: float) -> float:
    """The texture speed the shipped pair puts at `place` of full scale.

    So the two trackers start life agreeing with the prior they fall back to,
    and the scale cannot step when they settle.
    """
    return TEXTURE_ONSET_MS + place * (TEXTURE_FULL_MS - TEXTURE_ONSET_MS)
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
# **And neither boost applies at walking pace.** Session 41, measured: a spin
# at the Yas chicane left the car crawling back across kerb and grass at
# 14-31 km/h, and the boosts held the road bed at 0.15-0.49 for about four
# seconds with the car barely moving - reported from the seat as "prolonged
# rumble after going off track". The texture itself already scales with
# speed; the boosts were added AFTER that scaling, so a stationary car on a
# kerb rumbled like one riding it. Full authority by 45 km/h keeps every
# hairpin ripple strip exactly as it was - the lesson about kerbs mattering
# most in slow corners stands - and a car gathering itself up after a spin
# goes quiet.
SURFACE_BOOST_ONSET_KPH = 12.0
SURFACE_BOOST_FULL_KPH = 45.0

# **A kerb also gets a thump, separate from the rattle.**
#
# A real ripple strip is a thud with a rattle on top. The rattle rides on the
# road bed; this is the thud - a short pulse into `impact`, fired on the EDGE
# of touching the kerb rather than for as long as the wheel is on it, because
# the edge is what reads as sharp. Sitting on a kerb through a chicane stays a
# texture.
# **Graded by how hard the kerb is hit, not fired at one size.**
#
# Reported from the seat: "huge kerbs are felt huge but subtle kerbs aren't
# felt at all, there is no middle ground". The strike used to fire at a fixed
# 0.85 whatever happened - so what he was feeling as "huge" was the separate
# velocity-step impact and the texture bed, and the strike itself was the
# part he could not feel at any size. A binary input cannot have a middle
# ground; the suspension velocity at the moment of the strike can, and it is
# already measured: median 0.082 m/s on a kerb, p90 0.318.
KERB_THUMP_FLOOR = 0.70       # a brushed kerb, still unmistakably a kerb

# **Suspension bumps, lifted over the impact voice's own gate.**
#
# Reported from the seat on Rev B, 14 Sep 2026: "road bumps previously picked
# up from suspension travel seem missing". They were never all there. The
# compression event (`vehicle.VehicleState.compression`, an excursion beyond
# COMPRESSION_Z of that corner's own spread) rides the impact channel - and the
# impact voice gates everything under 25%, a threshold set for the noisy
# velocity-step detector. Compression is already a statistically gated event,
# so the gate only threw real bumps away.
#
# Measured over the 21 laps of 13 Sep before anything was built: 3.8 compression
# events a minute, **41% of them recurring at the same 20 m of the lap on at
# least half the laps** (five spots) - track features, not noise; the tarmac
# velocity channel, checked the same way, recurred 0%. Median event peak 0.16:
# under the gate, silent in every tune ever run. The p90 event (0.43) came
# through, and Rev A's -9 dB on impact took it 6 dB down with the kerb.
#
# So while one is live it is mapped into BUMP_FLOOR..BUMP_TOP: the floor just
# clears the gate so the smallest real bump is felt, and the top sits under
# KERB_THUMP_FLOOR so a bump never reads as a kerb. Single swell, no rhythm -
# the kerb strike keeps the double tap. Rev C and D.
BUMP_FLOOR = 0.35
BUMP_TOP = 0.60


def bump_level(compression: float) -> float:
    """A compression excursion as an impact-channel level, or 0 when none."""
    if compression <= 0.0:
        return 0.0
    return BUMP_FLOOR + (BUMP_TOP - BUMP_FLOOR) * min(1.0, compression)


# **A bump is an edge, not a state.** The first cut followed the compression
# level for as long as it lasted, and the driver felt all four sizes on the
# bench, graded, and under a kerb - "feel more like a rumble than a bump".
# Compression is a STATE: the spring stays down for a quarter second or more,
# and a voice that tracks it for that long is a rumble by construction. So the
# thud is fired on the rising edge, allowed to follow the rise for BUMP_RISE_S
# to catch the hit's real size, and then decays on its own clock whatever the
# spring does next - the same shape as the kerb thump, just lighter.
BUMP_RISE_S = 0.05
BUMP_DECAY_S = 0.09


class BumpPulse:
    """Turns a compression trace into a single decaying thud per event."""

    def __init__(self) -> None:
        self._level = 0.0
        self._age: float | None = None      # seconds since the edge, or None
        self._armed = True                  # re-arms once compression clears

    def update(self, compression: float, dt: float) -> float:
        self._level *= float(np.exp(-dt / BUMP_DECAY_S))
        if compression <= 0.0:
            self._armed, self._age = True, None
            return self._level
        if self._armed:
            self._armed, self._age = False, 0.0
        if self._age is not None:
            if self._age <= BUMP_RISE_S:
                self._level = max(self._level, bump_level(compression))
            self._age += dt
        return self._level
KERB_THUMP_FULL_MS = 0.30     # suspension velocity at which it maxes out
KERB_THUMP_DECAY_S = 0.12

# **The kerb the surface channel cannot see.**
#
# A sausage kerb clipped at speed is under the wheel for less than one 60 Hz
# frame, so the per-wheel surface char can miss it entirely - and one mounted
# behind a ripple strip is a C-to-C non-edge, which the tarmac-only guard on
# the strike above rejects on purpose. Reported from the seat: "ripple strips
# feel great but when I go over a sausage at speed I feel nothing."
#
# The suspension is the witness the surface char is not: the contact is
# sub-frame but the spring stays compressed for frames afterwards, so the
# height channel carries a step the surface channel never saw. Measured over
# 8 stored laps (246,097 wheel-frames on tarmac, 9,221 touching kerb),
# per-wheel compression in one frame, as a velocity:
#
#     tarmac        p99 0.17 m/s   p99.9 0.53   p99.99 1.08   max 1.44
#     riding a kerb p50 0.08       p90 0.59     p99 1.39
#     the silent hits the report was about: 1.5 to 3.4, almost all C-to-C
#     with no edge, recurring at the same lap positions across laps
#
# Onset sits above the kerb-riding p99 so hammering a ripple strip stays the
# texture and edge-thump it already is; full scale is the biggest hit
# actually recorded. Worst wheel, not the average - a one-wheel clip is the
# event, and averaging it over four wheels is how it was being lost.
STRIKE_ONSET_MS = 1.5
STRIKE_FULL_MS = 3.2
STRIKE_FLOOR = 0.70           # fires rarely; when it fires it is a hit

# **The strike is a rhythm, not a level.**
#
# Measured at T7, the second Lesmo's inside strip: the sausage fired the
# strike at 0.77 in the very frames the strip's edge thump held the impact
# channel at 0.87-1.00 - and the channel took the max, so the sausage never
# won a single frame. Reported from the seat, twice: "still not feeling the
# sausage strikes." Not an amplitude problem - the strip is also loud, and
# more level on a shared voice cannot separate two events. What nothing else
# in the mix does is double-tap: for a quarter second the strike OWNS the
# channel - full hit, a real gap, a second hit - and the gap punched into
# the strip's barrage is as much of the signature as the taps.
STRIKE_TAP_S = 0.07           # the first hit
STRIKE_GAP_S = 0.08           # the silence that makes it a rhythm
STRIKE_SECOND = 0.85          # the echo hit, which then decays normally
STRIKE_OWN_TAIL_S = 0.15      # how far past the gap it keeps the channel

# **The rear coming round under braking now speaks in the tyre voice, and
# the throb it used to get here is gone.**
#
# The history is worth a paragraph because it ran through three shapes in two
# days. Session 40 read it as "brakes extremely intense" - REAR_UNSTABLE
# riding the brake voice - so it was capped at 0.30-0.55 and chopped into a
# 3.5 Hz throb to separate it from a lock. Session 41 the driver compared the
# result with the throttle-side cue and chose: "traction loss from throttle
# is very intuitive... match the rear traction loss [on braking] to more like
# the throttle traction loss." The replay then settled it structurally: the
# wheel-bias witness behind most of those brake-channel episodes was engine
# braking, not the rear stepping out (two cars, 108 episodes, chassis
# rotation present on 1-3% of the frames - see `vehicle.py` above
# BRAKE_ROTATION_GATE), and every genuine episode was ALREADY being carried
# by the rotation witness on `rear_traction`. So the brake channel reports
# braking, the tyre channel reports the rear - however it let go - and "the
# rear is going" has one voice, one ramp and one rhythm everywhere.

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
# **The ceiling is right, the signal reaching it is not, and the correction
# was built, measured and thrown away. All three of those are the finding.**
#
# 2.20 looked like a Porsche number applied to a fleet: it is exceeded on
# 1.97% of the Shelby's frames at Road Atlanta against 0.16% of the RSR's at
# Monza, twelve times as often. It is not. Replayed across three cars and
# three circuits the p90 of lateral g is 1.45, 1.53, 1.53, 1.69 and 1.68 -
# stable to within 15% of itself - and the spread is CIRCUIT rather than car:
# Monza's median is 0.21 g against 0.62 at Spa and Road Atlanta, because Monza
# is straights. "1.2 g is 1.2 g in every corner and every car" survived its
# own test. The ceiling stays.
#
# **The signal defect is real.** `speed x yaw rate` is the path's centripetal
# acceleration only while sideslip is small; sideways, the chassis turns
# faster than its path and the number leaves the physics - 17.8 g at Road
# Atlanta, on a road car. Measured against a path-derived figure, **79% of the
# Road Atlanta frames that reach this ceiling are below 2.2 g on the path
# measure** (Spa 64%, Monza 67%). The ceiling is being reached by artefact.
#
# **And it does not reach the driver, because the mixer already fixed it.**
# `chassis_load` is STATE, so it ducks under `rear_traction`, which is
# CRITICAL and at full level during exactly those frames. Driving the real
# gain chain over a spin: the background duck is already pinned at its 0.180
# floor and the "full scale" load cue arrives at the piston at **0.0357 -
# below the whole-lap median of 0.0527**. The priority classes had done the
# job before anything was added.
#
# **What was tried, and what it cost.** Fading the load by sideslip ANGLE over
# `BETA_ONSET_DEG..BETA_FULL_DEG`. Scored against the path-derived figure it
# is worse than doing nothing on all four datasets - Road Atlanta MAE 0.0656
# against 0.0614, correlation 0.901 against 0.926 - because the angle is the
# wrong variable. The error in `speed x yaw` is `speed x beta_RATE`: at a
# steady drift with constant sideslip, `speed x yaw` is exactly right and
# needs no correction, and those are precisely the frames the angle taper
# mutes. At Spa it attenuated 4.25% of the lap by 23-100% while the car was
# pulling a median 1.69 g **by the path measure too** - the driver's best
# cornering, muted.
#
# `beta_rate` is on the state and is the error term exactly. It is not used
# here either, because `speed x (yaw - beta_rate)` IS the path measure
# algebraically, so keying on it is not a correction to this signal but a
# substitution of the other one - and that one's problem is outliers (max 28.9
# with a 3-frame stencil), not bias. Its body is fine: Road Atlanta p50/p90
# 0.655/1.611 against 0.668/1.692 here, with a much better tail.
#
# So: if this is ever revisited, the question is not "how do I taper" but
# "is a smoothed path-derived lateral g worth its outliers", and the answer
# has to beat doing nothing on MAE against ordinary cornering, which the
# obvious fix did not.
# **A rear lock throbs, and that is how one piston says two things.**
#
# The brake voice already spends its three discriminable axes on severity:
# amplitude, and an AM rate riding the same number, and a carrier pitch that
# is perceptually inert here anyway - `transducer` measured that at a 40-100 Hz
# carrier "44 Hz and 52 Hz feel like the same thing at different strengths".
# There is no band left to give the rear either: 28-66 Hz is fully allocated,
# 80-115 sits inside or beside `rear_traction`, and 66-80 crosses the measured
# null at 70.
#
# What is unspent is a gesture BELOW the AM band. `AM_RANGE_HZ` starts at 5.0
# and `EffectSpec` records why - under 5 Hz "the pulses are separate events" -
# so 3.5 Hz cannot be heard as a slower severity rate. It is a different kind
# of thing, not a different amount of the same thing.
#
# **The driver has already learned this gesture.** It was built once for
# REAR_UNSTABLE and retired - but retired because the WITNESS was wrong (97-99%
# engine braking), not because the signature failed to separate. It meant
# "rear, under braking" then and it means that now.
#
# **Gated to a floor, and the floor is what keeps the rhythm inside this
# voice.** Measured by driving the real `HapticMix`: a gate that dips below
# `synth.ARBITRATE_ABOVE` re-decides arbitration twice per cycle, so the
# throb stops being a property of the brake cue and becomes a 3.5 Hz rhythm on
# `rear_traction` (6.9 dB, antiphase) and a 6.5 dB breathing of the road bed -
# which is precisely the fault `DUCK_GATE` was added to cure, described from
# the seat as "a constant on and off hum I could not work out". Net swing came
# out at 5.9 dB where the brake voice itself was doing 12, because the other
# voices filled the gap it was trying to make.
#
# So the dip is clamped to stay above the arbitration threshold whenever the
# cue itself is above it. Gating to silence would be worse again: level and
# carrier pitch both ride the shaped intensity.
REAR_THROB_HZ = 3.5
REAR_THROB_FLOOR = 0.25
# A hair above `ARBITRATE_ABOVE`, so a cue sitting above the threshold never
# crosses back down through it mid-gesture.
REAR_THROB_GUARD = synth.ARBITRATE_ABOVE * 1.05
# **Most rear locks are too short to carry a rhythm, and that is written down
# rather than left to be found from the seat.** Phase starts at full, so the
# first 143 ms of an episode is ungated. Measured over his stored laps, gates
# actually delivered during a lock: Shelby/Yas ABS Off 57% of episodes get two
# or more (median episode 558 ms), but RSR Monza 41%, 992 Spa 25%. Outside the
# ABS-off Shelby the usual delivery is ONE dip, which is a dropout rather than
# a rhythm. There is no headroom to fix that by rate - 3.5 Hz is already
# between "separate events" and `AM_RANGE_HZ[0]` = 5.0 - so it is a known
# limit of the gesture, and the cue's amplitude still carries the severity.
REAR_THROB_TAIL_S = 0.25

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
        # Read once, from the same selector as the mix profile and the duck, so
        # the three cannot disagree about which tune is running.
        self._lift_bumps = synth.rig_revision() in ("C", "D", "E", "F")
        self._bump = BumpPulse()
        self._out = np.zeros(len(self.NAMES) + len(self.MODIFIERS),
                             dtype=np.float32)
        self._prev_suspension: tuple[float, ...] | None = None
        self._prev_gear: int | None = None
        self._prev_velocity: tuple[float, float, float] | None = None
        self._gear_pulse = 0.0
        self._impact_pulse = 0.0
        self._kerb_pulse = 0.0
        self._strike_t: float | None = None
        self._strike_size = 0.0
        self._limiter_pulse = 0.0
        self._prev_limiter = False
        self._throb_t = 0.0
        self._throb_phase = 0.0
        # The road bed's scale, learned. Same tracker the traction reference
        # uses, and for the same reason: one float of state and no history.
        #
        # **Seeded from the shipped pair, never from the first frame seen.**
        # The traction reference next door was seeded by its own first sample
        # and a pit-exit driveline snatch put a whole session's cue on the
        # floor; this is the identical estimator reading a channel taken at the
        # identical moment, and it would have inherited the identical fault. A
        # high seed is the expensive one here - the downward step is 2e-5, so a
        # tracker seeded at 0.60 needs minutes to come back, and both clamps in
        # `_texture_scale` engage while it does.
        self._tarmac_p50 = vehicle._Quantile(
            0.50, TEXTURE_LEARN_STEP, initial=_seed_at(TEXTURE_AT_TARMAC_P50))
        self._tarmac_p90 = vehicle._Quantile(
            0.90, TEXTURE_LEARN_STEP, initial=_seed_at(TEXTURE_AT_TARMAC_P90))
        # **Seeded at the tarmac top, so before it has settled the shape is
        # exactly what it was.** A kerb ceiling below the tarmac knee would
        # inverted the ramp, so `_shape` refuses one; seeding here means it is
        # refused by arithmetic rather than by a special case.
        # **No settle gate.** It is seeded at `TEXTURE_FULL_MS`, so it starts
        # exactly where the unraised ceiling sits and walks from there, and
        # `_shape` refuses any ceiling at or below the tarmac top - so there is
        # no discontinuity for a gate to hide. `_shape` waits for one kerb
        # frame, which is the honest bar: the ceiling should be measured, not
        # assumed.
        #
        # The gate did real harm. Kerb frames are 2.2-2.8% of a Daytona lap, so
        # 400 of them arrive four to five MINUTES in - three or four laps of a
        # five-lap session - and one session on file reached only 323 and never
        # settled at all. For all of that time the bed ran on the unraised
        # line, which is the saturation this was written to fix, and the
        # complaint that prompted it was about the first lap.
        self._kerb_p90 = vehicle._Quantile(
            0.90, KERB_LEARN_STEP, initial=TEXTURE_FULL_MS)
        self.state = vehicle.VehicleState()

    def set_abs(self, setting: str | None) -> None:
        """The assist declared on the event, on its way to the brake model."""
        self.model.set_abs(setting)

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
        self._bump = BumpPulse()
        self._strike_t = None
        self._strike_size = 0.0
        self._limiter_pulse = 0.0
        self._prev_limiter = False
        self._spike_speed = 0.0
        self._throb_t = 0.0
        self._throb_phase = 0.0
        # **The road scale is deliberately NOT reset here.** `reset()` runs on
        # a pause and on every haptics restart, including a watchdog recovery,
        # and neither the car nor the circuit changes across either. It is a
        # property of the two, like `VehicleModel._car_id`, and clearing it on
        # a pause would throw away a circuit's worth of road for nothing.
        #
        # It is dropped on a car change, in `update` below - and NOT on a
        # circuit change, because there is no track ID in the feed to drop it
        # on (CLAUDE.md §3.3). The same car moved to another circuit therefore
        # carries the old road across, and walks to the new one in about 500
        # samples because both trackers keep adapting. Benign, and named here
        # rather than left to be discovered.
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
        if self.model.car_changed:
            # The model has already dropped its own references; this is the
            # per-car state that lives on this side of the boundary. Back to
            # the seeds rather than to nothing, for the reason in `__init__`.
            self._tarmac_p50.reset(_seed_at(TEXTURE_AT_TARMAC_P50))
            self._tarmac_p90.reset(_seed_at(TEXTURE_AT_TARMAC_P90))
            self._kerb_p90.reset(TEXTURE_FULL_MS)
            # And the differenced channels, which is what `reset`'s own
            # docstring is about: ride heights differ between cars by tens of
            # millimetres, and 0.03 m across one frame is 1.8 m/s - past
            # STRIKE_ONSET_MS, so the new car arrives on a suspension strike.
            self._prev_suspension = None
            self._prev_velocity = None

        out[0] = self._engine(packet)
        out[1] = self._road(packet, state, dt)
        # As computed in `vehicle._braking`, rendered as computed. The rear
        # coming round under braking is not on this channel any more - the
        # rotation witness carries it into `traction_level` below, in the
        # same vocabulary as throttle traction loss.
        out[2] = self._brake_throb(state, state.brake_level, dt)
        out[3] = max(self._driveline(packet, state, dt),
                     self._limiter(state, dt))
        strike, strike_owns = self._suspension_strike(state, dt)
        compression = (self._bump.update(state.compression, dt)
                       if self._lift_bumps else state.compression)
        others = max(self._impact(packet, dt), self._kerb_thump(state, dt),
                     state.landed, compression)
        out[4] = strike if strike_owns else max(others, strike)
        out[5] = self._chassis_load(state)
        out[6] = state.traction_level
        out[7] = state.unload
        return out

    # ------------------------------------------------------------- immersion

    # Suspension velocity this frame, kept for the kerb grading below.
    _texture_speed = 0.0
    # Worst single wheel's compression velocity this frame, for the strike.
    _spike_speed = 0.0

    def _texture_scale(self) -> tuple[float, float]:
        """Where the road bed's ramp starts and tops out, for this car.

        A line through two learned quantiles of tarmac texture speed, placed so
        that the median lands at `TEXTURE_AT_TARMAC_P50` of full scale and the
        p90 at `TEXTURE_AT_TARMAC_P90` - the proportions his hand-tuned pair
        already had. Both trackers are seeded at that pair, so at frame 0 this
        returns it exactly and then walks; there is nothing to gate.
        """
        median, ninety = self._tarmac_p50.value, self._tarmac_p90.value
        if median is None or ninety is None:
            return TEXTURE_ONSET_MS, TEXTURE_FULL_MS
        span = ninety - median
        if span <= 0.0:
            return TEXTURE_ONSET_MS, TEXTURE_FULL_MS
        width = span / (TEXTURE_AT_TARMAC_P90 - TEXTURE_AT_TARMAC_P50)
        width = min(max(width, TEXTURE_FULL_MIN_MS), TEXTURE_FULL_MAX_MS)
        # Never below zero: the onset is a suspension speed, and a negative one
        # would make a stationary car read as textured road.
        onset = max(0.0, median - TEXTURE_AT_TARMAC_P50 * width)
        return onset, onset + width

    def _shape(self, speed: float, onset: float, full: float) -> float:
        """The ramp, with the top segment stretched to reach a real kerb.

        **Below the tarmac p90 nothing changes, and that is deliberate.** The
        proportions in `_texture_scale` are the ones he tuned by hand over
        eight days, and moving the ceiling alone would drag tarmac down the
        range with it - quieter road as the price of louder kerbs, which is
        not what was asked for. So the curve has a knee at the tarmac p90:
        below it the line is exactly the line it always was, and above it a
        second segment carries `TEXTURE_AT_TARMAC_P90` up to 1.0 at the
        learned kerb ceiling instead of at the tarmac top.

        On the Daytona measurement that takes the median kerb from 0.61 to
        0.49 - slightly softer - while taking the share of kerb frames pinned
        at full scale from 30.5% to about a tenth. The kerb stops being one
        flat maximum and becomes a range again, which is the complaint.
        """
        knee = onset + TEXTURE_AT_TARMAC_P90 * (full - onset)
        # **Read once a kerb has actually been touched, not once 400 have.**
        # Requiring 400 kerb frames put the ceiling four to five minutes into a
        # session on a circuit where kerbs are 2.2-2.8% of a lap, and a short
        # session never reached it at all.
        #
        # **`samples` is a gate against an UNTOUCHED prior, not a claim that
        # one frame measures anything.** At `samples == 1` the value is still
        # the seed to within one step of 2.25e-3, and the guard below refuses
        # any ceiling at or under the tarmac top - so a single frame, good or
        # bad, changes nothing. In practice the ceiling starts to raise the top
        # after roughly 25 net upward kerb frames. One bad reading cannot pin
        # it either: the tracker steps rather than jumps, and the raise-only
        # guard makes a wrong ceiling recoverable rather than permanent.
        ceiling = self._kerb_p90.value if self._kerb_p90.samples else None
        # **The ceiling may only ever RAISE the top, never lower it.** A
        # circuit whose kerbs are gentler than its road - Spa learned 0.107
        # against a tarmac-derived top of 0.127 - would otherwise get a
        # steeper second segment than the line it replaced and pin EARLIER,
        # turning a fix for saturation into a cause of it. Bounded below by
        # the original top, this change can only add headroom.
        if ceiling is not None and ceiling <= full:
            ceiling = None
        if ceiling is None or ceiling <= knee or speed <= knee:
            # Not yet learned, gentler than the road, or below the knee: the
            # original line, unchanged.
            return _ramp(speed, onset, full)
        above = (speed - knee) / (ceiling - knee)
        return min(1.0, TEXTURE_AT_TARMAC_P90
                   + (1.0 - TEXTURE_AT_TARMAC_P90) * above)

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
            self._spike_speed = 0.0
            return 0.0
        speed = sum(abs(h - q) for h, q in zip(heights, previous)) / (4.0 * dt)
        self._texture_speed = speed
        # Larger is more compressed, so a positive step is the wheel taking a
        # hit. Worst wheel, kept for the suspension strike below.
        self._spike_speed = max(h - q for h, q in zip(heights, previous)) / dt

        # Teach the scale what this car on this road actually does, from
        # tarmac only and above a crawl.
        #
        # Fed before it is read, which is the opposite order to the traction
        # reference next door - and deliberately, because the two are doing
        # different jobs. That reference is read first so an EVENT cannot
        # contribute to the measurement of what normal is. This is a bed with
        # no events in it, and one frame moves the estimate by at most 1.8e-4.
        # `p.surface_types` is in the condition and not assumed: it is absent
        # on packet formats `A` and `B`, and `vehicle._surfaces` then leaves
        # `on_kerb` and `off_surface` at their defaults of False. Absent is
        # missing, not tarmac - without this the whole of a kerb teaches the
        # scale on the fallback format, and the scale climbs until kerbs are
        # ordinary, which is the one thing it exists to prevent.
        if (p.surface_types and not s.on_kerb and not s.off_surface
                and p.speed_kmh >= TEXTURE_LEARN_MIN_KPH):
            self._tarmac_p50.update(speed)
            self._tarmac_p90.update(speed)
        # **And teach the ceiling from kerbs, which is the other half.** Same
        # guard in reverse: only frames actually ON a kerb, and never off the
        # racing surface, so grass and a spin cannot raise the top either.
        if (p.surface_types and s.on_kerb and not s.off_surface
                and p.speed_kmh >= TEXTURE_LEARN_MIN_KPH):
            self._kerb_p90.update(speed)
        onset, full = self._texture_scale()
        texture = self._shape(speed, onset, full)

        # **The speed scaling belongs to the texture, not to the surface.**
        #
        # A bump at 40 km/h genuinely is not the bump it is at 130 - the
        # suspension is moving less. But a kerb is a kerb: the wheel is on a
        # different surface, and scaling that down because the corner happens
        # to be slow is what made ripple strips feel soft in the hairpins,
        # which is where kerbs matter most.
        texture *= min(1.0, p.speed_kmh / TEXTURE_FULL_SPEED_KPH)
        # The boosts carry their own, gentler speed gate - see
        # SURFACE_BOOST_ONSET_KPH: full by 45 km/h so slow-corner kerbs keep
        # their voice, nothing at a crawl so a car limping back from a spin
        # does not rumble while barely moving.
        moving = _ramp(p.speed_kmh, SURFACE_BOOST_ONSET_KPH,
                       SURFACE_BOOST_FULL_KPH)
        if s.on_kerb:
            texture = min(1.0, texture + KERB_BOOST * moving)
        elif s.off_surface:
            texture = min(1.0, texture + OFF_SURFACE_BOOST * moving)
        return texture

    def _brake_throb(self, s: vehicle.VehicleState, level: float,
                     dt: float) -> float:
        """A rear lock, rendered as a rhythm rather than as more level.

        Shaped here on the telemetry thread and not in the mixer, exactly like
        the suspension strike's double tap: the mix knows nothing about it, so
        this needs no new voice, no new band and no new `EffectSpec` field -
        and arbitration, which scales amplitude, cannot scale a rhythm away.
        """
        rear = s.brake_state == vehicle.BRAKE_LOCKED_REAR
        if rear:
            self._throb_t = REAR_THROB_TAIL_S
        elif s.brake_state in (vehicle.BRAKE_LOCKED, vehicle.BRAKE_INCIPIENT):
            # **The tail does not outlive its own subject.** It exists so a
            # rear flickering across its floor does not alternate rhythms - but
            # the front latch outlasts the rear on most episodes, so a tail
            # that kept gating whatever came next spent real time cutting a
            # genuine FRONT lock to a quarter: measured at 2.83 s over 24 laps,
            # removing up to 0.568 of level from a cue that had reverted to
            # meaning the other axle.
            self._throb_t = 0.0
        if self._throb_t <= 0.0:
            self._throb_phase = 0.0
            return level
        self._throb_t -= dt
        self._throb_phase = (self._throb_phase + REAR_THROB_HZ * dt) % 1.0
        if self._throb_phase < 0.5:
            return level
        return max(level * REAR_THROB_FLOOR, min(level, REAR_THROB_GUARD))

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

        **Deliberately not corrected for sideslip**, and the attempt is worth
        recording because the defect it chased is real. See the block above
        LAT_G_ONSET.
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
            hit = KERB_THUMP_FLOOR + (1.0 - KERB_THUMP_FLOOR) * _ramp(
                self._texture_speed, 0.0, KERB_THUMP_FULL_MS)
            self._kerb_pulse = max(self._kerb_pulse, hit)
        return self._kerb_pulse

    def _suspension_strike(self, s: vehicle.VehicleState,
                           dt: float) -> tuple[float, bool]:
        """A sausage kerb, read off the spring rather than the surface char.

        Fires on the worst wheel's single-frame compression velocity, so it
        works when the contact was too brief for the surface channel to see -
        the case the edge-triggered thump above structurally cannot catch.
        Off the racing surface it holds its peace: bouncing across grass is
        exactly this signature and is not an event worth reporting.

        Returns the level and whether the strike currently OWNS the impact
        channel. While it owns it, the caller renders this envelope INSTEAD
        of the max of everything else - the double-tap's gap has to actually
        reach the piston, and against a ripple strip's edge thumps a max()
        fills the gap straight back in.
        """
        if self._strike_t is not None:
            self._strike_t += dt
        firing = not s.off_surface and self._spike_speed >= STRIKE_ONSET_MS
        if firing and self._strike_t is None:
            self._strike_t = 0.0
            self._strike_size = STRIKE_FLOOR + (1.0 - STRIKE_FLOOR) * _ramp(
                self._spike_speed, STRIKE_ONSET_MS, STRIKE_FULL_MS)
        t = self._strike_t
        if t is None:
            return 0.0, False
        if t < STRIKE_TAP_S:
            level = self._strike_size
        elif t < STRIKE_TAP_S + STRIKE_GAP_S:
            level = 0.0
        else:
            level = self._strike_size * STRIKE_SECOND * float(
                np.exp(-(t - STRIKE_TAP_S - STRIKE_GAP_S) / IMPACT_DECAY_S))
            if level < 0.02:
                self._strike_t = None
                return 0.0, False
        owns = t < STRIKE_TAP_S + STRIKE_GAP_S + STRIKE_OWN_TAIL_S
        return level, owns

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
                # Per band, so a reference stuck below the stream is visible
                # rather than silent. Thousands here is the trapdoor.
                "reference_blanked": self.model._slip_ref.withheld,
                "witness": s.reasons.get("traction"),
            },
            "brake": {
                "state": s.brake_state, "level": round(s.brake_level, 3),
                # **"the axle that OWNS the channel", not "the worse axle".**
                # Since the rear takes priority this reads "rear" on about a
                # quarter of both-locked frames where `front_lock` in this same
                # dict is the larger number. That is not a contradiction, it is
                # the ownership rule - but it changed meaning, so it says so.
                "axle": s.brake_axle,
                "front_lock": round(s.front_lock, 4),
                "rear_lock": round(s.rear_lock, 4),
                "lock_threshold": round(s.lock_threshold, 4),
                # `brake.level` above is the level BEFORE the throb gate, so a
                # log read months later can tell an ungated cue from a gated
                # one rather than inferring it from a number that moved.
                "throbbing": self._throb_t > 0.0,
                # Which assist the scale was measured on, against which one is
                # fitted. A borrowed scale is visible in a log an hour later
                # instead of being inferred from how the seat behaved.
                "abs": self.model._abs,
                "confidence": s.brake_confidence,
                "anchors": self.model._anchors.source,
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
