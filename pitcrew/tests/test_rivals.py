"""What a rival's stop costs, from what the screen shows.

The numbers in these tests are read off the Spa replay of 1 Sep 2026
(`InstantReplays/2026-09-01 07-34-03.mp4`), where the leaderboard carries a
pit flag, a compound disc and a live fuel figure for every car that has
entered the pit lane.
"""
from __future__ import annotations

import pytest

from pitcrew.race.rivals import (
    DEAD_TIME_S,
    Stop,
    deferring_costs_s,
    fill_at,
    earliest_stop_lap,
    forced_stop_lap,
    fuel_swing,
)

RATE = 1.0          # L/s, measured three ways: tank telemetry, frames, screen


def test_litres_taken_is_the_difference_between_the_two_readings():
    """CruisingChaos: entered on 10, left on 93."""
    assert Stop(fuel_in_l=10.0, fuel_out_l=93.0).litres == pytest.approx(83.0)


def test_an_unread_reading_gives_no_litres_rather_than_a_full_tank():
    assert Stop(fuel_in_l=None, fuel_out_l=93.0).litres is None
    assert Stop(fuel_in_l=10.0, fuel_out_l=None).litres is None
    assert Stop().litres is None


def test_a_negative_fill_is_refused_rather_than_clamped():
    """CLAUDE.md rule 9: a quantity that came out negative is a reading whose
    reference is wrong, not a quantity of zero. Clamping turns "I misread"
    into a confident "he took nothing"."""
    assert Stop(fuel_in_l=60.0, fuel_out_l=20.0).litres is None


def test_standing_time_is_the_fill_plus_the_measured_dead_time():
    stop = Stop(fuel_in_l=10.0, fuel_out_l=93.0)
    assert stop.standing_s(RATE) == pytest.approx(83.0 + DEAD_TIME_S)


def test_standing_time_needs_a_rate_and_says_so_without_one():
    stop = Stop(fuel_in_l=10.0, fuel_out_l=93.0)
    assert stop.standing_s(None) is None
    assert stop.standing_s(0.0) is None


# ------------------------------------------------------------- the swing

def test_the_swing_is_the_difference_in_standing_time():
    """Boxhead came in on 1 L, CruisingChaos on 10. Take the same amount and
    the one who came in emptier stands there longer."""
    mine = Stop(fuel_in_l=45.0, fuel_out_l=69.0)          # Beeni, 24 L
    theirs = Stop(fuel_in_l=10.0, fuel_out_l=93.0)        # 83 L
    swing = fuel_swing(mine, theirs, RATE)
    assert swing.known
    assert swing.seconds == pytest.approx(59.0)
    assert "+59 s" in swing.reason


def test_a_swing_against_us_is_negative_and_says_so():
    mine = Stop(fuel_in_l=8.0, fuel_out_l=88.0)           # 80 L
    theirs = Stop(fuel_in_l=45.0, fuel_out_l=69.0)        # 24 L
    swing = fuel_swing(mine, theirs, RATE)
    assert swing.seconds == pytest.approx(-56.0)


def test_an_unread_side_names_which_side_was_unread():
    """CLAUDE.md rule 12: the reason must come from the expression that
    produced the answer."""
    known = Stop(fuel_in_l=45.0, fuel_out_l=69.0)
    swing = fuel_swing(known, Stop(), RATE)
    assert not swing.known
    assert "theirs" in swing.reason and "ours" not in swing.reason
    assert swing.ours_standing_s is not None
    assert swing.theirs_standing_s is None


def test_the_dead_time_cancels_between_two_cars():
    """Both pay it, so it must not change the swing — only the fill does."""
    a = Stop(fuel_in_l=0.0, fuel_out_l=30.0)
    b = Stop(fuel_in_l=0.0, fuel_out_l=50.0)
    assert fuel_swing(a, b, RATE).seconds == pytest.approx(20.0)


# -------------------------------------------------------- staying out

def test_the_fill_is_the_same_length_whatever_lap_the_stop_happens_on():
    """The correction, and it was this module's headline claim.

    A lap deferred shrinks the fill by a lap's burn AND means arriving with a
    lap's burn less aboard. They cancel: the litres through the hose are
    `laps_total x burn - start`, with no lap term. Spa, 20 laps, 8 L a lap,
    full 100 L tank.
    """
    assert [fill_at(lap, 20, 8.0, 100.0) for lap in (8, 10, 12)] == [60.0] * 3


def test_below_the_tank_clamp_the_fill_is_capped_and_deferring_costs():
    """The one regime where the lap matters - and the old figure had the right
    magnitude with the wrong sign."""
    assert [fill_at(lap, 20, 8.0, 100.0) for lap in (5, 6, 7)] == [40.0, 48.0,
                                                                   56.0]
    assert deferring_costs_s(5, 20, 8.0, 100.0, 1.0) == pytest.approx(8.0)


def test_above_the_clamp_deferring_costs_and_saves_nothing():
    """Not eight seconds a lap. Zero."""
    assert deferring_costs_s(8, 20, 8.0, 100.0, 1.0) == pytest.approx(0.0)
    assert deferring_costs_s(10, 20, 8.0, 100.0, 1.0) == pytest.approx(0.0)


def test_a_lap_the_tank_cannot_reach_has_no_answer():
    """Entry fuel would be negative, which is not a car with an empty tank -
    it is a lap he cannot arrive at on this one."""
    assert fill_at(14, 20, 8.0, 100.0) is None
    assert deferring_costs_s(12, 20, 8.0, 100.0, 1.0) is None


def test_no_burn_no_answer():
    assert deferring_costs_s(8, 20, None, 100.0, 1.0) is None
    assert deferring_costs_s(8, 20, 8.0, 100.0, None) is None
    assert deferring_costs_s(8, 20, 0.0, 100.0, 1.0) is None
    assert deferring_costs_s(None, 20, 8.0, 100.0, 1.0) is None
    assert fill_at(8, None, 8.0, 100.0) is None
    assert fill_at(8, 20, 8.0, None) is None


def test_a_stop_lap_outside_the_race_is_refused():
    assert fill_at(-1, 20, 8.0, 100.0) is None
    assert fill_at(21, 20, 8.0, 100.0) is None


# ------------------------------------------------------------- the floor

def test_a_stop_cannot_be_called_before_the_tank_can_reach_the_flag():
    """20 laps, 8 L a lap, 100 L tank: 12.5 laps of range, so the earliest
    stop that still reaches the end is lap 8."""
    assert earliest_stop_lap(20, 5, 8.0, 100.0) == 8


def test_the_floor_never_points_backwards():
    assert earliest_stop_lap(20, 12, 8.0, 100.0) == 12


def test_the_floor_is_unknown_without_all_of_its_inputs():
    assert earliest_stop_lap(None, 5, 8.0, 100.0) is None
    assert earliest_stop_lap(20, 5, None, 100.0) is None
    assert earliest_stop_lap(20, 5, 8.0, None) is None
    assert earliest_stop_lap(20, 5, 0.0, 100.0) is None


# --------------------------------------------------- their constraint

def test_a_rival_who_left_on_a_short_fill_must_stop_again():
    """Boxhead came in on 1 L. Whatever he leaves with bounds his race."""
    stop = Stop(lap=10, fuel_out_l=41.0)
    assert forced_stop_lap(stop, 8.0) == 15


def test_an_unread_tank_is_not_a_full_one():
    assert forced_stop_lap(Stop(lap=10, fuel_out_l=None), 8.0) is None
    assert forced_stop_lap(Stop(lap=None, fuel_out_l=41.0), 8.0) is None
