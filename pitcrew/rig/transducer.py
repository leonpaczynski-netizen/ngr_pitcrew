"""The tactile transducer as measured, not as specified.

A ButtKicker Gamer Pro on a BKA-PRO amplifier, connected by USB so the amp is
its own Windows audio endpoint. Everything here was established on the bench
on 15 Aug 2026 with the driver in the seat and Windows' own endpoint meter
watching, because the datasheet answers none of the questions that matter and
one of the things it implies turned out to be false.

Nothing in this module makes a sound. It is the set of facts the haptics layer
has to be built against, kept separate so those facts can be read, tested and
argued with on their own.
"""
from __future__ import annotations

# The Windows endpoint. Matched by name rather than index, because indices
# renumber between sessions and the name does not.
DEVICE_NAME = "Speakers (ButtKicker PRO)"

# WASAPI reports this endpoint as **stereo at 48 kHz**, and opening it with 4
# or 8 channels fails outright (-9998). The 8-channel views under MME,
# DirectSound and WDM-KS are routes to the same hardware and are not worth
# taking - see `audio_devices._HOST_API_ORDER`. SimHub drove this rig in a
# Quad configuration with all four corners at 100; that does not survive the
# move and does not need to, because there is one physical piston.
CHANNELS = 2
SAMPLE_RATE = 48000

# **Shared, not exclusive.** Exclusive mode opens on this device, reports
# 21.3 ms and a sensible rate, and renders nothing at all: the endpoint
# metered 0.0000 for a whole call and the driver felt nothing, while the same
# tone shared metered 0.125 and was felt. See `audio_devices
# .open_exclusive_output` for the full account. The isolation that was wanted
# from it survives anyway - the amp is its own endpoint and is not the Windows
# default - but the APO bypass does not, so Bass Management and Loudness
# Equalization are in the path and must be off on this endpoint.
EXCLUSIVE = False

# Both channels reach the piston and they SUM: driven together the same tone
# was clearly stronger than either alone. So the mono mix goes to both at half
# amplitude, summing to the equivalent of one channel at full - no headroom
# thrown away to the doubling, and a channel failing costs 6 dB rather than
# everything.
CHANNELS_SUM = True
PER_CHANNEL_SCALE = 0.5

# The usable band, and it is the amplifier that decides it, not the transducer.
#
#   * The BKA-PRO has a FIXED low-cut at 25 Hz, 12 dB/octave. Confirmed: 20 Hz
#     at -18 dBFS was felt as nothing at all while 40 Hz at the same level was
#     strong. Synthesising below this is excursion spent for no output, and
#     excursion is what bottoms a piston.
#   * The high-cut is user-selectable from 40 to 160 Hz. **This rig is set to
#     160**, read off the amp's own display - the best case, and it means every
#     band in the driver's SimHub profile fits unchanged, wheel rumble at
#     112-152 Hz included.
#
# The transducer is specified 5-200 Hz and the amp 10-300 Hz. Neither is the
# constraint. The switch is.
BAND_LOW_HZ = 25.0
BAND_HIGH_HZ = 160.0
AMP_HIGH_CUT_HZ = 160.0

