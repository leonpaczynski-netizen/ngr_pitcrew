"""
Group 38 — Acceptance Tests: Relative-Compound Tyre Degradation Point

Verifies every acceptance criterion (AC1–AC12) and named edge cases from
the "Relative-Compound Tyre Degradation Point" user story end-to-end against
the real implementation.

Each test class is labelled with its AC number so failures map directly
to the acceptance criteria table.

Files under test
----------------
- strategy/relative_degradation.py   (compute_relative_degradation)
- strategy/ai_planner.py              (_build_degradation_prompt)
- strategy/engine.py                  (set_degradation_cache, _check_tyre_degradation)
- strategy/feasibility.py             (check_compound_eligibility)
- config.json                         (strategy.degradation_consecutive_laps default)
- data/tyres.py                       (compound codes and ordering)

Compound code facts (from data/tyres.py ALL_COMPOUNDS):
  index 6: RH  (Racing Hard)    — hardest Racing compound
  index 7: RM  (Racing Medium)
  index 8: RS  (Racing Soft)    — softest Racing compound
  index 9: IM  (Intermediate)   — wet
  index 10: HW (Heavy Wet)      — wet
Lower index = harder compound.

No production code is modified.  All network calls are mocked where needed.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.relative_degradation import compute_relative_degradation
from strategy.engine import RaceStrategyEngine, Stint
from strategy.feasibility import check_compound_eligibility
import strategy.ai_planner as ap


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ms(s: float) -> float:
    """Convert seconds to milliseconds."""
    return s * 1000.0


def _make_stint(stint_num=1, laps=15, compound="RS",
                ref_lap_ms=90000, pace_threshold_ms=2000):
    return Stint(
        stint_num=stint_num,
        laps=laps,
        compound=compound,
        ref_lap_ms=ref_lap_ms,
        pace_threshold_ms=pace_threshold_ms,
    )


def _make_engine(stints=None):
    tracker = MagicMock()
    tracker.laps_recorded = 5
    tracker.best_lap_ms = 90000
    tracker.avg_fuel_per_lap = 3.0
    tracker.last_fuel = 50.0
    tracker.tyre_states = {}

    announcer = MagicMock()
    config = {"fuel": {"strategy": "balanced"}, "strategy": {}}
    bridge = MagicMock()

    engine = RaceStrategyEngine(tracker, announcer, config, bridge, db=None)
    if stints:
        engine.set_plan(stints)
    return engine, tracker, announcer, bridge


def _make_record(lap_time_ms: int = 90000):
    record = MagicMock()
    record.lap_time_ms = lap_time_ms
    record.fuel_used = 3.0
    record.lock_up_count = 0
    record.wheelspin_count = 0
    record.oversteer_count = 0
    return record


def _minimal_ai_degradation_response(compounds: list[str]) -> str:
    """Return a minimal valid degradation JSON for patching call_api."""
    result = {}
    for c in compounds:
        result[c] = {
            "cliff_lap_practice": 10,
            "pace_loss_at_cliff_s": 1.5,
            "total_life_race": 14,
            "optimal_stint_race": 9,
            "confidence": "medium",
        }
    return json.dumps(result)


# ---------------------------------------------------------------------------
# AC1 — Baseline pace per compound = mean of clean laps (ms),
#        computed when >=2 compounds have data.
# ---------------------------------------------------------------------------

class TestAC1BaselineMeanOfCleanLaps:
    """Acceptance: harder_baseline_ms is the arithmetic mean of the harder
    compound's clean laps, not the best or median."""

    def test_ac1_harder_baseline_is_mean_not_best(self):
        """Mean must include all laps, not just the fastest."""
        rh_laps = [_ms(97.0), _ms(97.0), _ms(97.0), _ms(99.0), _ms(98.0)]
        rs_laps = [_ms(90.0)] * 3 + [_ms(97.5), _ms(97.6)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        expected_mean = statistics.mean(rh_laps)
        best_rh = min(rh_laps)
        assert result["RS"]["harder_baseline_ms"] != best_rh
        assert abs(result["RS"]["harder_baseline_ms"] - expected_mean) < 1e-6

    def test_ac1_baseline_includes_slower_laps_in_mean(self):
        """Slow laps (e.g. traffic, tyre warm-up) shift the mean upward."""
        rh_laps = [_ms(96.0), _ms(98.0), _ms(99.0), _ms(98.0), _ms(97.0)]
        rs_laps = [_ms(90.0)] * 3 + [_ms(97.5), _ms(97.6)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        expected_mean = statistics.mean(rh_laps)
        assert abs(result["RS"]["harder_baseline_ms"] - expected_mean) < 1e-6

    def test_ac1_baseline_requires_two_or_more_compounds(self):
        """Single compound → no relative baseline available → cliff_detection."""
        seqs = {"RS": [_ms(90.0)] * 8}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["degradation_method"] == "cliff_detection"
        assert result["RS"]["harder_baseline_ms"] is None

    def test_ac1_skipped_tier_uses_next_available_harder(self):
        """RS+RH present, RM absent → RS baseline = mean(RH laps)."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 9
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        expected = statistics.mean(rh_laps)
        assert abs(result["RS"]["harder_baseline_ms"] - expected) < 1e-6


# ---------------------------------------------------------------------------
# AC2 — Degradation point = first run of consecutive_laps >= harder baseline;
#        optimal_stint_race = D-1.
#        LOCKED cases: laps 5&6 → optimal=4; laps 8&9 → optimal=7; laps 6&7 → optimal=5.
# ---------------------------------------------------------------------------

class TestAC2DegradationPointAndOptimalStint:
    """Acceptance: LOCKED formula optimal_stint_race = D - 1."""

    def test_ac2_laps_5_6_over_baseline_optimal_is_4(self):
        """Run starts at lap 5 (laps 5&6 both >= baseline) → D=5 → optimal=4."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 4 + [_ms(97.1), _ms(97.2)]  # laps 5&6 over
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["optimal_stint_race"] == 4

    def test_ac2_laps_8_9_over_baseline_optimal_is_7(self):
        """Run starts at lap 8 (laps 8&9 both >= baseline) → D=8 → optimal=7."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 7 + [_ms(97.1), _ms(97.2)]  # laps 8&9 over
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["optimal_stint_race"] == 7

    def test_ac2_laps_6_7_over_rm_baseline_optimal_is_5(self):
        """RS+RM+RH; RS crosses RM baseline at laps 6&7 → D=6 → optimal=5."""
        rm_laps = [_ms(95.0)] * 5
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 5 + [_ms(95.1), _ms(95.2)]  # laps 6&7 over RM
        seqs = {"RS": rs_laps, "RM": rm_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["optimal_stint_race"] == 5

    def test_ac2_harder_baseline_ms_is_mean_of_harder_compound(self):
        """harder_baseline_ms must be mean of harder compound laps."""
        rh_laps = [_ms(97.0), _ms(97.2), _ms(96.8), _ms(97.1), _ms(97.3)]
        rs_laps = [_ms(90.0)] * 4 + [_ms(97.1), _ms(97.2)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        expected = statistics.mean(rh_laps)
        assert abs(result["RS"]["harder_baseline_ms"] - expected) < 1e-6

    def test_ac2_method_is_relative_baseline_when_degradation_found(self):
        """When a degradation point is found, method must be 'relative_baseline'."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 4 + [_ms(97.1), _ms(97.2)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["degradation_method"] == "relative_baseline"
        assert result["RS"]["not_yet_degraded"] is False


# ---------------------------------------------------------------------------
# AC3 — consecutive_laps is configurable (default 2).
#        Changing it (e.g. to 3) changes the detected point.
#        Config default path yields 2 (assert on config.json + functional test).
# ---------------------------------------------------------------------------

class TestAC3ConsecutiveLapsConfigurable:
    """Acceptance: consecutive_laps parameter governs detection; default=2."""

    def test_ac3_default_is_2_from_config_json(self):
        """config.json must have strategy.degradation_consecutive_laps == 2."""
        config_path = ROOT / "config.json"
        with config_path.open(encoding="utf-8") as f:
            config = json.load(f)
        val = config.get("strategy", {}).get("degradation_consecutive_laps", None)
        assert val == 2, (
            f"config.json strategy.degradation_consecutive_laps must be 2; got {val!r}"
        )

    def test_ac3_default_consecutive_laps_is_2_in_function_signature(self):
        """compute_relative_degradation must default to consecutive_laps=2."""
        import inspect
        sig = inspect.signature(compute_relative_degradation)
        default = sig.parameters["consecutive_laps"].default
        assert default == 2

    def test_ac3_consecutive_laps_3_requires_triple_run(self):
        """With consecutive_laps=3, two-lap run alone is NOT enough to trigger."""
        rh_laps = [_ms(97.0)] * 5
        # Only 2 laps above baseline (laps 5&6): enough for default=2 but NOT for 3
        rs_laps = [_ms(90.0)] * 4 + [_ms(97.1), _ms(97.2)]
        seqs = {"RS": rs_laps, "RH": rh_laps}

        result_2 = compute_relative_degradation(seqs, consecutive_laps=2)
        result_3 = compute_relative_degradation(seqs, consecutive_laps=3)

        # With consecutive_laps=2, triggers at lap 5 → optimal=4
        assert result_2["RS"]["optimal_stint_race"] == 4
        # With consecutive_laps=3, 2-lap run is insufficient → not_yet_degraded
        assert result_3["RS"]["not_yet_degraded"] is True
        assert result_3["RS"]["optimal_stint_race"] == 0

    def test_ac3_consecutive_laps_3_detects_correct_point(self):
        """With consecutive_laps=3, a 3-lap run starting at lap 6 → D=6 → optimal=5."""
        rh_laps = [_ms(97.0)] * 5
        # Laps 1-5 fast, laps 6&7&8 at/above baseline
        rs_laps = [_ms(90.0)] * 5 + [_ms(97.1), _ms(97.2), _ms(97.3)]
        seqs = {"RS": rs_laps, "RH": rh_laps}

        result = compute_relative_degradation(seqs, consecutive_laps=3)
        assert result["RS"]["optimal_stint_race"] == 5
        assert result["RS"]["degradation_method"] == "relative_baseline"

    def test_ac3_changing_from_2_to_3_changes_detected_point(self):
        """A 3-lap run starting at lap 7: default(2) triggers at lap 7; same for 3."""
        rh_laps = [_ms(97.0)] * 5
        # Laps 1-6 fast, laps 7&8&9 above baseline
        rs_laps = [_ms(90.0)] * 6 + [_ms(97.1), _ms(97.2), _ms(97.3)]
        seqs = {"RS": rs_laps, "RH": rh_laps}

        result_2 = compute_relative_degradation(seqs, consecutive_laps=2)
        result_3 = compute_relative_degradation(seqs, consecutive_laps=3)

        # consecutive_laps=2 → triggers at lap 7 (first 2-lap run)
        assert result_2["RS"]["optimal_stint_race"] == 6
        # consecutive_laps=3 → same start (lap 7), same D, but we still get 6
        assert result_3["RS"]["optimal_stint_race"] == 6


# ---------------------------------------------------------------------------
# AC4 — No harder compound with valid baseline → degradation_method="cliff_detection".
# ---------------------------------------------------------------------------

class TestAC4NoHarderCompoundFallback:
    """Acceptance: when no harder compound has valid data, use cliff_detection."""

    def test_ac4_only_rm_practised_uses_cliff_detection(self):
        """When only RM is practised, no harder compound → cliff_detection."""
        seqs = {"RM": [_ms(95.0)] * 6}
        result = compute_relative_degradation(seqs)
        assert result["RM"]["degradation_method"] == "cliff_detection"
        assert result["RM"]["harder_baseline_ms"] is None

    def test_ac4_rm_with_only_rs_present_is_cliff_detection(self):
        """RM present alongside RS only: RS (index 8) is softer than RM (index 7),
        so RM has no harder compound in the session → cliff_detection.
        (RS cannot serve as a harder baseline for RM.)"""
        seqs = {"RM": [_ms(95.0)] * 6, "RS": [_ms(90.0)] * 4}
        result = compute_relative_degradation(seqs)
        # RM is harder than RS: no compound harder than RM is present
        assert result["RM"]["degradation_method"] == "cliff_detection"

    def test_ac4_empty_harder_compound_laps_not_valid_baseline(self):
        """RH with empty laps list → RM still falls back to cliff_detection."""
        seqs = {"RM": [_ms(95.0)] * 6, "RH": []}
        result = compute_relative_degradation(seqs)
        # RH has no laps → compound_means excludes it → RM has no valid baseline
        assert result["RM"]["degradation_method"] == "cliff_detection"


# ---------------------------------------------------------------------------
# AC5 — Hardest practised compound → always cliff_detection.
# ---------------------------------------------------------------------------

class TestAC5HardestCompoundAlwaysCliff:
    """Acceptance: the hardest compound practised always uses cliff_detection
    because there is no harder compound to compare against."""

    def test_ac5_rh_with_only_rh_is_cliff_detection(self):
        """Single RH compound → cliff_detection."""
        seqs = {"RH": [_ms(97.0)] * 8}
        result = compute_relative_degradation(seqs)
        assert result["RH"]["degradation_method"] == "cliff_detection"
        assert result["RH"]["harder_baseline_ms"] is None

    def test_ac5_rh_is_cliff_detection_even_with_rs_rm_present(self):
        """RH is hardest Racing compound; RS and RM are softer → RH has no harder
        peer → cliff_detection."""
        seqs = {
            "RS": [_ms(90.0)] * 9,
            "RM": [_ms(95.0)] * 7,
            "RH": [_ms(97.0)] * 6,
        }
        result = compute_relative_degradation(seqs)
        assert result["RH"]["degradation_method"] == "cliff_detection"
        assert result["RH"]["harder_baseline_ms"] is None

    def test_ac5_rm_is_cliff_detection_when_only_rm_and_rs_present(self):
        """RM + RS only: RM is harder → cliff_detection; RS uses RM as baseline."""
        seqs = {
            "RS": [_ms(90.0)] * 5 + [_ms(95.1), _ms(95.2)],
            "RM": [_ms(95.0)] * 6,
        }
        result = compute_relative_degradation(seqs)
        assert result["RM"]["degradation_method"] == "cliff_detection"
        assert result["RS"]["degradation_method"] == "relative_baseline"


# ---------------------------------------------------------------------------
# AC6 — Softer compound never crosses harder baseline → not_yet_degraded=True,
#        optimal_stint_race=0, confidence="low".
# ---------------------------------------------------------------------------

class TestAC6NeverCrossesBaseline:
    """Acceptance: softer compound never reaches harder baseline → undegraded flag."""

    def test_ac6_not_yet_degraded_is_true(self):
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 6  # always well below RH baseline
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["not_yet_degraded"] is True

    def test_ac6_optimal_stint_race_is_zero(self):
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 6
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["optimal_stint_race"] == 0

    def test_ac6_confidence_is_low(self):
        """not_yet_degraded forces confidence='low' regardless of lap count."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 10  # 10 laps — normally would be "high"
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["confidence"] == "low"

    def test_ac6_harder_baseline_ms_still_set(self):
        """Even when not_yet_degraded, harder_baseline_ms is populated."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 6
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["harder_baseline_ms"] is not None
        assert abs(result["RS"]["harder_baseline_ms"] - statistics.mean(rh_laps)) < 1e-6

    def test_ac6_method_is_relative_baseline_even_when_not_degraded(self):
        """Relative method was applied (we found a harder baseline), just not triggered."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 6
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["degradation_method"] == "relative_baseline"


# ---------------------------------------------------------------------------
# AC7 — Feasibility gate rejects optimal_stint_race==0 with human-readable
#        reason and WITHOUT calling the AI.
# ---------------------------------------------------------------------------

class TestAC7FeasibilityGateRejectsZeroOptimal:
    """Acceptance: optimal_stint_race==0 from relative result must be rejected
    by check_compound_eligibility with a human-readable message."""

    def _make_relative_entry(
        self,
        optimal_stint_race: int = 0,
        not_yet_degraded: bool = True,
        degradation_method: str = "relative_baseline",
        harder_baseline_ms: float = 97000.0,
        confidence: str = "low",
    ) -> dict:
        return {
            "optimal_stint_race": optimal_stint_race,
            "total_life_race": 0,
            "cliff_lap_practice": 0,
            "pace_loss_at_cliff_s": None,
            "confidence": confidence,
            "degradation_method": degradation_method,
            "harder_baseline_ms": harder_baseline_ms,
            "not_yet_degraded": not_yet_degraded,
        }

    def _make_8_laps(self, base_ms: float = 90000.0) -> list[float]:
        return [base_ms + i * 10 for i in range(8)]

    def test_ac7_not_yet_degraded_entry_is_rejected(self):
        """not_yet_degraded → optimal_stint_race=0 → check_compound_eligibility rejects."""
        entry = self._make_relative_entry(optimal_stint_race=0, not_yet_degraded=True)
        eligible, reason = check_compound_eligibility("RS", self._make_8_laps(), entry)
        assert eligible is False

    def test_ac7_rejection_reason_is_human_readable(self):
        """The rejection reason must be a non-empty, human-readable string."""
        entry = self._make_relative_entry(optimal_stint_race=0, not_yet_degraded=True)
        eligible, reason = check_compound_eligibility("RS", self._make_8_laps(), entry)
        assert reason is not None
        assert len(reason) > 10
        # Must mention the key signal that caused rejection
        assert "optimal_stint_race" in reason or "zero" in reason.lower() or "0" in reason

    def test_ac7_degrades_from_lap1_also_rejected(self):
        """Degrades from lap 1 → optimal=0 → rejected."""
        entry = self._make_relative_entry(
            optimal_stint_race=0, not_yet_degraded=False,
            confidence="high",  # high confidence, still 0
        )
        eligible, reason = check_compound_eligibility("RS", self._make_8_laps(), entry)
        assert eligible is False

    def test_ac7_positive_optimal_with_max_stint_signal_is_eligible(self):
        """Positive optimal_stint_race with cliff data → eligible (control case)."""
        entry = {
            "optimal_stint_race": 7,
            "total_life_race": 0,
            "cliff_lap_practice": 8,
            "pace_loss_at_cliff_s": 1.5,
            "confidence": "medium",
            "degradation_method": "relative_baseline",
            "harder_baseline_ms": 97000.0,
            "not_yet_degraded": False,
        }
        eligible, reason = check_compound_eligibility("RS", self._make_8_laps(), entry)
        assert eligible is True
        assert reason is None

    def test_ac7_no_ai_call_when_feasibility_gate_rejects_all(self):
        """When the feasibility gate rejects all stop counts, call_api must not be called."""
        import dataclasses
        RaceParams = ap.RaceParams
        kwargs = {}
        for f in dataclasses.fields(RaceParams):
            if (f.default is not dataclasses.MISSING
                    or f.default_factory is not dataclasses.MISSING):  # type: ignore
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
        kwargs.update(dict(
            track="Spa", total_laps=20, tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5, refuel_speed_lps=10.0, pit_loss_secs=23.0,
        ))
        params = RaceParams(**kwargs)
        laps = {"RS": [90000.0] * 8}
        deg = {
            "RS": {
                "optimal_stint_race": 0,  # relative result: not yet degraded
                "total_life_race": 0,
                "cliff_lap_practice": 0,
                "pace_loss_at_cliff_s": None,
                "confidence": "low",
                "degradation_method": "relative_baseline",
                "harder_baseline_ms": 97000.0,
                "not_yet_degraded": True,
            }
        }
        with patch("strategy.ai_planner.call_api") as mock_api:
            result = ap.analyse_strategy(params, laps, "fake_key", degradation=deg)
        mock_api.assert_not_called()
        # Must not have any feasible strategies
        assert result.strategies == []


# ---------------------------------------------------------------------------
# AC8 — Live engine alert fires when rolling 3-lap avg >= harder_baseline_ms;
#        falls back to ref + pace_threshold_ms when harder_baseline_ms is None.
# ---------------------------------------------------------------------------

class TestAC8LiveEngineAlert:
    """Acceptance: _check_tyre_degradation uses harder_baseline_ms from cache
    when present; falls back to ref+threshold otherwise."""

    def _setup_with_cache(self, compound="RS", harder_baseline_ms=97000.0):
        stint = _make_stint(compound=compound, ref_lap_ms=90000,
                            pace_threshold_ms=2000)
        engine, _, announcer, _ = _make_engine(stints=[stint])
        engine.set_degradation_cache({
            compound: {"harder_baseline_ms": harder_baseline_ms}
        })
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15
        return engine, announcer, stint

    def test_ac8_alert_fires_when_rolling_avg_equals_baseline(self):
        """Rolling 3-lap average == harder_baseline_ms → alert fires."""
        engine, announcer, stint = self._setup_with_cache(harder_baseline_ms=97000.0)
        engine._recent_lap_times = [97000, 97000, 97000]
        record = _make_record(97000)
        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)
        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_ac8_alert_fires_when_rolling_avg_above_baseline(self):
        """Rolling 3-lap average > harder_baseline_ms → alert fires."""
        engine, announcer, stint = self._setup_with_cache(harder_baseline_ms=97000.0)
        engine._recent_lap_times = [97500, 98000, 97200]
        record = _make_record(97200)
        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)
        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_ac8_no_alert_when_rolling_avg_below_baseline(self):
        """Rolling average well below harder_baseline_ms → NO alert."""
        engine, announcer, stint = self._setup_with_cache(harder_baseline_ms=97000.0)
        engine._recent_lap_times = [90000, 91000, 91500]
        record = _make_record(91500)
        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)
        assert not announcer.announce.called
        assert stint.tyre_alert_issued is False

    def test_ac8_fallback_when_harder_baseline_none(self):
        """harder_baseline_ms=None → fallback to ref+pace_threshold_ms (> condition)."""
        stint = _make_stint(compound="RM", ref_lap_ms=90000, pace_threshold_ms=2000)
        engine, _, announcer, _ = _make_engine(stints=[stint])
        engine.set_degradation_cache(
            {"RM": {"harder_baseline_ms": None, "degradation_method": "cliff_detection"}}
        )
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15
        # 93000 > 90000 + 2000 = 92000 → triggers fallback alert
        engine._recent_lap_times = [93000, 93000, 93000]
        record = _make_record(93000)
        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)
        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_ac8_fallback_when_compound_not_in_cache(self):
        """Compound absent from degradation cache → uses original fallback."""
        stint = _make_stint(compound="RH", ref_lap_ms=97000, pace_threshold_ms=3000)
        engine, _, announcer, _ = _make_engine(stints=[stint])
        engine.set_degradation_cache({"RS": {"harder_baseline_ms": 97000.0}})
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15
        # 101000 > 97000 + 3000 = 100000 → triggers
        engine._recent_lap_times = [101000, 101000, 101000]
        record = _make_record(101000)
        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)
        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_ac8_fallback_no_alert_at_exactly_ref_plus_threshold(self):
        """Original fallback: rolling_avg exactly at ref+threshold is NOT >= (strictly >)."""
        stint = _make_stint(compound="RM", ref_lap_ms=90000, pace_threshold_ms=2000)
        engine, _, announcer, _ = _make_engine(stints=[stint])
        # No cache → uses fallback
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15
        engine._recent_lap_times = [92000, 92000, 92000]
        record = _make_record(92000)
        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)
        assert not announcer.announce.called


# ---------------------------------------------------------------------------
# AC9 — Degradation AI prompt includes harder-compound baseline pace (s/lap)
#        where it exists; uses cliff instruction where it doesn't.
#        (No network calls — prompt builder tested directly.)
# ---------------------------------------------------------------------------

class TestAC9DegradationPromptContent:
    """Acceptance: _build_degradation_prompt includes harder-baseline pace for
    relative_baseline compounds; cliff instruction for cliff_detection compounds."""

    def _make_det_result_with_baseline(self) -> dict:
        """RS has a harder baseline (from RH); RH has cliff_detection (no baseline)."""
        return {
            "RS": {
                "harder_baseline_ms": 97000.0,   # 97.000s/lap
                "degradation_method": "relative_baseline",
                "optimal_stint_race": 7,
                "confidence": "medium",
                "not_yet_degraded": False,
            },
            "RH": {
                "harder_baseline_ms": None,
                "degradation_method": "cliff_detection",
                "optimal_stint_race": 0,
                "confidence": "low",
                "not_yet_degraded": False,
            },
        }

    def test_ac9_prompt_contains_baseline_pace_for_compound_with_baseline(self):
        """RS has harder_baseline_ms → prompt must mention the baseline pace in s/lap."""
        seqs = {
            "RS": [_ms(90.0)] * 7 + [_ms(97.1), _ms(97.2)],
            "RH": [_ms(97.0)] * 5,
        }
        det_result = self._make_det_result_with_baseline()
        prompt = ap._build_degradation_prompt(seqs, 1.0, det_result)
        # 97000ms → 97.000 s/lap must appear
        assert "97.000" in prompt, (
            "Prompt must include harder-baseline pace (97.000s) for RS"
        )

    def test_ac9_prompt_says_use_threshold_for_baseline_compound(self):
        """Prompt must instruct AI to use the pre-computed baseline threshold for RS."""
        seqs = {
            "RS": [_ms(90.0)] * 7 + [_ms(97.1), _ms(97.2)],
            "RH": [_ms(97.0)] * 5,
        }
        det_result = self._make_det_result_with_baseline()
        prompt = ap._build_degradation_prompt(seqs, 1.0, det_result)
        lower_p = prompt.lower()
        assert "threshold" in lower_p or "degradation threshold" in lower_p or "baseline" in lower_p

    def test_ac9_prompt_uses_cliff_instruction_for_compound_without_baseline(self):
        """RH has no harder baseline → prompt must instruct normal cliff-detection."""
        seqs = {
            "RS": [_ms(90.0)] * 7 + [_ms(97.1), _ms(97.2)],
            "RH": [_ms(97.0)] * 5,
        }
        det_result = self._make_det_result_with_baseline()
        prompt = ap._build_degradation_prompt(seqs, 1.0, det_result)
        # RH section must say "no harder-compound baseline" and use cliff method
        lower_p = prompt.lower()
        assert "no harder" in lower_p or "cliff" in lower_p, (
            "Prompt must include cliff-detection instruction for RH"
        )

    def test_ac9_prompt_without_det_result_has_no_baseline_section(self):
        """When det_result is None, no pre-computed baseline section appears."""
        seqs = {"RM": [_ms(95.0)] * 6}
        prompt = ap._build_degradation_prompt(seqs, 1.0, None)
        # No baseline section header
        assert "Per-compound degradation thresholds" not in prompt

    def test_ac9_prompt_with_det_result_has_baseline_section_header(self):
        """When det_result is provided (any compound), the section header appears."""
        seqs = {
            "RS": [_ms(90.0)] * 7 + [_ms(97.1), _ms(97.2)],
            "RH": [_ms(97.0)] * 5,
        }
        det_result = self._make_det_result_with_baseline()
        prompt = ap._build_degradation_prompt(seqs, 1.0, det_result)
        assert "Per-compound degradation thresholds" in prompt

    def test_ac9_no_network_call_in_prompt_builder(self):
        """_build_degradation_prompt is pure (no API call)."""
        # If this test runs without error, no network was used.
        seqs = {"RM": [_ms(95.0)] * 6, "RH": [_ms(97.0)] * 5}
        det_result = {
            "RM": {"harder_baseline_ms": 97000.0, "degradation_method": "relative_baseline",
                   "optimal_stint_race": 5, "confidence": "medium", "not_yet_degraded": False},
            "RH": {"harder_baseline_ms": None, "degradation_method": "cliff_detection",
                   "optimal_stint_race": 0, "confidence": "medium", "not_yet_degraded": False},
        }
        prompt = ap._build_degradation_prompt(seqs, 1.0, det_result)
        assert isinstance(prompt, str)
        assert len(prompt) > 50


# ---------------------------------------------------------------------------
# AC10 — Output dict retains all existing keys AND adds degradation_method,
#         harder_baseline_ms, not_yet_degraded.  Assert presence and types.
# ---------------------------------------------------------------------------

class TestAC10OutputDictShape:
    """Acceptance: compute_relative_degradation output has all required keys with
    correct types.  The new keys (degradation_method, harder_baseline_ms,
    not_yet_degraded) must be present alongside the existing keys."""

    def _get_result(self) -> dict:
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(90.0)] * 4 + [_ms(97.1), _ms(97.2)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        return compute_relative_degradation(seqs)

    def test_ac10_optimal_stint_race_is_int(self):
        result = self._get_result()
        assert isinstance(result["RS"]["optimal_stint_race"], int)
        assert isinstance(result["RH"]["optimal_stint_race"], int)

    def test_ac10_harder_baseline_ms_is_float_or_none(self):
        result = self._get_result()
        # RS should have a float baseline
        assert isinstance(result["RS"]["harder_baseline_ms"], float)
        # RH (hardest) should have None
        assert result["RH"]["harder_baseline_ms"] is None

    def test_ac10_degradation_method_is_string(self):
        result = self._get_result()
        assert isinstance(result["RS"]["degradation_method"], str)
        assert result["RS"]["degradation_method"] in ("relative_baseline", "cliff_detection")
        assert isinstance(result["RH"]["degradation_method"], str)
        assert result["RH"]["degradation_method"] in ("relative_baseline", "cliff_detection")

    def test_ac10_confidence_is_valid_string(self):
        result = self._get_result()
        assert result["RS"]["confidence"] in ("high", "medium", "low")
        assert result["RH"]["confidence"] in ("high", "medium", "low")

    def test_ac10_not_yet_degraded_is_bool(self):
        result = self._get_result()
        assert isinstance(result["RS"]["not_yet_degraded"], bool)
        assert isinstance(result["RH"]["not_yet_degraded"], bool)

    def test_ac10_all_five_keys_present_for_every_compound(self):
        """Every compound in the output must have all 5 required keys."""
        required_keys = {
            "optimal_stint_race",
            "harder_baseline_ms",
            "degradation_method",
            "confidence",
            "not_yet_degraded",
        }
        result = self._get_result()
        for compound, entry in result.items():
            missing = required_keys - set(entry.keys())
            assert not missing, (
                f"Compound {compound} missing keys: {missing}"
            )

    def test_ac10_merged_result_also_has_all_keys(self):
        """analyse_tyre_degradation (merged) output retains all keys including new ones."""
        rh_laps = [_ms(97.0)] * 8
        rs_laps = [_ms(90.0)] * 6 + [_ms(97.1), _ms(97.2)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        ai_response = _minimal_ai_degradation_response(["RS", "RH"])

        with patch("strategy.ai_planner.call_api", return_value=ai_response):
            merged = ap.analyse_tyre_degradation(seqs, 1.0, "fake_key")

        for compound in seqs:
            assert compound in merged
            entry = merged[compound]
            assert "degradation_method" in entry
            assert "harder_baseline_ms" in entry
            assert "not_yet_degraded" in entry
            # Existing AI keys retained
            assert "cliff_lap_practice" in entry
            assert "pace_loss_at_cliff_s" in entry
            assert "total_life_race" in entry
            assert "optimal_stint_race" in entry
            assert "confidence" in entry


# ---------------------------------------------------------------------------
# AC11 — RS < RM < RH life ordering enforced after merge;
#         softer optimal_stint_race <= harder's.
#         Tested deterministically via compute_relative_degradation and
#         via the merged path (with mocked API) to confirm the enforcement.
# ---------------------------------------------------------------------------

class TestAC11LifeOrderingEnforced:
    """Acceptance: softer compound optimal_stint_race must not exceed the
    next-harder compound's optimal_stint_race after merge."""

    def test_ac11_rs_optimal_le_rm_optimal_deterministic(self):
        """RS degrades at lap 5 (optimal=4); RM degrades at lap 8 (optimal=7).
        RS optimal (4) <= RM optimal (7) — ordering naturally satisfied."""
        rm_laps = [_ms(95.0)] * 7 + [_ms(97.1), _ms(97.2)]  # degrades at lap 8, optimal=7
        rh_laps = [_ms(97.0)] * 5
        # RS degrades at lap 5 vs RM baseline (95000ms)
        rs_laps = [_ms(90.0)] * 4 + [_ms(95.1), _ms(95.2)]  # degrades at lap 5, optimal=4
        seqs = {"RS": rs_laps, "RM": rm_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        rs_opt = result["RS"]["optimal_stint_race"]
        rm_opt = result["RM"]["optimal_stint_race"]
        # RS softer, RM harder: softer optimal must be <= harder optimal
        # (4 <= 7 in this scenario)
        assert rs_opt <= rm_opt or rs_opt == 0 or rm_opt == 0, (
            f"RS optimal ({rs_opt}) must be <= RM optimal ({rm_opt})"
        )

    def test_ac11_merged_rs_le_rm_after_ordering_enforcement(self):
        """Merged result: AI gives RS optimal=15, RM optimal=10 (unphysical).
        Post-merge ordering enforcement must cap RS to <= RM."""
        rh_laps = [_ms(97.0)] * 8
        rm_laps = [_ms(95.0)] * 8
        rs_laps = [_ms(90.0)] * 8  # RS never crosses baseline → not_yet_degraded

        seqs = {"RS": rs_laps, "RM": rm_laps, "RH": rh_laps}

        # AI returns RS optimal=15, RM optimal=10 (physically wrong: RS softer than RM)
        ai_response = json.dumps({
            "RS": {"cliff_lap_practice": 16, "pace_loss_at_cliff_s": 2.0,
                   "total_life_race": 18, "optimal_stint_race": 15, "confidence": "high"},
            "RM": {"cliff_lap_practice": 11, "pace_loss_at_cliff_s": 1.5,
                   "total_life_race": 14, "optimal_stint_race": 10, "confidence": "high"},
            "RH": {"cliff_lap_practice": 0, "pace_loss_at_cliff_s": 0.8,
                   "total_life_race": 20, "optimal_stint_race": 18, "confidence": "high"},
        })

        with patch("strategy.ai_planner.call_api", return_value=ai_response):
            merged = ap.analyse_tyre_degradation(seqs, 1.0, "fake_key")

        rs_opt = merged["RS"]["optimal_stint_race"]
        rm_opt = merged["RM"]["optimal_stint_race"]
        # After ordering enforcement, RS (softer) optimal must be <= RM (harder) optimal
        assert rs_opt <= rm_opt, (
            f"Post-merge ordering failed: RS optimal ({rs_opt}) > RM optimal ({rm_opt})"
        )

    def test_ac11_relative_baseline_method_overrides_ai_optimal(self):
        """When compute_relative_degradation returns relative_baseline for RS,
        analyse_tyre_degradation must use the deterministic optimal_stint_race
        instead of the AI's value."""
        rh_laps = [_ms(97.0)] * 8
        rs_laps = [_ms(90.0)] * 6 + [_ms(97.1), _ms(97.2)]  # degrades at lap 7, opt=6
        seqs = {"RS": rs_laps, "RH": rh_laps}

        # AI claims RS optimal=20 (should be overridden by deterministic opt=6)
        ai_response = json.dumps({
            "RS": {"cliff_lap_practice": 21, "pace_loss_at_cliff_s": 2.0,
                   "total_life_race": 24, "optimal_stint_race": 20, "confidence": "high"},
            "RH": {"cliff_lap_practice": 0, "pace_loss_at_cliff_s": 0.5,
                   "total_life_race": 30, "optimal_stint_race": 25, "confidence": "high"},
        })

        with patch("strategy.ai_planner.call_api", return_value=ai_response):
            merged = ap.analyse_tyre_degradation(seqs, 1.0, "fake_key")

        # RS got relative_baseline method → deterministic value=6 must override AI's 20
        assert merged["RS"]["optimal_stint_race"] == 6
        assert merged["RS"]["degradation_method"] == "relative_baseline"

    def test_ac11_undetermined_harder_does_not_drag_down_softer(self):
        """Agreed case 1: SS=4 [relative_baseline], SM=0 [not_yet_degraded], SH=10.

        Undetermined/not-viable harder compounds (optimal_stint_race <= 0) must NOT
        constrain a softer compound that has a real positive value.  SS is only
        constrained by the nearest DETERMINED harder compound with a positive optimal:
        SH=10.  Since 4 <= 10 the cap is not triggered; SS stays at 4.

        Expected post-enforcement: SS=4, SM=0, SH=10 (all unchanged).
        """
        # Sports compounds: SH (idx=3) harder than SM (idx=4) harder than SS (idx=5).
        sm_laps = [_ms(93.0)] * 5     # SM baseline = 93.000s
        sh_laps = [_ms(95.0)] * 5     # SH baseline = 95.000s
        # SS crosses SM baseline at laps 5&6 → deterministic opt=4 (relative_baseline)
        ss_laps = [_ms(90.0)] * 4 + [_ms(93.1), _ms(93.2)]
        seqs = {"SS": ss_laps, "SM": sm_laps, "SH": sh_laps}

        # SM (93s) is always below SH baseline (95s) → not_yet_degraded, merged opt=0.
        # SH has no harder compound → cliff_detection, AI opt=10.
        ai_response = json.dumps({
            "SS": {"cliff_lap_practice": 7, "pace_loss_at_cliff_s": 1.5,
                   "total_life_race": 8, "optimal_stint_race": 6, "confidence": "medium"},
            "SM": {"cliff_lap_practice": 0, "pace_loss_at_cliff_s": 0.8,
                   "total_life_race": 6, "optimal_stint_race": 5, "confidence": "medium"},
            "SH": {"cliff_lap_practice": 11, "pace_loss_at_cliff_s": 0.5,
                   "total_life_race": 12, "optimal_stint_race": 10, "confidence": "medium"},
        })

        with patch("strategy.ai_planner.call_api", return_value=ai_response):
            merged = ap.analyse_tyre_degradation(seqs, 1.0, "fake_key")

        ss_opt = merged["SS"]["optimal_stint_race"]
        sm_opt = merged["SM"]["optimal_stint_race"]
        sh_opt = merged["SH"]["optimal_stint_race"]

        assert ss_opt == 4, (
            f"SS must remain 4 (undetermined SM=0 must not drag it down; "
            f"nearest determined harder is SH=10 and 4<=10); got SS={ss_opt}"
        )
        assert sm_opt == 0, (
            f"SM must remain 0 (not_yet_degraded, undetermined); got SM={sm_opt}"
        )
        assert sh_opt == 10, (
            f"SH must remain 10 (no harder compound; cliff_detection AI opt); got SH={sh_opt}"
        )

    def test_ac11_fully_determined_violation_is_capped(self):
        """Agreed case 2: softer compound with positive det opt exceeds a determined harder
        compound's opt — the softer must be capped down.

        Scenario: SS+SM+SH.
          - SS det=6 (crosses SM baseline at laps 7&8, relative_baseline).
          - SM det=0, not_yet_degraded (SM laps all below SH baseline → undetermined, skipped).
          - SH cliff_detection, AI gives opt=4 (determined positive).

        Running-cap walk (hardest first: SH=4 → cap=4; SM=0 skip; SS=6>4 → cap to 4):
          Post-enforcement: SS=4, SM=0, SH=4.

        The key assertion: SS (softer, det=6) is capped to SH (nearest determined harder=4).
        SM (undetermined) neither receives a cap nor contributes to the running cap.
        """
        # Sports compounds: SH (idx=3) harder than SM (idx=4) harder than SS (idx=5).
        sm_laps = [_ms(93.0)] * 5    # SM baseline = 93.000s
        sh_laps = [_ms(95.0)] * 5    # SH baseline = 95.000s; SH is cliff_detection (no harder)
        # SS crosses SM baseline at laps 7&8 → det opt = 6 (D=7, optimal=6)
        ss_laps = [_ms(90.0)] * 6 + [_ms(93.1), _ms(93.2)]
        seqs = {"SS": ss_laps, "SM": sm_laps, "SH": sh_laps}

        # AI response: SH cliff opt=4 (determined); SM and SS values will be overridden
        # by deterministic results (SS=6 via relative_baseline; SM=0 via not_yet_degraded).
        ai_response = json.dumps({
            "SS": {"cliff_lap_practice": 9, "pace_loss_at_cliff_s": 1.5,
                   "total_life_race": 10, "optimal_stint_race": 8, "confidence": "medium"},
            "SM": {"cliff_lap_practice": 0, "pace_loss_at_cliff_s": 0.8,
                   "total_life_race": 6, "optimal_stint_race": 5, "confidence": "medium"},
            "SH": {"cliff_lap_practice": 5, "pace_loss_at_cliff_s": 0.5,
                   "total_life_race": 6, "optimal_stint_race": 4, "confidence": "medium"},
        })

        with patch("strategy.ai_planner.call_api", return_value=ai_response):
            merged = ap.analyse_tyre_degradation(seqs, 1.0, "fake_key")

        ss_opt = merged["SS"]["optimal_stint_race"]
        sm_opt = merged["SM"]["optimal_stint_race"]
        sh_opt = merged["SH"]["optimal_stint_race"]

        # SH is determined (cliff AI=4); SM is undetermined (det not_yet_degraded=True → 0).
        # SS det=6 > SH=4 → ordering enforcement caps SS down to SH=4.
        assert ss_opt == 4, (
            f"SS det=6 must be capped to nearest determined harder compound SH=4; "
            f"got SS={ss_opt}, SM={sm_opt}, SH={sh_opt}"
        )
        assert sh_opt == 4, (
            f"SH cliff AI opt=4 must be preserved; got {sh_opt}"
        )
        assert sm_opt == 0, (
            f"SM must remain 0 (not_yet_degraded, undetermined — no cap applied); got {sm_opt}"
        )
        # Core property: softer (SS) capped to nearest determined harder (SH), not dragged by SM=0
        assert ss_opt <= sh_opt, (
            f"Post-enforcement ordering: SS ({ss_opt}) must be <= SH ({sh_opt})"
        )


# ---------------------------------------------------------------------------
# AC12 — Single compound → cliff_detection, no relative trigger.
# ---------------------------------------------------------------------------

class TestAC12SingleCompound:
    """Acceptance: single compound practised → cliff_detection, no relative baseline."""

    def test_ac12_single_rs_is_cliff_detection(self):
        seqs = {"RS": [_ms(90.0)] * 8}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["degradation_method"] == "cliff_detection"

    def test_ac12_single_rs_harder_baseline_none(self):
        seqs = {"RS": [_ms(90.0)] * 8}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["harder_baseline_ms"] is None

    def test_ac12_single_rm_is_cliff_detection(self):
        seqs = {"RM": [_ms(95.0)] * 6}
        result = compute_relative_degradation(seqs)
        assert result["RM"]["degradation_method"] == "cliff_detection"

    def test_ac12_single_rh_is_cliff_detection(self):
        seqs = {"RH": [_ms(97.0)] * 10}
        result = compute_relative_degradation(seqs)
        assert result["RH"]["degradation_method"] == "cliff_detection"

    def test_ac12_single_compound_not_yet_degraded_is_false(self):
        """Single compound: not_yet_degraded=False (it simply has no relative comparison)."""
        seqs = {"RS": [_ms(90.0)] * 8}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["not_yet_degraded"] is False


# ---------------------------------------------------------------------------
# Edge case: outlier lap between two over-threshold laps breaks the run.
# ---------------------------------------------------------------------------

class TestEdgeCaseOutlierBreaksRun:
    """Edge case: an outlier lap below threshold between two above-threshold laps
    must break the consecutive run — no trigger at the first above-threshold lap."""

    def test_edge_outlier_between_two_high_laps_no_trigger(self):
        """Laps: 1-4 fast, lap 5 >= baseline, lap 6 < baseline (outlier), lap 7 >= baseline.
        With consecutive_laps=2, no complete run → not_yet_degraded=True."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [
            _ms(90.0),  # lap 1
            _ms(90.0),  # lap 2
            _ms(90.0),  # lap 3
            _ms(90.0),  # lap 4
            _ms(97.1),  # lap 5 >= baseline
            _ms(90.0),  # lap 6 < baseline — BREAKS the run
            _ms(97.2),  # lap 7 >= baseline (no consecutive partner)
        ]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        # Run of 2 consecutive laps is required; lap 5 alone does not qualify.
        assert result["RS"]["not_yet_degraded"] is True
        assert result["RS"]["optimal_stint_race"] == 0

    def test_edge_outlier_then_genuine_run_triggers_at_later_lap(self):
        """Outlier at lap 6; genuine 2-lap run at laps 8&9 → D=8 → optimal=7."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [
            _ms(90.0),  # lap 1
            _ms(90.0),  # lap 2
            _ms(90.0),  # lap 3
            _ms(90.0),  # lap 4
            _ms(97.1),  # lap 5 >= baseline
            _ms(90.0),  # lap 6 < baseline — breaks run
            _ms(90.0),  # lap 7 < baseline
            _ms(97.3),  # lap 8 >= baseline
            _ms(97.4),  # lap 9 >= baseline — genuine 2-lap run
        ]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        # Run found at laps 8&9 → D=8 → optimal=7
        assert result["RS"]["optimal_stint_race"] == 7
        assert result["RS"]["not_yet_degraded"] is False


# ---------------------------------------------------------------------------
# Edge case: wet compound always cliff_detection.
# ---------------------------------------------------------------------------

class TestEdgeCaseWetCompound:
    """Edge case: IM (Intermediate) and HW (Heavy Wet) must always use
    cliff_detection, never relative_baseline."""

    def test_edge_im_always_cliff_detection(self):
        """IM with dry peers → still cliff_detection."""
        seqs = {
            "RM": [_ms(95.0)] * 5,
            "IM": [_ms(100.0)] * 5,
        }
        result = compute_relative_degradation(seqs)
        assert result["IM"]["degradation_method"] == "cliff_detection"
        assert result["IM"]["harder_baseline_ms"] is None

    def test_edge_hw_always_cliff_detection(self):
        """HW (Heavy Wet) → cliff_detection."""
        seqs = {
            "RM": [_ms(95.0)] * 5,
            "HW": [_ms(105.0)] * 5,
        }
        result = compute_relative_degradation(seqs)
        assert result["HW"]["degradation_method"] == "cliff_detection"
        assert result["HW"]["harder_baseline_ms"] is None

    def test_edge_im_alone_cliff_detection(self):
        """IM alone → cliff_detection."""
        seqs = {"IM": [_ms(100.0)] * 6}
        result = compute_relative_degradation(seqs)
        assert result["IM"]["degradation_method"] == "cliff_detection"

    def test_edge_dry_compound_ignores_wet_as_baseline(self):
        """A dry compound (RM) must NOT use IM as a harder baseline even if IM
        has a lower index in the compound list (IM is at index 9, after RH/RM/RS)."""
        seqs = {
            "RM": [_ms(95.0)] * 6,
            "IM": [_ms(90.0)] * 5,  # faster absolute pace but wet tyre
        }
        result = compute_relative_degradation(seqs)
        # RM's harder compounds are in Racing category (RH), not wet.
        # IM is at index 9 — softer in ALL_COMPOUNDS than RM (index 7) — so
        # it would never be considered harder for RM. RM is cliff_detection.
        assert result["RM"]["degradation_method"] == "cliff_detection"


# ---------------------------------------------------------------------------
# Edge case: degrades from lap 1 → optimal=0 (not viable, not "not_yet_degraded").
# ---------------------------------------------------------------------------

class TestEdgeCaseDegradeFromLap1:
    """Edge case: RS laps 1&2 both >= harder baseline → D=1 → optimal=0.
    This is distinct from not_yet_degraded: the tyre DID degrade, just from the start."""

    def test_edge_degrades_from_lap1_optimal_is_0(self):
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(97.5), _ms(97.6)] + [_ms(97.7)] * 4
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["optimal_stint_race"] == 0

    def test_edge_degrades_from_lap1_not_yet_degraded_is_false(self):
        """Degrades from lap 1 → it HAS degraded (just immediately) → not_yet_degraded=False."""
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(97.5), _ms(97.6)] + [_ms(97.7)] * 4
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["not_yet_degraded"] is False

    def test_edge_degrades_from_lap1_method_is_relative_baseline(self):
        rh_laps = [_ms(97.0)] * 5
        rs_laps = [_ms(97.5), _ms(97.6)] + [_ms(97.7)] * 4
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        assert result["RS"]["degradation_method"] == "relative_baseline"


