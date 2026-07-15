"""
Group 32 — Feasibility-gated race strategy prompt pipeline

Tests the feasibility gate (strategy/feasibility.py) and its integration
with the AI strategy prompt pipeline (strategy/ai_planner.py).

All tests are in-memory only: no Qt widgets, no real API calls, no file I/O.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_params import RaceParams, StrategyOption, StrategyResult
from strategy.feasibility import (
    DataGap,
    FeasibilityReport,
    RejectedStrategy,
    check_compound_eligibility,
    compute_feasibility,
    estimate_race_laps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(**overrides):
    """Construct a minimal RaceParams, tolerant of the dataclass's required fields."""
    kwargs = {}
    for f in dataclasses.fields(RaceParams):
        if (
            f.default is not dataclasses.MISSING
            or f.default_factory is not dataclasses.MISSING  # type: ignore[attr-defined]
        ):
            continue
        ann = str(f.type)
        if "int" in ann:
            kwargs[f.name] = 0
        elif "float" in ann:
            kwargs[f.name] = 0.0
        elif "str" in ann:
            kwargs[f.name] = ""
        elif "bool" in ann:
            kwargs[f.name] = False
        else:
            kwargs[f.name] = None
    # Sensible race-ready defaults
    kwargs.update(dict(
        track="Spa",
        total_laps=20,
        tyre_wear_multiplier=1.0,
        fuel_burn_per_lap=2.5,
        refuel_speed_lps=10.0,
        pit_loss_secs=23.0,
    ))
    kwargs.update(overrides)
    return RaceParams(**kwargs)


def _make_deg_entry(
    optimal_stint_race: int = 18,
    total_life_race: int = 22,
    cliff_lap_practice: int = 19,
    pace_loss_at_cliff_s: float = 1.5,
    confidence: str = "high",
) -> dict:
    return {
        "optimal_stint_race": optimal_stint_race,
        "total_life_race": total_life_race,
        "cliff_lap_practice": cliff_lap_practice,
        "pace_loss_at_cliff_s": pace_loss_at_cliff_s,
        "confidence": confidence,
    }


def _make_8_laps(base_ms: float = 96290.0) -> list[float]:
    return [base_ms + i * 10 for i in range(8)]


def _make_feasible_report(feasible_stop_counts: list[int] | None = None) -> FeasibilityReport:
    return FeasibilityReport(
        estimated_laps=20,
        feasible_stop_counts=feasible_stop_counts if feasible_stop_counts is not None else [1],
        rejected_strategies=[],
        data_gaps=[],
        assumptions=["Test assumption."],
        calculation_notes=["Test note."],
        eligible_compounds=["RM"],
        ineligible_compounds=[],
    )


# ---------------------------------------------------------------------------
# estimate_race_laps
# ---------------------------------------------------------------------------

class TestEstimateRaceLaps:
    def test_120min_at_96290ms_gives_75(self):
        # 120 min = 7200s; 96.290s/lap → ceil(7200/96.290) = ceil(74.77) = 75
        result = estimate_race_laps(7200.0, 96.290)
        assert result == 75

    def test_exact_division_no_rounding_needed(self):
        # 100s / 10s = 10.0 exactly → ceil = 10
        result = estimate_race_laps(100.0, 10.0)
        assert result == 10

    def test_non_exact_rounds_up(self):
        # 101s / 10s = 10.1 → ceil = 11
        result = estimate_race_laps(101.0, 10.0)
        assert result == 11

    def test_zero_lap_time_returns_zero(self):
        result = estimate_race_laps(7200.0, 0.0)
        assert result == 0

    def test_negative_lap_time_returns_zero(self):
        result = estimate_race_laps(7200.0, -1.0)
        assert result == 0

    def test_zero_duration_returns_zero(self):
        result = estimate_race_laps(0.0, 90.0)
        assert result == 0


# ---------------------------------------------------------------------------
# check_compound_eligibility
# ---------------------------------------------------------------------------

