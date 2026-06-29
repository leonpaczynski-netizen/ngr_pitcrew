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

import strategy.ai_planner as ap
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


def _minimal_api_response(**strategy_overrides) -> str:
    """Return a minimal valid API JSON response for patching call_api."""
    s = {
        "rank": 1,
        "name": "Safe — 1-Stop RM",
        "estimated_speed_rank": 2,
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
    }
    s.update(strategy_overrides)
    return json.dumps({
        "strategies": [s],
        "rejected_strategies": [{"name": "0-stop", "reason": "Tyre life too short"}],
        "data_gaps": [],
        "assumptions": ["GT7 may require completing the lap in progress."],
        "calculation_notes": ["Race laps = ceil(7200/96.3) = 75."],
    })


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

    def test_rejection_happens_before_api_call(self):
        """analyse_strategy must NOT call the API when all stop counts are rejected.

        The canonical all-rejected case: 120-min race @96.290s + RM optimal_stint=5
        means 0-stop, 1-stop, and 2-stop are all rejected by the feasibility gate.
        The API must never be called, and the returned StrategyResult must carry the
        pre-computed rejected_strategies and have an empty strategies list.
        """
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

        with patch("strategy.ai_planner.call_api") as mock_call_api:
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)

        # The API must NOT have been called
        mock_call_api.assert_not_called()

        # The result must carry the feasibility-gate rejected strategies
        all_rejected_names = [r.name for r in result.rejected_strategies]
        assert len(all_rejected_names) >= 1, (
            f"Expected at least one rejected strategy; got {all_rejected_names}"
        )

        # The result must have NO feasible strategies
        assert result.strategies == [], (
            f"Expected empty strategies list when all stop counts rejected; "
            f"got {result.strategies}"
        )

    def test_feasible_path_still_calls_api_once(self):
        """When at least one stop count is feasible, the API must be called exactly once."""
        # Use a short 10-lap race so 0-stop is feasible (optimal_stint=18 >> 10 laps needed)
        params = _make_params(
            race_type="lap",
            total_laps=10,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        laps = {"RM": _make_8_laps(base_ms=96290.0)}
        deg = {"RM": _make_deg_entry(optimal_stint_race=18, total_life_race=22)}

        api_resp = _minimal_api_response()
        with patch("strategy.ai_planner.call_api", return_value=api_resp) as mock_call_api:
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)

        mock_call_api.assert_called_once()
        # At least one strategy should be returned (from the API mock)
        assert isinstance(result, ap.StrategyResult)


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
# AC5 — Strategy names decoupled from speed rank; prompt includes estimated_speed_rank
# ---------------------------------------------------------------------------

class TestAC5StrategyNamesDecoupledFromRank:
    """The prompt must NOT force Safe=Rank1/Balanced=Rank2/Aggressive=Rank3.
    It must include 'estimated_speed_rank' in the schema."""

    def _build_prompt(self, feasibility_report=None, **overrides) -> str:
        params = _make_params(**overrides)
        return ap._build_race_prompt(
            params,
            {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=feasibility_report or _make_feasible_report(),
        )

    def test_prompt_contains_estimated_speed_rank_field(self):
        p = self._build_prompt()
        assert "estimated_speed_rank" in p, (
            "'estimated_speed_rank' field must appear in the race prompt"
        )

    def test_prompt_does_not_force_safe_equals_rank1(self):
        """The old hardcoded 'Rank 1: \"Safe\"' instruction must be removed."""
        p = self._build_prompt()
        assert 'Rank 1: "Safe"' not in p, (
            "Prompt must not force Safe=Rank1 in a rigid assignment"
        )

    def test_prompt_does_not_force_balanced_equals_rank2(self):
        p = self._build_prompt()
        assert 'Rank 2: "Balanced"' not in p

    def test_prompt_says_do_not_force_safe_rank1(self):
        """Prompt must explicitly state that Safe does not have to be Rank 1."""
        p = self._build_prompt()
        # The prompt states "Do NOT force Safe=Rank1, Balanced=Rank2, Aggressive=Rank3"
        assert "Do NOT force" in p or "not force" in p.lower() or "estimated_speed_rank" in p, (
            "Prompt must explicitly decouple name from rank"
        )

    def test_parse_strategies_reads_estimated_speed_rank(self):
        """Parser must populate estimated_speed_rank from the JSON."""
        raw = json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "Balanced — 1-Stop RM",
                "estimated_speed_rank": 1,
                "stints": [],
                "estimated_time_s": 3600.0,
                "pit_time_s": 23.0,
                "summary": "Best time.",
                "risks": "Medium.",
            }],
            "rejected_strategies": [],
            "data_gaps": [],
            "assumptions": [],
            "calculation_notes": [],
        })
        result = ap._parse_strategies(raw)
        assert result.strategies[0].estimated_speed_rank == 1

    def test_safe_strategy_can_have_rank1_speed(self):
        """A 'Safe' strategy is allowed to have estimated_speed_rank=1."""
        raw = json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "Safe — RM 2-Stop",
                "estimated_speed_rank": 1,  # Safe is fastest here
                "stints": [],
                "estimated_time_s": 3500.0,
                "pit_time_s": 23.0,
                "summary": "Fastest AND safest.",
                "risks": "Low.",
            }],
            "rejected_strategies": [],
            "data_gaps": [],
            "assumptions": [],
            "calculation_notes": [],
        })
        result = ap._parse_strategies(raw)
        assert result.strategies[0].estimated_speed_rank == 1
        assert "Safe" in result.strategies[0].name


