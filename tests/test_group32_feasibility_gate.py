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

import strategy.ai_planner as ap
from strategy.feasibility import (
    DataGap,
    FeasibilityReport,
    RejectedStrategy,
    check_compound_eligibility,
    compute_feasibility,
    estimate_race_laps,
)

AP_SOURCE = (ROOT / "strategy" / "ai_planner.py").read_text(encoding="utf-8")
FEASIBILITY_SOURCE = (ROOT / "strategy" / "feasibility.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(**overrides):
    """Construct a minimal RaceParams, tolerant of the dataclass's required fields."""
    RaceParams = ap.RaceParams
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
# _parse_strategies — new fields populated from JSON
# ---------------------------------------------------------------------------

class TestParseStrategiesNewFields:
    def _make_raw(self, strategy_extra: dict | None = None, **top_level) -> str:
        s = {
            "rank": 1,
            "name": "Safe",
            "stints": [],
            "estimated_time_s": 3600.0,
            "pit_time_s": 23.0,
            "summary": "Test",
            "risks": "None",
            "positives": "",
            "negatives": "",
            "estimated_speed_rank": 2,
            "tyre_risk": "low",
            "fuel_risk": "medium",
            "traffic_risk": "high",
            "undercut_risk": "low",
            "confidence_score": 0.85,
            "why_label": "Because it is safe.",
        }
        if strategy_extra:
            s.update(strategy_extra)
        data = {"strategies": [s], **top_level}
        return json.dumps(data)

    def test_estimated_speed_rank_parsed(self):
        raw = self._make_raw()
        result = ap._parse_strategies(raw)
        assert result.strategies[0].estimated_speed_rank == 2

    def test_tyre_risk_parsed(self):
        raw = self._make_raw()
        result = ap._parse_strategies(raw)
        assert result.strategies[0].tyre_risk == "low"

    def test_fuel_risk_parsed(self):
        raw = self._make_raw()
        result = ap._parse_strategies(raw)
        assert result.strategies[0].fuel_risk == "medium"

    def test_traffic_risk_parsed(self):
        raw = self._make_raw()
        result = ap._parse_strategies(raw)
        assert result.strategies[0].traffic_risk == "high"

    def test_undercut_risk_parsed(self):
        raw = self._make_raw()
        result = ap._parse_strategies(raw)
        assert result.strategies[0].undercut_risk == "low"

    def test_confidence_score_parsed(self):
        raw = self._make_raw()
        result = ap._parse_strategies(raw)
        assert abs(result.strategies[0].confidence_score - 0.85) < 1e-6

    def test_why_label_parsed(self):
        raw = self._make_raw()
        result = ap._parse_strategies(raw)
        assert result.strategies[0].why_label == "Because it is safe."

    def test_top_level_rejected_strategies_parsed(self):
        raw = self._make_raw(
            rejected_strategies=[{"name": "0-stop", "reason": "Tyre life too short"}]
        )
        result = ap._parse_strategies(raw)
        assert len(result.rejected_strategies) == 1
        assert result.rejected_strategies[0].name == "0-stop"
        assert "Tyre life" in result.rejected_strategies[0].reason

    def test_top_level_data_gaps_parsed(self):
        raw = self._make_raw(
            data_gaps=[{"name": "compound_RS_insufficient_data", "description": "RS has only 3 laps"}]
        )
        result = ap._parse_strategies(raw)
        assert len(result.data_gaps) == 1
        assert result.data_gaps[0].name == "compound_RS_insufficient_data"
        assert "3 laps" in result.data_gaps[0].description

    def test_top_level_data_gaps_plain_strings_tolerated(self):
        raw = self._make_raw(data_gaps=["RS has only 3 laps"])
        result = ap._parse_strategies(raw)
        assert len(result.data_gaps) == 1
        assert "3 laps" in result.data_gaps[0].description

    def test_top_level_assumptions_parsed(self):
        raw = self._make_raw(assumptions=["GT7 may require completing the lap in progress."])
        result = ap._parse_strategies(raw)
        assert len(result.assumptions) == 1
        assert "lap in progress" in result.assumptions[0]

    def test_top_level_calculation_notes_parsed(self):
        raw = self._make_raw(calculation_notes=["Race laps = ceil(7200/96.3) = 75."])
        result = ap._parse_strategies(raw)
        assert len(result.calculation_notes) == 1
        assert "75" in result.calculation_notes[0]


# ---------------------------------------------------------------------------
# _parse_strategies — backward compat on old JSON (missing new fields)
# ---------------------------------------------------------------------------

class TestParseStrategiesBackwardCompat:
    def _old_json(self) -> str:
        return json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "Safe",
                "stints": [],
                "estimated_time_s": 3600.0,
                "pit_time_s": 23.0,
                "summary": "Old style",
                "risks": "None",
            }]
            # No new fields, no rejected_strategies, no data_gaps, etc.
        })

    def test_no_keyerror_on_old_json(self):
        result = ap._parse_strategies(self._old_json())
        assert len(result.strategies) == 1

    def test_new_fields_default_when_absent(self):
        result = ap._parse_strategies(self._old_json())
        s = result.strategies[0]
        assert s.estimated_speed_rank == 0
        assert s.tyre_risk == ""
        assert s.fuel_risk == ""
        assert s.traffic_risk == ""
        assert s.undercut_risk == ""
        assert s.confidence_score == 0.0
        assert s.why_label == ""

    def test_rejected_strategies_empty_when_absent(self):
        result = ap._parse_strategies(self._old_json())
        assert result.rejected_strategies == []

    def test_data_gaps_empty_when_absent(self):
        result = ap._parse_strategies(self._old_json())
        assert result.data_gaps == []

    def test_assumptions_empty_when_absent(self):
        result = ap._parse_strategies(self._old_json())
        assert result.assumptions == []

    def test_calculation_notes_empty_when_absent(self):
        result = ap._parse_strategies(self._old_json())
        assert result.calculation_notes == []


