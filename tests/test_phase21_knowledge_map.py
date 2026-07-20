"""Phase 21 — season knowledge-map domain tests.

Every state reachable + explained + sourced; classification uses existing Phase-18/19/20
measures only; deterministic; never raises.
"""
import inspect

import pytest

from strategy.season_knowledge_map import (
    SeasonKnowledgeState, classify_campaign_knowledge, SEASON_KNOWLEDGE_MAP_VERSION,
)


def rec(status="active", opportunity="worth_another_confirmation", confidence="medium",
        conflicting=False, executed=1, confirmations=1, testable=True, cid="c1"):
    return {"campaign_id": cid, "objective": "obj", "status": status,
            "opportunity": opportunity, "confidence_level": confidence,
            "conflicting": conflicting, "executed": executed, "confirmations": confirmations,
            "testable": testable}


def test_engineering_complete():
    r = classify_campaign_knowledge(rec(status="completed", opportunity="complete"))
    assert r.state == SeasonKnowledgeState.ENGINEERING_COMPLETE.value


def test_contradictory():
    r = classify_campaign_knowledge(rec(conflicting=True, opportunity="worth_contradiction_testing"))
    assert r.state == SeasonKnowledgeState.CONTRADICTORY.value


def test_knowledge_plateau():
    r = classify_campaign_knowledge(rec(opportunity="knowledge_plateau", testable=False,
                                        confidence="low"))
    assert r.state == SeasonKnowledgeState.KNOWLEDGE_PLATEAU.value


def test_no_useful_experiments_overtested():
    r = classify_campaign_knowledge(rec(opportunity="evidence_exhausted", testable=False,
                                        confidence="low"))
    assert r.state == SeasonKnowledgeState.NO_USEFUL_EXPERIMENTS.value


def test_no_useful_experiments_saturated_not_worth():
    r = classify_campaign_knowledge(rec(opportunity="not_worth_further_work", testable=False,
                                        confidence="medium"))
    assert r.state == SeasonKnowledgeState.NO_USEFUL_EXPERIMENTS.value


def test_well_understood():
    r = classify_campaign_knowledge(rec(confidence="very_high",
                                        opportunity="not_worth_further_work"))
    assert r.state == SeasonKnowledgeState.WELL_UNDERSTOOD.value


def test_emerging_confidence():
    r = classify_campaign_knowledge(rec(confidence="medium", opportunity="none", confirmations=1))
    assert r.state == SeasonKnowledgeState.EMERGING_CONFIDENCE.value


def test_needs_confirmation_medium():
    r = classify_campaign_knowledge(rec(confidence="medium",
                                        opportunity="worth_another_confirmation"))
    assert r.state == SeasonKnowledgeState.NEEDS_CONFIRMATION.value


def test_needs_confirmation_low():
    r = classify_campaign_knowledge(rec(confidence="low", opportunity="none", executed=2))
    assert r.state == SeasonKnowledgeState.NEEDS_CONFIRMATION.value


def test_little_evidence_no_execution():
    r = classify_campaign_knowledge(rec(confidence="unknown", opportunity="none", executed=0))
    assert r.state == SeasonKnowledgeState.LITTLE_EVIDENCE.value


def test_little_evidence_very_low():
    r = classify_campaign_knowledge(rec(confidence="very_low", opportunity="none", executed=1))
    assert r.state == SeasonKnowledgeState.LITTLE_EVIDENCE.value


def test_every_state_explained_and_sourced():
    for r in (rec(status="completed", opportunity="complete"),
              rec(conflicting=True),
              rec(confidence="very_high", opportunity="not_worth_further_work"),
              rec(confidence="unknown", executed=0)):
        k = classify_campaign_knowledge(r)
        assert k.reason and k.source and "factors" in k.to_dict()


def test_deterministic():
    r = rec(confidence="medium")
    assert classify_campaign_knowledge(r).to_dict() == classify_campaign_knowledge(r).to_dict()


def test_never_raises_on_garbage():
    for junk in (None, {}, {"confidence_level": None}, {"executed": "x"}):
        k = classify_campaign_knowledge(junk)
        assert k.state in {s.value for s in SeasonKnowledgeState}


def test_no_forbidden_imports():
    src = inspect.getsource(__import__("strategy.season_knowledge_map", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db", "sklearn", "numpy"):
        assert banned not in src
    assert SEASON_KNOWLEDGE_MAP_VERSION == "season_knowledge_map_v1"
