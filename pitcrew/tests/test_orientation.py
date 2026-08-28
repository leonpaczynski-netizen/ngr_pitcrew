"""Where he is, when the screen no longer says.

The driver turned GT7's race-information HUD off on 28 Aug 2026 - lap number,
position and time remaining all came off the display, leaving car information
only. Those three now exist nowhere except in this call, which changes what it
is: not reassurance duplicating a dashboard, but the instrument.

*"Laps remaining must be 100% accurate even in a timed race... George can work
out my average lap time and time left divided by it rounded up to the next
whole lap. George can notify time at the start but from the half way point I
want time and laps remaining."*

The arithmetic he describes is `clock.laps_left` and was already there. What
was missing was that nothing said it, and that two things had to be right
first: the lap count, and the clock.
"""
from __future__ import annotations

from pitcrew.race.calls import (
    LAPS_FROM_FRACTION,
    RaceState,
    minutes_left,
    orientation,
)


def timed(**overrides) -> RaceState:
    fields = dict(lap=13, laps_total=22, race_minutes=30.0, position=3,
                  fuel_l=60.0, fuel_per_lap_l=6.0, last_said_lap=12,
                  status_every_laps=1)
    state = RaceState(**{**fields, **overrides})
    state.race_remaining_s = overrides.pop("_left", 660.0)
    return state


# ------------------------------------------------------------- the lap number

def test_the_lap_number_is_gt7s_count_not_the_app_s():
    """**Road Atlanta is on file.** GT7's `laps_completed` sat +1 above the
    app's on lap 1 and +2 by lap 20 - the crossing inside the pit sequence
    never reached the app - so its table holds 21 laps of a race he drove 22
    of. `laps_remaining()` has always applied that correction; the lap NUMBER
    never did, because nothing spoke it."""
    state = timed(lap=13)
    state.laps_dropped_seen = 1
    assert state.lap_now() == 14


def test_a_missed_crossing_is_named_as_two_laps_not_guessed_at():
    """A confident wrong lap number is worse than an honest pair, and with the
    HUD off he cannot check either against anything."""
    state = timed(lap=13)
    state.laps_dropped_seen = 1
    assert "Lap 13 or 14" in orientation(state)


def test_a_clean_count_says_one_number():
    assert orientation(timed(lap=13)).startswith("Lap 13")


# ------------------------------------------------------------------ the clock

def test_minutes_are_the_measurement():
    """The app timer runs from the green and is reconciled against GT7's own
    exact lap figures. The lap count divides it by a median and inherits that
    median's error - so the clock is said whenever it exists, and the laps
    only when they resolve."""
    state = timed()
    state.race_remaining_s = 660.0
    assert minutes_left(state) == "11 minutes left."


def test_the_last_minute_is_counted_in_seconds():
    state = timed()
    state.race_remaining_s = 45.0
    assert minutes_left(state) == "45 seconds left."


def test_a_clock_it_does_not_have_is_said_rather_than_dropped():
    """With the HUD off, a race with no clause about its own length is
    indistinguishable from a race with no end - and from a dead app."""
    state = timed()
    state.race_remaining_s = None
    assert "I don't have the clock" in orientation(state)


# ------------------------------------------------- time first, then time+laps

def test_the_first_half_is_the_clock_only():
    """His call, and it matches the measurement: `ceil(time/lap)` is
    unresolvable early - on a real 30-minute race the first four crossings
    would have flipped on a median error of 0.12-0.66 s against a 2.04 s
    spread - and firms up as the remaining time shrinks."""
    state = timed(lap=3, laps_total=22)
    state.race_remaining_s = 30.0 * 60 * (1.0 - LAPS_FROM_FRACTION) + 60
    said = orientation(state)
    assert "minutes left" in said
    assert "to go" not in said


def test_from_halfway_it_is_both():
    state = timed(lap=13, laps_total=22)
    state.race_remaining_s = 660.0
    state.laps_estimate_firm = True
    assert orientation(state) == "Lap 13. 11 minutes left. 9 laps to go."


def test_an_unresolved_count_names_both_candidates():
    """`ceil` flips when the time left is near a whole number of laps. There
    the answer is not unknown - it is one of two, and naming them beats
    picking one and beats the silence this used to fall to."""
    state = timed(lap=13, laps_total=22)
    state.race_remaining_s = 660.0
    state.laps_estimate_firm = False
    assert orientation(state) == "Lap 13. 11 minutes left. 9 or 10 laps to go."


# -------------------------------------------------------------- the lap race

def test_a_lap_race_says_the_lap_and_what_is_left_of_it():
    """**One number per sentence.** The pack plays a call by peeling known
    sentences and splitting what is left on its single number, so "Lap 7 of
    24." carries two and falls whole to live synthesis - a pause on every
    crossing at the cadence he asked for. Two sentences cost one clip each and
    say more: the count he is on and the count still to run."""
    state = RaceState(lap=7, laps_total=24, position=4)
    assert orientation(state) == "Lap 7. 17 laps to go."


def test_a_lap_race_with_no_distance_still_says_the_lap():
    state = RaceState(lap=7, position=4)
    assert orientation(state) == "Lap 7."


def test_nothing_is_said_before_the_first_crossing():
    assert orientation(RaceState(lap=0, laps_total=24)) == ""
