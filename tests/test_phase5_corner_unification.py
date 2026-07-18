"""Engineering-Brain Phase 5 — per-corner producer unification + lap-validity migration."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from strategy.corner_evidence import (
    from_issue_occurrence_row, from_corner_slip_aggregate, unify_corner_observations,
    classify_recurrence,
)
from strategy.live_corner_aggregator import CornerTelemetryAggregate
from strategy.practice_pattern_analysis import RecurrenceClass

ROOT = Path(__file__).resolve().parents[1]


def _occ(lap, seg="T5", issue="wheelspin", phase="exit", axle="rear",
         session=800, cp="cp1"):
    return from_issue_occurrence_row(
        {"session_id": session, "setup_checkpoint_id": cp, "lap_number": lap,
         "segment_id": seg, "corner_phase": phase, "issue_type": issue, "axle": axle,
         "confidence": 0.8}, scope_fingerprint="x")


def _agg(seg="T5", wheelspin=6, phase="exit", axle="rear", samples=40):
    return CornerTelemetryAggregate(
        segment_id=seg, turn=None, display_name="Final", direction="",
        samples=samples, wheelspin_events=wheelspin, lockup_events=0,
        wheelspin_by_phase={phase: wheelspin}, lockup_by_phase={},
        spin_axle_counts={axle: wheelspin}, lock_axle_counts={},
        avg_throttle=0.8, avg_brake=0.0, exit_gear=3, exit_rpm_avg=6000.0)


# --- 12.5 unification ------------------------------------------------------
def test_practice_source_conversion():
    r = _occ(2)
    assert r.source == "corner_issue_occurrences" and r.occurred_on_lap


def test_live_slip_source_conversion():
    recs = from_corner_slip_aggregate(_agg(), scope_fingerprint="x", run_id=1,
                                      session_id=800, checkpoint_id="cp1",
                                      track="Fuji", layout_id="full")
    assert recs and recs[0].source == "corner_slip_telemetry"
    assert recs[0].issue_type == "wheelspin" and recs[0].axle == "rear"


def test_slip_provenance_retained():
    recs = from_corner_slip_aggregate(_agg(), scope_fingerprint="x", run_id=7,
                                      session_id=800, checkpoint_id="cp1")
    assert recs[0].run_id == "7" and recs[0].session_id == "800"
    assert recs[0].applied_checkpoint_id == "cp1"


def test_missing_checkpoint_and_session_is_unlinked():
    recs = from_corner_slip_aggregate(_agg(), scope_fingerprint="x", run_id=9)
    assert recs[0].telemetry_available == "unlinked"
    assert recs[0].exclusion_reason


def test_duplicate_event_removed():
    occ = [_occ(n) for n in (2, 3, 4, 5)]
    slip = from_corner_slip_aggregate(_agg(), scope_fingerprint="x", run_id=1,
                                      session_id=800, checkpoint_id="cp1")
    unified, audit = unify_corner_observations(occ, slip, valid_lap_numbers=[2, 3, 4, 5])
    assert audit.duplicates_removed == 1
    assert audit.distinct_affected_valid_laps == 4    # slip cannot inflate this


def test_similar_but_distinct_events_retained():
    occ = [_occ(2, seg="T5")]
    slip = from_corner_slip_aggregate(_agg(seg="T3"), scope_fingerprint="x", run_id=1,
                                      session_id=800, checkpoint_id="cp1")
    unified, audit = unify_corner_observations(occ, slip)
    assert audit.duplicates_removed == 0              # different corner → kept


def test_excluded_events_never_count():
    occ = [_occ(2), _occ(3),
           from_issue_occurrence_row({"session_id": 800, "lap_number": 4,
               "segment_id": "T5", "corner_phase": "exit", "issue_type": "wheelspin",
               "axle": "rear", "exclusion_reason": "kerb"}, scope_fingerprint="x")]
    _, audit = unify_corner_observations(occ, [], valid_lap_numbers=[2, 3, 4])
    assert audit.distinct_affected_valid_laps == 2    # excluded lap 4 not counted


def test_recurrence_uses_distinct_valid_laps_not_raw_count():
    # one lap, many slip events cannot make it recurring
    slip = from_corner_slip_aggregate(_agg(wheelspin=20), scope_fingerprint="x",
                                      run_id=1, session_id=800, checkpoint_id="cp1")
    res = classify_recurrence(list(slip), total_valid_laps=5)
    assert res.affected_valid_laps == 0               # slip has no lap attribution
    assert res.classification == RecurrenceClass.STRENGTH


def test_unification_source_order_independent():
    occ = [_occ(n) for n in (2, 3)]
    slip = from_corner_slip_aggregate(_agg(), scope_fingerprint="x", run_id=1,
                                      session_id=800, checkpoint_id="cp1")
    _, a = unify_corner_observations(occ, slip, valid_lap_numbers=[2, 3])
    _, b = unify_corner_observations(list(reversed(occ)), slip, valid_lap_numbers=[2, 3])
    assert a.to_dict() == b.to_dict()


def test_audit_reports_source_counts():
    occ = [_occ(2)]
    slip = from_corner_slip_aggregate(_agg(), scope_fingerprint="x", run_id=1,
                                      session_id=800, checkpoint_id="cp1")
    _, audit = unify_corner_observations(occ, slip)
    assert audit.source_counts["corner_issue_occurrences"] == 1
    assert audit.source_counts["corner_slip_telemetry"] == 1
