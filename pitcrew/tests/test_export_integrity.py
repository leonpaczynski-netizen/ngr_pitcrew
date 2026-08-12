"""The ten defects the knowledge base found in the 11 Aug Monza export.

Every test here is a regression test for something that was exported as fact
and was not one. They are kept together rather than spread across the module
they each touch, because what they have in common — a number that reached the
consumer carrying more authority than it had earned — matters more than which
file produced it.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from pitcrew.analysis.gearing import final_drive, gearing_export
from pitcrew.analysis.runs import (
    classify_exclusions,
    fuel_implausible_laps,
    split_runs,
)
from pitcrew.analysis.session import LapInput, counted_laps, session_export
from pitcrew.analysis.wear import trend_slope, wear_export
from pitcrew.export.payload import Meta, build_payload, validate

from .test_corners import frame


def a_lap(lap_num: int, *, fuel_start: float, fuel_end: float,
          **overrides) -> LapInput:
    fields = dict(lap_num=lap_num, lap_time_ms=109_000,
                  fuel_start=fuel_start, fuel_end=fuel_end)
    fields.update(overrides)
    return LapInput(**fields)


def a_run(first: int, count: int, *, compound: str, burn: float = 6.5,
          tank: float = 100.0, final_wear: float | None = None,
          lap_ms: int = 109_000, **overrides) -> list[LapInput]:
    """One tank's worth of laps, the gauge read on the last of them."""
    laps = []
    for step in range(count):
        wear = final_wear if step == count - 1 else None
        laps.append(a_lap(first + step,
                          fuel_start=round(tank - burn * step, 2),
                          fuel_end=round(tank - burn * (step + 1), 2),
                          compound=compound, lap_time_ms=lap_ms,
                          wear_rl=wear, **overrides))
    return laps


def a_meta(**overrides) -> Meta:
    fields = dict(car="Porsche 911 RSR (991) '17", circuit="Monza",
                  date="2026-08-11", session_type="practice", packet="C",
                  game_version="1.70")
    fields.update(overrides)
    return Meta(**fields)


# ------------------------------------------------------- P1 the compound record

def test_a_compound_never_run_cannot_reach_bycompound():
    """The defect: rates for Racing Soft and Racing Medium in a session that
    ran neither, each tagged `driver-gauge` - the highest-trust provenance the
    schema has - and a race compound chosen off them."""
    payload = build_payload(
        a_meta(compound_front="Racing Hard", compound_rear="Racing Hard",
               compounds_run=["Racing Hard"]),
        wear={"channelAvailable": False,
              "byCompound": {"RM": {"compound": "Racing Medium",
                                    "wearPerLap": 0.076, "stints": 1}}})
    problems = validate(payload)
    assert any("never ran" in problem for problem in problems)


def test_bycompound_may_only_name_what_the_session_recorded():
    laps = a_run(1, 6, compound="RH", final_wear=0.4)
    wear = wear_export(laps)
    assert set(wear["byCompound"]) == {"RH"}
    assert wear["byCompound"]["RH"]["compound"] == "Racing Hard"


def test_a_single_compound_meta_and_several_rates_is_refused():
    payload = build_payload(
        a_meta(compound_front="Racing Hard", compound_rear="Racing Hard",
               compounds_run=["Racing Hard", "Racing Medium"]),
        wear={"channelAvailable": False,
              "byCompound": {
                  "RH": {"compound": "Racing Hard", "wearPerLap": 0.05},
                  "RM": {"compound": "Racing Medium", "wearPerLap": 0.07}}})
    assert any("inventing a stint" in problem for problem in validate(payload))


def test_stints_counts_the_runs_and_says_how_many_were_readable():
    """Three runs on the soft, one of them read. That is a thinner claim than
    one run read once, and the pair of counts is what says so."""
    laps = (a_run(1, 4, compound="RS")
            + a_run(5, 2, compound="RS")
            + a_run(7, 4, compound="RS", final_wear=0.69))
    entry = wear_export(laps)["byCompound"]["RS"]
    assert entry["stints"] == 3
    assert entry["stintsMeasured"] == 1
    assert entry["runIds"] == [1, 2, 3]


# ------------------------------------------------- P2 the implausible best lap

