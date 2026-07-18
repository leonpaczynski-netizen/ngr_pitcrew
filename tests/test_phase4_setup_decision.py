"""Engineering-Brain Phase 4 — canonical setup-decision status authority tests."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from strategy.setup_decision_status import (
    resolve_setup_decision, SetupDecisionState, SETUP_DECISION_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]


# 62
def test_no_recommendation():
    assert resolve_setup_decision().state == SetupDecisionState.NO_RECOMMENDATION


# 63
def test_evidence_required():
    r = resolve_setup_decision(recommendation_status="evidence_required")
    assert r.state == SetupDecisionState.EVIDENCE_REQUIRED


def test_recommendation_ready():
    r = resolve_setup_decision(recommendation_status="approved")
    assert r.state == SetupDecisionState.RECOMMENDATION_READY


# 64
def test_ready_for_apply():
    r = resolve_setup_decision(experiment_status="ready_for_apply")
    assert r.state == SetupDecisionState.READY_FOR_APPLY
    assert "apply_in_game" in r.allowed_actions


# 65 / 66
def test_applied_test_required():
    r = resolve_setup_decision(experiment_status="applied")
    assert r.state == SetupDecisionState.TEST_REQUIRED
    assert "review_outcome" in r.allowed_actions
    assert "apply_in_game" in r.blocked_actions


# 67
def test_ready_for_review():
    r = resolve_setup_decision(experiment_status="ready_for_review")
    assert r.state == SetupDecisionState.READY_FOR_REVIEW


# 68
def test_confirmed():
    r = resolve_setup_decision(experiment_status="completed",
                               outcome_status="confirmed_improvement")
    assert r.state == SetupDecisionState.CONFIRMED
    assert "retain" in r.allowed_actions


# 69
def test_partial():
    r = resolve_setup_decision(experiment_status="ready_for_review",
                               outcome_status="partial_improvement")
    assert r.state == SetupDecisionState.PARTIAL


# 70
def test_rejected():
    r = resolve_setup_decision(experiment_status="rejected", outcome_status="regression")
    assert r.state == SetupDecisionState.REJECTED
    assert "revert_to_parent" in r.allowed_actions


# 71
def test_inconclusive():
    for oc in ("no_meaningful_change", "confounded", "insufficient_evidence"):
        r = resolve_setup_decision(experiment_status="ready_for_review", outcome_status=oc)
        assert r.state == SetupDecisionState.INCONCLUSIVE


# 72
def test_reverted():
    r = resolve_setup_decision(experiment_status="reverted", outcome_status="regression")
    assert r.state == SetupDecisionState.REVERTED


# 73
def test_invalid_contradiction():
    # experiment COMPLETED but no outcome → contradiction
    r = resolve_setup_decision(experiment_status="completed")
    assert r.state == SetupDecisionState.INVALID
    assert r.is_inconsistent
    # applied but nothing saved
    r2 = resolve_setup_decision(experiment_status="applied", apply_state="not_saved")
    assert r2.state == SetupDecisionState.INVALID


# 74
def test_allowed_actions_deterministic():
    a = resolve_setup_decision(experiment_status="ready_for_apply")
    b = resolve_setup_decision(experiment_status="ready_for_apply")
    assert a.to_dict() == b.to_dict()
    assert a.eval_version == SETUP_DECISION_VERSION


def test_mismatch_reason_surfaced():
    r = resolve_setup_decision(experiment_status="applied", applied_match_state="mismatch")
    assert any("differ" in rc for rc in r.reason_codes)


# 75 — UI renders the authority (imports + uses resolve_setup_decision)
def test_ui_uses_authority():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "resolve_setup_decision" in src


# 76 — dormant competing arbiter retired / formally deprecated (no live path)
def test_dormant_arbiter_deprecated_and_unwired():
    # formal deprecation note present
    dec = (ROOT / "strategy" / "setup_decision.py").read_text(encoding="utf-8")
    assert "DEPRECATED" in dec
    assert "resolve_setup_decision" in dec        # points to the Phase 4 authority
    # no UI runtime references the arbiter entry point
    for p in (ROOT / "ui").glob("*.py"):
        assert not re.search(r"\barbitrate_setup_decision\b",
                             p.read_text(encoding="utf-8", errors="ignore"))
    # the wiring-status guard still holds
    from tests.test_engine_wiring_status import EXPERIMENTAL_SYMBOLS
    assert "arbitrate_setup_decision" in EXPERIMENTAL_SYMBOLS


def test_module_pure():
    src = (ROOT / "strategy" / "setup_decision_status.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "from ui.", "import sqlite3", "from data.session_db",
                   "requests", "anthropic", "openai", "datetime.now", "random"):
        assert banned not in src, banned
