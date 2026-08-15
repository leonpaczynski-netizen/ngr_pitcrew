"""Which laps are out-laps, and why the answer depends on the session type.

The driver's account, which the capture set bears out: *"Lap one in a lobby is
always an out lap. In time trial you start on track before the s/f line."*

That is the difference between the app doing his housekeeping for him and the
app throwing away the fastest lap of the day. In six of the eight time trials
on record the opening lap is the quickest lap of the session.
"""
from __future__ import annotations

from pitcrew.analysis.runs import (
    LOBBY,
    TIME_TRIAL,
    auto_out_laps,
    split_runs,
)
from pitcrew.analysis.session import LapInput


def a_lap(lap_num: int, *, fuel_start: float, fuel_end: float,
          **overrides) -> LapInput:
    fields = dict(lap_num=lap_num, lap_time_ms=109_000, fuel_start=fuel_start,
                  fuel_end=fuel_end, compound="RH", session_id=1)
    fields.update(overrides)
    return LapInput(**fields)


def a_stint(first: int, count: int, *, tank: float = 100.0,
            **overrides) -> list[LapInput]:
    return [a_lap(first + n, fuel_start=tank - 6.5 * n,
                  fuel_end=tank - 6.5 * (n + 1), **overrides)
            for n in range(count)]


def test_a_lobby_session_opens_with_an_out_lap():
    """Out of the pit box on cold tyres. It always was one."""
    laps = a_stint(1, 5, practice_mode=LOBBY)
    assert auto_out_laps(laps) == {1}


def test_a_time_trial_opens_with_a_timed_lap_and_it_is_kept():
    """The car starts on the track ahead of the line, so GT7 times the first
    lap like any other — and on the capture set it is usually the best one."""
    laps = a_stint(1, 5, practice_mode=TIME_TRIAL)
    assert auto_out_laps(laps) == set()


def test_a_time_trial_still_gets_an_out_lap_after_a_stop():
    """The exception is about where the car starts the session, nothing else.
    Come in mid-session and the lap after it is an out-lap either way."""
    laps = a_stint(1, 4, practice_mode=TIME_TRIAL) + a_stint(
        5, 4, practice_mode=TIME_TRIAL)
    assert auto_out_laps(laps) == {5}


def test_an_undeclared_session_is_treated_as_a_lobby():
    """The safer of the two errors, and the one the app made before the
    exception existed: a struck lap is visible on the rack and can be put
    back, a counted out-lap is invisible and moves every aggregate."""
    assert auto_out_laps(a_stint(1, 5)) == {1}


def test_a_stop_for_tyres_alone_opens_a_run_and_so_an_out_lap():
    """The old rule asked for a refuel, which was a proxy for "a stop
    happened" written when a stop could not be detected."""
    laps = a_stint(1, 4, practice_mode=LOBBY)
    laps[-1] = LapInput(**{**laps[-1].__dict__, "is_pit_lap": True,
                           "tyres_changed": True})
    # No refuel: the tank keeps falling straight through the stop.
    laps += [a_lap(5, fuel_start=laps[-1].fuel_end,
                   fuel_end=laps[-1].fuel_end - 6.5, practice_mode=LOBBY)]
    assert 5 in auto_out_laps(laps)


def test_going_back_to_the_garage_opens_a_run():
    """Stopping and restarting the app means he went back in, so the laps
    either side are not one continuous stint."""
    first = a_stint(1, 3, practice_mode=TIME_TRIAL)
    second = [a_lap(n, fuel_start=100.0, fuel_end=93.5, session_id=2,
                    practice_mode=LOBBY) for n in (4,)]
    assert [run.first_lap for run in split_runs(first + second)] == [1, 4]
    assert auto_out_laps(first + second) == {4}


def test_every_time_trial_of_the_day_keeps_its_opening_lap():
    """The exception used to be applied to `runs[0]` alone.

    `practice_mode` is per session and an event export concatenates them all,
    so the second and third time trial of the day each lost their opening lap
    - the fastest lap of the session in six of the eight on record - and
    `_rows_for_event` re-struck it on every rebuild, so it could not be put
    back by hand either.
    """
    first = a_stint(1, 3, practice_mode=TIME_TRIAL)
    second = [a_lap(n, fuel_start=100.0 - 6.5 * (n - 4),
                    fuel_end=100.0 - 6.5 * (n - 3), session_id=2,
                    practice_mode=TIME_TRIAL) for n in (4, 5, 6)]
    assert auto_out_laps(first + second) == set()


def test_a_refuel_inside_a_time_trial_still_opens_an_out_lap():
    """The exception is about where the car starts the *session*. A run that
    opens mid-session opens in the box like any other."""
    laps = (a_stint(1, 3, practice_mode=TIME_TRIAL)
            + a_stint(4, 3, practice_mode=TIME_TRIAL))
    assert auto_out_laps(laps) == {4}
