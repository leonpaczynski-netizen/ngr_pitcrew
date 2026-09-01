"""The practice debrief — the honesty rules, not the arithmetic.

Every test here exists because the analysis it guards would otherwise say
something to the driver that is not true. Synthetic laps throughout: the live
archive is never opened by the suite.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.corner_model import Corner, CornerModel
from pitcrew.analysis.corners import CountedLap
from pitcrew.analysis.debrief import (
    ALPHA,
    CLEAN_OFF_TRACK_S,
    MIN_LAPS_FOR_CORRELATION,
    Burn,
    Census,
    Pace,
    _sd,
    analyse,
    correlation_p,
    is_clean,
)

MODEL = CornerModel(
    model_id="test", version=1, source="auto-segment", lap_length_m=1000.0,
    corners=(Corner(id="T1", name="Turn 1", start_m=100.0, apex_m=150.0, end_m=200.0),
             Corner(id="T2", name="Turn 2", start_m=500.0, apex_m=550.0, end_m=600.0)))


def _lap(number: int, *, t1_min: float, t2_min: float,
         t1_gear: int = 2, t2_gear: int = 3) -> CountedLap:
    """A lap whose speed dips to a chosen minimum in each corner window."""
    frames = []
    for metre in range(0, 1000, 5):
        speed, gear = 200.0, 5
        if 100 <= metre <= 200:
            speed = t1_min + abs(metre - 150) * 0.4
            gear = t1_gear
        elif 500 <= metre <= 600:
            speed = t2_min + abs(metre - 550) * 0.4
            gear = t2_gear
        frames.append({"lap_distance_m": float(metre), "speed_kph": speed,
                       "gear": gear, "t_ms": metre * 5})
    return CountedLap(lap=number, frames=frames, sample_hz=60.0)


def _census(analysed: int, excursions: int = 0) -> Census:
    return Census(recorded=analysed + excursions, out_laps=0, in_laps=0,
                  excluded=0, excursions=excursions, analysed=analysed)


_PACE = Pace(n=0, median_ms=None, best_ms=None, sd_ms=None)
_BURN = Burn(n=0, median_l=None, sd_l=None)


def _run(laps):
    return analyse(MODEL, laps, census=_census(len(laps)),
                   pace=_PACE, burn=_BURN)


# ------------------------------------------------------------- statistics

@pytest.mark.parametrize("r, n, expected", [
    # Published two-tailed critical values for Pearson r at p = 0.05.
    (0.632, 10, 0.05),
    (0.444, 20, 0.05),
    (0.361, 30, 0.05),
])
def test_the_p_value_matches_published_critical_values(r, n, expected):
    """There is no SciPy here, so the t-distribution is hand-rolled. It is
    checked against a table rather than against itself."""
    assert correlation_p(r, n) == pytest.approx(expected, abs=0.002)


def test_a_correlation_needs_three_pairs_before_it_means_anything():
    assert correlation_p(0.9, 2) is None


def test_a_single_sample_has_no_spread_rather_than_a_spread_of_zero():
    """CLAUDE.md rule 3. A corner seen once is not a perfectly repeatable
    corner, and 0.0 would rank it top of the consistency table."""
    assert _sd([42.0]) is None
    assert _sd([]) is None
    assert _sd([10.0, 12.0]) == pytest.approx(1.0)


# ---------------------------------------------------------- the clean filter

def test_a_lap_with_no_surface_channel_is_refused_not_assumed_clean():
    """Absent is missing, not tarmac."""
    assert is_clean(0.0) is True
    assert is_clean(CLEAN_OFF_TRACK_S - 0.01) is True
    assert is_clean(CLEAN_OFF_TRACK_S) is False
    assert is_clean(None) is False


def test_the_filter_is_stricter_than_the_incident_threshold():
    """The two Daytona laps that carried a false finding were 1.22 s and
    1.43 s off — both well under `incidents.OFF_TRACK_MIN_S` of 2.5."""
    from pitcrew.analysis.incidents import OFF_TRACK_MIN_S

    assert CLEAN_OFF_TRACK_S < OFF_TRACK_MIN_S
    assert not is_clean(1.22)
    assert not is_clean(1.43)


# ---------------------------------------------------------------- silences

def test_a_corner_that_fails_significance_says_so_rather_than_vanishing():
    """Silence means "I cannot see it", never "nothing is happening". A corner
    that simply did not appear reads as the second."""
    laps = [(_lap(i, t1_min=90 + (i % 3), t2_min=120.0), 100_000 + i * 37)
            for i in range(1, 13)]
    out = _run(laps)
    assert not out.spoken
    assert any("Turn 1" in line for line in out.silences)
    assert any("Turn 2" in line for line in out.silences)


def test_too_few_laps_is_reported_as_too_few_laps():
    laps = [(_lap(i, t1_min=90 + i, t2_min=120.0), 100_000 - i * 400)
            for i in range(1, 6)]
    out = _run(laps)
    assert not out.spoken
    assert any(str(MIN_LAPS_FOR_CORRELATION) in line for line in out.silences)


def test_a_corner_reached_on_one_lap_gets_no_scatter_row_and_an_explanation():
    laps = [(_lap(1, t1_min=90.0, t2_min=120.0), 100_000)]
    out = _run(laps)
    assert out.scatter == ()
    assert len(out.silences) == 2


# ------------------------------------------------------------- correlation

def test_a_real_correlation_is_spoken_with_its_n_and_p():
    """Built so T1 genuinely drives the lap: every km/h slower at the apex
    costs a fixed slice of lap time, with a little noise on top."""
    laps = []
    for i in range(14):
        low = 88.0 + (i % 7)
        jitter = (-1) ** i * 60
        laps.append((_lap(i + 1, t1_min=low, t2_min=120.0),
                     int(112_000 - low * 60 + jitter)))
    out = _run(laps)
    spoken = {c.corner_id for c in out.spoken}
    assert "T1" in spoken
    found = next(c for c in out.spoken if c.corner_id == "T1")
    assert found.r < 0            # quicker lap when faster through the corner
    assert found.p <= ALPHA
    assert found.n == 14


# -------------------------------------------------------------------- gear

def test_a_gear_split_with_both_arms_populated_is_called_balanced():
    laps = []
    for i in range(10):
        gear = 2 if i % 2 else 3
        laps.append((_lap(i + 1, t1_min=90.0, t2_min=120.0, t1_gear=gear),
                     100_000 + i))
    out = _run(laps)
    split = next(g for g in out.gears if g.corner_id == "T1")
    assert split.balanced
    assert {arm.gear for arm in split.arms} == {2, 3}
    assert sum(arm.n for arm in split.arms) == 10


def test_a_one_lap_gear_difference_is_not_dressed_up_as_a_comparison():
    """The Spa Bus Stop shape: one lap in a different gear, and it happened to
    be the fastest lap in the set. A hypothesis, not a finding."""
    laps = [(_lap(i + 1, t1_min=90.0, t2_min=120.0,
                  t1_gear=3 if i == 0 else 2), 100_000 + i * 100)
            for i in range(9)]
    out = _run(laps)
    split = next(g for g in out.gears if g.corner_id == "T1")
    assert not split.balanced
    assert split.quickest.gear == 3       # it WAS quickest, and still unbalanced


def test_a_corner_taken_in_one_gear_every_lap_produces_no_split():
    laps = [(_lap(i + 1, t1_min=90.0, t2_min=120.0), 100_000 + i)
            for i in range(8)]
    out = _run(laps)
    assert all(g.corner_id != "T1" for g in out.gears)


# ------------------------------------------------------------- consistency

def test_the_least_repeatable_corner_is_the_one_with_the_widest_spread():
    """The headline of the debrief, and the one claim needing no reference of
    any kind — not a best lap, not a teammate, not a correlation."""
    laps = []
    for i in range(10):
        laps.append((_lap(i + 1, t1_min=90.0 + (i % 2) * 0.5,
                          t2_min=120.0 + (i % 5) * 4.0), 100_000 + i))
    out = _run(laps)
    assert out.least_repeatable.corner_id == "T2"
    assert out.scatter[0].corner_id == "T2"        # sorted worst first
    assert out.scatter[0].n == 10


def test_every_scatter_row_carries_its_sample_count():
    """CLAUDE.md rule 4: a metric from two laps and one from eleven are not
    the same claim."""
    laps = [(_lap(i + 1, t1_min=90.0 + i, t2_min=120.0), 100_000 + i)
            for i in range(6)]
    out = _run(laps)
    assert all(row.n == 6 for row in out.scatter)


def test_the_census_arithmetic_closes():
    census = _census(analysed=11, excursions=2)
    out = analyse(MODEL, [(_lap(i, t1_min=90.0 + (i % 3), t2_min=120.0),
                           100_000 + i) for i in range(1, 12)],
                  census=census, pace=_PACE, burn=_BURN)
    assert out.census.analysed + out.census.excursions == out.census.recorded
    assert "11 of 13" in out.census.describe()
    assert "excursion" in out.census.describe()
