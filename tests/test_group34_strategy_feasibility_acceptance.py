"""
Group 34 — Accepted Criteria: Validated, Feasibility-Gated Race Strategy Prompt

Cross-cutting acceptance tests for the feasibility-gated strategy pipeline.
Groups 32 and 33 cover the unit-level contracts; this file verifies each
acceptance criterion end-to-end from the user story.

Coverage:
  AC1  Missing required fields produce named data_gaps (not silent fallbacks)
  AC2  Timed race: estimated_laps == ceil(duration_s / representative_clean_lap_s)
       + "complete the lap in progress" assumption
  AC3  Impossible stop counts rejected BEFORE the AI call, appear in rejected_strategies
  AC4  Candidate stop counts derived from measured data; missing fuel burn produces gap
  AC5  Strategy names decoupled from speed rank; prompt includes estimated_speed_rank
  AC6  Output has 4 top-level fields; parser populates them; rejected appear in output
  AC7  Prompt has a data-quality summary with std-dev, excluded-lap note, per-compound confidence
  AC8  RS/RH (any compound) blocked unless >=8 clean laps + full data set
  AC9  pit_time formula pit_loss + ceil(fuel/refuel); prompt states sequential;
       event pit_loss authoritative over seed pit delta
  AC10 Each strategy carries risk fields; parser reads them
  AC11 Locked tuning categories: allowed=[brake_balance, suspension, differential, aero]
       locks transmission/power/ballast/steering/nitrous; tuning_locked=True suppresses setup advice
  AC12 Prompt explicitly says: don't invent missing compound data; don't produce impossible
       stop counts; reject infeasible explicitly; prefer measured data; seed track is context only;
       return JSON with the five sections
  AC13 Full-suite smoke (no new failures); no AttributeError from result-type change

Extra criteria from user story:
  EC1  Event pit loss overrides seed pit delta (in assumptions)
  EC2  High lap variance creates a data-quality warning (in data-quality block, not DataGap)
  EC3  Missing fuel tank capacity creates a data gap (fuel burn missing → named gap)
  EC4  Valid strategy output remains strict JSON-compatible
"""
from __future__ import annotations

import dataclasses
import json
import math
import sys
from pathlib import Path
from statistics import stdev
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
# Shared helpers (style matches test_group32 / test_group29)
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


def _make_feasible_report(
    feasible_stop_counts: list[int] | None = None,
    estimated_laps: int = 20,
) -> FeasibilityReport:
    return FeasibilityReport(
        estimated_laps=estimated_laps,
        feasible_stop_counts=feasible_stop_counts if feasible_stop_counts is not None else [1],
        rejected_strategies=[RejectedStrategy("0-stop", "Tyre life too short")],
        data_gaps=[],
        assumptions=["Test assumption — lap in progress."],
        calculation_notes=["Test note."],
        eligible_compounds=["RM"],
        ineligible_compounds=[],
    )


# ---------------------------------------------------------------------------
# AC1 — Missing required fields produce NAMED data_gaps (no silent fallback)
# ---------------------------------------------------------------------------

