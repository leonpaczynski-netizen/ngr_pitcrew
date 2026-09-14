"""Rev A is the first profile built from the two measured curves.

Until 12 Sep 2026 only one of them existed - `FELT_RESPONSE`, a 0-3 rating of
how well the rig delivers a frequency. The sweep added the other two: where the
transducer runs out of travel (`KNOCK_ONSET_DBFS`) and where the driver stops
feeling anything (`PERCEPTION_FLOOR_DBFS`). Laying the effects' real in-car
levels against both showed the rig's range allocated to one end - the beds
below the floor, two events past the stops.

These tests pin the SHAPE of the fix, not the exact trims. A trim is allowed to
move when the rig is re-measured; what may not happen again is an effect
sitting outside the range the hardware and the driver jointly define, with
nothing noticing.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pitcrew.rig import synth, transducer  # noqa: E402

# What each effect actually reaches in the car, replayed over twelve of his own
# laps through the real derivers and the real gain chain (`tools/rig_levels.py`,
# 12 Sep 2026), at the trims in force that day.
FIRES_AT = {"engine": 0.0380, "road": 0.0513, "brake_limit": 0.3016,
            "driveline": 0.2705, "impact": 0.4886, "chassis_load": 0.0493,
            "rear_traction": 0.5000}
TRIM_THEN = {"engine": 2.50, "road": 0.80, "brake_limit": 0.85,
             "driveline": 0.95, "impact": 3.80, "chassis_load": 0.85,
             "rear_traction": 1.00}

# **A scale is not an amplitude, and conflating them costs 6 dB.**
#
# `FIRES_AT` above are SCALES - the coefficient an effect's shaped intensity is
# multiplied by. What reaches the transducer is smaller, because the shaping
# (gamma, threshold, min_force, noise, AM) never delivers a full-scale value.
# Measured twice on `impact` through the real mix on 12 Sep 2026: scale 0.4886
# rendered a peak of 0.2306, and scale 0.0891 rendered 0.0500 - ratios of 0.47
# and 0.56.
#
# Knock depends on the amplitude that actually arrives, so the comparison
# against the knock curve has to carry this. Comparing the scale directly is
# what made the first per-band ceiling roughly 6 dB too aggressive and turned
# the kerb strike into something the driver said "didn't feel like a kerb
# strike".
#
# It is measured on ONE effect and assumed for the rest, which is the weakest
# assumption in this file. Re-measure per effect before trusting a 2 dB margin.
PEAK_BELOW_SCALE_DB = -5.9


def _floor_dbfs(freq: float) -> float:
    """The driver's measured detection floor, interpolated between the four
    frequencies a staircase was actually run at. Held flat outside them - the
    floors are measurements, not a model, and must not be extrapolated."""
    points = transducer.PERCEPTION_FLOOR_DBFS
    if freq <= points[0][0]:
        return points[0][1]
    if freq >= points[-1][0]:
        return points[-1][1]
    for (lo_hz, lo), (hi_hz, hi) in zip(points, points[1:]):
        if lo_hz <= freq <= hi_hz:
            span = hi_hz - lo_hz
            return lo + (hi - lo) * (freq - lo_hz) / span
    return points[-1][1]


def _level_dbfs(spec) -> float:
    """Where this effect lands in the car under its Rev A trim."""
    gain = 20 * math.log10(spec.felt_trim / TRIM_THEN[spec.name])
    return 20 * math.log10(FIRES_AT[spec.name]) + gain


def _band_centre(spec) -> float:
    return (spec.freq_lo + spec.freq_hi) / 2 if spec.freq_hi else spec.freq_lo


@pytest.mark.parametrize("spec", synth.PORSCHE_RSR_17_REV_A,
                         ids=lambda s: s.name)
def test_every_effect_clears_the_drivers_floor(spec):
    """A cue below the floor is not quiet, it is absent.

    Measured at the trims of 12 Sep: `engine` sat 3.4 dB UNDER the floor and
    `road` 0.8 dB under, so two of the three beds could not be felt at all -
    and at amp 29 they are 9.4 and 6.8 dB under.
    """
    level = _level_dbfs(spec)
    floor = _floor_dbfs(_band_centre(spec))
    assert level > floor, (
        f"{spec.name} lands at {level:.1f} dBFS against a measured floor of "
        f"{floor:.1f} - it cannot be felt")


@pytest.mark.parametrize("spec", synth.PORSCHE_RSR_17_REV_A,
                         ids=lambda s: s.name)
def test_no_effect_drives_the_transducer_into_its_stops(spec):
    """`impact` ran 7 dB past the knock threshold on every kerb of every lap.

    The limiter never saw a problem because `SUSTAINED_CEILING` is one number
    and the real ceiling moves by 15 dB across the band.
    """
    peak = _level_dbfs(spec) + PEAK_BELOW_SCALE_DB
    ceiling = 20 * math.log10(
        transducer.knock_ceiling_for_band(spec.freq_lo, spec.freq_hi))
    ceiling += transducer.KNOCK_MARGIN_DB      # compare against onset itself
    assert peak < ceiling, (
        f"{spec.name} peaks at {peak:.1f} dBFS against a knock onset of "
        f"{ceiling:.1f} - it reaches the end stops")


def test_the_engine_bed_stays_the_quietest_thing_in_the_mix():
    """It is the LOWEST band and it is always on.

    Salience is set by the ratio to the lowest component present (Le et al.
    2023), so an always-on bed at the bottom of the range anchors the
    perception of everything above it. It has to clear the floor and then stop.
    """
    margins = {s.name: _level_dbfs(s) - _floor_dbfs(_band_centre(s))
               for s in synth.PORSCHE_RSR_17_REV_A}
    assert margins["engine"] == min(margins.values()), (
        "engine is no longer the closest to the floor - it is the lowest "
        "always-on band and must not anchor the mix")


def test_rev_a_is_opt_in(monkeypatch):
    """Rev A was rejected in the seat and is never the default: with nothing
    selected the locked tune runs; Rev A only runs when asked for by name."""
    monkeypatch.delenv("PITCREW_RIG_REV", raising=False)
    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    assert synth.default_profile() is not synth.PORSCHE_RSR_17_REV_A
    assert synth.default_profile() is synth.PORSCHE_RSR_17_REV_G


def test_rev_a_changes_only_trims():
    """Bands, gains and shaping are untouched, so a lap comparison has ONE
    variable. `impact` in particular stays at 52-60 Hz: moving it down costs
    perceptibility no trim can buy back, and moving it to 120-140 was tried in
    the seat and read as "more like ABS or traction control"."""
    for old, new in zip(synth.PORSCHE_RSR_17, synth.PORSCHE_RSR_17_REV_A):
        assert old.name == new.name
        assert (old.freq_lo, old.freq_hi) == (new.freq_lo, new.freq_hi)
        assert old.gain == new.gain
        assert old.priority == new.priority
        assert (old.threshold, old.min_force, old.gamma) == (
            new.threshold, new.min_force, new.gamma)


def test_the_live_engine_follows_the_flag(monkeypatch):
    """The engine the app actually runs must pick up Rev A.

    `HapticsEngine` used to bind `specs=synth.PROFILE` at import, so the flag
    reached `DUCK_DEPTH` (read at import) but never the trims. The first Rev A
    laps would have driven the old trims under the new duck and been reported
    as Rev A. Constructing an engine opens no device, so this needs no rig.
    """
    from pitcrew.rig import haptics

    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "ORIGINAL")
    assert haptics.HapticsEngine()._specs == tuple(synth.PORSCHE_RSR_17)

    monkeypatch.delenv("PITCREW_RIG_REV", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV_A", "1")
    assert haptics.HapticsEngine()._specs == tuple(synth.PORSCHE_RSR_17_REV_A)
