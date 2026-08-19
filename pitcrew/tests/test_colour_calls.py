"""Colour calls: engagement on the quiet laps, and the budget that keeps it
from becoming the nine-box-calls defect wearing a different hat."""
from pitcrew.race.colour import (
    BEST_LAP,
    CHATTY,
    CONSISTENCY,
    GAUGE_PROMPT,
    GAP_LAPS,
    MILESTONE,
    NORMAL,
    QUIET,
    RUN_IN,
    STINT_COUNTDOWN,
    ColourCalls,
)


def run(calls, laps, **kw):
    """Drive a stretch of laps, returning what was actually said."""
    said = []
    for lap, ms in laps:
        out = calls.consider(lap=lap, lap_time_ms=ms, **kw)
        if out is not None:
            said.append((lap, out))
    return said


def steady(n, ms=110_000, start=1):
    return [(i, ms) for i in range(start, start + n)]


def test_quiet_is_off_and_not_merely_less_often():
    calls = ColourCalls(level=QUIET)
    said = run(calls, steady(30), laps_remaining=10, stint_ends_on_lap=15,
               sigma_s=0.7, wear_reading_age=20)
    assert said == []


def test_at_most_one_call_per_crossing():
    """Everything could fire on the same lap. Only one may."""
    calls = ColourCalls(level=CHATTY)
    out = calls.consider(lap=10, lap_time_ms=100_000, laps_remaining=10,
                         laps_total=20, stint_ends_on_lap=11, sigma_s=0.7,
                         wear_reading_age=20)
    assert out is not None


def test_silence_is_kept_between_calls():
    calls = ColourCalls(level=NORMAL)
    said = run(calls, steady(30), laps_remaining=None, stint_ends_on_lap=None,
               sigma_s=0.7, wear_reading_age=30)
    laps = [lap for lap, _ in said]
    gaps = [b - a for a, b in zip(laps, laps[1:])]
    assert all(g >= GAP_LAPS[NORMAL] for g in gaps), laps


def test_chatty_talks_more_but_still_keeps_a_gap():
    quiet_run = run(ColourCalls(level=NORMAL), steady(30),
                    laps_remaining=None, sigma_s=0.7, wear_reading_age=30)
    loud_run = run(ColourCalls(level=CHATTY), steady(30),
                   laps_remaining=None, sigma_s=0.7, wear_reading_age=30)
    assert len(loud_run) >= len(quiet_run)
    laps = [lap for lap, _ in loud_run]
    assert all(b - a >= GAP_LAPS[CHATTY] for a, b in zip(laps, laps[1:]))


def test_a_kind_is_said_once_per_stint():
    calls = ColourCalls(level=CHATTY)
    said = run(calls, steady(40), laps_remaining=None, sigma_s=0.7,
               wear_reading_age=40)
    kinds = [c.kind for _, c in said if c.kind != BEST_LAP]
    assert len(kinds) == len(set(kinds)), kinds


def test_a_stop_makes_every_kind_news_again():
    calls = ColourCalls(level=CHATTY)
    run(calls, steady(20), laps_remaining=None, sigma_s=0.7,
        wear_reading_age=20)
    calls.new_stint()
    said = run(calls, steady(20, start=21), laps_remaining=None, sigma_s=0.7,
               wear_reading_age=20)
    assert any(c.kind == GAUGE_PROMPT for _, c in said)


def test_a_personal_best_is_called_and_may_repeat():
    """The one kind that repeats within a stint: a new best is a new fact
    every time, and it is the most motivating thing an engineer says."""
    calls = ColourCalls(level=CHATTY)
    laps = [(1, 112_000), (2, 111_000), (3, 110_500)]
    laps += [(4, 110_000)] + [(i, 111_000) for i in range(5, 8)]
    laps += [(8, 109_000)] + [(i, 111_000) for i in range(9, 12)]
    laps += [(12, 108_000)]
    said = [c for _, c in run(calls, laps, laps_remaining=None)]
    bests = [c for c in said if c.kind == BEST_LAP]
    assert len(bests) >= 2, [c.kind for c in said]
    assert "best lap of the race" in bests[0].call


def test_no_consistency_call_without_a_measured_sigma():
    """His scatter is measured from the race in progress and never inherited.
    Without one there is no band, and an invented band is a pace verdict -
    which this app is forbidden from making."""
    calls = ColourCalls(level=CHATTY)
    said = run(calls, steady(20), laps_remaining=None, sigma_s=None,
               wear_reading_age=None)
    assert not any(c.kind == CONSISTENCY for _, c in said)


def test_consistency_needs_the_laps_to_actually_be_inside_his_own_spread():
    tight = ColourCalls(level=CHATTY)
    laps = [(i, 110_000 + (i % 2) * 200) for i in range(1, 9)]
    assert any(c.kind == CONSISTENCY
               for _, c in run(tight, laps, laps_remaining=None, sigma_s=0.7))

    loose = ColourCalls(level=CHATTY)
    scattered = [(i, 110_000 + (i % 2) * 4_000) for i in range(1, 9)]
    assert not any(c.kind == CONSISTENCY
                   for _, c in run(loose, scattered, laps_remaining=None,
                                   sigma_s=0.7))


