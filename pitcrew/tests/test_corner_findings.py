"""The corner debrief, and the claims it is not entitled to make.

This module exists because live corner coaching was measured and refuted: over
307 clean laps, per-corner metrics are RELATIVELY NOISIER than lap time (corner
time 2 sd 4-6% against a lap's 1.66%), and `brake_point_m` carries a 2 sd of
14-37 m. So the tests that matter are the refusals - a debrief that reports
noise is worse than one that says nothing, because it sends him to fix a corner
that was never broken.
"""
from __future__ import annotations

import random

from pitcrew.analysis.corner_findings import (
    MIN_TREND_LAPS,
    Report,
    analyse,
)
from pitcrew.analysis.corners import CountedLap

from .test_corners import a_model, frame

# The single corner every fixture is built around: apex 300, window 200-400.
APEX = 300.0


def a_lap(number: int, *, min_kph: float = 100.0, jitter: float = 0.0,
          seed: int | None = None, length_m: float = 2000.0,
          corner_step: float | None = None) -> CountedLap:
    """One lap whose corner has a stated minimum speed.

    Speed is flat at 200 outside the window and dips to `min_kph` at the apex,
    so `min_kph` is exactly what the aggregate reads.

    **`corner_step` is what makes corner TIME vary.** `time_ms` comes from the
    frame count inside the window, so a fixture that steps a fixed distance
    everywhere pins it to a constant - which silently made every corner-time
    test vacuous until `opportunities` came back empty and said so. A smaller
    step means more frames over the same road, which is a slower corner.
    """
    rng = random.Random(seed if seed is not None else number)
    wobble = rng.uniform(-jitter, jitter) if jitter else 0.0
    inside = corner_step if corner_step is not None else 5.0
    frames, distance, index = [], 0.0, 0
    while distance <= length_m:
        if 200.0 <= distance <= 400.0:
            # A V through the corner, floored at the stated minimum.
            speed = min_kph + wobble + abs(distance - APEX) * 0.3
            step = inside
        else:
            speed = 200.0
            step = 5.0
        frames.append(frame(distance, speed, index))
        distance += step
        index += 1
    return CountedLap(number, frames)


def a_stint(count: int, **kwargs) -> list[CountedLap]:
    return [a_lap(n, **kwargs) for n in range(1, count + 1)]


# ------------------------------------------------------------ it stays quiet

def test_a_consistent_stint_produces_no_findings():
    """The common and correct answer."""
    report = analyse(a_model(), a_stint(12, jitter=1.0))
    assert report.quiet
    assert report.laps_used == 12


def test_silence_is_reported_as_silence_and_never_as_health():
    """**The doctrine the lap-time work established**: an engineer whose
    silence is indistinguishable from nothing being wrong is not reporting."""
    report = analyse(a_model(), a_stint(12, jitter=1.0))
    assert report.silent, "a corner that said nothing must still be listed"
    assert "noise" in report.silent[0].reason
    assert "not the same as nothing being wrong" in report.summary()


def test_too_few_laps_says_so_rather_than_reporting_from_them():
    report = analyse(a_model(), a_stint(MIN_TREND_LAPS - 2, jitter=1.0))
    assert report.quiet
    assert report.silent
    assert "consecutive" in report.silent[0].reason


def test_no_laps_at_all_is_not_a_crash():
    report = analyse(a_model(), [])
    assert isinstance(report, Report)
    assert report.laps_used == 0
    assert "No laps" in report.summary()


# ----------------------------------------------------------- it does report

def test_a_real_trend_is_found_and_carries_its_evidence():
    """Minimum speed falling 1 km/h a lap over twelve laps - the degradation
    shape, and the one finding that arrives before the stopwatch does."""
    laps = [a_lap(n, min_kph=110.0 - n, jitter=0.4, seed=n)
            for n in range(1, 13)]
    report = analyse(a_model(), laps)
    trends = [f for f in report.findings if f.kind == "trend"]
    assert trends, "a 12 km/h fall over 12 laps must be found"
    found = trends[0]
    assert found.metric == "min_kph"
    assert found.samples == 12
    assert found.magnitude < 0            # down
    assert found.noise_2sd > 0            # measured, not assumed
    assert "t " in found.detail and "noise" in found.detail


