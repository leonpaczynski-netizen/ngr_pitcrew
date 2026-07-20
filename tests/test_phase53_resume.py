"""Phase 53 — restart/resume, interrupted activity, telemetry dropout (task items 20-23)."""
from __future__ import annotations

from strategy.live_activity import LiveActivityState as L
from strategy.programme_resume import (
    InterruptedActivityResolution as IR, build_resume_state, classify_interrupted_activity,
    resolve_telemetry_dropout,
)


def test_restart_never_restores_interrupted_as_complete():
    # a restart cannot fabricate a completion — a COMPLETED interrupted activity is downgraded
    r = build_resume_state(selected_cycle_id="c1", interrupted_activity_id="a1",
                           interrupted_state=L.COMPLETED)
    assert r.interrupted_state == L.INTERRUPTED


def test_resume_state_restores_operational_fields():
    r = build_resume_state(selected_cycle_id="c1", current_phase="setup_development",
                           completed_activity_ids=("a1", "a2"), next_activity_id="a3",
                           pending_binding=True, setup_locks=("qualifying",), strategy_finalised=False)
    assert r.selected_cycle_id == "c1" and r.next_activity_id == "a3"
    assert r.pending_binding is True and "qualifying" in r.setup_locks


def test_voice_restored_disabled_by_default():
    assert build_resume_state(selected_cycle_id="c1").voice_preserved is False


def test_resume_state_deterministic():
    a = build_resume_state(selected_cycle_id="c1", next_activity_id="a3")
    b = build_resume_state(selected_cycle_id="c1", next_activity_id="a3")
    assert a.fingerprint == b.fingerprint


# --- interrupted activity classification -----------------------------------

def test_interrupted_resumable_when_no_partial_session():
    assert classify_interrupted_activity(telemetry_recoverable=False, has_partial_session=False,
                                         min_evidence_met=False) == IR.RESUMABLE


def test_interrupted_recoverable_session():
    assert classify_interrupted_activity(telemetry_recoverable=True, has_partial_session=True,
                                         min_evidence_met=False) == IR.SESSION_RECOVERABLE
    assert classify_interrupted_activity(telemetry_recoverable=True, has_partial_session=True,
                                         min_evidence_met=True) == IR.BINDING_REQUIRED


def test_interrupted_insufficient_evidence():
    assert classify_interrupted_activity(telemetry_recoverable=False, has_partial_session=True,
                                         min_evidence_met=False) == IR.INSUFFICIENT_EVIDENCE


def test_interrupted_explicit_abandon_or_invalid():
    assert classify_interrupted_activity(telemetry_recoverable=True, has_partial_session=True,
                                         min_evidence_met=True, user_abandon=True) == IR.ABANDONED
    assert classify_interrupted_activity(telemetry_recoverable=True, has_partial_session=True,
                                         min_evidence_met=True, user_invalid=True) == IR.INVALID


def test_interrupted_never_auto_completes():
    # there is no code path that returns COMPLETED / a can_complete flag from an interruption
    for tr in (True, False):
        for hp in (True, False):
            for me in (True, False):
                res = classify_interrupted_activity(telemetry_recoverable=tr, has_partial_session=hp,
                                                    min_evidence_met=me)
                assert res in set(IR)  # always a recovery classification, never a completion


# --- telemetry dropout -----------------------------------------------------

def test_telemetry_dropout_suppresses_advisories_preserves_evidence():
    d = resolve_telemetry_dropout(gap_detected=True)
    assert d.advisories_suppressed is True
    assert d.evidence_preserved is True
    assert d.duplicate_session_created is False
    assert d.activity_completed is False
    assert d.recovery_state == "telemetry_lost"


def test_no_dropout_is_live():
    d = resolve_telemetry_dropout(gap_detected=False)
    assert d.advisories_suppressed is False and d.recovery_state == "live"
    assert d.activity_completed is False  # a dropout never completes an activity either way
