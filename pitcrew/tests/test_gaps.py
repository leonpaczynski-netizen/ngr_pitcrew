"""The three gap readouts: where a stop puts you, and how fast you are closing.

**Every gap box in every frame of available footage read `--:--.---`**, so for
a fortnight a live gap had never been through this: the arithmetic below was
exercised on figures and the reading only on the fastest-lap banner and on the
dash box it must refuse.

**That is no longer the honest state of it.** The 4 Sep race capture draws real
gaps, and `test_both_gaps_read_off_a_real_race_frame` runs a whole frame from
it through the locator, the box and the digit bank to two known values. The
per-glyph work is in `test_smallfont.py`, which carries the hold-out counts.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import pytest

import pitcrew.race.gaps as gaps
from pitcrew.telemetry.board import find
from pitcrew.race.rival_calls import closing_call
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


# Bathurst, session 176, the car ahead: readings per lap of the car that was
# there, and the laps on which ONE reading carried another name.
_BATHURST_AHEAD = {1: 27, 2: 19, 3: 24, 4: 21, 5: 22, 6: 23, 7: 18, 8: 16,
                   9: 20, 10: 19}
_BATHURST_FLICKERS = {2: ["Car #4", "82"], 4: ["Car #4"],
                      5: ["Car #31", "Car #4"], 6: ["Car #31"],
                      7: ["Car #31"], 10: ["Car #4"]}


def test_a_misread_name_no_longer_erases_the_history():
    """**The closing call was unreachable all race at Bathurst.** One stray
    reading on laps 2, 4, 5, 6, 7 and 10 each wiped the history, so five
    consecutive laps never existed. The lap's car is now its majority, and a
    stray reading is outvoted rather than obeyed."""
    trend = GapTrend()
    gap = 30.0
    for lap in sorted(_BATHURST_AHEAD):
        gap -= 1.2                                   # closing 1.2 s a lap
        n = _BATHURST_AHEAD[lap]
        flickers = list(_BATHURST_FLICKERS.get(lap, []))
        for i in range(n):
            trend.note(lap, gap + 0.01 * (i % 3), subject="78")
            if flickers and i == n // 2:
                trend.note(lap, 55.0, subject=flickers.pop())
        for stray in flickers:
            trend.note(lap, 55.0, subject=stray)
    assert trend.subject == "78"
    rate, count = trend.closing_s_per_lap()
    assert count == MIN_LAPS_FOR_TREND
    assert rate == pytest.approx(1.2, abs=0.05)
    assert closing_call(trend, lap=10, who="Rocky") is not None


def test_a_lone_new_name_at_the_crossing_moves_the_subject_until_outvoted():
    """One reading of a new car is what an overtake looks like at first, so it
    is obeyed - but when the lap's next readings are the old car again, the
    old car's laps come back instead of being gone."""
    trend = GapTrend()
    for lap, gap in enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=6):
        for _ in range(5):
            trend.note(lap, gap, subject="rocky")
    trend.note(11, 60.0, subject="punished")
    assert trend.subject == "punished"
    trend.note(11, 4.5, subject="rocky")          # a tie: the incumbent holds
    assert trend.subject == "punished"
    trend.note(11, 4.5, subject="rocky")
    assert trend.subject == "rocky"
    rate, count = trend.closing_s_per_lap()
    assert count == MIN_LAPS_FOR_TREND and rate == pytest.approx(1.1)


def test_a_genuine_overtake_still_starts_a_new_history():
    trend = GapTrend()
    for lap, gap in enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=6):
        for _ in range(5):
            trend.note(lap, gap, subject="rocky")
    for lap in (11, 12):
        for _ in range(5):
            trend.note(lap, 12.0, subject="punished")
    assert trend.subject == "punished"
    assert sorted(trend.seen) == [11, 12]


def test_a_lap_about_another_car_is_not_this_cars_lap():
    """A stray reading of the old car inside a lap that was about the new
    one does not stitch the two histories together."""
    trend = GapTrend()
    for lap in (1, 2, 3):
        for _ in range(4):
            trend.note(lap, 5.0, subject="rocky")
    for _ in range(4):
        trend.note(4, 9.0, subject="punished")
    trend.note(4, 5.0, subject="rocky")
    for _ in range(4):
        trend.note(5, 9.5, subject="punished")
    assert trend.subject == "punished"
    assert sorted(trend.seen) == [4, 5]
    assert trend.seen[4] == 9.0


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


