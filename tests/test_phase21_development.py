"""Phase 21 — season-development summary + report-assembly domain tests.

Every metric exposes reason/source/calculation; totals reuse Phase-17 value + Phase-19 cost
verbatim; the report preserves campaign order and aggregates nothing new. Deterministic;
empty + large-count safe; never raises.
"""
import inspect

import pytest

from strategy.season_development import summarize_season, SEASON_DEVELOPMENT_VERSION
from strategy.season_engineering_report import build_season_report


def rec(cid, status="active", opportunity="worth_another_confirmation", confidence="medium",
        total_value=1.0, remaining_value=0.5, laps=13, tyres=1.0, minutes=26.0):
    return {"campaign_id": cid, "objective": cid, "status": status, "opportunity": opportunity,
            "confidence_level": confidence, "total_value": total_value,
            "remaining_value": remaining_value, "remaining_laps": laps,
            "remaining_tyre_sets": tyres, "remaining_minutes": minutes}


def kstate(cid, state):
    return {"campaign_id": cid, "state": state}


def test_counts_and_totals():
    records = [rec("A", status="completed", confidence="very_high", total_value=1.0,
                   remaining_value=0.0),
               rec("B", status="active", confidence="low", total_value=2.0,
                   remaining_value=1.5),
               rec("C", status="active", opportunity="knowledge_plateau", confidence="medium")]
    states = [kstate("A", "engineering_complete"), kstate("B", "needs_confirmation"),
              kstate("C", "knowledge_plateau")]
    s = summarize_season(records, states)
    assert s.value("campaign_count") == 3
    assert s.value("completed_campaigns") == 1
    assert s.value("high_confidence_campaigns") == 1
    assert s.value("low_confidence_campaigns") == 1
    assert s.value("campaigns_plateaued") == 1
    assert s.value("total_engineering_value") == 4.0
    assert s.value("total_remaining_value") == 2.0
    assert s.value("estimated_remaining_cost")["laps"] == 39
    assert s.value("knowledge_completion") == round(1 / 3, 4)


def test_every_metric_has_reason_source_calculation():
    s = summarize_season([rec("A")], [kstate("A", "needs_confirmation")])
    for name, m in s.to_dict()["metrics"].items():
        assert m["reason"] and m["source"] and m["calculation"]


def test_empty_season():
    s = summarize_season([], [])
    assert s.value("campaign_count") == 0
    assert "No engineering campaigns" in s.engineering_summary


def test_deterministic():
    records = [rec("A"), rec("B")]
    states = [kstate("A", "well_understood"), kstate("B", "needs_confirmation")]
    assert summarize_season(records, states).to_dict() == \
        summarize_season(records, states).to_dict()


def test_never_raises_on_garbage():
    s = summarize_season([None, 5, {"campaign_id": "x"}], [None])
    assert "campaign_count" in s.to_dict()["metrics"]


# --- report assembly --------------------------------------------------------
def _prog(cid, fam, reg, fields, mech, status="active"):
    return {"identity": {"campaign_id": cid, "objective_family": fam, "objective_region": reg,
                         "car": "RSR", "track": "Fuji", "layout": "fc", "discipline": "Race"},
            "objective": {"title": f"{fam}-{reg}", "source_mechanisms": mech}, "status": status,
            "experiments": [{"field": f, "engineering_value": 0.6} for f in fields]}


def _eff(cid, conf=1, testable=True, laps=13):
    return {"campaign_id": cid, "objective": cid, "remaining_information_gain": "high",
            "estimated_remaining_laps": laps, "estimated_remaining_tyre_sets": 1.0,
            "estimated_remaining_time_minutes": 26.0,
            "experiment_costs": [{"engineering_value": 0.6, "testable": testable,
                                  "field": "arb_front"}],
            "saturation": {"signals": {"confirmations": conf, "regressions": 0,
                                       "executed": conf, "conflicting_evidence": False,
                                       "unresolved_mechanisms": 0,
                                       "remaining_untested_experiments": 1 if testable else 0}}}


def _qual(cid, level, opp, worth=True):
    return {"campaign_id": cid, "objective": cid, "confidence": {"overall_level": level,
            "overall_score": 0.7}, "roi": {"knowledge_gap": 0.3, "testable": True},
            "opportunity": {"opportunity": opp, "worthwhile": worth}}


def test_report_assembles_all_three_layers():
    prog = {"content_fingerprint": "p", "context_summary": {"car": "RSR"}, "campaigns": [
        _prog("A", "rotation", "front", ["arb_front"], ["m1"]),
        _prog("B", "rotation", "front", ["arb_front"], ["m2"])]}
    eff = {"content_fingerprint": "e", "campaigns": [_eff("A", conf=2), _eff("B", conf=1)]}
    qual = {"content_fingerprint": "q", "campaigns": [
        _qual("A", "very_high", "not_worth_further_work", False),
        _qual("B", "medium", "worth_another_confirmation")]}
    rep = build_season_report(prog, eff, qual).to_dict()
    assert rep["development"]["metrics"]["campaign_count"]["value"] == 2
    assert len(rep["knowledge_map"]) == 2
    # A and B duplicate (same family/region/field)
    assert any(e["relationship"] == "duplicates" for e in rep["relationships"]["edges"])
    assert rep["campaigns"][0]["campaign_id"] == "A"      # order preserved
    assert rep["safety_statement"]


def test_report_order_preserved_and_deterministic():
    prog = {"campaigns": [_prog("A", "rotation", "front", ["arb_front"], ["m1"]),
                          _prog("B", "braking", "rear", ["brake_bias"], ["m9"])]}
    eff = {"campaigns": [_eff("A"), _eff("B")]}
    qual = {"campaigns": [_qual("A", "medium", "worth_another_confirmation"),
                          _qual("B", "medium", "worth_another_confirmation")]}
    r1 = build_season_report(prog, eff, qual).to_dict()
    r2 = build_season_report(prog, eff, qual).to_dict()
    assert r1 == r2
    assert [c["campaign_id"] for c in r1["campaigns"]] == ["A", "B"]


def test_report_empty_safe():
    rep = build_season_report({}, {}, {}).to_dict()
    assert rep["campaigns"] == [] and rep["safety_statement"]


def test_report_never_raises_on_garbage():
    for junk in (None, {"campaigns": None}, {"campaigns": [None]}):
        rep = build_season_report(junk, junk, junk)
        assert rep.safety_statement


def test_no_forbidden_imports():
    for mod in ("strategy.season_development", "strategy.season_engineering_report"):
        src = inspect.getsource(__import__(mod, fromlist=["x"]))
        for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                       "date.today", "time.time", "from data.session_db", "sklearn", "numpy"):
            assert banned not in src, f"{mod}: {banned}"
    assert SEASON_DEVELOPMENT_VERSION == "season_development_v1"
