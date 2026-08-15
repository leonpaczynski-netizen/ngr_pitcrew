"""The haptic signal, checked without a transducer in the room.

This is the part that runs 48,000 times a second inside an audio callback, so
the things worth asserting are not "does it make a noise" but the ones that go
wrong silently: a discontinuity between blocks, a level that steps instead of
ramping, an effect placed outside what the amplifier passes, a peak that trips
the amp's DC-protect and stops the unit for the rest of the race.

A click at 150 W into a 1 lb piston is a thump, so continuity is the headline
here and most of these are really one assertion asked in different ways.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.rig import transducer
from pitcrew.rig.synth import (
    PORSCHE_RSR_17,
    EffectSpec,
    HapticMix,
    to_stereo,
)

BLOCK = 512


def _full(mix: HapticMix, value: float = 0.5) -> np.ndarray:
    return np.full(len(mix.specs), value, dtype=np.float32)


def _settle(mix: HapticMix, intensities, blocks: int = 40) -> np.ndarray:
    out = None
    for _ in range(blocks):
        out = mix.render(intensities, BLOCK).copy()
    return out


# ------------------------------------------------------------- the profile

def test_the_six_effects_are_the_ones_he_actually_had_on():
    """Twenty more exist in SimHub and were all disabled. Porting those would
    be inventing a preference he never expressed."""
    assert len(PORSCHE_RSR_17) == 6
    assert {s.name for s in PORSCHE_RSR_17} == {
        "wheels_spin_lock", "gear", "wheels_rumble", "traction_loss",
        "wheels_impact", "rpm"}


def test_his_tuned_gains_and_bands_came_across_unchanged():
    """Eight days of tuning, in his numbers rather than in defaults."""
    by_name = {s.name: s for s in PORSCHE_RSR_17}
    assert by_name["wheels_spin_lock"].gain == 70.00
    assert (by_name["wheels_rumble"].freq_lo,
            by_name["wheels_rumble"].freq_hi) == (112.0, 152.0)
    assert by_name["gear"].freq_lo == 48.0
    assert by_name["gear"].freq_hi == 0.0, "the gear thump is a single tone"


def test_every_effect_fits_inside_what_this_amplifier_passes():
    for spec in PORSCHE_RSR_17:
        top = spec.freq_hi or spec.freq_lo
        assert spec.freq_lo >= transducer.BAND_LOW_HZ
        assert top <= transducer.BAND_HIGH_HZ


def test_an_effect_outside_the_band_is_refused_at_construction():
    """Below the amp's fixed low-cut is excursion spent for no output, and
    excursion is what bottoms a piston. Better a ValueError than a mystery."""
    with pytest.raises(ValueError, match="outside"):
        EffectSpec("too_low", 50.0, 10.0, 20.0)
    with pytest.raises(ValueError, match="outside"):
        EffectSpec("too_high", 50.0, 150.0, 400.0)


# --------------------------------------------------------------- continuity

def test_nothing_jumps_between_blocks():
    """The sample either side of a block boundary is where a click lives, and
    a click at 150 W is a thump. Phase is carried forward for exactly this."""
    mix = HapticMix(block=BLOCK)
    intensities = _full(mix, 0.6)
    _settle(mix, intensities)

    first = mix.render(intensities, BLOCK).copy()
    second = mix.render(intensities, BLOCK).copy()
    seam = abs(float(second[0]) - float(first[-1]))
    biggest_inside = float(np.max(np.abs(np.diff(first))))
    assert seam <= biggest_inside * 3.0, (
        f"the block boundary jumped by {seam:.5f} where the largest step "
        f"inside a block is {biggest_inside:.5f}")


def test_a_frequency_change_bends_the_wave_rather_than_jumping_it():
    """Wheelspin rises in pitch as it worsens. Recomputing phase from an
    absolute sample index would click on every one of those changes."""
    mix = HapticMix(specs=(PORSCHE_RSR_17[0],), block=BLOCK)
    quiet = np.array([0.2], dtype=np.float32)
    loud = np.array([0.9], dtype=np.float32)
    _settle(mix, quiet)
    before = mix.render(quiet, BLOCK).copy()
    after = mix.render(loud, BLOCK).copy()
    seam = abs(float(after[0]) - float(before[-1]))
    assert seam < 0.05, f"pitch change clicked, seam {seam:.4f}"


def test_a_level_change_ramps_across_the_block_and_does_not_step():
    mix = HapticMix(specs=(PORSCHE_RSR_17[2],), block=BLOCK)
    off = np.array([0.0], dtype=np.float32)
    on = np.array([1.0], dtype=np.float32)
    _settle(mix, off, blocks=5)
    first_on = mix.render(on, BLOCK).copy()
    start = float(np.max(np.abs(first_on[:32])))
    end = float(np.max(np.abs(first_on[-32:])))
    assert start < end, "the effect arrived at full level instantly"


def test_silence_in_gives_silence_out():
    mix = HapticMix(block=BLOCK)
    out = _settle(mix, np.zeros(len(mix.specs), dtype=np.float32))
    assert float(np.max(np.abs(out))) < 1e-3


# -------------------------------------------------------------- protection

def test_the_output_never_passes_the_hard_limit():
    """The BKA-PRO's DC-protect trips on excessive input and stops the unit
    until it is reset. The limiter is the difference between one loud moment
    and no haptics for the rest of the race."""
    mix = HapticMix(block=BLOCK)
    everything = _full(mix, 1.0)
    for _ in range(60):
        out = mix.render(everything, BLOCK)
        assert float(np.max(np.abs(out))) <= transducer.HARD_LIMIT + 1e-6


def test_reaching_the_limiter_is_counted_because_it_means_the_mix_is_wrong():
    mix = HapticMix(block=BLOCK)
    for _ in range(60):
        mix.render(_full(mix, 1.0), BLOCK)
    assert isinstance(mix.limited_blocks, int)


def test_a_transient_may_be_louder_than_anything_sustained():
    """One piston, everything summed into one signal - so contrast is the only
    thing that keeps a gear shift legible over the road bed."""
    by_name = {s.name: s for s in PORSCHE_RSR_17}
    assert by_name["gear"].transient is True
    assert by_name["wheels_rumble"].transient is False


def test_the_output_is_finite_under_everything_at_once():
    mix = HapticMix(block=BLOCK)
    for value in (0.0, 0.3, 1.0, 0.0, 1.0):
        out = _settle(mix, _full(mix, value), blocks=10)
        assert bool(np.all(np.isfinite(out)))


# ------------------------------------------------------------ the two ears

def test_the_mix_goes_to_both_channels_at_half():
    """Both reach the piston and they sum, measured. Full scale on both would
    spend 6 dB on the doubling; half on each sums back to one at full, and a
    channel failing then costs 6 dB rather than everything."""
    mono = np.full(8, 0.4, dtype=np.float32)
    out = np.zeros((8, 2), dtype=np.float32)
    to_stereo(mono, out, 8)
    assert np.allclose(out[:, 0], 0.2)
    assert np.allclose(out[:, 1], out[:, 0])


# ------------------------------------------------------------- the budget

def test_a_block_costs_a_small_fraction_of_its_own_duration():
    """Measured at about 1% for a 1024-sample block with every effect running.
    Asserted loosely, because this runs on whatever machine CI has - the point
    is to catch a change that makes it an order of magnitude worse, which is
    what reintroducing a per-sample Python loop would do.
    """
    import time

    mix = HapticMix(block=1024)
    everything = _full(mix, 0.5)
    for _ in range(20):
        mix.render(everything, 1024)
    start = time.perf_counter()
    for _ in range(100):
        mix.render(everything, 1024)
    each = (time.perf_counter() - start) / 100
    budget = 1024 / transducer.SAMPLE_RATE
    assert each < budget * 0.25, (
        f"{each * 1e6:.0f} us against a {budget * 1e6:.0f} us budget - "
        f"too close to real time to be safe in a callback")


# --------------------------------------------------- his gain chain, restored

def test_an_effect_that_fires_at_all_starts_at_his_minimum_force():
    """Reported from the seat as "worked fine, just very weak".

    His profile puts `MinimumForce` at 12-28 on every continuous effect, so an
    effect that fires starts there rather than creeping up from nothing. The
    first build implemented a plain linear intensity and left it out, which
    turns every ordinary event into a whisper - the raw intensities out of
    `effects` sit low most of the time and a linear map keeps them there.
    """
    rumble = {s.name: s for s in PORSCHE_RSR_17}["wheels_rumble"]
    assert rumble.min_force == 28.0
    just_over = rumble.shape(rumble.threshold / 100.0 + 0.01)
    assert just_over >= 0.28, "it crept up from nothing instead of starting"


def test_below_the_threshold_nothing_happens_at_all():
    """The floor must not make the threshold meaningless - order matters."""
    impact = {s.name: s for s in PORSCHE_RSR_17}["wheels_impact"]
    assert impact.threshold == 55.0
    assert impact.shape(0.30) == 0.0
    assert impact.shape(0.90) > 0.0


def test_gamma_lifts_the_small_end_without_moving_the_top():
    sensitive = EffectSpec("a", 50.0, 40.0, 60.0, gamma=1.6)
    flat = EffectSpec("b", 50.0, 40.0, 60.0, gamma=1.0)
    assert sensitive.shape(0.3) > flat.shape(0.3)
    assert sensitive.shape(1.0) == pytest.approx(flat.shape(1.0))


def test_gains_are_relative_to_the_loudest_effect_not_to_an_abstract_full():
    """SimHub's gains are weights inside its own chain - his sat under a
    profile gain of 49.8. Read as fractions of full scale, even the strongest
    effect peaked at 0.35 against a reference of 0.5 he called very strong."""
    mix = HapticMix(block=BLOCK)
    loudest = max(s.gain for s in mix.specs)
    strongest = mix.specs[[s.gain for s in mix.specs].index(loudest)]
    index = mix.names.index(strongest.name)
    ceiling = (transducer.TRANSIENT_CEILING if strongest.transient
               else transducer.SUSTAINED_CEILING)
    assert mix._scale[index] == pytest.approx(ceiling)


def test_the_balance_between_effects_is_still_his():
    """Normalising must not reorder them - the proportions are the tuning."""
    mix = HapticMix(block=BLOCK)
    by_gain = sorted(mix.specs, key=lambda s: s.gain)
    scales = [mix._scale[mix.names.index(s.name)] for s in by_gain
              if not s.transient]
    assert scales == sorted(scales)


def test_the_master_gain_moves_everything_and_still_respects_the_limiter():
    """The amplifier is at its maximum, so "everything stronger" has nowhere
    else to come from."""
    quiet = HapticMix(block=BLOCK, master=0.5)
    loud = HapticMix(block=BLOCK, master=3.0)
    intensities = _full(quiet, 0.5)
    a = float(np.max(np.abs(_settle(quiet, intensities))))
    b = float(np.max(np.abs(_settle(loud, _full(loud, 0.5)))))
    assert b > a
    assert b <= transducer.HARD_LIMIT + 1e-6


def test_an_impossible_shaping_is_refused():
    with pytest.raises(ValueError):
        EffectSpec("bad", 50.0, 40.0, 60.0, gamma=0.0)
    with pytest.raises(ValueError):
        EffectSpec("bad", 50.0, 40.0, 60.0, min_force=140.0)


def test_a_transient_can_actually_get_past_the_bed():
    """The headroom above the sustained ceiling only means something if the
    limiter lets a peak reach it.

    It used to soft-clip at the SUSTAINED ceiling, so the summed output was
    pinned there whatever went in - measured at 0.499 across every master gain
    from 1 to 4 - and a gear shift could never be louder than the road it was
    heard over. The contrast the whole one-piston design rests on was being
    removed by its own protection.
    """
    mix = HapticMix(block=BLOCK, master=3.0)
    peak = 0.0
    for _ in range(80):
        out = mix.render(_full(mix, 1.0), BLOCK)
        peak = max(peak, float(np.max(np.abs(out))))
    assert peak > transducer.SUSTAINED_CEILING * 1.2, (
        f"the mix is still clamped at the bed's ceiling - peaked at {peak:.3f}")
    assert peak <= transducer.HARD_LIMIT + 1e-6


def test_compression_is_counted_so_a_squashed_mix_can_be_seen():
    """Driving the limiter constantly is not the limiter working - it is the
    level being wrong, and it holds the transducer near full scale against an
    amplifier whose rating assumes a one-third duty cycle."""
    hot = HapticMix(block=BLOCK, master=4.0)
    for _ in range(60):
        hot.render(_full(hot, 1.0), BLOCK)
    calm = HapticMix(block=BLOCK, master=0.5)
    for _ in range(60):
        calm.render(_full(calm, 0.3), BLOCK)
    assert hot.limited_blocks > calm.limited_blocks
    assert calm.limited_blocks == 0