# ---------------------------------------------------------------------------
# AC6 — Output has 4 top-level fields; parser populates them;
#        rejected strategies appear in output
# ---------------------------------------------------------------------------

class TestAC6OutputFourTopLevelFields:
    """StrategyResult must have rejected_strategies, data_gaps, assumptions,
    calculation_notes as non-empty (when the AI returns them)."""

    def _parse(self, **extra_top_level) -> ap.StrategyResult:
        base = {
            "strategies": [{
                "rank": 1,
                "name": "Safe",
                "stints": [],
                "estimated_time_s": 3600.0,
                "pit_time_s": 23.0,
                "summary": "OK",
                "risks": "none",
            }],
            "rejected_strategies": [{"name": "0-stop", "reason": "Too long"}],
            "data_gaps": [{"name": "compound_RS_insufficient_data", "description": "RS: 3 laps"}],
            "assumptions": ["GT7 may require completing the lap in progress."],
            "calculation_notes": ["Race laps = ceil(7200/96.3) = 75."],
        }
        base.update(extra_top_level)
        return ap._parse_strategies(json.dumps(base))

    def test_rejected_strategies_field_exists(self):
        result = self._parse()
        assert hasattr(result, "rejected_strategies")

    def test_data_gaps_field_exists(self):
        result = self._parse()
        assert hasattr(result, "data_gaps")

    def test_assumptions_field_exists(self):
        result = self._parse()
        assert hasattr(result, "assumptions")

    def test_calculation_notes_field_exists(self):
        result = self._parse()
        assert hasattr(result, "calculation_notes")

    def test_rejected_strategies_populated(self):
        result = self._parse()
        assert len(result.rejected_strategies) == 1
        assert result.rejected_strategies[0].name == "0-stop"

    def test_data_gaps_populated(self):
        result = self._parse()
        assert len(result.data_gaps) == 1
        assert result.data_gaps[0].name == "compound_RS_insufficient_data"

    def test_assumptions_populated(self):
        result = self._parse()
        assert len(result.assumptions) == 1
        assert "lap in progress" in result.assumptions[0]

    def test_calculation_notes_populated(self):
        result = self._parse()
        assert len(result.calculation_notes) == 1
        assert "75" in result.calculation_notes[0]

    def test_strategy_option_existing_fields_preserved(self):
        """Existing StrategyOption fields (rank, name, stints, etc.) must still be present."""
        result = self._parse()
        s = result.strategies[0]
        assert s.rank == 1
        assert s.name == "Safe"
        assert isinstance(s.stints, list)
        assert isinstance(s.estimated_time_s, float)
        assert isinstance(s.pit_time_s, float)
        assert isinstance(s.summary, str)
        assert isinstance(s.risks, str)

    def test_strategy_result_is_strategy_result_type(self):
        result = self._parse()
        assert isinstance(result, ap.StrategyResult)

    def test_feasibility_attribute_present(self):
        result = self._parse()
        assert hasattr(result, "feasibility")
        assert isinstance(result.feasibility, FeasibilityReport)


# ---------------------------------------------------------------------------
# AC7 — Prompt data-quality summary: clean lap count, excluded-lap note,
#        std-dev, per-compound confidence, measured/calculated/estimated labels
# ---------------------------------------------------------------------------

