"""Phase 58 — NGR Live Pit Wall domain (task items 15-18, 20)."""
from __future__ import annotations

from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime
from strategy.live_runtime_authority import evaluate_runtime_transition
from strategy.ngr_live_pit_wall import (
    LivePitWallMode as PM, VoiceStatus as VS, build_ngr_live_pit_wall,
)


def _pw(discipline="race", activity_type="setup_experiment", now=100.5, was_running=True, **tk):
    fields = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                  lap=3, session_state="running", current_segment="T1", fuel="80", tyre_compound="MR",
                  valid_laps=5, last_packet_monotonic=100.0)
    fields.update(tk)
    tracker = TrackerRuntimeSnapshot(**fields)
    ctx = SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type=activity_type,
                                  discipline=discipline, car="Porsche", track="Fuji", layout="Full",
                                  expected_setup_fingerprint="fp", event_context_digest="", objective="rotation",
                                  target_laps=8)
    ev = evaluate_live_runtime(tracker, ctx, now_monotonic=now)
    tr = evaluate_runtime_transition(ev, was_running=was_running)
    return build_ngr_live_pit_wall(ev, tr, event_line="NGR Porsche Cup R3 - Setup exp",
                                   voice_status=VS.DISABLED)


def test_practice_mode():
    pw = _pw(discipline="race", activity_type="setup_experiment")
    assert pw.mode == PM.PRACTICE
    assert "hold the setup constant" in pw.purpose_note.lower()


def test_qualifying_mode_low_density():
    pw = _pw(discipline="qualifying", activity_type="qualifying_simulation")
    assert pw.mode == PM.QUALIFYING


def test_race_mode():
    # discipline race but not a setup experiment -> race mode
    pw = _pw(discipline="race", activity_type="long_race_run")
    assert pw.mode == PM.RACE


def test_setup_mismatch_blocks_and_suppresses_advisory():
    pw = _pw(applied_setup_fingerprint="other")
    assert pw.blocked is True and pw.advisory_suppressed is True and pw.advisory == ""
    assert "MISMATCH" in pw.match_summary


def test_stale_telemetry_recovery_mode_suppresses_advisory():
    pw = _pw(now=110.0, was_running=False)  # stale, not previously running
    assert pw.mode == PM.RECOVERY and pw.advisory_suppressed is True
    assert "recover" in pw.next_action.lower()


def test_session_end_transition_mode():
    pw = _pw(session_state="ended", valid_laps=8)
    assert pw.mode == PM.TRANSITION
    assert "bind" in pw.next_action.lower()


def test_single_advisory_delivered_when_fresh_and_matched():
    fields = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                  valid_laps=5, last_packet_monotonic=100.0, session_state="running")
    tracker = TrackerRuntimeSnapshot(**fields)
    ctx = SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type="setup_experiment",
                                  discipline="race", car="Porsche", track="Fuji", layout="Full",
                                  expected_setup_fingerprint="fp", objective="rotation", target_laps=8)
    ev = evaluate_live_runtime(tracker, ctx, now_monotonic=100.5)
    tr = evaluate_runtime_transition(ev, was_running=True)
    pw = build_ngr_live_pit_wall(ev, tr, advisory_text="brake slightly earlier into T1")
    assert pw.advisory_suppressed is False and pw.advisory == "brake slightly earlier into T1"


def test_voice_status_comes_from_controller_not_manufactured():
    pw_disabled = _pw()
    assert pw_disabled.voice_status == VS.DISABLED
    # the pit wall only reflects the supplied voice status; it cannot set ELIGIBLE itself
    from strategy.ngr_live_pit_wall import build_ngr_live_pit_wall as build
    fields = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                  valid_laps=5, last_packet_monotonic=100.0)
    ev = evaluate_live_runtime(TrackerRuntimeSnapshot(**fields),
                               SelectedActivityContext(activity_id="exp", discipline="race", car="Porsche",
                                                       track="Fuji", layout="Full",
                                                       expected_setup_fingerprint="fp", target_laps=8),
                               now_monotonic=100.5)
    tr = evaluate_runtime_transition(ev, was_running=True)
    assert build(ev, tr, voice_status=VS.VISUAL_ONLY).voice_status == VS.VISUAL_ONLY


def test_pit_wall_deterministic():
    a = _pw()
    b = _pw()
    assert a.fingerprint == b.fingerprint


def test_race_pit_wall_issues_no_commands_text():
    pw = _pw(discipline="race", activity_type="long_race_run")
    # the next action never contains autonomous commands
    banned = ["pit now", "change tyres", "change fuel", "push", "defend", "overtake", "brake balance"]
    assert not any(b in pw.next_action.lower() for b in banned)