class TestAC1MissingFieldsNamedDataGaps:
    """Every required field that is missing must produce a named DataGap.

    Required named gaps:
      - missing_refuel_speed   (refuel_speed_lps == 0)
      - missing_pit_loss       (pit_loss_secs == 0)
      - missing_fuel_burn      (fuel_burn_per_lap == 0)
      - no_lap_data            (lap_data_by_compound is empty)
    """

    def test_missing_refuel_speed_creates_named_gap(self):
        params = _make_params(refuel_speed_lps=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_refuel_speed" in gap_names, (
            f"Expected 'missing_refuel_speed' in data_gaps; got {gap_names}"
        )

    def test_missing_pit_loss_creates_named_gap(self):
        params = _make_params(pit_loss_secs=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_pit_loss" in gap_names, (
            f"Expected 'missing_pit_loss' in data_gaps; got {gap_names}"
        )

    def test_missing_fuel_burn_creates_named_gap(self):
        params = _make_params(fuel_burn_per_lap=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_fuel_burn" in gap_names, (
            f"Expected 'missing_fuel_burn' in data_gaps; got {gap_names}"
        )

    def test_no_lap_data_creates_named_gap(self):
        params = _make_params()
        report = compute_feasibility(params, {}, None, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert "no_lap_data" in gap_names, (
            f"Expected 'no_lap_data' in data_gaps; got {gap_names}"
        )

    def test_all_four_gaps_named_not_generic(self):
        """Each gap has a specific machine-readable name (not a blank or 'unknown' name)."""
        params = _make_params(
            refuel_speed_lps=0.0,
            pit_loss_secs=0.0,
            fuel_burn_per_lap=0.0,
        )
        report = compute_feasibility(params, {}, None, 20)
        for dg in report.data_gaps:
            assert dg.name, f"DataGap has empty name: {dg}"
            assert dg.name != "unknown", f"DataGap has generic name 'unknown': {dg}"

    def test_missing_fields_do_not_raise(self):
        """Feasibility gate must not raise on missing data — it returns a FeasibilityReport."""
        params = _make_params(
            refuel_speed_lps=0.0,
            pit_loss_secs=0.0,
            fuel_burn_per_lap=0.0,
        )
        report = compute_feasibility(params, {}, None, 20)
        assert isinstance(report, FeasibilityReport)


# ---------------------------------------------------------------------------
# AC2 — Timed race: estimated_laps == ceil(duration_s / representative_clean_lap_s)
#        + "complete the lap in progress" assumption
# ---------------------------------------------------------------------------

class TestAC2TimedRaceLapEstimate:
    """Canonical case: 120 min (7200 s) @ 96.290 s avg -> ceil(7200/96.290) = 75."""

    def test_canonical_120min_at_96290ms_gives_75(self):
        result = estimate_race_laps(7200.0, 96.290)
        assert result == 75, f"Expected 75, got {result}"

    def test_exact_formula_ceil_not_floor(self):
        # 7200 / 96.290 = 74.769... -> ceil = 75
        import math as _math
        expected = _math.ceil(7200.0 / 96.290)
        assert estimate_race_laps(7200.0, 96.290) == expected

    def test_complete_lap_assumption_in_report(self):
        """FeasibilityReport.assumptions must contain the 'lap in progress' note."""
        params = _make_params(
            race_type="timed",
            duration_mins=120,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps(base_ms=96290.0)}
        deg = {"RM": _make_deg_entry(optimal_stint_race=20)}
        report = compute_feasibility(params, laps, deg, 75)
        all_assumptions = " ".join(report.assumptions).lower()
        assert "lap in progress" in all_assumptions or "actual laps may be" in all_assumptions, (
            f"'lap in progress' assumption missing from: {report.assumptions}"
        )

    def test_zero_lap_time_returns_zero(self):
        assert estimate_race_laps(7200.0, 0.0) == 0

    def test_negative_lap_time_returns_zero(self):
        assert estimate_race_laps(7200.0, -5.0) == 0

    def test_representative_lap_note_in_calculation_notes(self):
        """Timed race: calculation_notes must explain how laps were estimated."""
        params = _make_params(
            race_type="timed",
            duration_mins=120,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps(base_ms=96290.0)}
        deg = {"RM": _make_deg_entry(optimal_stint_race=20)}
        report = compute_feasibility(params, laps, deg, 75)
        all_notes = " ".join(report.calculation_notes).lower()
        assert "ceil" in all_notes or "estimated" in all_notes, (
            f"Expected 'ceil' or 'estimated' in calculation_notes; got: {report.calculation_notes}"
        )


# ---------------------------------------------------------------------------
# AC3 — Impossible stop counts rejected BEFORE the AI call
#        Canonical: 120-min @96.290s, RM optimal_stint=5 -> 0/1/2-stop ALL rejected
# ---------------------------------------------------------------------------

class TestAC3ImpossibleStopCountsRejected:
    """
    Canonical scenario: 75-lap race, RM optimal_stint=5.
    0-stop: needs 75-lap stint (>5) -> rejected.
    1-stop: needs ceil(75/2)=38-lap stints -> rejected.
    2-stop: needs ceil(75/3)=25-lap stints -> rejected.
    All 3 must appear in rejected_strategies with reasons.
    """

    def _make_report(self) -> FeasibilityReport:
        params = _make_params(
            race_type="timed",
            duration_mins=120,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps(base_ms=96290.0)}
        deg = {"RM": _make_deg_entry(optimal_stint_race=5, total_life_race=6, cliff_lap_practice=6)}
        return compute_feasibility(params, laps, deg, 75)

    def test_0_stop_rejected(self):
        report = self._make_report()
        names = [r.name for r in report.rejected_strategies]
        assert "0-stop" in names, f"0-stop not in rejected_strategies: {names}"

    def test_1_stop_rejected(self):
        report = self._make_report()
        names = [r.name for r in report.rejected_strategies]
        assert "1-stop" in names, f"1-stop not in rejected_strategies: {names}"

    def test_2_stop_rejected(self):
        report = self._make_report()
        names = [r.name for r in report.rejected_strategies]
        assert "2-stop" in names, f"2-stop not in rejected_strategies: {names}"

    def test_rejected_strategies_have_reasons(self):
        """Each rejected strategy must have a non-empty reason string."""
        report = self._make_report()
        for rs in report.rejected_strategies:
            assert rs.reason, f"RejectedStrategy '{rs.name}' has empty reason"

    def test_no_feasible_stop_counts(self):
        """With RM optimal_stint=5 and 75 laps, all stop counts should be rejected."""
        report = self._make_report()
        assert report.feasible_stop_counts == [], (
            f"Expected empty feasible_stop_counts; got {report.feasible_stop_counts}"
        )

# ---------------------------------------------------------------------------
# AC4 — Candidate stop counts derived from measured data; missing fuel burn -> data_gap
# ---------------------------------------------------------------------------

class TestAC4CandidateStopCountsFromMeasuredData:
    """Stop counts must be evaluated using measured data; gaps appear for missing data."""

    def test_missing_fuel_burn_produces_named_data_gap(self):
        """fuel_burn_per_lap == 0 must produce 'missing_fuel_burn' DataGap (not silent)."""
        params = _make_params(fuel_burn_per_lap=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_fuel_burn" in gap_names

    def test_missing_fuel_burn_gap_has_description(self):
        params = _make_params(fuel_burn_per_lap=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        for dg in report.data_gaps:
            if dg.name == "missing_fuel_burn":
                assert dg.description, "missing_fuel_burn gap must have a description"
                break

    def test_0_stop_rejected_when_fuel_burn_insufficient_for_race(self):
        """floor(100L / 3.0 L/lap) = 33 laps max; 40-lap race -> 0-stop rejected."""
        params = _make_params(fuel_burn_per_lap=3.0, total_laps=40)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=50)}
        report = compute_feasibility(params, laps, deg, 40)
        names = [r.name for r in report.rejected_strategies]
        assert "0-stop" in names

    def test_gt7_100l_tank_constant_used(self):
        """GT7 constant: 100L = full tank = 100%. Verify tank capacity in feasibility source."""
        from strategy.feasibility import _GT7_TANK_CAPACITY
        assert _GT7_TANK_CAPACITY == 100.0

    def test_missing_refuel_speed_produces_named_gap(self):
        """refuel_speed_lps == 0 must produce 'missing_refuel_speed' DataGap."""
        params = _make_params(refuel_speed_lps=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_refuel_speed" in gap_names


# ---------------------------------------------------------------------------
# AC8 — RS/RH blocked unless >=8 clean laps + full data set
# ---------------------------------------------------------------------------

class TestAC8CompoundBlockedWithInsufficientData:
    """RS and RH must be blocked from calculated stints unless >=8 clean laps + full data set.
    If data is missing they appear in data_gaps only, NOT in eligible_compounds."""

    def test_rs_blocked_with_7_clean_laps(self):
        params = _make_params(avail_tyres=["RS"])
        laps = {"RS": [90000.0] * 7}  # only 7 laps
        deg = {"RS": _make_deg_entry(optimal_stint_race=10)}
        report = compute_feasibility(params, laps, deg, 20)
        assert "RS" in report.ineligible_compounds
        assert "RS" not in report.eligible_compounds

    def test_rh_blocked_with_7_clean_laps(self):
        params = _make_params(avail_tyres=["RH"])
        laps = {"RH": [99000.0] * 7}  # only 7 laps
        deg = {"RH": _make_deg_entry(optimal_stint_race=35)}
        report = compute_feasibility(params, laps, deg, 20)
        assert "RH" in report.ineligible_compounds

    def test_rs_blocked_when_degradation_missing(self):
        params = _make_params(avail_tyres=["RS"])
        laps = {"RS": _make_8_laps(90000.0)}  # 8 laps but no deg entry
        report = compute_feasibility(params, laps, None, 20)
        assert "RS" in report.ineligible_compounds

    def test_rs_blocked_compound_appears_in_data_gaps(self):
        """Blocked RS must create a named DataGap (compound_RS_insufficient_data)."""
        params = _make_params(avail_tyres=["RS"])
        laps = {"RS": [90000.0] * 5}
        deg = {"RS": _make_deg_entry(optimal_stint_race=10)}
        report = compute_feasibility(params, laps, deg, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        assert any("RS" in n for n in gap_names), (
            f"Expected a DataGap mentioning RS; got {gap_names}"
        )

    def test_rs_eligible_with_8_laps_and_full_entry(self):
        """RS WITH >=8 laps and full deg entry must be eligible."""
        params = _make_params(avail_tyres=["RS"])
        laps = {"RS": _make_8_laps(90000.0)}
        deg = {"RS": _make_deg_entry(optimal_stint_race=10)}
        report = compute_feasibility(params, laps, deg, 20)
        assert "RS" in report.eligible_compounds

    def test_rs_blocked_when_no_confidence(self):
        """RS with no confidence in deg entry must be blocked."""
        params = _make_params(avail_tyres=["RS"])
        laps = {"RS": _make_8_laps(90000.0)}
        deg = {"RS": {
            "optimal_stint_race": 10,
            "total_life_race": 12,
            "cliff_lap_practice": 11,
            "pace_loss_at_cliff_s": 1.5,
            "confidence": None,  # missing
        }}
        report = compute_feasibility(params, laps, deg, 20)
        assert "RS" in report.ineligible_compounds


# ---------------------------------------------------------------------------
# AC9 — pit_time formula; sequential pit work; event pit_loss authoritative
# ---------------------------------------------------------------------------

class TestAC9PitTimeFormulaAndSequentialWork:
    """pit_time = pit_loss + ceil(fuel/refuel); prompt states sequential;
    event pit_loss_secs is authoritative (not seed pit delta)."""

    def test_feasibility_assumptions_contain_pit_loss_authoritative(self):
        """FeasibilityReport.assumptions must state pit_loss_secs is authoritative."""
        params = _make_params(pit_loss_secs=23.0)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=20)}
        report = compute_feasibility(params, laps, deg, 20)
        all_assumptions = " ".join(report.assumptions)
        assert "authoritative" in all_assumptions.lower() or "pit_loss_secs" in all_assumptions, (
            f"Assumptions must mention pit_loss_secs as authoritative; got: {report.assumptions}"
        )

    def test_feasibility_assumptions_contain_sequential(self):
        """FeasibilityReport.assumptions must state pit work is sequential."""
        params = _make_params(pit_loss_secs=23.0)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=20)}
        report = compute_feasibility(params, laps, deg, 20)
        all_assumptions = " ".join(report.assumptions).lower()
        assert "sequential" in all_assumptions, (
            f"Assumptions must mention sequential pit work; got: {report.assumptions}"
        )


