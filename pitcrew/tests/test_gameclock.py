"""What a lobby's time-of-day preset does, read off GT7's own clock.

The lobby offers names, not hours - "Late Morning", "Afternoon" - and what hour
each means differs by circuit. No published table maps one to the other: the
community lists are from 2022, cover a subset of circuits, and give ranges
rather than presets.

It does not need looking up. GT7 broadcasts its clock, so the hour, the
multiplier and - the finding no table carries - **where the clock stops** all
come off the stream.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.gameclock import (
    ClockReading,
    clock,
    lap_multiplier,
    race_span,
    read_clock,
)
from pitcrew.analysis.session import LapInput

HOUR_MS = 3_600_000


def a_lap(lap_num: int, *, start_hour: float, multiplier: float,
          lap_s: float = 108.0, ceiling_hour: float | None = None) -> LapInput:
    """One lap whose game clock advances at `multiplier`, optionally capped."""
    frames = []
    for index in range(60):
        game = start_hour * HOUR_MS + index * (lap_s / 60) * 1000 * multiplier
        if ceiling_hour is not None:
            game = min(game, ceiling_hour * HOUR_MS)
        frames.append({"time_of_day_ms": int(game)})
    return LapInput(lap_num=lap_num, lap_time_ms=int(lap_s * 1000),
                    fuel_start=90.0, fuel_end=84.0, frames=frames)


def a_session(count: int, *, start_hour: float, multiplier: float,
              ceiling_hour: float | None = None) -> list[LapInput]:
    laps, hour = [], start_hour
    for n in range(1, count + 1):
        laps.append(a_lap(n, start_hour=hour, multiplier=multiplier,
                          ceiling_hour=ceiling_hour))
        hour += (108.0 * multiplier) / 3600.0
    return laps


# ------------------------------------------------------------ the multiplier

def test_the_multiplier_is_the_clock_against_real_time():
    """Session 9 of the Monza practice reads exactly 6.00, eight laps running."""
    assert lap_multiplier(a_lap(1, start_hour=15.0, multiplier=6.0)) == \
        pytest.approx(6.0, abs=0.15)


def test_a_frozen_clock_is_a_fixed_time_of_day_not_a_missing_one():
    reading = read_clock(a_session(5, start_hour=15.0, multiplier=0.0))
    assert reading.multiplier == 0.0
    assert "fixed time of day" in reading.note


def test_no_clock_at_all_says_it_does_not_know():
    """Every lap recorded before the channel existed."""
    bare = [LapInput(lap_num=1, lap_time_ms=108_000, fuel_start=90.0,
                     fuel_end=84.0, frames=[{"speed_kph": 100.0}])]
    reading = read_clock(bare)
    assert reading.measured is False
    assert "Run one session" in reading.note


# ------------------------------------------------------------ the start hour

def test_the_preset_start_hour_comes_off_the_stream():
    reading = read_clock(a_session(4, start_hour=18.83, multiplier=6.0))
    assert clock(reading.start_hour) == "18:50"


# -------------------------------------------------- where the clock stops

def test_a_circuit_without_a_24_hour_cycle_stops_and_says_so():
    """It holds at the end of its range rather than rolling into the next
    morning, which is a hard ceiling on any race run there."""
    laps = a_session(12, start_hour=18.83, multiplier=6.0, ceiling_hour=20.5)
    reading = read_clock(laps)
    assert clock(reading.stopped_at_hour) == "20:30"
    assert "no 24-hour cycle" in reading.note


def test_a_24_hour_circuit_never_stops():
    reading = read_clock(a_session(8, start_hour=18.0, multiplier=6.0))
    assert reading.stopped_at_hour is None


# ------------------------------------------------------------- the race span

def test_the_span_is_capped_by_the_circuits_own_clock():
    """The finding: 50 minutes at x6 looks like five hours of evening, and at
    Monza it is an hour and forty because the clock stops at 20:30."""
    monza = ClockReading(6.0, 18.83, 20.5, 20.5, 15, "")
    start, end = race_span(monza, minutes=50.0)
    assert clock(start) == "18:50"
    assert clock(end) == "20:30"
    assert end - start == pytest.approx(1.67, abs=0.01)


def test_a_24_hour_circuit_runs_the_whole_span():
    enduro = ClockReading(12.0, 18.0, None, None, 20, "")
    start, end = race_span(enduro, minutes=120.0)
    assert (end - start) == pytest.approx(24.0)


def test_a_measurement_beats_the_typed_figures():
    measured = ClockReading(6.0, 18.0, None, None, 9, "")
    start, end = race_span(measured, minutes=60.0, declared_start=9.0,
                           declared_multiplier=1.0)
    assert start == 18.0
    assert end == pytest.approx(24.0)


def test_the_typed_figures_are_used_until_something_is_measured():
    start, end = race_span(None, minutes=60.0, declared_start=9.0,
                           declared_multiplier=2.0)
    assert (start, end) == (9.0, 11.0)


def test_no_span_without_either():
    assert race_span(None, minutes=60.0) is None