class TestCheckCompoundEligibility:
    def test_eligible_with_8_laps_and_full_entry(self):
        eligible, reason = check_compound_eligibility(
            "RM", _make_8_laps(), _make_deg_entry()
        )
        assert eligible is True
        assert reason is None

    def test_ineligible_fewer_than_8_laps(self):
        eligible, reason = check_compound_eligibility(
            "RM", [96000.0] * 7, _make_deg_entry()
        )
        assert eligible is False
        assert "7" in reason
        assert "8 required" in reason

    def test_ineligible_no_degradation_entry(self):
        eligible, reason = check_compound_eligibility("RM", _make_8_laps(), None)
        assert eligible is False
        assert "degradation" in reason.lower() or "no degradation" in reason

    def test_ineligible_missing_optimal_stint(self):
        entry = _make_deg_entry(optimal_stint_race=0)
        eligible, reason = check_compound_eligibility("RM", _make_8_laps(), entry)
        assert eligible is False
        assert "optimal_stint_race" in reason

    def test_ineligible_no_max_stint_signal(self):
        entry = {
            "optimal_stint_race": 18,
            "total_life_race": 0,
            "cliff_lap_practice": 0,
            "pace_loss_at_cliff_s": None,
            "confidence": "high",
        }
        eligible, reason = check_compound_eligibility("RM", _make_8_laps(), entry)
        assert eligible is False
        assert "max-stint" in reason

    def test_eligible_with_cliff_data_but_no_total_life(self):
        entry = {
            "optimal_stint_race": 18,
            "total_life_race": 0,
            "cliff_lap_practice": 19,
            "pace_loss_at_cliff_s": 1.5,
            "confidence": "high",
        }
        eligible, reason = check_compound_eligibility("RM", _make_8_laps(), entry)
        assert eligible is True
        assert reason is None

    def test_eligible_with_total_life_but_no_cliff_data(self):
        entry = {
            "optimal_stint_race": 18,
            "total_life_race": 22,
            "cliff_lap_practice": 0,
            "pace_loss_at_cliff_s": None,
            "confidence": "high",
        }
        eligible, reason = check_compound_eligibility("RM", _make_8_laps(), entry)
        assert eligible is True
        assert reason is None

    def test_ineligible_missing_confidence(self):
        entry = _make_deg_entry()
        entry["confidence"] = None
        eligible, reason = check_compound_eligibility("RM", _make_8_laps(), entry)
        assert eligible is False
        assert "confidence" in reason


# ---------------------------------------------------------------------------
# compute_feasibility — global field validation
# ---------------------------------------------------------------------------

