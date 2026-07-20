"""Phase 57 — GT7 runtime adapter + immutable snapshot + freshness (task items 5, 6, 9-14)."""
from __future__ import annotations

from strategy.gt7_live_adapter import (
    TrackerRuntimeSnapshot, SelectedActivityContext, Gt7LiveActivityAdapter, evaluate_freshness,
    evaluate_live_runtime,
)
from strategy.live_activity_bridge import LiveActivityMatch as MM


def _tracker(**kw):
    base = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                lap=3, session_state="running", current_segment="T1", fuel="80", tyre_compound="MR",
                valid_laps=3, last_packet_monotonic=100.0)
    base.update(kw)
    return TrackerRuntimeSnapshot(**base)


def _ctx(**kw):
    base = dict(cycle_id="c1", activity_id="exp", activity_type="setup_experiment", discipline="race",
                car="Porsche", track="Fuji", layout="Full", expected_setup_fingerprint="fp",
                event_context_digest="", run_plan_fingerprint="rp", objective="rotation", target_laps=8)
    base.update(kw)
    return SelectedActivityContext(**base)


# --- freshness -------------------------------------------------------------

def test_freshness_fresh_within_threshold():
    assert evaluate_freshness(100.0, 101.0, threshold_seconds=1.5).fresh is True


def test_freshness_stale_beyond_threshold():
    assert evaluate_freshness(100.0, 103.0, threshold_seconds=1.5).fresh is False


def test_freshness_unknown_packet_is_stale():
    assert evaluate_freshness(None, 101.0).fresh is False
    assert evaluate_freshness(100.0, None).fresh is False


# --- adapter mapping -------------------------------------------------------

def test_adapter_maps_tracker_to_snapshot():
    snap = Gt7LiveActivityAdapter.build_runtime_snapshot(_tracker(), _ctx(), now_monotonic=100.5)
    assert snap.activity_selected is True and snap.telemetry_fresh is True
    assert snap.car_live == "Porsche" and snap.car_expected == "Porsche"
    assert snap.live_setup_fingerprint == "fp" and snap.expected_setup_fingerprint == "fp"


def test_adapter_unknown_stays_unknown():
    snap = Gt7LiveActivityAdapter.build_runtime_snapshot(_tracker(car=""), _ctx(), now_monotonic=100.5)
    assert snap.car_live == ""  # never fabricated


def test_discipline_comes_from_activity_by_default():
    # no tracker-detected discipline -> discipline_live == expected (purpose from selected activity)
    snap = Gt7LiveActivityAdapter.build_runtime_snapshot(_tracker(session_discipline=""), _ctx(),
                                                         now_monotonic=100.5)
    assert snap.discipline_live == snap.discipline_expected == "race"


def test_tracker_detected_discipline_can_surface_mismatch():
    snap = Gt7LiveActivityAdapter.build_runtime_snapshot(_tracker(session_discipline="qualifying"),
                                                         _ctx(discipline="race"), now_monotonic=100.5)
    assert snap.discipline_live == "qualifying" and snap.discipline_expected == "race"


# --- live runtime evaluation (reuses canonical classifier) -----------------

def test_evaluate_real_tracker_default_is_match_with_limitations():
    # a live tracker cannot verify the engineering context digest -> honest MATCH_WITH_LIMITATIONS
    e = evaluate_live_runtime(_tracker(), _ctx(), now_monotonic=100.5)
    assert e.match.match == MM.MATCH_WITH_LIMITATIONS
    assert e.evidence_progress == 3 / 8


def test_evaluate_exact_match_when_context_digest_known():
    e = evaluate_live_runtime(_tracker(live_context_digest="ctx"), _ctx(event_context_digest="ctx"),
                              now_monotonic=100.5)
    assert e.match.match == MM.EXACT_ACTIVITY_MATCH


def test_evaluate_setup_mismatch():
    e = evaluate_live_runtime(_tracker(applied_setup_fingerprint="other"), _ctx(), now_monotonic=100.5)
    assert e.match.match == MM.SETUP_MISMATCH


def test_evaluate_car_and_track_mismatch():
    assert evaluate_live_runtime(_tracker(car="GT3"), _ctx(), now_monotonic=100.5).match.match == MM.CAR_MISMATCH
    assert evaluate_live_runtime(_tracker(track="Spa"), _ctx(), now_monotonic=100.5).match.match == MM.TRACK_MISMATCH


def test_evaluate_stale_telemetry():
    e = evaluate_live_runtime(_tracker(), _ctx(), now_monotonic=110.0)  # 10s old -> stale
    assert e.match.match == MM.TELEMETRY_STALE


def test_evaluate_activity_not_selected():
    e = evaluate_live_runtime(_tracker(), _ctx(activity_id=""), now_monotonic=100.5)
    assert e.match.match == MM.ACTIVITY_NOT_SELECTED


def test_unknown_layout_is_limited_or_unverifiable_never_exact():
    e = evaluate_live_runtime(_tracker(layout=""), _ctx(layout=""), now_monotonic=100.5)
    assert e.match.match != MM.EXACT_ACTIVITY_MATCH


def test_same_sequence_same_decision():
    a = evaluate_live_runtime(_tracker(), _ctx(), now_monotonic=100.5)
    b = evaluate_live_runtime(_tracker(), _ctx(), now_monotonic=100.5)
    assert a.fingerprint == b.fingerprint


def test_monotonic_time_affects_freshness_not_engineering_fingerprint():
    # the underlying activity decision (match) does not change with a fresher/older monotonic time as
    # long as it stays fresh; the volatile snapshot fingerprint excludes live counters.
    fresh1 = evaluate_live_runtime(_tracker(), _ctx(), now_monotonic=100.2)
    fresh2 = evaluate_live_runtime(_tracker(), _ctx(), now_monotonic=101.0)
    assert fresh1.match.match == fresh2.match.match  # decision stable while fresh (monotonic only gates expiry)