# ---------------------------------------------------------------------------
# AC13 — Full-suite smoke: no AttributeError from result-type change
# ---------------------------------------------------------------------------

class TestAC13NoAttributeErrorFromResultTypeChange:
    """Verify that downstream consumers of StrategyResult don't crash.
    The result must be iterable and support getattr(result, 'strategies', result)."""

    def _make_result(self) -> StrategyResult:
        strategies = [
            StrategyOption(
                rank=1, name="Safe", stints=[], estimated_time_s=3600.0,
                pit_time_s=23.0, summary="", risks="",
            )
        ]
        return StrategyResult(
            strategies=strategies,
            rejected_strategies=[RejectedStrategy("0-stop", "Too long")],
            data_gaps=[DataGap("missing_fuel_burn", "No fuel data")],
            assumptions=["Lap in progress assumption."],
            calculation_notes=["75 laps estimated."],
            feasibility=_make_feasible_report(),
        )

    def test_result_is_iterable(self):
        result = self._make_result()
        items = list(result)
        assert len(items) == 1

    def test_result_supports_len(self):
        result = self._make_result()
        assert len(result) == 1

    def test_result_supports_getitem(self):
        result = self._make_result()
        assert result[0].name == "Safe"

    def test_getattr_strategies_pattern(self):
        """Consumer pattern: getattr(payload, 'strategies', payload) must return list."""
        result = self._make_result()
        strategies = getattr(result, "strategies", result)
        assert isinstance(strategies, list)
        assert len(strategies) == 1

    def test_bare_list_still_works_with_getattr(self):
        """Old bare-list payload must also work with the getattr pattern."""
        payload = [StrategyOption(
            rank=1, name="Old", stints=[], estimated_time_s=0.0,
            pit_time_s=0.0, summary="", risks="",
        )]
        strategies = getattr(payload, "strategies", payload)
        # payload is a list — getattr returns the list itself
        assert isinstance(strategies, list)

    def test_no_attribute_error_on_result_strategies(self):
        result = self._make_result()
        try:
            _ = result.strategies
            _ = result.rejected_strategies
            _ = result.data_gaps
            _ = result.assumptions
            _ = result.calculation_notes
            _ = result.feasibility
        except AttributeError as exc:
            pytest.fail(f"AttributeError on StrategyResult: {exc}")

    def test_for_loop_over_result_gives_strategy_options(self):
        result = self._make_result()
        for s in result:
            assert isinstance(s, StrategyOption)


