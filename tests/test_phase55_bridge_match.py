"""Phase 55 — live GT7 runtime snapshot + activity matching (task items 14-15, 19)."""
from __future__ import annotations

from strategy.live_activity_bridge import (
    LiveActivityRuntimeSnapshot, LiveActivityMatch as MM, classify_live_activity_match,
    match_permits_evidence,
)


def _snap(**kw):
    base = dict(activity_selected=True, activity_id="exp", activity_type="setup_experiment",
                cycle_id="c1", telemetry_fresh=True,
                car_expected="Porsche", car_live="Porsche", track_expected="Fuji", track_live="Fuji",
                layout_expected="Full", layout_live="Full", discipline_expected="race",
                discipline_live="race", expected_setup_fingerprint="fp", live_setup_fingerprint="fp",
                event_context_digest="ctx", live_context_digest="ctx", tyre_compound="MR",
                run_plan_fingerprint="rp")
    base.update(kw)
    return LiveActivityRuntimeSnapshot(**base)


def test_exact_match():
    assert classify_live_activity_match(_snap()).match == MM.EXACT_ACTIVITY_MATCH


def test_no_activity_selected():
    assert classify_live_activity_match(_snap(activity_selected=False)).match == MM.ACTIVITY_NOT_SELECTED


def test_stale_telemetry():
    assert classify_live_activity_match(_snap(telemetry_fresh=False)).match == MM.TELEMETRY_STALE


def test_hard_mismatches_in_order():
    assert classify_live_activity_match(_snap(car_live="GT3")).match == MM.CAR_MISMATCH
    assert classify_live_activity_match(_snap(track_live="Spa")).match == MM.TRACK_MISMATCH
    assert classify_live_activity_match(_snap(layout_live="Short")).match == MM.LAYOUT_MISMATCH
    assert classify_live_activity_match(_snap(discipline_live="qualifying")).match == MM.DISCIPLINE_MISMATCH
    assert classify_live_activity_match(_snap(live_setup_fingerprint="other")).match == MM.SETUP_MISMATCH
    assert classify_live_activity_match(_snap(live_context_digest="other")).match == MM.CONTEXT_MISMATCH


def test_unknown_required_field_is_unverifiable_not_match():
    # a required field unknown -> UNVERIFIABLE (never treated as a verified match)
    r = classify_live_activity_match(_snap(car_expected="", car_live=""))
    assert r.match == MM.UNVERIFIABLE
    assert any("car unknown" in l for l in r.limitations)


def test_match_with_limitations_when_noncritical_unknown():
    r = classify_live_activity_match(_snap(tyre_compound="", run_plan_fingerprint=""))
    assert r.match == MM.MATCH_WITH_LIMITATIONS
    assert r.limitations


def test_match_permits_evidence():
    assert match_permits_evidence(classify_live_activity_match(_snap())) is True
    assert match_permits_evidence(classify_live_activity_match(_snap(car_live="GT3"))) is False
    assert match_permits_evidence(classify_live_activity_match(_snap(telemetry_fresh=False))) is False


def test_snapshot_fingerprint_excludes_volatile_counters():
    a = _snap(lap=1, valid_laps=1, fuel="80", current_segment="T1")
    b = _snap(lap=9, valid_laps=7, fuel="20", current_segment="T13")
    assert a.fingerprint() == b.fingerprint()  # volatile live counters not in stable identity


def test_match_result_deterministic():
    assert classify_live_activity_match(_snap()).fingerprint == classify_live_activity_match(_snap()).fingerprint
