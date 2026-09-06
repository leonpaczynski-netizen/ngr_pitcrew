"""What followed a call, and the far larger set the app may not answer.

The log carried what was said, why and how sure, and nothing about what the
driver then did — so a call he acted on and a call he ignored read identically
afterwards. Those are the two that most need telling apart on this rig: he has
overruled the engineer and been right four sessions running.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.call_outcome import (
    ACTED,
    CANNOT_TELL,
    NOT_ACTED,
    outcome_for,
    summarise,
)
from pitcrew.race.calls import BOX_NOW, BOX_SOON, Call, TYRE_TEMP


@dataclass
class _Lap:
    lap_num: int
    is_pit_lap: bool = False
    short_shift_rpm: float | None = None


def a_race(count: int, *, pit_on: int | None = None,
           short_shift_on: int | None = None):
    return [_Lap(lap_num=n,
                 is_pit_lap=(n == pit_on),
                 short_shift_rpm=450.0 if n == short_shift_on else 0.0)
            for n in range(1, count + 1)]


def a_call(kind=BOX_NOW, lap=10, **kw):
    return Call(kind=kind, lap=lap, call="Box this lap or next.",
                reason="Fuel is the constraint.", **kw)


# ------------------------------------------------------------- box calls

def test_a_stop_inside_the_window_is_acted_on():
    outcome = outcome_for(a_call(lap=10), a_race(20, pit_on=11))
    assert outcome.verdict == ACTED
    assert "lap 11" in outcome.detail


def test_no_stop_in_a_fully_driven_window_is_not_acted_on():
    """**Not a judgement on the driver.** At Fuji he ignored two box calls,
    ran to the flag and finished P5, and the app's own binding-constraint
    figure was the thing that was wrong."""
    outcome = outcome_for(a_call(lap=10), a_race(20))
    assert outcome.verdict == NOT_ACTED
    assert "10-12" in outcome.detail


def test_a_stop_after_the_window_is_not_late_compliance():
    """"Box this lap or next" is the instruction. A stop three laps later is
    a different decision, and recording it as obedience would make the log
    agree with whatever happened."""
    assert outcome_for(a_call(lap=10), a_race(20, pit_on=14)).verdict == NOT_ACTED


def test_a_window_the_race_never_reached_says_so():
    """**The flag is not disobedience.** A box call on the last lap with two
    laps of window and none of them driven says nothing about the driver."""
    outcome = outcome_for(a_call(lap=19), a_race(20))
    assert outcome.verdict == CANNOT_TELL
    assert "never fully driven" in outcome.detail


def test_a_call_after_the_last_lap_on_file_is_unanswerable():
    outcome = outcome_for(a_call(lap=25), a_race(20))
    assert outcome.verdict == CANNOT_TELL


def test_box_soon_is_judged_the_same_way_as_box_now():
    assert outcome_for(a_call(kind=BOX_SOON, lap=5),
                       a_race(20, pit_on=6)).verdict == ACTED


# ------------------------------------------------------- the short-shift

def test_a_short_shift_is_answerable_because_the_beep_records_it():
    call = a_call(kind=TYRE_TEMP, lap=8, short_shift_drop_rpm=450.0)
    outcome = outcome_for(call, a_race(20, short_shift_on=9))
    assert outcome.verdict == ACTED
    assert "lap 9" in outcome.detail


def test_a_short_shift_nobody_took_is_recorded_as_such():
    call = a_call(kind=TYRE_TEMP, lap=8, short_shift_drop_rpm=450.0)
    assert outcome_for(call, a_race(20)).verdict == NOT_ACTED


# ------------------------------------------- everything the feed cannot see

def test_a_call_the_feed_cannot_confirm_says_so_rather_than_guessing():
    """**GT7 broadcasts no fuel map, no brake balance and no driving style.**
    Reporting those as "not acted on" would turn a missing channel into a
    disobedient driver - a zero standing in for a measurement nobody took."""
    outcome = outcome_for(a_call(kind=TYRE_TEMP, lap=10), a_race(20))
    assert outcome.verdict == CANNOT_TELL
    assert "no fuel map" in outcome.detail


def test_the_unanswerable_ones_are_counted_not_dropped():
    """A summary reading "2 acted, 1 not" over nine calls invites the reader
    to believe the app watched all nine."""
    calls = [a_call(lap=5), a_call(lap=10),
             a_call(kind=TYRE_TEMP, lap=12),
             a_call(kind=TYRE_TEMP, lap=13)]
    tally = summarise(calls, a_race(20, pit_on=6))
    assert tally[ACTED] == 1
    assert tally[NOT_ACTED] == 1
    assert tally[CANNOT_TELL] == 2
    assert sum(tally.values()) == len(calls)