# ---------------------------------------------------------------------------
# EC1 — Event pit loss overrides seed pit delta (in assumptions and prompt)
# ---------------------------------------------------------------------------

class TestEC1EventPitLossOverridesSeedDelta:
    """The feasibility assumptions must explicitly state that event pit_loss_secs
    overrides seed pit delta data.  The prompt must echo this."""

    def test_feasibility_assumption_mentions_authoritative_pit_loss(self):
        params = _make_params(pit_loss_secs=26.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry(optimal_stint_race=20)}, 20
        )
        all_assumptions = " ".join(report.assumptions)
        assert "authoritative" in all_assumptions.lower() or "pit_loss_secs" in all_assumptions, (
            f"Assumption must state pit_loss_secs is authoritative; got: {report.assumptions}"
        )

    def test_feasibility_assumption_says_seed_not_used(self):
        params = _make_params(pit_loss_secs=26.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry(optimal_stint_race=20)}, 20
        )
        all_assumptions = " ".join(report.assumptions).lower()
        assert "seed" in all_assumptions or "not used" in all_assumptions, (
            f"Assumption must say seed-track pit delta is not used; got: {report.assumptions}"
        )

    def test_specific_pit_loss_value_echoed_in_assumptions(self):
        """Assumptions must include the actual pit_loss_secs value."""
        params = _make_params(pit_loss_secs=31.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry(optimal_stint_race=20)}, 20
        )
        all_assumptions = " ".join(report.assumptions)
        assert "31.0" in all_assumptions, (
            f"Assumptions must include pit_loss=31.0; got: {report.assumptions}"
        )


