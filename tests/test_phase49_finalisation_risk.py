"""Phase 49 — strategy finalisation & deadline-aware risk tests (task items 26, 27)."""
from __future__ import annotations

from strategy.strategy_maturity import StrategyMaturity as M
from strategy.strategy_finalisation import (
    StrategyPlan, build_strategy_finalisation, assess_deadline_risk, RiskPosture as RP,
)


def test_strategy_not_finalised_without_confirmation():
    d = build_strategy_finalisation(M.FINALISATION_READY, confirmed=False)
    assert d.finalised is False
    assert "acknowledgement required" in d.reason


def test_strategy_finalised_when_ready_and_confirmed():
    d = build_strategy_finalisation(M.FINALISATION_READY, confirmed=True,
                                    primary=StrategyPlan("2-stop", confidence="high"))
    assert d.finalised is True
    assert d.primary.label == "2-stop"


def test_cannot_finalise_immature_without_low_confidence_acceptance():
    d = build_strategy_finalisation(M.DEVELOPING, confirmed=True,
                                    evidence_still_missing=("validated long run",))
    assert d.finalised is False
    assert "without required evidence" in d.reason
    assert "validated long run" in d.evidence_still_missing


def test_low_confidence_acceptance_finalises_with_visible_assumptions():
    d = build_strategy_finalisation(M.PROVISIONAL, confirmed=True, low_confidence_accepted=True,
                                    evidence_still_missing=("tyre/fuel multipliers",))
    assert d.finalised is True
    assert d.low_confidence_accepted is True
    assert "tyre/fuel multipliers" in d.evidence_still_missing  # still visible


def test_finalisation_fingerprint_deterministic():
    a = build_strategy_finalisation(M.FINALISATION_READY, confirmed=True,
                                    primary=StrategyPlan("1-stop"))
    b = build_strategy_finalisation(M.FINALISATION_READY, confirmed=True,
                                    primary=StrategyPlan("1-stop"))
    assert a.fingerprint == b.fingerprint


# --- deadline-aware risk ---------------------------------------------------

def test_high_interaction_experiment_blocked_near_race():
    r = assess_deadline_risk(2, high_interaction_experiment=True)
    assert r.posture == RP.BLOCK_UNLESS_OVERRIDDEN
    assert r.allow_experiment is False
    assert "override" in r.warning.lower()


def test_high_interaction_experiment_allowed_with_explicit_override():
    r = assess_deadline_risk(2, high_interaction_experiment=True, explicitly_overridden=True)
    assert r.allow_experiment is True
    assert r.posture == RP.PROTECT_BEST_KNOWN
    assert "override" in r.warning.lower()


def test_near_race_prefers_protection_for_low_risk_confirmation():
    r = assess_deadline_risk(1, high_interaction_experiment=False)
    assert r.posture == RP.PROTECT_BEST_KNOWN
    assert r.allow_experiment is True  # a low-risk confirmation is fine


def test_race_week_prefers_confirmation():
    r = assess_deadline_risk(5, high_interaction_experiment=False)
    assert r.posture == RP.PREFER_CONFIRMATION


def test_early_preparation_allows_exploration():
    r = assess_deadline_risk(20, high_interaction_experiment=True)
    assert r.posture == RP.EXPLORATORY_OK
    assert r.allow_experiment is True


def test_unknown_countdown_defaults_to_exploratory():
    r = assess_deadline_risk(None, high_interaction_experiment=True)
    assert r.posture == RP.EXPLORATORY_OK
