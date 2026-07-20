"""Engineering-Brain Phase 6 — issue identity + residual-state detection (pure)."""
from __future__ import annotations

from pathlib import Path

import pytest

from strategy.engineering_issue import (
    ENGINEERING_ISSUE_VERSION, IssueFamily, issue_family_for, ResidualState,
    EngineeringIssueIdentity, classify_corner_residual, classify_protected_residual,
    residual_issues_from_outcome, residual_severity_rank,
)

ROOT = Path(__file__).resolve().parents[1]


def _corner(issue="understeer", phase="apex", seg="T3", axle="", b_cls="strongly_recurring",
            t_cls="isolated", b_aff=4, t_aff=1, samples=5, conf="high", verdict="improved",
            is_protected=0):
    return {"segment_id": seg, "corner_name": seg, "issue_type": issue, "phase": phase,
            "axle": axle, "baseline_class": b_cls, "test_class": t_cls,
            "baseline_affected": b_aff, "test_affected": t_aff, "sample_count": samples,
            "confidence": conf, "verdict": verdict, "is_target": 1,
            "is_protected": is_protected}


# --- 20.1 residual states ---------------------------------------------------
def test_resolved():
    r = classify_corner_residual(_corner(verdict="improved", t_cls="isolated", samples=5))
    assert r.residual_state == ResidualState.RESOLVED


def test_improved_but_present():
    r = classify_corner_residual(_corner(verdict="improved", t_cls="recurring", t_aff=3))
    assert r.residual_state == ResidualState.IMPROVED_BUT_PRESENT


def test_unchanged():
    r = classify_corner_residual(_corner(verdict="unchanged", b_cls="recurring",
                                         t_cls="recurring", t_aff=3, b_aff=3))
    assert r.residual_state == ResidualState.UNCHANGED


def test_worsened():
    r = classify_corner_residual(_corner(verdict="regressed", b_cls="recurring",
                                         t_cls="strongly_recurring", t_aff=4, b_aff=3))
    assert r.residual_state == ResidualState.WORSENED


def test_new():
    r = classify_corner_residual(_corner(verdict="regressed", b_cls="strength",
                                         t_cls="recurring", b_aff=0, t_aff=3))
    assert r.residual_state == ResidualState.NEW and r.is_new


def test_confirmed_good():
    r = classify_protected_residual({"behaviour": "rear traction", "verdict": "preserved",
                                     "corners_json": "[]", "confidence": "high"})
    assert r.residual_state == ResidualState.CONFIRMED_GOOD


def test_good_behaviour_damaged():
    r = classify_protected_residual({"behaviour": "rear traction",
                                     "verdict": "material_regression",
                                     "corners_json": "[]", "confidence": "high"})
    assert r.residual_state == ResidualState.GOOD_BEHAVIOUR_DAMAGED and r.is_regression


def test_insufficient_evidence():
    r = classify_corner_residual(_corner(verdict="unmeasurable", samples=0))
    assert r.residual_state == ResidualState.INSUFFICIENT_EVIDENCE


def test_invalid_comparison():
    r = classify_corner_residual(_corner(), association_ok=False)
    assert r.residual_state == ResidualState.INVALID_COMPARISON


def test_not_observed_vs_resolved():
    # nothing at baseline, nothing at test → not a resolution
    r = classify_corner_residual(_corner(verdict="unchanged", b_cls="strength",
                                         t_cls="strength", b_aff=0, t_aff=0))
    assert r.residual_state == ResidualState.NOT_OBSERVED


def test_weak_baseline_improved_needs_samples():
    r = classify_corner_residual(_corner(verdict="improved", t_cls="isolated", samples=2))
    # too few valid laps → cannot claim resolution
    assert r.residual_state == ResidualState.IMPROVED_BUT_PRESENT
    assert any("too few" in w for w in r.warnings)


def test_missing_test_evidence_not_resolution():
    # unmeasurable never becomes resolved
    r = classify_corner_residual(_corner(verdict="unmeasurable"))
    assert r.residual_state != ResidualState.RESOLVED


def test_distinct_affected_lap_recurrence_used():
    r = classify_corner_residual(_corner(b_aff=4, t_aff=1))
    assert r.recurrence_change == "decreased"


def test_deterministic_serialisation():
    a = classify_corner_residual(_corner()).to_dict()
    b = classify_corner_residual(_corner()).to_dict()
    assert a == b


# --- 20.2 issue identity ----------------------------------------------------
def test_issue_family_mapping():
    assert issue_family_for("front_lock") == IssueFamily.BRAKING
    assert issue_family_for("wheelspin") == IssueFamily.TRACTION
    assert issue_family_for("wrong_gear") == IssueFamily.GEARING


