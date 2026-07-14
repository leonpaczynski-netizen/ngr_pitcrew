"""Per-corner diagnosis tests (Engineering-Brain Phase 5).

A corner-scoped complaint resolves to the actual track corner, is bucketed by phase,
mapped to candidate causes, and — when the telemetry to pick between causes is absent —
gets reduced confidence and a precise controlled test instead of a guess.
"""
from __future__ import annotations

from strategy.corner_diagnosis import (
    CornerFeedback, diagnose_corner_feedback, resolve_corner_reference,
    parse_corner_number, PHASE_APEX, PHASE_EXIT, PHASE_BRAKING,
)


def _fuji_segments():
    return [
        {"segment_type": "apex_zone", "turn_number": 1, "lap_progress_mid": 0.17,
         "reviewed_display_name": "T1 Apex", "direction": "right"},
        {"segment_type": "apex_zone", "turn_number": 2, "lap_progress_mid": 0.29,
         "reviewed_display_name": "T2 Apex", "direction": "left"},
        {"segment_type": "corner_entry", "turn_number": 2, "lap_progress_start": 0.26},
        {"segment_type": "straight", "lap_progress_start": 0.0},
    ]


# ------------------------------------------------------------------ resolution

def test_parse_corner_number():
    assert parse_corner_number("not hooking up especially Corner 2") == 2
    assert parse_corner_number("T2") == 2
    assert parse_corner_number("turn 11") == 11
    assert parse_corner_number("#3") == 3
    assert parse_corner_number("the hairpin") is None


def test_resolve_corner_matches_reviewed_segment():
    cr = resolve_corner_reference("Corner 2", _fuji_segments())
    assert cr.resolved and cr.turn == 2 and "T2" in cr.display_name
    assert abs(cr.apex_progress - 0.29) < 1e-6 and cr.direction == "left"
    assert cr.confidence == "high"


def test_resolve_unmatched_corner_is_honest():
    cr = resolve_corner_reference("Corner 9", _fuji_segments())
    assert not cr.resolved and cr.confidence == "low" and "no reviewed segment" in cr.note
    cr2 = resolve_corner_reference("the fast bit", _fuji_segments())
    assert not cr2.resolved and "no corner number" in cr2.note


# ------------------------------------------------------------------ diagnosis + test

def test_apex_not_hooking_up_multiple_causes_prescribes_test():
    d = diagnose_corner_feedback(
        CornerFeedback("Corner 2", "apex", "not hooking up"), _fuji_segments(),
        telemetry_available=False)
    assert d.corner.resolved and d.phase == PHASE_APEX and d.symptom == "not_hooking_up"
    causes = [c["cause"] for c in d.causes]
    assert any("LSD preload" in c for c in causes) and any("front grip" in c for c in causes)
    assert "lsd_initial" in d.fields_involved and "aero_front" in d.fields_involved
    # Multiple causes + no telemetry → low confidence + a precise test, not a guess.
    assert d.confidence == "low"
    assert "candidate causes" in d.controlled_test and "3 clean laps" in d.controlled_test


def test_telemetry_and_single_cause_raises_confidence():
    d = diagnose_corner_feedback(
        CornerFeedback(2, "braking", "locks up rear"), _fuji_segments(),
        telemetry_available=True)
    assert d.phase == PHASE_BRAKING and d.symptom == "loose"
    assert d.causes and d.confidence == "high"       # resolved + telemetry + single cause
    assert "brake_bias" in d.fields_involved


def test_exit_loose_separates_lsd_from_rear_support_from_gear():
    d = diagnose_corner_feedback(
        CornerFeedback(2, "exit", "steps out"), _fuji_segments(),
        telemetry_available=False)
    causes = " ".join(c["cause"] for c in d.causes)
    assert "acceleration lock" in causes and "rear support" in causes and "gear" in causes
    assert d.confidence == "low" and "wheel-slip" in d.controlled_test


def test_unresolved_corner_prescribes_resolution_first():
    d = diagnose_corner_feedback(
        CornerFeedback("somewhere", "apex", "understeer"), _fuji_segments(),
        telemetry_available=True)
    assert not d.corner.resolved and d.confidence == "low"
    assert "Resolve the corner first" in d.controlled_test


def test_as_json_shape():
    d = diagnose_corner_feedback(
        CornerFeedback(2, "apex", "understeer"), _fuji_segments())
    j = d.as_json()
    assert j["corner"]["turn"] == 2 and j["phase"] == "apex"
    assert "causes" in j and "controlled_test" in j and "fields_involved" in j
