"""Tyre temperature is measured; the window it was judged against never was.

These tests used to protect a rule - "a cold tyre is slower than the compound
is and wears less than it will" - which is true of tyres and was being applied
through thresholds that are not GT7's. They are real-world slick figures at
90-110 degC, and every lap of every compound in 51 laps of Monza ran between
68 degC and 78 degC. So the qualification fired on every compound of every
session and put a confident sentence about nothing into every export.

**The bands themselves have now been deleted rather than flagged**, because
the flag did not stop them being read and the four-zone SHAPE was itself the
fabrication: researched Aug 2026, no optimal tyre-temperature window has ever
been published for GT7 by anyone, and nothing in the evidence base describes a
cold side at all. What survives is one sourced UPPER figure per Racing
compound - the temperature above which wear climbs, from a single 2025 test in
this very telemetry channel - and these tests protect the distinction between
that and a window.
"""
from __future__ import annotations

from pitcrew.analysis.session import LapInput
from pitcrew.analysis.tyre_window import (
    BAND_ABOVE_WEAR_ONSET,
    above_wear_onset,
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


# --------------------------------------------------- the one sourced figure

def test_the_wear_onset_threshold_is_read_per_compound():
    """RS 88, RM 90, RH 93 degC - one test, GT7 1.55, in our own channel."""
    assert above_wear_onset("RS", 89.0) is True
    assert above_wear_onset("RS", 87.0) is False
    assert above_wear_onset("RH", 89.0) is False      # RH's threshold is 93
    assert above_wear_onset("RH", 94.0) is True


def test_an_untested_compound_has_no_threshold_rather_than_a_guessed_one():
    """Only the three Racing compounds were ever tested. Everything else is
    None - which is "nobody has measured this", never "the tyre is fine"."""
    assert above_wear_onset("CS", 85.0) is None
    assert above_wear_onset("SS", 85.0) is None
    assert above_wear_onset("IM", 85.0) is None
    assert above_wear_onset("ZZ", 85.0) is None
    assert above_wear_onset("", 85.0) is None
    assert above_wear_onset(None, 85.0) is None


def test_there_is_no_cold_side_to_read():
    """The deleted table had a `cold_max` per compound. Nothing in the
    evidence base describes a cold side for GT7, so the app must not have one
    to import."""
    from pitcrew.store import tyres
    assert not hasattr(tyres.get_by_code("RS"), "cold_max")
    assert not hasattr(tyres, "temp_preset")


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


def test_no_window_is_emitted_because_none_exists():
    """`windowC` used to carry two of the fabricated thresholds "for the UI's
    colour bands". There is no window to carry - missing is null - and the
    source line says so in words rather than leaving a reader to infer it."""
    laps = [lap_at(n, "RH", 74.0) for n in range(1, 7)]
    window = window_by_compound(laps)["RH"]
    assert window["windowC"] is None
    assert window["windowMeasured"] is False
    assert window["inWindow"] is None
    assert window["band"] is None                     # 74 degC is under RH's 93
    assert "No GT7 window exists" in window["windowSource"]
    assert "wear-onset threshold of 93" in window["windowSource"]


def test_a_compound_running_over_its_wear_threshold_says_so():
    laps = [lap_at(n, "RS", 91.0) for n in range(1, 7)]
    window = window_by_compound(laps)["RS"]
    assert window["band"] == BAND_ABOVE_WEAR_ONSET
    assert window["lapsInWindow"] == 6                # laps past the threshold


def test_an_untested_compound_reports_the_temperature_and_nothing_else():
    laps = [lap_at(n, "CS", 74.0) for n in range(1, 7)]
    window = window_by_compound(laps)["CS"]
    assert window["meanC"] == 74.0
    assert window["band"] is None
    assert window["lapsInWindow"] is None             # not zero - unmeasured
    assert "NO GT7 FIGURE EXISTS for CS" in window["windowSource"]


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
