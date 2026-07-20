"""Engineering-Brain Phase 6 — priority, conflict, clustering, planning (pure)."""
from __future__ import annotations

from pathlib import Path

import pytest

from strategy.engineering_issue import (
    ResidualIssue, EngineeringIssueIdentity, IssueFamily, ResidualState, IssueRelevance)
from strategy.engineering_state import build_engineering_state, ValidLapSummary
from strategy.experiment_planning import (
    prioritise_issues, detect_conflicts, cluster_issues, build_development_plan,
    ConflictType, PlanStatus, QueueState, ActionKind,
    TIER_NEW_REGRESSION, TIER_DAMAGED_GOOD, TIER_PERSISTENT_DOMINANT,
    TIER_DRIVE_OUT_GEARING, TIER_NONE,
)

ROOT = Path(__file__).resolve().parents[1]


def _ri(issue="wheelspin", fam=IssueFamily.TRACTION, state=ResidualState.UNCHANGED,
        seg="T4", axle="rear", phase="exit", t_aff=3, t_cls="recurring",
        relevance=IssueRelevance.SETUP, protected=False):
    ident = EngineeringIssueIdentity(fam, issue, axle=axle, phase=phase, segment_id=seg,
                                     corner_name=seg, discipline="Race",
                                     scope_fingerprint="x")
    return ResidualIssue(
        identity=ident, residual_state=state, baseline_class="recurring",
        test_class=t_cls, baseline_affected=3, test_affected=t_aff, sample_count=5,
        recurrence_change="unchanged", confidence="high", comparison_status="comparable",
        protected_good=protected, setup_relevance=relevance.value,
        is_new=(state == ResidualState.NEW),
        is_regression=(state in (ResidualState.NEW, ResidualState.WORSENED,
                                 ResidualState.GOOD_BEHAVIOUR_DAMAGED)),
        warnings=(), reasoning="")


# --- 20.4 priority ----------------------------------------------------------
def test_new_regression_outranks_persistent_minor():
    issues = [_ri(issue="wheelspin", state=ResidualState.UNCHANGED),
              _ri(issue="rear_wheelspin", seg="Final", state=ResidualState.NEW, t_cls="recurring")]
    pr = prioritise_issues(issues)
    assert pr[0].residual_state == ResidualState.NEW.value
    assert pr[0].tier == TIER_NEW_REGRESSION


def test_damaged_good_outranks_weak_issue():
    issues = [_ri(issue="wheelspin", state=ResidualState.IMPROVED_BUT_PRESENT),
              _ri(issue="rear traction", fam=IssueFamily.UNKNOWN,
                  state=ResidualState.GOOD_BEHAVIOUR_DAMAGED, protected=True)]
    pr = prioritise_issues(issues)
    assert pr[0].tier == TIER_DAMAGED_GOOD


def test_resolved_and_confirmed_good_excluded():
    issues = [_ri(state=ResidualState.RESOLVED), _ri(state=ResidualState.CONFIRMED_GOOD)]
    pr = prioritise_issues(issues)
    assert all(p.tier == TIER_NONE for p in pr)
    assert all(not p.actionable_as_setup for p in pr)


def test_decision_blocks_all():
    pr = prioritise_issues([_ri(state=ResidualState.UNCHANGED)], decision_blocks=True)
    assert all("setup_decision_blocks" in p.exclusion_reasons for p in pr)


def test_gearing_issue_routed_not_setup():
    pr = prioritise_issues([_ri(issue="wrong_gear", fam=IssueFamily.GEARING,
                                state=ResidualState.UNCHANGED,
                                relevance=IssueRelevance.GEARING)])
    p = pr[0]
    assert not p.actionable_as_setup
    assert p.action_kind == ActionKind.GEARING_REVIEW


