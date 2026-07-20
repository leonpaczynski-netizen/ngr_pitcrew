"""Phase 54-56 — golden behavioural scenarios + metamorphic properties (task sections 14-15)."""
from __future__ import annotations

from data.session_db import SessionDB
from strategy.event_preparation_cycle import PreparationActivityType as T, PreparationActivityState as PS
from strategy.live_activity import LiveActivityState as L
from strategy.canonical_activity_state import ActivityFact, derive_activity_state
from strategy.setup_convergence import SetupConvergenceState as CS
from strategy.strategy_maturity import StrategyMaturity as M
from strategy.setup_strategy_readiness import (
    derive_setup_lock_readiness, derive_strategy_finalisation_readiness)
from strategy.live_activity_bridge import LiveActivityRuntimeSnapshot, classify_live_activity_match, LiveActivityMatch
from strategy.live_session_detection import detect_session_end, SessionEndState
from strategy.event_revision_impact import assess_event_revision
from strategy.setup_lock_reopen import assess_lock_reopen
from strategy.event_programme_certification import (
    CertificationArea, EvidenceType as E, CertificationLevel as C, build_event_programme_certification)


def _cycle(db, cid="c1"):
    db.upsert_preparation_cycle({"cycle_id": cid, "event_name": "Cup", "track": "Fuji", "car": "P",
                                 "official_race_date": "2026-06-21", "format_profile_id": "multiweek",
                                 "explicit_state": "active"})


def _session(db, laps=8):
    sid = db.open_session(car_id=1, track="Fuji", session_type="Practice", car_name="P")
    db._conn.execute("UPDATE sessions SET total_laps=? WHERE CAST(id AS TEXT)=?", (laps, str(sid)))
    db._conn.commit()
    return sid


# --- section 14 scenarios (through real DB) --------------------------------

def test_scenario_pending_binding_then_debrief_then_clear():
    db = SessionDB(":memory:")
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    sid = _session(db)
    assert db.build_command_centre_truth("c1")["pending_binding"] is True
    db.bind_session_to_activity("exp", sid, "c1")
    t = db.build_command_centre_truth("c1")
    assert t["pending_binding"] is False and t["pending_debrief"] is True
    db.close()


def test_scenario_lock_readiness_does_not_lock():
    r = derive_setup_lock_readiness("race", CS.LOCK_READY.value)
    assert r.lock_eligible is True and r.is_locked is False


def test_scenario_strategy_readiness_does_not_finalise():
    r = derive_strategy_finalisation_readiness(M.FINALISATION_READY.value)
    assert r.finalisation_eligible is True and r.is_finalised is False


def test_scenario_event_revision_caps_evidence_keeps_history():
    old = {"tyre_multiplier": "1"}
    i = assess_event_revision(old, {"tyre_multiplier": "5"})
    assert not i.prior_evidence_compatible and i.strategy_recalc_required
    assert old == {"tyre_multiplier": "1"}  # completed/immutable inputs unchanged


def test_scenario_live_match_and_setup_mismatch_blocks():
    def _snap(**kw):
        base = dict(activity_selected=True, activity_id="exp", telemetry_fresh=True, car_expected="P",
                    car_live="P", track_expected="Fuji", track_live="Fuji", layout_expected="F",
                    layout_live="F", discipline_expected="race", discipline_live="race",
                    expected_setup_fingerprint="fp", live_setup_fingerprint="fp",
                    event_context_digest="c", live_context_digest="c", tyre_compound="MR",
                    run_plan_fingerprint="rp")
        base.update(kw)
        return LiveActivityRuntimeSnapshot(**base)
    assert classify_live_activity_match(_snap()).match == LiveActivityMatch.EXACT_ACTIVITY_MATCH
    assert classify_live_activity_match(_snap(live_setup_fingerprint="x")).match == LiveActivityMatch.SETUP_MISMATCH


def test_scenario_session_end_is_binding_required_not_completed():
    d = detect_session_end(was_running=True, telemetry_fresh=False, session_state="ended",
                           valid_laps=8, evidence_permitted=True)
    assert d.state == SessionEndState.BINDING_REQUIRED and d.activity_completed is False


def test_scenario_noisy_lap_vs_critical_regression_reopen():
    assert assess_lock_reopen(noisy_lap=True).eligible is False
    assert assess_lock_reopen(corroborated_regression=True, critical_instability=True).eligible is True


# --- section 15 metamorphic properties -------------------------------------

def test_property_home_refresh_cannot_change_pending_state():
    db = SessionDB(":memory:")
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    _session(db)
    a = db.build_command_centre_truth("c1")
    b = db.build_command_centre_truth("c1")
    assert a["fingerprint"] == b["fingerprint"]  # refresh is pure; cannot create/clear pending
    db.close()


def test_property_unbound_session_cannot_complete_activity():
    f = ActivityFact("a", T.SETUP_EXPERIMENT, state=PS.COMPLETED, has_binding=False, session_ended=True)
    assert derive_activity_state(f).live_state != L.COMPLETED


def test_property_bound_without_debrief_is_debrief_required():
    f = ActivityFact("a", T.SETUP_EXPERIMENT, state=PS.IN_PROGRESS, has_binding=True, has_debrief_outcome=False)
    assert derive_activity_state(f).live_state == L.DEBRIEF_REQUIRED


def test_property_lock_readiness_cannot_create_lock():
    assert derive_setup_lock_readiness("race", CS.LOCK_READY.value).is_locked is False


def test_property_strategy_readiness_cannot_finalise():
    assert derive_strategy_finalisation_readiness(M.FINALISATION_READY.value).is_finalised is False


def test_property_automated_cannot_award_live_certification():
    cert = build_event_programme_certification(
        [CertificationArea("home", E.AUTOMATED), CertificationArea("live", E.AUTOMATED)],
        operationally_ready_granted=True)
    assert cert.overall_level == C.AUTOMATED_ONLY


def test_property_replay_cannot_award_visual_certification():
    cert = build_event_programme_certification([CertificationArea("home", E.REPLAY)])
    assert cert.overall_level == C.REPLAY_VALIDATED  # below VISUAL_UAT_*


def test_property_offscreen_cannot_award_live_operational():
    cert = build_event_programme_certification([CertificationArea("home", E.OFFSCREEN)],
                                               operationally_ready_granted=True)
    assert cert.overall_level == C.OFFSCREEN_VALIDATED


def test_property_selecting_event_cannot_change_evidence():
    from strategy.active_cycle_resolution import CycleCandidate, resolve_active_cycle
    cands = [CycleCandidate("a", explicit_state="active"), CycleCandidate("b", explicit_state="active")]
    assert (resolve_active_cycle(cands).as_semantic_payload()["candidates"]
            == resolve_active_cycle(cands, selected_cycle_id="a").as_semantic_payload()["candidates"])
