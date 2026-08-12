"""The tyre window, and what it does to a compound comparison.

`store/tyres.py` has carried a per-compound temperature window since the
rebuild and nothing read it. Wiring it in does not change any measured number
— it says how far each measured number can be trusted, which is a separate
claim and has to read as one.

The rule these tests protect: **a cold tyre is slower than the compound is and
wears less than it will.** Measure a Racing Hard below its window and it looks
like a bad tyre that lasts forever. Both halves of that are the temperature,
not the compound, and a race plan built on it fails in the direction that
costs most.
"""
from __future__ import annotations

from pitcrew.analysis.session import LapInput
from pitcrew.analysis.tyre_window import (
    BAND_COLD,
    BAND_HOT,
    BAND_OPTIMAL,
    BAND_OVERHEATING,
    band_for,
    qualification,
    window_by_compound,
)
from pitcrew.strategy.evidence import compound_profiles
from pitcrew.strategy.model import CompoundProfile, RaceInputs, recommend


def frames(temp_c: float, count: int = 20) -> list[dict]:
    return [{f"temp_{corner}": temp_c for corner in ("fl", "fr", "rl", "rr")}
            for _ in range(count)]


def lap_at(lap_num: int, compound: str, temp_c: float, **overrides) -> LapInput:
    # The tank descends across the run; fuel is what tells one run from the
    # next, and a fixture that refills every lap reads as one stop per lap.
    fields = dict(lap_num=lap_num, lap_time_ms=94_000,
                  fuel_start=round(100.0 - 2.6 * (lap_num - 1), 2),
                  fuel_end=round(100.0 - 2.6 * lap_num, 2),
                  compound=compound, frames=frames(temp_c))
    fields.update(overrides)
    return LapInput(**fields)


# ------------------------------------------------------------------ the bands

def test_a_band_is_read_against_the_compounds_own_window():
    """Racing Hard's optimal starts where Comfort Soft is already cooked.

    85 °C is the middle of RH's range and past the top of CS's; 92 °C is well
    beyond anything a Comfort tyre survives.
    """
    assert band_for("RH", 85.0) == BAND_OPTIMAL
    assert band_for("CS", 85.0) == BAND_HOT
    assert band_for("CS", 92.0) == BAND_OVERHEATING


def test_a_hard_tyre_below_its_window_is_cold_not_merely_cool():
    # RH warms through to 75 C; below 60 it is cold.
    assert band_for("RH", 55.0) == BAND_COLD


def test_an_unknown_compound_gets_no_band_rather_than_a_wrong_one():
    """A band off the wrong thresholds is worse than none at all."""
    assert band_for("ZZ", 85.0) is None
    assert band_for("", 85.0) is None


# ------------------------------------------------------- per-compound windows

def test_a_compound_in_its_window_needs_no_qualification():
    laps = [lap_at(n, "RH", 88.0) for n in range(1, 6)]
    window = window_by_compound(laps)["RH"]
    assert window["band"] == BAND_OPTIMAL
    assert window["inWindow"] is True
    assert window["lapsInWindow"] == 5
    assert qualification("RH", window) is None


def test_a_cold_compound_says_its_pace_and_stint_are_both_flattered():
    laps = [lap_at(n, "RH", 66.0) for n in range(1, 6)]
    window = window_by_compound(laps)["RH"]
    note = qualification("RH", window)

    assert window["inWindow"] is False
    assert "never got into its window" in note
    # Both halves matter: too slow *and* apparently too durable.
    assert "slower than the compound is" in note
    assert "wears less than it will" in note


def test_an_overheating_compound_says_its_stint_is_pessimistic():
    laps = [lap_at(n, "RS", 125.0) for n in range(1, 6)]
    note = qualification("RS", window_by_compound(laps)["RS"])
    assert "ran hot" in note
    assert "pessimistic" in note


def test_a_compound_only_sometimes_in_window_says_it_is_a_mixture():
    """Averages to 82 °C, inside the window, but only half the laps were.

    A tyre in window for half the run spent half the run somewhere else, and
    the mean hides exactly that.
    """
    laps = ([lap_at(n, "RH", 95.0) for n in range(1, 4)]
            + [lap_at(n, "RH", 70.0) for n in range(4, 7)])
    window = window_by_compound(laps)["RH"]
    assert window["band"] == BAND_OPTIMAL       # the mean says it was fine
    assert window["inWindow"] is False          # the laps say otherwise
    assert "mixture of conditions" in qualification("RH", window)


def test_a_compound_with_no_captured_temperature_gets_no_entry():
    """Absent and fine must not look alike."""
    laps = [LapInput(lap_num=n, lap_time_ms=94_000, fuel_start=92.0,
                     fuel_end=89.4, compound="RH") for n in range(1, 6)]
    assert window_by_compound(laps) == {}
    assert qualification("RH", None) is None


def test_the_hottest_corner_is_named():
    """Which corner is cooking is a setup finding, like the wear one."""
    hot = [{"temp_fl": 118.0, "temp_fr": 92.0,
            "temp_rl": 90.0, "temp_rr": 91.0} for _ in range(20)]
    laps = [LapInput(lap_num=n, lap_time_ms=94_000, fuel_start=92.0,
                     fuel_end=89.4, compound="RH", frames=hot)
            for n in range(1, 4)]
    assert window_by_compound(laps)["RH"]["hottestCorner"] == "fl"