# **The rig's actual response, measured 16 Aug 2026.** Nine equal-amplitude
# tones at -18 dBFS, one per run, rated 0-3 by the driver in the seat. The
# endpoint metered exactly 0.125 for every one, so the digital side was
# identical and every difference below is the rig.
#
#     30 Hz  2      70 Hz  1   <- null
#     40 Hz  3      85 Hz  2
#     50 Hz  3     100 Hz  2
#     60 Hz  2     120 Hz  1
#                  140 Hz  0.5
#
# This is a resonance structure, not a rolloff: two usable regions, 40-55 Hz
# and 85-105 Hz, separated by a dead spot at 70 and falling away above 120.
# It is the seat, the mounts and the chassis as much as the transducer.
#
# **It also refutes the model every earlier decision here was built on.** That
# model was "felt output falls as 1/f-squared", extrapolated from a single
# measured pair - 20 Hz felt as nothing, 40 Hz felt as strong - which the
# model itself contradicts, because 1/f-squared predicts 20 Hz should be the
# most felt frequency of all. Three rounds of trims were sized against it and
# each one moved an effect the wrong way or not far enough.
#
# And it makes the driver's SimHub gains legible at last. His highest gain is
# wheel-spin at 82-108 Hz (70.0) and his lowest is RPM at 34-42 Hz (9.5): he
# turned up what sat in a weak region and turned down what sat on a peak. The
# gains are a compensation curve for THIS response, arrived at by feel over
# eight days - which is why a systematic 1/f-squared weighting on top of them
# was rightly rejected, though not for the reason given at the time.
# **Re-measured 12 Sep 2026 after the vertical remount.** Same method - nine
# tones at -18 dBFS, one per invocation, rated 0-3 in the seat, endpoint
# metered 0.124-0.125 for every one so the digital side was identical and
# every difference is the rig. Amp 35. Control (50 Hz) re-run at the end and
# came back unchanged, so the run stands. `docs/RIG-SWEEP_2026-09-12.md`.
#
#     Aug (horizontal)          Sep (vertical)
#     30 Hz 2                   30 Hz 2
#     40 Hz 3                   40 Hz 2
#     50 Hz 3                   50 Hz 3
#     60 Hz 2                   60 Hz 4  <- off the top of the scale
#     70 Hz 1  <- null          70 Hz 2  <- the null is GONE
#     85 Hz 2                   85 Hz 2
#    100 Hz 2                  100 Hz 2
#    120 Hz 1                  120 Hz 2
#    140 Hz 0.5                140 Hz 2
#
# **The 4 at 60 Hz is a real reading, not a typo.** The 0-3 scale ran out and
# the driver said so; it was confirmed scale-free by paired comparison against
# 50 Hz ("60 is stronger") and corroborated acoustically - 60 Hz showed the
# loudest fundamental of the set by 18 dB.
#
# **What changed and why it matters more than the numbers.** The old table was
# two narrow peaks either side of a dead spot, which is the signature of a
# COMPLIANT path: the seat brackets' bending modes gave resonant gain at
# 40-55 and an antiresonance at 70. Turning the transducer vertical moved the
# drive from those brackets' weak axis onto their stiff one (75x6 flat bar
# bends 156x more easily one way than the other), so the bracket modes stopped
# shaping the response. What is left is flat-at-2 from 70 to 140 plus the
# transducer's OWN resonance at 60, previously masked.
#
# So the constraint that shaped every placement decision before this - "two
# narrow usable regions, so frequency separates nothing" - no longer holds.
FELT_RESPONSE = ((30.0, 2.0), (40.0, 2.0), (50.0, 3.0), (60.0, 4.0),
                 (70.0, 2.0), (85.0, 2.0), (100.0, 2.0), (120.0, 2.0),
                 (140.0, 2.0))
# The one remaining peak is the reaction mass's own resonance - and it is the
# LEAST usable frequency on the rig, not the most, because excursion peaks
# there too and it runs out of travel 12 dB before anywhere else. Felt
# response and usable range point in opposite directions here; see
# `KNOCK_ONSET_DBFS` and `PERCEPTION_FLOOR_DBFS` below, which together are
# what placement should actually be decided on.
FELT_PEAK_LOW = (50.0, 60.0)
FELT_PEAK_HIGH = (70.0, 140.0)
# **There is no null any more.** `FELT_NULL_HZ` was 70.0 and is deliberately
# not replaced: it was the brackets' antiresonance, not a property of the
# transducer, and the stiff path does not have one. Nothing may route around
# a dead spot that no longer exists.
FELT_NULL_HZ = None

# **What the driver can FEEL, by frequency** - measured 12 Sep 2026 by adaptive
# staircase, binary felt/not-felt, amp 35, driver in the seat. Nine catch
# trials (silent, presented at random) drew zero false alarms, so these came
# from sensation rather than expectation. Biased about 1 dB low by the method.
#
# Only four frequencies were measured; the rest of the band is unknown and is
# deliberately not interpolated here, because a floor is the kind of number
# that gets quoted as though it were measured everywhere.
PERCEPTION_FLOOR_DBFS = ((40.0, -25.0), (60.0, -35.0), (100.0, -27.5),
                         (120.0, -28.5))