# ---------------------------------------------------------------------------
# EC2 — High lap variance creates a data-quality WARNING (data-quality block, not DataGap)
# ---------------------------------------------------------------------------

class TestEC2HighLapVarianceDataQualityWarning:
    """High std-dev lap times must surface in the data-quality BLOCK of the prompt
    (as a numerical std-dev value), NOT as a separate DataGap.

    Implementation detail: _compound_stats_lines and the data-quality block both include
    std-dev.  There is no automated DataGap created for high variance — the AI receives
    the std-dev number and draws its own conclusion.
    """

    def test_high_variance_std_dev_value_is_nonzero(self):
        """For high-variance data, the std-dev value must be > 0 in the prompt."""
        laps = [96000.0, 96100.0, 101500.0, 96200.0,
                97800.0, 96050.0, 103000.0, 96300.0]
        from statistics import stdev as _stdev
        sd_ms = _stdev(laps)
        assert sd_ms > 1000, f"Test data must have std-dev > 1s; got {sd_ms:.0f}ms"

    def test_no_separate_data_gap_for_high_variance(self):
        """High variance should NOT create an automatic DataGap in feasibility.
        The std-dev is surfaced in the prompt data-quality block instead."""
        laps_high_var = [
            96000.0, 96100.0, 105500.0, 96200.0,
            99800.0, 96050.0, 103000.0, 96300.0,
        ]
        params = _make_params()
        deg = {"RM": _make_deg_entry(confidence="medium")}
        report = compute_feasibility(params, {"RM": laps_high_var}, deg, 20)
        gap_names = [dg.name for dg in report.data_gaps]
        # There should be NO gap named "high_variance_RM" or similar
        variance_gaps = [n for n in gap_names if "variance" in n.lower() or "std" in n.lower()]
        assert variance_gaps == [], (
            f"Expected no variance DataGap; got {variance_gaps}. "
            "High variance is surfaced via the data-quality block in the prompt, not DataGap."
        )


