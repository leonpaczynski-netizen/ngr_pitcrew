"""A refuel that lands inside one lap still ends the tank.

Event 11, session 158 (RSR, Sardegna, 10 Sep 2026): lap 11 opened on 31.4 L
and closed on 93.1 L with `is_pit_lap = 0`. The runs were split only where the
tank rose *between* two laps, so laps 12-16 were read as laps 12+ of the same
run - every tyre-age window after that stop was wrong, and the stop lap's fuel
burn read negative.

The fill opens the run on the lap after it, exactly where a flagged pit lap
would put the boundary: one stop, one split, whether or not a detector saw it.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.analysis.runs import (
    auto_out_laps,
    compound_for_new_lap,
    refuelled_between,
    refuelled_within,
    run_start_flags,
    split_runs,
    starts_run,
)
from pitcrew.analysis.session import LapInput

BURN = 6.8


def a_lap(lap_num: int, fuel_start, fuel_end, **overrides) -> LapInput:
    fields = dict(lap_num=lap_num, lap_time_ms=101_000, fuel_start=fuel_start,
                  fuel_end=fuel_end, compound="RM", session_id=158,
                  practice_mode="lobby")
    fields.update(overrides)
    return LapInput(**fields)


def session_158() -> list[LapInput]:
    """Ten laps down from full, a fill inside lap 11, eight more laps."""
    laps = [a_lap(n, 100.0 - BURN * (n - 1), 100.0 - BURN * n)
            for n in range(1, 11)]
    laps.append(a_lap(11, laps[-1].fuel_end, 93.06))
    laps += [a_lap(n, 93.06 - BURN * (n - 12), 93.06 - BURN * (n - 11))
             for n in range(12, 20)]
    return laps


def test_a_fill_inside_a_lap_is_seen():
    assert refuelled_within(a_lap(11, 31.4, 93.06)) is True
    assert refuelled_within(a_lap(5, 72.4, 65.5)) is False
    # Inside the margin: a net rise of half a litre or less is not a fill.
    assert refuelled_within(a_lap(5, 50.0, 50.5)) is False


def test_session_158_splits_after_the_stop_lap():
    runs = split_runs(session_158())
    assert [(run.first_lap, run.last_lap) for run in runs] == [(1, 11), (12, 19)]
    assert runs[1].refuelled_before is True


def test_tyre_age_restarts_on_the_lap_after_the_fill():
    runs = split_runs(session_158())
    ages = {lap.lap_num: age for run in runs for age, lap in enumerate(run.laps)}
    assert ages[12] == 0
    assert ages[16] == 4


def test_the_boundary_is_where_a_flagged_pit_lap_puts_it():
    """The same stop, flagged or not, is the same split (CLAUDE.md rule 13)."""
    unflagged = session_158()
    flagged = [LapInput(**{**lap.__dict__, "is_pit_lap": lap.lap_num == 11})
               for lap in unflagged]
    assert ([(r.first_lap, r.last_lap) for r in split_runs(unflagged)]
            == [(r.first_lap, r.last_lap) for r in split_runs(flagged)])
    assert ([r.refuelled_before for r in split_runs(unflagged)]
            == [r.refuelled_before for r in split_runs(flagged)])


def test_the_tyre_answer_is_read_off_the_stop_lap():
    laps = session_158()
    laps[10] = LapInput(**{**laps[10].__dict__, "tyres_changed": True})
    assert split_runs(laps)[1].tyres_changed_before is True


def test_the_lap_after_the_fill_is_the_out_lap():
    assert 12 in auto_out_laps(session_158())


def test_a_session_opening_on_a_fill_is_not_split():
    """Every race on file opens at ~50 L and fills during lap 1 on the grid.
    There is no tank before it to separate, so lap 2 is not a new run."""
    laps = [a_lap(1, 49.9, 91.5, practice_mode=None)]
    laps += [a_lap(n, 91.5 - BURN * (n - 2), 91.5 - BURN * (n - 1),
                   practice_mode=None) for n in range(2, 8)]
    assert [(r.first_lap, r.last_lap) for r in split_runs(laps)] == [(1, 7)]


def test_an_opening_fill_after_another_session_is_not_split_either():
    """An event export concatenates sessions: the opener's `before` is the
    last lap of the session ahead of it, and the session change is the
    boundary already."""
    first = [a_lap(n, 100.0 - BURN * (n - 1), 100.0 - BURN * n, session_id=1)
             for n in range(1, 4)]
    second = [a_lap(4, 49.9, 91.5, session_id=2)]
    second += [a_lap(n, 91.5 - BURN * (n - 5), 91.5 - BURN * (n - 4),
                     session_id=2) for n in range(5, 8)]
    assert ([(r.first_lap, r.last_lap) for r in split_runs(first + second)]
            == [(1, 3), (4, 7)])


def test_a_fill_that_crossed_the_line_is_not_split_twice():
    """A box past the line: the pit lap is flagged, and the fill lands in the
    out-lap after it. That out-lap already opened the run."""
    laps = [a_lap(n, 100.0 - BURN * (n - 1), 100.0 - BURN * n)
            for n in range(1, 13)]
    laps[11] = LapInput(**{**laps[11].__dict__, "is_pit_lap": True})
    laps.append(a_lap(13, laps[-1].fuel_end, 48.2, is_out_lap=True))
    laps += [a_lap(n, 48.2 - BURN * (n - 14), 48.2 - BURN * (n - 13))
             for n in range(14, 18)]
    assert ([(r.first_lap, r.last_lap) for r in split_runs(laps)]
            == [(1, 12), (13, 17)])


def test_missing_fuel_is_cannot_tell_not_a_refuel():
    assert refuelled_within(a_lap(3, None, 80.0)) is False
    assert refuelled_within(a_lap(3, 80.0, None)) is False
    assert refuelled_between(a_lap(2, 90.0, None), a_lap(3, 99.0, 92.0)) is False
    laps = [a_lap(1, 100.0, 93.2), a_lap(2, 93.2, 86.4), a_lap(3, None, None),
            a_lap(4, 79.6, 72.8)]
    assert len(split_runs(laps)) == 1


def test_a_caller_holding_two_laps_cannot_tell():
    """Without the lap before `previous`, a fill inside it is not a stop."""
    laps = session_158()
    assert starts_run(laps[10], laps[11]) is False
    assert starts_run(laps[10], laps[11], before=laps[9]) is True


@dataclass
class Row:
    """The rack's shape: mutable, and no `is_out_lap` unless it is given."""
    lap_id: int
    lap_num: int
    fuel_start: float
    fuel_end: float
    compound: str | None = None
    is_pit_lap: bool = False
    tyres_changed: bool | None = None
    session_id: int | None = 158