class TestComputeFeasibilityFieldValidation:
    def test_refuel_speed_zero_creates_gap_and_no_crash(self):
        params = _make_params(refuel_speed_lps=0.0)
        report = compute_feasibility(params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_refuel_speed" in gap_names
        # Fatal gap → no feasible stop counts but no crash
        assert report.feasible_stop_counts == []

    def test_fuel_burn_zero_creates_gap(self):
        params = _make_params(fuel_burn_per_lap=0.0)
        report = compute_feasibility(params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_fuel_burn" in gap_names

    def test_tyre_wear_zero_creates_gap(self):
        params = _make_params(tyre_wear_multiplier=0.0)
        report = compute_feasibility(params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_tyre_wear_multiplier" in gap_names

    def test_no_lap_data_creates_fatal_gap(self):
        params = _make_params()
        report = compute_feasibility(params, {}, None, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert "no_lap_data" in gap_names
        assert report.feasible_stop_counts == []

    def test_pit_loss_zero_creates_gap(self):
        params = _make_params(pit_loss_secs=0.0)
        report = compute_feasibility(params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_pit_loss" in gap_names


# ---------------------------------------------------------------------------
# compute_feasibility — compound eligibility integration
# ---------------------------------------------------------------------------

class TestComputeFeasibilityCompoundEligibility:
    def test_compound_fewer_than_8_laps_ineligible(self):
        params = _make_params()
        laps = {"RM": [96000.0] * 5}
        deg = {"RM": _make_deg_entry()}
        report = compute_feasibility(params, laps, deg, 20)
        assert "RM" in report.ineligible_compounds
        gap_names = [dg.name for dg in report.data_gaps]
        assert "compound_RM_insufficient_data" in gap_names

    def test_compound_missing_degradation_ineligible(self):
        params = _make_params()
        laps = {"RM": _make_8_laps()}
        report = compute_feasibility(params, laps, None, 20)  # degradation=None
        assert "RM" in report.ineligible_compounds

    def test_eligible_compound_appears_in_eligible_list(self):
        params = _make_params()
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry()}
        report = compute_feasibility(params, laps, deg, 20)
        assert "RM" in report.eligible_compounds

    def test_rs_rh_blocked_with_fewer_than_8_laps(self):
        """RS and RH with <8 laps must be blocked — brief requirement."""
        params = _make_params(avail_tyres=["RS", "RH"])
        laps = {"RS": [90000.0] * 3, "RH": [99000.0] * 6}
        deg = {"RS": _make_deg_entry(optimal_stint_race=10), "RH": _make_deg_entry(optimal_stint_race=35)}
        report = compute_feasibility(params, laps, deg, 20)
        assert "RS" in report.ineligible_compounds
        assert "RH" in report.ineligible_compounds


# ---------------------------------------------------------------------------
# compute_feasibility — 120-min at 96.29s with 5-lap optimal RM: rejects 0/1/2-stop
# ---------------------------------------------------------------------------

class TestFeasibilityRejectsShortOptimalStint:
    """The 120-min @ 96.290s + 5-lap-optimal RM case.

    estimated_laps = 75. For n stops:
      - 0-stop: per_stint = 75 > 5 → rejected (tyre limitation)
      - 1-stop: per_stint = ceil(75/2) = 38 > 5 → rejected
      - 2-stop: per_stint = ceil(75/3) = 25 > 5 → rejected
      - 3-stop: per_stint = ceil(75/4) = 19 > 5 → rejected
      - 4-stop: per_stint = ceil(75/5) = 15 > 5 → rejected
    All rejected because RM optimal stint is only 5 laps.
    """
    def _make_report(self) -> FeasibilityReport:
        params = _make_params(
            race_type="timed",
            duration_mins=120,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps(base_ms=96290.0)}
        deg = {"RM": _make_deg_entry(optimal_stint_race=5, total_life_race=6, cliff_lap_practice=6)}
        return compute_feasibility(params, laps, deg, 75)

    def test_0_stop_rejected(self):
        report = self._make_report()
        rejected_names = [r.name for r in report.rejected_strategies]
        assert "0-stop" in rejected_names

    def test_1_stop_rejected(self):
        report = self._make_report()
        rejected_names = [r.name for r in report.rejected_strategies]
        assert "1-stop" in rejected_names

    def test_2_stop_rejected(self):
        report = self._make_report()
        rejected_names = [r.name for r in report.rejected_strategies]
        assert "2-stop" in rejected_names

    def test_no_feasible_stop_counts(self):
        report = self._make_report()
        # All rejected → feasible_stop_counts is empty; no crash
        assert report.feasible_stop_counts == []

    def test_report_populated_even_when_all_rejected(self):
        report = self._make_report()
        assert len(report.rejected_strategies) > 0
        assert len(report.data_gaps) >= 0  # may or may not have gaps
        assert len(report.assumptions) > 0


# ---------------------------------------------------------------------------
# compute_feasibility — mandatory stop count
# ---------------------------------------------------------------------------

class TestMandatoryStopCount:
    def test_0_stop_rejected_when_mandatory_1_stop(self):
        params = _make_params(min_mandatory_stops=1)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=30)}
        report = compute_feasibility(params, laps, deg, 20)
        rejected_names = [r.name for r in report.rejected_strategies]
        assert "0-stop" in rejected_names

    def test_feasible_counts_respect_mandatory_minimum(self):
        params = _make_params(min_mandatory_stops=2)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=30)}
        report = compute_feasibility(params, laps, deg, 20)
        for n in report.feasible_stop_counts:
            assert n >= 2


# ---------------------------------------------------------------------------
# compute_feasibility — mandatory compound with no lap data
# ---------------------------------------------------------------------------

class TestMandatoryCompoundNoData:
    def test_mandatory_compound_no_data_creates_gap(self):
        params = _make_params(mandatory_compounds=["RS"])
        laps = {"RM": _make_8_laps()}  # RS has no data
        deg = {"RM": _make_deg_entry()}
        report = compute_feasibility(params, laps, deg, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert any("RS" in n for n in gap_names)

    def test_mandatory_compound_no_data_rejects_dependent_counts(self):
        params = _make_params(mandatory_compounds=["RS"])
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=30)}
        report = compute_feasibility(params, laps, deg, 20)
        # All stop counts should be rejected because RS (mandatory) has no data
        assert report.feasible_stop_counts == []


# ---------------------------------------------------------------------------
# compute_feasibility — fuel-limited 0-stop rejection
# ---------------------------------------------------------------------------

