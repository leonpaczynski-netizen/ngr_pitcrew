"""Phase 22 — knowledge-maturity domain tests.

Every level reachable + explained + sourced; determined only from existing measures; no invented
weighting; deterministic; never raises.
"""
import inspect

import pytest

from strategy.knowledge_maturity import (
    KnowledgeMaturity, classify_maturity, best_confidence, KNOWLEDGE_MATURITY_VERSION,
)


def sig(campaigns=1, executed=2, confirmations=1, regressions=0, conflicting=False,
        unresolved=0, testable=False, confidences=("medium",), states=("needs_confirmation",)):
    return {"contributing_campaigns": campaigns, "executed_total": executed,
            "confirmations_total": confirmations, "regressions_total": regressions,
            "conflicting_any": conflicting, "unresolved_total": unresolved,
            "testable_any": testable, "confidence_levels": list(confidences),
            "knowledge_states": list(states)}


def test_unknown_no_evidence():
    r = classify_maturity(sig(campaigns=0, executed=0))
    assert r.maturity == KnowledgeMaturity.UNKNOWN.value


def test_complete_via_state():
    r = classify_maturity(sig(states=("engineering_complete",), confidences=("very_high",),
                              testable=False))
    assert r.maturity == KnowledgeMaturity.COMPLETE.value


def test_complete_via_confidence_no_remaining():
    r = classify_maturity(sig(confidences=("very_high",), testable=False, conflicting=False,
                              states=("well_understood",)))
    assert r.maturity == KnowledgeMaturity.COMPLETE.value


def test_plateaued():
    r = classify_maturity(sig(confidences=("low",), states=("knowledge_plateau",),
                              testable=False, executed=3))
    assert r.maturity == KnowledgeMaturity.PLATEAUED.value


def test_mature():
    r = classify_maturity(sig(confidences=("high",), testable=True, states=("well_understood",)))
    assert r.maturity == KnowledgeMaturity.MATURE.value


def test_established():
    r = classify_maturity(sig(confidences=("medium",), confirmations=1, testable=True,
                              states=("emerging_confidence",)))
    assert r.maturity == KnowledgeMaturity.ESTABLISHED.value


def test_developing():
    r = classify_maturity(sig(confidences=("low",), confirmations=0, executed=2, testable=True,
                              states=("needs_confirmation",)))
    assert r.maturity == KnowledgeMaturity.DEVELOPING.value


def test_emerging():
    r = classify_maturity(sig(confidences=("low",), confirmations=0, executed=1, testable=True,
                              states=("little_evidence",)))
    assert r.maturity == KnowledgeMaturity.EMERGING.value


def test_best_confidence_picks_strongest():
    assert best_confidence(["low", "very_high", "medium"]) == "very_high"
    assert best_confidence([]) == "unknown"
    assert best_confidence(["nonsense"]) == "unknown"


def test_every_level_explained_and_sourced():
    for s in (sig(campaigns=0, executed=0), sig(states=("engineering_complete",)),
              sig(confidences=("high",), testable=True),
              sig(confidences=("low",), states=("knowledge_plateau",), testable=False)):
        r = classify_maturity(s)
        assert r.reason and r.source and "factors" in r.to_dict()


def test_deterministic():
    s = sig(confidences=("medium",), confirmations=1)
    assert classify_maturity(s).to_dict() == classify_maturity(s).to_dict()


def test_never_raises_on_garbage():
    for junk in (None, {}, {"executed_total": "x"}, {"confidence_levels": None}):
        r = classify_maturity(junk)
        assert r.maturity in {m.value for m in KnowledgeMaturity}


def test_no_forbidden_imports():
    src = inspect.getsource(__import__("strategy.knowledge_maturity", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db", "sklearn", "numpy",
                   "networkx", "def optimi", "argmax"):
        assert banned not in src
    assert KNOWLEDGE_MATURITY_VERSION == "knowledge_maturity_v1"
