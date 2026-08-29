"""Wear measured off the replay, and carried into the next race.

**The highest-value number in the app, and it has never survived a race.** GT7
broadcasts no tyre wear channel; the model was measured at ~21% low against the
replay reader, which is verified to 0.5% against the game's own gauge. That
error sat underneath every stint length raced so far.

The reader has transcribed the gauge since 26 Aug and the numbers went into
`laps.wear_*` and stopped there. These are the tests for the two steps after:
fit a rate from a race, and let the next race run on it when the gauge - which
in VR reads about 6 crossings in 22 - says nothing at all.
"""
from __future__ import annotations

import pytest

from dataclasses import dataclass

from pitcrew.analysis import wear_rates
from pitcrew.analysis.wear_rates import MIN_READINGS, MIN_SPAN, fit, fit_stint
from pitcrew.race.calls import (
    BRIEFED,
    GAUGE,
    WEAR,
    RaceState,
    _wear,
    _wear_laps_left,
    _wear_rate,
)


@dataclass
class FakeLap:
    lap_num: int = 1
    compound: str | None = "RS"
    is_pit_lap: bool = False
    wear_fl: float | None = None
    wear_fr: float | None = None
    wear_rl: float | None = None
    wear_rr: float | None = None


def a_stint(rate: float, n: int = 8, start: int = 1, compound: str = "RS"):
    return [FakeLap(lap_num=start + i, compound=compound,
                    wear_fl=rate * i, wear_fr=rate * i,
                    wear_rl=rate * i * 1.1, wear_rr=rate * i)
            for i in range(n)]


# --- the fit ---------------------------------------------------------------

def test_a_stint_yields_the_rate_it_was_built_from():
    rate, readings, span = fit_stint(a_stint(0.04))
    assert rate == pytest.approx(0.044)          # RL is the worst corner
    assert readings == 8


def test_too_few_readings_is_refused_with_its_reasons_intact():
    """Two points and a quantum of noise is a rate of anything you like."""
    rate, readings, _ = fit_stint(a_stint(0.04, n=MIN_READINGS - 1))
    assert rate is None
    assert readings == MIN_READINGS - 1, \
        "a refusal has to be tellable from an absence"


def test_a_gauge_that_barely_moved_is_refused():
    """One pixel of the bar is 3.3% of tyre life, so a span under two quanta
    is indistinguishable from a bar crossing a pixel boundary."""
    rate, _, span = fit_stint(a_stint(MIN_SPAN / 100.0, n=4))
    assert rate is None
    assert span < MIN_SPAN


def test_a_backwards_gauge_is_refused_and_never_clamped():
    """A tyre that is not wearing is a reading problem, not a finding.
    `max(x, 0.0)` here is CLAUDE.md rule 9 exactly."""
    laps = a_stint(0.04)
    laps.reverse()
    for index, lap in enumerate(laps, 1):
        lap.lap_num = index
    assert fit_stint(laps)[0] is None


def test_an_impossible_rate_is_refused():
    """A full set in under four laps is a misread bar, not a tyre."""
    assert fit_stint(a_stint(0.30))[0] is None


def test_a_lap_where_only_some_bars_read_contributes_nothing():
    """It is not a lap where the other two corners were fine; it is a lap the
    reader could not see, and the max of a subset is not the worst of the set."""
    laps = a_stint(0.04)
    laps[3].wear_rl = None
    rate, readings, _ = fit_stint(laps)
    assert readings == 7
    assert rate is not None


# --- stints, not races ------------------------------------------------------

def test_a_stop_splits_the_fit():
    """A fresh set resets the gauge to zero, so a slope taken across a stop is
    a line through two unrelated segments and comes out SHALLOW - which is the
    direction that overruns the cliff."""
    first = a_stint(0.04, n=6, start=1)
    pit = [FakeLap(lap_num=7, is_pit_lap=True)]
    second = a_stint(0.04, n=6, start=8)
    got = fit(first + pit + second)

    assert set(got) == {"RS"}
    assert got["RS"].stints == 2
    assert got["RS"].per_lap == pytest.approx(0.044, rel=0.02)


def test_two_compounds_are_two_rates():
    got = fit(a_stint(0.04, n=6, start=1, compound="RS")
              + a_stint(0.02, n=6, start=7, compound="RH"))
    assert set(got) == {"RS", "RH"}
    assert got["RS"].per_lap > got["RH"].per_lap