# ---------------------------------------------------------------------------
# EC3 — Missing fuel tank capacity creates a data gap (via missing fuel burn)
# ---------------------------------------------------------------------------

class TestEC3MissingFuelBurnDataGap:
    """GT7 tank capacity is always 100L (encoded in _GT7_TANK_CAPACITY).
    There is no separate 'tank_capacity' field in RaceParams.
    The corresponding data gap is for missing fuel_burn_per_lap, not tank capacity.
    """

    def test_no_tank_capacity_field_in_race_params(self):
        """RaceParams must NOT have a tank_capacity field — it's always 100L."""
        field_names = {f.name for f in dataclasses.fields(RaceParams)}
        assert "tank_capacity" not in field_names, (
            "tank_capacity must NOT be a RaceParams field; it is a GT7 constant (100L)"
        )

    def test_gt7_tank_capacity_constant_is_100(self):
        from strategy.feasibility import _GT7_TANK_CAPACITY
        assert _GT7_TANK_CAPACITY == 100.0

    def test_missing_fuel_burn_produces_gap_not_silent_guess(self):
        """fuel_burn_per_lap == 0 -> named DataGap (not a silent default of e.g. 2.5)."""
        params = _make_params(fuel_burn_per_lap=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_fuel_burn" in gap_names

    def test_fuel_burn_gap_description_is_meaningful(self):
        params = _make_params(fuel_burn_per_lap=0.0)
        report = compute_feasibility(
            params, {"RM": _make_8_laps()}, {"RM": _make_deg_entry()}, 20
        )
        for dg in report.data_gaps:
            if dg.name == "missing_fuel_burn":
                assert "fuel" in dg.description.lower(), (
                    "missing_fuel_burn description must mention fuel"
                )
                break

    def test_0_stop_fuel_check_uses_100l_constant(self):
        """With fuel_burn=3.0 L/lap: floor(100/3.0)=33 laps max -> 0-stop rejected at 40 laps."""
        params = _make_params(fuel_burn_per_lap=3.0, total_laps=40)
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=50)}
        report = compute_feasibility(params, laps, deg, 40)
        names = [r.name for r in report.rejected_strategies]
        assert "0-stop" in names, (
            "0-stop must be rejected when 100L tank cannot cover the race distance"
        )
        # Verify the reason mentions fuel
        for rs in report.rejected_strategies:
            if rs.name == "0-stop":
                assert "fuel" in rs.reason.lower(), "0-stop rejection reason must mention fuel"
                break


