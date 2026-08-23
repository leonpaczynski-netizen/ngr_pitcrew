"""What the car is doing, as against what the packet says.

`effects.py` used to read GT7's channels and map them almost directly onto
amplitudes. That is the fault this module exists to correct, and the reason is
one measurement: **the rear axle of the Porsche RSR reports a slip ratio of
1.032 across a lap, and the old wheelspin threshold was 1.04.** Measured over
278,034 frames of his own laps, the rear axle read at least 2.3% faster than
the road on 99% of throttle-on frames and never once read below it. The effect
meant to tell him the rear was sliding was, for most of every lap, an
amplitude-modulated readout of how hard he was accelerating.

**And the first explanation offered for that was wrong, which is worth
recording because it changed the design.** The obvious reading is a rolling-
radius artefact: GT7 reports the unloaded tyre radius, so surface speed comes
out systematically high. It is not that. Split by throttle:

    throttle    0-5%    5-15%   15-30%  30-50%  50-70%  70-90%
    median      0.0002  0.0064  0.0180  0.0302  0.0442  0.0596

At zero throttle the rear axle reads **exactly what the front reads**. The
offset is not a constant to subtract; it is genuine driven-wheel slip, and it
is proportional to the torque going through the axle. A tyre putting power
down runs a few percent of slip, and that is the tyre working properly.

So the reference is not a number, it is a curve: what this axle reads while
driving normally *at this much throttle*. Wheelspin is what stands above it.
Fitting a physical model instead - expected slip proportional to longitudinal
acceleration - was tried and is worse (r=0.63 raw, falling to 0.42 once the
acceleration is smoothed, which says most of the raw correlation was the two
signals sharing their differencing noise). Four throttle-indexed quantile
trackers beat it and need no vehicle parameters at all.

Nothing here is a measurement. GT7 broadcasts no slip channel, no grip
channel, no tyre force, no ABS flag and no sideslip. Everything below is a
model with a threshold, and CLAUDE.md 4 rule 5 requires those to be named as
derived and to state what they were fitted against. Every constant in this
file carries the percentile of his own driving that it sits at.

Three ideas run through all of it.

**A reference, not a constant.** Anything compared against "rolling true",
"normal ride height" or "how hard the ABS regulates" learns that value from
the car it is in, slowly, while the car is demonstrably doing nothing
interesting. A threshold measured on a Porsche is a threshold about a
Porsche; a threshold measured against a learned baseline is a threshold about
a car. This is what lets the same tactile vocabulary mean the same thing in a
Gr.4 hatchback and a Gr.1 prototype without a per-car table.

**Two witnesses where there are two.** The rear letting go shows up in wheel
speed when it is driven and in the chassis heading when it is not. Lift-off
and trail-braking oversteer produce no wheelspin at all, so a wheel-speed
model is blind to exactly the case that hurts him most. Both are computed and
the driver is told the larger - one meaning, two independent pieces of
evidence, which is also why they share a single tactile cue rather than
getting one each.

**A state that cannot be trusted says so.** Every state carries a confidence,
and a cue built on an unconfirmed model is withheld or attenuated rather than
presented as fact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from pitcrew.telemetry.packet import GT7Packet

FRAME_S = 1.0 / 60.0

# --------------------------------------------------------------------- gates
#
# Below this the wheel-speed ratio divides by a speed that means nothing and
# the heading of a velocity vector is dominated by noise. 5 m/s is walking out
# of the pit box; `recorder._slip_ratios` uses 2.0 for the same reason and can
# afford to, because it is not driving a piston.
MIN_SPEED_MS = 5.0
# A pedal fraction, 0-1. `GT7Packet.throttle` and `.brake` divide the raw byte
# by 255, so these are NOT percentages - the mistake that once halved
# wheelspin and made lock-up unreachable.
PEDAL_ON = 0.02

# --------------------------------------------------------- rolling reference
#
# **The most consequential thing in this module, and it is learned per car.**
#
# Expected driven-axle slip at a given throttle opening, tracked in four bands
# and interpolated between their centres. Four is enough to follow the curve in
# the table above, and few enough that every band has settled inside a couple
# of laps; more bands means more of them still learning when he goes out.
#
# Each band tracks a low QUANTILE rather than a mean, and the difference
# matters. A mean learns the wheelspin: leave it running through a session and
# the reference climbs to meet whatever the rear is doing, and the effect goes
# quiet exactly where it should be loudest. A quantile tracker steps up by
# `q * step` when it is under the sample and down by `(1-q) * step` when it is
# over, so it converges on the 35th percentile of that band and an excursion
# above it moves it almost not at all.
#
# Measured on his laps, with each band referenced to its own 35th percentile:
#
#     band       0-25%    25-50%   50-75%   75-100%
#     reference  0.0047   0.0241   0.0418   0.0321
#     p90 above  0.0174   0.0387   0.0524   0.0283
#     p99 above  0.0481   0.1050   0.1721   0.0695
#
# The band references differ by a factor of nine and the excess above them does
# not, which is the whole argument for indexing on throttle.
REFERENCE_QUANTILE = 0.35
REFERENCE_STEP = 2.0e-4
REFERENCE_BANDS = 4
# Sampled everywhere the car is driving forward off the brakes, including at
# the limit: the quantile is what makes that safe, and restricting sampling to
# gentle driving is what made an earlier version learn 0.008 for a band whose
# true value is 0.032. A reference learned only in conditions the cue is never
# used in is not a reference.
REFERENCE_LAT_G_MAX = 3.0
# Until a band has this many samples it borrows the nearest settled band, and
# until none has settled the traction state is UNKNOWN rather than a number
# built on nothing. 240 frames is four seconds; the model is reset between
# sessions, not between laps.
REFERENCE_SETTLE_FRAMES = 240
# **Where a band starts, so that no band ever starts from one frame.**
# Measured, sessions 65 and 66: the first full-throttle sample
# of a session is taken at pit exit, ~18 km/h in first gear, where the
# driveline snatches and the rear axle reads 0.90 one frame and 1.25 the next.
# `_Quantile` seeds from its first sample, so the band took -0.099 as its
# estimate of normal. Every honest sample is then far above it, so the caller
# withholds every rise; nothing is ever below it, so it never steps down. A
# one-way trapdoor, and the band stayed at -0.075 for the whole session while
# reporting itself settled - which is EXCESSIVE_WHEELSPIN on 94% of frames at
# 209-247 km/h, and the beds ducked 41% underneath it.
#
# **The fix is at the seed, not at the symptom.** A tracker that begins from
# its own first sample has no defence against that sample being nonsense, and
# at pit exit it always is. So each band now STARTS from the measured table
# above rather than from whatever it is shown first - the same thing the ABS
# plateau already does with `initial=LOCK_FLOOR / PLATEAU_MARGIN`.
#
# One car's numbers, and they are a starting point rather than an answer: the
# band is unsettled at birth, so it learns freely until it has 240 samples of
# this car, and downward steps are never withheld at all. Across the three
# cars on file the true band-3 value spans 0.013 to 0.060, which brackets the
# 0.0321 seed on both sides - so every one of them walks to its own value
# rather than being trapped on the way there.
REFERENCE_PRIOR = (0.0047, 0.0241, 0.0418, 0.0321)
# **And no automatic release, deliberately.** Two were tried against the same
# session and both were worse than the seed alone.
#
# Discarding a long-blanked band re-seeds it from the next sample - and that
# sample is taken DURING whatever caused the blanking, so the reference lands
# exactly on the event and reports GRIPPED through a slide. That is a silent
# false negative on a CRITICAL cue, traded for the old loud false positive,
# and it is the wrong direction to be wrong in. Granting one step per timeout
# instead is safe and useless: 0.088 at `q * step` is 1257 steps, which at any
# threshold worth having is hours.
#
# What is left is the honest position. The trapdoor needed a reference sitting
# further from the stream than SLIP_USEFUL on EVERY frame, and only a
# single-sample seed could put it there - session 65 sat 0.088 out, where the
# whole distribution of ordinary driving is inside 0.030. Seeded from the
# table, a band walks; it is never dropped somewhere it cannot walk back from.
# So `withheld` is kept and published, and nothing acts on it: a band that
# somehow does stick is then visible in the explainer for the length of one
# session rather than silent, which is what the shift beep already does with a
# gearbox nobody has measured.

# **Rear traction, in slip above the learned reference.**
#
# Measured distribution of that excess, pooled over all four bands:
#
#     p50 0.0047   p75 0.0162   p90 0.0286   p95 0.0359   p99 0.0738
#
# and how often each threshold fires, in episodes rather than frames, which is
# the number that decides whether a cue is information or wallpaper:
#
#     >0.012   27% of on-power frames, 2585 episodes, median 117 ms
#     >0.030    4.0%,                   957 episodes, median  50 ms
#     >0.060    1.2%,                   287 episodes, median  67 ms
#     >0.120    0.4%,                    66 episodes, median 117 ms
#
# Full scale sits at 0.15; the 99.9th percentile of 0.254 is reached only in a
# genuine slide, so the top of the range keeps resolution where the driver
# needs it and does not saturate the moment the car steps out.
SLIP_ONSET = 0.012
SLIP_FULL = 0.150
# Where the named states sit on that ramp. Hysteresis is applied on release so
# a state does not chatter at its own boundary - see `_Latch`.
SLIP_APPROACHING = 0.012      # p72 pooled: the axle is working
SLIP_USEFUL = 0.030           # p90
SLIP_EXCESSIVE = 0.060        # p98.5
SLIP_SEVERE = 0.120           # p99.6
# A state must survive this long before it is believed, and stays this long
# after it stops. Two frames is 33 ms: enough to reject a single-frame
# driveline spike, short enough that the cue is not late.
CONFIRM_FRAMES = 2
HOLD_S = 0.10
# **Release, not attack.** A critical level rises the instant the evidence
# does - anything else is latency on the one cue that cannot afford it - and
# falls over this long. Measured: the traction excess crosses its onset in
# 6445 episodes of which the median is a single frame, so without a release
# the bottom of the range is a 17 ms flicker, which on a 150 W piston is a
# click rather than a cue. 80 ms is long enough to join a flicker into a
# sensation and short enough that the cue still stops when the car grips.
LEVEL_RELEASE_S = 0.08

# A gearshift shocks the driveline and the wheel rate steps with it. Measured
# on his laps the step is brief; ignoring the frames just after a shift removes
# it without hiding anything real, because a rear that is genuinely spinning is
# still spinning 50 ms later.
SHIFT_BLIND_S = 0.05

# ------------------------------------------------------------------ braking
#
# **GT7's ABS regulates, it does not pulse, and that changes everything.**
#
# The lock detector this replaces carried a 220 ms attack, added because
# "ABS is way too strong" was reported from the seat and the belief was that
# ABS pulses the brakes at 10-15 Hz, so a slow attack could not climb on it.
# Measured over 40 laps, front axle slip under braking:
#
#     p50 0.070   p75 0.135   p90 0.147   p95 0.152   p99 0.171   max 0.258
#
# and the time it spends there: **above 0.10 for a median of 1292 ms at a
# time, 204 separate times.** That is not a pulse train. It is a regulator
# holding the front axle at its slip peak, and a 220 ms attack climbs it
# perfectly. The effect was reporting the ABS for over a second in every
# braking zone, exactly as reported from the seat, and the fix that was meant
# to stop it could not have.
#
# Two things follow. First, the threshold has to sit ABOVE the regulated
# plateau rather than below it - at 0.15 the runs collapse from 1292 ms to
# 50 ms, which is the wheel actually breaking away. Second, the 220 ms attack
# is then unnecessary, and removing it takes a fifth of a second out of the
# most time-critical cue in the system.
#
# And the plateau itself is information. A driver who can feel where the ABS
# starts working can brake to it deliberately. So the regulated band is not
# discarded, it becomes its own state - AT_LIMIT - at a modest level, with
# LOCKED reserved for what happens above it.
BRAKE_STABLE = 0.055          # p20 of braking frames: the axle is just working
BRAKE_AT_LIMIT = 0.075        # p55: the regulator has started
# **Where the tyre actually stops giving more, measured rather than assumed.**
#
# Reported from the seat: the braking cue is "too heavy and loud... GT7 doesn't
# punish the abuse of ABS as far as I am aware". Worth settling from his own
# laps rather than from a forum, and the physical test is direct - if GT7
# models a slip-versus-force curve with a peak, deceleration falls once slip
# goes past it.
#
# Straight-line braking (pedal above 85%, under 0.35 lateral g), 50-70 m/s,
# where there is enough downforce and enough force demand for the curve to
# show:
#
#     front slip   0.06-0.09   0.09-0.12   0.12-0.15   0.15-0.18
#     median decel   2.022 g     2.192 g     2.022 g     1.920 g
#     frames           334        1994        5794         903
#
# **GT7 punishes it by 12.4%.** There is a peak at about 0.105 and the deepest
# band gives up an eighth of the braking force. And 68% of his heavy-braking
# frames sit past that peak, so the information is worth real time - which is
# exactly why the answer is not to turn the cue down and lose it.
#
# What was wrong is the SHAPE. The cue ramped from 0.075 to the lock threshold
# as one climb, so it was loudest at 0.15 - already past the peak and well
# into the region where he is losing brake force - and it was a full pulsing
# judder for about eight seconds a lap. It told him "you are braking" loudly
# instead of "you have gone past the best of it".
#
# So the ramp is anchored here instead. At and below the optimum the cue is a
# light presence: the brakes are working, nothing to correct. Above it the
# level and the pulse rate climb together, and that climb is the message.
#
# Below 50 m/s the trend reverses (1.741 g at 0.09-0.12 against 1.869 at
# 0.15-0.18), which is not evidence that deep slip helps at low speed so much
# as that the deepest slip there happens at the end of a zone with the car
# already slow. The high-speed band is where the physics is clean, and it is
# also where the lap time is.
BRAKE_OPTIMUM = 0.105
# The floor under the lock threshold. Above every plateau measured on this car
# and below the 0.258 maximum ever seen.
LOCK_FLOOR = 0.170
LOCK_FULL = 0.260             # the largest excursion in 77 minutes of driving
# **The plateau is learned too**, because it is a property of the assist and
# the car. Tracked as the 85th percentile of the worst axle's slip while the
# brakes are genuinely working: measured, that lands on 0.147, which is the
# top of the regulated band and below the 0.171 the state machine needs.
#
# A peak-follower was tried first and is wrong here. It climbs to the largest
# excursion of the session - 0.258 on these laps - and then multiplies it by
# the margin, which puts the lock threshold above anything the car can produce
# and switches the cue off silently. A quantile cannot do that.
#
# With ABS off there is no plateau and a locking wheel runs toward a slip of
# 1.0; the learned value then stays low and `LOCK_FLOOR` governs. The threshold
# is never allowed below that floor - a learner that can only make the system
# less sensitive is a learner that can switch it off.
PLATEAU_QUANTILE = 0.85
PLATEAU_STEP = 3.0e-4
PLATEAU_MARGIN = 1.15


# Confidence, in the vocabulary the export already uses.
HIGH, MEDIUM, LOW, NONE = "high", "medium", "low", "none"


@dataclass(frozen=True)
class BrakeAnchors:
    """The brake cue's scale, for one assist setting.

    **Keyed by ASSIST and not by car, and that is the whole argument.** The
    genuinely per-car quantity here is the ABS plateau, and it is already
    learned per car at runtime and dropped on a car change. What is left -
    the slip at which the tyre stops giving more braking force, and the slip a
    stopped wheel reads - is tyre and geometry rather than car. A table keyed
    by car would manufacture a "car nobody has measured" hole for numbers that
    are not per-car, and would then need a fallback, which is the thing the
    shift beep's silence exists to forbid.

    The hole that DOES exist is an assist nobody has measured. `source` is
    carried so that a borrowed scale says so in the explainer rather than
    being inferred from behaviour an hour later.
    """

    stable: float
    at_limit: float
    # Where the graded rasp begins, and WHAT IT CLAIMS - which is not the
    # same question on both assists.
    #
    # With a regulator there is a measurable grip peak and the rasp means
    # "past the peak". With ABS off no peak resolves: the deep-slip frames are
    # cornering frames - measured, only 49-54% pass the straight-line gate, at
    # 0.32-0.36 lateral g - so the gate that makes the measurement clean
    # removes the region the peak would be in.
    #
    # **The first attempt rendered silence there, and that was wrong.** It cut
    # the brake cue on his current series from 1.5 audible episodes a lap to
    # 0.6 and put `amp_p99` at exactly 0.0000 - a 62% reduction, shipped to a
    # driver whose standing complaint is that braking feels numb.
    #
    # The fix is to change what is CLAIMED, not to invent a peak. "You are
    # past the grip peak" needs a peak; "you are approaching a lock" does not,
    # and the lock threshold is the one number on this branch that IS
    # measured. So off the regulator the same band grades proximity to the
    # threshold instead, and `rasp_means` carries which claim is being made
    # all the way into the explainer.
    rasp_from: float
    rasp_means: str
    lock_floor: float
    lock_full: float
    plateau_learned: bool
    # Whether the scale was measured on THIS assist, or borrowed from another.
    # On the record rather than inferred from the lookup succeeding: a key
    # existing in a dict is not evidence that anyone measured anything.
    confidence: str
    source: str


# **Re-measured on v1.71, and the peak moved a long way.** The constants above
# are v1.70 numbers and every one of them is kept, because they are the record
# of how this cue was built - but none of them is what the car does now.
#
# Re-derived by the original method (median longitudinal decel binned on
# front-axle lock, straight-line braking only, pedal >85%, lateral g <0.35,
# 50-70 m/s, peak bootstrapped 400x), the grip peak sits at:
#
#     RSR 991,  Monza, v1.70, ABS Weak   0.101   (reproduces the shipped 0.105)
#     RSR 991,  Monza, v1.71, ABS Weak   0.067   5-95% 0.066-0.075
#     992 GT3R, Spa,   v1.71, ABS Weak   0.062   5-95% 0.058-0.063
#
# The first pair is the controlled comparison - same car, same circuit, same
# assist, the version the only change - and a second car at a second circuit
# lands within 0.005 of it. **Their bootstrap intervals do not actually
# overlap** (0.066-0.075 against 0.058-0.063) at a resolution floor of about
# 1%, so this is two nearby per-car peaks rather than one fleet number; 0.065
# is the middle of them and the per-car question is open.
#
# 0.105 is about **p83** of the v1.71 RSR's braking frames - 16.9% still reach
# it, largest ever seen 0.152 - so the ramp was not starved of input. What it
# lost was the span: an onset at 0.105 against a top at 0.152 leaves 0.047 of
# range, and `amp_p99` fell 0.117 to 0.048 across the patch. Starting the ramp
# at the peak restores the span rather than finding new input.
#
# `at_limit` IS the peak, exactly. Its old definition - "the regulator has
# started" - did not survive contact with the measurement: it matches its
# stated percentile on no dataset, including the one it was fitted on. One
# threshold with one meaning, which is where the tyre stops giving more braking
# force, is worth more than two that disagree.
#
# A 0.005 gap was tried first, to stop the state boundary and the ramp onset
# landing on the same float. It was unnecessary - `ramp()` returns 0.0 at
# `value <= onset`, so a frame held exactly at the peak resolves
# deterministically to state AT_LIMIT at level 0.0, which is the shape the
# driver asked for - and it put the threshold below both cars' measured
# intervals to buy nothing.
#
# `stable` is now only a gate on what teaches the plateau, and it is set to
# what it always claimed to be: p20 of braking frames, re-measured.
# `lock_full` is the pooled RACING-SPEED maximum, and the speed gate is the
# point. Taken ungated it lands on a wheel stopping at the end of a stop: the
# frames that set the RSR/992 tail sit at a median of 27-32 km/h, and a ramp
# topped out there spends its whole usable range in the bottom fifth. Every
# other threshold in this module is measured under a speed gate and this one
# was not.
#
# **It is also the one field the second car refutes.** At 0.152 - the RSR's
# all-time maximum - 46.4% of the 992's locks at Spa saturate, with a ramp
# median of 0.899. The 992 genuinely reaches past 0.30 at racing speed (32
# frames, median 61 km/h). So the top is per-car in a way `stable`, `at_limit`
# and `rasp_from` are not, and 0.300 is the pooled figure until there is a
# per-car one. The RSR then sits low in the ramp and renders 0.65-0.70 - the
# LOCKED floor carries it, so low in the ramp is quiet, not silent.
ABS_ON = BrakeAnchors(
    stable=0.016, at_limit=0.065, rasp_from=0.065, rasp_means="past-peak",
    lock_floor=0.130, lock_full=0.300, plateau_learned=True, confidence=HIGH,
    source="RSR 991 12 laps + 992 GT3R 33 laps, 21-22 Aug 2026, v1.71, ABS Weak")

# **With no regulator the shape is different, not just the numbers, and this
# record is the least certain thing in the file.**
#
# `lock_full` = 0.260 was the largest excursion in 77 minutes of REGULATED
# driving. Off the regulator a locking wheel runs toward 1.0 and gets there:
# a quarter of every lock the model called on the Shelby was pinned at full
# scale, with the median lock already halfway up the ramp. All the resolution
# had been thrown away at exactly the assist where nothing is catching a
# locked wheel for him.
#
# 0.330 is the racing-speed maximum on the only v1.71 ABS-Off data there is.
# The ungated p99.9 is 0.880, and 0.880 was tried - but the frames that set it
# sit at a median of 27 km/h, so it reproduces the 0.260 pathology mirrored:
# at racing speed the whole usable range would live in the bottom fifth of the
# ramp.
#
# **The floor stays at 0.170 deliberately.** Lifting it past ~0.30 deletes the
# rear lock on downshifts - driver-confirmed, measured at 344 episodes with a
# median peak of 0.127 - so a tidier floor would silence something he has
# already said he feels.
#
# **`confidence` is LOW and it is LOW on purpose.** These are v1.70 numbers,
# one car, one circuit, and CLAUDE.md rule 7 voids pre-patch tuning logic - a
# provenance string documents that, it does not cure it. The one v1.71
# ABS-Off sample says the distribution shrank about 2.2x across the patch,
# the same order as the RSR's controlled 1.6x, and circuit and version are
# confounded in the only pair available. So the cue runs, and it says out loud
# that its scale is borrowed, until a v1.71 ABS-Off session exists.
ABS_OFF = BrakeAnchors(
    stable=0.016, at_limit=0.100, rasp_from=0.100,
    rasp_means="approaching-lock",
    lock_floor=0.170, lock_full=0.330, plateau_learned=False, confidence=LOW,
    source="Shelby GT350R 24 laps Yas v1.70 + 14 laps Road Atlanta v1.71, "
           "ABS Off - BORROWED ACROSS THE PATCH")

ANCHORS = {"Weak": ABS_ON, "Default": ABS_ON, "Off": ABS_OFF}

# **Rear instability under braking**, which matters more here than anywhere
# else because his whole technique is trail-braking deep.
#
# **The wheel-speed witness this used to carry is dead, and the replay is
# what killed it.** The design assumed the rear running slower than the front
# was rare and sharp - measured on the Porsche, the front locks more on 97%
# of braking frames - so a latched rear-vs-front bias was allowed to drive a
# REAR_UNSTABLE state on the brake channel. Replayed over two cars in one
# day (sessions 40 and 41): 20 episodes at Monza, 88 at Yas Marina, and the
# chassis was actually rotating during 1% and 3% of those frames. The other
# 97-99% were engine braking - the driven axle reads a few percent slow the
# moment the throttle closes, the drag varies with gear and revs, and the
# throttle-indexed reference cannot cancel a load it never sees. The same
# fault as the 1.04 wheelspin threshold, at the other end of the car: a cue
# reading the drivetrain and calling it the tyres.
#
# So the rear coming round under braking keeps ONE witness - the chassis
# rotating while the brake is meaningfully applied - and it is not a brake
# state at all any more: the rotation witness already feeds the traction
# channel in `_traction`, so the rear stepping out reads in the same voice,
# the same ramp and the same rhythm whether the throttle or the brake caused
# it. Asked for directly (session 41): "traction loss from throttle is very
# intuitive... can you match the rear traction loss [on braking] to more
# like the throttle traction loss." A rear axle that genuinely LOCKS still
# reports through the worst-axle path; `rear_unstable` stays in the state
# for the explainer, as the rotation witness's view of the same event.
BRAKE_ROTATION_GATE = 0.15    # brake fraction at which rotation counts here
# How much rotation counts as instability rather than as the car turning in.
# Set against the replayed distribution: at 0.35 the state fires on 0.9% of
# frames in runs of about 100 ms, which is a handful of genuine moments per
# lap. At 0.25 it fired on 2.6%, which is most of every corner entry, and a
# warning that is on for most of every corner entry is not a warning.
REAR_ROTATION_ONSET = 0.35

# ----------------------------------------------------------------- rotation
#
# **Sideslip, from two channels that are both in the base packet.**
#
# GT7 broadcasts no sideslip angle. What it does broadcast is the world
# velocity vector and the yaw rate, and the angle between where the car is
# pointing and where it is going is the difference between them, integrated.
#
# Validated on 40 recorded laps by reconstructing the path heading from
# position - the only route available offline, because world velocity is not
# among the recorded channels - over a +-83 ms stencil:
#
#     corr(yaw_rate, path yaw rate) = -0.9985,  slope -0.998
#
# So `angvel_y` is the chassis yaw rate, the path heading derived from world
# coordinates runs in the OPPOSITE sense, and the residual between them is the
# rate of change of sideslip. The sign is measured, not assumed, and it is
# checked again at runtime - see `_HeadingCheck`. A sign convention that
# silently flipped would turn an oversteer warning into a reward for it.
#
# **Confirmed against the real channel, 16 Aug 2026.** The reconstruction
# above had to difference positions stored to the centimetre, which put the
# residual near its own noise floor and was the reason this state was capped
# at MEDIUM. `vel_x/y/z` were added to the recorder to settle it, and one lap
# does:
#
#     corr(angvel_y, velocity-derived path yaw) = -0.9779
#     slope                                     = -0.9961
#     residual on straights   p50 0.0019 rad/s, p90 0.0059 rad/s
#
# The sign is confirmed, the scale is 1.0, and the noise floor supports the
# thresholds with room to spare: 0.0059 rad/s integrated over a 0.3 s slide is
# 0.10 deg of sideslip against a 1.5 deg onset, and the rate onset of 0.15
# rad/s sits at twenty-five times the straight-line residual. So the state is
# reported at HIGH confidence and the cue is no longer attenuated.
#
# One caution worth keeping: the first attempt at this validation returned
# corr -0.27 and was wrong. Two laps had been concatenated and the heading
# differenced across the seam, and a single 188 rad/s outlier in 13,922
# samples is enough to bury a correlation of -0.98. Differencing anything
# across a lap boundary is a mistake this file should not have to learn twice.
HEADING_SIGN = -1.0           # measured: path heading runs opposite to angvel_y
# Sideslip that counts as the car sliding rather than merely cornering.
# 1.5 deg is above every straight-line reading and above the 90th percentile
# of limit cornering; 8 deg is a slide the driver is already correcting.
BETA_ONSET_DEG = 1.5
BETA_FULL_DEG = 8.0
# The rate is the early half of the same message: the rear leaving is rotation
# the driver did not ask for, and it is detectable before the angle has grown.
# 0.15 rad/s is about 8.6 deg/s.
BETA_RATE_ONSET = 0.15
BETA_RATE_FULL = 0.90
# **Where the sideslip reference is re-anchored, and why this is now a
# washout rather than a drifting integral.**
#
# Reported from the seat: a constant vibration after coming off track. The log
# named it exactly - `rear_traction 0.425@101Hz` with the car stationary, and
# `rotation SEVERE_ROTATION 1.00` driving it through the rotation witness.
#
# The cause is this estimator. Sideslip is integrated from the residual
# between yaw and the path heading, and the original design only pulled the
# reference back when the car was above 40 m/s, dead straight and unsteered.
# Everywhere else it leaked with a 120 s time constant, which is no leak at
# all. Any small bias in the residual therefore accumulated: reproduced, a two
# second excursion put the estimate at +136 deg, and a full minute of crawling
# back to the pits left it at +82. The cue has no way back from that - the car
# never gets fast and straight again, so the anchor is never retaken, and the
# rasp is permanent.
#
# **A sideslip angle is a transient quantity and must be treated as one.** A
# genuine slide lasts a few tenths of a second to a couple of seconds; nothing
# a driver needs to be told about lasts ten. So the integral now washes out
# with a 4 s time constant whatever the car is doing, and the straight-line
# anchor stays as the fast path on top of it.
#
# The cost is deliberate and is the right direction to be wrong in: a drift
# held for many seconds fades from the ANGLE term. It does not fade from the
# RATE term, which is the half that catches the rear leaving in the first
# place, and a ten second drift is a spin the driver already knows about.
ANCHOR_SPEED_MS = 40.0
ANCHOR_YAW = 0.03
ANCHOR_STEER = 0.02
ANCHOR_PULL_S = 0.30          # how quickly the anchor is taken when available
ANCHOR_LEAK_S = 4.0           # and how quickly it washes out when it is not
# A hard stop on what the estimate may claim, in degrees. Past about this the
# car is spinning rather than sliding, the driver has more pressing evidence
# than a transducer, and the only thing an unbounded number can do from here
# is get stuck. Reproduced at +136 deg with the car parked.
BETA_LIMIT_DEG = 25.0
# Runtime proof that the two channels still mean what they meant on the bench.
# Correlation is accumulated over a rolling window; below the threshold the
# rotation state reports UNKNOWN and the cue is silent rather than wrong.
CHECK_WINDOW = 600            # frames, ten seconds
CHECK_MIN_CORR = 0.80
# Below this much variance in the yaw channel there is nothing for a
# correlation to measure - see `_HeadingCheck.trusted`. 0.02 rad/s is well
# under the 0.045 median of his lap and comfortably over a straight.
CHECK_MIN_VARIANCE = 4e-4     # rad/s squared

# --------------------------------------------------------------------- load
#
# **Suspension is compression, and larger is more loaded.** Measured rather
# than assumed, because the packet documentation calls it a height and the
# sign decides whether a crest reads as unloading or as bottoming:
#
#     front mean under heavy braking 290.2 mm, cruising 284.7
#     rear  mean under heavy braking 279.9 mm, cruising 301.5
#     corr(roll, signed lateral g) = -0.976
#
# The front compresses under braking and the rear under power, and the roll
# term tracks lateral load transfer almost perfectly. Larger is more loaded.
#
# The sum over four corners correlates 0.861 with speed squared, which is
# aerodynamic downforce showing up in the only channel that can see it. That
# is what makes a load proxy possible at all.
LOAD_REFERENCE_S = 20.0       # how slowly the per-wheel neutral is learned
LOAD_SETTLE_FRAMES = 300
# How far below its own reference a corner has to go to count as unloading, in
# units of that corner's own spread. Measured: all four extending together by
# more than 2 sigma happens on 0.32% of frames in 147 episodes of about
# 100 ms, which is what a crest looks like.
UNLOAD_ONSET_Z = 1.0
UNLOAD_FULL_Z = 2.6
# Compression beyond anything the car normally reaches. Not called bottoming:
# GT7 reports no travel remaining, and CLAUDE.md 3.3 is explicit that a bare
# "travel remaining" implies a measurement nobody made. This is an excursion
# toward the observed extreme and it is named as that.
COMPRESSION_Z = 2.6
# How long after rejoining the tarmac the load cues stay quiet while the car
# settles and the suspension stops carrying the excursion.
OFF_SURFACE_GRACE_S = 1.5

# States, as words rather than numbers, because these are what the driver is
# told and what the tests assert on.
GRIPPED = "GRIPPED"
APPROACHING_SLIP = "APPROACHING_SLIP"
USEFUL_SLIP = "USEFUL_SLIP"
EXCESSIVE_WHEELSPIN = "EXCESSIVE_WHEELSPIN"
SEVERE_TRACTION_LOSS = "SEVERE_TRACTION_LOSS"
UNKNOWN = "UNKNOWN"

BRAKE_FREE = "FREE"
BRAKE_STABLE_S = "STABLE"
BRAKE_LIMIT_S = "AT_LIMIT"
BRAKE_INCIPIENT = "INCIPIENT_LOCK"
BRAKE_LOCKED = "LOCKED"

ROTATION_NEUTRAL = "NEUTRAL"
ROTATION_ROTATING = "ROTATING"
ROTATION_OVERSTEER = "OVERSTEER"
ROTATION_SEVERE = "SEVERE_ROTATION"



def ramp(value: float, onset: float, full: float) -> float:
    """0 below `onset`, 1 at `full`, a straight line between."""
    if full <= onset:
        return 0.0
    if value <= onset:
        return 0.0
    return min(1.0, (value - onset) / (full - onset))


class _Reference:
    """A value that follows one direction quickly and the other slowly.

    Used where a slow symmetric average is wanted with a bias - the per-wheel
    ride-height neutral, which has to move when the car is set up differently
    but must not chase a single kerb.
    """

    def __init__(self, fall_s: float, rise_s: float,
                 settle_frames: int = 0) -> None:
        self._fall = fall_s
        self._rise = rise_s
        self._settle = settle_frames
        self.value: float | None = None
        self.samples = 0

    def update(self, sample: float, dt: float = FRAME_S) -> float | None:
        if self.value is None:
            self.value = float(sample)
            self.samples = 1
            return self.value
        tau = self._fall if sample < self.value else self._rise
        self.value += (float(sample) - self.value) * min(1.0, dt / tau)
        self.samples += 1
        return self.value

    def reset(self) -> None:
        self.value = None
        self.samples = 0

    @property
    def settled(self) -> bool:
        return self.value is not None and self.samples >= self._settle


class _Quantile:
    """Tracks a chosen quantile of whatever it is fed, one step at a time.

    Frugal-2U in everything but name: step up by `q * step` when the sample is
    above, down by `(1 - q) * step` when it is below, and the value converges
    on the q-th quantile of the stream. It needs one float of state, no
    history, no sorting and no allocation, which is what makes it usable on
    the telemetry thread.

    Why not a mean: a mean learns the excursion. The rear axle's rolling
    reference and the ABS regulation plateau are both quantities that have to
    be estimated from a stream that CONTAINS the events they are used to
    detect, and an estimator that moves toward those events destroys the very
    contrast it exists to provide.
    """

    def __init__(self, quantile: float, step: float,
                 settle_frames: int = 0, initial: float | None = None) -> None:
        self._q = quantile
        self._step = step
        self._settle = settle_frames
        self.value = initial
        self.samples = 0
        self.withheld = 0
        # Set by the caller the first time this tracker sees a sample near its
        # own value - see `_SlipReference.observe`. Until then the tracker has
        # not shown it is anywhere near the stream, and blanking it would be
        # defending an estimate that has not earned defending.
        self.arrived = False

    def update(self, sample: float, allow_rise: bool = True) -> float | None:
        """One sample. `allow_rise=False` suppresses the upward step only.

        The asymmetry is what lets a caller blank the estimator during the
        very event it is used to detect without freezing it altogether: a
        reference that is too HIGH hides events, so downward correction is
        always allowed, and only the direction that could learn the event away
        is withheld.
        """
        sample = float(sample)
        if self.value is None:
            self.value = sample
            self.samples = 1
            return self.value
        if sample > self.value:
            # **Counted even when the step is withheld**, and it was not.
            # `settled` is a sample count, so returning early here meant a
            # band sitting below its true value never accumulated any: every
            # sample was above it, every rise was suppressed, and it could
            # therefore neither climb nor ever settle. A band stuck in that
            # state is read back by borrowing a neighbour - and the neighbour
            # is a lower throttle band with a genuinely lower slip, which is
            # how the driven axle came to look like it was spinning at
            # 247 km/h in top gear for a whole practice session.
            #
            # Suppressing the STEP is the point. Suppressing the OBSERVATION
            # was an accident: the estimator still saw the sample, and that
            # it saw it is what "settled" is counting.
            self.samples += 1
            if not allow_rise:
                # **A withheld rise is evidence about the estimate too.**
                # Every sample above and none below, for as long as the caller
                # keeps saying "event", is not what an event looks like - it is
                # what a reference sitting below the whole stream looks like.
                # Counted and published, and nothing acts on it: see
                # REFERENCE_PRIOR for why the seed is the fix and an automatic
                # release is not.
                self.withheld += 1
                return self.value
            self.withheld = 0
            self.value += self._step * self._q
            return self.value
        self.withheld = 0
        if sample < self.value:
            self.value -= self._step * (1.0 - self._q)
        self.samples += 1
        return self.value

    def reset(self, initial: float | None = None) -> None:
        self.value = initial
        self.samples = 0
        self.withheld = 0
        self.arrived = False

    @property
    def settled(self) -> bool:
        return self.value is not None and self.samples >= self._settle


class _SlipReference:
    """Expected driven-axle slip as a function of throttle, learned per car.

    Four quantile trackers over four throttle bands, read back by
    interpolating between band centres. The interpolation matters as much as
    the tracking: a step between bands would put a discontinuity in the middle
    of a corner exit, and a discontinuity in a reference is a phantom event in
    everything measured against it.

    A band that has not settled borrows the nearest one that has, so going out
    on cold tyres does not mean no traction cue for a lap.
    """

    def __init__(self, bands: int = REFERENCE_BANDS) -> None:
        # Seeded from the measured table, so no band ever takes its estimate
        # from a single frame. A band count other than four has no measured
        # seed and falls back to the old behaviour rather than to a number
        # borrowed from a differently-shaped curve.
        seeds = (REFERENCE_PRIOR if bands == len(REFERENCE_PRIOR)
                 else (None,) * bands)
        self._bands = [_Quantile(REFERENCE_QUANTILE, REFERENCE_STEP,
                                 REFERENCE_SETTLE_FRAMES, initial=seed)
                       for seed in seeds]
        self._seeds = seeds
        self._n = bands

    def _index(self, throttle: float) -> int:
        raw = int(throttle * self._n)
        return min(self._n - 1, max(0, raw))

    def observe(self, throttle: float, slip: float,
                allow_rise: bool = True) -> None:
        """One sample into the band this throttle falls in.

        **A band that has not ARRIVED always learns, whatever the caller
        says.** The caller withholds the rise while an event is running, so a
        stream that is nothing but wheelspin cannot teach the estimator that
        wheelspin is normal. That protects a reference which already knows
        what normal is.

        Applied to a band that does NOT yet know, it is a deadlock: the band
        starts below its true value, so every honest sample reads as an event,
        so the rise is withheld for ever and the band never converges.

        **Arrival is proof, not elapsed time, and that distinction is the
        whole guard.** An earlier version armed on `settled` - 240 samples -
        which buys a band at most `240 * q * step` = 0.0168 of travel. From the
        0.0321 seed that caps it at 0.0489, so any car whose true value is
        above 0.0489 + SLIP_USEFUL = **0.0789** armed the guard while still
        below the stream and stuck there for the session. The measured span
        across three cars is 0.013 to 0.060, which is a margin of 1.32x, and a
        high-torque RWD road car on Comfort tyres in a no-BoP league is not an
        exotic way to spend it.

        A band has arrived the first time it sees a sample within SLIP_USEFUL
        of its own value. That cannot be satisfied by an event - an event is
        what sits ABOVE the reference by more than that - so it says the band
        is in the neighbourhood of the stream, which is the only thing worth
        defending.
        """
        band = self._bands[self._index(throttle)]
        if band.value is not None and slip - band.value < SLIP_USEFUL:
            band.arrived = True
        band.update(slip, allow_rise or not band.arrived)

    def value(self, throttle: float) -> float | None:
        """The expected slip at this throttle, or None if nothing has settled."""
        settled = [(i, b) for i, b in enumerate(self._bands) if b.settled]
        if not settled:
            return None
        # Band centres in throttle units, so the reference is a piecewise line
        # through the middle of each band rather than a staircase at its edges.
        width = 1.0 / self._n
        xs = [(i + 0.5) * width for i, _ in settled]
        ys = [b.value or 0.0 for _, b in settled]
        if throttle <= xs[0]:
            return ys[0]
        if throttle >= xs[-1]:
            return ys[-1]
        for (x0, y0), (x1, y1) in zip(zip(xs, ys), list(zip(xs, ys))[1:]):
            if x0 <= throttle <= x1:
                span = x1 - x0
                return y0 if span <= 0 else y0 + (y1 - y0) * (throttle - x0) / span
        return ys[-1]

    @property
    def settled(self) -> bool:
        return any(b.settled for b in self._bands)

    @property
    def samples(self) -> tuple[int, ...]:
        return tuple(b.samples for b in self._bands)

    @property
    def withheld(self) -> tuple[int, ...]:
        """Consecutive blanked rises per band, for the explainer.

        A band whose count runs into the thousands is sitting below the whole
        stream rather than watching a long event, and this is the only place
        that says so. Nothing acts on it - see REFERENCE_PRIOR.
        """
        return tuple(b.withheld for b in self._bands)

    def reset(self) -> None:
        # Back to the measured seeds, not to nothing: a band that reset to
        # empty would take its next estimate from one frame again, and the
        # frame after a reset is the frame after a garage visit.
        for band, seed in zip(self._bands, self._seeds):
            band.reset(seed)


class _Latch:
    """A threshold with hysteresis, a confirmation count and a hold.

    Critical cues must not chatter at their own boundary and must not be late.
    Those pull opposite ways, so all three controls are separate: `confirm`
    frames to come on, a lower level to stay on, and a hold before going off.
    A single smoothing time constant cannot express that - which is how the
    old lock detector came to carry a 220 ms attack on the most urgent cue in
    the system.
    """

    def __init__(self, on: float, off: float, confirm: int = CONFIRM_FRAMES,
                 hold_s: float = HOLD_S) -> None:
        self.on = on
        self.off = off
        self._confirm = confirm
        self._hold_s = hold_s
        self._count = 0
        self._held = 0.0
        self.active = False

    def update(self, value: float, dt: float = FRAME_S) -> bool:
        if self.active:
            if value < self.off:
                self._held += dt
                if self._held >= self._hold_s:
                    self.active = False
                    self._count = 0
            else:
                self._held = 0.0
        else:
            if value >= self.on:
                self._count += 1
                if self._count >= self._confirm:
                    self.active = True
                    self._held = 0.0
            else:
                self._count = 0
        return self.active

    def reset(self) -> None:
        self._count = 0
        self._held = 0.0
        self.active = False


class _Envelope:
    """Instant on the way up, exponential on the way down.

    The asymmetry is the point and it is the opposite of a smoothing filter.
    Smoothing costs latency in both directions; a driver needs a slide
    reported the frame it starts and does not need it to stop the frame it
    stops.
    """

    def __init__(self, release_s: float = LEVEL_RELEASE_S) -> None:
        self._release = release_s
        self.value = 0.0

    def update(self, target: float, dt: float = FRAME_S) -> float:
        target = float(target)
        if target >= self.value:
            self.value = target
        else:
            self.value += (target - self.value) * min(1.0, dt / self._release)
        return self.value

    def reset(self) -> None:
        self.value = 0.0


class _HeadingCheck:
    """Runtime proof that yaw and the velocity heading still agree.

    The sideslip model rests on a sign and a scale established on recorded
    laps. If GT7 changes a coordinate convention, or an offset drifts, or the
    car is one where the velocity vector behaves differently, the model does
    not fail loudly - it reports the driver's ordinary cornering as a slide, at
    the exact moment he is busy.

    So the two are correlated continuously over a rolling window, and a
    correlation that falls away takes the rotation cue with it. Same shape of
    argument as the transducer's endpoint meter: an output that can be
    confidently wrong needs a second witness.
    """

    def __init__(self, window: int = CHECK_WINDOW) -> None:
        self._n = window
        self._count = 0
        self._sxx = self._syy = self._sxy = 0.0
        self._sx = self._sy = 0.0
        self.correlation = 0.0
        self._variance = 0.0
        # What the last verdict was while there was still evidence for one.
        # Starts False so nothing is trusted before it has been earned.
        self._last_verdict = False

    def update(self, yaw: float, path_yaw: float) -> None:
        # A decaying accumulator rather than a ring buffer: no allocation, and
        # it forgets at the rate the window implies.
        decay = 1.0 - 1.0 / self._n
        self._sx = self._sx * decay + yaw
        self._sy = self._sy * decay + path_yaw
        self._sxx = self._sxx * decay + yaw * yaw
        self._syy = self._syy * decay + path_yaw * path_yaw
        self._sxy = self._sxy * decay + yaw * path_yaw
        self._count = min(self._n, self._count + 1)
        n = 1.0 / (1.0 - decay)
        cov = self._sxy - self._sx * self._sy / n
        vx = self._sxx - self._sx * self._sx / n
        vy = self._syy - self._sy * self._sy / n
        self._variance = vx / n
        self.correlation = ((cov / math.sqrt(vx * vy))
                            if vx > 1e-9 and vy > 1e-9 else 0.0)

    def reset(self) -> None:
        self._count = 0
        self._sx = self._sy = self._sxx = self._syy = self._sxy = 0.0
        self.correlation = 0.0
        self._variance = 0.0
        self._last_verdict = False

    @property
    def trusted(self) -> bool:
        """Whether the two channels have been shown to agree recently.

        **A straight is not disagreement.** The log from a real drive shows
        this flapping between trusted and not several times a lap - `rotation
        NEUTRAL (high)` in the corners and `rotation UNKNOWN (none)` on the
        straights - which took the rotation cue away exactly where it would
        next be needed, at the end of the straight under braking.

        The reason is arithmetic rather than physical. A correlation needs
        variance in both channels to mean anything, and on a straight both yaw
        and the path yaw rate are flat, so the ratio is noise over noise. The
        check was reporting "these channels no longer agree" when what it had
        actually found was "there is nothing here to agree about".

        So a verdict is only revised where there is something to revise it
        with. Below the variance floor the last real verdict stands, which is
        the honest reading: the last time there was evidence, they agreed.
        """
        if self._count < self._n // 4:
            return False
        if self._variance < CHECK_MIN_VARIANCE:
            return self._last_verdict
        self._last_verdict = abs(self.correlation) >= CHECK_MIN_CORR
        return self._last_verdict


@dataclass
class VehicleState:
    """Everything derived, for one frame, with what it was derived from.

    Deliberately a record rather than six floats: the diagnostics have to be
    able to answer "what exactly caused that vibration", and they can only do
    that if the inputs travel with the answer.
    """

    # --- rear traction
    traction: str = UNKNOWN
    traction_level: float = 0.0
    traction_confidence: str = NONE
    slip_excess: float = 0.0
    slip_reference: float | None = None
    # --- braking
    brake_state: str = BRAKE_FREE
    brake_level: float = 0.0
    brake_axle: str | None = None
    front_lock: float = 0.0
    rear_lock: float = 0.0
    # The live default comes from the anchors, not from the v1.70
    # constant: this field is logged, and session 39 was diagnosed off it.
    lock_threshold: float = ABS_ON.lock_floor
    rear_unstable: float = 0.0
    # Whether the scale behind `brake_level` was measured on the assist
    # actually fitted, or borrowed from another one. See `VehicleModel.set_abs`.
    brake_confidence: str = NONE
    # --- rotation
    rotation: str = UNKNOWN
    rotation_level: float = 0.0
    rotation_confidence: str = NONE
    beta_deg: float = 0.0
    beta_rate: float = 0.0
    heading_correlation: float = 0.0
    # --- load
    load_front: float = 0.0
    load_rear: float = 0.0
    unload: float = 0.0
    unload_front: float = 0.0
    unload_rear: float = 0.0
    compression: float = 0.0
    landed: float = 0.0
    # --- surface and driveline
    on_kerb: bool = False
    off_surface: bool = False
    kerb_strike: float = 0.0
    surface_change: float = 0.0
    shifted: bool = False
    limiter: bool = False
    # --- raw, kept for the explainer
    speed_ms: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    lateral_g: float = 0.0
    long_g: float = 0.0
    reasons: dict = field(default_factory=dict)


class VehicleModel:
    """One frame in, one `VehicleState` out, and the memory in between.

    Called on the telemetry thread once per packet. Holds no lock, allocates
    one small record, and never raises on a channel it did not get - a packet
    format without surface types produces a state with the surface fields
    empty rather than an exception in the output path.
    """

    def __init__(self) -> None:
        self._slip_ref = _SlipReference()
        self._plateau = _Quantile(PLATEAU_QUANTILE, PLATEAU_STEP,
                                  initial=ABS_ON.lock_floor / PLATEAU_MARGIN)
        self._load_ref = [_Reference(LOAD_REFERENCE_S, LOAD_REFERENCE_S,
                                     LOAD_SETTLE_FRAMES) for _ in range(4)]
        self._load_spread = [_Reference(LOAD_REFERENCE_S, LOAD_REFERENCE_S)
                             for _ in range(4)]
        self._heading = _HeadingCheck()
        self._traction_env = _Envelope()
        self._brake_env = _Envelope()
        self._latches = {
            "approaching": _Latch(SLIP_APPROACHING, SLIP_APPROACHING * 0.7),
            "useful": _Latch(SLIP_USEFUL, SLIP_USEFUL * 0.75),
            "excessive": _Latch(SLIP_EXCESSIVE, SLIP_EXCESSIVE * 0.75),
            "severe": _Latch(SLIP_SEVERE, SLIP_SEVERE * 0.8),
            "at_limit": _Latch(BRAKE_AT_LIMIT, BRAKE_AT_LIMIT * 0.8, confirm=1),
            "locking": _Latch(LOCK_FLOOR, LOCK_FLOOR * 0.82, confirm=2,
                              hold_s=0.08),
        }
        self._prev_heading: float | None = None
        self._beta_raw = 0.0
        self._beta_anchor: float | None = None
        self._prev_gear: int | None = None
        self._shift_blind = 0.0
        self._prev_surfaces: tuple[str, ...] | None = None
        self._prev_speed: float | None = None
        self._unload_peak = 0.0
        self._unload_since = 0.0
        self._offtrack_grace = 0.0
        # Deliberately NOT cleared by `reset()`: which car this is survives a
        # session boundary, and clearing it there would make the first frame of
        # every session look like a car change and reset a model that had just
        # been reset. `_note_car` owns it.
        self._car_id: int | None = None
        self.car_changed = False
        # The assist declared on the event, and the scale that goes with it.
        # Like `_car_id`, deliberately NOT cleared by `reset()`: that runs on
        # a session boundary, a car change and a watchdog recovery, and
        # clearing it there would drop a live race into the borrowed branch
        # mid-stint without anything saying so.
        self._abs: str | None = None
        self._anchors: BrakeAnchors = ABS_ON
        self._borrowed = True
        self.state = VehicleState()

    def set_abs(self, setting: str | None) -> None:
        """Which ABS the regulations put in the car, from `events.abs_setting`.

        **A declared assist with no measured scale still gets a cue.** The
        repo's usual answer to "nobody has measured this" is silence - the
        shift beep does exactly that for an unmeasured gearbox - but the
        trade is different here and it goes the other way. A gearbox with no
        beep costs a tenth; a brake cue that goes quiet under ABS Off is a
        silent false negative on the highest-priority cue in the rig, at the
        one assist setting where nothing is catching a locked wheel for him.
        A wrong silence is also harder to notice from the seat than a wrong
        level.

        So an unmeasured assist BORROWS the ABS-on scale and says so:
        `brake_confidence` drops to LOW and the explainer names the borrow.
        `None` is kept as None rather than defaulted to a string - the app not
        knowing and the event declaring "Weak" are different facts.
        """
        self._abs = setting or None
        anchors = ANCHORS.get(self._abs or "")
        # Order matters: `_anchors` first, so a telemetry frame landing between
        # the two writes can never read the new confidence against the old
        # scale.
        self._anchors = anchors or ABS_ON
        # **Borrowed, not merely absent.** An assist the table has never heard
        # of gets ABS_ON at LOW - and an assist the table DOES have can still
        # be LOW, because a key existing is not evidence anyone measured it.
        self._borrowed = anchors is None
        # Re-seeded, because the seed is a property of the scale: leaving the
        # old assist's floor in the learner would keep the previous
        # regulation's threshold alive for the first minutes of the new one.
        self._plateau.reset(self._anchors.lock_floor / PLATEAU_MARGIN)

    # ------------------------------------------------------------- lifecycle

    def reset(self) -> None:
        """Between sessions. A garage visit teleports the car, which makes
        every differenced channel produce an event that never happened."""
        self._slip_ref.reset()
        self._plateau.reset(self._anchors.lock_floor / PLATEAU_MARGIN)
        for ref in self._load_ref + self._load_spread:
            ref.reset()
        self._heading.reset()
        self._traction_env.reset()
        self._brake_env.reset()
        for latch in self._latches.values():
            latch.reset()
        self._prev_heading = None
        self._beta_raw = 0.0
        self._beta_anchor = None
        self._prev_gear = None
        self._shift_blind = 0.0
        self._prev_surfaces = None
        self._prev_speed = None
        self._unload_peak = 0.0
        self._unload_since = 0.0
        self._offtrack_grace = 0.0
        self.state = VehicleState()

    # -------------------------------------------------------------- a frame

    def _note_car(self, p: GT7Packet) -> None:
        """Forget everything learned when the car underneath changes.

        Every reference in this model is a property of one car - the driven
        axle's slip at a given throttle, the per-wheel load neutral, the ABS
        plateau. `reset()` is called between SESSIONS, which is not the same
        boundary: a garage visit inside one session swaps the car and leaves
        the previous car's references in place, and they are then read back as
        if they described this one. Measured across three cars in three days,
        the band-3 slip reference spans 0.013 to 0.060 - a factor of 4.6, and
        the cue reads slip ABOVE that number.

        `car_id` 0 is GT7's "not loaded yet" sentinel and arrives during
        loading screens, so it is not a car and never triggers the reset - the
        same guard the controller applies before it announces a car.
        """
        self.car_changed = False
        car = getattr(p, "car_id", None)
        if not car:
            return
        if self._car_id is None:
            self._car_id = car
            return
        if car != self._car_id:
            self._car_id = car
            self.reset()
            # Published for one frame so anything holding its own per-car
            # learning - the road bed's scale in `effects` - can drop it on the
            # same boundary rather than keeping a second, disagreeing idea of
            # which car this is.
            self.car_changed = True

    def update(self, p: GT7Packet, dt: float = FRAME_S) -> VehicleState:
        self._note_car(p)
        s = VehicleState()
        self.state = s
        s.speed_ms = p.speed_ms
        s.throttle = p.throttle
        s.brake = p.brake
        s.limiter = p.rev_limiter_active

        self._note_gear(p, dt)
        s.shifted = self._shift_blind > 0.0
        self._surfaces(p, s)

        if p.speed_ms < MIN_SPEED_MS:
            # Not an error and not a state: below walking pace the ratios
            # divide by nothing and a velocity heading is noise. Everything
            # else stays at its default, which is silence.
            self._prev_speed = p.speed_ms
            self._prev_heading = None
            return s

        s.lateral_g = abs(p.speed_ms * p.angvel_y) / 9.81
        if self._prev_speed is not None and dt > 0:
            s.long_g = (p.speed_ms - self._prev_speed) / dt / 9.81
        self._prev_speed = p.speed_ms

        self._load(p, s, dt)
        self._rotation(p, s, dt)
        self._traction(p, s, dt)
        self._braking(p, s, dt)
        return s

    # ------------------------------------------------------------- driveline

    def _note_gear(self, p: GT7Packet, dt: float) -> None:
        gear = p.current_gear
        previous, self._prev_gear = self._prev_gear, gear
        self._shift_blind = max(0.0, self._shift_blind - dt)
        if (previous is not None and gear != previous
                and gear > 0 and previous > 0):
            self._shift_blind = SHIFT_BLIND_S

    # --------------------------------------------------------------- surface

    def _surfaces(self, p: GT7Packet, s: VehicleState) -> None:
        """The one genuinely measured channel in this module.

        GT7 sends a character per wheel and nothing else here is a
        measurement. It is also the channel SimHub's GT7 support cannot see at
        all, because it reads the base packet only.
        """
        surfaces = p.surface_types
        previous, self._prev_surfaces = self._prev_surfaces, surfaces
        if not surfaces:
            return
        s.on_kerb = any(c == "C" for c in surfaces)
        s.off_surface = any(c in ("D", "G", "S", "s") for c in surfaces)
        if not previous:
            return
        # **From tarmac only.** `car_on_track` is GT7's flags bit 0, which
        # means "in a session" rather than "on the racing surface", so a run
        # wide and a scrabble back over the kerb used to fire a full-strength
        # apex hit.
        if any(now == "C" and was == "T"
               for now, was in zip(surfaces, previous)):
            s.kerb_strike = 1.0
        changed = sum(1 for now, was in zip(surfaces, previous) if now != was)
        s.surface_change = changed / 4.0

    # ------------------------------------------------------------------ load

    def _load(self, p: GT7Packet, s: VehicleState, dt: float) -> None:
        """Vertical load, as far as suspension compression can carry it.

        Never called tyre force. GT7 broadcasts no tyre force, and CLAUDE.md
        3.3 is explicit that reporting one implies a measurement nobody made.
        What this is: how far each corner sits from where that corner sits
        when the car is doing nothing, in units of its own spread.
        """
        # **Off the racing surface, the load model stops listening.**
        #
        # Reported from the seat: "when I went off track it took a while for
        # haptics to settle, it didn't recognise I was back on track straight
        # away". The neutral is a 20-second average, and twenty seconds of
        # bouncing across grass drags it somewhere no tarmac lap ever goes -
        # so the first corners after rejoining read as phantom unloading and
        # compression until the reference has crawled back. The excursion is
        # not evidence about normal ride height, so it is not allowed to
        # teach, and the cues built on the reference hold their peace for a
        # moment after rejoining rather than reporting the reference's error.
        if s.off_surface:
            self._offtrack_grace = OFF_SURFACE_GRACE_S
            return
        if self._offtrack_grace > 0.0:
            self._offtrack_grace = max(0.0, self._offtrack_grace - dt)
            return
        heights = (p.suspension_fl, p.suspension_fr,
                   p.suspension_rl, p.suspension_rr)
        zs = []
        for index, height in enumerate(heights):
            ref = self._load_ref[index]
            # The neutral is a SLOW symmetric average, unlike the slip
            # reference: an average ride height is exactly what is wanted here,
            # and load transfer averages out over a lap by definition.
            previous = ref.value
            ref.update(height, dt)
            spread = self._load_spread[index]
            if previous is not None:
                spread.update(abs(height - previous), dt)
            # `spread` is the mean absolute deviation from the slow neutral.
            # For a normal distribution the standard deviation is 1.25 times
            # that, and it is the standard deviation the thresholds below are
            # written in. A first attempt used a factor of twelve, which put
            # every corner inside a tenth of a sigma of its own neutral and
            # meant the unloading cue could not fire at all - measured, its
            # maximum over 278,034 frames was exactly zero.
            sigma = max(1e-5, (spread.value or 0.0) * 1.25)
            zs.append((height - (ref.value or height)) / sigma)
        if not all(r.settled for r in self._load_ref):
            return
        front_z = (zs[0] + zs[1]) / 2.0
        rear_z = (zs[2] + zs[3]) / 2.0
        s.load_front = max(0.0, front_z)
        s.load_rear = max(0.0, rear_z)
        s.unload_front = ramp(-front_z, UNLOAD_ONSET_Z, UNLOAD_FULL_Z)
        s.unload_rear = ramp(-rear_z, UNLOAD_ONSET_Z, UNLOAD_FULL_Z)
        s.unload = ramp(-(front_z + rear_z) / 2.0, UNLOAD_ONSET_Z, UNLOAD_FULL_Z)
        s.compression = ramp(max(zs), COMPRESSION_Z, COMPRESSION_Z + 1.6)

        # **Landing is the return, not the flight.** A car that has been light
        # and then compresses hard has landed; the same compression without the
        # lightness before it is a dip in the road. Keeping the peak of the
        # unloading is what separates them, and it is what puts the thump at
        # the moment the driver feels the tyres take the weight again.
        if s.unload > 0.15:
            self._unload_peak = max(self._unload_peak, s.unload)
            self._unload_since = 0.0
        else:
            self._unload_since += dt
            if (self._unload_peak > 0.3 and s.compression > 0.05
                    and self._unload_since < 0.6):
                s.landed = min(1.0, self._unload_peak * (0.4 + s.compression))
                self._unload_peak = 0.0
            elif self._unload_since > 0.6:
                self._unload_peak = 0.0

    # -------------------------------------------------------------- rotation

    def _rotation(self, p: GT7Packet, s: VehicleState, dt: float) -> None:
        """Sideslip, from the velocity vector against the yaw rate.

        Both channels are in the base packet, so this works on every format
        GT7 emits, including the ones carrying no steering angle at all.
        """
        heading = math.atan2(p.vel_z, p.vel_x)
        previous, self._prev_heading = self._prev_heading, heading
        yaw = p.angvel_y
        if previous is None or dt <= 0:
            return
        delta = (heading - previous + math.pi) % (2.0 * math.pi) - math.pi
        path_yaw = HEADING_SIGN * delta / dt
        self._heading.update(yaw, path_yaw)
        s.heading_correlation = self._heading.correlation

        # The rate of change of sideslip: the chassis turning faster than the
        # path it is on is the rear leaving, and it is visible before the angle
        # has grown.
        beta_rate = yaw - path_yaw
        self._beta_raw += beta_rate * dt

        straight = (p.speed_ms > ANCHOR_SPEED_MS and abs(yaw) < ANCHOR_YAW
                    and abs(p.steering_norm or 0.0) < ANCHOR_STEER)
        if self._beta_anchor is None:
            self._beta_anchor = self._beta_raw
        tau = ANCHOR_PULL_S if straight else ANCHOR_LEAK_S
        self._beta_anchor += ((self._beta_raw - self._beta_anchor)
                              * min(1.0, dt / tau))
        beta = self._beta_raw - self._beta_anchor
        # Clamped, and the raw integral pulled back with it so the estimator
        # cannot sit outside its own range carrying a number it can never
        # work off.
        ceiling = math.radians(BETA_LIMIT_DEG)
        if abs(beta) > ceiling:
            beta = math.copysign(ceiling, beta)
            self._beta_raw = self._beta_anchor + beta

        s.beta_deg = math.degrees(beta)
        s.beta_rate = beta_rate
        if not self._heading.trusted:
            s.rotation = UNKNOWN
            s.rotation_confidence = NONE
            s.rotation_level = 0.0
            return
        # Signed toward "the rear is going the way the car is already turning".
        # Rotation that opposes the corner is the driver catching it, not the
        # car leaving.
        sign = 1.0 if yaw >= 0 else -1.0
        angle_part = ramp(abs(s.beta_deg), BETA_ONSET_DEG, BETA_FULL_DEG)
        rate_part = ramp(beta_rate * sign, BETA_RATE_ONSET, BETA_RATE_FULL)
        s.rotation_level = max(angle_part, rate_part)
        # High, since the model was checked against the real velocity vector
        # rather than against a path reconstructed from stored positions. The
        # runtime check above is what keeps it honest frame to frame.
        s.rotation_confidence = HIGH
        if s.rotation_level >= 0.75:
            s.rotation = ROTATION_SEVERE
        elif s.rotation_level >= 0.40:
            s.rotation = ROTATION_OVERSTEER
        elif s.rotation_level > 0.0:
            s.rotation = ROTATION_ROTATING
        else:
            s.rotation = ROTATION_NEUTRAL

    # -------------------------------------------------------------- traction

    def _axle_slip(self, p: GT7Packet) -> tuple[float, float] | None:
        """Front and rear axle slip ratios, or None below usable speed.

        **The per-wheel channel is rad/s, not rev/s** - see
        `recorder._slip_ratios` for the account of a factor of 2pi that meant a
        driver whose whole technique is trail-braking deep had never once been
        shown a lockup.
        """
        if p.speed_ms < MIN_SPEED_MS:
            return None
        rps = (p.wheel_rps_fl, p.wheel_rps_fr, p.wheel_rps_rl, p.wheel_rps_rr)
        radius = (p.tyre_radius_fl, p.tyre_radius_fr,
                  p.tyre_radius_rl, p.tyre_radius_rr)
        speeds = [abs(w) * r / p.speed_ms for w, r in zip(rps, radius)]
        return (speeds[0] + speeds[1]) / 2.0, (speeds[2] + speeds[3]) / 2.0

    def _traction(self, p: GT7Packet, s: VehicleState, dt: float) -> None:
        axles = self._axle_slip(p)
        if axles is None:
            return
        front, rear = axles

        # **What the rear is measured against, and why it changes.**
        #
        # Off the brakes the front axle is free-rolling, which makes it a
        # better reference than the chassis speed: it shares the tyre-radius
        # convention, the speed channel and whatever rounding both carry, so
        # the difference cancels all of them.
        #
        # Under braking it is not free-rolling at all - measured, the front
        # runs 7-15% of slip through every braking zone while the ABS works.
        # Referencing the rear against that reads a LOCKING FRONT as a
        # SPINNING REAR: caught by a test with the front at 0.74 and the rear
        # at 0.95, which is a heavy stop, and which this model reported as a
        # full-scale slide. Opposite correction, on the cue that matters most.
        #
        # So on the brakes the reference is the road, which is what the rear
        # is actually being compared to.
        braking = p.brake >= PEDAL_ON
        difference = rear - (1.0 if braking else front)

        # Read the reference BEFORE feeding it, so the event about to be
        # measured cannot contribute to the measurement of what normal is.
        reference = self._slip_ref.value(p.throttle)
        s.slip_reference = reference

        # Sampled while the car is driving forward off the brakes and on a
        # real surface. Not restricted to gentle driving: the quantile is what
        # makes learning at the limit safe, and a reference learned only in
        # conditions the cue is never used in is not a reference - an earlier
        # version sampled at partial throttle only and learned 0.008 for a band
        # whose true value is 0.032.
        usable = (p.brake < PEDAL_ON and s.lateral_g < REFERENCE_LAT_G_MAX
                  and not s.shifted and not s.off_surface)
        if usable:
            # **Blanked while an event is running.** A quantile converges on
            # the quantile of the stream it is shown, so a stream that is
            # nothing but wheelspin teaches it that wheelspin is normal.
            # Measured on this exact case: ten seconds of a held 12% slide
            # moved the reference by 0.042 and quartered the cue. Suppressing
            # only the upward step keeps the estimator honest in the direction
            # that matters - a reference that is too high hides events, so it
            # is always allowed to fall.
            quiet = (reference is None
                     or (difference - reference) < SLIP_USEFUL)
            self._slip_ref.observe(p.throttle, difference, allow_rise=quiet)

        if reference is None:
            s.traction = UNKNOWN
            s.traction_confidence = NONE
            return

        excess = difference - reference
        s.slip_excess = excess

        # A gearshift steps the driveline and the wheel rate steps with it. A
        # rear that is genuinely spinning is still spinning 50 ms later.
        #
        # The wheel witness is also silent under the brakes. A driven wheel
        # cannot spin up while the brakes are on it, so anything the ratio
        # says there is the front axle's behaviour leaking in - and the rear
        # coming round under braking is real, common for this driver, and
        # carried by the rotation witness below, which stays live on the
        # brakes for exactly that reason. This is the whole of the braking
        # rear-instability cue since the wheel-bias witness was measured and
        # retired - see the account above BRAKE_ROTATION_GATE.
        wheel_level = (0.0 if (s.shifted or braking)
                       else ramp(excess, SLIP_ONSET, SLIP_FULL))

        # **Two witnesses.** Lift-off and trail-braking oversteer produce no
        # wheelspin at all, so a wheel-speed model is blind to exactly the case
        # that costs him most. The rotation model sees those and is blind to a
        # standing-start burnout, which the wheels see. The driver is told the
        # larger of the two, because "the rear is going" is one message however
        # it was arrived at - telling him which sensor noticed would be a
        # second thing to learn for no gain.
        slide_level = s.rotation_level
        if s.rotation_confidence == MEDIUM:
            # Kept for the case where the runtime check has only partly
            # settled. With the model validated against the real velocity
            # vector the ordinary path is HIGH and carries no attenuation.
            slide_level *= 0.80
        level = self._traction_env.update(max(wheel_level, slide_level), dt)

        gated = 0.0 if (s.shifted or braking) else excess
        for name in ("approaching", "useful", "excessive", "severe"):
            self._latches[name].update(gated, dt)
        # **The state is named from the latches, not from the level.** The
        # level carries a release tail so the cue does not flicker; the state
        # is a claim about the car right now and must not inherit that tail.
        # Naming it from the enveloped level put the car in APPROACHING_SLIP
        # for 83% of the lap and in GRIPPED for 0.2% of it.
        if self._latches["severe"].active or slide_level >= 0.85:
            s.traction = SEVERE_TRACTION_LOSS
        elif self._latches["excessive"].active or slide_level >= 0.55:
            s.traction = EXCESSIVE_WHEELSPIN
        elif self._latches["useful"].active or slide_level >= 0.25:
            s.traction = USEFUL_SLIP
        elif self._latches["approaching"].active or slide_level > 0.0:
            s.traction = APPROACHING_SLIP
        else:
            s.traction = GRIPPED
        s.traction_level = level
        s.traction_confidence = (HIGH if wheel_level >= slide_level
                                 else s.rotation_confidence)
        s.reasons["traction"] = ("wheel" if wheel_level >= slide_level
                                 else "rotation")

    # --------------------------------------------------------------- braking

    def _braking(self, p: GT7Packet, s: VehicleState, dt: float) -> None:
        axles = self._axle_slip(p)
        if axles is None:
            return
        front, rear = axles
        # Against the SAME learned reference the traction model uses, read at
        # the throttle actually applied - which on the brakes is near zero, and
        # measured, the expected slip there is 0.005 rather than the 0.032 that
        # applies on full throttle. Subtracting a single whole-lap average here
        # would credit the rear axle with three percent less lock than the
        # front on every corner entry.
        offset = self._slip_ref.value(p.throttle) or 0.0
        s.front_lock = max(0.0, 1.0 - front)
        s.rear_lock = max(0.0, 1.0 - (rear - offset))

        if p.brake < PEDAL_ON:
            s.brake_state = BRAKE_FREE
            s.brake_level = 0.0
            s.brake_axle = None
            for name in ("at_limit", "locking"):
                self._latches[name].reset()
            return

        # **The rear axle is NOT shift-blinded here, and that is a finding,
        # not an omission.** Session 41: 87 of 390 LOCKED(rear) frames sat
        # within 0.25 s of a downshift, which looked like the driveline step
        # leaking in - and the driver then confirmed from the seat that the
        # Shelby's downshifts genuinely lock the rears in game. Engine
        # braking through a downshift IS a rear lock; a blind here would
        # hide a real event exactly where his trail-braking lives.
        worst = max(s.front_lock, s.rear_lock)
        s.brake_axle = "front" if s.front_lock >= s.rear_lock else "rear"

        # The scale for the assist actually fitted to this car, and the
        # honesty about whether it was measured on it - see `set_abs`.
        anchors = self._anchors
        s.brake_confidence = LOW if self._borrowed else anchors.confidence

        plateau = max(anchors.lock_floor / PLATEAU_MARGIN,
                      self._plateau.value or 0.0)
        lock_threshold = max(anchors.lock_floor, plateau * PLATEAU_MARGIN)
        s.lock_threshold = lock_threshold
        self._latches["locking"].on = lock_threshold
        self._latches["locking"].off = lock_threshold * 0.82

        # Re-derived per frame like `locking`, and it was not: `at_limit` was
        # pinned to the module constant at construction, so the one threshold
        # that says "past the peak" could not follow a change of assist.
        self._latches["at_limit"].on = anchors.at_limit
        self._latches["at_limit"].off = anchors.at_limit * 0.8
        self._latches["at_limit"].update(worst, dt)
        self._latches["locking"].update(worst, dt)

        # The regulated plateau, learned. Sampled only where the axle is
        # genuinely working, so cruising on the brakes does not drag it down.
        #
        # **Blanked while a lock is running, exactly like the slip reference.**
        # A quantile converges on the quantile of the stream it is shown, and
        # this one was being shown its own detections: every LOCKED frame
        # taught it that locking is normal, at a rise 5.7x faster than the
        # fall. Reported from the seat as "braking starts over the top, learns,
        # then goes very quiet" - about 3.4 s of deep braking moved the
        # threshold up by 0.05, and working that off needs ~19 s of braking
        # below it, more than the rest of the session contained. The upward
        # step alone is withheld during the event: a threshold that is too
        # high hides locks, so the estimator is always allowed to fall.
        # **Fed from the FRONT axle, not from `worst`.** It is a model of the
        # regulator, and the regulator's working point is a front-axle
        # quantity: measured, the front is the worse axle on 97-98.8% of
        # braking frames, so this was already a front plateau on almost every
        # frame and was being taught with rear data on the rest.
        #
        # **And not learned at all with ABS off.** With no regulator there is
        # no plateau to find, and a q0.85 of a stream with nothing regulating
        # it is a quantile of his own pedal discipline - which would report
        # "unusual for Leon" while claiming "past the limit", the same
        # self-referential fault the road bed's scale is allowed to have
        # precisely because it is a bed and this is not.
        if anchors.plateau_learned and s.front_lock > anchors.stable:
            quiet = (not self._latches["locking"].active
                     and s.front_lock < lock_threshold)
            self._plateau.update(s.front_lock, allow_rise=quiet)

        # The rotation witness's view of the rear under braking, kept for the
        # explainer only. The EVENT reaches the driver through the traction
        # channel - the rotation witness in `_traction` is live under braking
        # by design - so the rear stepping out reads in the tyre voice, in
        # the same vocabulary as throttle traction loss. See the account
        # above BRAKE_ROTATION_GATE for the wheel-speed witness this replaced.
        s.rear_unstable = (ramp(s.rotation_level, REAR_ROTATION_ONSET, 1.0)
                           if p.brake >= BRAKE_ROTATION_GATE else 0.0)

        if self._latches["locking"].active:
            s.brake_state = BRAKE_LOCKED
            s.brake_level = 0.65 + 0.35 * ramp(worst, lock_threshold,
                                               anchors.lock_full)
        elif self._latches["at_limit"].active:
            s.brake_state = BRAKE_LIMIT_S
            # **Silent at the optimum, growing as the lock worsens.**
            #
            # The third shape this cue has had, each driven from the seat.
            # The first ramped smoothly across the whole range and changed
            # nothing measurable about his braking. The second put a step AT
            # the optimum - a boundary a smooth ramp cannot mark - and the
            # step did mark it, but it also meant the cue was never quiet: a
            # light presence below the optimum, a jump to 0.22 at it, and
            # most of every heavy stop spent at 0.27-0.47. Reported as "not
            # feeling right and intuitive... a bit of feedback to a lot of
            # feedback", meaning the amplitudes carried no readable meaning.
            #
            # The driver then chose the mapping himself: "quiet at optimum,
            # grow as brake locking worsens." So the boundary is now marked
            # by the ONSET of feedback rather than by a step between two
            # nonzero levels - silence turning into anything is the change a
            # body notices best. Braking done well feels like nothing; the
            # rasp appearing and growing means slip past the peak, heading
            # for the lock threshold; LOCKED stays the alarm it was. The AM
            # rate rides the same number, so the rhythm quickens with it.
            # One ramp, and `rasp_means` says which claim it is making: past
            # the grip peak where a peak resolves, approaching the lock where
            # none does. Same shape, same authority, different sentence - and
            # the explainer carries the difference so a log can be read months
            # later without guessing which assist was fitted.
            s.brake_level = 0.50 * ramp(worst, anchors.rasp_from,
                                        lock_threshold)
        else:
            # Working brakes on the right side of the optimum, including the
            # old STABLE presence band: silence, by the same choice.
            s.brake_state = BRAKE_STABLE_S
            s.brake_level = 0.0

        # A wheel that is unloaded under braking slows because nothing is
        # holding it down, not because the tyre is past its limit. Still worth
        # knowing, but it is not a lock-up, so it is reported as incipient and
        # attenuated rather than at full authority.
        if s.unload > 0.4 and s.brake_state == BRAKE_LOCKED:
            s.brake_state = BRAKE_INCIPIENT
            s.brake_level *= 0.6
            s.reasons["brake"] = "wheel unloaded"
        s.brake_level = self._brake_env.update(s.brake_level, dt)
