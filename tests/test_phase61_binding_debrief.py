"""Phase 61 — binding, debrief handover, cumulative update, Command Centre return (task items 20-23)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.activity_binding import DebriefKind, EvidenceClassification as EC
from strategy.binding_debrief_workflow import (
    build_binding_workflow, decide_debrief_launch, plan_cumulative_event_update,
    resolve_command_centre_return,
)


# --- binding workflow ------------------------------------------------------

def test_binding_requires_explicit_selection_never_newest():
    sessions = [
        {"session_id": "match_old", "car": "P", "track": "Fuji", "clean_laps": 8, "end": "2026-06-01"},
        {"session_id": "mismatch_new", "car": "GT3", "track": "Spa", "clean_laps": 8, "end": "2026-06-20"},
    ]
    vm = build_binding_workflow(sessions, {"car": "P", "track": "Fuji"})
    assert vm.requires_explicit_selection is True and vm.auto_bind_forbidden is True
    assert vm.candidates[0]["session_id"] == "match_old"  # context beats recency


# --- debrief launch --------------------------------------------------------

def test_debrief_requires_binding_first():
    assert decide_debrief_launch(T.SETUP_EXPERIMENT, session_bound=False).ready is False
    ok = decide_debrief_launch(T.SETUP_EXPERIMENT, session_bound=True)
    assert ok.ready is True and ok.debrief_kind == DebriefKind.PRACTICE_RUN


def test_debrief_routes_qualifying_and_race():
    assert decide_debrief_launch(T.QUALIFYING, session_bound=True).debrief_kind == DebriefKind.QUALIFYING_REVIEW
    assert decide_debrief_launch(T.RACE, session_bound=True).debrief_kind == DebriefKind.RACE_DEBRIEF


# --- cumulative update -----------------------------------------------------

def test_cumulative_update_requires_confirmed_outcome():
    # unconfirmed debrief updates nothing
    unconfirmed = plan_cumulative_event_update(T.SETUP_EXPERIMENT, debrief_confirmed=False,
                                               classification=EC.VALID)
    assert unconfirmed.can_update is False and unconfirmed.updated_domains == ()
    # confirmed + valid -> updates the activity's domains
    confirmed = plan_cumulative_event_update(T.SETUP_EXPERIMENT, debrief_confirmed=True,
                                             classification=EC.VALID)
    assert confirmed.can_update is True and "setup_base" in confirmed.updated_domains


def test_cumulative_update_invalid_updates_nothing_even_confirmed():
    for cls in (EC.INVALID, EC.MISMATCHED, EC.ABANDONED):
        u = plan_cumulative_event_update(T.SETUP_EXPERIMENT, debrief_confirmed=True, classification=cls)
        assert u.can_update is False and u.updated_domains == ()


# --- Command Centre return -------------------------------------------------

def test_return_refreshes_from_canonical_truth():
    assert resolve_command_centre_return(debrief_complete=True).refresh_required is True
    assert resolve_command_centre_return(debrief_complete=False).refresh_required is False


def test_binding_deterministic():
    a = build_binding_workflow([{"session_id": "s", "car": "P", "track": "F", "clean_laps": 5}], {"car": "P"})
    b = build_binding_workflow([{"session_id": "s", "car": "P", "track": "F", "clean_laps": 5}], {"car": "P"})
    assert a.fingerprint == b.fingerprint
