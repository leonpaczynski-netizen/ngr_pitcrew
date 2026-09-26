"""The gauge comparison was a one-way ratchet, and it shut itself.

Fuji, 24 Aug 2026, session 88: the reader made 553 attempts after the green
flag and accepted **none**. 432 of those were refused by one rule, naming
figures from 19% to 76%, and the app told the driver "I have the tyre gauge
this race" in the brief and "No tyre gauge" three and a half minutes later.

The mechanism is an asymmetry between the two halves of `_coherent`:

* it refuses two shapes - corners moving both ways, and every corner dropping
  onto a set too worn to be new - and **silently accepts everything else**,
  including a reading that rose forty points in ten seconds;
* a refusal deliberately does not become the baseline, and an accept silently
  does.

So the baseline can only ever climb, and once it is above the gauge every
honest reading is refused forever. There is no path back. The sampler was
rebuilt with an empty series at 20:03:47 and was already refusing a 32%
reading by 20:07:28 - which requires an unlogged accept above 37% inside those
four minutes.

Three fixes, and they are independent:

1. a rise cap, so the baseline cannot climb on a misread;
2. a re-seed, so a baseline that refuses everything is itself discarded;
3. a session reset, so a stint that ended is not evidence about the one
   starting.
"""
from __future__ import annotations

import logging

import pytest

from pitcrew.telemetry.hud import (GAUGE_MAX_RISE, REFUSALS_WINDOW_S,
                                   LiveWearSampler, Reading)

from .test_hud_wear import FakeSource


def a_sampler():
    return LiveWearSampler(FakeSource((None, "unused")),
                           lambda lap, wear: None)


def kept(sampler, fl, fr, rl, rr, at=0.0):
    return sampler._keep(at, Reading({"fl": fl, "fr": fr,
                                       "rl": rl, "rr": rr}))


def seeded(at=0.30, t=0.0):
    sampler = a_sampler()
    assert kept(sampler, at, at, at, at, at=t)
    return sampler


# --------------------------------------------------------- 1. the rise cap

def test_a_reading_that_leaps_upward_is_not_the_gauge():
    """The refusal rule only ever looked downward. This is the other half."""
    sampler = seeded(0.30)

    assert not kept(sampler, 0.76, 0.76, 0.76, 0.76)
    assert sampler.series[-1][1]["fl"] == 0.30, (
        "the leap must not become the baseline everything else is judged on")


def test_ordinary_wear_between_samples_is_still_accepted():
    """Samples are seconds apart and a lap is a few percent. The cap has to
    sit far above that or it refuses the thing it exists to read."""
    sampler = seeded(0.30)

    assert kept(sampler, 0.34, 0.33, 0.36, 0.35)
    assert kept(sampler, 0.38, 0.36, 0.41, 0.39)


def test_the_cap_is_the_documented_one():
    sampler = seeded(0.30)
    just_under = 0.30 + GAUGE_MAX_RISE - 0.01

    assert kept(sampler, just_under, just_under, just_under, just_under)


def test_one_corner_leaping_is_enough_to_refuse_the_reading():
    """A reading is of four bars or it is not of the gauge."""
    sampler = seeded(0.30)

    assert not kept(sampler, 0.32, 0.31, 0.80, 0.33)


# ---------------------------------------------------------- 2. the re-seed

def test_a_baseline_that_refuses_everything_is_dropped():
    """432 refusals in a row is evidence about the baseline, not the gauge."""
    sampler = seeded(0.60)

    # Every one of these is an honest reading of a fresher set, and every one
    # is refused against a baseline that should never have been filed.
    # Trigger the window by advancing the timestamp past REFUSALS_WINDOW_S.
    for _ in range(5):
        assert not kept(sampler, 0.30, 0.28, 0.33, 0.31, at=0.0)
    # Final refusal past the window — the bad baseline is dropped.
    assert not kept(sampler, 0.30, 0.28, 0.33, 0.31,
                    at=REFUSALS_WINDOW_S + 1.0)

    assert sampler.series == [], "the bad baseline should have been discarded"
    # And the very next reading gets in, which is the whole point.
    assert kept(sampler, 0.30, 0.28, 0.33, 0.31)