def test_same_issue_across_sources_same_key():
    a = EngineeringIssueIdentity(IssueFamily.BRAKING, "front_lock", phase="braking",
                                 segment_id="T1", scope_fingerprint="x")
    b = EngineeringIssueIdentity(IssueFamily.BRAKING, "front_lock", phase="braking",
                                 segment_id="T1", scope_fingerprint="x", corner_name="Turn 1")
    assert a.key() == b.key()   # corner_name display text does not change identity


def test_different_issue_same_corner_distinct():
    lock = EngineeringIssueIdentity(IssueFamily.BRAKING, "front_lock", segment_id="T1")
    rot = EngineeringIssueIdentity(IssueFamily.ROTATION, "understeer", segment_id="T1")
    assert lock.key() != rot.key()


def test_same_issue_different_corners_distinct():
    a = EngineeringIssueIdentity(IssueFamily.ROTATION, "understeer", segment_id="T3")
    b = EngineeringIssueIdentity(IssueFamily.ROTATION, "understeer", segment_id="T7")
    assert a.key() != b.key()


def test_same_issue_different_phase_distinct():
    a = EngineeringIssueIdentity(IssueFamily.ROTATION, "understeer", phase="entry")
    b = EngineeringIssueIdentity(IssueFamily.ROTATION, "understeer", phase="apex")
    assert a.key() != b.key()


def test_axle_distinction():
    a = EngineeringIssueIdentity(IssueFamily.TRACTION, "wheelspin", axle="rear")
    b = EngineeringIssueIdentity(IssueFamily.TRACTION, "wheelspin", axle="front")
    assert a.key() != b.key()


def test_gear_vs_traction_distinct():
    g = EngineeringIssueIdentity(IssueFamily.GEARING, "wrong_gear", segment_id="T4")
    t = EngineeringIssueIdentity(IssueFamily.TRACTION, "wheelspin", segment_id="T4")
    assert g.key() != t.key()
    assert g.issue_family == IssueFamily.GEARING


def test_no_display_string_in_key():
    a = EngineeringIssueIdentity(IssueFamily.TRACTION, "wheelspin", corner_name="Final")
    b = EngineeringIssueIdentity(IssueFamily.TRACTION, "wheelspin", corner_name="Turn 13")
    assert a.key() == b.key()


def test_stable_fingerprint_versioned():
    k = EngineeringIssueIdentity(IssueFamily.BRAKING, "front_lock").key()
    assert k.startswith(ENGINEERING_ISSUE_VERSION)


# --- outcome-level derivation + de-dup --------------------------------------
def test_outcome_dedup_keeps_most_severe():
    outcome = {"scope_fingerprint": "x", "corners": [
        _corner(issue="wheelspin", seg="T4", axle="rear", verdict="unchanged",
                b_cls="recurring", t_cls="recurring", b_aff=3, t_aff=3),
        _corner(issue="wheelspin", seg="T4", axle="rear", verdict="regressed",
                b_cls="recurring", t_cls="strongly_recurring", b_aff=3, t_aff=4)]}
    issues = residual_issues_from_outcome(outcome, discipline="Race")
    # same identity → one issue, the WORSENED (more severe) wins
    assert len(issues) == 1
    assert issues[0].residual_state == ResidualState.WORSENED


# --- property / metamorphic -------------------------------------------------
def test_reorder_observations_cannot_change_classification():
    outcome = {"scope_fingerprint": "x", "corners": [
        _corner(issue="understeer", seg="T3"),
        _corner(issue="wheelspin", seg="T4", axle="rear", verdict="unchanged",
                b_cls="recurring", t_cls="recurring", b_aff=3, t_aff=3)]}
    a = residual_issues_from_outcome(outcome, discipline="Race")
    outcome2 = {"scope_fingerprint": "x", "corners": list(reversed(outcome["corners"]))}
    b = residual_issues_from_outcome(outcome2, discipline="Race")
    assert [x.to_dict() for x in a] == [x.to_dict() for x in b]


def test_missing_test_cannot_produce_resolution():
    r = classify_corner_residual(_corner(verdict="unmeasurable", t_cls="", t_aff=0))
    assert r.residual_state == ResidualState.INSUFFICIENT_EVIDENCE


def test_module_pure():
    src = (ROOT / "strategy" / "engineering_issue.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "from ui.", "import sqlite3", "from data.session_db",
                   "requests", "anthropic", "openai", "datetime.now", "import random"):
        assert banned not in src, banned