# ---------------------------------------------------------------------------
# StrategyResult iterable shim
# ---------------------------------------------------------------------------

class TestStrategyResultIterable:
    def _make_result(self, n_strategies: int = 2) -> ap.StrategyResult:
        strategies = [
            ap.StrategyOption(
                rank=i + 1, name=f"S{i}", stints=[], estimated_time_s=3600.0,
                pit_time_s=23.0, summary="", risks="",
            )
            for i in range(n_strategies)
        ]
        feasibility = _make_feasible_report()
        return ap.StrategyResult(
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
            assert isinstance(s, ap.StrategyOption)


# ---------------------------------------------------------------------------
# _build_race_prompt — content checks
# ---------------------------------------------------------------------------

class TestBuildRacePromptContent:
    def _make_prompt(
        self,
        feasibility_report: FeasibilityReport | None = None,
        **param_overrides,
    ) -> str:
        params = _make_params(**param_overrides)
        lap_data = {"RM": _make_8_laps()}
        return ap._build_race_prompt(
            params, lap_data, degradation=None,
            feasibility_report=feasibility_report,
        )

    def test_considers_only_feasible_stop_counts_when_provided(self):
        report = _make_feasible_report(feasible_stop_counts=[2])
        p = self._make_prompt(feasibility_report=report)
        # Must mention "consider ONLY" or equivalent
        assert "consider ONLY" in p or "2-stop" in p
        # Must NOT contain the old hardcoded 1-stop/2-stop/no-stop instruction
        assert "1-stop, 2-stop, and no-stop" not in p

    def test_prompt_contains_data_quality_block(self):
        report = _make_feasible_report()
        p = self._make_prompt(feasibility_report=report)
        assert "Data Quality" in p

    def test_prompt_decouples_safe_balanced_aggressive_from_rank(self):
        report = _make_feasible_report()
        p = self._make_prompt(feasibility_report=report)
        # Must mention estimated_speed_rank
        assert "estimated_speed_rank" in p
        # Must NOT force Safe=Rank1 in a rigid assignment
        # The old "Name the three strategies exactly: Rank 1: Safe" is removed
        assert "Rank 1: \"Safe\"" not in p

    def test_prompt_contains_do_not_invent_missing_compound_data(self):
        report = _make_feasible_report()
        p = self._make_prompt(feasibility_report=report)
        assert "do not invent missing compound data" in p.lower()

    def test_prompt_mentions_sequential_pit_work(self):
        report = _make_feasible_report()
        p = self._make_prompt(feasibility_report=report)
        assert "sequential" in p.lower()

    def test_prompt_contains_feasibility_section(self):
        report = _make_feasible_report(feasible_stop_counts=[1, 2])
        p = self._make_prompt(feasibility_report=report)
        assert "Feasibility Gate" in p

    def test_empty_feasible_counts_instructs_zero_strategies(self):
        report = _make_feasible_report(feasible_stop_counts=[])
        p = self._make_prompt(feasibility_report=report)
        assert "zero feasible strategies" in p.lower() or "return zero feasible" in p.lower() or "ALL stop counts" in p

    def test_prompt_risk_fields_in_schema(self):
        report = _make_feasible_report()
        p = self._make_prompt(feasibility_report=report)
        assert "tyre_risk" in p
        assert "fuel_risk" in p
        assert "traffic_risk" in p
        assert "undercut_risk" in p
        assert "confidence_score" in p
        assert "why_label" in p

    def test_prompt_without_feasibility_report_still_works(self):
        # No feasibility_report → falls back to generic instruction
        p = self._make_prompt(feasibility_report=None)
        assert "consider" in p.lower()
        # Should not crash
        assert len(p) > 100


# ---------------------------------------------------------------------------
# analyse_strategy end-to-end (mocked API)
# ---------------------------------------------------------------------------

class TestAnalyseStrategyEndToEnd:
    def _make_api_response(self) -> str:
        return json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "Safe — 1-Stop RM",
                "estimated_speed_rank": 1,
                "stints": [{"compound": "RM", "laps": 10, "ref_lap_ms": 96290, "pace_threshold_ms": 2500}],
                "estimated_time_s": 3600.0,
                "pit_time_s": 23.0,
                "summary": "One stop on Medium.",
                "risks": "Low risk.",
                "positives": "Stable.",
                "negatives": "Not the fastest.",
                "tyre_risk": "low",
                "fuel_risk": "low",
                "traffic_risk": "medium",
                "undercut_risk": "medium",
                "confidence_score": 0.8,
                "why_label": "Chosen for safety.",
            }],
            "rejected_strategies": [],
            "data_gaps": [],
            "assumptions": [],
            "calculation_notes": [],
        })

    def test_returns_strategy_result(self):
        params = _make_params(total_laps=20)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry()}
        with patch("strategy.ai_planner.call_api", return_value=self._make_api_response()):
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)
        assert isinstance(result, ap.StrategyResult)

    def test_result_is_iterable(self):
        params = _make_params(total_laps=20)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry()}
        with patch("strategy.ai_planner.call_api", return_value=self._make_api_response()):
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)
        strategies = list(result)
        assert len(strategies) >= 0

    def test_result_has_feasibility_attribute(self):
        params = _make_params(total_laps=20)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry()}
        with patch("strategy.ai_planner.call_api", return_value=self._make_api_response()):
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)
        assert hasattr(result, "feasibility")
        assert isinstance(result.feasibility, FeasibilityReport)

    def test_feasibility_gaps_merged_into_result(self):
        """Feasibility data_gaps from the report are merged into the StrategyResult."""
        params = _make_params(total_laps=20, fuel_burn_per_lap=0.0)  # missing_fuel_burn
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry()}
        with patch("strategy.ai_planner.call_api", return_value=self._make_api_response()):
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)
        gap_names = [dg.name for dg in result.data_gaps]
        assert "missing_fuel_burn" in gap_names

    def test_feasibility_assumptions_merged_into_result(self):
        """Feasibility assumptions from the report are merged into the StrategyResult."""
        params = _make_params(race_type="timed", duration_mins=60, total_laps=0)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry()}
        with patch("strategy.ai_planner.call_api", return_value=self._make_api_response()):
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)
        all_assumptions = " ".join(result.assumptions)
        assert "sequential" in all_assumptions or "pit_loss_secs" in all_assumptions


