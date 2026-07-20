"""Phase 57 — live runtime session start/end transitions (task items 21-22, 25)."""
from __future__ import annotations

from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime
from strategy.live_runtime_authority import (
    LiveRuntimeTransition as TR, evaluate_runtime_transition,
)


def _eval(now=100.5, **tk):
    fields = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                  lap=3, session_state="running", current_segment="T1", fuel="80", tyre_compound="MR",
                  valid_laps=5, last_packet_monotonic=100.0)
    fields.update(tk)
    tracker = TrackerRuntimeSnapshot(**fields)
    ctx = SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type="setup_experiment",
                                  discipline="race", car="Porsche", track="Fuji", layout="Full",
                                  expected_setup_fingerprint="fp", event_context_digest="", target_laps=8)
    return evaluate_live_runtime(tracker, ctx, now_monotonic=now)


def test_start_from_idle():
    r = evaluate_runtime_transition(_eval(), was_running=False)
    assert r.transition == TR.STARTED and r.now_running is True


def test_running_continues():
    r = evaluate_runtime_transition(_eval(), was_running=True)
    assert r.transition == TR.RUNNING and r.now_running is True


def test_session_end_on_stale_while_running_is_binding_required_not_completed():
    r = evaluate_runtime_transition(_eval(now=110.0, valid_laps=8), was_running=True)  # 10s old -> stale
    assert r.transition == TR.ENDED_BINDING_REQUIRED
    assert r.activity_completed is False
    assert r.session_end is not None and r.session_end.binding_required is True


def test_session_end_state_ended_while_running():
    r = evaluate_runtime_transition(_eval(session_state="ended", valid_laps=8), was_running=True)
    assert r.transition == TR.ENDED_BINDING_REQUIRED and r.activity_completed is False


def test_session_end_without_evidence_is_insufficient():
    r = evaluate_runtime_transition(_eval(session_state="ended", valid_laps=0), was_running=True)
    assert r.transition == TR.ENDED_INSUFFICIENT and r.activity_completed is False


def test_stale_while_not_running_is_stale_no_end():
    r = evaluate_runtime_transition(_eval(now=110.0), was_running=False)
    assert r.transition == TR.STALE and r.session_end is None


def test_hard_mismatch_blocks():
    r = evaluate_runtime_transition(_eval(applied_setup_fingerprint="other"), was_running=True)
    assert r.transition == TR.BLOCKED


def test_not_selected():
    from strategy.gt7_live_adapter import TrackerRuntimeSnapshot as TS, SelectedActivityContext as SC, evaluate_live_runtime as ev
    e = ev(TS(car="P", track="F", last_packet_monotonic=100.0), SC(activity_id=""), now_monotonic=100.2)
    assert evaluate_runtime_transition(e, was_running=False).transition == TR.NOT_SELECTED


def test_transition_never_completes_activity():
    for wr in (True, False):
        for ss in ("running", "ended"):
            for now in (100.5, 110.0):
                r = evaluate_runtime_transition(_eval(now=now, session_state=ss), was_running=wr)
                assert r.activity_completed is False


def test_transition_deterministic():
    a = evaluate_runtime_transition(_eval(), was_running=True)
    b = evaluate_runtime_transition(_eval(), was_running=True)
    assert a.fingerprint == b.fingerprint
