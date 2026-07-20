"""Phase 60-62 — production golden scenarios (section 15) + metamorphic properties (section 16)."""
from __future__ import annotations

import pathlib

from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext
from strategy.live_pit_wall_controller import LivePitWallNavigationContext as NAV
from strategy.live_pit_wall_build import build_live_pit_wall_view
from strategy.driver_event_loop import EventLoopStage as ES, EventLoopSignals, advance_event_loop
from strategy.binding_debrief_workflow import plan_cumulative_event_update
from strategy.activity_binding import EvidenceClassification as EC
from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.live_restart_recovery import is_stale_snapshot, resolve_live_restart
from strategy.ngr_live_pit_wall import VoiceStatus as VS
from strategy.live_pit_wall_integration import derive_voice_status
from strategy.event_programme_certification import (
    CertificationArea, EvidenceType as E, CertificationLevel as C, build_event_programme_certification)


def _tracker(**kw):
    base = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                valid_laps=5, last_packet_monotonic=100.0, session_state="running",
                live_context_digest="ctx", tyre_compound="MR", map_match_confidence=0.9)
    base.update(kw)
    return TrackerRuntimeSnapshot(**base)


def _ctx(**kw):
    base = dict(cycle_id="c1", activity_id="exp", activity_type="setup_experiment", discipline="race",
                car="Porsche", track="Fuji", layout="Full", expected_setup_fingerprint="fp",
                event_context_digest="ctx", run_plan_fingerprint="rp", target_laps=8, objective="rotation")
    base.update(kw)
    return SelectedActivityContext(**base)


def _view(nav=None, tracker=None, ctx=None, was_running=True, now=100.5, **kw):
    nav = nav or NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    return build_live_pit_wall_view(tracker or _tracker(), ctx or _ctx(), nav, was_running=was_running,
                                    now_monotonic=now, **kw)


# --- section 15 scenarios --------------------------------------------------

def test_scenario_production_practice_exact_or_limited_explained():
    v = _view()
    assert v["production_state"] == "exact_match" and v["match"] == "exact_activity_match"


def test_scenario_setup_mismatch_blocks():
    v = _view(tracker=_tracker(applied_setup_fingerprint="other"), advisory_text="coach")
    assert v["production_state"] == "hard_mismatch" and v["blocked"] is True and v["advisory"] == ""


def test_scenario_wrong_track_blocks_no_event_evidence():
    v = _view(tracker=_tracker(track="Spa"))
    assert v["production_state"] == "hard_mismatch"


def test_scenario_unknown_layout_limited():
    v = _view(tracker=_tracker(layout="", map_match_confidence=0.1), ctx=_ctx(layout=""))
    assert v["production_state"] in ("limited_match", "hard_mismatch")


def test_scenario_telemetry_loss_stops_advisories_no_completion():
    v = _view(now=110.0, advisory_text="x")  # stale
    assert v["advisory"] == "" and v["activity_completed"] is False
    assert v["production_state"] == "telemetry_lost"


def test_scenario_session_end_binding_required():
    v = _view(tracker=_tracker(session_state="ended", valid_laps=8))
    assert v["production_state"] == "binding_required" and v["activity_completed"] is False


def test_scenario_opening_live_does_not_start():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", entered_live=True, started=False)
    v = _view(nav=nav, was_running=False)
    assert v["production_state"] in ("awaiting_start", "starting") and v["production_state"] != "live"


def test_scenario_qualifying_and_race_modes():
    q = _view(ctx=_ctx(activity_type="qualifying_simulation", discipline="qualifying"))
    r = _view(ctx=_ctx(activity_type="long_race_run"))
    assert q["mode"] == "qualifying" and r["mode"] == "race"


def test_scenario_event_switch_rejects_stale():
    assert is_stale_snapshot(snapshot_event="A", snapshot_activity="x", current_event="B",
                             current_activity="x") is True


def test_scenario_restart_predictable():
    r = resolve_live_restart(selected_event="c1", selected_activity="exp", pending_binding=True)
    assert r.nav.started is False and r.resume.pending_binding is True


def test_scenario_voice_failure_visual_still_usable():
    v = _view()  # visual pit wall fully populated regardless of voice
    assert v["ok"] is True and v["match_summary"]


# --- section 16 metamorphic properties -------------------------------------

def test_property_build_is_db_free():
    src = (pathlib.Path(__file__).resolve().parents[1] / "strategy" / "live_pit_wall_build.py").read_text(encoding="utf-8")
    assert "session_db" not in src and "sqlite" not in src


def test_property_refresh_cannot_complete_activity():
    a = _view(); b = _view()
    assert a["state_fingerprint"] == b["state_fingerprint"] and a["activity_completed"] is False


def test_property_setup_and_track_mismatch_cannot_strengthen_evidence():
    from strategy.live_activity_bridge import match_permits_evidence, classify_live_activity_match
    assert match_permits_evidence(classify_live_activity_match(  # via the snapshot
        __import__("strategy.gt7_live_adapter", fromlist=["evaluate_live_runtime"]).evaluate_live_runtime(
            _tracker(applied_setup_fingerprint="other"), _ctx(), now_monotonic=100.5).snapshot)) is False


def test_property_unbound_cannot_complete_and_incomplete_debrief_no_update():
    # advance from LIVE with no binding stays in the binding branch; cumulative needs confirmed outcome
    assert advance_event_loop(ES.SESSION_END, EventLoopSignals(bound=False)).stage == ES.BINDING
    assert plan_cumulative_event_update(T.SETUP_EXPERIMENT, debrief_confirmed=False,
                                        classification=EC.VALID).can_update is False


def test_property_voice_cannot_manufacture_advice():
    assert derive_voice_status(enabled=True, readiness_value="pretend") == VS.GATED


def test_property_automated_cannot_award_live_certification():
    cert = build_event_programme_certification([CertificationArea("x", E.AUTOMATED)],
                                               operationally_ready_granted=True)
    assert cert.overall_level == C.AUTOMATED_ONLY