# ---------------------------------------------------------------------------
# Source-level checks
# ---------------------------------------------------------------------------

class TestSourceLevelChecks:
    def test_feasibility_import_present_in_ai_planner(self):
        assert "from strategy.feasibility import" in AP_SOURCE

    def test_strategy_result_defined(self):
        assert "class StrategyResult" in AP_SOURCE

    def test_estimate_race_laps_imported(self):
        assert "estimate_race_laps" in AP_SOURCE

    def test_compute_feasibility_imported(self):
        assert "compute_feasibility" in AP_SOURCE

    def test_gt7_tank_capacity_constant_in_feasibility(self):
        assert "_GT7_TANK_CAPACITY" in FEASIBILITY_SOURCE
        assert "100.0" in FEASIBILITY_SOURCE

    def test_no_tank_capacity_field_added_to_race_params(self):
        # Brief says: do NOT add tank_capacity to RaceParams.
        # Check that RaceParams doesn't have a tank_capacity field (not just string match,
        # since "tank_capacity" appears legitimately in the race engineering context prose).
        field_names = {f.name for f in dataclasses.fields(ap.RaceParams)}
        assert "tank_capacity" not in field_names

    def test_sequential_pit_work_in_feasibility_assumptions(self):
        assert "sequential" in FEASIBILITY_SOURCE

    def test_analyse_strategy_returns_strategy_result_annotation(self):
        assert "StrategyResult" in AP_SOURCE