def test_the_sample_count_travels_with_the_rate():
    """A rate from one stint and one from six are not the same claim."""
    record = fit(a_stint(0.04)).get("RS").as_record()
    assert record["samples"] == 1
    assert record["source"] == "hud-gauge, replay"


def test_the_offline_thresholds_match_the_live_ones():
    """Two numbers that must agree and cannot see each other is how they come
    to disagree. Both fit the same gauge and answer the same question."""
    from pitcrew.race.calls import WEAR_MIN_READINGS, WEAR_MIN_SPAN

    assert MIN_READINGS == WEAR_MIN_READINGS
    assert MIN_SPAN == WEAR_MIN_SPAN


# --- the briefed rate, which is the VR case and the normal one --------------

def a_state(**over) -> RaceState:
    fields = dict(lap=8, laps_total=20, laps_since_stop=8,
                  fuel_l=40.0, fuel_per_lap_l=3.0)
    fields.update(over)
    return RaceState(**fields)


def test_the_live_fit_beats_the_briefed_rate():
    """A slope from THESE tyres on THIS fuel load at THIS pace is better
    evidence than one carried in from a race already driven."""
    state = a_state(briefed_wear_per_lap=0.09)
    for lap, worn in ((5, 0.20), (6, 0.24), (7, 0.28), (8, 0.32)):
        state.note_wear(lap, {"fl": worn, "fr": worn, "rl": worn, "rr": worn})

    rate, source = _wear_rate(state)
    assert source == GAUGE
    assert rate == pytest.approx(0.04, abs=0.005)


def test_the_briefed_rate_is_used_when_the_gauge_never_read():
    """**The VR case, and it is the normal one.** GT7 draws the HUD on the
    car's dashboard in 3D, so the gauge reads about 6 crossings in 22 and a
    live fit needs three inside one stint."""
    rate, source = _wear_rate(a_state(briefed_wear_per_lap=0.05))
    assert (rate, source) == (0.05, BRIEFED)


def test_nothing_at_all_is_still_nothing():
    assert _wear_rate(a_state()) == (None, None)


def test_a_briefed_projection_anchors_on_a_fresh_set():
    """A fresh set at zero is a fact rather than a reading - the bar is full
    white the moment new rubber goes on."""
    view = _wear_laps_left(a_state(briefed_wear_per_lap=0.05,
                                   laps_since_stop=10))
    assert view.source == BRIEFED
    assert view.consumed == pytest.approx(0.5)
    assert view.reading is None, "there was no reading, so there is none to quote"


def test_a_briefed_call_never_says_measured():
    """There is no reading at all on this path. The word would be a projection
    wearing a measurement's clothes, which is the most repeated defect here."""
    state = a_state(briefed_wear_per_lap=0.05, laps_since_stop=18,
                    fuel_l=90.0, fuel_per_lap_l=3.0)
    call = _wear(state)

    assert call is not None and call.kind == WEAR
    assert "measured at" not in call.spoken()
    assert "measured rate" in call.spoken()


def test_a_briefed_call_never_makes_the_balance_call():
    """A rate is one number for the worst corner; which corner is going first
    is a fact about four bars, and there are no bars to read here."""
    state = a_state(briefed_wear_per_lap=0.02, laps_since_stop=4)
    call = _wear(state)
    assert call is None or "balance" not in call.spoken().lower()


def test_a_gauge_call_still_says_measured():
    state = a_state(laps_since_stop=8)
    for lap, worn in ((5, 0.70), (6, 0.76), (7, 0.82), (8, 0.88)):
        state.note_wear(lap, {"fl": worn, "fr": worn, "rl": worn, "rr": worn})

    call = _wear(state)
    assert call is not None
    assert "measured" in call.spoken()


# --- against the archive ----------------------------------------------------

def test_the_fit_reproduces_the_monza_figure_on_file():
    """Post-patch Monza RH was measured at 0.0493/lap by hand. The fit finds
    the same number off the same laps, which is what makes it believable."""
    from pitcrew.export.build import event_lap_inputs
    from pitcrew.store.db import Store

    store = Store()
    try:
        got = fit(event_lap_inputs(store, 1, "practice", hydrate=set()))
    finally:
        store.close()
    assert "RH" in got
    assert got["RH"].per_lap == pytest.approx(0.0493, abs=0.001)
