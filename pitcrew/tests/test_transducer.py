"""The measured rig, pinned.

These are not really tests of behaviour - `transducer.py` has none. They exist
because every figure in it was paid for with a driver sitting in the seat
saying what he could feel, and a number arrived at that way must not drift
back to a guess when someone tidies up later.
"""
from __future__ import annotations

from pitcrew.rig import transducer as t


def test_the_band_is_the_amplifiers_and_not_the_transducers():
    """The ButtKicker is specified 5-200 Hz and the amp 10-300 Hz. Neither is
    the constraint - the amp's switchable high-cut is, and it reads 160."""
    assert t.BAND_LOW_HZ == 25.0
    assert t.BAND_HIGH_HZ == t.AMP_HIGH_CUT_HZ == 160.0


def test_nothing_is_synthesised_below_the_fixed_low_cut():
    """20 Hz at -18 dBFS was felt as nothing while 40 Hz at the same level was
    strong. Below the corner, excursion is spent for no output - and excursion
    is what bottoms a piston."""
    assert t.BAND_LOW_HZ >= 25.0


def test_the_rumble_band_still_fits():
    """The driver's SimHub wheel-rumble effect ran 112-152 Hz. Had the amp's
    high-cut been at its minimum of 40 Hz, every effect would have had to be
    crammed below it and spectral separation would have gone with it."""
    assert t.BAND_HIGH_HZ >= 152.0


def test_the_channels_sum_so_each_carries_half():
    """Both channels drive the piston and together are clearly stronger than
    either alone. Writing the mono mix to both at full scale would spend 6 dB
    on the doubling."""
    assert t.CHANNELS_SUM is True
    assert t.PER_CHANNEL_SCALE == 0.5


def test_exclusive_mode_is_recorded_as_not_working_here():
    """It opens, reports 21.3 ms, and renders nothing."""
    assert t.EXCLUSIVE is False


def test_wasapi_gives_two_channels_not_the_quad_simhub_used():
    assert t.CHANNELS == 2
    assert t.SAMPLE_RATE == 48000


def test_a_transient_may_be_louder_than_anything_sustained():
    """One piston, everything summed into one signal - so contrast is the only
    thing that keeps a kerb strike legible over the road bed."""
    assert t.TRANSIENT_CEILING > t.SUSTAINED_CEILING
    assert t.HARD_LIMIT > t.TRANSIENT_CEILING
    assert t.HARD_LIMIT < 1.0, "no headroom left before the DC-protect trips"


def test_the_reference_is_a_level_someone_actually_felt():
    """40 Hz at -6 dBFS, amp at 50: very strong, no knock. Every effect gain
    is a fraction of that rather than of a guess."""
    assert t.CALIBRATION_FREQ_HZ == 40.0
    assert t.CALIBRATION_DBFS == -6.0
    assert abs(t.CALIBRATION_AMPLITUDE - 0.5) < 1e-9
    assert t.SUSTAINED_CEILING == t.CALIBRATION_AMPLITUDE


def test_the_amp_has_no_room_left_to_turn_up():
    """It calibrated at its maximum. Anything needing to be stronger has to
    come out of the 6 dB above the reference, and after that the answer is a
    different balance rather than more gain."""
    assert t.AMP_AT_MAXIMUM is True
