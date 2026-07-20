"""Phase 57-59 — golden behavioural scenarios (section 15) + metamorphic properties (section 16)."""
from __future__ import annotations

from strategy.gt7_live_adapter import (
    TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime)
from strategy.live_activity_bridge import LiveActivityMatch as MM, match_permits_evidence
from strategy.live_runtime_authority import evaluate_runtime_transition, LiveRuntimeTransition as TR
from strategy.live_runtime_cache import runtime_cache_key, LiveEvaluationCadence
from strategy.ngr_live_pit_wall import build_ngr_live_pit_wall, LivePitWallMode as PM, VoiceStatus as VS
from strategy.live_pit_wall_integration import derive_voice_status, coordinate_single_advisory
from strategy.event_programme_certification import (
    CertificationArea, EvidenceType as E, CertificationLevel as C, build_event_programme_certification)


def _tracker(**kw):
    base = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                valid_laps=5, last_packet_monotonic=100.0, session_state="running")
    base.update(kw)
    return TrackerRuntimeSnapshot(**base)


def _ctx(**kw):
    base = dict(cycle_id="c1", activity_id="exp", activity_type="setup_experiment", discipline="race",
                car="Porsche", track="Fuji", layout="Full", expected_setup_fingerprint="fp", target_laps=8)
    base.update(kw)
    return SelectedActivityContext(**base)


def _ev(tracker=None, ctx=None, now=100.5):
    return evaluate_live_runtime(tracker or _tracker(), ctx or _ctx(), now_monotonic=now)


# --- section 15 scenarios --------------------------------------------------

def test_scenario_real_tracker_match_progresses_without_completion():
    ev = _ev(ctx=_ctx(event_context_digest="ctx", run_plan_fingerprint="rp"),
             tracker=_tracker(live_context_digest="ctx", tyre_compound="MR"))
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert ev.match.match == MM.EXACT_ACTIVITY_MATCH
    assert tr.activity_completed is False and tr.transition == TR.RUNNING


def test_scenario_setup_mismatch_blocks_and_suppresses_coaching():
    ev = _ev(tracker=_tracker(applied_setup_fingerprint="other"))
    pw = build_ngr_live_pit_wall(ev, evaluate_runtime_transition(ev, was_running=True),
                                 advisory_text="coach: rotate earlier")
    assert ev.match.match == MM.SETUP_MISMATCH and pw.blocked is True
    assert pw.advisory == "" and match_permits_evidence(ev.match) is False


def test_scenario_track_mismatch_no_exact_evidence():
    ev = _ev(tracker=_tracker(track="Spa"))
    assert ev.match.match == MM.TRACK_MISMATCH and match_permits_evidence(ev.match) is False


def test_scenario_unknown_layout_never_exact():
    ev = _ev(tracker=_tracker(layout=""), ctx=_ctx(layout=""))
    assert ev.match.match != MM.EXACT_ACTIVITY_MATCH


def test_scenario_practice_completion_is_binding_required_not_completed():
    ev = _ev(tracker=_tracker(session_state="ended", valid_laps=8))
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert tr.transition == TR.ENDED_BINDING_REQUIRED and tr.activity_completed is False


def test_scenario_qualifying_and_race_modes():
    q = _ev(ctx=_ctx(activity_type="qualifying_simulation", discipline="qualifying"))
    r = _ev(ctx=_ctx(activity_type="long_race_run"))
    assert build_ngr_live_pit_wall(q, evaluate_runtime_transition(q, was_running=True)).mode == PM.QUALIFYING
    assert build_ngr_live_pit_wall(r, evaluate_runtime_transition(r, was_running=True)).mode == PM.RACE


def test_scenario_telemetry_dropout_stops_advisories_incomplete():
    ev = _ev(now=110.0)  # stale
    tr = evaluate_runtime_transition(ev, was_running=False)
    pw = build_ngr_live_pit_wall(ev, tr, advisory_text="x")
    assert pw.advisory == "" and tr.activity_completed is False


def test_scenario_event_switch_invalidates_cache():
    cad = LiveEvaluationCadence(0.5)
    k1 = runtime_cache_key(_ctx(cycle_id="c1"))
    cad.should_evaluate(k1, 100.0); cad.record(k1, 100.0)
    k2 = runtime_cache_key(_ctx(cycle_id="c2", activity_id="other"))
    assert cad.should_evaluate(k2, 100.1) is True  # switching event forces re-evaluation


def test_scenario_no_active_event_does_not_attach_live_telemetry():
    ev = _ev(ctx=_ctx(activity_id=""))
    assert ev.match.match == MM.ACTIVITY_NOT_SELECTED
    pw = build_ngr_live_pit_wall(ev, evaluate_runtime_transition(ev, was_running=False))
    assert pw.mode == PM.IDLE


# --- section 16 metamorphic properties -------------------------------------

def test_property_same_sequence_same_decision():
    a = _ev(); b = _ev()
    assert a.fingerprint == b.fingerprint
    assert a.match.match == b.match.match


def test_property_ui_refresh_cannot_advance_activity():
    # re-evaluating the same tracker+ctx (a "refresh") yields the same transition; nothing advances
    ev = _ev()
    t1 = evaluate_runtime_transition(ev, was_running=True)
    t2 = evaluate_runtime_transition(ev, was_running=True)
    assert t1.fingerprint == t2.fingerprint and t1.activity_completed is False


def test_property_stale_cannot_deliver_routine_advice():
    ev = _ev(now=110.0)
    pw = build_ngr_live_pit_wall(ev, evaluate_runtime_transition(ev, was_running=True), advisory_text="x")
    assert pw.advisory == ""


def test_property_voice_settings_cannot_alter_engineering_fingerprint():
    # the runtime evaluation fingerprint is independent of voice status/settings
    ev = _ev()
    fp = ev.fingerprint
    _ = build_ngr_live_pit_wall(ev, evaluate_runtime_transition(ev, was_running=True), voice_status=VS.ELIGIBLE)
    _ = build_ngr_live_pit_wall(ev, evaluate_runtime_transition(ev, was_running=True), voice_status=VS.DISABLED)
    assert ev.fingerprint == fp  # voice choice does not enter the evaluation fingerprint


def test_property_voice_cannot_be_manufactured_by_ui():
    assert derive_voice_status(enabled=True, readiness_value="pretend_eligible") == VS.GATED


def test_property_single_advisory_never_multiple_voices():
    decisions = [{"delivered": True, "priority": 3, "message": "a"},
                 {"delivered": True, "priority": 3, "message": "b"}]
    out = coordinate_single_advisory(decisions, suppressed=False)
    assert out in ("a", "b") and "\n" not in out  # exactly one message


def test_property_automated_cannot_grant_visual_or_live():
    cert = build_event_programme_certification([CertificationArea("x", E.AUTOMATED)],
                                               operationally_ready_granted=True)
    assert cert.overall_level == C.AUTOMATED_ONLY


def test_property_replay_cannot_grant_live_gt7():
    assert build_event_programme_certification([CertificationArea("x", E.REPLAY)]).overall_level == C.REPLAY_VALIDATED
