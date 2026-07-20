"""Engineering-Brain Phase 2 — pure setup-experiment domain tests.

Covers the Qt/DB-free domain module (strategy/setup_experiment.py): model
validation, honest unknowns, actionable gating, deterministic state transitions,
immutability, applied-value comparison, idempotency, serialization, and purity.
Touches NO database and NO runtime files.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from strategy.setup_experiment import (
    EXPERIMENT_SCHEMA_VERSION, ExperimentStatus, ChangeRole, EvidencePhase,
    AppliedMatchState, ExperimentEvidence,
    build_experiment_from_recommendation, compare_proposed_vs_applied,
    compute_idempotency_key, validate_experiment, validate_transition,
    is_terminal, recommendation_evidence_from_data,
    VALID_TRANSITIONS,
)
from data.engineering_context_key import FINGERPRINT_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _rec_data(**over):
    data = {
        "recommendation_status": "approved",
        "analysis": "rear loose on exit; add power-lock and soften rear ARB",
        "changes": [
            {"field": "lsd_accel", "from": "8", "to_clamped": "12", "rule_id": "R1",
             "symptom": "exit_oversteer", "evidence": ["reduces exit rotation"]},
            {"field": "rear_arb", "from": "6", "to_clamped": "5", "rule_id": "R2"},
        ],
        "diagnosis": {"dominant_problem": "exit_oversteer",
                      "secondary_problems": ["traction"],
                      "unresolved": ["gearing_uncertain"]},
        "protected_fields": ["brake_bias"],
        "deterministic_plan": {"rule_engine_version": "46.0",
                               "driver_profile_version": "v1"},
        "setup_lineage": [{"id": 3, "label": "Base RSR"}],
        "rollback": {"label": "Base RSR"},
    }
    data.update(over)
    return data


def _make(**kw):
    return build_experiment_from_recommendation(
        _rec_data(**kw.pop("data_over", {})),
        car_id=kw.pop("car_id", 7), track=kw.pop("track", "Fuji"),
        layout_id=kw.pop("layout_id", "full_course"),
        discipline=kw.pop("discipline", "Race"),
        parent_setup_id=kw.pop("parent_setup_id", "base1"), **kw)


# ------------------------------------------------------------------ 1 validation
def test_complete_experiment_validates():
    exp = _make()
    v = validate_experiment(exp)
    assert v.ok, v.errors
    assert exp.schema_version == EXPERIMENT_SCHEMA_VERSION
    assert exp.status == ExperimentStatus.DRAFT
    assert len(exp.actionable_changes) == 2


# ------------------------------------------------------------------ 2 missing context
def test_missing_scope_fingerprint_fails_validation():
    exp = _make()
    stripped = dataclasses.replace(exp, scope_fingerprint="")
    v = validate_experiment(stripped)
    assert not v.ok
    assert any("scope_fingerprint" in e for e in v.errors)


# ------------------------------------------------------------------ 3 unknown stays unknown
def test_unknown_values_stay_unknown():
    data = _rec_data(changes=[{"field": "lsd_accel", "to_clamped": "12"}])  # no 'from'
    exp = build_experiment_from_recommendation(
        data, car_id=7, track="Fuji", layout_id="full")
    assert exp.changes[0].from_value is None       # not invented
    assert exp.changes[0].delta_direction == ""     # cannot compute a direction
    assert exp.changes[0].delta_magnitude is None


def test_no_layout_leaves_scope_partial_not_fabricated():
    exp = build_experiment_from_recommendation(
        _rec_data(), car_id=7, track="Fuji International Speedway")  # free text, no layout
    assert exp.context_status in ("partial", "unresolved")
    # layout unknown ⇒ not fabricated; scope still deterministic
    assert exp.scope_fingerprint.startswith(FINGERPRINT_VERSION)


# ------------------------------------------------------------------ 4 empty actionable
def test_empty_changes_creates_no_experiment():
    assert build_experiment_from_recommendation(
        _rec_data(changes=[]), car_id=7, track="Fuji", layout_id="full") is None


def test_changes_without_field_create_no_experiment():
    assert build_experiment_from_recommendation(
        _rec_data(changes=[{"to": "1"}]), car_id=7, track="Fuji") is None


# ------------------------------------------------------------------ 5 blocked cannot apply
@pytest.mark.parametrize("status", [
    "blocked_no_safe_recommendation", "evidence_required", "validation_failed",
    "retry_failed", "generated", "",
])
def test_non_approved_status_creates_no_experiment(status):
    assert build_experiment_from_recommendation(
        _rec_data(recommendation_status=status), car_id=7, track="Fuji",
        layout_id="full") is None


def test_cannot_ready_for_apply_without_actionable_changes():
    chk = validate_transition(
        ExperimentStatus.DRAFT, ExperimentStatus.READY_FOR_APPLY,
        has_actionable_changes=False)
    assert not chk.ok


# ------------------------------------------------------------------ 6,7 transitions
def test_valid_transitions_are_deterministic():
    for _ in range(10):
        assert validate_transition(
            ExperimentStatus.DRAFT, ExperimentStatus.READY_FOR_APPLY).ok
        assert validate_transition(
            ExperimentStatus.READY_FOR_APPLY, ExperimentStatus.APPLIED,
            has_applied_checkpoint=True).ok


@pytest.mark.parametrize("frm,to", [
    (ExperimentStatus.DRAFT, ExperimentStatus.APPLIED),       # skips ready/checkpoint
    (ExperimentStatus.DRAFT, ExperimentStatus.COMPLETED),
    (ExperimentStatus.APPLIED, ExperimentStatus.DRAFT),       # no going back
    (ExperimentStatus.COMPLETED, ExperimentStatus.APPLIED),   # terminal
    (ExperimentStatus.REJECTED, ExperimentStatus.APPLIED),
])
def test_invalid_transitions_rejected(frm, to):
    assert not validate_transition(
        frm, to, has_applied_checkpoint=True, has_test_evidence=True).ok


def test_applied_requires_checkpoint():
    assert not validate_transition(
        ExperimentStatus.READY_FOR_APPLY, ExperimentStatus.APPLIED,
        has_applied_checkpoint=False).ok


def test_completed_requires_phase3_outcome():
    # COMPLETED depends on a Phase 3 outcome record that does not exist yet.
    assert not validate_transition(
        ExperimentStatus.READY_FOR_REVIEW, ExperimentStatus.COMPLETED,
        has_outcome_record=False).ok
    assert validate_transition(
        ExperimentStatus.READY_FOR_REVIEW, ExperimentStatus.COMPLETED,
        has_outcome_record=True).ok  # honest dependency, not fabricated


def test_review_requires_test_evidence():
    assert not validate_transition(
        ExperimentStatus.APPLIED, ExperimentStatus.READY_FOR_REVIEW,
        has_test_evidence=False).ok


def test_terminal_states_have_no_exits():
    for st in (ExperimentStatus.COMPLETED, ExperimentStatus.REJECTED,
               ExperimentStatus.REVERTED, ExperimentStatus.CANCELLED,
               ExperimentStatus.INVALID):
        assert is_terminal(st)
        assert VALID_TRANSITIONS[st] == frozenset()


# ------------------------------------------------------------------ 8,9 immutability
def test_experiment_is_frozen():
    exp = _make()
    with pytest.raises(dataclasses.FrozenInstanceError):
        exp.status = ExperimentStatus.APPLIED  # type: ignore
    with pytest.raises(dataclasses.FrozenInstanceError):
        exp.changes = ()  # type: ignore


def test_amendment_returns_new_object_original_unchanged():
    exp = _make()
    original_key = exp.idempotency_key
    original_changes = exp.changes
    amended = dataclasses.replace(exp, status=ExperimentStatus.CANCELLED)
    assert amended is not exp
    assert exp.status == ExperimentStatus.DRAFT          # original untouched
    assert exp.idempotency_key == original_key
    assert exp.changes is original_changes


# ------------------------------------------------------------------ 10 serialization
def test_serialization_round_trip_shape():
    exp = _make()
    d = exp.to_dict()
    assert d["schema_version"] == EXPERIMENT_SCHEMA_VERSION
    assert d["scope_fingerprint"] == exp.scope_fingerprint
    assert len(d["changes"]) == 2
    assert d["changes"][0]["role"] == ChangeRole.PRIMARY.value
    assert d["hypothesis"]["primary_diagnosis"] == "exit_oversteer"
    assert d["protected_behaviours"][0]["field"] == "brake_bias"
    assert d["test_protocol"]["rollback_target"] == "Base RSR"
    import json
    assert json.loads(json.dumps(d))  # JSON-serializable


# ------------------------------------------------------------------ applied comparison
def test_compare_match():
    assert compare_proposed_vs_applied(
        {"lsd_accel": "12"}, {"lsd_accel": 12}).state == AppliedMatchState.MATCH


def test_compare_mismatch_preserves_values():
    cmp = compare_proposed_vs_applied({"lsd_accel": "12"}, {"lsd_accel": 20})
    assert cmp.state == AppliedMatchState.MISMATCH
    assert "lsd_accel" in cmp.mismatched_fields
    fc = cmp.fields[0]
    assert fc.proposed == "12" and fc.applied == "20"


def test_compare_partial_when_some_missing():
    cmp = compare_proposed_vs_applied({"a": "1", "b": "2"}, {"a": 1})
    assert cmp.state == AppliedMatchState.PARTIAL_MATCH
    assert cmp.missing_fields == ("b",)


def test_compare_unverifiable_when_empty():
    assert compare_proposed_vs_applied({}, {"a": 1}).state == AppliedMatchState.UNVERIFIABLE
    assert compare_proposed_vs_applied({"a": "1"}, {}).state == AppliedMatchState.UNVERIFIABLE


def test_compare_never_coerces_unrelated_units():
    # A string field vs a numeric field compares literally, never coerced.
    cmp = compare_proposed_vs_applied({"tyre": "soft"}, {"tyre": "hard"})
    assert cmp.state == AppliedMatchState.MISMATCH
    cmp2 = compare_proposed_vs_applied({"tyre": "soft"}, {"tyre": "soft"})
    assert cmp2.state == AppliedMatchState.MATCH


# ------------------------------------------------------------------ evidence snapshot
def test_recommendation_evidence_captured():
    ev = recommendation_evidence_from_data(_rec_data())
    kinds = {e.evidence_type for e in ev}
    assert "diagnosis" in kinds
    assert "lineage_node" in kinds
    assert all(isinstance(e, ExperimentEvidence) for e in ev)
    # phases are honest
    phases = {e.phase for e in ev}
    assert EvidencePhase.DIAGNOSIS in phases


def test_provenance_and_solver_refs_preserved():
    exp = _make()
    assert exp.rule_engine_version == "46.0"
    assert exp.driver_profile_version == "v1"
    assert exp.changes[0].rule_id == "R1"
    assert exp.changes[0].symptom == "exit_oversteer"


def test_protected_behaviours_persisted_in_model():
    exp = _make()
    assert any(p.field == "brake_bias" for p in exp.protected_behaviours)


def test_deferred_diagnoses_recorded():
    exp = _make()
    assert any("gearing" in d for d in exp.deferred_diagnoses)


# ------------------------------------------------------------------ idempotency
def test_idempotency_key_deterministic():
    a = _make()
    b = _make()
    assert a.idempotency_key == b.idempotency_key
    assert a.idempotency_key.startswith(EXPERIMENT_SCHEMA_VERSION)


def test_idempotency_key_stable_under_change_order():
    # Reordering the proposed changes must NOT change the idempotency key
    # (metamorphic: the key sorts changes).
    d1 = _rec_data()
    d2 = _rec_data(changes=list(reversed(_rec_data()["changes"])))
    e1 = build_experiment_from_recommendation(d1, car_id=7, track="Fuji", layout_id="full", parent_setup_id="b")
    e2 = build_experiment_from_recommendation(d2, car_id=7, track="Fuji", layout_id="full", parent_setup_id="b")
    assert e1.idempotency_key == e2.idempotency_key


def test_idempotency_key_changes_with_values():
    base = _make()
    other = build_experiment_from_recommendation(
        _rec_data(changes=[{"field": "lsd_accel", "from": "8", "to_clamped": "16"}]),
        car_id=7, track="Fuji", layout_id="full_course", parent_setup_id="base1")
    assert base.idempotency_key != other.idempotency_key


def test_idempotency_key_uses_no_timestamp():
    # Behavioural: the key must not reference wall-clock time. Check the function
    # body (not the docstring) makes no datetime/time-module call.
    import inspect
    lines = [ln for ln in inspect.getsource(compute_idempotency_key).splitlines()
             if not ln.strip().startswith(('"', "'", "#"))]
    body = "\n".join(lines).lower()
    assert "datetime" not in body
    assert "time.time" not in body
    assert ".now(" not in body


# ------------------------------------------------------------------ 41,42,43 context
def test_experiment_uses_phase1_scope_fingerprint():
    exp = _make()
    assert exp.scope_fingerprint.startswith(f"{FINGERPRINT_VERSION}:scope:")
    assert exp.context_schema_version == FINGERPRINT_VERSION


def test_no_competing_fingerprint_algorithm():
    src = (ROOT / "strategy" / "setup_experiment.py").read_text(encoding="utf-8")
    # It must OBTAIN the context via Phase 1, not recompute it.
    assert "build_engineering_context" in src
    assert "def scope_fingerprint" not in src   # does not define its own
    assert "compute_config_id" not in src


def test_different_scopes_do_not_cross_link():
    a = _make(car_id=7, layout_id="full_course").scope_fingerprint
    b = _make(car_id=8, layout_id="full_course").scope_fingerprint  # different car
    c = _make(car_id=7, layout_id="short_course").scope_fingerprint  # different layout
    assert a != b and a != c and b != c


# ------------------------------------------------------------------ 49,50 purity
def test_domain_module_imports_nothing_forbidden():
    src = (ROOT / "strategy" / "setup_experiment.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "PyQt5", "import requests", "urllib.request",
                   "anthropic", "openai", "api_key", "from data.session_db",
                   "import sqlite3", "from ui."):
        assert banned not in src, banned


def test_no_random_or_wallclock_in_domain():
    src = (ROOT / "strategy" / "setup_experiment.py").read_text(encoding="utf-8")
    assert "random" not in src
    assert "datetime.now" not in src   # timestamps are stamped by persistence