def test_a_lap_that_burned_no_fuel_is_not_a_lap():
    """Lap 8 of the Monza session burned 0.16 L against a 6.57 L median, was
    counted, and became the session best 1.9 s clear of the real one."""
    laps = (a_run(1, 5, compound="RH")
            + [a_lap(6, fuel_start=67.5, fuel_end=67.34, compound="RH",
                     lap_time_ms=104_912)]
            + a_run(7, 4, compound="RH", tank=67.34, final_wear=0.4))
    marked = classify_exclusions(laps, 100.0)

    struck = [lap for lap in marked if lap.lap_num == 6][0]
    assert struck.counted is False
    assert struck.exclusion_reason == "fuel-implausible"
    assert struck.exclusion_source == "auto"

    session = session_export(marked, fuel_capacity_l=100.0)
    assert 6 not in [lap.lap_num for lap in counted_laps(marked)]
    assert session["bestLapMs"] == 109_000


def test_an_electric_car_burns_nothing_and_keeps_every_lap():
    """A capacity of 0 is a real value, not a missing one. Applying the test
    to a car that burns nothing would strike the whole session."""
    laps = [a_lap(n, fuel_start=0.0, fuel_end=0.0, compound="RH")
            for n in range(1, 6)]
    assert fuel_implausible_laps(laps, 0.0) == set()
    assert len(counted_laps(classify_exclusions(laps, 0.0))) == 5


# -------------------------------------------------------- P4 the fitted trend

def test_degradation_is_fitted_inside_one_run_and_names_it():
    """Fitted across five tanks, a sawtooth reads as a rising trend: the
    Monza export said +72 ms/lap on a car that was getting faster."""
    laps = (a_run(1, 6, compound="RH", lap_ms=109_000)
            + a_run(7, 8, compound="RH", lap_ms=108_000, final_wear=0.5))
    fitted = wear_export(laps)["byLapTime"]
    assert fitted["fittedRunId"] == 2
    assert fitted["fittedOverLaps"] == [7, 14]
    assert fitted["samples"] == 8
    assert fitted["fuelNetted"] is False
    assert fitted["fuelDeltaL"] > 0


def test_a_car_getting_faster_is_reported_as_getting_faster():
    laps = [a_lap(n, fuel_start=100.0 - 6.5 * (n - 1),
                  fuel_end=100.0 - 6.5 * n, compound="RH",
                  lap_time_ms=110_000 - n * 40)
            for n in range(1, 12)]
    assert wear_export(laps)["byLapTime"]["degradationMsPerLap"] < 0


def test_no_run_long_enough_gives_null_rather_than_a_number():
    laps = a_run(1, 3, compound="RH", final_wear=0.2)
    fitted = wear_export(laps)["byLapTime"]
    assert fitted["degradationMsPerLap"] is None
    assert "degradationUnavailable" in fitted


def test_one_incident_lap_cannot_set_the_trend():
    """Least squares gave an un-struck five-second lap full weight and took
    the sign of the whole session with it."""
    clean = [(n, 109_000) for n in range(1, 12)]
    assert trend_slope(clean) == 0
    assert trend_slope(clean[:3] + [(4, 137_000)] + clean[4:]) == 0


def test_two_runs_trending_opposite_ways_are_not_hidden_behind_one():
    laps = ([a_lap(n, fuel_start=100.0 - 6.5 * (n - 1),
                   fuel_end=100.0 - 6.5 * n, compound="RH",
                   lap_time_ms=109_000 + n * 200) for n in range(1, 8)]
            + [a_lap(n, fuel_start=100.0 - 6.5 * (n - 8),
                     fuel_end=100.0 - 6.5 * (n - 7), compound="RH",
                     lap_time_ms=112_000 - n * 60) for n in range(8, 16)])
    fitted = wear_export(laps)["byLapTime"]
    assert "runsDisagree" in fitted
    assert "does not agree with itself" in fitted["runsDisagree"]


# ------------------------------------------------------------ P6 run identity

def test_runs_come_from_the_tank_and_carry_their_laps():
    laps = a_run(1, 4, compound="RS") + a_run(5, 3, compound="RS")
    runs = split_runs(laps)
    assert [(run.id, run.first_lap, run.last_lap) for run in runs] == [
        (1, 1, 4), (2, 5, 7)]
    assert runs[0].refuelled_before is False
    assert runs[1].refuelled_before is True


def test_fresh_tyres_are_null_until_the_driver_says_never_false():
    """`false` is the positive claim that the set carried over, and GT7
    broadcasts no tyre-change event either way."""
    runs = split_runs(a_run(1, 4, compound="RS") + a_run(5, 3, compound="RS"))
    assert [run.as_export()["tyresFresh"] for run in runs] == [None, None]


def test_a_declared_fresh_set_makes_the_rate_measured():
    laps = a_run(1, 6, compound="RH", final_wear=0.42)
    laps[0] = replace(laps[0], tyres_fresh=True)
    record = wear_export(laps)["byRun"][0]
    assert record["confidence"] == "measured"
    assert "assumesFreshAtLap" not in record


