"""Phase 25 — knowledge-convergence + transition domain tests.

Strong convergence requires independent evidence; repeated dependent evidence does not converge;
confirmed-good distinct; conflict reduces certainty; regression prevents false convergence; retired
stays retired; later weaker evidence does not override; supersession requires stronger evidence;
context-bound is not universal; heavily contradicted -> honest unresolved.
"""
import inspect

import pytest

from strategy.knowledge_convergence import (
    ConvergenceStatus, assess_convergence, CONVERGENCE_PRIORITY, STRONG_MIN_INDEPENDENT_GROUPS,
    KNOWLEDGE_CONVERGENCE_VERSION,
)
from strategy.knowledge_transition import (
    KnowledgeTransitionType, classify_transition, outcome_kind,
)


def auth(maturity="mature", confidence="high", confirmations=2, regressions=0, conflicting=False,
         confirmed_good=False, transfer_class="architecture_dependent", transfer_limits=(),
         retired=()):
    return {"maturity": maturity, "confidence": confidence, "confirmations": confirmations,
            "regressions": regressions, "conflicting": conflicting, "confirmed_good": confirmed_good,
            "transfer_class": transfer_class, "transfer_limitations": list(transfer_limits),
            "retired_directions": list(retired), "unresolved_boundaries": [],
            "compatible_contexts": 2, "context_limited_observations": 0}


def ind(independent=2, partial=0, same_session=0, same_record=0):
    return {"independent_groups": independent, "partially_independent": partial,
            "same_session": same_session, "same_source_record": same_record,
            "distinct_sessions": independent + partial}


# --- convergence -----------------------------------------------------------
def test_strong_requires_independent_evidence():
    c = assess_convergence("differential", [], ind(independent=2), auth())
    assert c.convergence_status == ConvergenceStatus.STRONGLY_CONVERGED.value


def test_dependent_repeats_do_not_strongly_converge():
    # one independent line + many dependent repeats -> not strong
    c = assess_convergence("differential", [], ind(independent=1, same_record=4), auth())
    assert c.convergence_status != ConvergenceStatus.STRONGLY_CONVERGED.value
    assert c.convergence_status in (ConvergenceStatus.CONVERGING.value,)


def test_confirmed_good_distinct():
    c = assess_convergence("differential", [], ind(independent=2),
                           auth(confirmed_good=True))
    assert c.convergence_status == ConvergenceStatus.STABLE_CONFIRMED_GOOD.value


def test_conflict_reduces_certainty():
    c = assess_convergence("springs", [], ind(independent=1),
                           auth(confirmations=1, regressions=1, conflicting=True))
    assert c.convergence_status == ConvergenceStatus.CONFLICTING.value


def test_regression_prevents_false_convergence():
    c = assess_convergence("springs", [], ind(independent=0),
                           auth(confirmations=0, regressions=2))
    assert c.convergence_status == ConvergenceStatus.REGRESSED.value


def test_context_bound_is_not_universal():
    c = assess_convergence("gearbox", [], ind(independent=2),
                           auth(transfer_class="car_track_specific"))
    assert c.convergence_status == ConvergenceStatus.STABLE_BUT_CONTEXT_BOUND.value


def test_insufficient_evidence():
    c = assess_convergence("dampers", [], ind(independent=0),
                           auth(maturity="emerging", confirmations=0, regressions=0))
    assert c.convergence_status == ConvergenceStatus.INSUFFICIENT_EVIDENCE.value


def test_superseded_requires_stronger_later_evidence():
    points = [
        {"transition_type": "direction_retired", "sequence_key": 1, "confidence_after": "medium"},
        {"transition_type": "independent_confirmation", "sequence_key": 3,
         "confidence_after": "high"}]
    c = assess_convergence("differential", points, ind(independent=2), auth())
    assert c.convergence_status == ConvergenceStatus.SUPERSEDED.value


def test_investigation_aid_when_transfer_limited():
    c = assess_convergence("springs", [], ind(independent=2),
                           auth(transfer_limits=["manufacturer_specific: x"]))
    assert c.suitable_only_as_investigation_aid is True


