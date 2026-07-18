"""Engineering-Brain Phase 4 — canonical per-corner evidence + recurrence tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from strategy.corner_evidence import (
    CornerPhase, CornerObservationRecord, from_issue_occurrence_row, normalise_phase,
    classify_recurrence, aggregate_corner_evidence, to_phase3_observations,
    CORNER_EVIDENCE_VERSION, R_REPEATABLE, R_ISOLATED_ONE_LAP,
)
from strategy.practice_pattern_analysis import RecurrenceClass

ROOT = Path(__file__).resolve().parents[1]


def _occ(lap, seg="T1", issue="front_lock", phase="braking", axle="front",
         checkpoint="cp1", session=10, excl="", conf=0.8):
    return {"session_id": session, "setup_checkpoint_id": checkpoint,
            "lap_number": lap, "segment_id": seg, "corner_phase": phase,
            "issue_type": issue, "axle": axle, "severity": 0.7, "confidence": conf,
            "exclusion_reason": excl, "track": "Fuji", "layout_id": "full_course"}


def _rec(lap, **kw):
    return from_issue_occurrence_row(_occ(lap, **kw), scope_fingerprint="eck_v1:scope:x")


# 16
def test_canonical_observation_construction():
    r = _rec(2)
    assert r.segment_id == "T1" and r.phase == CornerPhase.BRAKING
    assert r.issue_type == "front_lock" and r.axle == "front"
    assert r.applied_checkpoint_id == "cp1" and r.occurred_on_lap
    assert r.eval_version == CORNER_EVIDENCE_VERSION


def test_phase_normalisation():
    assert normalise_phase("mid_corner") == CornerPhase.APEX
    assert normalise_phase("") == CornerPhase.UNRESOLVED


# 17
def test_same_corner_phase_issue_aggregates():
    recs = [_rec(n) for n in (2, 3, 4)]
    aggs = aggregate_corner_evidence(recs, total_valid_laps=5)
    assert len(aggs) == 1 and aggs[0].affected_valid_laps == 3


# 18
def test_different_corners_do_not_aggregate():
    aggs = aggregate_corner_evidence(
        [_rec(2, seg="T1"), _rec(2, seg="T5", issue="rear_wheelspin")],
        total_valid_laps=5)
    assert len(aggs) == 2


# 19
def test_different_phases_do_not_aggregate():
    aggs = aggregate_corner_evidence(
        [_rec(2, phase="braking"), _rec(2, phase="exit")], total_valid_laps=5)
    assert len(aggs) == 2


# 20
def test_axle_specific_evidence_distinct():
    aggs = aggregate_corner_evidence(
        [_rec(2, axle="front"), _rec(2, axle="rear")], total_valid_laps=5)
    assert len(aggs) == 2


# 21
def test_excluded_events_do_not_count():
    recs = [_rec(2), _rec(3), _rec(4, excl="kerb"), _rec(5, excl="airborne")]
    res = classify_recurrence(recs, total_valid_laps=5)
    assert res.affected_valid_laps == 2      # only laps 2,3 admissible
    assert res.excluded_count == 2


# 22
def test_confidence_retained():
    r = _rec(2, conf=0.9)
    assert r.confidence == "high"
    r2 = _rec(2, conf=0.2)
    assert r2.confidence == "low"


# 23
def test_unresolved_corner_stays_unresolved():
    r = from_issue_occurrence_row(_occ(2, seg="", phase=""))
    assert not r.resolved
    assert r.corner_resolution_confidence == "low"


# 24
def test_no_invented_metrics():
    r = from_issue_occurrence_row({
        "lap_number": 2, "segment_id": "T1", "issue_type": "x",
        "steering_angle": 45, "tyre_wear_pct": 0.3, "entry_speed_kmh": 180})
    assert "steering_angle" not in r.metrics
    assert "tyre_wear_pct" not in r.metrics
    assert r.metrics.get("entry_speed_kmh") == 180.0


# --- recurrence 25-33 ---
def test_isolated():
    res = classify_recurrence([_rec(2)], total_valid_laps=5)
    assert res.classification == RecurrenceClass.ISOLATED
    assert res.rationale_code == R_ISOLATED_ONE_LAP


def test_emerging():
    res = classify_recurrence([_rec(2), _rec(3)], total_valid_laps=6)
    assert res.classification == RecurrenceClass.EMERGING


def test_recurring():
    res = classify_recurrence([_rec(2), _rec(3), _rec(4)], total_valid_laps=8)
    assert res.classification == RecurrenceClass.RECURRING


def test_strongly_recurring():
    res = classify_recurrence([_rec(n) for n in (2, 3, 4, 5)], total_valid_laps=5)
    assert res.classification == RecurrenceClass.STRONGLY_RECURRING
    assert res.rationale_code == R_REPEATABLE


def test_repeated_same_corner_outweighs_noisy_lap():
    # 4 distinct valid laps at T1 vs 11 events on ONE lap at T5
    t1 = [_rec(n, seg="T1") for n in (2, 3, 4, 5)]
    t5 = [_rec(5, seg="T5", issue="rear_wheelspin") for _ in range(11)]
    r_t1 = classify_recurrence(t1, total_valid_laps=5)
    r_t5 = classify_recurrence(t5, total_valid_laps=5)
    assert r_t1.classification == RecurrenceClass.STRONGLY_RECURRING
    assert r_t5.classification == RecurrenceClass.ISOLATED


def test_event_count_on_one_lap_not_recurrence():
    many = [_rec(2) for _ in range(20)]
    res = classify_recurrence(many, total_valid_laps=6)
    assert res.classification == RecurrenceClass.ISOLATED
    assert res.affected_valid_laps == 1


def test_excluded_noise_cannot_increase_recurrence():
    base = classify_recurrence([_rec(2), _rec(3)], total_valid_laps=6)
    noisy = classify_recurrence(
        [_rec(2), _rec(3)] + [_rec(4, excl="kerb"), _rec(5, excl="noise")],
        total_valid_laps=6)
    order = [RecurrenceClass.STRENGTH, RecurrenceClass.ISOLATED,
             RecurrenceClass.EMERGING, RecurrenceClass.RECURRING,
             RecurrenceClass.STRONGLY_RECURRING]
    assert order.index(noisy.classification) <= order.index(base.classification)


def test_lower_valid_laps_cannot_increase_confidence():
    hi = classify_recurrence([_rec(n) for n in (2, 3, 4)], total_valid_laps=6)
    lo = classify_recurrence([_rec(2)], total_valid_laps=2)
    levels = {"low": 0, "medium": 1, "high": 2}
    assert levels[lo.confidence] <= levels[hi.confidence]


def test_recurrence_order_independent():
    recs = [_rec(n) for n in (2, 3, 4)]
    a = classify_recurrence(recs, total_valid_laps=5)
    b = classify_recurrence(list(reversed(recs)), total_valid_laps=5)
    assert a.to_dict() == b.to_dict()


# metamorphic: moving events from one bad lap across several valid laps increases recurrence
def test_spreading_events_increases_recurrence():
    one_lap = [_rec(2) for _ in range(4)]
    spread = [_rec(n) for n in (2, 3, 4, 5)]
    a = classify_recurrence(one_lap, total_valid_laps=5)
    b = classify_recurrence(spread, total_valid_laps=5)
    order = [RecurrenceClass.ISOLATED, RecurrenceClass.EMERGING,
             RecurrenceClass.RECURRING, RecurrenceClass.STRONGLY_RECURRING]
    assert order.index(b.classification) > order.index(a.classification)


# to_phase3 conversion + valid-lap filtering
def test_phase3_conversion_excludes_invalid_laps():
    recs = [_rec(n) for n in (2, 3, 4, 6)]
    p3 = to_phase3_observations(recs, total_valid_laps=3, valid_lap_numbers=[2, 3, 4])
    assert p3[0].affected_laps == 3        # lap 6 excluded
    assert p3[0].segment_id == "T1"


def test_module_pure():
    src = (ROOT / "strategy" / "corner_evidence.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "from ui.", "import sqlite3", "from data.session_db",
                   "requests", "anthropic", "openai", "datetime.now", "random"):
        assert banned not in src, banned