# --- one bad lap does not become a rate -------------------------------------
#
# Session 135, 6 Sep 2026. The engineer told the driver at lap 5 "You are
# losing 1.6 seconds a lap to the car ahead"; he was closing, and passed that
# car two laps later. His own laps were 95.325, 97.698, 90.228, 88.966, 87.459
# - lap 2 was a crash, about ten seconds gone in one lap - and a least-squares
# fit over five laps described the crash rather than the pace.
#
# **The gaps themselves were never recorded.** `GapSample` lives in memory for
# the race and nothing writes it, so the real series cannot be replayed and
# these tests do not pretend to. Swept over the one free parameter - the
# rival's pace - NO constant rival pace reproduces both the call that was
# spoken and the overtake that followed, so the rival's pace moved too. What
# the tests below pin is the property that matters and does not depend on it:
# one bad lap must not set the rate.

OUR_LAPS_135 = [95.325, 97.698, 90.228, 88.966, 87.459]


def _gaps_against(rival_s: float, ours=OUR_LAPS_135) -> list[tuple[int, float]]:
    """The gap series our laps produce against a rival holding `rival_s`."""
    gap, out = 0.0, []
    for lap, lap_time in enumerate(ours, start=1):
        gap += lap_time - rival_s
        out.append((lap, gap))
    return out


def _trend(series) -> GapTrend:
    trend = GapTrend()
    for lap, gap in series:
        trend.note(lap, gap)
    return trend


def _ols(series) -> float:
    """The estimator as it stood when the wrong call was made."""
    laps = [lap for lap, _ in series]
    mx = sum(laps) / len(laps)
    my = sum(g for _, g in series) / len(series)
    sxx = sum((k - mx) ** 2 for k in laps)
    return -sum((k - mx) * (g - my) for k, g in series) / sxx


def test_a_crash_ANYWHERE_in_the_window_no_longer_sets_the_rate():
    """The case a critic found the Theil-Sen version still failing.

    A crash is a STEP, not an outlier - the ten seconds stay lost - so every
    pairwise slope spanning it is contaminated, which at five laps is up to six
    of the ten pairs. Theil-Sen only survived session 135 because that crash
    sat at the very START of the window, which is the BEST place for it. Moved
    into the middle it returned "losing 1.92 a lap" while the driver was
    closing at 1.0.
    """
    for name, gaps in (
            ("at the start", [0.0, 10.0, 9.0, 8.0, 7.0]),
            ("second lap", [10.0, 19.0, 18.0, 17.0, 16.0]),
            ("MID-window", [10.0, 9.0, 18.0, 17.0, 16.0]),
            ("late", [10.0, 9.0, 8.0, 7.0, 16.0])):
        trend = _trend(list(enumerate(gaps, start=1)))
        rate, count = trend.closing_s_per_lap()
        assert count == MIN_LAPS_FOR_TREND
        assert rate == pytest.approx(1.0, abs=0.01), (
            f"a crash {name} still set the rate: {rate:+.2f}")


def test_it_never_says_losing_where_he_actually_caught_and_passed():
    """The previous fix passed its test by 0.087 s/lap - it was passing on
    `TREND_WORTH_SAYING_S`, not on the estimator, and a critic showed one tenth
    of rival pace either side brought the same wrong sentence back (at 88.3 the
    Theil-Sen version read "losing 1.61").

    The honest assertion is not "always silent" - against a slow enough rival
    "losing" is the CORRECT call. It is that in the regime consistent with what
    actually happened, where he closes the gap out by lap 7, the engineer must
    never tell him he is losing ground.
    """
    ours7 = OUR_LAPS_135 + [87.479, 87.430]
    checked = 0
    for tenth in range(0, 60):
        rival = 88.0 + tenth / 10
        if _gaps_against(rival, ours7)[-1][1] > 0:
            continue                    # he does not pass: not this regime
        checked += 1
        call = closing_call(_trend(_gaps_against(rival)), lap=5)
        assert call is None or "losing" not in call.call, (
            f"rival {rival:.1f}: {call.call}")
    assert checked >= 10, "the sweep did not cover the regime"