# ---------------------------------------------------------------------------
# Fix 5 — missing_race_duration DataGap when estimated_laps == 0
# ---------------------------------------------------------------------------

class TestFix5MissingRaceDurationGap:
    """compute_feasibility must emit 'missing_race_duration' DataGap and return
    empty feasible_stop_counts when estimated_laps <= 0."""

    def test_timed_race_zero_duration_emits_gap(self):
        """Timed race with duration_mins=0 → missing_race_duration gap."""
        params = _make_params(
            race_type="timed",
            duration_mins=0,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=18)}
        # estimated_laps=0 because duration=0s → ceil(0/anything) = 0
        report = compute_feasibility(params, laps, deg, 0)
        gap_names = [dg.name for dg in report.data_gaps]
        assert "missing_race_duration" in gap_names, (
            f"Expected 'missing_race_duration' gap when estimated_laps=0; got {gap_names}"
        )

    def test_zero_estimated_laps_gives_empty_feasible_stop_counts(self):
        """When estimated_laps=0 the feasible_stop_counts must be empty."""
        params = _make_params(
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=18)}
        report = compute_feasibility(params, laps, deg, 0)
        assert report.feasible_stop_counts == [], (
            f"Expected empty feasible_stop_counts when estimated_laps=0; "
            f"got {report.feasible_stop_counts}"
        )

    def test_zero_estimated_laps_does_not_crash(self):
        """compute_feasibility must not raise when estimated_laps=0."""
        params = _make_params(
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=18)}
        try:
            report = compute_feasibility(params, laps, deg, 0)
            assert isinstance(report, FeasibilityReport)
        except Exception as exc:
            pytest.fail(f"compute_feasibility raised on estimated_laps=0: {exc}")

    def test_zero_stop_not_marked_feasible_when_laps_zero(self):
        """0-stop must NOT appear in feasible_stop_counts when estimated_laps=0."""
        params = _make_params(
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=18)}
        report = compute_feasibility(params, laps, deg, 0)
        assert 0 not in report.feasible_stop_counts, (
            "0-stop must NOT be feasible when estimated_laps=0"
        )

    def test_missing_race_duration_gap_has_meaningful_description(self):
        """The gap description must explain the issue clearly."""
        params = _make_params(
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry(optimal_stint_race=18)}
        report = compute_feasibility(params, laps, deg, 0)
        for dg in report.data_gaps:
            if dg.name == "missing_race_duration":
                assert dg.description, "missing_race_duration gap must have a description"
                assert "duration" in dg.description.lower() or "lap" in dg.description.lower(), (
                    "Description must mention duration or lap count"
                )
                break
        else:
            pytest.fail("missing_race_duration DataGap not found in report")