def test_the_rack_rows_split_by_the_same_rule():
    rows = [Row(lap.lap_num, lap.lap_num, lap.fuel_start, lap.fuel_end)
            for lap in session_158()]
    flags = run_start_flags(rows)
    assert [row.lap_num for row, starts in zip(rows, flags) if starts] == [1, 12]
    assert ({run.first_lap for run in split_runs(session_158())}
            == {row.lap_num for row, starts in zip(rows, flags) if starts})


def test_a_compound_does_not_carry_across_the_fill():
    rows = [Row(lap.lap_num, lap.lap_num, lap.fuel_start, lap.fuel_end,
                compound="RM") for lap in session_158()]
    assert compound_for_new_lap(rows[10], rows[11], before=rows[9]) is None
    assert compound_for_new_lap(rows[9], rows[10], before=rows[8]) == "RM"


def test_the_live_rack_marks_the_same_run_starts():
    from pitcrew.ui.practice_screen import LapRow, run_start_ids

    rows = [LapRow(lap_id=lap.lap_num, lap_num=lap.lap_num,
                   lap_time_ms=lap.lap_time_ms, fuel_used=BURN,
                   fuel_start=lap.fuel_start, fuel_end=lap.fuel_end,
                   session_id=158)
            for lap in session_158()]
    assert run_start_ids(rows) == {1, 12}