def test_an_undeclared_set_states_what_it_assumed():
    record = wear_export(a_run(1, 6, compound="RH", final_wear=0.42))["byRun"][0]
    assert record["confidence"] == "assumed"
    assert record["assumesFreshAtLap"] == 1


def test_every_gauge_reading_names_its_run():
    """Without it, a reading at lap 21 and the same reading at lap 36 cannot
    be told from one set read twice."""
    laps = (a_run(1, 4, compound="RS", final_wear=0.5)
            + a_run(5, 4, compound="RS", final_wear=0.8))
    assert [r["runId"] for r in wear_export(laps)["byDriverGauge"]] == [1, 2]


def test_a_rate_is_never_taken_across_a_refuel():
    """The defect: one reading divided by the laps of three tanks, which read
    a set consuming 17% a lap as 6.9%."""
    laps = (a_run(1, 4, compound="RS")
            + a_run(5, 2, compound="RS")
            + a_run(7, 4, compound="RS", final_wear=0.69))
    assert wear_export(laps)["byCompound"]["RS"]["wearPerLap"] == 0.1725


def test_a_pinned_gauge_is_flagged_rather_than_read_through():
    """Twice the same reading on one set: the gauge has saturated."""
    laps = a_run(1, 10, compound="RH")
    laps[4] = replace(laps[4], wear_rl=0.84)
    laps[9] = replace(laps[9], wear_rl=0.84)
    assert "gaugePinned" in wear_export(laps)


def test_two_sets_ending_equally_worn_are_not_a_pinned_gauge():
    """The reading at lap 5 and the reading at lap 10 are of different sets.

    Before runs existed the two cases were indistinguishable, and the 11 Aug
    session's 84% at lap 21 and 84% at lap 36 was reported as a gauge that had
    stopped moving. It was two sets that came off equally worn.
    """
    laps = (a_run(1, 5, compound="RH", final_wear=0.84)
            + a_run(6, 5, compound="RH", final_wear=0.84))
    assert "gaugePinned" not in wear_export(laps)


# ------------------------------------------------ P5 the confidence roll-up

def test_the_section_confidence_is_no_stronger_than_what_is_beneath_it():
    laps = a_run(1, 6, compound="RH", final_wear=0.42)
    wear = wear_export(laps)
    assert wear["byRun"][0]["confidence"] == "assumed"
    assert wear["modelConfidence"] == "assumed"
    assert "byRun[1]" in wear["modelConfidenceBasis"]


def test_the_roll_up_names_what_it_does_not_cover():
    laps = [replace(lap, frames=[frame(n * 10.0, 200.0, n) for n in range(30)])
            for lap in a_run(1, 6, compound="RH", final_wear=0.42)]
    basis = wear_export(laps)["modelConfidenceBasis"]
    assert "corroborate" in basis


def test_the_multiplier_the_rate_was_measured_at_travels_with_it():
    """Multiplier linearity is assumed and has never been demonstrated."""
    wear = wear_export(a_run(1, 6, compound="RH", final_wear=0.42),
                       race_multiplier="8x")
    assert wear["wearMeasuredAtRaceMultiplier"] is True
    assert wear["wearMultiplier"] == "8x"


# ------------------------------------------------------- P7 exclusion reasons

def test_the_out_lap_after_a_refuel_names_itself():
    """Four of the eight hand strikes in the Monza session were out-laps the
    refuel boundary names for free."""
    laps = classify_exclusions(
        a_run(1, 4, compound="RH") + a_run(5, 4, compound="RH"), 100.0)
    detail = session_export(laps, 100.0)["lapsExcludedDetail"]
    assert detail == [{"lap": 5, "reason": "out-lap", "source": "auto"}]


# ---------------------------------------------------------------- P3 gearing

class _FrameLap:
    """A lap of frames, with the ratios the box was running."""

    def __init__(self, frames, ratios=None):
        self.frames = frames
        self.gear_ratios = ratios


def _cruise(speed_kph: float, rpm: float, gear: int, radius: float = 0.355):
    return [frame(index * 10.0, speed_kph, index, gear=gear, rpm=rpm,
                  tyre_radius_m=radius) for index in range(40)]


def test_the_final_drive_derivation_is_not_inverted():
    """More engine revs for the same road speed is *more* final drive.

    Reported as inverted, and it is not - the figure reads high because GT7
    broadcasts the unloaded tyre radius. Tested in both directions because an
    inverted ratio produces a plausible number rather than an absurd one.
    """
    ratios = [2.7, 1.9, 1.5, 1.3, 1.15, 1.06]
    low = final_drive([_FrameLap(_cruise(280.0, 8000.0, 6))], ratios)
    high = final_drive([_FrameLap(_cruise(280.0, 9000.0, 6))], ratios)
    taller = final_drive([_FrameLap(_cruise(320.0, 8000.0, 6))], ratios)
    assert high > low
    assert taller < low