def test_priority_order_input_independent():
    issues = [_ri(issue="a", seg="T1", state=ResidualState.UNCHANGED),
              _ri(issue="b", seg="T2", state=ResidualState.NEW),
              _ri(issue="c", seg="T3", state=ResidualState.WORSENED)]
    a = [p.issue_key for p in prioritise_issues(issues)]
    b = [p.issue_key for p in prioritise_issues(list(reversed(issues)))]
    assert a == b


def test_stable_tiebreak():
    # same tier + severity → stable by test_affected then key
    issues = [_ri(issue="x", seg="T1", state=ResidualState.UNCHANGED, t_aff=2),
              _ri(issue="y", seg="T2", state=ResidualState.UNCHANGED, t_aff=4)]
    pr = prioritise_issues(issues)
    assert pr[0].test_affected == 4    # more affected laps first


# --- 9 conflict detection ---------------------------------------------------
def test_same_field_opposite_directions_conflict():
    cands = [{"candidate_id": "arb_front:increase", "field": "arb_front", "direction": "increase"},
             {"candidate_id": "arb_front:decrease", "field": "arb_front", "direction": "decrease"}]
    conf = detect_conflicts(cands)
    assert any(c.conflict_type == ConflictType.SAME_FIELD_OPPOSITE for c in conf)


def test_strong_interaction_conflict():
    cands = [{"candidate_id": "arb_front:increase", "field": "arb_front", "direction": "increase"},
             {"candidate_id": "arb_rear:increase", "field": "arb_rear", "direction": "increase"}]
    conf = detect_conflicts(cands)
    assert any(c.conflict_type == ConflictType.STRONG_INTERACTION for c in conf)


def test_protected_good_conflict():
    cands = [{"candidate_id": "x", "field": "aero_rear", "direction": "increase",
              "protected_behaviours_at_risk": ["rear traction"]}]
    conf = detect_conflicts(cands)
    assert any(c.conflict_type == ConflictType.PROTECTED_GOOD for c in conf)


def test_no_conflict_unrelated_fields():
    # camber_front (apex_front_support/tyre_preservation/high_speed_stability) and
    # lsd_decel (trail_braking_stability/entry_rotation) share no handling axis.
    cands = [{"candidate_id": "a", "field": "camber_front", "direction": "increase"},
             {"candidate_id": "b", "field": "lsd_decel", "direction": "increase"}]
    conf = [c for c in detect_conflicts(cands)
            if c.conflict_type == ConflictType.STRONG_INTERACTION]
    assert not conf


# --- 20.3 clustering --------------------------------------------------------
def test_same_cause_cluster():
    issues = [_ri(issue="wheelspin", seg="T4", axle="rear", phase="exit"),
              _ri(issue="wheelspin", seg="Final", axle="rear", phase="exit")]
    clusters = cluster_issues(issues)
    assert clusters and clusters[0].isolation_required
    assert not clusters[0].coupled_response_permitted


def test_different_cause_no_cluster():
    issues = [_ri(issue="wheelspin", fam=IssueFamily.TRACTION, seg="T4", axle="rear", phase="exit"),
              _ri(issue="understeer", fam=IssueFamily.ROTATION, seg="T3", axle="", phase="apex")]
    clusters = cluster_issues(issues)
    assert clusters == ()   # different family/axle/phase → not clustered


def test_cluster_order_independent():
    issues = [_ri(issue="wheelspin", seg="T4", axle="rear", phase="exit"),
              _ri(issue="wheelspin", seg="Final", axle="rear", phase="exit")]
    a = cluster_issues(issues)
    b = cluster_issues(list(reversed(issues)))
    assert [c.to_dict() for c in a] == [c.to_dict() for c in b]


# --- 20.5 plan --------------------------------------------------------------
def _snapshot(issues):
    outcome = {"scope_fingerprint": "x", "status": "regression", "corners": []}
    snap = build_engineering_state(outcome=outcome, scope_fingerprint="x", car="RSR",
                                   track="Fuji", layout_id="full", discipline="Race",
                                   applied_checkpoint_id="cp1", experiment_id="1",
                                   valid_laps=ValidLapSummary(5, 0, 95000),
                                   generated_at="t")
    import dataclasses
    return dataclasses.replace(snap, residual_issues=tuple(issues))


