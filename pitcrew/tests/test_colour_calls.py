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