def test_matches_sheet_says_what_it_does_not_cover():
    ratios = [2.7, 1.9, 1.5, 1.3, 1.15, 1.06]
    gearing = gearing_export([_FrameLap(_cruise(280.0, 8000.0, 6), ratios)],
                             ratios, sheet_final_gear=3.55)
    assert gearing["matchesSheet"] is True
    assert "does NOT cover the final drive" in gearing["matchesSheetCovers"]
    assert gearing["finalGearSheet"] == 3.55
    assert gearing["finalGearVsSheetPct"] is not None


def test_the_limiter_says_which_gear_it_fired_in():
    """`observed-at-rev-limiter` beside `topGearReachedLimiter: false` reads
    as a contradiction until this says the limiter fired in first."""
    ratios = [2.7, 1.9, 1.5, 1.3, 1.15, 1.06]
    frames = _cruise(280.0, 8000.0, 6) + [
        frame(500.0, 80.0, 50, gear=1, rpm=8600.0, rev_limiter=1)]
    gearing = gearing_export([_FrameLap(frames, ratios)], ratios)
    assert gearing["limiterGear"] == 1
    assert gearing["topGearReachedLimiter"] is False


# --------------------------------------------------------- P10 the constant K

def test_k_is_extrapolated_to_the_limiter_and_says_so():
    ratios = [2.7, 1.9, 1.5, 1.3, 1.15, 1.062]
    frames = _cruise(278.7, 8009.0, 6) + [
        frame(500.0, 80.0, 50, gear=1, rpm=8600.0, rev_limiter=1)]
    gearing = gearing_export([_FrameLap(frames, ratios)], ratios,
                             sheet_final_gear=3.55)
    assert gearing["gearingConstantK"] == pytest.approx(1128.3, abs=1.0)
    assert gearing["gearingConstantSource"].startswith("extrapolated:")
    assert gearing["gearingConstantSamples"] == 1


def test_k_uses_the_sheets_final_drive_not_the_derived_one():
    """The derived figure is a few percent high through the unloaded radius,
    and K built on it would put every future gearbox out by the same."""
    ratios = [2.7, 1.9, 1.5, 1.3, 1.15, 1.062]
    frames = _cruise(278.7, 8009.0, 6) + [
        frame(500.0, 80.0, 50, gear=1, rpm=8600.0, rev_limiter=1)]
    gearing = gearing_export([_FrameLap(frames, ratios)], ratios,
                             sheet_final_gear=3.55)
    assert gearing["gearingConstantFinalGear"] == 3.55
    assert gearing["gearingConstantFinalGearSource"] == "sheet"
    assert gearing["fittedFinalGear"] != 3.55


def test_k_is_omitted_outside_top_gear():
    """Anywhere else the car was not going as fast as the gearing allows, and
    no scaling recovers that."""
    ratios = [2.7, 1.9, 1.5, 1.3, 1.15, 1.062]
    gearing = gearing_export([_FrameLap(_cruise(200.0, 8000.0, 4), ratios)],
                             ratios, sheet_final_gear=3.55)
    assert "gearingConstantK" not in gearing


# ------------------------------------------------------------------ P9 / meta

def test_a_measurement_without_a_game_version_is_refused():
    """GT7 rewrote its physics twice in two updates; a measurement that does
    not say which one it was taken under cannot be filed."""
    problems = validate(build_payload(a_meta(game_version=None)))
    assert any("gameVersion" in problem for problem in problems)


def test_runs_must_not_overlap():
    payload = build_payload(a_meta(), runs=[
        {"id": 1, "firstLap": 1, "lastLap": 10},
        {"id": 2, "firstLap": 8, "lastLap": 14}])
    assert any("belongs to one run" in problem for problem in validate(payload))


def test_a_carried_over_set_needs_its_source():
    payload = build_payload(a_meta(), runs=[
        {"id": 1, "firstLap": 1, "lastLap": 10, "tyresFresh": False}])
    assert any("positive claim" in problem for problem in validate(payload))


def test_no_key_anywhere_may_claim_a_tow():
    """GT7 carries no proximity, closing speed or opponent positions."""
    payload = build_payload(a_meta(), runs=[
        {"id": 1, "firstLap": 1, "lastLap": 4, "towDetected": True}])
    assert any("tow" in problem for problem in validate(payload))
