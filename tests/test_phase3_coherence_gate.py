"""Phase 3 — dominant-problem coherence gate.

A plan whose dominant REQUIRED problem is neither addressed nor explicitly
deferred must never be reported as fully approved. Covers the diagnosis flags,
the _finalise_recommendation gate, and the bottoming-from-thin-data case.
"""
from __future__ import annotations

from strategy.driving_advisor import _finalise_recommendation
from strategy._setup_constants import APPROVED_STATUSES, EVIDENCE_REQUIRED_STATUS
from strategy.setup_diagnosis import (
    _dominant_problem_key, DOMINANT_ADDRESSING_FIELDS, build_setup_diagnosis,
)


def _resp(changes):
    fields = {c["field"]: c.get("to_clamped", c.get("to")) for c in changes}
    return {
        "analysis": "Deterministic rule-first analysis.",
        "primary_issue": "bottoming",
        "changes": changes,
        "setup_fields": fields,
        "confidence": {"overall": "low", "reason": "test"},
    }


def _ch(field, to=5):
    return {"field": field, "from": 4, "to": to, "setting": field, "why": "x", "to_clamped": to}


_DOM_BOTTOMING = {
    "dominant_problem": "bottoming (required — bottoming needs attention)",
    "dominant_problem_key": "bottoming",
    "dominant_required": True,
    "dominant_evidence_sufficient": False,
}


# ------------------------------------------------------------- dominant key map

def test_dominant_key_recovery():
    assert _dominant_problem_key("bottoming (required — …)") == "bottoming"
    assert _dominant_problem_key("wheelspin (severe)") == "wheelspin"
    assert _dominant_problem_key("braking instability — lockups") == "braking_instability"
    assert _dominant_problem_key("front aero / platform limited …") == "front_aero_platform_limited"
    assert _dominant_problem_key("no dominant issue identified") == ""


def test_addressing_fields_cover_bottoming():
    assert "ride_height_rear" in DOMINANT_ADDRESSING_FIELDS["bottoming"]
    assert "arb_front" not in DOMINANT_ADDRESSING_FIELDS["bottoming"]


# ------------------------------------------------------------- the gate

def test_untreated_dominant_with_other_changes_is_partial():
    # Exact UAT shape: dominant bottoming (required, thin data) but only arb/final
    # drive/lsd changes -> partial_recommendation, not approved.
    resp = _resp([_ch("arb_front"), _ch("final_drive", to=4.2), _ch("lsd_accel", to=16)])
    r = _finalise_recommendation(resp, [], False, False, diagnosis=_DOM_BOTTOMING)
    assert r.status == "partial_recommendation"
    assert r.status in APPROVED_STATUSES           # survivors are still applyable
    assert {c["field"] for c in r.approved_changes} == {"arb_front", "final_drive", "lsd_accel"}
    assert "DEFERRED" in r.analysis or "deferred" in r.analysis.lower()


def test_untreated_dominant_with_no_changes_is_evidence_required():
    r = _finalise_recommendation(_resp([]), [], False, False, diagnosis=_DOM_BOTTOMING)
    assert r.status == EVIDENCE_REQUIRED_STATUS
    assert r.status not in APPROVED_STATUSES        # blocks apply
    assert r.approved_changes == []


def test_addressed_dominant_is_approved():
    # A ride-height change DOES address bottoming -> normal approval, no override.
    resp = _resp([_ch("ride_height_rear", to=72), _ch("arb_front")])
    r = _finalise_recommendation(resp, [], False, False, diagnosis=_DOM_BOTTOMING)
    assert r.status == "approved"


def test_no_dominant_required_leaves_status_unchanged():
    # When the dominant problem is not "required", the gate is inert.
    diag = {"dominant_problem_key": "wheelspin", "dominant_required": False,
            "dominant_evidence_sufficient": True, "dominant_problem": "wheelspin (major)"}
    r = _finalise_recommendation(_resp([_ch("lsd_accel", to=16)]), [], False, False, diagnosis=diag)
    assert r.status == "approved"


def test_gate_inert_without_diagnosis():
    # Back-compat: no diagnosis passed -> gate does nothing.
    r = _finalise_recommendation(_resp([_ch("arb_front")]), [], False, False)
    assert r.status == "approved"


def test_evidence_sufficient_untreated_uses_test_wording():
    diag = dict(_DOM_BOTTOMING, dominant_evidence_sufficient=True)
    r = _finalise_recommendation(_resp([_ch("arb_front")]), [], False, False, diagnosis=diag)
    assert r.status == "partial_recommendation"
    assert "targeted test" in r.analysis.lower()


# ------------------------------------------------------------- upstream flags

def test_diagnosis_exposes_coherence_flags():
    d = build_setup_diagnosis(laps=[], setup={"aero_front": 400}, car_name="",
                              event_ctx={}, feeling=None, location_confidence="low")
    for k in ("dominant_problem_key", "dominant_required", "dominant_evidence_sufficient"):
        assert k in d, k