def test_a_trend_inside_the_noise_is_not_a_finding():
    """**Both tests, not either.** A statistically certain quarter of a km/h
    is not a finding about driving."""
    laps = [a_lap(n, min_kph=110.0 - n * 0.02, jitter=0.4, seed=n)
            for n in range(1, 13)]
    report = analyse(a_model(), laps)
    assert not [f for f in report.findings if f.kind == "trend"]


def test_pure_noise_does_not_manufacture_a_trend():
    """Fifty tests a session at t=2.0 would clear two or three by chance,
    which is why the threshold is 2.5."""
    laps = [a_lap(n, min_kph=110.0, jitter=3.0, seed=1000 + n)
            for n in range(1, 15)]
    report = analyse(a_model(), laps)
    assert not [f for f in report.findings if f.kind == "trend"]


# ------------------------------------------------------ the refuted finding

def test_there_is_no_you_are_off_your_best_finding():
    """**The defect this module shipped with in draft.** Mean against the best
    value seen, kept where the gap cleared the noise floor, fired on eighteen
    of twenty-four Monza corner-metrics.

    The maximum of n samples sits about sigma*sqrt(2 ln n) above the mean by
    construction - ~2.5 sigma at 24 laps - so the test was very nearly a
    theorem. Any finding kind that compares against a single best value is
    this bug returning."""
    laps = a_stint(24, jitter=3.0)
    report = analyse(a_model(), laps)
    assert all(f.kind in ("trend", "inconsistent") for f in report.findings)


def test_the_opportunity_ordering_makes_no_claim_of_significance():
    """It is descriptive. It exists so he knows where to spend a session, and
    it is ranked widest-first."""
    rng = random.Random(7)
    report = analyse(a_model(), [
        a_lap(n, jitter=2.0, seed=n, corner_step=rng.uniform(4.2, 5.0))
        for n in range(1, 13)])
    assert report.opportunities
    gaps = [o.gap_ms for o in report.opportunities]
    assert gaps == sorted(gaps, reverse=True)
    assert all(o.samples >= MIN_TREND_LAPS for o in report.opportunities)
    # ...and it is NOT counted as a finding.
    assert report.quiet or all(
        f.kind != "opportunity" for f in report.findings)


# ---------------------------------------------------------- the length gate

def test_a_lap_that_measured_a_different_road_is_held_out():
    """`length_gate` runs first: a corner window is a fixed distance range."""
    laps = a_stint(10, jitter=1.0) + [a_lap(11, length_m=4000.0)]
    report = analyse(a_model(), laps)
    assert report.laps_held_out == 1
    assert report.laps_used == 10


# --------------------------------------------------------- the noise floor

def test_the_floor_is_measured_from_this_session_and_published():
    """A stored per-corner table would be a claim about a car, a circuit, a
    tyre and a day that have all moved on."""
    quiet = analyse(a_model(), a_stint(12, jitter=0.5))
    noisy = analyse(a_model(), [a_lap(n, jitter=6.0, seed=n)
                                for n in range(1, 13)])
    corner = a_model().corners[0].id
    assert quiet.noise[corner]["min_kph"] < noisy.noise[corner]["min_kph"]


def test_every_finding_carries_its_sample_count():
    """CLAUDE.md 4.4 - a corner metric from two laps and one from eleven are
    not the same claim."""
    laps = [a_lap(n, min_kph=110.0 - n, jitter=0.4, seed=n)
            for n in range(1, 13)]
    for found in analyse(a_model(), laps).findings:
        assert found.samples >= MIN_TREND_LAPS
