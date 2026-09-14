""""Two to go." in a lap race is not "on the clock".

Bathurst, 14 Sep 2026, a 20-lap race: "Two to go. On the clock." The
`_laps_to_go` branches are about a timed race's estimate, and the fall-through
named a clock the count never used.
"""
from __future__ import annotations

from pitcrew.race.calls import HIGH, LAPS_TO_GO, MEDIUM, RaceState, _laps_to_go


def test_a_lap_race_counts_down_with_no_clock_in_the_sentence():
    state = RaceState(lap=18, laps_total=20, laps_to_go_estimate=2,
                      laps_estimate_firm=True)
    call = _laps_to_go(state)
    assert call.kind == LAPS_TO_GO and call.call == "Two to go."
    assert call.reason == "" and call.confidence == HIGH
    assert call.spoken() == "Two to go."
    last = _laps_to_go(RaceState(lap=19, laps_total=20, laps_to_go_estimate=1))
    assert last.spoken() == "Last lap."


def test_a_lap_race_never_hedges_on_a_clock_it_does_not_have():
    state = RaceState(lap=18, laps_total=20, laps_to_go_estimate=2,
                      laps_count_hedged=True, clock_corroborated=False)
    call = _laps_to_go(state)
    assert call.call == "Two to go."
    assert "clock" not in call.spoken().lower()
    assert "lap times" not in call.spoken().lower()


def test_a_missed_crossing_in_a_lap_race_is_recorded_not_blamed_on_a_timer():
    state = RaceState(lap=17, laps_total=20, laps_to_go_estimate=2,
                      laps_dropped_seen=1)
    call = _laps_to_go(state)
    assert call.spoken() == "Two to go."
    assert call.confidence == MEDIUM


def test_a_timed_race_still_says_what_it_rests_on():
    state = RaceState(lap=12, laps_total=14, race_minutes=30.0,
                      laps_to_go_estimate=2)
    assert _laps_to_go(state).reason == "On the clock."
