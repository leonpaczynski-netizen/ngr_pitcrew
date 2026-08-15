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
    practice_clock_warning,
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


def test_the_declaration_beats_a_measurement_taken_off_practice():
    """His word is primary evidence; the reading corroborates it (§4.1).

    The reading comes from *practice*, and practice is frequently not run at
    the race's clock - which is what `practice_clock_warning` in this same
    module exists to report. It used to overwrite the declaration, so a race
    declared 18:00 x6 was planned against whatever the practice lobby was set
    to.
    """
    measured = ClockReading(1.0, 15.0, None, None, 9, "")
    start, end = race_span(measured, minutes=50.0, declared_start=18.0,
                           declared_multiplier=6.0)
    assert start == 18.0
    assert end == pytest.approx(23.0)


def test_a_frozen_practice_clock_never_becomes_the_races():
    """0.0 is a fact about that lobby and says nothing about the race.

    It is not None, so it won: a 50-minute race declared 18:00 x6 came back as
    the span (15:00, 15:00) - `raceSpanHours: 0.0`, `covered: true` - on a race
    that runs 18:00 to 23:00 with none of it driven.
    """
    frozen = ClockReading(0.0, 15.0, 15.0, None, 9, "")
    start, end = race_span(frozen, minutes=50.0, declared_start=18.0,
                           declared_multiplier=6.0)
    assert (start, end) == (18.0, pytest.approx(23.0))
    # And with nothing declared it fills nothing: no span at all beats a span
    # of zero hours reported as covered.
    assert race_span(frozen, minutes=50.0) is None


def test_a_measurement_fills_the_gap_the_driver_left():
    measured = ClockReading(6.0, 18.0, None, None, 9, "")
    start, end = race_span(measured, minutes=60.0)
    assert start == 18.0
    assert end == pytest.approx(24.0)


def test_the_typed_figures_are_used_until_something_is_measured():
    start, end = race_span(None, minutes=60.0, declared_start=9.0,
                           declared_multiplier=2.0)
    assert (start, end) == (9.0, 11.0)


def test_no_span_without_either():
    assert race_span(None, minutes=60.0) is None


# ------------------------------------------- practice run at the wrong clock

def test_practice_with_the_clock_frozen_is_called_out():
    """The driver's own reason: stopping the clock keeps the lobby light. It
    is also why a race run into the dark never gets practised - a frozen
    session sits at one hour and produces laps, not evidence."""
    sessions = [ClockReading(0.0, None, None, None, 11, ""),
                ClockReading(6.0, None, None, None, 15, "")]
    warning = practice_clock_warning(sessions, race_multiplier=6.0)
    assert "clock frozen" in warning
    assert "1 of 2" in warning


def test_practice_at_a_different_multiplier_is_called_out():
    sessions = [ClockReading(1.0, None, None, None, 4, "")]
    warning = practice_clock_warning(sessions, race_multiplier=6.0)
    assert "x1 against the race's x6" in warning


def test_practice_at_the_races_clock_raises_nothing():
    sessions = [ClockReading(6.0, None, None, None, 15, "")]
    assert practice_clock_warning(sessions, race_multiplier=6.0) is None


def test_nothing_is_claimed_without_a_race_multiplier():
    sessions = [ClockReading(0.0, None, None, None, 11, "")]
    assert practice_clock_warning(sessions, race_multiplier=None) is None


# ------------------------------------------------ reading it without frames
#
# Built from the 14 Aug Monza sessions, which are what exposed the defect:
# the clock runs at x6 from 15:56, and then stops dead at 18:50 because the
# circuit has no 24-hour cycle. Every lap after the pit stop sits at 18:50.

MONZA_START_H = 15.933
MONZA_CEILING_H = 18.833


def a_stored_lap(lap_num: int, *, start_hour: float, end_hour: float,
                 lap_s: float = 108.5) -> LapInput:
    """A lap carrying only the stored clock pair — no frames at all."""
    return LapInput(lap_num=lap_num, lap_time_ms=int(lap_s * 1000),
                    fuel_start=90.0, fuel_end=84.0,
                    tod_start_ms=int(start_hour * HOUR_MS),
                    tod_end_ms=int(end_hour * HOUR_MS))