def test_an_excluded_lap_does_not_colour_the_window():
    laps = ([lap_at(n, "RH", 88.0) for n in range(1, 5)]
            + [lap_at(5, "RH", 40.0, excluded=True)])
    window = window_by_compound(laps)["RH"]
    assert window["lapsSampled"] == 4
    assert window["inWindow"] is True


# ------------------------------------------------- reaching the strategy call

def test_the_qualification_travels_onto_the_compound_profile():
    """Two gauged stints: the soft in its window, the hard never in its."""
    laps = ([lap_at(n, "RS", 100.0) for n in range(1, 5)]
            + [lap_at(5, "RS", 100.0, is_pit_lap=True, wear_fl=0.5)]
            + [lap_at(n, "RH", 66.0) for n in range(6, 10)]
            + [lap_at(10, "RH", 66.0, is_pit_lap=True, wear_fl=0.25)])
    profiles = compound_profiles(laps, "RS")

    assert profiles["RS"].is_measured
    assert profiles["RS"].window_note is None
    assert profiles["RS"].evidence_is_clean

    # Measured, and the number is real - it just describes a cold tyre, so it
    # is not clean evidence about the compound.
    assert profiles["RH"].is_measured
    assert profiles["RH"].wear_per_lap == 0.05
    assert "never got into its window" in profiles["RH"].window_note
    assert profiles["RH"].evidence_is_clean is False


def test_a_cold_compound_taints_the_verdict_it_wins_with():
    """The arithmetic is untouched; the sentence says how far to trust it."""
    cold = {"band": BAND_COLD, "inWindow": False, "meanC": 66.0,
            "windowC": [75, 100], "lapsSampled": 5, "lapsInWindow": 0}
    inputs = RaceInputs(
        race_laps=30, lap_time_ms=93_000, fuel_per_lap_l=2.6,
        fuel_capacity_l=100.0, refuel_rate_lps=2.5, pit_loss_s=20.0,
        available_compounds=("RS", "RH"), evidence_compound="RS",
        wear_per_lap=0.055,
        compound_profiles={
            "RS": CompoundProfile("RS", 0.0, 0.055, "measured", 12, 1),
            "RH": CompoundProfile(
                "RH", 0.60, 0.026, "measured", 11, 1, window=cold,
                window_note=qualification("RH", cold)),
        })
    best = recommend(inputs)[0]

    assert best.compounds == ("RH",)          # it still wins on the numbers
    assert best.crossover["outsideTyreWindow"]
    assert "never got into its window" in best.crossover["verdict"]
    assert "RH beats" in best.crossover["verdict"]


def test_a_clean_comparison_carries_no_window_warning():
    from .test_compound_crossover import a_race
    best = recommend(a_race(rh_delta=0.60))[0]
    assert best.crossover["outsideTyreWindow"] == []
    assert "window" not in best.crossover["verdict"]


# ------------------------------------------------- what gets decoded, and why

def test_only_the_sampled_laps_have_their_frames_decoded():
    """One lap's blob is ~1.6 MiB. Decoding a whole practice event to read a
    mean temperature would freeze the Strategy screen for seconds, and freeze
    it again when the race is armed."""
    from pitcrew.strategy.evidence import WINDOW_SAMPLE_LAPS, _laps_to_hydrate

    rows = [{"id": n, "compound": "RS", "excluded": 0,
             "is_out_lap": 0, "is_pit_lap": 0} for n in range(1, 31)]
    wanted = _laps_to_hydrate(rows)

    assert len(wanted) == WINDOW_SAMPLE_LAPS
    # The most recent ones: latest setup, track at its most rubbered in.
    assert wanted == {25, 26, 27, 28, 29, 30}


def test_each_compound_gets_its_own_sample():
    """A sample of the soft's laps says nothing about the hard's window."""
    from pitcrew.strategy.evidence import _laps_to_hydrate

    rows = ([{"id": n, "compound": "RS", "excluded": 0,
              "is_out_lap": 0, "is_pit_lap": 0} for n in range(1, 21)]
            + [{"id": n, "compound": "RH", "excluded": 0,
                "is_out_lap": 0, "is_pit_lap": 0} for n in range(21, 41)])
    wanted = _laps_to_hydrate(rows)
    assert wanted == {15, 16, 17, 18, 19, 20, 35, 36, 37, 38, 39, 40}


def test_uncounted_laps_are_never_sampled():
    """An out-lap's temperatures describe a tyre that has not warmed up."""
    from pitcrew.strategy.evidence import _laps_to_hydrate

    rows = [{"id": 1, "compound": "RS", "excluded": 0,
             "is_out_lap": 1, "is_pit_lap": 0},
            {"id": 2, "compound": "RS", "excluded": 1,
             "is_out_lap": 0, "is_pit_lap": 0},
            {"id": 3, "compound": "RS", "excluded": 0,
             "is_out_lap": 0, "is_pit_lap": 0}]
    assert _laps_to_hydrate(rows) == {3}


def test_the_sample_size_travels_with_the_conclusion():
    """CLAUDE.md 4: every aggregate carries its sample count. A capped sample
    that did not say so would read as the whole event."""
    laps = [lap_at(n, "RH", 88.0) for n in range(1, 4)]
    assert window_by_compound(laps)["RH"]["lapsSampled"] == 3
