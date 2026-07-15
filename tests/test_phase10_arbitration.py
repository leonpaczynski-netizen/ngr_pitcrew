"""Phase 10 — cross-symptom arbitration.

Two things stop reading "Considered alternatives: none":
  1. same-FIELD contests: the winning rule records the beaten rule in its
     rejected_alternatives (setup_rule_engine arbitration helpers);
  2. the FINAL proposed set is analysed for changes that push the front/rear
     balance the same way (overshoot risk) or offset each other.
Neither fabricates a magnitude.
"""
from __future__ import annotations

from strategy.setup_rule_engine import (
    SetupChangeIntent, _arbitration_note, _record_alternative,
)
from strategy.setup_knowledge_base import RiskLevel, ConfidenceLevel
from strategy.setup_driver_profile import DriverStyleAlignment
from strategy.setup_arbitration import analyse_change_interactions


def _intent(field, delta, rule_id, symptom="", alts=None):
    return SetupChangeIntent(
        field=field, delta=delta, from_value=10, to_value=10 + delta,
        symptom=symptom, evidence=[], rule_id=rule_id, rationale="",
        rejected_alternatives=list(alts or []),
        risk=RiskLevel.low, confidence=ConfidenceLevel.med,
        driver_style_alignment=DriverStyleAlignment.neutral)


# ------------------------------------------------- winner records the loser

def test_arbitration_note_names_beaten_rule_and_direction():
    loser = _intent("arb_front", +2, "B2", symptom="pushes wide")
    note = _arbitration_note(loser, "lower confidence")
    assert "B2" in note and "raise arb_front" in note
    assert "pushes wide" in note and "lower confidence" in note


def test_record_alternative_appends_to_winner():
    winner = _intent("arb_front", -2, "B2b")
    loser = _intent("arb_front", +2, "B2")
    out = _record_alternative(winner, loser, "opposite direction, lower confidence")
    assert len(out.rejected_alternatives) == 1
    assert "B2" in out.rejected_alternatives[0]
    # winner's own identity/decision is untouched
    assert out.rule_id == "B2b" and out.delta == -2


def test_record_alternative_preserves_prior_alternatives():
    winner = _intent("lsd_accel", +2, "B6", alts=["X: prior"])
    out = _record_alternative(winner, _intent("lsd_accel", +1, "C5"), "lower confidence")
    assert out.rejected_alternatives == ["X: prior", out.rejected_alternatives[1]]
    assert "C5" in out.rejected_alternatives[1]


# ------------------------------------------------- set-level interactions

def _ch(field, delta):
    return {"field": field, "delta": delta}


def test_compounding_same_direction_flagged():
    # aero_front + (looser) and arb_rear + (looser) -> both push looser
    r = analyse_change_interactions([_ch("aero_front", 20), _ch("arb_rear", 2)])
    assert r.compounding is True and r.offsetting is False
    assert r.net_direction == "looser"
    assert "overshoot" in r.as_note()


def test_offsetting_opposite_directions_flagged():
    # aero_front + (looser) and aero_rear + (more stable) -> offset
    r = analyse_change_interactions([_ch("aero_front", 20), _ch("aero_rear", 20)])
    assert r.offsetting is True and r.compounding is False
    assert "opposite directions" in r.as_note()


def test_single_axis_change_not_compounding():
    r = analyse_change_interactions([_ch("aero_front", 20)])
    assert r.compounding is False and r.offsetting is False
    assert r.as_note() == ""


def test_off_axis_changes_ignored():
    r = analyse_change_interactions([_ch("camber_front", 0.5), _ch("toe_front", -0.05)])
    assert r.net_direction == "neutral" and r.contributors == []


def test_no_op_delta_ignored():
    r = analyse_change_interactions([_ch("aero_front", 0), _ch("arb_rear", 2)])
    assert r.compounding is False and r.contributors == ["arb_rear"]


def test_empty_set_is_safe():
    r = analyse_change_interactions([])
    assert r.compounding is False and r.as_note() == ""


# ------------------------------------------------- integration

def test_response_carries_arbitration_block():
    import json
    import tests.test_group41_validation_gate as G
    adv = G._make_full_advisor({}, [G._make_lap()])
    res = json.loads(adv.build_combined_setup_response(
        setup_dict={"aero_front": 400, "aero_rear": 690},
        car_name="Porsche 911 RSR (991) '17",
        feeling="The car pushes wide in the middle of the corner"))
    assert "arbitration" in res            # structure present even when no compounding
    assert isinstance(res["arbitration"], dict)