# **Usable range = knock ceiling - perception floor, and THIS is what an effect
# needs, not loudness.** A cue with 3 dB of range is a switch; one with 25 dB
# is an instrument.
#
#     40 Hz   19 dB
#     60 Hz   17 dB   <- the most SENSITIVE frequency, and the least usable
#    100 Hz   22 dB
#    120 Hz   25.5 dB <- the best, and August's table called it dead
#
# 60 Hz is felt 10 dB earlier than anywhere else and has the narrowest range
# on the rig, because it runs out of travel almost immediately. Every
# placement decision made before 12 Sep 2026 was made on sensitivity alone.


def felt_response(frequency: float) -> float:
    """How well this rig delivers a given frequency, 0-3, by interpolation.

    Measured, not modelled - see `FELT_RESPONSE`. Use it to place an effect,
    not to scale one: the driver's gains already carry his own compensation
    and multiplying by this as well would count it twice.
    """
    points = FELT_RESPONSE
    if frequency <= points[0][0]:
        return points[0][1]
    if frequency >= points[-1][0]:
        return points[-1][1]
    for (low_hz, low), (high_hz, high) in zip(points, points[1:]):
        if low_hz <= frequency <= high_hz:
            span = high_hz - low_hz
            return low + (high - low) * (frequency - low_hz) / span
    return points[-1][1]

# **The spectral plan, and why there is one.**
#
# Six effects used to be placed one at a time, each against its own argument,
# and two of them ended up in the same twelve hertz: wheel-spin at 82-108 and
# road rumble at 86-104. The road bed is live for 95% of a lap and wheel-spin
# for 9%, on one piston, summed into one signal - so the continuous immersion
# effect sat directly on top of the limit cue for the whole of every lap. That
# is the "immersion masking performance" failure in its purest form, and no
# amount of gain on wheel-spin fixes it, because raising it raises what it has
# to beat once the limiter closes.
#
# So placement is decided here, for the whole set at once, against the measured
# response above. Two regions deliver: 28-66 Hz and 80-115 Hz. Everything else
# is either below the amplifier's low-cut, in the 70 Hz null, or in the falling
# region above 120.
#
# The organising idea is physical rather than arbitrary, because a tactile
# vocabulary has to be learnable without being memorised:
#
#     **low is the car, high is the contact patch.**
#
# Engine, road, brakes, impacts and chassis load - everything that is mass
# moving - lives in the low region, in the order a driver would expect: the
# quietest continuous thing at the bottom, the sharpest events in the middle
# where this rig is strongest. Tyre slip - the only thing here that is
# happening at the road surface rather than in the structure - has the whole of
# the high region to itself, so "the tyres are letting go" is the one message
# that never shares a frequency with anything.
#
#     band        felt   effect          class      why here
#     28-34 Hz    1.8-2.4  engine        bed        weakest region, lowest value
#     34-41 Hz    2.4-3.0  road          bed        the thing he is inside all lap
#     40-50 Hz    3.0-3.0  brake limit   CRITICAL   strongest region, highest value
#     50 Hz       3.0      driveline     transient  a single confirming tick
#     52-60 Hz    2.9-2.0  impact        transient  strong, and clear of the null
#     56-66 Hz    2.4-1.4  chassis load  state      compensated across its band
#     88-108 Hz   2.0-1.9  rear traction CRITICAL   the high region, undivided
#
# The overlaps are deliberate and are separated in TIME rather than in
# frequency. Brake and impact share 44-50 Hz; a brake cue is a pulse train
# lasting the whole braking zone and an impact is a 120 ms one-shot, and the
# body has no trouble with that. What the body cannot do is separate two
# continuous rasps in the same band, which is exactly what the old placement
# asked of it.
BAND_PLAN = (
    ("engine",        28.0,  34.0),
    ("road",          34.0,  41.0),
    ("brake_limit",   40.0,  50.0),
    ("driveline",     50.0,  50.0),
    ("impact",        52.0,  60.0),
    ("chassis_load",  56.0,  66.0),
    ("rear_traction", 88.0, 108.0),
)