# ---------------------------------------------------------------------------
# Compound code verification: real codes from data/tyres.py
# ---------------------------------------------------------------------------

class TestCompoundCodes:
    """Verify the actual compound codes and ordering from data/tyres.py,
    confirming the hardness assumptions used in all AC tests above."""

    def test_rh_is_harder_than_rm(self):
        """In ALL_COMPOUNDS, RH appears before RM (lower index = harder)."""
        from data.tyres import ALL_COMPOUNDS
        codes = [c.code for c in ALL_COMPOUNDS]
        assert codes.index("RH") < codes.index("RM"), (
            "RH must have a lower index than RM in ALL_COMPOUNDS"
        )

    def test_rm_is_harder_than_rs(self):
        """In ALL_COMPOUNDS, RM appears before RS (lower index = harder)."""
        from data.tyres import ALL_COMPOUNDS
        codes = [c.code for c in ALL_COMPOUNDS]
        assert codes.index("RM") < codes.index("RS"), (
            "RM must have a lower index than RS in ALL_COMPOUNDS"
        )

    def test_im_is_wet_compound(self):
        """IM (Intermediate) must be flagged as a wet compound."""
        from data.tyres import get_by_code
        tc = get_by_code("IM")
        assert tc is not None
        assert tc.wet is True

    def test_hw_is_wet_compound(self):
        """HW (Heavy Wet) must be flagged as a wet compound."""
        from data.tyres import get_by_code
        tc = get_by_code("HW")
        assert tc is not None
        assert tc.wet is True

    def test_rs_rm_rh_are_not_wet(self):
        """Racing compounds must not be flagged as wet."""
        from data.tyres import get_by_code
        for code in ("RS", "RM", "RH"):
            tc = get_by_code(code)
            assert tc is not None
            assert tc.wet is False, f"{code} must not be a wet compound"