def test_the_stop_countdown_only_runs_near_the_stop():
    calls = ColourCalls(level=CHATTY)
    said = run(calls, steady(6), laps_remaining=None, stint_ends_on_lap=20)
    assert not any(c.kind == STINT_COUNTDOWN for _, c in said)

    near = ColourCalls(level=CHATTY)
    said = run(near, steady(6, start=14), laps_remaining=None,
               stint_ends_on_lap=18)
    assert any(c.kind == STINT_COUNTDOWN for _, c in said)


def test_milestones_are_laps_remaining_not_laps_done():
    calls = ColourCalls(level=CHATTY)
    out = calls.consider(lap=17, lap_time_ms=110_000, laps_remaining=10)
    assert out is not None and out.kind == MILESTONE
    assert out.call == "10 to go."


def test_the_gauge_prompt_fires_when_the_set_has_never_been_read():
    """GT7 broadcasts no wear channel, so the gauge is the only ground truth
    that exists - and on the Monza race he read it zero times."""
    calls = ColourCalls(level=NORMAL)
    said = run(calls, steady(12), laps_remaining=None, wear_reading_age=12)
    prompts = [c for _, c in said if c.kind == GAUGE_PROMPT]
    assert prompts
    assert "gauge" in prompts[0].call.lower()


def test_a_freshly_read_gauge_is_not_asked_for_again():
    calls = ColourCalls(level=CHATTY)
    said = run(calls, steady(12), laps_remaining=None, wear_reading_age=1)
    assert not any(c.kind == GAUGE_PROMPT for _, c in said)


def test_nothing_is_said_about_a_car_the_feed_cannot_see():
    """No proximity channel exists in any packet format. A gap the app
    invented is a lie told at 200 km/h."""
    calls = ColourCalls(level=CHATTY)
    said = run(calls, steady(40), laps_remaining=10, laps_total=40,
               stint_ends_on_lap=20, sigma_s=0.7, wear_reading_age=40)
    words = " ".join(c.spoken().lower() for _, c in said)
    for banned in ("ahead", "behind", "gap", "catching", "pulling away"):
        assert banned not in words, words


# ------------------------------------------------------------- the run-in
#
# *"I want each lap updates in the last 5 laps to keep me pushing to the end
# and aware of what is going on."* - the driver, 19 Aug 2026.


def run_in_laps(calls, count=6, ms=110_000, **kw):
    """The closing laps, counting down to the flag."""
    said = []
    for index in range(count):
        remaining = count - index
        out = calls.consider(lap=20 + index, lap_time_ms=ms,
                             laps_remaining=remaining, **kw)
        said.append((remaining, out))
    return said


def test_the_run_in_speaks_every_lap():
    calls = ColourCalls(level=NORMAL)
    said = run_in_laps(calls, count=5, sigma_s=0.7, wear_reading_age=1)
    assert all(out is not None for _, out in said)
    assert [out.kind for _, out in said] == [RUN_IN] * 5


def test_the_run_in_counts_down_and_names_the_last_lap():
    calls = ColourCalls(level=NORMAL)
    said = run_in_laps(calls, count=5, sigma_s=0.7, wear_reading_age=1)
    spoken = [out.call for _, out in said]
    assert spoken[0].startswith("5 to go")
    assert spoken[-1] == "Last lap."


def test_the_run_in_does_not_start_early():
    """Six laps out is not the run-in, and the gap still governs there."""
    calls = ColourCalls(level=NORMAL)
    out = calls.consider(lap=10, lap_time_ms=110_000, laps_remaining=6,
                         sigma_s=0.7, wear_reading_age=1)
    assert out is None or out.kind != RUN_IN


def test_quiet_still_means_off_in_the_run_in():
    """He can turn the engineer down, and that must hold everywhere."""
    calls = ColourCalls(level=QUIET)
    said = run_in_laps(calls, count=5, sigma_s=0.7, wear_reading_age=1)
    assert all(out is None for _, out in said)


def test_the_run_in_hedges_a_lap_count_it_cannot_resolve():
    """A timed race's distance is an output of the plan, and the count can sit
    inside this car's own lap-time noise. Quoting it flat is inventing
    precision - see the 2.04 s spread measured at Yas Marina."""
    firm = ColourCalls(level=NORMAL)
    loose = ColourCalls(level=NORMAL)
    said_firm = run_in_laps(firm, count=3, laps_firm=True, sigma_s=0.7,
                            wear_reading_age=1)
    said_loose = run_in_laps(loose, count=3, laps_firm=False, sigma_s=0.7,
                             wear_reading_age=1)
    assert said_firm[0][1].call == "3 to go."
    assert said_loose[0][1].call == "About 3 to go."


def test_the_run_in_carries_position_and_pace_against_his_own_best():
    calls = ColourCalls(level=NORMAL)
    # A quick lap sets the best, then the run-in reports against it.
    calls.consider(lap=18, lap_time_ms=108_000, laps_remaining=8)
    said = run_in_laps(calls, count=3, ms=109_500, position=4, sigma_s=0.7,
                       wear_reading_age=1)
    reason = said[0][1].reason
    assert reason.startswith("P4.")
    assert "1.5 off your best" in reason


def test_the_run_in_says_nothing_it_did_not_measure():
    """No gap to the car ahead - there is no proximity channel in any packet
    format. With no position and no best, it still counts the laps down."""
    calls = ColourCalls(level=NORMAL)
    out = calls.consider(lap=20, lap_time_ms=None, laps_remaining=3)
    assert out is not None and out.call == "3 to go."
    assert out.reason == ""
