"""Phase 20 — campaign-opportunity domain tests.

Classification orchestrates existing authorities (Phase-18 status + Phase-19 saturation +
Phase-20 confidence); every branch is explained. It never overrides Phase-18 completion.
Advisory only; never raises.
"""
import inspect

import pytest

from strategy.knowledge_confidence import assess_campaign_confidence
from strategy.development_roi import estimate_campaign_roi
from strategy.campaign_opportunity import (
    CampaignOpportunity, classify_campaign_opportunity, CAMPAIGN_OPPORTUNITY_VERSION,
)


def eff(conf=1, part=0, reg=0, nochg=0, unresolved=0, untested=1, disc=1, info="high",
        sat="building", status="active", cid="c1"):
    executed = conf + part + reg + nochg
    return {"campaign_id": cid, "objective": "obj", "status": status,
            "remaining_information_gain": info,
            "estimated_remaining_laps": 13, "estimated_remaining_tyre_sets": 1.0,
            "estimated_remaining_time_minutes": 26.0,
            "saturation": {"status": sat, "information_gain_remaining": info, "signals": {
                "confirmations": conf, "partial_improvements": part, "regressions": reg,
                "no_change": nochg, "executed": executed,
                "conflicting_evidence": (conf > 0 and reg > 0),
                "unresolved_mechanisms": unresolved,
                "remaining_untested_experiments": untested,
                "remaining_discriminating_experiments": disc}}}


CAL = {"reconciliations": 2, "overall_accuracy": 0.8}


def _classify(e, cal=CAL):
    conf = assess_campaign_confidence(e, cal).to_dict()
    roi = estimate_campaign_roi(e, conf, cal).to_dict()
    return classify_campaign_opportunity(e, conf, roi)


def test_completed_status_is_complete():
    r = _classify(eff(status="completed", untested=0, disc=0))
    assert r.opportunity == CampaignOpportunity.COMPLETE.value and r.worthwhile is False


def test_ready_to_freeze_is_nearly_complete():
    r = _classify(eff(status="ready_to_freeze", conf=2, untested=0, disc=0, info="none",
                      sat="saturated"))
    assert r.opportunity == CampaignOpportunity.NEARLY_COMPLETE.value


def test_conflicting_with_discriminator_is_contradiction_testing():
    r = _classify(eff(conf=1, reg=1, disc=1, untested=1))
    assert r.opportunity == CampaignOpportunity.WORTH_CONTRADICTION_TESTING.value
    assert r.worthwhile is True


def test_overtested_is_evidence_exhausted():
    r = _classify(eff(conf=0, nochg=3, untested=0, disc=0, info="none", sat="overtested"))
    assert r.opportunity == CampaignOpportunity.EVIDENCE_EXHAUSTED.value
    assert r.worthwhile is False


def test_unresolved_mechanism_with_test_is_mechanism_isolation():
    r = _classify(eff(conf=1, unresolved=1, untested=1, disc=0))
    assert r.opportunity == CampaignOpportunity.WORTH_MECHANISM_ISOLATION.value


def test_confirmed_not_high_with_test_is_another_confirmation():
    r = _classify(eff(conf=1, unresolved=0, untested=1, disc=0))
    assert r.opportunity == CampaignOpportunity.WORTH_ANOTHER_CONFIRMATION.value


def test_nothing_left_saturated_not_worth():
    r = _classify(eff(conf=2, unresolved=0, untested=0, disc=0, info="none", sat="saturated"))
    assert r.opportunity == CampaignOpportunity.NOT_WORTH_FURTHER_WORK.value


def test_nothing_left_unresolved_is_plateau():
    # executed but stuck: confirmations 0, a no-change, nothing left, low confidence
    r = _classify(eff(conf=0, nochg=1, unresolved=1, untested=0, disc=0, info="none",
                      sat="building"))
    assert r.opportunity == CampaignOpportunity.KNOWLEDGE_PLATEAU.value


def test_never_overrides_phase18_completion():
    # even with a huge remaining info gain, a COMPLETED campaign stays COMPLETE
    r = _classify(eff(status="completed", conf=2, unresolved=2, untested=5, disc=3, info="high"))
    assert r.opportunity == CampaignOpportunity.COMPLETE.value


def test_factors_visible():
    r = _classify(eff(conf=1, reg=1))
    for k in ("campaign_status", "saturation_status", "confidence_level", "executed",
              "remaining_untested_experiments", "conflicting_evidence"):
        assert k in r.factors


def test_deterministic():
    e = eff(conf=1, unresolved=1)
    assert _classify(e).to_dict() == _classify(e).to_dict()


def test_never_raises_on_garbage():
    for junk in (None, {}, {"saturation": None}):
        r = classify_campaign_opportunity(junk, {}, {})
        assert r.opportunity in {o.value for o in CampaignOpportunity}


def test_no_forbidden_imports():
    src = inspect.getsource(__import__("strategy.campaign_opportunity", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db",
                   "def complete", "def freeze", "mark_applied("):
        assert banned not in src
    assert CAMPAIGN_OPPORTUNITY_VERSION == "campaign_opportunity_v1"
