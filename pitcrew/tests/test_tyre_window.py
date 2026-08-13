"""Tyre temperature is measured; the window it was judged against was not.

These tests used to protect a rule — "a cold tyre is slower than the compound
is and wears less than it will" — which is true of tyres and was being applied
through thresholds that are not GT7's. They are real-world slick figures, at
90-110 °C, and every lap of every compound in 51 laps of Monza ran between
68 °C and 78 °C. So the qualification fired on every compound of every session
and put a confident sentence about nothing into every export.

What they protect now is the silence: the temperature is reported, the band
travels flagged as unmeasured, and **no verdict is drawn from it** until a
window has been measured in GT7. Measuring one is a driving job — the same
corner at several times of day, achieved temperature against lap time.
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

def test_no_verdict_is_drawn_from_an_unmeasured_window():
    """The defect: this returned "RM never got into its window ... its pace
    deficit is overstated and its stint length is flattered" on every export,
    from thresholds nobody measured in this game."""
    laps = [lap_at(n, "RH", 45.0) for n in range(1, 7)]
    window = window_by_compound(laps)["RH"]
    assert qualification("RH", window) is None


def test_the_temperature_is_still_measured_and_reported():
    laps = [lap_at(n, "RH", 74.0) for n in range(1, 7)]
    window = window_by_compound(laps)["RH"]
    assert window["meanC"] == 74.0
    assert window["lapsSampled"] == 6
    assert window["source"] == "tyre-surface-temp"


def test_the_band_travels_flagged_as_not_measured():
    """Kept for the UI's colour, where being roughly right is all it does -
    and marked so nothing downstream reads it as a finding."""
    laps = [lap_at(n, "RH", 74.0) for n in range(1, 7)]
    window = window_by_compound(laps)["RH"]
    assert window["windowMeasured"] is False
    assert window["inWindow"] is None
    assert "NOT MEASURED IN GT7" in window["windowSource"]


def test_an_excluded_lap_does_not_colour_the_temperature():
    """A lap that does not count does not describe the compound either."""
    laps = ([lap_at(n, "RH", 90.0) for n in range(1, 5)]
            + [lap_at(5, "RH", 40.0, excluded=True,
                      exclusion_reason="spun at T4")])
    window = window_by_compound(laps)["RH"]
    assert window["lapsSampled"] == 4
    assert window["meanC"] == 90.0


def test_the_measured_temperature_travels_onto_the_compound_profile():
    """Two gauged stints. The temperature is carried; no verdict is drawn."""
    laps = ([lap_at(n, "RS", 100.0) for n in range(1, 5)]
            + [lap_at(5, "RS", 100.0, is_pit_lap=True, wear_fl=0.5)]
            + [lap_at(n, "RH", 66.0) for n in range(6, 10)]
            + [lap_at(10, "RH", 66.0, is_pit_lap=True, wear_fl=0.25)])
    profiles = compound_profiles(laps, "RS")

    assert profiles["RS"].is_measured
    assert profiles["RH"].is_measured
    assert profiles["RH"].window["meanC"] == 66.0
    # The tyre ran 34 °C cooler than the other compound and that is measured
    # and reported - but no conclusion is drawn from it, because the window
    # that would license one has never been measured in GT7.
    assert profiles["RH"].window_note is None
    assert profiles["RH"].evidence_is_clean


def test_a_crossover_is_not_tainted_by_an_unmeasured_window():
    """It used to be: a compound was declared out of its window on invented
    thresholds, and the verdict of the comparison it won was downgraded for it.

    The comparison stands or falls on the measured pace and wear.
    """
    cold = {"meanC": 66.0, "lapsSampled": 5, "windowMeasured": False,
            "inWindow": None}
    inputs = RaceInputs(
        race_laps=30, lap_time_ms=93_000, fuel_per_lap_l=2.6,
        fuel_capacity_l=100.0, refuel_rate_lps=2.5, pit_loss_s=20.0,
        available_compounds=("RS", "RH"), evidence_compound="RS",
        wear_per_lap=0.055,
        compound_profiles={
            "RS": CompoundProfile("RS", 0.0, 0.055, "measured", 12, 1,
                                  longest_stint_laps=12),
            "RH": CompoundProfile(
                "RH", 0.60, 0.026, "measured", 11, 1, longest_stint_laps=30,
                window=cold, window_note=qualification("RH", cold)),
        })
    best = recommend(inputs)[0]

    assert best.compounds == ("RH",)
    assert best.crossover["outsideTyreWindow"] == []
    assert "window" not in best.crossover["verdict"].lower()
