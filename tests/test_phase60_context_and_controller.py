"""Phase 60 — runtime context resolution (Audit B) + Live controller state machine (task items 4-5, 15-16)."""
from __future__ import annotations

from strategy.runtime_context_resolution import resolve_runtime_context
from strategy.gt7_live_adapter import (
    TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime)
from strategy.live_runtime_authority import evaluate_runtime_transition
from strategy.live_activity_bridge import LiveActivityMatch as MM
from strategy.live_pit_wall_controller import (
    LivePitWallRuntimeState as PS, LivePitWallNavigationContext as NAV, reduce_live_state,
)


# --- context resolution (Audit B) ------------------------------------------

def _resolve(**kw):
    base = dict(tracker_car="Porsche", tracker_track="Fuji", tracker_layout="Full",
                map_match_confidence=0.9, expected_car="Porsche", expected_track="Fuji",
                expected_layout="Full", expected_context_digest="ctx",
                applied_setup_fingerprint="fp", expected_setup_fingerprint="fp")
    base.update(kw)
    return resolve_runtime_context(**base)


def test_confirmed_context_composes_live_digest_and_allows_exact():
    r = _resolve()
    assert r.context_confirmed is True and r.live_context_digest == "ctx" and r.exact_possible is True


def test_applied_setup_is_always_flagged_a_proxy():
    r = _resolve()
    assert any("proxy" in l for l in r.limitations)  # honest: GT7 does not broadcast the setup


def test_low_map_confidence_keeps_layout_limited():
    r = _resolve(map_match_confidence=0.3)
    assert r.context_confirmed is False and r.live_context_digest == ""
    assert any("layout" in l for l in r.limitations)


def test_wrong_car_not_confirmed():
    r = _resolve(tracker_car="GT3")
    assert r.context_confirmed is False and r.exact_possible is False
    assert any("car" in l for l in r.limitations)


def test_setup_mismatch_blocks_exact_even_when_context_confirmed():
    r = _resolve(applied_setup_fingerprint="other")
    assert r.context_confirmed is True and r.exact_possible is False


def test_composed_digest_lifts_match_to_exact():
    # feeding the composed live digest into the adapter yields EXACT (not MATCH_WITH_LIMITATIONS)
    res = _resolve()
    tracker = TrackerRuntimeSnapshot(car="Porsche", track="Fuji", layout="Full",
                                     applied_setup_fingerprint=res.applied_setup_fingerprint,
                                     live_context_digest=res.live_context_digest, tyre_compound="MR",
                                     valid_laps=3, last_packet_monotonic=100.0)
    ctx = SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type="setup_experiment",
                                  discipline="race", car="Porsche", track="Fuji", layout="Full",
                                  expected_setup_fingerprint="fp", event_context_digest="ctx",
                                  run_plan_fingerprint="rp", target_laps=8)
    assert evaluate_live_runtime(tracker, ctx, now_monotonic=100.5).match.match == MM.EXACT_ACTIVITY_MATCH


def test_resolution_deterministic():
    assert _resolve().fingerprint == _resolve().fingerprint


# --- controller state machine ----------------------------------------------

def _eval(**tk):
    now = tk.pop("now", 100.5)
    fields = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                  valid_laps=5, last_packet_monotonic=100.0, session_state="running",
                  live_context_digest="ctx", tyre_compound="MR")
    fields.update(tk)
    ctx = SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type="setup_experiment",
                                  discipline="race", car="Porsche", track="Fuji", layout="Full",
                                  expected_setup_fingerprint="fp", event_context_digest="ctx",
                                  run_plan_fingerprint="rp", target_laps=8)
    return evaluate_live_runtime(TrackerRuntimeSnapshot(**fields), ctx, now_monotonic=now)


def test_no_active_event():
    assert reduce_live_state(NAV()).state == PS.NO_ACTIVE_EVENT


def test_no_selected_activity():
    assert reduce_live_state(NAV(active_event_id="c1")).state == PS.NO_SELECTED_ACTIVITY


def test_opening_live_never_starts_activity():
    # entered_live but not started -> AWAITING_START/STARTING, never LIVE
    nav = NAV(active_event_id="c1", selected_activity_id="exp", entered_live=True, started=False)
    st = reduce_live_state(nav, _eval()).state
    assert st in (PS.AWAITING_START, PS.STARTING) and st != PS.LIVE


def test_started_exact_match_is_live():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", entered_live=True, started=True)
    ev = _eval()
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert reduce_live_state(nav, ev, tr).state == PS.EXACT_MATCH


def test_limited_match_state():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    ev = _eval(live_context_digest="")  # unknown context -> limitations
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert reduce_live_state(nav, ev, tr).state == PS.LIMITED_MATCH


def test_hard_mismatch_state():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    ev = _eval(applied_setup_fingerprint="other")
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert reduce_live_state(nav, ev, tr).state == PS.HARD_MISMATCH


def test_session_end_binding_required():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    ev = _eval(session_state="ended", valid_laps=8)
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert reduce_live_state(nav, ev, tr).state == PS.BINDING_REQUIRED


def test_telemetry_lost_and_abandon_and_return():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    ev = _eval(now=110.0)  # stale
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert reduce_live_state(nav, ev, tr).state == PS.TELEMETRY_LOST
    assert reduce_live_state(NAV(active_event_id="c1", selected_activity_id="exp", abandoned=True)).state == PS.ACTIVITY_ABANDONED
    assert reduce_live_state(NAV(active_event_id="c1", selected_activity_id="exp", returning=True)).state == PS.RETURNING_TO_GARAGE


def test_reduce_never_completes_activity():
    for started in (True, False):
        for ss in ("running", "ended"):
            nav = NAV(active_event_id="c1", selected_activity_id="exp", started=started)
            ev = _eval(session_state=ss)
            tr = evaluate_runtime_transition(ev, was_running=started)
            assert reduce_live_state(nav, ev, tr).activity_completed is False


def test_reduce_deterministic():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    ev = _eval(); tr = evaluate_runtime_transition(ev, was_running=True)
    assert reduce_live_state(nav, ev, tr).fingerprint == reduce_live_state(nav, ev, tr).fingerprint
