"""Whether practice has driven the conditions the race will be run in.

GT7 runs its own clock. 50 real minutes at x6 is five hours of game time; a
two-hour enduro at x12 is a full day and night. The track cools through it,
which lengthens a stint and can leave a harder compound below its working
range - and the two pull opposite ways, so it cannot be reasoned out. It has to
be driven.

GT7 broadcasts neither track nor air temperature, so the only way to know
whether a measurement belongs to the race's conditions is where in the day it
was taken. That is the gap this reports. It never predicts the temperature.
"""
from __future__ import annotations

from pitcrew.analysis.daylight import (
    coverage,
    covered_hours,
    hour_of,
    lap_hour,
    race_span_h,
)
from pitcrew.analysis.session import LapInput

HOUR_MS = 3_600_000


def a_lap(lap_num: int, hour: float | None) -> LapInput:
    frames = None
    if hour is not None:
        frames = [{"time_of_day_ms": int(hour * HOUR_MS)} for _ in range(10)]
    return LapInput(lap_num=lap_num, lap_time_ms=94_000, fuel_start=90.0,
                    fuel_end=86.0, frames=frames)


# ------------------------------------------------------------- reading the clock

def test_the_clock_reads_as_an_hour_of_the_day():
    assert hour_of(0) == 0.0
    assert hour_of(int(14.5 * HOUR_MS)) == 14.5
    assert hour_of(None) is None


def test_a_clock_past_midnight_wraps():
    assert hour_of(int(26.0 * HOUR_MS)) == 2.0


def test_a_lap_is_placed_by_its_own_frames():
    assert lap_hour(a_lap(1, 14.0)) == 14.0


def test_a_lap_recorded_before_the_clock_was_captured_has_no_hour():
    """Every lap up to now. They cannot be placed in the day, and saying so
    is different from saying they were driven at midnight."""
    assert lap_hour(a_lap(1, None)) is None
    assert covered_hours([a_lap(1, None), a_lap(2, None)]) == []


# ---------------------------------------------------------------- the race span

def test_a_race_span_is_the_clock_times_the_multiplier():
    """50 real minutes at x6 is five hours of game time."""
    assert race_span_h(15.0, 50.0, 6.0) == (15.0, 20.0)


def test_a_span_past_midnight_stays_contiguous():
    """A race from 22:00 running eight game hours ends at 06:00. Saying 6.0
    would read as an eight-hour race run backwards."""
    start, end = race_span_h(22.0, 40.0, 12.0)
    assert (start, end) == (22.0, 30.0)


def test_no_span_without_the_declaration():
    assert race_span_h(None, 50.0, 6.0) is None
    assert race_span_h(15.0, 50.0, None) is None


# ------------------------------------------------------------------ coverage

def test_practice_in_the_race_hours_is_covered():
    laps = [a_lap(n, hour) for n, hour in enumerate([15.0, 16.0, 17.0], 1)]
    report = coverage(laps, race_span_h(15.0, 20.0, 6.0))   # 15:00 - 17:00
    assert report["covered"] is True
    assert report["uncoveredHours"] == []


def test_the_hours_never_driven_are_named():
    """The finding: a plan for the closing stints of a night race, built
    entirely on daytime running, rests on nothing - and unlike a missing wear
    rate it does not announce itself, because every number in it looks
    measured."""
    laps = [a_lap(n, 15.0) for n in range(1, 4)]
    report = coverage(laps, race_span_h(15.0, 50.0, 6.0))   # 15:00 - 20:00
    assert report["covered"] is False
    assert 20.0 in report["uncoveredHours"]
    assert "never been driven" in report["note"]
    assert "cools" in report["note"]


def test_practice_close_enough_counts():
    """Track temperature moves slowly; half an hour either side is the same
    conditions, and tighter would call almost everything uncovered."""
    laps = [a_lap(n, 15.4) for n in range(1, 4)]
    assert coverage(laps, race_span_h(15.0, 10.0, 6.0))["covered"] is True


def test_coverage_compares_around_the_clock():
    """23:30 practice covers a 00:00 race hour."""
    laps = [a_lap(n, 23.5) for n in range(1, 4)]
    assert coverage(laps, race_span_h(23.5, 5.0, 6.0))["covered"] is True


def test_an_undeclared_race_time_says_so_rather_than_passing():
    report = coverage([a_lap(1, 15.0)], None)
    assert report["covered"] is None
    assert "not declared" in report["note"]


def test_nothing_on_record_is_not_the_same_as_nothing_to_report():
    """Laps recorded before the clock existed are not evidence of darkness."""
    report = coverage([a_lap(1, None)], race_span_h(15.0, 50.0, 6.0))
    assert report["covered"] is False
    assert "No lap on record carries a time of day" in report["note"]


def test_the_enduro_case():
    """Two hours at x12 is a full day and night from an evening start."""
    span = race_span_h(18.0, 120.0, 12.0)
    assert span == (18.0, 42.0)
    report = coverage([a_lap(n, 14.0) for n in range(1, 4)], span)
    assert report["raceSpanHours"] == 24.0
    assert report["covered"] is False
    # An afternoon of practice says nothing about the small hours.
    assert len(report["uncoveredHours"]) > 20