def test_lineage_summary_mentions_one_lineage():
    c = assess_convergence("differential", [], ind(independent=2), auth())
    assert "one lineage" in c.evidence_lineage_summary


def test_convergence_enum_complete():
    vals = {e.value for e in ConvergenceStatus}
    assert vals == {"strongly_converged", "converging", "stable_but_context_bound",
                    "stable_confirmed_good", "mixed", "conflicting", "regressed", "superseded",
                    "insufficient_evidence", "unknown"}
    for v in vals:
        assert v in CONVERGENCE_PRIORITY


def test_convergence_deterministic():
    args = ("differential", [], ind(independent=2), auth())
    assert assess_convergence(*args).to_dict() == assess_convergence(*args).to_dict()


def test_convergence_never_raises():
    for junk in (None, {}, {"maturity": None}):
        c = assess_convergence("x", None, None, junk)
        assert c.convergence_status in {e.value for e in ConvergenceStatus}


# --- transitions -----------------------------------------------------------
def test_transition_enum_complete():
    assert len({t.value for t in KnowledgeTransitionType}) == 18


def test_initial_observation():
    r = classify_transition({"observed": False}, {"outcome_status": "confirmed_improvement"},
                            "independent")
    assert r.transition_type == KnowledgeTransitionType.INITIAL_OBSERVATION.value


def test_independent_confirmation():
    r = classify_transition({"observed": True, "positive_count": 1, "best_conf_rank": 3},
                            {"outcome_status": "confirmed_improvement", "confidence_level": "high"},
                            "independent")
    assert r.transition_type == KnowledgeTransitionType.INDEPENDENT_CONFIRMATION.value


def test_repeated_support_when_dependent():
    r = classify_transition({"observed": True, "positive_count": 1, "best_conf_rank": 3},
                            {"outcome_status": "confirmed_improvement", "confidence_level": "high"},
                            "same_session")
    assert r.transition_type == KnowledgeTransitionType.REPEATED_SUPPORT.value


def test_direction_retired_on_regression_after_support():
    r = classify_transition({"observed": True, "positive_count": 2, "best_conf_rank": 3},
                            {"outcome_status": "regression", "is_failed_direction": True}, "independent")
    assert r.transition_type == KnowledgeTransitionType.DIRECTION_RETIRED.value


def test_conflict_introduced():
    r = classify_transition({"observed": True, "positive_count": 2, "best_conf_rank": 3},
                            {"outcome_status": "regression", "is_failed_direction": False},
                            "independent")
    assert r.transition_type == KnowledgeTransitionType.CONFLICT_INTRODUCED.value


def test_later_weaker_positive_does_not_reopen_retired():
    r = classify_transition({"observed": True, "positive_count": 1, "retired": True,
                             "best_conf_rank": 3},
                            {"outcome_status": "confirmed_improvement", "confidence_level": "low"},
                            "independent")
    assert r.transition_type == KnowledgeTransitionType.NO_MATERIAL_CHANGE.value


def test_stronger_positive_reopens_retired():
    r = classify_transition({"observed": True, "positive_count": 1, "retired": True,
                             "best_conf_rank": 1},
                            {"outcome_status": "confirmed_improvement", "confidence_level": "high"},
                            "independent")
    assert r.transition_type == KnowledgeTransitionType.INDEPENDENT_CONFIRMATION.value


def test_outcome_kind():
    assert outcome_kind("confirmed_improvement") == "positive"
    assert outcome_kind("regression") == "negative"
    assert outcome_kind("insufficient_evidence") == "insufficient"
    assert outcome_kind("no_meaningful_change") == "neutral"


def test_no_forbidden_imports():
    for mod in ("strategy.knowledge_convergence", "strategy.knowledge_transition"):
        src = inspect.getsource(__import__(mod, fromlist=["x"]))
        for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                       "date.today", "time.time", "from data.session_db", "sklearn", "numpy"):
            assert banned not in src, f"{mod}: {banned}"
    assert KNOWLEDGE_CONVERGENCE_VERSION == "knowledge_convergence_v1"
