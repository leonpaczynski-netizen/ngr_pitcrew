"""Phase 55 — session-end detection, telemetry recovery, binding handover (task items 20-24)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.activity_binding import DebriefKind
from strategy.live_session_detection import (
    SessionEndState as SE, detect_session_end, build_binding_handover, handle_telemetry_dropout,
)


# --- session-end detection -------------------------------------------------

def test_live_run_not_ended():
    d = detect_session_end(was_running=True, telemetry_fresh=True, session_state="running",
                           valid_laps=3, evidence_permitted=True)
    assert d.state == SE.LIVE and d.binding_required is False


def test_ended_with_evidence_becomes_binding_required_not_completed():
    d = detect_session_end(was_running=True, telemetry_fresh=False, session_state="ended",
                           valid_laps=8, evidence_permitted=True)
    assert d.state == SE.BINDING_REQUIRED
    assert d.binding_required is True
    assert d.activity_completed is False    # session end NEVER completes an activity
    assert d.snapshot_frozen is True


def test_ended_without_evidence_is_insufficient():
    d = detect_session_end(was_running=True, telemetry_fresh=False, session_state="ended",
                           valid_laps=0, evidence_permitted=True)
    assert d.state == SE.ENDED_INSUFFICIENT and d.binding_required is False


def test_ended_but_not_evidence_permitted_is_insufficient():
    # a mismatched run that ended produced no bindable evidence
    d = detect_session_end(was_running=True, telemetry_fresh=False, session_state="ended",
                           valid_laps=8, evidence_permitted=False)
    assert d.state == SE.ENDED_INSUFFICIENT


def test_session_end_never_completes_activity():
    for tf in (True, False):
        for ss in ("running", "ended"):
            for vl in (0, 8):
                for ep in (True, False):
                    d = detect_session_end(was_running=True, telemetry_fresh=tf, session_state=ss,
                                           valid_laps=vl, evidence_permitted=ep)
                    assert d.activity_completed is False


# --- binding handover ------------------------------------------------------

def test_binding_handover_ranks_and_routes_debrief():
    sessions = [{"session_id": "match", "car": "P", "track": "Fuji", "clean_laps": 8, "end": "2026-06-01"}]
    h = build_binding_handover(T.SETUP_EXPERIMENT, sessions, {"car": "P", "track": "Fuji"})
    assert h.binding_required is True
    assert h.ranking["auto_bind_forbidden"] is True and h.ranking["requires_explicit_selection"] is True
    assert h.debrief_kind == DebriefKind.PRACTICE_RUN


def test_binding_handover_qualifying_routes_review():
    h = build_binding_handover(T.QUALIFYING, [], {})
    assert h.debrief_kind == DebriefKind.QUALIFYING_REVIEW


# --- telemetry dropout -----------------------------------------------------

def test_telemetry_dropout_no_completion_no_duplicate():
    d = handle_telemetry_dropout(gap_detected=True)
    assert d.advisories_suppressed is True
    assert d.evidence_preserved is True
    assert d.duplicate_session_created is False
    assert d.activity_completed is False


def test_no_gap_is_live():
    assert handle_telemetry_dropout(gap_detected=False).recovery_state == "live"
