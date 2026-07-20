"""Phase 49 — tyre, fuel and strategy maturation tests (task items 18-21)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.preparation_evidence import (
    PracticeEvidenceSample, EvidenceCompatibility as C, EvidenceDomain as Dom,
    build_cumulative_evidence,
)
from strategy.strategy_maturity import (
    StrategyMaturity as M, ModelMaturity as Mm, StrategyEvidenceReadiness,
    assess_strategy_maturity, build_strategy_maturity,
)


def _s(sid, atype, **kw):
    return PracticeEvidenceSample(session_id=sid, activity_id="a" + sid, activity_type=atype, **kw)


def test_strategy_starts_with_no_evidence():
    assert assess_strategy_maturity(StrategyEvidenceReadiness()) == M.NO_EVIDENCE


def test_strategy_progresses_through_states():
    early = StrategyEvidenceReadiness(has_lap_consistency=True)  # no rep pace yet
    assert assess_strategy_maturity(early) == M.EARLY_MODEL
    partial = StrategyEvidenceReadiness(has_representative_race_pace=True)
    assert assess_strategy_maturity(partial) == M.PARTIAL
    developing = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                           has_fuel_use=True)
    assert assess_strategy_maturity(developing) == M.DEVELOPING


def test_strategy_validation_required_then_finalisation_ready():
    pre = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                    has_fuel_use=True, has_tyre_degradation=True)
    assert assess_strategy_maturity(pre) == M.VALIDATION_REQUIRED
    validated = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                          has_fuel_use=True, has_tyre_degradation=True,
                                          validated_long_run=True, race_duration_known=True,
                                          multipliers_known=True)
    assert assess_strategy_maturity(validated) == M.FINALISATION_READY


def test_provisional_when_duration_or_multipliers_unknown():
    r = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                  has_fuel_use=True, has_tyre_degradation=True, validated_long_run=True,
                                  race_duration_known=True, multipliers_known=False)
    assert assess_strategy_maturity(r) == M.PROVISIONAL


def test_dependency_change_forces_replan():
    r = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                  has_fuel_use=True, has_tyre_degradation=True, validated_long_run=True,
                                  race_duration_known=True, multipliers_known=True,
                                  dependency_changed=True)
    assert assess_strategy_maturity(r) == M.REPLAN_REQUIRED


def test_finalised_stays_finalised_without_dependency_change():
    r = StrategyEvidenceReadiness(is_finalised=True)
    assert assess_strategy_maturity(r) == M.FINALISED


def test_tyre_fuel_maturity_reads_evidence_domains():
    # 4 exact long runs -> mature tyre; fuel unknown-multiplier -> capped
    samples = [_s(f"r{i}", T.LONG_RACE_RUN, valid_laps=14,
                  domain_overrides={Dom.FUEL_MODEL: C.UNKNOWN}) for i in range(4)]
    evidence = build_cumulative_evidence(samples)
    r = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                  has_tyre_degradation=True)
    summary = build_strategy_maturity(evidence, r)
    assert summary.tyre_fuel.tyre == Mm.MATURE
    assert summary.tyre_fuel.fuel == Mm.CAPPED
    assert "tyre/fuel multipliers" in summary.missing_evidence


def test_maturity_summary_fingerprint_deterministic():
    evidence = build_cumulative_evidence([_s("r1", T.LONG_RACE_RUN)])
    r = StrategyEvidenceReadiness(has_representative_race_pace=True)
    a = build_strategy_maturity(evidence, r)
    b = build_strategy_maturity(evidence, r)
    assert a.fingerprint == b.fingerprint
