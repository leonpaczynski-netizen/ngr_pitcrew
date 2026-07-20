"""Phase 69 — Live UAT Runtime snapshot: construction, partial init, disconnected/stale telemetry,
determinism, tyre-proxy honesty, explicit missing evidence."""
from __future__ import annotations

import types

from strategy.live_uat_runtime_snapshot import (
    build_live_uat_runtime_snapshot, LiveUatRuntimeSnapshot, LIVE_UAT_RUNTIME_SNAPSHOT_VERSION,
)
from strategy.canonical_live_race_state import build_canonical_live_race_state
from strategy.event_programme_certification import live_vr_certification


def _lap_tracker():
    return types.SimpleNamespace(
        race_type="laps", laps_recorded=5, laps_in_race=20, last_fuel=60.0, avg_fuel_per_lap=3.2,
        best_lap_ms=88000, tyre_compound="RH", laps_since_pit=5, in_pit=False, pit_stops_completed=0,
        last_position=3, car_name="GT3", track="Fuji", layout_id="full")


def _timed_tracker():
    return types.SimpleNamespace(
        race_type="timed", laps_recorded=8, timed_duration_minutes=30, last_fuel=42.0,
        avg_fuel_per_lap=3.0, best_lap_ms=90000, tyre_compound="RM", laps_since_pit=8, in_pit=False,
        pit_stops_completed=1, last_position=2, car_name="GT3", track="Fuji", layout_id="full")


def test_empty_snapshot_is_defensive():
    snap = build_live_uat_runtime_snapshot()
    assert isinstance(snap, LiveUatRuntimeSnapshot)
    assert snap.certification_summary == "not_tested"
    assert snap.replan_ready is False
    assert snap.objective == "unknown"
    assert snap.fingerprint.startswith(LIVE_UAT_RUNTIME_SNAPSHOT_VERSION)


def test_lap_race_snapshot_fields():
    canon = build_canonical_live_race_state(_lap_tracker(), elapsed_s=440.0, telemetry_fresh=True,
                                            recent_clean_lap_times_s=[88.1, 88.3, 88.0, 88.2, 88.4])
    snap = build_live_uat_runtime_snapshot(canonical=canon, certification=live_vr_certification(),
                                           tracker_connected=True, telemetry_fresh=True,
                                           pace_sample_count=5)
    assert snap.objective == "lap_count"
    assert snap.current_lap == 5 and snap.total_race_laps == 20
    assert snap.fuel_remaining_l == 60.0
    assert snap.pace_estimate_s is not None
    assert snap.certification_summary == "not_tested"


def test_time_certain_snapshot():
    canon = build_canonical_live_race_state(_timed_tracker(), elapsed_s=600.0, telemetry_fresh=True,
                                            recent_clean_lap_times_s=[90.1, 90.0, 90.2, 90.1, 90.0])
    snap = build_live_uat_runtime_snapshot(canonical=canon, tracker_connected=True, telemetry_fresh=True)
    assert snap.objective == "time_certain"
    assert snap.race_time_remaining_s is not None


def test_tyre_proxy_never_measured():
    canon = build_canonical_live_race_state(_lap_tracker(), telemetry_fresh=True,
                                            recent_clean_lap_times_s=[88.0, 88.3, 88.6, 89.0, 89.4])
    snap = build_live_uat_runtime_snapshot(canonical=canon)
    # the tyre value is always a proxy, never a measured tyre condition
    assert snap.tyre_age_proxy_is_measured is False


def test_disconnected_telemetry_snapshot():
    snap = build_live_uat_runtime_snapshot(tracker_connected=False, telemetry_fresh=False)
    assert snap.tracker_connected is False
    assert snap.telemetry_fresh is False
    assert "telemetry" in snap.stale_evidence


def test_missing_evidence_is_explicit():
    canon = build_canonical_live_race_state(_lap_tracker(), telemetry_fresh=True)
    snap = build_live_uat_runtime_snapshot(canonical=canon)
    # no pre-race plan supplied → the plan baselines are explicitly missing (never a silent default)
    assert "fuel_per_lap_plan" in snap.missing_evidence
    assert "lap_time_plan_s" in snap.missing_evidence


def test_missing_evidence_never_increases_confidence():
    # a bare tracker (no fuel/pace samples) must not manufacture HIGH/MEDIUM confidence
    bare = types.SimpleNamespace(race_type="laps", laps_recorded=3, laps_in_race=20, car_name="GT3")
    canon = build_canonical_live_race_state(bare, telemetry_fresh=True)
    snap = build_live_uat_runtime_snapshot(canonical=canon)
    assert snap.fuel_confidence in ("none", "low")
    assert snap.pace_confidence in ("none", "low")


def test_fingerprint_excludes_volatile_identity_and_timestamp():
    canon = build_canonical_live_race_state(_lap_tracker(), telemetry_fresh=True,
                                            recent_clean_lap_times_s=[88.1, 88.0, 88.2, 88.1, 88.0])
    a = build_live_uat_runtime_snapshot(timestamp="12:00:00", session_identity="s1", event_identity="e1",
                                        canonical=canon)
    b = build_live_uat_runtime_snapshot(timestamp="23:59:59", session_identity="sX", event_identity="e1",
                                        canonical=canon)
    assert a.fingerprint == b.fingerprint   # timestamp + session identity are volatile


def test_partial_initialisation_does_not_raise():
    # a half-built canonical (None fields) must be handled without raising
    snap = build_live_uat_runtime_snapshot(canonical=None, strategy_state=None, decision=None, audio=None,
                                           certification=None)
    assert isinstance(snap, LiveUatRuntimeSnapshot)


def test_snapshot_to_dict_has_no_raw_secrets():
    canon = build_canonical_live_race_state(_lap_tracker(), telemetry_fresh=True)
    d = build_live_uat_runtime_snapshot(canonical=canon).to_dict()
    joined = " ".join(str(k) for k in d).lower()
    assert "api_key" not in joined and "secret" not in joined and "password" not in joined