def test_at_most_one_immediate():
    issues = [_ri(issue="wheelspin", state=ResidualState.UNCHANGED),
              _ri(issue="understeer", fam=IssueFamily.ROTATION, seg="T3",
                  state=ResidualState.UNCHANGED)]
    snap = _snapshot(issues)
    pr = prioritise_issues(issues)
    immediate = {"selected": {"candidate_id": "aero_rear:increase", "field": "aero_rear",
                              "direction": "increase", "target_issue": "wheelspin"}}
    queued = [{"candidate_id": "aero_front:increase", "field": "aero_front",
               "target_issue": "understeer", "_issue_key": pr[1].issue_key}]
    plan = build_development_plan(snap, pr, immediate_selection=immediate,
                                 queued_candidates=queued, plan_id="P", generated_at="t")
    assert plan.has_immediate
    assert len(plan.queued) == 1
    assert plan.queued[0].queue_state == QueueState.WAITING_FOR_CURRENT_EXPERIMENT.value


def test_empty_queue_no_selection_retain():
    issues = [_ri(state=ResidualState.RESOLVED)]
    snap = _snapshot(issues)
    plan = build_development_plan(snap, prioritise_issues(issues), plan_id="P", generated_at="t")
    assert not plan.has_immediate
    assert plan.status == PlanStatus.RETAIN_SETUP


def test_decision_blocks_no_immediate():
    issues = [_ri(state=ResidualState.UNCHANGED)]
    snap = _snapshot(issues)
    plan = build_development_plan(snap, prioritise_issues(issues, decision_blocks=True),
                                 decision_blocks=True, plan_id="P", generated_at="t")
    assert plan.status == PlanStatus.BLOCKED and not plan.has_immediate


def test_plan_has_invalidation_triggers():
    issues = [_ri(state=ResidualState.UNCHANGED)]
    snap = _snapshot(issues)
    plan = build_development_plan(snap, prioritise_issues(issues), plan_id="P", generated_at="t")
    assert "applied setup checkpoint changes" in plan.invalidation_triggers
    assert "scope fingerprint changes" in plan.invalidation_triggers


def test_plan_deterministic_fingerprint():
    issues = [_ri(state=ResidualState.UNCHANGED)]
    snap = _snapshot(issues)
    a = build_development_plan(snap, prioritise_issues(issues), plan_id="P", generated_at="t")
    b = build_development_plan(snap, prioritise_issues(issues), plan_id="P", generated_at="DIFFERENT")
    assert a.content_fingerprint == b.content_fingerprint   # time not in fingerprint


# --- property / metamorphic -------------------------------------------------
def test_reordering_candidates_cannot_change_plan_immediate():
    issues = [_ri(issue="wheelspin", state=ResidualState.UNCHANGED)]
    snap = _snapshot(issues)
    imm = {"selected": {"candidate_id": "aero_rear:increase", "field": "aero_rear",
                        "direction": "increase", "target_issue": "wheelspin"}}
    q1 = [{"candidate_id": "a", "field": "arb_rear"}, {"candidate_id": "b", "field": "toe_rear"}]
    a = build_development_plan(snap, prioritise_issues(issues), immediate_selection=imm,
                              queued_candidates=q1, plan_id="P", generated_at="t")
    b = build_development_plan(snap, prioritise_issues(issues), immediate_selection=imm,
                              queued_candidates=list(reversed(q1)), plan_id="P", generated_at="t")
    assert a.immediate_experiment == b.immediate_experiment


def test_module_pure():
    for mod in ("engineering_state", "experiment_planning"):
        src = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        for banned in ("PyQt6", "from ui.", "import sqlite3", "from data.session_db",
                       "requests", "anthropic", "openai", "datetime.now", "import random"):
            assert banned not in src, f"{mod}: {banned}"
