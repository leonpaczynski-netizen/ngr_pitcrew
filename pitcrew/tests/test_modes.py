"""Two populations must not be collapsed into one number."""
from __future__ import annotations

from pitcrew.analysis.modes import find_split

# Session 60, 21 Aug 2026: laps 1-10 short-shifted, 11-12 at full RPM.
SESSION_60 = [5.154, 5.133, 5.222, 5.276, 5.246, 5.323,
              5.280, 5.283, 5.356, 5.331, 6.663, 6.808]


def test_the_run_that_this_exists_for():
    """The app cannot see the discipline, but it can see the consequence.

    `short_shift_rpm` reads 0.0 on all twelve laps, so nothing downstream can
    separate them and the weighted median lands on the short-shifted figure -
    5.28 L/lap. A plan costed on it goes into a full-RPM race a quarter light.
    """
    split = find_split(SESSION_60)
    assert split is not None
    assert round(split.low, 2) == 5.28 and round(split.high, 2) == 6.74
    assert split.low_laps == 10 and split.high_laps == 2
    assert 0.20 < split.gap_fraction < 0.24

    said = split.describe()
    # Both figures and both counts, or he cannot act on it.
    assert "5.28" in said and "6.74" in said
    assert "10" in said and "2 at about" in said
    # And it must not pretend to know WHY. Naming the cause would invent it.
    assert "short" not in said.lower()


def test_one_discipline_is_one_population():
    assert find_split([6.10, 6.20, 6.15, 6.18, 6.22, 6.09, 6.30, 6.11]) is None


def test_a_smooth_spread_is_not_a_split():
    """Otherwise an evenly-spread set divides at an arbitrary point."""
    assert find_split([5.0, 5.4, 5.8, 6.2, 6.6, 7.0, 7.4, 7.8]) is None


def test_a_single_outlier_is_not_a_second_population():
    """One lap is one lap - a botched in-lap, a spin, a missed shift."""
    assert find_split([6.10, 6.20, 6.15, 6.18, 6.22, 6.09, 9.90]) is None


def test_too_few_laps_to_have_two_groups_of_anything():
    assert find_split([5.2, 6.8]) is None
    assert find_split([]) is None


def test_a_small_gap_is_ordinary_scatter():
    """The measured short-shift saving is 21-25%; scatter is a few percent."""
    assert find_split([6.00, 6.02, 6.05, 6.30, 6.33, 6.35]) is None
