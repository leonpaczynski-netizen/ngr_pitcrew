"""The three gap readouts: where a stop puts you, and how fast you are closing.

**Every gap box in every frame of available footage read `--:--.---`**, so a
live gap has never been through this. The arithmetic below is exercised on
figures; the reading is exercised on the fastest-lap banner, whose value is
known, and on the dash box it must refuse. That division is the honest state of
this module and the docstring says so too.
"""
from __future__ import annotations

import numpy as np

import pytest

from pitcrew.race.gaps import (
    MIN_LAPS_FOR_TREND,
    REJOIN_MARGIN_S,
    TREND_WORTH_SAYING_S,
    GapTrend,
    read_gaps,
    rejoin_against,
    stop_costs_s,
)

# Spa: 60 L to take at 1.0 L/s, and a measured 19.5 s in the lane.
SPA_FILL, RATE, LANE = 60.0, 1.0, 19.5
SPA_STOP = 79.5


# --- what a stop costs -----------------------------------------------------

def test_a_stop_is_the_fill_plus_the_lane():
    assert stop_costs_s(SPA_FILL, RATE, LANE) == SPA_STOP


def test_half_a_stop_cost_is_not_a_stop_cost():
    """CLAUDE.md rule 3: an unmeasured pit loss is not a pit loss of zero."""
    assert stop_costs_s(SPA_FILL, RATE, None) is None
    assert stop_costs_s(None, RATE, LANE) is None
    assert stop_costs_s(SPA_FILL, None, LANE) is None


def test_negative_litres_refuse_rather_than_clamp():
    """Rule 9: the arithmetic went backwards, so the reading is wrong."""
    assert stop_costs_s(-5.0, RATE, LANE) is None


# --- the rejoin ------------------------------------------------------------

def test_a_car_closer_than_the_stop_comes_out_in_front_of_us():
    """The call the engineer was missing entirely. He is 40 s back and the
    stop costs 80, so he emerges ahead."""
    rejoin = rejoin_against(40.0, SPA_STOP)
    assert rejoin.ahead is False
    assert rejoin.margin_s < 0


def test_a_car_further_back_than_the_stop_stays_behind():
    rejoin = rejoin_against(120.0, SPA_STOP)
    assert rejoin.ahead is True
    assert rejoin.margin_s > 0


def test_too_close_to_call_is_an_answer_and_not_a_guess():
    """The pit loss itself is only good to about a second, and his next lap
    moves the gap by more than that."""
    rejoin = rejoin_against(80.0, SPA_STOP)
    assert rejoin.ahead is None and rejoin.too_close
    assert abs(rejoin.margin_s) < REJOIN_MARGIN_S


def test_without_a_gap_or_a_stop_cost_there_is_no_rejoin():
    assert rejoin_against(None, SPA_STOP) is None
    assert rejoin_against(40.0, None) is None


def test_a_negative_gap_is_a_misread_not_a_car_behind_us():
    assert rejoin_against(-4.0, SPA_STOP) is None


# --- closing rate ----------------------------------------------------------
#
# The gap is the cumulative SUM of per-lap pace differences, so it is a random
# walk and a slope fitted to five of them has a standard deviation near
# 0.5 s/lap. At the old 0.15 threshold the gate fired on 68-82% of five-lap
# windows where the two cars had IDENTICAL pace. Every rate below is well clear
# of that, deliberately.

def test_a_shrinking_gap_reads_as_closing():
    trend = GapTrend()
    for lap, gap in enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=6):
        trend.note(lap, gap)
    rate, count = trend.closing_s_per_lap()
    assert count == MIN_LAPS_FOR_TREND
    assert rate == pytest.approx(1.1, abs=0.05)


def test_a_growing_gap_reads_as_the_gap_opening():
    trend = GapTrend()
    for lap, gap in enumerate([5.0, 6.1, 7.2, 8.3, 9.4], start=6):
        trend.note(lap, gap)
    rate, _ = trend.closing_s_per_lap()
    assert rate < 0


def test_the_rate_means_the_gap_is_shrinking_on_both_sides():
    """CLAUDE.md rule 13. One class is built twice - for the car ahead and the
    car behind - and "positive means we are catching him" is true of only one
    of them. The NUMBER means the same thing on both; the sentence differs."""
    values = [10.0, 8.9, 7.8, 6.7, 5.6]
    ahead, behind = GapTrend(side="ahead"), GapTrend(side="behind")
    for lap, gap in enumerate(values, start=6):
        ahead.note(lap, gap)
        behind.note(lap, gap)
    assert ahead.closing_s_per_lap()[0] == behind.closing_s_per_lap()[0]
    assert ahead.side != behind.side


