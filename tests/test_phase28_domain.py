"""Phase 28 — pure domain unit tests: per-domain readiness ladder + rule-based programme grade.

Core doctrine: 'ready' means the evidence supports relying on the knowledge, never 'apply this
setup'; unvalidated knowledge is never ready; a recorded conflict/regression blocks readiness and
prevents a HIGH grade; the grade is rule-based over visible counts, not an opaque score.
"""
from strategy.knowledge_readiness import (
    KnowledgeReadinessStatus as R, READINESS_PRIORITY, RELYABLE_STATUSES, BLOCKING_STATUSES,
    classify_readiness,
)
from strategy.readiness_grade import (
    ProgrammeReadinessGrade as G, grade_programme, MIN_ASSESSABLE_FOR_GRADE,
    HIGH_RELYABLE_FRACTION,
)


def _conv(**kw):
    base = {"domain": "differential", "convergence_status": "strongly_converged",
            "independent_support_count": 3, "dependent_support_count": 0, "confirmed_good": True,
            "compatible_contexts": 3, "current_maturity": "mature", "current_confidence": "high"}
    base.update(kw)
    return base


def _classify(conv=None, fresh="current", gap=0, blind=""):
    return classify_readiness(_conv(**(conv or {})), {"freshness_status": fresh},
                              {"gap_count": gap, "blind_spot_severity": blind}).readiness_status


# ---- enums / constants ---------------------------------------------------------------------

def test_11_statuses_all_have_priority():
    assert len(list(KnowledgeReadinessStatus_all())) == 11
    for s in KnowledgeReadinessStatus_all():
        assert s.value in READINESS_PRIORITY


def KnowledgeReadinessStatus_all():
    return list(R)


def test_relyable_and_blocking_sets():
    assert RELYABLE_STATUSES == {"ready", "ready_with_limitations", "context_bound_only"}
    assert BLOCKING_STATUSES == {"conflicted", "regressed"}


# ---- readiness ladder ----------------------------------------------------------------------

def test_strong_current_well_covered_is_ready():
    assert _classify(gap=0) == R.READY.value


def test_strong_current_minor_gaps_is_ready_with_limitations():
    assert _classify(gap=2) == R.READY_WITH_LIMITATIONS.value


def test_conflict_blocks():
    assert _classify({"convergence_status": "conflicting", "conflict_count": 1},
                     fresh="weakened_by_conflict") == R.CONFLICTED.value


def test_regression_blocks():
    assert _classify({"convergence_status": "regressed", "regression_count": 1},
                     fresh="weakened_by_regression") == R.REGRESSED.value


def test_version_change_needs_revalidation():
    assert _classify(fresh="invalidated_by_version_change") == R.NEEDS_REVALIDATION.value
    assert _classify(fresh="revalidation_required") == R.NEEDS_REVALIDATION.value


def test_critical_blind_spot_needs_more_evidence():
    assert _classify(blind="critical") == R.NEEDS_MORE_EVIDENCE.value


def test_context_bound_only():
    assert _classify({"convergence_status": "stable_but_context_bound"}) == \
        R.CONTEXT_BOUND_ONLY.value


def test_provisional_when_converging():
    assert _classify({"convergence_status": "converging", "confirmed_good": False}) == \
        R.PROVISIONAL.value


def test_superseded():
    assert _classify({"convergence_status": "superseded"}, fresh="superseded") == R.SUPERSEDED.value


def test_insufficient_evidence():
    assert _classify({"convergence_status": "insufficient_evidence", "confirmed_good": False},
                     fresh="insufficient_context_evidence") == R.INSUFFICIENT_EVIDENCE.value


def test_ready_never_marks_unvalidated():
    """A domain that is only converging must never come out READY."""
    item = classify_readiness(_conv(convergence_status="converging", confirmed_good=False),
                              {"freshness_status": "current"}, {"gap_count": 1})
    assert item.readiness_status != R.READY.value
    assert item.usable_as != "decision" or item.readiness_status == R.CONTEXT_BOUND_ONLY.value


def test_readiness_item_usable_as_and_no_action():
    item = classify_readiness(_conv(), {"freshness_status": "current"}, {"gap_count": 0})
    assert item.usable_as == "decision"
    assert "never 'apply this setup'" in item.no_action_statement


# ---- programme grade -----------------------------------------------------------------------

def _items(*statuses):
    return [{"readiness_status": s} for s in statuses]


def test_grade_high_needs_no_blockers():
    g = grade_programme(_items("ready", "ready", "ready", "ready_with_limitations"))
    assert g["grade"] == G.HIGH.value and g["blocking"] == 0
    assert g["relyable"] / g["assessable"] >= HIGH_RELYABLE_FRACTION


def test_single_blocker_prevents_high():
    g = grade_programme(_items("ready", "ready", "ready", "conflicted"))
    assert g["grade"] != G.HIGH.value
    assert g["blocking"] == 1


def test_grade_insufficient_when_too_few_assessable():
    g = grade_programme(_items("ready", "insufficient_evidence"))
    assert g["grade"] == G.INSUFFICIENT_EVIDENCE.value
    assert g["assessable"] < MIN_ASSESSABLE_FOR_GRADE


def test_grade_exposes_counts_and_rule():
    g = grade_programme(_items("ready", "provisional", "needs_more_evidence"))
    assert "counts" in g and "rule" in g and g["reasons"]


def test_grade_low_when_few_relyable():
    g = grade_programme(_items("provisional", "needs_more_evidence", "provisional",
                               "needs_more_evidence"))
    assert g["grade"] == G.LOW.value


def test_grade_empty_safe():
    g = grade_programme([])
    assert g["grade"] == G.INSUFFICIENT_EVIDENCE.value