def test_a_step_is_not_an_outlier_and_they_need_different_estimators():
    """`analysis.wear.trend_slope` (Theil-Sen) is right for its OWN question -
    one lap off the pace that returns to trend - and wrong for this one. Pinned
    so the next person does not swap them back."""
    from pitcrew.analysis.wear import trend_slope

    spike = [10.0, 9.0, 16.0, 7.0, 6.0]      # returns to trend
    step = [10.0, 9.0, 18.0, 17.0, 16.0]     # the time stays lost

    # On a spike the two agree - that is why Theil-Sen looked sufficient.
    ts_spike = -trend_slope(list(enumerate(spike))) 
    assert ts_spike == pytest.approx(1.0, abs=0.01)
    assert _trend(list(enumerate(spike, start=1))).closing_s_per_lap()[0] ==         pytest.approx(1.0, abs=0.01)

    # On a step they do not, and Theil-Sen gets the SIGN wrong.
    ts_step = -trend_slope(list(enumerate(step)))
    assert ts_step < 0, "Theil-Sen should call this losing (it is wrong)"
    assert _trend(list(enumerate(step, start=1))).closing_s_per_lap()[0] > 0.9


def test_a_clean_series_reads_the_same_as_it_always_did():
    """The estimator changed twice; the answer on a series with nothing wrong
    in it must not."""
    trend = _trend(list(enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=1)))
    rate, count = trend.closing_s_per_lap()
    assert count == MIN_LAPS_FOR_TREND
    assert rate == pytest.approx(1.1, abs=0.01)


def test_a_steady_loss_is_still_reported_as_a_loss():
    """Trimming the largest difference must not silence a real, steady loss -
    on clean data every difference is alike and the trim changes nothing."""
    trend = _trend(list(enumerate([5.0, 6.5, 8.0, 9.5, 11.0], start=1)))
    rate, _ = trend.closing_s_per_lap()
    assert rate == pytest.approx(-1.5, abs=0.01)


def test_the_trim_costs_a_little_on_an_accelerating_close():
    """Stated rather than hidden: dropping the largest difference under-reports
    a genuinely accelerating trend. That is the same direction
    `TREND_WORTH_SAYING_S` already chose - miss a real trend rather than
    invent one."""
    trend = _trend(list(enumerate([10.0, 9.5, 8.5, 7.0, 5.0], start=1)))
    rate, _ = trend.closing_s_per_lap()
    assert rate == pytest.approx(1.0, abs=0.01), "under-reports 1.25 as 1.00"
    assert rate > 0, "but it must not lose the sign"


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


def a_real_board():
    from PIL import Image
    name = Path(__file__).parent / "fixtures" / "daytona-race-board-p2.png"
    with Image.open(name) as image:
        return np.asarray(image.convert("RGB"))


def test_both_gaps_read_off_a_real_race_frame():
    """**The measurement this module was written for and never had.**

    `daytona-race-board-p2.png` is a whole board cut from the 4 Sep race, and
    the two readouts either side of his own row carry `+ 1.062` and `- 0.761`.
    Everything above this line is exercised on figures; this is the one test
    that runs a frame, the locator, the box and the digit bank end to end, and
    it returned `(None, None)` on every frame ever tried until 5 Sep 2026.
    """
    frame = a_real_board()
    assert read_gaps(frame, find(frame)) == (pytest.approx(1.062),
                                             pytest.approx(0.761))


def test_a_sign_that_disagrees_with_the_side_is_refused(monkeypatch):
    """GT7 draws `+` on the row above his own and `-` on the row below, and it
    agreed with the side on all 165 boxes measured that carried one. A box
    whose sign disagrees is not the box this function thinks it is - a
    mis-anchored row, or a board found in the scenery - and a value taken from
    it would be attached with confidence to the wrong car.

    So: hand the `behind` box back as the `ahead` one. Its digits read
    perfectly well. Its sign says it belongs to the other side.
    """
    frame = a_real_board()
    found = find(frame)
    monkeypatch.setattr(gaps, "gap_lines",
                        lambda frame, row: (found.behind, found.behind))
    ahead, behind = read_gaps(frame, found.row)
    assert ahead is None, "a `-` in the ahead box is not the car ahead"
    assert behind == pytest.approx(0.761)
