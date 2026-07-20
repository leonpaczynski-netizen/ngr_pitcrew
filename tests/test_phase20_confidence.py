"""Phase 20 — knowledge-confidence domain tests.

Every component is explained (reason/source/calculation), every threshold is a named visible
constant, contradictions/repeatability behave as specified, and the overall is the equal-
weighted mean of the included components (no hidden weighting). Advisory only; never raises.
"""
import inspect

import pytest

from strategy.knowledge_confidence import (
    ConfidenceLevel, assess_campaign_confidence, KNOWLEDGE_CONFIDENCE_VERSION,
    MIN_CONFIRMATIONS_HIGH, MIN_REPEATABILITY, CONTRADICTION_FULL_PENALTY,
    MECHANISM_FULL_PENALTY, MIN_PREDICTION_ACCURACY_HIGH,
)


def eff(conf=1, part=0, reg=0, nochg=0, unresolved=0, untested=1, disc=1, info="high",
        sat="building", cid="c1"):
    executed = conf + part + reg + nochg
    return {"campaign_id": cid, "objective": "Cure entry understeer", "status": "active",
            "remaining_information_gain": info, "estimated_remaining_laps": 13,
            "estimated_remaining_tyre_sets": 1.0, "estimated_remaining_time_minutes": 26.0,
            "saturation": {"status": sat, "information_gain_remaining": info, "signals": {
                "confirmations": conf, "partial_improvements": part, "regressions": reg,
                "no_change": nochg, "executed": executed,
                "conflicting_evidence": (conf > 0 and reg > 0),
                "unresolved_mechanisms": unresolved,
                "remaining_untested_experiments": untested,
                "remaining_discriminating_experiments": disc}}}


CAL = {"reconciliations": 2, "overall_accuracy": 0.8}


def test_unknown_when_no_evidence():
    e = eff(conf=0, untested=2)
    e["saturation"]["signals"]["executed"] = 0
    r = assess_campaign_confidence(e, {})
    assert r.overall_level == ConfidenceLevel.UNKNOWN.value and r.overall_score is None


def test_single_confirmation_capped_at_medium():
    r = assess_campaign_confidence(eff(conf=1, unresolved=0), CAL)
    assert r.overall_level == ConfidenceLevel.MEDIUM.value
    assert any("MIN_REPEATABILITY" in c for c in r.caps_applied)


def test_two_confirmations_resolved_high_or_very_high():
    r = assess_campaign_confidence(
        eff(conf=2, unresolved=0, untested=0, disc=0, info="none", sat="saturated"), CAL)
    assert r.overall_level in (ConfidenceLevel.HIGH.value, ConfidenceLevel.VERY_HIGH.value)


def test_conflicting_caps_at_low():
    r = assess_campaign_confidence(eff(conf=1, reg=1), CAL)
    assert r.overall_level == ConfidenceLevel.LOW.value
    assert any("conflicting" in c for c in r.caps_applied)


def test_only_regression_caps_very_low():
    r = assess_campaign_confidence(eff(conf=0, reg=1, unresolved=0), CAL)
    assert r.overall_level == ConfidenceLevel.VERY_LOW.value


def test_contradiction_component_falls_with_regressions():
    clean = assess_campaign_confidence(eff(conf=2, reg=0), CAL).component("contradiction_level")
    dirty = assess_campaign_confidence(eff(conf=2, reg=1), CAL).component("contradiction_level")
    assert clean.score > dirty.score


def test_mechanism_support_falls_with_unresolved():
    a = assess_campaign_confidence(eff(conf=2, unresolved=0), CAL).component("mechanism_support")
    b = assess_campaign_confidence(eff(conf=2, unresolved=1), CAL).component("mechanism_support")
    assert a.score > b.score


def test_prediction_accuracy_excluded_when_no_calibration():
    r = assess_campaign_confidence(eff(conf=2), {})
    pa = r.component("prediction_accuracy")
    assert pa.included_in_overall is False and pa.score is None


def test_prediction_accuracy_included_when_calibrated():
    r = assess_campaign_confidence(eff(conf=2), CAL)
    pa = r.component("prediction_accuracy")
    assert pa.included_in_overall is True and pa.score == 0.8


def test_remaining_uncertainty_informational_not_in_overall():
    r = assess_campaign_confidence(eff(conf=2), CAL)
    ru = r.component("remaining_uncertainty")
    assert ru.included_in_overall is False


def test_overall_is_equal_weighted_mean_of_included():
    r = assess_campaign_confidence(eff(conf=2, unresolved=0, untested=0, disc=0,
                                       info="none", sat="saturated"), CAL)
    included = [c.score for c in r.components if c.included_in_overall and c.score is not None]
    assert r.overall_score == round(sum(included) / len(included), 4)
    assert any("equal-weighted mean" in x for x in r.reasons)


def test_every_component_explained():
    r = assess_campaign_confidence(eff(conf=2), CAL)
    for c in r.components:
        assert c.reason and c.source and c.calculation


def test_thresholds_visible():
    r = assess_campaign_confidence(eff(conf=1), CAL)
    for k in ("min_confirmations_high", "min_repeatability", "contradiction_full_penalty",
              "mechanism_full_penalty", "min_prediction_accuracy_high"):
        assert k in r.thresholds


def test_deterministic():
    e = eff(conf=1, reg=1, unresolved=1)
    assert assess_campaign_confidence(e, CAL).to_dict() == \
        assess_campaign_confidence(e, CAL).to_dict()


def test_never_raises_on_garbage():
    for junk in (None, {}, {"saturation": None}, {"saturation": {"signals": None}},
                 {"saturation": {"signals": {"confirmations": "x"}}}):
        r = assess_campaign_confidence(junk, None)
        assert r.overall_level in {lvl.value for lvl in ConfidenceLevel}


def test_no_forbidden_imports():
    src = inspect.getsource(__import__("strategy.knowledge_confidence", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db"):
        assert banned not in src
    assert KNOWLEDGE_CONFIDENCE_VERSION == "knowledge_confidence_v1"
    # decision numbers are named constants, not bare literals in the logic
    assert "MIN_REPEATABILITY" in src and "CONF_BAND_HIGH" in src