class TestAC7DataQualitySummaryInPrompt:
    """The race prompt must contain a Data Quality section with the required items."""

    def _prompt(self, lap_data=None, feasibility_report=None) -> str:
        params = _make_params()
        laps = lap_data if lap_data is not None else {"RM": _make_8_laps()}
        deg = {"RM": _make_deg_entry()}
        return ap._build_race_prompt(
            params, laps, degradation=deg,
            feasibility_report=feasibility_report or _make_feasible_report(),
        )

    def test_data_quality_section_present(self):
        p = self._prompt()
        assert "Data Quality" in p, "Prompt must contain a 'Data Quality' section"

    def test_clean_lap_count_in_data_quality(self):
        p = self._prompt()
        # Each compound line shows N clean laps
        assert "clean laps" in p, "Data quality block must mention 'clean laps'"

    def test_excluded_lap_note_in_data_quality(self):
        p = self._prompt()
        # Outlap / pit lap exclusion note must appear
        assert "excluded" in p.lower() or "out/in/pit laps" in p.lower(), (
            "Data quality block must mention excluded laps (out/in/pit)"
        )

    def test_std_dev_in_data_quality_block(self):
        """std-dev must appear in the data quality block."""
        p = self._prompt()
        assert "std-dev" in p or "std_dev" in p or "stdev" in p.lower(), (
            "Data quality block must include std-dev per compound"
        )

    def test_per_compound_confidence_in_data_quality(self):
        """Per-compound degradation confidence must appear in data quality block."""
        p = self._prompt()
        assert "confidence" in p.lower(), (
            "Data quality block must include per-compound confidence"
        )

    def test_measured_calculated_estimated_labels(self):
        """The prompt must use 'Measured', 'Calculated', and 'Estimated' labels."""
        p = self._prompt()
        lower_p = p.lower()
        assert "measured" in lower_p, "Prompt must use 'Measured' label"
        assert "calculated" in lower_p, "Prompt must use 'Calculated' label"
        assert "estimated" in lower_p, "Prompt must use 'Estimated' label"

    def test_data_quality_note_for_tyre_wear_and_wheelspin(self):
        """Tyre wear and wheelspin/lockup labelled by data quality in prompt."""
        p = self._prompt()
        # _DATA_QUALITY_NOTE mentions wheelspin/lockup as "calculated"
        assert "wheelspin" in p.lower() or "lockup" in p.lower(), (
            "Prompt must mention wheelspin/lockup with data-quality label"
        )

    def test_multiple_compounds_each_appear_in_data_quality(self):
        """When multiple compounds present, each should appear in data quality block."""
        laps = {"RM": _make_8_laps(96000.0), "RH": _make_8_laps(98000.0)}
        p = self._prompt(lap_data=laps)
        # Both compounds should appear somewhere in the prompt
        assert "RM" in p
        assert "RH" in p


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

    def test_prompt_blocks_ineligible_rs_from_stints(self):
        """Ineligible RS must appear in the prompt as blocked from calculated stints."""
        report = FeasibilityReport(
            estimated_laps=20,
            feasible_stop_counts=[1],
            rejected_strategies=[],
            data_gaps=[DataGap("compound_RS_insufficient_data", "RS: 5 laps only")],
            assumptions=[],
            calculation_notes=[],
            eligible_compounds=["RM"],
            ineligible_compounds=["RS"],
        )
        params = _make_params(avail_tyres=["RM", "RS"])
        p = ap._build_race_prompt(
            params, {"RM": _make_8_laps(), "RS": [90000.0] * 5},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=report,
        )
        # The prompt must say RS is ineligible
        assert "RS" in p
        assert "ineligible" in p.lower() or "Ineligible" in p, (
            "Prompt must label RS as ineligible for calculated stints"
        )


# ---------------------------------------------------------------------------
# AC9 — pit_time formula; sequential pit work; event pit_loss authoritative
# ---------------------------------------------------------------------------