def test_the_sample_count_travels_with_the_rate():
    """CLAUDE.md rule 4: a slope through three points is not a trend."""
    trend = GapTrend()
    trend.note(6, 8.0)
    trend.note(7, 7.0)
    assert trend.closing_s_per_lap() == (None, 2)


def test_a_gap_read_twice_on_one_lap_replaces_rather_than_doubles():
    trend = GapTrend()
    trend.note(6, 8.0)
    trend.note(6, 7.5)
    assert trend.seen == {6: 7.5}


def test_an_unread_gap_is_not_a_gap_of_zero():
    trend = GapTrend()
    trend.note(6, None)
    trend.note(None, 8.0)
    assert trend.seen == {}


# --- the two ways a trend stops being about the same thing -----------------

def test_a_change_of_car_ahead_throws_the_history_away():
    """Measured on this class before the fix: when we passed the car ahead and
    the next was 12 s up the road it reported "losing 1.72 a lap"; when the car
    ahead pitted, "losing 9.79". Both about a car no longer there."""
    trend = GapTrend()
    for lap, gap in enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=6):
        trend.note(lap, gap, subject="rocky")
    trend.note(11, 60.0, subject="punished")
    rate, count = trend.closing_s_per_lap()
    assert count == 1 and rate is None


def test_only_consecutive_laps_are_fitted():
    """Five readings spanning laps 3, 4, 15, 16, 17 came back as a trend "over
    the last 5 laps", with a 10-lap hole regressed straight through."""
    trend = GapTrend()
    for lap, gap in ((3, 8.0), (4, 7.6), (15, 6.0), (16, 5.8), (17, 5.6)):
        trend.note(lap, gap)
    _, count = trend.closing_s_per_lap()
    assert count == 3


def test_a_series_broken_by_our_own_stop_is_not_a_pace_trend():
    """It reported the pit stop itself as ten seconds a lap of lost pace."""
    trend = GapTrend()
    for lap, gap in ((1, 14.0), (2, 13.0), (3, 12.5), (4, 12.0), (6, 68.0)):
        trend.note(lap, gap)
    rate, count = trend.closing_s_per_lap()
    assert count == 1 and rate is None


# --- laps to catch ---------------------------------------------------------

def test_laps_to_catch_needs_a_trend_not_a_slope():
    trend = GapTrend()
    for lap, gap in enumerate([8.0, 7.0, 6.0], start=6):
        trend.note(lap, gap)
    assert trend.laps_to_catch() is None


def test_catching_him_gives_a_number_of_laps():
    trend = GapTrend()
    for lap, gap in enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=6):
        trend.note(lap, gap)
    laps = trend.laps_to_catch()
    assert laps is not None and 4.0 < laps < 6.0


def test_an_answer_past_the_flag_is_not_said():
    """The denominator has a standard deviation near 0.5 s a lap, so just above
    the threshold an eight-second gap returns fifty laps in a twenty-lap
    race - a number with no information in it, spoken under a helmet."""
    trend = GapTrend()
    for lap, gap in enumerate([12.0, 11.1, 10.2, 9.3, 8.4], start=6):
        trend.note(lap, gap)
    assert trend.laps_to_catch() is not None
    assert trend.laps_to_catch(laps_left=3) is None


def test_not_closing_is_never_and_never_is_not_a_number_of_laps():
    trend = GapTrend()
    for lap, gap in enumerate([5.0, 5.1, 5.0, 5.1, 5.0], start=6):
        trend.note(lap, gap)
    assert trend.laps_to_catch() is None


def test_a_rate_inside_the_random_walk_is_not_a_trend():
    """0.15 s/lap fired on three windows in four where nothing was happening."""
    assert TREND_WORTH_SAYING_S >= 0.6


def test_a_new_session_forgets_the_last_race():
    """CLAUDE.md rule 11."""
    trend = GapTrend()
    trend.note(6, 8.0, subject="rocky")
    trend.new_session()
    assert trend.seen == {} and trend.subject is None


# --- reading the box -------------------------------------------------------

def test_reading_rubbish_gives_no_gaps_rather_than_raising():
    assert read_gaps(None, (0, 100, 200, 130)) == (None, None)
    assert read_gaps(np.zeros((10, 10, 3), dtype=int), None) == (None, None)


def test_an_empty_box_is_read_as_no_value():
    """`--:--.---` is what GT7 draws when there is nothing to say, and it must
    not come back as a gap of any size."""
    frame = np.zeros((400, 600, 3), dtype=int)
    assert read_gaps(frame, (40, 200, 250, 232)) == (None, None)
