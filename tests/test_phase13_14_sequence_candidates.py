"""Phase 13 (controlled test sequencing) + Phase 14 (candidate comparison).

13: the approved changes become a one-at-a-time programme — highest confidence /
    lowest risk / biggest effect first, each with a success criterion and rollback,
    same-axis stages flagged for isolation.
14: current vs proven-historical vs rule-recommended per field; only candidates
    actually computed are shown, never fabricated.
"""
from __future__ import annotations

from strategy.setup_test_plan import (
    build_test_sequence, test_sequence_to_json as seq_to_json,
)
from strategy.setup_candidates import (
    make_candidate, build_candidate_comparison, candidate_comparison_to_json,
)


def _ch(field, delta, conf="med", risk="low", symptom="", frm=10, to=None):
    return {"field": field, "delta": delta, "confidence_level": conf,
            "risk_level": risk, "symptom": symptom, "from": frm,
            "to": (frm + delta if to is None else to)}


# ============================================ Phase 13

def test_empty_changes_gives_empty_sequence():
    seq = build_test_sequence([])
    assert seq.is_empty() and "No changes" in seq.note


def test_noop_changes_excluded():
    seq = build_test_sequence([_ch("arb_rear", 0), {"field": "", "delta": 2}])
    assert seq.is_empty()


def test_high_confidence_low_risk_tested_first():
    seq = build_test_sequence([
        _ch("arb_rear", 2, conf="low", risk="high"),
        _ch("aero_front", 20, conf="high", risk="low"),
    ])
    assert seq.stages[0].field == "aero_front"     # high conf / low risk wins
    assert seq.stages[1].field == "arb_rear"
    assert seq.stages[0].order == 1


def test_bigger_effect_breaks_ties():
    seq = build_test_sequence([
        _ch("camber_front", 0.2, conf="med", risk="low"),
        _ch("toe_front", 0.9, conf="med", risk="low"),
    ])
    assert seq.stages[0].field == "toe_front"      # larger |delta|


def test_stage_carries_success_and_rollback():
    seq = build_test_sequence([_ch("arb_front", -2, symptom="pushes wide", frm=6)])
    s = seq.stages[0]
    assert "lower arb_front" in s.change_summary and "6" in s.change_summary
    assert "pushes wide" in s.success_criterion
    assert "revert arb_front to 6" in s.rollback


def test_same_axis_adjacent_stages_flagged_to_isolate():
    # aero_front and arb_rear both move front/rear balance
    seq = build_test_sequence([
        _ch("aero_front", 20, conf="high"),
        _ch("arb_rear", 2, conf="high"),
    ])
    assert any(s.isolate_note for s in seq.stages)


def test_off_axis_stage_not_flagged():
    seq = build_test_sequence([
        _ch("camber_front", 0.3, conf="high"),
        _ch("camber_rear", 0.3, conf="high"),
    ])
    assert all(not s.isolate_note for s in seq.stages)


def test_sequence_json_shape():
    seq = build_test_sequence([_ch("arb_rear", 2)])
    j = seq_to_json(seq)
    assert j["stages"][0]["field"] == "arb_rear" and "note" in j


# ============================================ Phase 14

def test_comparison_shows_only_available_candidates():
    cur = make_candidate("current", "Current", {"arb_rear": 5, "aero_front": 400})
    rec = make_candidate("recommended", "Rec", {"arb_rear": 7})
    hist = make_candidate("historical", "Proven", {})     # no data -> unavailable
    cmp = build_candidate_comparison([cur, rec, hist])
    names = {c.name for c in cmp.columns}
    assert names == {"current", "recommended"}            # hist dropped, not fabricated


def test_comparison_flags_field_where_candidates_differ():
    cur = make_candidate("current", "Current", {"arb_rear": 5})
    rec = make_candidate("recommended", "Rec", {"arb_rear": 7})
    cmp = build_candidate_comparison([cur, rec])
    row = next(r for r in cmp.rows if r.field == "arb_rear")
    assert row.differs is True
    assert row.values == {"current": 5.0, "recommended": 7.0}


def test_comparison_agreement_not_flagged():
    cur = make_candidate("current", "Current", {"lsd_accel": 8})
    hist = make_candidate("historical", "Proven", {"lsd_accel": 8})
    cmp = build_candidate_comparison([cur, hist])
    assert cmp.rows[0].differs is False


def test_comparison_field_order_respected():
    cur = make_candidate("current", "Current", {"arb_rear": 5, "aero_front": 400})
    cmp = build_candidate_comparison([cur], fields=["aero_front", "arb_rear"])
    assert [r.field for r in cmp.rows] == ["aero_front", "arb_rear"]


def test_comparison_empty_when_no_candidates():
    cmp = build_candidate_comparison([])
    assert cmp.is_empty()
    assert candidate_comparison_to_json(cmp) == {"columns": [], "rows": []}


def test_make_candidate_drops_non_numeric():
    c = make_candidate("x", "X", {"a": 5, "b": "n/a", "c": None})
    assert c.values == {"a": 5.0} and c.available is True


# ============================================ integration

def test_response_carries_sequence_and_comparison():
    import json
    import tests.test_group41_validation_gate as G
    adv = G._make_full_advisor({}, [G._make_lap()])
    res = json.loads(adv.build_combined_setup_response(
        setup_dict={"arb_front": 6, "arb_rear": 5, "aero_front": 400},
        car_name="Porsche 911 RSR (991) '17",
        feeling="The car pushes wide in the middle of the corner"))
    assert "test_sequence" in res and "stages" in res["test_sequence"]
    assert "candidate_comparison" in res and "columns" in res["candidate_comparison"]
