"""The three gap readouts: where a stop puts you, and how fast you are closing.

**Every gap box in every frame of available footage read `--:--.---`**, so a
live gap has never been through this. The arithmetic below is exercised on
figures; the reading is exercised on the fastest-lap banner, whose value is
known, and on the dash box it must refuse. That division is the honest state of
this module and the docstring says so too.
"""
from __future__ import annotations

import numpy as np

from pitcrew.race.gaps import (
    MIN_LAPS_FOR_TREND,
    REJOIN_MARGIN_S,
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

def test_a_shrinking_gap_reads_as_closing():
    trend = GapTrend()
    for lap, gap in enumerate([8.0, 7.2, 6.5, 5.9, 5.1], start=6):
        trend.note(lap, gap)
    rate, count = trend.closing_s_per_lap()
    assert count == MIN_LAPS_FOR_TREND
    assert 0.6 < rate < 0.8


def test_a_growing_gap_reads_as_losing_ground():
    trend = GapTrend()
    for lap, gap in enumerate([5.0, 5.6, 6.1, 6.9, 7.4], start=6):
        trend.note(lap, gap)
    rate, _ = trend.closing_s_per_lap()
    assert rate < 0


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


def test_laps_to_catch_needs_a_trend_not_a_slope():
    trend = GapTrend()
    for lap, gap in enumerate([8.0, 7.0, 6.0], start=6):
        trend.note(lap, gap)
    assert trend.laps_to_catch() is None


def test_catching_him_gives_a_number_of_laps():
    trend = GapTrend()
    for lap, gap in enumerate([8.0, 7.2, 6.5, 5.9, 5.1], start=6):
        trend.note(lap, gap)
    laps = trend.laps_to_catch()
    assert laps is not None and 6.0 < laps < 8.5


def test_not_closing_is_never_and_never_is_not_a_number_of_laps():
    trend = GapTrend()
    for lap, gap in enumerate([5.0, 5.1, 5.0, 5.1, 5.0], start=6):
        trend.note(lap, gap)
    assert trend.laps_to_catch() is None


def test_a_new_session_forgets_the_last_race():
    """CLAUDE.md rule 11."""
    trend = GapTrend()
    trend.note(6, 8.0)
    trend.new_session()
    assert trend.seen == {}


# --- reading the box -------------------------------------------------------

def test_reading_rubbish_gives_no_gaps_rather_than_raising():
    assert read_gaps(None, (0, 100, 200, 130)) == (None, None)
    assert read_gaps(np.zeros((10, 10, 3), dtype=int), None) == (None, None)


def test_an_empty_box_is_read_as_no_value():
    """`--:--.---` is what GT7 draws when there is nothing to say, and it must
    not come back as a gap of any size."""
    frame = np.zeros((400, 600, 3), dtype=int)
    assert read_gaps(frame, (40, 200, 250, 232)) == (None, None)