class TestFuelLimited0Stop:
    def test_0_stop_rejected_when_fuel_insufficient(self):
        # 100L / 3.0 L/lap = 33 laps max. Race is 40 laps → 0-stop is fuel-limited.
        params = _make_params(fuel_burn_per_lap=3.0, total_laps=40)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=50)}
        report = compute_feasibility(params, laps, deg, 40)
        rejected_names = [r.name for r in report.rejected_strategies]
        assert "0-stop" in rejected_names
        # 0-stop should mention fuel-limited in its reason
        for rs in report.rejected_strategies:
            if rs.name == "0-stop":
                assert "fuel" in rs.reason.lower()
                break


# ---------------------------------------------------------------------------
# compute_feasibility — all-rejected is valid, no crash
# ---------------------------------------------------------------------------

class TestAllRejectedNocrash:
    def test_empty_feasible_counts_no_exception(self):
        # Minimal valid params but very high lap count: optimal_stint=5, 75 laps
        params = _make_params(total_laps=75)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=5, total_life_race=6, cliff_lap_practice=6)}
        report = compute_feasibility(params, laps, deg, 75)
        # Must not raise; may have empty feasible counts
        assert isinstance(report, FeasibilityReport)
        assert isinstance(report.feasible_stop_counts, list)

    def test_populated_report_on_all_rejected(self):
        params = _make_params(total_laps=75)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=5, total_life_race=6, cliff_lap_practice=6)}
        report = compute_feasibility(params, laps, deg, 75)
        # Report must still have assumptions populated
        assert len(report.assumptions) > 0
        assert len(report.rejected_strategies) > 0


# ---------------------------------------------------------------------------
# compute_feasibility — single feasible stop count
# ---------------------------------------------------------------------------

class TestSingleFeasibleStopCount:
    def test_single_feasible_count(self):
        # 20 laps; optimal=15 laps. 0-stop needs 20 > 15 → rejected.
        # 1-stop needs ceil(20/2)=10 <= 15 → feasible.
        params = _make_params(total_laps=20)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=15, total_life_race=20, cliff_lap_practice=16)}
        report = compute_feasibility(params, laps, deg, 20)
        assert 1 in report.feasible_stop_counts


# ---------------------------------------------------------------------------
# compute_feasibility — standard assumptions always present
# ---------------------------------------------------------------------------

class TestStandardAssumptions:
    def test_timed_race_assumption_present(self):
        params = _make_params(race_type="timed", duration_mins=120)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=30)}
        report = compute_feasibility(params, laps, deg, 75)
        # The "lap in progress" assumption must be present
        all_assumptions = " ".join(report.assumptions)
        assert "lap in progress" in all_assumptions or "actual laps may be" in all_assumptions

    def test_pit_loss_assumption_present(self):
        params = _make_params()
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=30)}
        report = compute_feasibility(params, laps, deg, 20)
        all_assumptions = " ".join(report.assumptions)
        assert "pit_loss_secs" in all_assumptions or "authoritative" in all_assumptions

    def test_sequential_pit_work_assumption_present(self):
        params = _make_params()
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=30)}
        report = compute_feasibility(params, laps, deg, 20)
        all_assumptions = " ".join(report.assumptions)
        assert "sequential" in all_assumptions


# ---------------------------------------------------------------------------
# StrategyResult iterable shim
# ---------------------------------------------------------------------------

class TestStrategyResultIterable:
    def _make_result(self, n_strategies: int = 2) -> StrategyResult:
        strategies = [
            StrategyOption(
                rank=i + 1, name=f"S{i}", stints=[], estimated_time_s=3600.0,
                pit_time_s=23.0, summary="", risks="",
            )
            for i in range(n_strategies)
        ]
        feasibility = _make_feasible_report()
        return StrategyResult(
            strategies=strategies,
            rejected_strategies=[],
            data_gaps=[],
            assumptions=[],
            calculation_notes=[],
            feasibility=feasibility,
        )

    def test_len(self):
        result = self._make_result(2)
        assert len(result) == 2

    def test_iter(self):
        result = self._make_result(3)
        items = list(result)
        assert len(items) == 3

    def test_getitem(self):
        result = self._make_result(2)
        assert result[0].name == "S0"
        assert result[1].name == "S1"

    def test_for_loop(self):
        result = self._make_result(3)
        names = [s.name for s in result]
        assert names == ["S0", "S1", "S2"]

    def test_iterable_over_strategies_not_result_object(self):
        result = self._make_result(2)
        # Confirm iterating gives StrategyOption objects
        for s in result:
            assert isinstance(s, StrategyOption)