# **Amplitude modulation, and why it is the largest unused dimension here.**
#
# There are two usable regions and seven things to say, so frequency alone
# cannot carry the vocabulary. What it can carry is character, and the cheapest
# character available is the rate at which an effect pulses.
#
# The body is good at this in a way it is not good at carrier frequency. At
# 40-100 Hz the receptors involved integrate rather than resolve, so 44 Hz and
# 52 Hz feel like the same thing at different strengths. A 44 Hz tone pulsed
# eight times a second and the same tone pulsed sixteen times a second do not
# feel like the same thing at all - flutter in the 5-20 Hz range is
# discriminated well, and it is also how the two events being reported here
# actually feel in a real car: a locking tyre judders and a spinning one
# rasps.
#
# Above about 20 Hz the modulation fuses with the carrier and stops being a
# rate, which is why both ranges stop short of it.
AM_RANGE_HZ = (5.0, 16.0)
AM_MAX_DEPTH = 0.60

# **The reference.** 40 Hz at -6 dBFS, with the amp at 50 - which is its
# maximum - was reported very strong and did not knock the piston. That fixes
# what "full" means: every effect gain below is a fraction of a level someone
# has actually felt, rather than a number floating against an unknown knob.
#
# Recorded so that "the haptics feel weak" is answerable. If the mix has not
# changed and this has, the knob moved.
CALIBRATION_FREQ_HZ = 40.0
CALIBRATION_DBFS = -6.0
CALIBRATION_AMPLITUDE = 0.5
# **The bench calibration put this at 50, which is the amplifier's maximum,
# and racing has since moved it.** Driving at a master gain of 2 tripped the
# amp's protection and needed a full PC restart to clear; the settled
# operating point is amp 35 with a master of 1, which leaves real headroom on
# the knob for the first time.
#
# Kept as a record rather than a target. Every effect gain is a fraction of
# the digital reference above, which has not moved - this is here so that "the
# haptics feel weak" can be answered by asking whether the knob is where it
# was.
AMP_VOLUME_AT_CALIBRATION = 35
AMP_VOLUME_MAX = 50

# **The knob had to come down after the remount: 35 -> 29.** Measured in the
# seat on 12 Sep 2026, not derived. At 35 the vertical mount put `impact` into
# the transducer's end stops on every hard kerb - the driver heard it, and a
# replay of twelve of his own laps put that effect at 0.489 at 56 Hz against a
# knock onset near -18 dBFS there.
#
# 29 was chosen as roughly 6 dB down and then CONFIRMED by test rather than by
# arithmetic: `impact` at full intensity and `rear_traction` at full severity
# were each played through the real mix and reported clean, the latter
# "feels good".
#
# What it costs, and it is worth saying because it will be felt: about 6 dB off
# everything. The event cues keep 9-16 dB over the measured perception floors
# and survive. The BEDS do not - `road`, `engine` and `chassis_load` were
# already sitting at or below the floor at 35 and go under it at 29. The rig
# reads sparse: events without a bed beneath them.
#
# That is a stopgap for one race, not a setting to build on. The real answer is
# a spectral plan that puts each effect where the rig has range for it, which
# needs `docs/RESEARCH-VEHICLE-FREQUENCIES_2026-09-12.md` first, because the
# 130 Hz trial showed placement is bounded by what a band MEANS to the driver
# and not only by what the hardware can deliver there.
AMP_VOLUME_RACE_2026_09_13 = 29

# What is left above the reference, and it is deliberate rather than spare.
# Sustained content sits at or below -6 dBFS; a discrete event may use the
# 6 dB above it. That reserve is what makes a kerb strike read as an EVENT
# over the road bed rather than as the bed briefly getting louder - on one
# transducer, with everything summed into one signal, contrast is the only
# way an event stays legible.
SUSTAINED_CEILING = CALIBRATION_AMPLITUDE      # -6 dBFS
TRANSIENT_CEILING = 0.71                       # -3 dBFS
# The backstop. The BKA-PRO's DC-protect trips on excessive input and stops
# the unit until it is reset - so a limiter here is not about protecting the
# hardware from damage, it is about not having the transducer mute itself
# mid-race.
HARD_LIMIT = 0.89                              # -1 dBFS

