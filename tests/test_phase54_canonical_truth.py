"""Phase 54 — canonical activity truth + consistency (task test items 5-12)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T, PreparationActivityState as PS
from strategy.live_activity import LiveActivityState as L
from strategy.canonical_activity_state import (
    ActivityFact, derive_pending_binding, derive_pending_debrief, derive_activity_state,
    ConsistencyInputs, ConsistencySeverity, check_consistency,
)


def _fact(**kw):
    base = dict(activity_id="a1", activity_type=T.SETUP_EXPERIMENT, state=PS.IN_PROGRESS)
    base.update(kw)
    return ActivityFact(**base)


# --- pending binding -------------------------------------------------------

def test_pending_binding_true_when_run_ended_candidates_no_binding():
    f = _fact(session_ended=True, candidate_session_count=1, has_binding=False)
    assert derive_pending_binding(f).pending is True


def test_pending_binding_false_without_ended_run():
    assert derive_pending_binding(_fact(session_ended=False, candidate_session_count=1)).pending is False


def test_pending_binding_false_when_telemetry_exists_but_run_not_ended():
    # telemetry existing alone is NOT enough
    f = _fact(session_ended=False, candidate_session_count=5)
    assert derive_pending_binding(f).pending is False


def test_pending_binding_false_when_already_bound():
    assert derive_pending_binding(_fact(session_ended=True, candidate_session_count=1,
                                        has_binding=True)).pending is False


def test_pending_binding_false_for_non_telemetry_activity():
    f = _fact(activity_type=T.RACE_STRATEGY_MEETING, session_ended=True, candidate_session_count=1)
    assert derive_pending_binding(f).pending is False


def test_pending_binding_false_when_abandoned():
    assert derive_pending_binding(_fact(state=PS.CANCELLED, session_ended=True,
                                        candidate_session_count=1)).pending is False


# --- pending debrief -------------------------------------------------------

def test_pending_debrief_true_when_bound_no_outcome():
    f = _fact(has_binding=True, has_debrief_outcome=False)
    assert derive_pending_debrief(f).pending is True


def test_pending_debrief_false_without_binding():
    assert derive_pending_debrief(_fact(has_binding=False)).pending is False


def test_pending_debrief_false_when_outcome_recorded():
    assert derive_pending_debrief(_fact(has_binding=True, has_debrief_outcome=True)).pending is False


# --- canonical live state --------------------------------------------------

def test_live_state_binding_required():
    f = _fact(session_ended=True, candidate_session_count=1, has_binding=False)
    assert derive_activity_state(f).live_state == L.BINDING_REQUIRED


def test_live_state_debrief_required():
    f = _fact(has_binding=True, has_debrief_outcome=False)
    assert derive_activity_state(f).live_state == L.DEBRIEF_REQUIRED


def test_live_state_completed_requires_binding_and_outcome():
    f = _fact(state=PS.COMPLETED, has_binding=True, has_debrief_outcome=True)
    assert derive_activity_state(f).live_state == L.COMPLETED
    # persisted COMPLETED without an outcome is NOT canonically completed
    f2 = _fact(state=PS.COMPLETED, has_binding=True, has_debrief_outcome=False)
    assert derive_activity_state(f2).live_state != L.COMPLETED


def test_live_state_deterministic():
    f = _fact(state=PS.IN_PROGRESS)
    assert derive_activity_state(f).fingerprint == derive_activity_state(f).fingerprint


# --- consistency -----------------------------------------------------------

def test_completed_without_binding_is_critical():
    f = _fact(state=PS.COMPLETED, has_binding=False)
    r = check_consistency([f], ConsistencyInputs())
    kinds = {x.kind for x in r.findings}
    assert "completed_without_binding" in kinds and r.consistent is False


def test_debrief_without_session_is_critical():
    f = _fact(state=PS.IN_PROGRESS, has_binding=False, has_debrief_outcome=True)
    r = check_consistency([f], ConsistencyInputs())
    assert "debrief_without_session" in {x.kind for x in r.findings}


def test_two_active_activities_is_critical():
    facts = [_fact(activity_id="a", state=PS.IN_PROGRESS), _fact(activity_id="b", state=PS.IN_PROGRESS)]
    r = check_consistency(facts, ConsistencyInputs())
    assert "two_active_activities" in {x.kind for x in r.findings}


def test_locked_without_record_and_strategy_final_without_race_lock():
    r = check_consistency([], ConsistencyInputs(setup_locked=True, has_explicit_lock_record=False,
                                                strategy_finalised=True, race_setup_locked=False))
    kinds = {x.kind for x in r.findings}
    assert "locked_without_record" in kinds and "strategy_final_without_race_lock" in kinds


def test_selected_cycle_missing_is_flagged():
    r = check_consistency([], ConsistencyInputs(selected_cycle_exists=False))
    assert "selected_cycle_missing" in {x.kind for x in r.findings}


def test_cross_cycle_binding_and_wrong_discipline():
    r = check_consistency([], ConsistencyInputs(binding_cross_cycle_activity_ids=("x",),
                                                debrief_wrong_discipline_activity_ids=("y",)))
    kinds = {x.kind for x in r.findings}
    assert "binding_cross_cycle" in kinds and "debrief_wrong_discipline" in kinds


def test_consistency_never_repairs_and_is_pure():
    f = _fact(state=PS.COMPLETED, has_binding=False)
    check_consistency([f], ConsistencyInputs())
    assert f.state == PS.COMPLETED and f.has_binding is False  # inputs unchanged


def test_clean_state_is_consistent():
    f = _fact(state=PS.COMPLETED, has_binding=True, has_debrief_outcome=True)
    r = check_consistency([f], ConsistencyInputs())
    assert r.consistent is True and not [x for x in r.findings if x.severity == ConsistencySeverity.CRITICAL]
