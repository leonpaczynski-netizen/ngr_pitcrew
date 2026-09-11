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


def test_a_lap_already_stored_as_an_incident_is_counted():
    """Critic 6 (BLOCKER): stored incident laps arrive struck, and
    `find_incidents` skips struck laps - so none of the 19 stored race
    incidents on file was counted, the grass spin among them."""
    from dataclasses import replace

    laps = _laps(PRACTICE)
    laps[4] = replace(laps[4], excluded=True, exclusion_reason="incident")
    trend = session_trend(laps, kind="practice", evidence_for=_off_on())
    assert trend.incidents == 1
    assert trend.judged_laps == 7


def test_a_stored_incident_in_a_run_too_short_to_judge_is_named_not_rated():
    from dataclasses import replace

    laps = _laps([95.0, 90.0, 99.0])
    laps[2] = replace(laps[2], excluded=True, exclusion_reason="incident")
    trend = session_trend(laps, kind="practice", evidence_for=_off_on())
    assert trend.incidents is None
    assert any("stored as incidents" in line for line in trend.silences)


def test_a_lap_he_struck_in_his_own_words_is_quoted_not_counted():
    """Deep Forest s135's shape: lap 2 struck with "crash ... the driver
    reported damage". The export calls that manual, not an incident, so it
    is not counted - and it is not hidden behind a bare 0 either (rule 1)."""
    from dataclasses import replace

    laps = _laps([95.0, 97.7, 90.0, 90.2, 90.4, 90.1])
    laps[1] = replace(laps[1], excluded=True, exclusion_reason=(
        "crash - 97.698 against an 87.4 clean pace; the driver reported damage"))
    trend = session_trend(laps, kind="race", evidence_for=_off_on())
    assert trend.incidents == 0
    assert any(line.startswith("lap 2 struck by hand") and "reported damage" in line
               for line in trend.silences)


def test_the_apps_placeholder_is_not_quoted_as_his_words():
    """Critic 6, pass 2: "struck by hand" was quoted 22 times - the export's
    own rule (`runs._driver_note`) says it carries nothing."""
    from dataclasses import replace

    laps = _laps(PRACTICE)
    laps[2] = replace(laps[2], excluded=True, exclusion_reason="struck by hand")
    trend = session_trend(laps, kind="practice", evidence_for=_off_on())
    assert not any("in his words" in line for line in trend.silences)


def test_a_pit_lap_stored_as_an_incident_is_named():
    from dataclasses import replace

    laps = _laps(PRACTICE)
    laps[3] = replace(laps[3], is_pit_lap=True, excluded=True,
                      exclusion_reason="incident")
    trend = session_trend(laps, kind="practice", evidence_for=_off_on())
    assert any("stored as an incident on a pit lap" in line
               for line in trend.silences)


def test_no_spread_when_an_incident_leaves_two_counted_laps():
    """The n < 3 guard on its own: judged, but two laps left to spread."""
    trend = session_trend(_laps([95.0, 90.0, 90.2, 100.0]), kind="practice",
                          evidence_for=_off_on(4))
    assert trend.incidents == 1
    assert trend.consistency_n == 2 and trend.consistency_sd_s is None


def test_no_spread_over_counted_laps_nobody_could_screen():
    """The incidents-None guard on its own: two runs of two laps each - four
    counted laps, and no run long enough for `find_incidents` to judge."""
    from dataclasses import replace

    laps = _laps([95.0, 90.0, 90.5, 120.0, 100.0, 90.2, 90.4])
    laps[3] = replace(laps[3], is_pit_lap=True)
    trend = session_trend(laps, kind="practice", evidence_for=_off_on())
    assert trend.incidents is None
    assert trend.consistency_n >= 3 and trend.consistency_sd_s is None


def test_three_clean_laps_are_enough_to_judge():
    trend = session_trend(_laps([95.0, 90.0, 90.2, 90.4]), kind="practice",
                          evidence_for=_off_on())
    assert trend.judged_laps == 3 and trend.incidents == 0


def test_an_incident_lap_is_not_in_the_lap_one_reference():
    """Lap 6 went off: left in, three reference laps from lap 5 on; taken
    out, two - which is no reference at all."""
    race = [100.0, 91.0, 91.0, 91.0, 90.0, 110.0, 90.0]
    trend = session_trend(_laps(race), kind="race", evidence_for=_off_on(6))
    assert trend.lap_one_reference_n == 2
    assert trend.lap_one_cost_s is None


def test_a_pit_on_lap_one_is_not_a_lap_one_cost():
    from dataclasses import replace

    race = [160.0, 91.0, 91.0, 91.0, 90.0, 90.2, 89.8, 90.1]
    laps = _laps(race)
    laps[0] = replace(laps[0], is_pit_lap=True)
    trend = session_trend(laps, kind="race", evidence_for=_off_on())
    assert trend.lap_one_cost_s is None
    assert any("pit lap" in line for line in trend.silences)


def test_a_lap_one_stored_as_an_incident_says_its_cost_includes_it():
    """Critic 6, P11."""
    from dataclasses import replace

    race = [100.0, 91.0, 91.0, 91.0, 90.0, 90.2, 89.8, 90.1]
    laps = _laps(race)
    laps[0] = replace(laps[0], excluded=True, exclusion_reason="incident")
    trend = session_trend(laps, kind="race", evidence_for=_off_on())
    assert trend.lap_one_cost_s is not None
    assert any("lap one is stored as an incident" in line for line in trend.silences)
    assert not any("not judged for incidents" in line for line in trend.silences)


def test_a_rolling_start_says_so():
    race = [100.0, 91.0, 91.0, 91.0, 90.0, 90.2, 89.8, 90.1]
    trend = session_trend(_laps(race), kind="race", start_type="Rolling",
                          evidence_for=_off_on())
    assert trend.lap_one_cost_s is not None
    assert any("rolling start" in line for line in trend.silences)


def test_no_spread_over_laps_nobody_screened():
    """Critic 6: "sd 10.247 s (n=2)" off laps with no incident verdict."""
    trend = session_trend(_laps([95.0, 90.0, 100.2]), kind="practice",
                          evidence_for=_off_on())
    assert trend.incidents is None and trend.consistency_sd_s is None


def test_one_lap_of_spread_is_not_a_spread():
    trend = session_trend(_laps([95.0, 90.0]), kind="practice",
                          evidence_for=_off_on())
    assert trend.consistency_sd_s is None
    assert trend.consistency_n <= 1
