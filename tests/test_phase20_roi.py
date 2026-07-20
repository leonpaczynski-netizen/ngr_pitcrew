"""Phase 20 — development-ROI domain tests.

ROI reuses existing measures verbatim (info gain from Phase 19, cost from Phase 19, confidence
from Phase 20); it recomputes none, ranks none, and is not an optimiser. About engineering
KNOWLEDGE, never lap time. Advisory only; never raises.
"""
import inspect

import pytest

from strategy.knowledge_confidence import assess_campaign_confidence
from strategy.development_roi import (
    estimate_campaign_roi, DevelopmentROI, DEVELOPMENT_ROI_VERSION, INFO_GAIN_SCALE,
)


def eff(conf=1, part=0, reg=0, nochg=0, unresolved=0, untested=1, disc=1, info="high",
        laps=13, tyres=1.08, mins=26.0, cid="c1", status="active"):
    executed = conf + part + reg + nochg
    return {"campaign_id": cid, "objective": "Cure entry understeer", "status": status,
            "remaining_information_gain": info, "estimated_remaining_laps": laps,
            "estimated_remaining_tyre_sets": tyres, "estimated_remaining_time_minutes": mins,
            "saturation": {"status": "building", "information_gain_remaining": info, "signals": {
                "confirmations": conf, "partial_improvements": part, "regressions": reg,
                "no_change": nochg, "executed": executed,
                "conflicting_evidence": (conf > 0 and reg > 0),
                "unresolved_mechanisms": unresolved,
                "remaining_untested_experiments": untested,
                "remaining_discriminating_experiments": disc}}}


CAL = {"reconciliations": 2, "overall_accuracy": 0.8, "elevated_risk_regressions": 0}


def _roi(e, cal=CAL):
    conf = assess_campaign_confidence(e, cal).to_dict()
    return estimate_campaign_roi(e, conf, cal)


def test_information_gain_reused_from_phase19():
    for label, expected in INFO_GAIN_SCALE.items():
        r = _roi(eff(info=label, untested=1))
        assert r.expected_information_gain == round(expected, 4)


def test_cost_reused_verbatim_from_phase19():
    r = _roi(eff(laps=17, tyres=1.42, mins=34.0))
    assert r.cost_to_close_gap["laps"] == 17
    assert r.cost_to_close_gap["tyre_sets"] == 1.42
    assert r.cost_to_close_gap["time_minutes"] == 34.0
    assert "Phase 19" in r.cost_to_close_gap["source"]


def test_no_testable_zero_session_value():
    r = _roi(eff(conf=2, untested=0, disc=0, info="none"))
    assert r.testable is False
    assert r.estimated_session_value == 0.0
    assert r.expected_confidence_gain == 0.0
    assert "cannot add engineering knowledge" in r.engineering_priority_reason


def test_knowledge_gap_is_inverse_confidence():
    e = eff(conf=1)
    conf = assess_campaign_confidence(e, CAL).to_dict()
    r = estimate_campaign_roi(e, conf, CAL)
    assert r.knowledge_gap == round(1.0 - conf["overall_score"], 4)


def test_discriminating_test_closes_more_gap():
    disc = _roi(eff(conf=1, disc=1, untested=1))
    validation = _roi(eff(conf=1, disc=0, untested=1))
    assert disc.expected_confidence_gain >= validation.expected_confidence_gain


def test_remaining_risk_levels():
    assert _roi(eff(conf=2, reg=0, unresolved=0)).remaining_risk == "none"
    assert _roi(eff(conf=2, reg=0, unresolved=1)).remaining_risk == "low"
    # a regression with no confirmation to conflict with -> moderate (not conflicting)
    assert _roi(eff(conf=0, reg=1, unresolved=0)).remaining_risk == "moderate"
    assert _roi(eff(conf=1, reg=1)).remaining_risk == "high"          # conflicting
    assert _roi(eff(conf=2), {"reconciliations": 1, "overall_accuracy": 0.5,
                              "elevated_risk_regressions": 1}).remaining_risk == "high"


def test_not_lap_time_language():
    r = _roi(eff())
    d = r.to_dict()
    blob = (r.engineering_priority_reason + " " + str(d)).lower()
    assert "lap time" not in blob and "laptime" not in blob


def test_priority_reason_disclaims_ranking():
    r = _roi(eff())
    assert "rank" in r.engineering_priority_reason.lower()


def test_inputs_fully_visible():
    r = _roi(eff(conf=1, reg=0, unresolved=1))
    for k in ("information_gain_remaining", "overall_confidence_level", "remaining_untested_experiments",
              "remaining_discriminating_experiments", "unresolved_mechanisms"):
        assert k in r.inputs


def test_deterministic():
    e = eff(conf=1, unresolved=1)
    assert _roi(e).to_dict() == _roi(e).to_dict()


def test_never_raises_on_garbage():
    for junk in (None, {}, {"saturation": None}):
        r = estimate_campaign_roi(junk, {}, {})
        assert isinstance(r, DevelopmentROI)


def test_no_forbidden_imports_or_optimiser():
    src = inspect.getsource(__import__("strategy.development_roi", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db", "def rank", "sort("):
        assert banned not in src
    assert DEVELOPMENT_ROI_VERSION == "development_roi_v1"
