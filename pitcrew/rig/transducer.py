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

# The amp is at its maximum, so there is no knob left to turn up. Anything
# that needs to be stronger has to come out of the 6 dB above the reference,
# and once that is gone the answer is a different effect balance rather than
# more gain. Worth knowing before tuning starts.
AMP_AT_MAXIMUM = AMP_VOLUME_AT_CALIBRATION >= AMP_VOLUME_MAX
