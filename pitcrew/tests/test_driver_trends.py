"""The driver as a variable (plan row 2.11): three numbers per session, each
with its n, None where it cannot be known - and a description of sessions
driven, never a forecast (incidents are memoryless)."""
from __future__ import annotations

from statistics import pstdev

import pytest

from pitcrew.analysis.driver_trends import (LAP_ONE_REFERENCE_FROM,
                                            MIN_REFERENCE_LAPS, session_trend)
from pitcrew.analysis.incidents import Evidence
from pitcrew.analysis.session import LapInput


def _laps(seconds, *, session_id=1):
    """One run, one tank: a plausible 3 L a lap from full."""
    return [LapInput(lap_num=i, lap_time_ms=int(s * 1000),
                     fuel_start=100.0 - 3.0 * (i - 1), fuel_end=100.0 - 3.0 * i,
                     session_id=session_id)
            for i, s in enumerate(seconds, 1)]


def _off_on(*lap_nums):
    """Real evidence: 5 s off the road clears `OFF_TRACK_MIN_S` (2.5)."""
    return lambda lap: (Evidence(off_track_s=5.0) if lap.lap_num in lap_nums
                        else Evidence())


PRACTICE = [95.0, 90.0, 90.4, 89.8, 100.0, 90.2, 89.9, 90.1]


def test_practice_counts_the_incident_against_the_laps_that_were_judged():
    trend = session_trend(_laps(PRACTICE), session_id=7, kind="practice",
                          evidence_for=_off_on(5))
    # Lap 1 is the out-lap `find_incidents` does not judge; 2-8 are judged.
    assert trend.judged_laps == 7
    assert trend.incidents == 1
    assert trend.incident_rate == pytest.approx(1 / 7)


def test_consistency_is_the_counted_set_without_the_out_lap_or_the_incident():
    trend = session_trend(_laps(PRACTICE), kind="practice",
                          evidence_for=_off_on(5))
    kept = [90.0, 90.4, 89.8, 90.2, 89.9, 90.1]
    assert trend.consistency_n == len(kept)
    assert trend.consistency_sd_s == pytest.approx(pstdev(kept))


def test_practice_has_no_lap_one_cost_and_says_why():
    trend = session_trend(_laps(PRACTICE), kind="practice",
                          evidence_for=_off_on())
    assert trend.lap_one_cost_s is None
    assert any("out of the pits" in line for line in trend.silences)


def test_a_race_lap_one_is_measured_against_lap_five_on():
    """Warm-up laps two to four cost a little; they are not the reference."""
    race = [100.0, 91.0, 91.0, 91.0, 90.0, 90.2, 89.8, 90.1, 89.9, 90.0]
    trend = session_trend(_laps(race), kind="race", evidence_for=_off_on())
    assert trend.lap_one_reference_n == len(race) - (LAP_ONE_REFERENCE_FROM - 1)
    assert trend.lap_one_cost_s == pytest.approx(100.0 - 90.0)
    assert any("not judged for incidents" in line for line in trend.silences)


def test_too_few_reference_laps_is_no_lap_one_cost_rather_than_a_guess():
    race = [100.0, 91.0, 91.0, 91.0, 90.0, 90.2]        # two laps from lap 5
    trend = session_trend(_laps(race), kind="race", evidence_for=_off_on())
    assert trend.lap_one_cost_s is None
    assert trend.lap_one_reference_n == 2 < MIN_REFERENCE_LAPS
    assert any("2 counted lap(s)" in line for line in trend.silences)


def test_a_session_nobody_could_judge_has_no_incident_count_not_zero():
    """Rule 3: `find_incidents` gives no verdict on a run of fewer than three
    clean laps, so its laps are not 'no incidents' - they are unjudged."""
    trend = session_trend(_laps([95.0, 90.0, 90.5]), kind="practice",
                          evidence_for=_off_on())
    assert trend.judged_laps == 0
    assert trend.incidents is None
    assert trend.incident_rate is None
    assert any("not a count of zero" in line for line in trend.silences)


def test_a_clean_session_is_a_measured_zero():
    trend = session_trend(_laps(PRACTICE[:4] + [90.0] + PRACTICE[5:]),
                          kind="practice", evidence_for=_off_on())
    assert trend.incidents == 0 and trend.judged_laps == 7
    assert trend.incident_rate == 0.0


def test_one_lap_of_spread_is_not_a_spread():
    trend = session_trend(_laps([95.0, 90.0]), kind="practice",
                          evidence_for=_off_on())
    assert trend.consistency_sd_s is None
    assert trend.consistency_n <= 1
