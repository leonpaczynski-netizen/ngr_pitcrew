"""Inconsistency read as a finding, and the bars it has to clear first.

The driver's correction, 5 Sep 2026: a sector with spread while its
neighbours are steady is a question about the car in that sector, not noise
to be averaged away. Daytona T1 wanted `lsd_b` and the Bus Stop wanted front
compression lowered; both were found late.

These tests are mostly about what stops that becoming a licence to read
anything into a small sample.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.spread import (
    ALPHA,
    IMPLAUSIBLE_RELATIVE,
    MIN_LAPS,
    _betai,
    detrended_sd,
    least_repeatable,
    looks_like_a_fault,
    measure,
    ratio_p,
)


# ------------------------------------------------------- the F distribution

def _p_at(fcrit, d1, d2):
    x = d1 * fcrit / (d1 * fcrit + d2)
    return 1.0 - _betai(d1 / 2.0, d2 / 2.0, x)


@pytest.mark.parametrize("fcrit, d1, d2", [
    (3.179, 9, 9), (5.050, 5, 5), (2.978, 10, 10),
    (3.478, 4, 10), (3.490, 3, 12), (4.459, 2, 8),
])
def test_the_hand_rolled_f_matches_the_published_tables(fcrit, d1, d2):
    """scipy is not a dependency and adding one for a single distribution
    would be a poor trade - so the incomplete beta is written out, and it has
    to be checked against something that was not."""
    assert _p_at(fcrit, d1, d2) == pytest.approx(0.05, abs=0.0006)


def test_a_ratio_needs_real_separation_before_it_is_significant():
    """Nine laps a side needs about 3.2x. A sector 1.4x another is not the
    answer to anything, and this is why."""
    assert ratio_p(1.4, 9, 1.0, 9) > ALPHA
    assert ratio_p(4.0, 9, 1.0, 9) < ALPHA


def test_too_few_laps_is_no_answer_rather_than_a_weak_one():
    assert ratio_p(9.0, MIN_LAPS - 1, 1.0, 9) is None
    assert ratio_p(9.0, 9, 0.0, 9) is None, "a zero denominator is not infinity"


# ------------------------------------------------------------- what inflates

def test_learning_is_not_instability():
    """**Improvement across a run is ~0.3 s and beats every setup effect on
    file.** A sector getting quicker every lap has a large raw spread and a
    small residual one, and only the residual is about the car."""
    improving = [35.9, 35.7, 35.5, 35.3, 35.1, 34.9, 34.7]
    assert detrended_sd(improving) == pytest.approx(0.0, abs=1e-9)

    scattered = [35.3, 35.9, 35.0, 35.7, 35.1, 35.8, 35.2]
    assert detrended_sd(scattered) > 0.3


def test_a_spread_over_four_laps_is_not_a_spread():
    assert detrended_sd([1.0, 2.0, 3.0, 4.0]) is None
    assert measure("S1", [1.0, 2.0, 3.0, 4.0]) is None


# --------------------------------------------------- ruling out the instrument

def test_an_implausible_spread_points_at_the_data_first():
    """**A driver is inconsistent by a few percent of a corner.** Ten percent
    of a sector is seconds, and the likelier causes are all faults - 7% of
    laps in this archive teleport and speed integration cannot see it. Found
    live on session 93, where S1 carried 23% and 18x its neighbours."""
    wild = measure("S1", [17.0, 24.0, 15.0, 22.0, 16.5, 23.5, 14.0])
    assert wild.relative > IMPLAUSIBLE_RELATIVE
    assert looks_like_a_fault(wild)

    ordinary = measure("S2", [35.1, 35.3, 35.0, 35.4, 35.2, 35.3, 35.1])
    assert not looks_like_a_fault(ordinary)


# ----------------------------------------------------------- the comparison

def test_it_compares_the_extremes_and_says_how_sure():
    steady = measure("S3", [30.00, 30.05, 29.98, 30.03, 30.01, 29.99, 30.02])
    loose = measure("S2", [35.0, 35.6, 34.7, 35.5, 34.9, 35.7, 35.1])
    worst, steadiest, ratio, p = least_repeatable([steady, loose])
    assert worst.label == "S2" and steadiest.label == "S3"
    assert ratio > 5
    assert p < ALPHA


def test_it_is_relative_spread_that_is_ranked_not_absolute():
    """Sectors are not the same length. Absolute spread ranks the long one
    first by construction, which would make the answer an artefact of where
    the lines were drawn."""
    long_steady = measure("S1", [60.0, 60.3, 59.8, 60.2, 60.1, 59.9, 60.0])
    short_loose = measure("S3", [10.0, 10.4, 9.7, 10.5, 9.8, 10.3, 9.9])
    assert long_steady.sd < short_loose.sd * 2, "picked an unfair fixture"
    worst, _steadiest, _ratio, _p = least_repeatable([long_steady, short_loose])
    assert worst.label == "S3", "absolute spread won, not relative"


def test_one_part_alone_says_nothing():
    only = measure("S1", [35.0, 35.2, 35.1, 35.3, 35.0, 35.2, 35.1])
    assert least_repeatable([only]) is None
    assert least_repeatable([None, None]) is None