# **The ceiling is a CURVE, not a number, and this is the constraint that
# actually binds this rig.** Measured 12 Sep 2026, amp 35, driver in the seat,
# after the transducer was remounted vertically - see
# `docs/RIG-SWEEP_2026-09-12.md`.
#
# Mounted vertically the reaction mass sits off-centre under gravity, so the
# travel available in one direction is reduced and the mass reaches its stop
# at levels the horizontal mount never approached. Where that happens depends
# entirely on frequency, because excursion peaks at the mass's own resonance
# (60 Hz here) and falls away either side.
#
# Each entry is the level at which knock began, in dBFS. `knock_ceiling()`
# applies a safety margin below it.
#
#     30 Hz  none to -3      85 Hz  -6
#     40 Hz  none to -3 *   100 Hz  -6
#     50 Hz  -6             120 Hz  none to -3
#     60 Hz  -18            150 Hz  none to -3
#     70 Hz  -9
#
# * 40 Hz shows no SUSTAINED knock, but the driver heard two discrete thuds in
#   a ten-second tone at -12 dBFS. Intermittent contact is not measurable by
#   the instrument built for this (its impulse detector fired on ~70% of all
#   rows and was withdrawn), so 40 Hz carries the driver's figure, not a
#   machine's, and is the one entry here that is an ear rather than a curve.
#
# **Why this exists at all.** `SUSTAINED_CEILING` is one scalar and the
# limiter was frequency-blind, so it drove `impact` to 0.489 at 56 Hz while
# believing it was inside budget - about 13 dB past where that frequency runs
# out of travel, on every kerb strike of every lap. A single ceiling cannot
# express a constraint that moves by 15 dB across the band.
KNOCK_ONSET_DBFS = ((30.0, -3.0), (40.0, -12.0), (50.0, -6.0), (60.0, -18.0),
                    (70.0, -9.0), (85.0, -6.0), (100.0, -6.0), (120.0, -3.0),
                    (150.0, -3.0))
# Knock is a cliff, not a slope - 6 dB separated clean from knocking at 60 Hz -
# so the margin is small on purpose. Bigger would cost real output everywhere
# to buy nothing.
KNOCK_MARGIN_DB = 3.0


def knock_ceiling(frequency: float) -> float:
    """The largest amplitude this rig can deliver at `frequency` without knock.

    Interpolated in dB between measured points, with `KNOCK_MARGIN_DB` of
    margin, and never above `TRANSIENT_CEILING` - this is a cap, not a target.

    Measured, not modelled. Outside the measured span it holds the end value
    rather than extrapolating: below 30 Hz the amplifier's 25 Hz low-cut makes
    the question moot, and above 150 Hz nothing is placed.
    """
    points = KNOCK_ONSET_DBFS
    if frequency <= points[0][0]:
        onset = points[0][1]
    elif frequency >= points[-1][0]:
        onset = points[-1][1]
    else:
        onset = points[-1][1]
        for (lo_hz, lo), (hi_hz, hi) in zip(points, points[1:]):
            if lo_hz <= frequency <= hi_hz:
                span = hi_hz - lo_hz
                onset = lo + (hi - lo) * (frequency - lo_hz) / span
                break
    return min(TRANSIENT_CEILING, float(10 ** ((onset - KNOCK_MARGIN_DB) / 20)))


def knock_ceiling_for_band(freq_lo: float, freq_hi: float) -> float:
    """The safe amplitude for an effect occupying `freq_lo`..`freq_hi`.

    **Evaluated at the TOP of the band, not the worst point in it**, because
    in this synth pitch rises with the effect's own intensity: an effect is
    only down at `freq_lo` when it is quiet, and only reaches full amplitude
    at `freq_hi`. The worst frequency and the worst amplitude never coincide.

    Taking the minimum across the band instead - the obvious reading, and the
    first thing written here - would have throttled `brake_limit` by 4.6 dB to
    protect it at 40 Hz, a level it only ever visits at a whisper.
    """
    return knock_ceiling(float(freq_hi) if freq_hi else float(freq_lo))

# Whether the amplifier has anything left. It has: 35 of 50, about 3 dB.
#
# That matters more than it looks. Five places in this codebase used to say
# the amp was exhausted - one of them spoken to the driver after every haptics
# test - which sent him to the digital master instead. The master drives the
# limiter, the duty cycle and (because frequency is interpolated from
# amplitude) the pitch of every effect. The amp's knob drives none of those.
# When it is not strong enough, the knob is the right answer.
AMP_AT_MAXIMUM = AMP_VOLUME_AT_CALIBRATION >= AMP_VOLUME_MAX