def test_the_reseed_says_so_loudly():
    """The series is thrown away, so any wear slope built on it goes too."""
    sampler = seeded(0.60)
    logger = logging.getLogger("pitcrew.hud")
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logger.addHandler(handler)
    try:
        kept(sampler, 0.30, 0.28, 0.33, 0.31, at=0.0)
        kept(sampler, 0.30, 0.28, 0.33, 0.31, at=REFUSALS_WINDOW_S + 1.0)
    finally:
        logger.removeHandler(handler)

    assert any("so the baseline is what is wrong" in line for line in records)


def test_a_short_run_of_refusals_does_not_reseed():
    """A run under REFUSALS_WINDOW_S is the driver looking away in VR or the
    pit-lane HUD moving the gauge.  Re-seeding there would hand the series to
    the misread `_coherent` exists to reject."""
    sampler = seeded(0.60)

    # Any number of refusals within the window — baseline must survive.
    for _ in range(20):
        assert not kept(sampler, 0.30, 0.28, 0.33, 0.31, at=0.0)

    assert sampler.series, "it gave up on a healthy baseline too early"
    assert sampler.series[-1][1]["fl"] == 0.60


def test_one_good_reading_clears_the_timer():
    """The run has to be consecutive — refusals scattered across a stint are
    ordinary and must never accumulate into a re-seed."""
    sampler = seeded(0.30)

    # Accumulate some refusals, well within the window.
    for _ in range(10):
        assert not kept(sampler, 0.90, 0.90, 0.90, 0.90, at=0.0)
    # One good reading clears the refusal timer.
    assert kept(sampler, 0.32, 0.31, 0.34, 0.33, at=1.0)
    assert sampler._refused_since_s is None, "accept must reset the timer"
    # Refusals now restart; even past the old window they don't trigger the
    # re-seed because the timer was reset.
    for _ in range(10):
        assert not kept(sampler, 0.95, 0.95, 0.95, 0.95, at=2.0)

    assert sampler.series, "a cleared timer must start again from zero"


# ----------------------------------------------------- 3. the session reset

def test_a_new_session_forgets_the_last_one_s_baseline():
    """A race opened judging its fresh set against what practice left."""
    sampler = seeded(0.55)

    sampler.new_session()

    assert sampler.series == []
    assert sampler.latest() is None
    # A fresh set at the start of the race is now readable, where before it
    # was "every corner dropped but the set still reads 55% worst".
    assert kept(sampler, 0.02, 0.01, 0.03, 0.02)


def test_new_session_is_actually_called_by_the_app():
    """It existed, documented why it was needed, and had no caller at all
    outside the tests - which is why the baseline crossed sessions."""
    import inspect

    from pitcrew import controller

    source = inspect.getsource(controller)
    assert source.count("self._new_hud_session()") >= 2, (
        "both practice and race have to reset the gauge reader")


# ------------------------------------------------------ what gets logged

def test_accepts_are_logged_as_well_as_refusals():
    """The baseline climbed on accepts nobody could see. 432 refusals were
    logged and not one line said what they were being judged against."""
    sampler = a_sampler()
    logger = logging.getLogger("pitcrew.hud")
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logger.addHandler(handler)
    # `setLevel`, not `logger.level = ...`: logging caches the enabled-for
    # answer per logger and only setLevel invalidates that cache.
    was = logger.level
    logger.setLevel(logging.INFO)
    try:
        kept(sampler, 0.30, 0.28, 0.33, 0.31)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(was)

    assert any("reading accepted" in line for line in records)
    assert any("33%" in line for line in records), (
        "the number that sets the bar has to appear in the log")