def _monza_session() -> list[LapInput]:
    laps, hour = [], MONZA_START_H
    for lap_num in range(1, 27):
        end = min(hour + (108.5 * 6.0) / 3600.0, MONZA_CEILING_H)
        laps.append(a_stored_lap(lap_num, start_hour=hour, end_hour=end))
        hour = end
    return laps


def test_the_clock_is_readable_with_no_frame_ever_decoded():
    """The whole point of storing the pair on the lap.

    While the clock could only be read out of frame blobs, it could only be
    read from whichever laps something else had chosen to decode — and what
    was choosing decoded the last six counted laps per compound, for a tyre
    question.
    """
    reading = read_clock(_monza_session())
    assert all(lap.frames is None for lap in _monza_session())
    assert reading.multiplier == pytest.approx(6.0, abs=0.05)
    assert clock(reading.start_hour) == "15:56"
    assert reading.laps_sampled == 26


def test_the_tail_of_a_session_alone_reads_the_clock_as_stopped():
    """The regression, stated as the arithmetic that produced it.

    Monza's clock runs to the end of the circuit's range and holds there, so
    the last laps of a long session genuinely do not move. Read on their own
    they say the lobby holds a fixed time of day — a true statement about six
    laps and a false one about the session, and it was cached as the latter.
    """
    session = _monza_session()
    frozen = [lap for lap in session
              if lap.tod_start_ms == lap.tod_end_ms][-6:]
    assert len(frozen) == 6

    keyhole = read_clock(frozen)
    assert keyhole.multiplier == 0.0
    assert clock(keyhole.start_hour) == "18:50"

    whole = read_clock(session)
    assert whole.multiplier == pytest.approx(6.0, abs=0.05)
    assert clock(whole.stopped_at_hour) == "18:50"


def test_stored_stamps_win_over_frames():
    """Belt and braces: a lap carrying both is read from the stored pair.

    They cannot disagree in practice — one is lifted from the other at
    capture — but the fallback must not be able to override the fact.
    """
    lap = a_stored_lap(1, start_hour=10.0, end_hour=10.1)
    lap = type(lap)(**{**lap.__dict__,
                       "frames": [{"time_of_day_ms": 0},
                                  {"time_of_day_ms": 23 * HOUR_MS}]})
    assert lap_multiplier(lap) == pytest.approx(0.1 * HOUR_MS / 108_500, abs=0.05)


# ------------------------------------------------ writing it back to the event

def test_a_measured_clock_fills_an_event_that_has_not_been_told(store, event_id):
    """His question: why does practice never fill the start hour in?

    It was measured, cached against the circuit, and never written anywhere he
    could see it.
    """
    assert store.record_measured_clock(event_id, 15.933, 6.0) is True
    event = store.get_event(event_id)
    assert event["start_hour"] == 15.933
    assert event["time_multiplier"] == 6.0
    assert event["clock_source"] == "measured"


def test_it_never_writes_over_what_he_typed(store, event_id):
    """His declaration is primary evidence and the measurement corroborates
    it. A measurement that quietly replaced a declaration would destroy the
    disagreement between them, which is worth more than either."""
    store.update_event(event_id, start_hour=14.0, time_multiplier=1.0)
    assert store.record_measured_clock(event_id, 15.933, 6.0) is False
    assert store.get_event(event_id)["start_hour"] == 14.0


def test_a_figure_it_wrote_itself_is_updated_by_a_later_session(store, event_id):
    store.record_measured_clock(event_id, 15.933, 6.0)
    assert store.record_measured_clock(event_id, 9.5, 2.0) is True
    assert store.get_event(event_id)["start_hour"] == 9.5


def test_nothing_measured_writes_nothing(store, event_id):
    assert store.record_measured_clock(event_id, None, None) is False
    assert store.get_event(event_id)["clock_source"] is None
