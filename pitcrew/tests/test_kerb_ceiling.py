"""The road bed stops saturating on a kerb.

Reported from the seat, 2 Sep 2026: "every time I get on the banked kerb the
ButtKicker goes berserk". Measured, it was literal saturation rather than a
spurious trigger — 30.5% of Daytona kerb frames pinned at full scale, because
`_texture_scale` learned where the bed TOPS OUT from tarmac frames only and
that number had no relationship to how big a kerb can be.
"""
from __future__ import annotations

import pytest

from pitcrew.rig import effects as fx
from pitcrew.rig.vehicle import _Quantile


def a_deriver(ceiling=None, settled=True):
    dv = fx.EffectDeriver()
    tracker = _Quantile(0.90, fx.KERB_LEARN_STEP,
                        initial=ceiling if ceiling is not None
                        else fx.TEXTURE_FULL_MS,
                        settle_frames=0 if settled else 10_000)
    if settled:
        tracker.samples = fx.KERB_SETTLE_FRAMES + 1
    dv._kerb_p90 = tracker
    return dv


ONSET, FULL = 0.0204, 0.1497           # the Daytona learned scale
KNEE = ONSET + fx.TEXTURE_AT_TARMAC_P90 * (FULL - ONSET)


def test_below_the_knee_nothing_changes_at_all():
    """The proportions below the tarmac p90 are the ones he tuned by hand over
    eight days. Moving the ceiling must not drag the road down with it."""
    dv = a_deriver(ceiling=0.2418)
    for speed in (0.0, 0.01, ONSET, 0.04, 0.0706, KNEE):
        assert dv._shape(speed, ONSET, FULL) == pytest.approx(
            fx._ramp(speed, ONSET, FULL), abs=1e-9)


def test_the_curve_is_continuous_at_the_knee():
    dv = a_deriver(ceiling=0.2418)
    below = dv._shape(KNEE - 1e-6, ONSET, FULL)
    above = dv._shape(KNEE + 1e-6, ONSET, FULL)
    assert below == pytest.approx(above, abs=1e-4)
    assert below == pytest.approx(fx.TEXTURE_AT_TARMAC_P90, abs=1e-3)


def test_a_kerb_that_used_to_pin_now_has_somewhere_to_go():
    """Daytona's kerb p90 is 0.2418 m/s against a learned top of 0.1497 —
    3.1x past the end of the scale."""
    dv = a_deriver(ceiling=0.2418)
    assert fx._ramp(0.2418, ONSET, FULL) == 1.0          # was flat out
    assert dv._shape(0.2418, ONSET, FULL) == pytest.approx(1.0, abs=1e-6)
    # ...and the band that used to be one flat maximum is a range again.
    # 0.16 and 0.22 m/s are both past the old top of 0.1497, so the old curve
    # cannot tell them apart at all.
    assert fx._ramp(0.16, ONSET, FULL) == fx._ramp(0.22, ONSET, FULL) == 1.0
    assert 0.39 < dv._shape(0.16, ONSET, FULL) < 1.0
    assert dv._shape(0.16, ONSET, FULL) < dv._shape(0.22, ONSET, FULL)


def test_the_very_biggest_hits_are_still_full_scale():
    """A ceiling is not a promise that nothing reaches it. Daytona's kerb p99
    is 0.466 and should still be everything the rig has."""
    dv = a_deriver(ceiling=0.2418)
    assert dv._shape(0.466, ONSET, FULL) == 1.0


def test_a_gentler_kerb_than_the_road_can_only_be_ignored():
    """Spa learned a ceiling of 0.107 against a tarmac top of 0.127. Used, it
    would make the second segment steeper than the line it replaced and pin
    EARLIER — a fix for saturation becoming a cause of it."""
    dv = a_deriver(ceiling=0.107)
    for speed in (0.08, 0.11, 0.13, 0.20):
        assert dv._shape(speed, ONSET, FULL) == pytest.approx(
            fx._ramp(speed, ONSET, FULL), abs=1e-9)


def test_the_ceiling_engages_on_the_first_kerb_and_not_the_four_hundredth():
    """**The gate made the fix arrive after the complaint.** Kerb frames are
    2.2-2.8% of a Daytona lap, so 400 of them is four to five MINUTES of
    driving - three or four laps of a five-lap session - and one session on
    file reached 323 over its whole length and never settled at all. For all of
    that time the bed ran on the unraised line, which is the saturation this
    exists to remove.

    One measured kerb frame is the bar now: the ceiling must be measured
    rather than assumed, which is what the old gate was really protecting, and
    400 was never what that needed.
    """
    dv = fx.EffectDeriver()
    dv._kerb_p90 = _Quantile(0.90, fx.KERB_LEARN_STEP, initial=0.2418)
    assert dv._shape(0.20, ONSET, FULL) == pytest.approx(
        fx._ramp(0.20, ONSET, FULL))          # nothing measured yet
    dv._kerb_p90.update(0.24)                 # one kerb frame
    assert dv._shape(0.20, ONSET, FULL) < fx._ramp(0.20, ONSET, FULL)


def test_an_unmeasured_ceiling_is_not_used():
    """Before it has learned anything the shape is exactly what it was."""
    dv = a_deriver(ceiling=0.2418, settled=False)
    assert dv._shape(0.20, ONSET, FULL) == pytest.approx(
        fx._ramp(0.20, ONSET, FULL))


def test_it_never_exceeds_one_or_falls_below_the_old_curve():
    """The change may only ever ADD headroom."""
    dv = a_deriver(ceiling=0.2418)
    for i in range(0, 600):
        speed = i / 1000.0
        new = dv._shape(speed, ONSET, FULL)
        assert 0.0 <= new <= 1.0
        assert new <= fx._ramp(speed, ONSET, FULL) + 1e-9


def test_the_ceiling_learns_from_kerbs_and_not_from_the_road():
    """Same guard as the onset, in reverse: grass and a spin must not raise
    the top any more than a kerb may lower the onset."""
    import inspect

    source = inspect.getsource(fx.EffectDeriver._road)
    assert "self._kerb_p90.update(speed)" in source
    assert "s.on_kerb and not s.off_surface" in source
