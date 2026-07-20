"""Phase 52 — session binding, debrief handover, cumulative update (task items 16-19)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.activity_binding import (
    DebriefKind, EvidenceClassification as EC, rank_activity_sessions, debrief_kind_for,
    assess_debrief_readiness, plan_cumulative_update,
)


# --- candidate ranking (reuses canonical ranker) ---------------------------

def test_ranking_never_auto_binds_and_prefers_context_over_recency():
    sessions = [
        {"session_id": "old_match", "car": "P", "track": "Fuji", "layout_id": "fc", "compound": "MR",
         "clean_laps": 8, "start": "2026-06-01", "end": "2026-06-01"},
        {"session_id": "new_mismatch", "car": "GT3", "track": "Spa", "layout_id": "gp", "compound": "SS",
         "clean_laps": 8, "start": "2026-06-20", "end": "2026-06-20"},
    ]
    ctx = {"car": "P", "track": "Fuji", "layout_id": "fc", "compound": "MR"}
    ranking = rank_activity_sessions(sessions, ctx)
    assert ranking.auto_bind_forbidden is True and ranking.requires_explicit_selection is True
    # the context-matching (older) session ranks above the newer mismatched one
    assert ranking.candidates[0]["session_id"] == "old_match"


# --- debrief handover ------------------------------------------------------

def test_debrief_kind_by_activity_type():
    assert debrief_kind_for(T.SETUP_EXPERIMENT) == DebriefKind.PRACTICE_RUN
    assert debrief_kind_for(T.QUALIFYING) == DebriefKind.QUALIFYING_REVIEW
    assert debrief_kind_for(T.QUALIFYING_SIMULATION) == DebriefKind.QUALIFYING_REVIEW
    assert debrief_kind_for(T.RACE) == DebriefKind.RACE_DEBRIEF


def test_debrief_requires_binding_first():
    r = assess_debrief_readiness(T.SETUP_EXPERIMENT, session_bound=False)
    assert r.ready is False and r.debrief_kind == DebriefKind.PRACTICE_RUN
    ok = assess_debrief_readiness(T.SETUP_EXPERIMENT, session_bound=True)
    assert ok.ready is True


# --- cumulative update gate ------------------------------------------------

def test_valid_evidence_updates_domains():
    u = plan_cumulative_update(T.SETUP_EXPERIMENT, EC.VALID)
    assert u.can_update is True and u.labelled_limited is False
    assert "setup_base" in u.updated_domains and "working_window" in u.updated_domains


def test_limited_evidence_updates_but_labelled():
    u = plan_cumulative_update(T.LONG_RACE_RUN, EC.LIMITED)
    assert u.can_update is True and u.labelled_limited is True
    assert "race_pace" in u.updated_domains


def test_invalid_mismatched_abandoned_update_nothing():
    for cls in (EC.INVALID, EC.MISMATCHED, EC.ABANDONED):
        u = plan_cumulative_update(T.SETUP_EXPERIMENT, cls)
        assert u.can_update is False
        assert u.updated_domains == ()  # cannot strengthen confidence


def test_coaching_valid_update_never_touches_setup():
    u = plan_cumulative_update(T.COACHING_RUN, EC.VALID)
    assert "driver_coaching" in u.updated_domains
    assert "setup_base" not in u.updated_domains and "working_window" not in u.updated_domains


def test_cumulative_update_deterministic():
    a = plan_cumulative_update(T.SETUP_EXPERIMENT, EC.VALID)
    b = plan_cumulative_update(T.SETUP_EXPERIMENT, EC.VALID)
    assert a.fingerprint == b.fingerprint
