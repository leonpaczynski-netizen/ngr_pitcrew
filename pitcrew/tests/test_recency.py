"""Later laps count for more.

*"As I do more laps and refine the setup and my driving these laps should
carry more weight than the original laps for race strategy."*

Two separate reasons, and they are weighted separately. He gets faster: across
the Monza set the pooled clean-lap median is 109.43 s and the latest session
alone is 109.06, which is 0.37 s a lap. And the car changes: a lap on a
superseded setup sheet describes a car that no longer exists, which matters
more than age and is not fixed by recency.

On the real database this moves fuel per lap from 6.258 to 6.158 L — a tenth
of a litre a lap, or about 2.7 L over a 27-lap stint, which is half a lap of
fuel and therefore sometimes a stop.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.recency import (
    MINIMUM_WEIGHT,
    session_order,
    weighted,
    weighted_median,
)
from pitcrew.analysis.session import (
    LapInput,
    green_lap_reference_ms,
    reference_pace_ms,
)


def a_lap(lap_num: int, *, session_id: int, burn: float = 6.0,
          sheet_id: int | None = None, lap_ms: int = 109_000) -> LapInput:
    return LapInput(lap_num=lap_num, lap_time_ms=lap_ms,
                    fuel_start=100.0, fuel_end=100.0 - burn,
                    compound="RH", session_id=session_id,
                    setup_sheet_id=sheet_id)


def burn_of(lap):
    return lap.fuel_start - lap.fuel_end


# ----------------------------------------------------------------- weighting

def test_the_answer_moves_towards_the_recent_sessions():
    """Four sessions, each a little quicker on fuel than the last.

    Unweighted the median sits between the two middle sessions. Weighted it
    moves down towards what the car is doing now, which is the whole point —
    and on the real database that is 6.258 to 6.158 L a lap.
    """
    laps = []
    for index, burn in enumerate((7.0, 6.8, 6.5, 6.0), start=1):
        laps += [a_lap(index * 10 + n, session_id=index, burn=burn)
                 for n in range(3)]
    plain = sorted(burn_of(lap) for lap in laps)
    unweighted = plain[len(plain) // 2]
    value, _ = weighted(laps, burn_of)
    assert value < unweighted


def test_one_new_session_does_not_overturn_three_old_ones():
    """A two-session half-life is deliberately gentle. One run is a data
    point, not a new truth about the car, and a scheme that let it win
    outright would be truncation with extra steps."""
    old = [a_lap(n, session_id=n // 3 + 1, burn=7.0) for n in range(9)]
    new = [a_lap(n + 9, session_id=4, burn=6.0) for n in range(3)]
    value, _ = weighted(old + new, burn_of)
    assert value == 7.0


def test_it_does_not_simply_use_the_last_session():
    """Weighted, not truncated. Two sessions this week and eleven over the
    month is thirteen sessions of evidence, and throwing eleven away replaces
    a small bias with a large variance."""
    many = [a_lap(n, session_id=1, burn=6.0) for n in range(40)]
    few = [a_lap(n + 40, session_id=2, burn=9.0) for n in range(2)]
    value, _ = weighted(many + few, burn_of)
    assert value == 6.0, "two laps must not outvote forty"


def test_nothing_is_ever_weighted_to_nothing():
    """A lap from six sessions ago still happened. A floor is what keeps a
    long history from collapsing into the last two runs."""
    ages = session_order([a_lap(n, session_id=n) for n in range(1, 12)])
    oldest = a_lap(1, session_id=1)
    from pitcrew.analysis.recency import weight_of
    assert weight_of(oldest, ages, None) >= MINIMUM_WEIGHT


def test_a_lap_on_a_superseded_sheet_counts_for_less_than_its_age_alone():
    """It is describing a car that no longer exists, and no amount of
    recency rescues that."""
    from pitcrew.analysis.recency import weight_of
    ages = {1: 0}
    current = weight_of(a_lap(1, session_id=1, sheet_id=7), ages, 7)
    superseded = weight_of(a_lap(1, session_id=1, sheet_id=3), ages, 7)
    assert superseded < current


def test_a_lap_with_no_sheet_recorded_is_not_penalised():
    """Silence is not a positive claim that the car was different."""
    from pitcrew.analysis.recency import weight_of
    ages = {1: 0}
    assert weight_of(a_lap(1, session_id=1), ages, 7) == pytest.approx(
        weight_of(a_lap(1, session_id=1, sheet_id=7), ages, 7))


def test_three_sessions_old_on_the_current_sheet_beats_yesterday_on_an_old_one():
    """Weighting on time alone gets this backwards."""
    from pitcrew.analysis.recency import weight_of
    ages = {1: 3, 2: 0}
    old_but_current = weight_of(a_lap(1, session_id=1, sheet_id=7), ages, 7)
    recent_but_stale = weight_of(a_lap(2, session_id=2, sheet_id=3), ages, 7)
    assert old_but_current > recent_but_stale


# -------------------------------------------------------------- the mechanics

def test_the_median_is_by_weight_not_by_count():
    assert weighted_median([(1.0, 0.1), (2.0, 0.1), (9.0, 5.0)]) == 9.0


def test_a_single_bad_lap_does_not_move_it():
    """Median rather than mean, for the same reason the unweighted figures
    use one. A weighting scheme is not a reason to give that up."""
    pairs = [(6.0, 1.0), (6.1, 1.0), (6.0, 1.0), (99.0, 1.0)]
    assert weighted_median(pairs) < 7.0


def test_nothing_to_weigh_is_none_and_never_zero():
    """A figure that could not be computed and one that came out at zero are
    different claims, and only one of them is evidence."""
    value, weighting = weighted([], burn_of)
    assert value is None
    assert weighting.sessions == 0


def test_sessions_are_ordered_by_arrival_not_by_timestamp():
    """`started_at` is second-resolution, so two runs begun in the same second
    would tie — and the lap list is already in session order."""
    laps = ([a_lap(1, session_id=5)] + [a_lap(2, session_id=9)]
            + [a_lap(3, session_id=2)])
    assert session_order(laps) == {5: 2, 9: 1, 2: 0}


# -------------------------------------------------------------- what it skips

def test_the_weighting_declares_what_it_does_not_touch():
    """Wear is read off the in-game gauge rather than fitted, so reweighting
    it would reweight a measurement — and a gauge reading from three weeks ago
    is exactly as true as one from today."""
    _, weighting = weighted([a_lap(1, session_id=1)], burn_of)
    payload = weighting.as_export()
    assert "fuelPerLapL" in payload["appliesTo"]
    assert any("wear" in line for line in payload["excludes"])
    assert any("bestLapMs" in line for line in payload["excludes"])
    assert payload["source"] == "derived"


def test_appliesto_names_what_was_weighted_and_nothing_else():
    """It was a fixed `["referenceLapMs", "fuelPerLapL"]` while `weighted` was
    called for the fuel burn and nothing else — the reference pace came
    straight out of an unweighted `green_lap_reference_ms`. A claim about
    provenance that nothing computes is the one kind this app must not make.
    """
    _, fuel_only = weighted([a_lap(1, session_id=1)], burn_of)
    assert fuel_only.as_export()["appliesTo"] == ["fuelPerLapL"]

    _, both = weighted([a_lap(1, session_id=1)], burn_of,
                       applies_to=("referenceLapMs", "fuelPerLapL"))
    assert both.as_export()["appliesTo"] == ["referenceLapMs", "fuelPerLapL"]


def test_the_reference_pace_goes_through_the_weighting_too():
    """The module's own worked example is the pace — 0.37 s a lap, about ten
    seconds over a 50-minute race, and it moves the stop lap — and the pace
    was the one figure not going through it.

    `green_lap_reference_ms` cannot do this job: it is the best of the first
    three counted laps, which across a merged event is the *oldest* session's
    opening laps.
    """
    old = [a_lap(n, session_id=1, lap_ms=112_000) for n in range(1, 6)]
    new = [a_lap(n, session_id=2, lap_ms=109_000) for n in range(6, 11)]

    assert green_lap_reference_ms(old + new) == 112_000
    pace, weighting = reference_pace_ms(old + new)
    assert pace == 109_000
    assert weighting.as_export()["appliesTo"] == ["referenceLapMs"]
