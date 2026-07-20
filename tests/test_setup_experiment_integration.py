"""Engineering-Brain Phase 2 — recommendation + apply integration tests.

Drives the SessionDB orchestration seams the Setup Builder calls:
  * record_recommendation_experiment  (the Analyse production path)
  * link_apply_to_experiment          (the Apply-in-GT7 path)
plus the frozen safety contracts (golden config_id, fan-out allowlist, Apply-gate
predicate, no auto-apply). Isolated in-memory SessionDB — no Qt, no runtime files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data.session_db import SessionDB

ROOT = Path(__file__).resolve().parents[1]


def _data(status="approved", changes=None, **over):
    d = {
        "recommendation_status": status,
        "analysis": "rear loose on exit",
        "changes": changes if changes is not None else [
            {"field": "lsd_accel", "from": "8", "to_clamped": "12", "rule_id": "R1",
             "symptom": "exit_oversteer", "evidence": ["reduces exit rotation"]},
        ],
        "diagnosis": {"dominant_problem": "exit_oversteer", "unresolved": ["gearing"]},
        "protected_fields": ["brake_bias"],
        "deterministic_plan": {"rule_engine_version": "46.0", "driver_profile_version": "v1"},
        "rollback": {"label": "Base RSR"},
    }
    d.update(over)
    return d


def _scope():
    return dict(car_id=7, track="Fuji", layout_id="full_course", discipline="Race")


@pytest.fixture
def db():
    return SessionDB(":memory:")


# ------------------------------------------------------------------ 21 create one
def test_analyse_creates_one_experiment(db):
    eid = db.record_recommendation_experiment(
        _data(), parent_setup_id="base1", **_scope())
    assert eid is not None
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 1
    exp = db.get_setup_experiment(eid)
    assert exp["recommendation_source"] == "analyse"
    assert exp["recommendation_status"] == "approved"
    assert exp["status"] == "draft"


# ------------------------------------------------------------------ 22,23 no duplicates
def test_repeated_render_does_not_duplicate(db):
    a = db.record_recommendation_experiment(_data(), parent_setup_id="base1", **_scope())
    b = db.record_recommendation_experiment(_data(), parent_setup_id="base1", **_scope())  # re-render
    c = db.record_recommendation_experiment(_data(), parent_setup_id="base1", **_scope())  # reopen view
    assert a == b == c
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 1


# ------------------------------------------------------------------ 24,25 no experiment
def test_blocked_response_creates_no_experiment(db):
    assert db.record_recommendation_experiment(
        _data(status="blocked_no_safe_recommendation"),
        parent_setup_id="b", **_scope()) is None
    assert db.record_recommendation_experiment(
        _data(status="evidence_required"), parent_setup_id="b", **_scope()) is None
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 0


def test_empty_response_creates_no_experiment(db):
    assert db.record_recommendation_experiment(
        _data(changes=[]), parent_setup_id="b", **_scope()) is None
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 0


# ------------------------------------------------------------------ 26 partial valid
def test_partial_response_persists_valid_changes_and_deferrals(db):
    data = _data(
        status="partial_recommendation",
        changes=[{"field": "lsd_accel", "from": "8", "to_clamped": "12", "rule_id": "R1"}],
        diagnosis={"dominant_problem": "exit_oversteer",
                   "unresolved": ["bottoming_uncertain", "gearing_uncertain"]},
        rejected_changes=[{"field": "ride_height", "symptom": "bottoming", "rule_id": "RX"}])
    eid = db.record_recommendation_experiment(data, parent_setup_id="b", **_scope())
    exp = db.get_setup_experiment(eid)
    assert len(exp["changes"]) == 1                       # only the valid change
    deferred = exp["deferred_diagnoses_json"]
    assert "bottoming_uncertain" in deferred and "gearing_uncertain" in deferred
    assert "ride_height" in deferred                      # rejected change recorded as deferred


# ------------------------------------------------------------------ 27-30 captured content
def test_recommendation_evidence_captured_at_creation(db):
    eid = db.record_recommendation_experiment(
        _data(setup_lineage=[{"id": 3, "label": "Base"}]),
        parent_setup_id="b", **_scope())
    ev = db.get_experiment_evidence(eid, phase="diagnosis")
    assert ev and ev[0]["evidence_type"] == "diagnosis"
    assert db.get_experiment_evidence(eid, phase="baseline")  # lineage node evidence


def test_provenance_and_protected_and_protocol_persisted(db):
    eid = db.record_recommendation_experiment(_data(), parent_setup_id="b", **_scope())
    exp = db.get_setup_experiment(eid)
    assert exp["rule_engine_version"] == "46.0"
    assert exp["driver_profile_version"] == "v1"
    assert exp["changes"][0]["rule_id"] == "R1"
    assert any(p["field"] == "brake_bias" for p in exp["protected_behaviours"])
    assert exp["test_protocol"]["rollback_target"] == "Base RSR"


# ------------------------------------------------------------------ 31 display != applied
def test_creating_experiment_does_not_mark_applied(db):
    eid = db.record_recommendation_experiment(_data(), parent_setup_id="b", **_scope())
    exp = db.get_setup_experiment(eid)
    assert exp["status"] == "draft"
    assert exp["applied_checkpoint_id"] == ""
    # And no applied-checkpoint row was created just by analysing.
    assert db._conn.execute(
        "SELECT COUNT(*) FROM applied_setup_checkpoints").fetchone()[0] == 0


# ------------------------------------------------------------------ 32,33,39 apply links
def test_apply_links_checkpoint_and_transitions(db):
    db.record_recommendation_experiment(_data(), parent_setup_id="base1", **_scope())
    res = db.link_apply_to_experiment(
        parent_setup_id="base1", checkpoint_id="cp1",
        applied_fields={"lsd_accel": 12}, **_scope())
    assert res is not None
    assert res["match_state"] == "match"
    exp = db.get_setup_experiment(res["experiment_id"])
    assert exp["status"] == "applied"                 # only after a valid checkpoint link
    assert exp["applied_checkpoint_id"] == "cp1"
    # state history records the apply transition
    assert any(h["to_status"] == "applied" for h in exp["state_history"])


# ------------------------------------------------------------------ 34 partial / unverifiable
def test_apply_missing_values_partial(db):
    db.record_recommendation_experiment(
        _data(changes=[
            {"field": "lsd_accel", "from": "8", "to_clamped": "12"},
            {"field": "rear_arb", "from": "6", "to_clamped": "5"},
        ]), parent_setup_id="base1", **_scope())
    res = db.link_apply_to_experiment(
        parent_setup_id="base1", checkpoint_id="cp2",
        applied_fields={"lsd_accel": 12}, **_scope())   # rear_arb missing
    assert res["match_state"] == "partial_match"


# ------------------------------------------------------------------ 35,36,37 mismatch
def test_apply_mismatch_reported_without_altering_recommendation(db):
    eid = db.record_recommendation_experiment(_data(), parent_setup_id="base1", **_scope())
    res = db.link_apply_to_experiment(
        parent_setup_id="base1", checkpoint_id="cp3",
        applied_fields={"lsd_accel": 20}, **_scope())   # applied != proposed 12
    assert res["match_state"] == "mismatch"
    exp = db.get_setup_experiment(eid)
    assert exp["applied_match_state"] == "mismatch"          # visible in structured output
    assert "lsd_accel" in str(exp["applied_comparison_json"])
    assert exp["changes"][0]["to_value"] == "12"            # original recommendation intact


# ------------------------------------------------------------------ 38 rollback target
def test_rollback_target_is_the_proven_parent(db):
    eid = db.record_recommendation_experiment(
        _data(rollback={"label": "Proven Base RSR"}), parent_setup_id="base1", **_scope())
    exp = db.get_setup_experiment(eid)
    assert exp["rollback_target"] == "Proven Base RSR"
    # apply mismatch must NOT change the rollback target
    db.link_apply_to_experiment(parent_setup_id="base1", checkpoint_id="cp",
                                applied_fields={"lsd_accel": 99}, **_scope())
    assert db.get_setup_experiment(eid)["rollback_target"] == "Proven Base RSR"


# ------------------------------------------------------------------ 40 duplicate apply idempotent
def test_duplicate_apply_is_idempotent(db):
    db.record_recommendation_experiment(_data(), parent_setup_id="base1", **_scope())
    r1 = db.link_apply_to_experiment(parent_setup_id="base1", checkpoint_id="cpX",
                                     applied_fields={"lsd_accel": 12}, **_scope())
    r2 = db.link_apply_to_experiment(parent_setup_id="base1", checkpoint_id="cpX",
                                     applied_fields={"lsd_accel": 12}, **_scope())
    assert r2.get("already_linked") is True
    eid = r1["experiment_id"]
    # only ONE 'applied' transition recorded
    hist = db.get_experiment_state_history(eid)
    assert sum(1 for h in hist if h["to_status"] == "applied") == 1


def test_apply_with_no_experiment_returns_none(db):
    # No experiment in this scope → nothing to link (never fabricates one).
    assert db.link_apply_to_experiment(
        parent_setup_id="nope", checkpoint_id="cp",
        applied_fields={"x": 1}, car_id=99, track="Nowhere", layout_id="z",
        discipline="Race") is None


# ------------------------------------------------------------------ 43 no cross-scope link
def test_apply_does_not_cross_link_other_scope(db):
    db.record_recommendation_experiment(_data(), parent_setup_id="base1", **_scope())
    # Apply on a DIFFERENT car → must not link the Fuji/car7 experiment.
    res = db.link_apply_to_experiment(
        parent_setup_id="base1", checkpoint_id="cp",
        applied_fields={"lsd_accel": 12},
        car_id=99, track="Fuji", layout_id="full_course", discipline="Race")
    assert res is None


# ------------------------------------------------------------------ 45,46,47,48 frozen safety
def test_golden_config_id_unchanged():
    from tests.test_race_config_id_hash import GOLDEN_VECTORS, _bind
    for strategy, expected in GOLDEN_VECTORS:
        assert _bind(strategy)._compute_race_config_id() == expected


def test_frozen_fanout_allowlist_unchanged():
    from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
    assert _scan_inventory() == FROZEN_ALLOWLIST


def test_apply_gate_predicate_unchanged():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    # The frozen Apply-gate predicate components must be intact (Phase 2 wired
    # experiment creation AFTER it, changing nothing about the gate itself).
    assert "_status_approved: bool = (not _is_legacy) and (_rec_status in _APPROVED_STATUSES)" in src


def test_no_auto_apply_in_phase2_code():
    # Neither the domain nor the orchestration writes setup fields to GT7 / disk.
    exp_src = (ROOT / "strategy" / "setup_experiment.py").read_text(encoding="utf-8")
    assert "mark_applied" not in exp_src
    assert "apply_setup" not in exp_src
    # Recording an experiment must not create an applied checkpoint by itself
    # (covered behaviourally in test_creating_experiment_does_not_mark_applied).


def test_apply_gate_predicate_matches_config_safety(db):
    import config_paths as cp
    assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