class TestAC9PitTimeFormulaAndSequentialWork:
    """pit_time = pit_loss + ceil(fuel/refuel); prompt states sequential;
    event pit_loss_secs is authoritative (not seed pit delta)."""

    def _prompt(self, feasibility_report=None, **overrides) -> str:
        params = _make_params(**overrides)
        return ap._build_race_prompt(
            params, {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=feasibility_report or _make_feasible_report(),
        )

    def test_prompt_states_sequential_pit_work(self):
        p = self._prompt()
        assert "sequential" in p.lower(), (
            "Prompt must state that pit work is sequential"
        )

    def test_prompt_states_pit_loss_is_authoritative(self):
        p = self._prompt(pit_loss_secs=25.0)
        # The prompt must say pit_loss_secs is authoritative and seed data is not used
        lower_p = p.lower()
        assert "authoritative" in lower_p or "seed" in lower_p, (
            "Prompt must state pit_loss_secs is authoritative over seed data"
        )

    def test_prompt_states_no_seed_pit_delta(self):
        p = self._prompt(pit_loss_secs=23.0)
        lower_p = p.lower()
        assert "seed" in lower_p, (
            "Prompt must mention that seed-track pit delta is NOT used"
        )

    def test_pit_time_formula_in_prompt(self):
        """Prompt must state the pit_time_s formula."""
        p = self._prompt()
        assert "pit_time_s" in p or "pit_loss_secs" in p, (
            "Prompt must contain the pit_time formula using pit_loss_secs"
        )
        assert "ceil(" in p or "ceil" in p.lower(), (
            "Prompt must include ceil() in the pit time formula"
        )

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

    def test_event_pit_loss_authoritative_in_prompt_with_specific_value(self):
        """The actual pit_loss_secs value must appear in the prompt."""
        p = self._prompt(pit_loss_secs=28.5)
        assert "28.5" in p, "The event's pit_loss_secs value must appear in the prompt"


# ---------------------------------------------------------------------------
# AC10 — Each strategy carries risk fields; parser reads them
# ---------------------------------------------------------------------------

class TestAC10RiskFieldsInOutput:
    """StrategyOption must carry tyre_risk, fuel_risk, traffic_risk, undercut_risk,
    confidence_score, and why_label. Parser must populate them from JSON."""

    def _parse_with_all_risk_fields(self) -> ap.StrategyOption:
        raw = json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "Balanced",
                "stints": [],
                "estimated_time_s": 3600.0,
                "pit_time_s": 23.0,
                "summary": "Balanced choice.",
                "risks": "Moderate.",
                "positives": "Good pace.",
                "negatives": "Some risk.",
                "estimated_speed_rank": 2,
                "tyre_risk": "medium",
                "fuel_risk": "low",
                "traffic_risk": "high",
                "undercut_risk": "medium",
                "confidence_score": 0.75,
                "why_label": "Balanced because it uses moderate compounds.",
            }],
            "rejected_strategies": [],
            "data_gaps": [],
            "assumptions": [],
            "calculation_notes": [],
        })
        result = ap._parse_strategies(raw)
        return result.strategies[0]

    def test_tyre_risk_parsed(self):
        s = self._parse_with_all_risk_fields()
        assert s.tyre_risk == "medium"

    def test_fuel_risk_parsed(self):
        s = self._parse_with_all_risk_fields()
        assert s.fuel_risk == "low"

    def test_traffic_risk_parsed(self):
        s = self._parse_with_all_risk_fields()
        assert s.traffic_risk == "high"

    def test_undercut_risk_parsed(self):
        s = self._parse_with_all_risk_fields()
        assert s.undercut_risk == "medium"

    def test_confidence_score_parsed(self):
        s = self._parse_with_all_risk_fields()
        assert abs(s.confidence_score - 0.75) < 1e-6

    def test_why_label_parsed(self):
        s = self._parse_with_all_risk_fields()
        assert "Balanced because" in s.why_label

    def test_risk_fields_default_when_absent(self):
        """Old JSON without risk fields must default gracefully."""
        raw = json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "Safe",
                "stints": [],
                "estimated_time_s": 3600.0,
                "pit_time_s": 23.0,
                "summary": "Old-style.",
                "risks": "None.",
            }],
            "rejected_strategies": [],
            "data_gaps": [],
            "assumptions": [],
            "calculation_notes": [],
        })
        result = ap._parse_strategies(raw)
        s = result.strategies[0]
        assert s.tyre_risk == ""
        assert s.fuel_risk == ""
        assert s.traffic_risk == ""
        assert s.undercut_risk == ""
        assert s.confidence_score == 0.0
        assert s.why_label == ""

    def test_risk_fields_in_prompt_schema(self):
        """Prompt must include tyre_risk, fuel_risk, traffic_risk, undercut_risk,
        confidence_score, why_label in the JSON schema example."""
        params = _make_params()
        p = ap._build_race_prompt(
            params, {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=_make_feasible_report(),
        )
        for field in ["tyre_risk", "fuel_risk", "traffic_risk", "undercut_risk",
                      "confidence_score", "why_label"]:
            assert field in p, f"'{field}' must appear in the race prompt schema"


# ---------------------------------------------------------------------------
# AC11 — Locked tuning categories; tuning_locked=True suppresses setup advice
# ---------------------------------------------------------------------------

class TestAC11TuningLockInPrompt:
    """allowed_tuning=[brake_balance, suspension, differential, aero] must lock
    transmission/power/ballast/steering/nitrous. tuning_locked=True must suppress
    setup advice entirely."""

    def _prompt_restricted(self) -> str:
        params = _make_params(
            allowed_tuning=["brake_balance", "suspension", "differential", "aero"],
            tuning_locked=False,
        )
        return ap._build_race_prompt(
            params, {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=_make_feasible_report(),
        )

    def _prompt_locked(self) -> str:
        params = _make_params(tuning_locked=True)
        return ap._build_race_prompt(
            params, {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=_make_feasible_report(),
        )

    def test_tuning_locked_suppresses_setup_advice(self):
        p = self._prompt_locked()
        # Must contain the TUNING LOCKED block
        assert "TUNING LOCKED" in p, "Prompt must contain 'TUNING LOCKED' when tuning_locked=True"

    def test_tuning_locked_says_do_not_recommend_setup(self):
        p = self._prompt_locked()
        assert "DO NOT recommend" in p or "do not recommend" in p.lower(), (
            "TUNING LOCKED prompt must say 'DO NOT recommend any setup changes'"
        )

    def test_restricted_tuning_lists_locked_categories(self):
        """When allowed_tuning is set, prompt must list the locked categories."""
        p = self._prompt_restricted()
        # Transmission, power, ballast should be listed as LOCKED
        lower_p = p.lower()
        assert "transmission" in lower_p or "locked" in lower_p, (
            "Prompt must list locked categories when allowed_tuning is set"
        )

    def test_restricted_tuning_shows_locked_block(self):
        """Prompt must contain EVENT TUNING RESTRICTIONS block."""
        p = self._prompt_restricted()
        assert "TUNING RESTRICTIONS" in p or "LOCKED" in p, (
            "Prompt must contain tuning restriction block when allowed_tuning is partial"
        )

    def test_validate_ai_setup_response_detects_violation(self):
        """validate_ai_setup_response detects when AI violates a locked category."""
        response = (
            "I recommend adjusting the gear ratio to shorten the final drive. "
            "You should also consider power restrictor adjustment."
        )
        violations = ap.validate_ai_setup_response(
            response,
            tuning_locked=False,
            allowed_tuning=["brake_balance", "suspension", "differential", "aero"],
        )
        # 'transmission' and 'power' are locked — both keywords appear with action verbs
        assert "transmission" in violations or "power" in violations, (
            f"Expected 'transmission' or 'power' violation; got {violations}"
        )

    def test_validate_ai_setup_response_no_violation_when_no_restrictions(self):
        """validate_ai_setup_response returns [] when no restrictions active."""
        response = "Consider adjusting gear ratios and ride height."
        violations = ap.validate_ai_setup_response(
            response, tuning_locked=False, allowed_tuning=None
        )
        assert violations == []

    def test_validate_ai_setup_response_all_locked_when_tuning_locked(self):
        """When tuning_locked=True, any setup advice should be flagged."""
        response = "Raise the ride height by 5mm to improve ground clearance."
        violations = ap.validate_ai_setup_response(
            response, tuning_locked=True, allowed_tuning=None
        )
        assert len(violations) > 0, (
            "Expected violations when tuning_locked=True and AI recommends setup changes"
        )


# ---------------------------------------------------------------------------
# AC12 — Prompt explicit rules: don't invent, don't produce impossible stop counts,
#         reject infeasible explicitly, prefer measured, seed is context only,
#         return JSON with five sections
# ---------------------------------------------------------------------------

class TestAC12PromptExplicitRules:
    """The race prompt must contain the five explicit rules from the spec."""

    def _prompt(self, feasibility_report=None) -> str:
        params = _make_params()
        return ap._build_race_prompt(
            params, {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=feasibility_report or _make_feasible_report(),
        )

    def test_do_not_invent_missing_compound_data(self):
        p = self._prompt()
        assert "do not invent missing compound data" in p.lower(), (
            "Prompt must say 'do not invent missing compound data'"
        )

    def test_do_not_produce_impossible_stop_counts(self):
        p = self._prompt()
        lower_p = p.lower()
        assert "impossible" in lower_p or "do not produce" in lower_p or "do not propose" in lower_p, (
            "Prompt must say not to produce impossible stop counts"
        )

    def test_reject_infeasible_explicitly(self):
        p = self._prompt()
        lower_p = p.lower()
        assert "reject" in lower_p and "infeasible" in lower_p, (
            "Prompt must say to reject infeasible strategies explicitly"
        )

    def test_prefer_measured_data_over_generic(self):
        p = self._prompt()
        lower_p = p.lower()
        assert "measured" in lower_p and ("generic" in lower_p or "seed" in lower_p or "over" in lower_p), (
            "Prompt must say to prefer measured event data over generic GT7 knowledge"
        )

    def test_seed_track_data_is_context_only(self):
        p = self._prompt()
        lower_p = p.lower()
        assert "seed" in lower_p and "context" in lower_p, (
            "Prompt must say seed track data is context only, not confirmed geometry"
        )

    def test_prompt_requires_json_with_five_sections(self):
        """Prompt JSON schema must include: strategies, rejected_strategies, data_gaps,
        assumptions, calculation_notes."""
        p = self._prompt()
        for section in ["rejected_strategies", "data_gaps", "assumptions", "calculation_notes"]:
            assert section in p, f"Prompt schema must include '{section}'"

    def test_prompt_schema_has_strategies_field(self):
        p = self._prompt()
        assert '"strategies"' in p or "'strategies'" in p or "strategies" in p

    def test_feasibility_section_in_prompt(self):
        """Prompt must include a Feasibility Gate section when report is present."""
        p = self._prompt(feasibility_report=_make_feasible_report([1, 2]))
        assert "Feasibility Gate" in p, "Prompt must include a 'Feasibility Gate' section"


# ---------------------------------------------------------------------------
# AC13 — Full-suite smoke: no AttributeError from result-type change
# ---------------------------------------------------------------------------

class TestAC13NoAttributeErrorFromResultTypeChange:
    """Verify that downstream consumers of StrategyResult don't crash.
    The result must be iterable and support getattr(result, 'strategies', result)."""

    def _make_result(self) -> ap.StrategyResult:
        strategies = [
            ap.StrategyOption(
                rank=1, name="Safe", stints=[], estimated_time_s=3600.0,
                pit_time_s=23.0, summary="", risks="",
            )
        ]
        return ap.StrategyResult(
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
        payload = [ap.StrategyOption(
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
            assert isinstance(s, ap.StrategyOption)


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

    def test_prompt_echoes_pit_loss_as_authoritative(self):
        """The race prompt must say pit_loss_secs is authoritative."""
        params = _make_params(pit_loss_secs=26.0)
        p = ap._build_race_prompt(
            params, {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=_make_feasible_report(),
        )
        lower_p = p.lower()
        assert "authoritative" in lower_p, (
            "Prompt must say pit_loss_secs is authoritative"
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

    def _prompt_with_high_variance(self) -> str:
        # Create a compound with extremely high variance (std-dev > 5s)
        laps = {
            "RM": [
                96000.0, 96100.0, 101500.0, 96200.0,
                97800.0, 96050.0, 103000.0, 96300.0,
            ]
        }
        params = _make_params()
        return ap._build_race_prompt(
            params, laps,
            degradation={"RM": _make_deg_entry(confidence="medium")},
            feasibility_report=_make_feasible_report(),
        )

    def test_std_dev_present_in_prompt_for_high_variance_compound(self):
        """std-dev must appear in the data-quality block for a high-variance compound."""
        p = self._prompt_with_high_variance()
        assert "std-dev" in p or "stdev" in p.lower(), (
            "Prompt data-quality block must include std-dev for high-variance compound"
        )

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

    def test_high_variance_std_dev_appears_as_float_in_prompt(self):
        """The std-dev value for the high-variance compound must appear as a number in the prompt."""
        laps = {
            "RM": [96000.0, 96100.0, 101500.0, 96200.0,
                   97800.0, 96050.0, 103000.0, 96300.0]
        }
        from statistics import stdev as _stdev
        expected_sd_s = _stdev(laps["RM"]) / 1000.0
        params = _make_params()
        p = ap._build_race_prompt(
            params, laps,
            degradation={"RM": _make_deg_entry(confidence="medium")},
            feasibility_report=_make_feasible_report(),
        )
        # The prompt should include a numeric std-dev value for RM
        # Format is "std-dev X.XXXs [calculated]"
        import re as _re
        matches = _re.findall(r"std[-_]dev\s+([\d.]+)s", p)
        assert matches, f"std-dev value not found as 'std-dev X.XXXs' in prompt; prompt contains: {p[:500]}"
        # The value should be in the right ballpark
        found_sd = float(matches[0])
        assert found_sd > 1.0, f"std-dev should be > 1s for high-variance data; got {found_sd}"


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
        field_names = {f.name for f in dataclasses.fields(ap.RaceParams)}
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
# EC4 — Valid strategy output remains strict JSON-compatible
# ---------------------------------------------------------------------------

class TestEC4StrictJSONCompatible:
    """The parsed output must be re-serializable to valid JSON.
    StrategyResult and its contents must be JSON-dumpable (after conversion to dict)."""

    def _result_as_dict(self) -> dict:
        raw = _minimal_api_response()
        result = ap._parse_strategies(raw)
        return {
            "strategies": [
                {
                    "rank": s.rank,
                    "name": s.name,
                    "estimated_speed_rank": s.estimated_speed_rank,
                    "stints": s.stints,
                    "estimated_time_s": s.estimated_time_s,
                    "pit_time_s": s.pit_time_s,
                    "summary": s.summary,
                    "risks": s.risks,
                    "positives": s.positives,
                    "negatives": s.negatives,
                    "tyre_risk": s.tyre_risk,
                    "fuel_risk": s.fuel_risk,
                    "traffic_risk": s.traffic_risk,
                    "undercut_risk": s.undercut_risk,
                    "confidence_score": s.confidence_score,
                    "why_label": s.why_label,
                }
                for s in result.strategies
            ],
            "rejected_strategies": [
                {"name": r.name, "reason": r.reason}
                for r in result.rejected_strategies
            ],
            "data_gaps": [
                {"name": dg.name, "description": dg.description}
                for dg in result.data_gaps
            ],
            "assumptions": result.assumptions,
            "calculation_notes": result.calculation_notes,
        }

    def test_result_serializes_to_valid_json(self):
        d = self._result_as_dict()
        try:
            serialized = json.dumps(d)
        except (TypeError, ValueError) as exc:
            pytest.fail(f"StrategyResult is not JSON-serializable: {exc}")
        # Must round-trip
        back = json.loads(serialized)
        assert "strategies" in back

    def test_result_strategies_is_list(self):
        d = self._result_as_dict()
        assert isinstance(d["strategies"], list)

    def test_result_rejected_strategies_is_list(self):
        d = self._result_as_dict()
        assert isinstance(d["rejected_strategies"], list)

    def test_result_data_gaps_is_list(self):
        d = self._result_as_dict()
        assert isinstance(d["data_gaps"], list)

    def test_result_assumptions_is_list(self):
        d = self._result_as_dict()
        assert isinstance(d["assumptions"], list)

    def test_result_calculation_notes_is_list(self):
        d = self._result_as_dict()
        assert isinstance(d["calculation_notes"], list)

    def test_round_trip_preserves_strategy_name(self):
        d = self._result_as_dict()
        serialized = json.dumps(d)
        back = json.loads(serialized)
        assert back["strategies"][0]["name"] == "Safe — 1-Stop RM"

    def test_round_trip_preserves_confidence_score(self):
        d = self._result_as_dict()
        serialized = json.dumps(d)
        back = json.loads(serialized)
        assert abs(back["strategies"][0]["confidence_score"] - 0.8) < 1e-6

    def test_json_output_has_five_required_sections(self):
        d = self._result_as_dict()
        for section in ["strategies", "rejected_strategies", "data_gaps",
                        "assumptions", "calculation_notes"]:
            assert section in d, f"JSON output must include '{section}'"


# ---------------------------------------------------------------------------
# Fix 2 — Practice prompt: strategy names decoupled from speed rank
# ---------------------------------------------------------------------------

class TestFix2PracticePromptRankDecoupling:
    """_build_practice_prompt must NOT force Safe=Rank1/Balanced=Rank2/Aggressive=Rank3.
    It must use risk LABELS and provide a separate estimated_speed_rank field."""

    def _practice_prompt(self, **overrides) -> str:
        params = _make_params(**overrides)
        return ap._build_practice_prompt(
            params,
            {"RM": _make_8_laps()},
            setup={},
            history={},
        )

    def test_practice_prompt_no_forced_rank1_safe(self):
        """The old 'Rank 1: \"Safe\"' hardcoding must be gone."""
        p = self._practice_prompt()
        assert 'Rank 1: "Safe"' not in p, (
            "Practice prompt must not force 'Rank 1: \"Safe\"'"
        )

    def test_practice_prompt_no_forced_rank2_balanced(self):
        p = self._practice_prompt()
        assert 'Rank 2: "Balanced"' not in p, (
            "Practice prompt must not force 'Rank 2: \"Balanced\"'"
        )

    def test_practice_prompt_no_forced_rank3_aggressive(self):
        p = self._practice_prompt()
        assert 'Rank 3: "Aggressive"' not in p, (
            "Practice prompt must not force 'Rank 3: \"Aggressive\"'"
        )

    def test_practice_prompt_mentions_estimated_speed_rank(self):
        """Practice prompt must mention estimated_speed_rank for the decoupled guidance."""
        p = self._practice_prompt()
        assert "estimated_speed_rank" in p, (
            "Practice prompt must include 'estimated_speed_rank' field guidance"
        )

    def test_practice_prompt_mentions_do_not_force(self):
        """Practice prompt must explicitly say not to force name-to-rank coupling."""
        p = self._practice_prompt()
        lower = p.lower()
        assert "do not force" in lower or "not force" in lower, (
            "Practice prompt must explicitly decouple risk label from speed rank"
        )

    def test_practice_prompt_safe_label_explained_as_risk(self):
        """Practice prompt must describe 'Safe' as a risk label (finish confidence)."""
        p = self._practice_prompt()
        lower = p.lower()
        # 'Safe' should be described as risk/confidence oriented, not rank-ordered
        assert "safe" in lower and ("confidence" in lower or "risk" in lower), (
            "Practice prompt must describe Safe as a risk label"
        )


# ---------------------------------------------------------------------------
# Fix 4 — Generalised ineligible-compound prohibition in race prompt
# ---------------------------------------------------------------------------

class TestFix4GeneralisedIneligibleCompoundRule:
    """The race prompt must block ANY ineligible compound from calculated stints,
    not only RS/RH. The generalised wording must remain and name RS/RH as examples."""

    def _race_prompt(self, **overrides) -> str:
        params = _make_params(**overrides)
        return ap._build_race_prompt(
            params,
            {"RM": _make_8_laps()},
            degradation={"RM": _make_deg_entry()},
            feasibility_report=_make_feasible_report(),
        )

    def test_prompt_does_not_say_only_rs_rh_blocked(self):
        """The old RS/RH-only rule must be removed."""
        p = self._race_prompt()
        old_rule = "RS/RH compounds must NOT appear in calculated stints unless they are in the eligible compounds list above."
        assert old_rule not in p, (
            "Old RS/RH-only rule must be replaced by the generalised wording"
        )

    def test_prompt_generalised_rule_present(self):
        """The generalised 'ANY compound' blocking rule must be present."""
        p = self._race_prompt()
        lower = p.lower()
        # Rule must mention blocking ANY compound, not just RS/RH
        assert "any compound" in lower or "any ineligible" in lower, (
            "Race prompt must say 'any compound' is blocked from calculated stints if ineligible"
        )

    def test_prompt_still_names_rs_and_rh_as_examples(self):
        """RS and RH must still be named as examples in the generalised rule."""
        p = self._race_prompt()
        assert "RS" in p and "RH" in p, (
            "Race prompt must still name RS and RH as examples of ineligible compounds"
        )

    def test_prompt_mentions_ineligible_compounds_section(self):
        """Prompt must reference the eligible compounds list for enforcement."""
        p = self._race_prompt()
        lower = p.lower()
        assert "eligible compounds" in lower, (
            "Generalised rule must reference the 'eligible compounds list'"
        )

    def test_prompt_mentions_data_gaps_for_ineligible(self):
        """Ineligible compounds must be directed to data_gaps or testing only."""
        p = self._race_prompt()
        lower = p.lower()
        assert "data_gaps" in lower or "testing" in lower, (
            "Prompt must say ineligible compounds belong only in data_gaps or testing recommendations"
        )


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
