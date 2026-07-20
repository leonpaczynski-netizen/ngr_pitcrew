"""Phase 55 — Practice/Qualifying/Race bridge views (task items 16-19)."""
from __future__ import annotations

from strategy.live_activity_bridge import (
    LiveActivityRuntimeSnapshot, classify_live_activity_match)
from strategy.live_activity_modes import LiveMode, LiveDensity
from strategy.live_bridge_views import (
    build_practice_bridge, build_qualifying_bridge, build_race_bridge, bridge_blocked,
)


def _snap(**kw):
    base = dict(activity_selected=True, activity_id="exp", activity_type="setup_experiment",
                cycle_id="c1", telemetry_fresh=True, car_expected="Porsche", car_live="Porsche",
                track_expected="Fuji", track_live="Fuji", layout_expected="Full", layout_live="Full",
                discipline_expected="race", discipline_live="race", expected_setup_fingerprint="fp",
                live_setup_fingerprint="fp", event_context_digest="ctx", live_context_digest="ctx",
                tyre_compound="MR", run_plan_fingerprint="rp", target_laps=8, valid_laps=3, objective="rotation")
    base.update(kw)
    return LiveActivityRuntimeSnapshot(**base)


def _m(snap):
    return classify_live_activity_match(snap)


def test_practice_bridge_exact_match_permits_evidence():
    snap = _snap()
    b = build_practice_bridge(snap, _m(snap))
    assert b.mode == LiveMode.PRACTICE and b.blocked is False and b.evidence_permitted is True
    assert b.view.density == LiveDensity.FOCUSED and b.view.valid_laps == 3


def test_setup_mismatch_blocks_activity():
    snap = _snap(live_setup_fingerprint="other")
    b = build_practice_bridge(snap, _m(snap))
    assert b.blocked is True and b.evidence_permitted is False


def test_qualifying_bridge_is_minimal():
    snap = _snap(discipline_expected="qualifying", discipline_live="qualifying")
    b = build_qualifying_bridge(snap, _m(snap))
    assert b.view.density == LiveDensity.MINIMAL and b.blocked is False


def test_race_bridge_is_safety_and_issues_no_commands():
    snap = _snap()
    b = build_race_bridge(snap, _m(snap))
    assert b.view.density == LiveDensity.SAFETY and b.view.issues_commands is False


def test_stale_telemetry_blocks_and_suppresses_advisory():
    snap = _snap(telemetry_fresh=False)
    b = build_practice_bridge(snap, _m(snap))
    assert b.blocked is True and b.view.current_advisory == ""  # advisories suppressed on stale telemetry


def test_car_mismatch_blocks_race_bridge_with_warning():
    snap = _snap(car_live="GT3")
    b = build_race_bridge(snap, _m(snap))
    assert b.blocked is True and b.view.race_setup_match is False
    assert b.view.critical_warnings


def test_bridge_deterministic():
    snap = _snap()
    assert build_practice_bridge(snap, _m(snap)).fingerprint == build_practice_bridge(snap, _m(snap)).fingerprint


def test_bridge_blocked_helper():
    assert bridge_blocked(_m(_snap(car_live="GT3"))) is True
    assert bridge_blocked(_m(_snap())) is False
