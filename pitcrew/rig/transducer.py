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
FELT_RESPONSE = ((30.0, 2.0), (40.0, 3.0), (50.0, 3.0), (60.0, 2.0),
                 (70.0, 1.0), (85.0, 2.0), (100.0, 2.0), (120.0, 1.0),
                 (140.0, 0.5))
# Where the rig actually delivers. Anything an effect needs felt belongs in
# one of these; anything placed between them is spent for nothing.
FELT_PEAK_LOW = (40.0, 55.0)
FELT_PEAK_HIGH = (85.0, 105.0)
FELT_NULL_HZ = 70.0


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

# Whether the amplifier has anything left. It has: 35 of 50, about 3 dB.
#
# That matters more than it looks. Five places in this codebase used to say
# the amp was exhausted - one of them spoken to the driver after every haptics
# test - which sent him to the digital master instead. The master drives the
# limiter, the duty cycle and (because frequency is interpolated from
# amplitude) the pitch of every effect. The amp's knob drives none of those.
# When it is not strong enough, the knob is the right answer.
AMP_AT_MAXIMUM = AMP_VOLUME_AT_CALIBRATION >= AMP_VOLUME_MAX
