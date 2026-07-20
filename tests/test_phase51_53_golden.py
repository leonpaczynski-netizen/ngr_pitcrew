"""Phase 51-53 — golden behavioural scenarios + metamorphic properties (task sections 13-14)."""
from __future__ import annotations

from strategy.active_cycle_resolution import CycleCandidate, resolve_active_cycle, ActiveCycleResolutionState as R
from strategy.event_command_centre import build_event_command_centre, NextActionCategory as NA
from strategy.live_activity import ActivityExecutionContext, assess_start_readiness, assess_completion, LiveActivityState as L
from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.activity_binding import rank_activity_sessions, plan_cumulative_update, EvidenceClassification as EC
from strategy.programme_resume import build_resume_state, classify_interrupted_activity, resolve_telemetry_dropout, InterruptedActivityResolution as IR
from strategy.event_revision_impact import assess_event_revision
from strategy.setup_lock_reopen import assess_lock_reopen, SetupLockReopenReason as RR
from strategy.operational_certification import build_certification, CertificationArea, ProofLevel as P, CertificationState as C


def _report():
    return {"ok": True, "cycle": {"event_name": "Cup R3", "series": "NGR", "round": "R3", "state": "active",
                                  "current_phase": "setup_development", "official_race_date": "2026-06-21",
                                  "days_until_race": 12},
            "next_action": {"headline": "Build race_setup evidence"}, "timeline": [],
            "progress": {"valid_laps": 100}, "readiness": [], "setup": {"race": "improving"},
            "strategy": {"maturity": "developing"}}


# --- section 13 scenarios --------------------------------------------------

def test_scenario_multiple_active_events_require_selection():
    r = resolve_active_cycle([CycleCandidate("a", explicit_state="active", official_race_date="2026-06-21"),
                              CycleCandidate("b", explicit_state="active", official_race_date="2026-07-21")])
    assert r.state == R.EVENT_REQUIRES_SELECTION and r.resolved_cycle_id == ""


def test_scenario_restart_during_practice_shows_interrupted_not_complete():
    r = build_resume_state(selected_cycle_id="c1", interrupted_activity_id="exp", interrupted_state=L.COMPLETED)
    assert r.interrupted_state == L.INTERRUPTED


def test_scenario_telemetry_loss_stops_advisories_evidence_incomplete():
    d = resolve_telemetry_dropout(gap_detected=True)
    assert d.advisories_suppressed and not d.activity_completed and d.evidence_preserved


def test_scenario_pending_binding_is_home_primary_action():
    r = resolve_active_cycle([CycleCandidate("a", explicit_state="active")], selected_cycle_id="a")
    cc = build_event_command_centre(r, _report(), pending_binding=True)
    assert cc.next_action.category == NA.BIND_SESSION


def test_scenario_event_revision_tyre_multiplier_identifies_impact():
    i = assess_event_revision({"tyre_multiplier": "1"}, {"tyre_multiplier": "5"})
    assert i.lock_reopen_required and i.strategy_recalc_required and not i.prior_evidence_compatible


def test_scenario_critical_regression_after_lock_recommends_reopen():
    assert assess_lock_reopen(corroborated_regression=True, critical_instability=True).eligible is True


def test_scenario_noisy_lap_after_lock_does_not_reopen():
    assert assess_lock_reopen(noisy_lap=True).eligible is False


def test_scenario_long_gap_no_false_urgency():
    r = resolve_active_cycle([CycleCandidate("a", explicit_state="active", official_race_date="2026-07-31")],
                             selected_cycle_id="a", now_date="2026-06-01")
    rep = dict(_report()); rep["cycle"]["days_until_race"] = 60
    cc = build_event_command_centre(r, rep, now_date="2026-06-01")
    assert cc.days_until_race == 60 and cc.next_action.category == NA.NEXT_ACTIVITY  # no urgent action


def test_scenario_official_qualifying_and_race_modes():
    from strategy.live_activity_modes import build_qualifying_live_view, build_race_live_view, LiveDensity
    assert build_qualifying_live_view().density == LiveDensity.MINIMAL
    assert build_race_live_view().density == LiveDensity.SAFETY


# --- section 14 metamorphic properties -------------------------------------

def test_property_home_refresh_cannot_advance_activity():
    r = resolve_active_cycle([CycleCandidate("a", explicit_state="active")], selected_cycle_id="a")
    a = build_event_command_centre(r, _report())
    b = build_event_command_centre(r, _report())
    assert a.fingerprint == b.fingerprint  # pure — repeated refresh changes nothing


def test_property_selecting_event_cannot_change_its_evidence():
    cands = [CycleCandidate("a", explicit_state="active"), CycleCandidate("b", explicit_state="active")]
    assert (resolve_active_cycle(cands).as_semantic_payload()["candidates"]
            == resolve_active_cycle(cands, selected_cycle_id="a").as_semantic_payload()["candidates"])


def test_property_restart_cannot_convert_active_to_complete():
    assert build_resume_state(selected_cycle_id="c", interrupted_activity_id="x",
                              interrupted_state=L.COMPLETED).interrupted_state == L.INTERRUPTED


def test_property_telemetry_loss_cannot_increase_confidence():
    # a dropout preserves (not strengthens) evidence; and invalid-classified evidence updates nothing
    assert resolve_telemetry_dropout(gap_detected=True).evidence_preserved is True
    assert plan_cumulative_update(T.SETUP_EXPERIMENT, EC.INVALID).updated_domains == ()


def test_property_newest_session_cannot_auto_bind():
    ranking = rank_activity_sessions(
        [{"session_id": "new", "car": "P", "track": "Fuji", "clean_laps": 8, "end": "2026-06-20"}],
        {"car": "P", "track": "Fuji"})
    assert ranking.auto_bind_forbidden is True and ranking.requires_explicit_selection is True


def test_property_invalid_activity_cannot_update_maturity():
    for cls in (EC.INVALID, EC.MISMATCHED, EC.ABANDONED):
        assert plan_cumulative_update(T.LONG_RACE_RUN, cls).can_update is False


def test_property_independent_confirmed_regression_is_reopen_eligible():
    assert assess_lock_reopen(independent_corroborated_evidence=True).eligible is True


def test_property_event_revision_cannot_rewrite_completed_context():
    old = {"car": "P"}
    assess_event_revision(old, {"car": "GT3"})
    assert old == {"car": "P"}


def test_property_voice_certification_not_from_home_state():
    # an offscreen/automated build can never reach a live/operational certification
    cert = build_certification([CertificationArea("home", P.OFFSCREEN), CertificationArea("voice", P.AUTOMATED)],
                               operationally_ready_granted=True)
    assert cert.overall_state in (C.AUTOMATED_ONLY, C.OFFSCREEN_VALIDATED)


def test_property_start_readiness_pure_no_advance():
    ctx = ActivityExecutionContext(cycle_id="c", activity_id="a", activity_type=T.SETUP_EXPERIMENT,
                                   track="Fuji", car="P", discipline="race", run_plan_present=True,
                                   telemetry_available=True, expected_setup_fingerprint="fp",
                                   applied_setup_fingerprint="fp", setup_delta_present=True, preflight_done=True)
    assert assess_start_readiness(ctx).fingerprint == assess_start_readiness(ctx).fingerprint
