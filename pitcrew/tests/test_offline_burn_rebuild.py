"""The offline rebuild clamped a burn it could not read, and then counted it.

`_LapRow` is the stored lap seen as a live one, for `audit_line_from_laps` ->
the export's `strategy.outcome`. It read:

    self.fuel_used = max(0.0, (lap.fuel_start or 0.0) - (lap.fuel_end or 0.0))

`LapInput` carries no `fuel_added_l`, so every lap with a fill in it
differences to a large negative number and clamped to zero, and a lap with no
tank reading at one end differenced against `0.0` and clamped too. CLAUDE.md
rule 9: *"a quantity that came out negative is not a quantity of zero - it is
a reading whose reference is wrong, and clamping it converts 'I cannot tell
you' into a confident, well-formed, wrong answer."*

The second half is rule 12. `audit_line` quoted `len(clean)` - every green lap
- beside a median that `race_fuel_per_lap_l` had taken over the green laps
that actually **reported** a burn. Two expressions, one sample size, and the
larger of the two was the one said out loud.

(`pitcrew/telemetry/session_state.py:167-170` is the same clamp on the live
path and is deliberately NOT touched here: `laps.fuel_used` is `NOT NULL`, the
rebuild cascades into `lap_frames`, and a `None` there aborts inside a Qt slot.
That one needs a schema change.)
"""
from __future__ import annotations

import pytest

from pitcrew.race.expectations import (ExpectationTracker, _LapRow,
                                       audit_line_from_laps)


class _Stored:
    """A `laps` row as `LapInput` hands it over: two tank readings, no fill."""

    def __init__(self, num, ms, start, end, *, pit=False, out=False):
        self.lap_num = num
        self.lap_time_ms = ms
        self.fuel_start = start
        self.fuel_end = end
        self.is_pit_lap = pit
        self.is_out_lap = out


# ----------------------------------------------------------------- rule 9

def test_a_lap_that_took_fuel_reports_no_burn_rather_than_zero():
    """Session 204 lap 12: 8.36 L at the line, 91.87 at the next. 91.45 L went
    in. The difference is -83.5 and it is not a lap that burned nothing."""
    row = _LapRow(_Stored(12, 175_079, 8.36498, 91.87375, out=True))
    assert row.fuel_used is None
    assert "fuel_added_l" in row.fuel_used_why


def test_a_lap_with_no_tank_reading_says_which_end_was_missing():
    assert _LapRow(_Stored(4, 126_000, None, 66.4)).fuel_used is None
    row = _LapRow(_Stored(4, 126_000, 74.9, None))
    assert row.fuel_used is None
    assert row.fuel_used_why == "no tank reading at one end of the lap"


def test_an_ordinary_lap_still_differences():
    row = _LapRow(_Stored(13, 125_974, 91.87375, 83.45668))
    assert row.fuel_used == pytest.approx(8.417, abs=0.001)
    assert row.fuel_used_why is None


def test_an_unreadable_burn_never_enters_a_median():
    """It was excluded before too - as a clamped 0.0 against a `used > 0`
    filter - so no figure moves. What changes is that it is now excluded
    because it is missing rather than because zero happens to be falsy."""
    tracker = ExpectationTracker(planned_fuel_per_lap_l=10.625)
    for num in range(2, 8):
        tracker.note_lap(_LapRow(_Stored(num, 126_000, 90.0 - num * 8.4,
                                         90.0 - (num + 1) * 8.4)))
    before = tracker.race_fuel_per_lap_l()
    # A green lap in the middle of a refuel: nothing about it is readable.
    tracker.note_lap(_LapRow(_Stored(8, 126_000, 30.0, 95.0)))
    assert tracker.race_fuel_per_lap_l() == before
    assert tracker.race_burn_laps() == 6


# ---------------------------------------------------------------- rule 12

def test_the_audit_counts_the_laps_its_median_was_taken_over():
    """The count and the figure come from one expression. A green lap whose
    burn could not be read inflated the count and not the median."""
    tracker = ExpectationTracker(planned_fuel_per_lap_l=8.4)
    for num in range(2, 8):
        tracker.note_lap(_LapRow(_Stored(num, 126_000, 90.0 - num * 8.4,
                                         90.0 - (num + 1) * 8.4)))
    tracker.note_lap(_LapRow(_Stored(8, 126_000, 30.0, 95.0)))
    line = tracker.audit_line()
    assert "over 6 green laps" in line, line
    assert "1 more took fuel" in line, line


def test_a_race_with_nothing_unreadable_says_nothing_extra():
    tracker = ExpectationTracker(planned_fuel_per_lap_l=8.4)
    for num in range(2, 8):
        tracker.note_lap(_LapRow(_Stored(num, 126_000, 90.0 - num * 8.4,
                                         90.0 - (num + 1) * 8.4)))
    line = tracker.audit_line()
    assert "over 6 green laps" in line
    assert "could not be differenced" not in line


def test_the_real_race_rebuilds_to_the_burn_it_actually_ran():
    """Session 204's own laps, verbatim. The three laps carrying a fill are
    lap 1 (the grid) and the two out laps, all of which the green filter drops
    anyway - so the burn is unchanged and the honesty is the whole gain."""
    from pitcrew.tests.test_bathurst_race_204_target_burn import LAPS

    laps = [_Stored(num, ms, start, end, pit=bool(pit), out=bool(out))
            for num, (ms, start, end, _used, pit, out, _pos) in LAPS.items()]
    line = audit_line_from_laps(
        {"expected_fuel_per_lap_l": 10.625, "expected_fuel_samples": 30,
         "expected_lap_time_ms": 125_897, "expected_lap_time_samples": 30},
        laps)
    assert "ran 8.28 over 22 green laps" in line
    assert "22% under" in line
