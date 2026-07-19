"""Programme Readiness Grade — a rule-based, transparent aggregate grade (Program 2, Phase 28).

Grades the whole programme's engineering knowledge readiness from the distribution of per-domain
readiness statuses. It is NOT an opaque numeric score: the grade is decided by a small set of
visible rules over counts, and the report always exposes the counts that produced it. A single
recorded problem (conflict / regression) prevents a HIGH grade; too little assessable knowledge
yields INSUFFICIENT_EVIDENCE rather than a falsely low or high grade.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Mapping, Sequence, Tuple

from strategy.knowledge_readiness import RELYABLE_STATUSES, BLOCKING_STATUSES

READINESS_GRADE_VERSION = "readiness_grade_v1"

# Visible thresholds. A grade never depends on anything but these counts + rules.
MIN_ASSESSABLE_FOR_GRADE = 2          # fewer assessable domains -> INSUFFICIENT_EVIDENCE
HIGH_RELYABLE_FRACTION = 0.75         # >= this fraction relyable AND no blockers -> HIGH
MEDIUM_RELYABLE_FRACTION = 0.40       # >= this fraction relyable -> at least MEDIUM


class ProgrammeReadinessGrade(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def grade_programme(items: Sequence[Mapping]) -> dict:
    """Return the rule-based programme grade + the visible counts + the rule that fired. Never
    raises. ``items`` are per-domain readiness dicts."""
    try:
        return _grade([i for i in (items or []) if isinstance(i, Mapping)])
    except Exception:
        return {"grade": ProgrammeReadinessGrade.INSUFFICIENT_EVIDENCE.value, "counts": {},
                "assessable": 0, "relyable": 0, "blocking": 0, "rule": "error", "reasons": ()}


def _grade(items: List[Mapping]) -> dict:
    counts: dict = {}
    for i in items:
        counts[_lc(i.get("readiness_status"))] = counts.get(_lc(i.get("readiness_status")), 0) + 1

    total = len(items)
    # "assessable" excludes domains we genuinely cannot judge (insufficient / unknown).
    unassessable = counts.get("insufficient_evidence", 0) + counts.get("unknown", 0)
    assessable = total - unassessable
    relyable = sum(counts.get(s, 0) for s in RELYABLE_STATUSES)
    blocking = sum(counts.get(s, 0) for s in BLOCKING_STATUSES)

    reasons: List[str] = []
    if assessable < MIN_ASSESSABLE_FOR_GRADE:
        grade, rule = ProgrammeReadinessGrade.INSUFFICIENT_EVIDENCE, "too_few_assessable_domains"
        reasons.append(f"only {assessable} assessable domain(s) (need "
                       f"{MIN_ASSESSABLE_FOR_GRADE})")
    else:
        frac = relyable / assessable if assessable else 0.0
        if blocking > 0:
            # a recorded conflict/regression prevents HIGH regardless of the relyable fraction.
            if frac >= MEDIUM_RELYABLE_FRACTION:
                grade, rule = ProgrammeReadinessGrade.MEDIUM, "blockers_present_cap_medium"
            else:
                grade, rule = ProgrammeReadinessGrade.LOW, "blockers_and_low_relyable"
            reasons.append(f"{blocking} domain(s) with a recorded conflict/regression prevent a "
                           "HIGH grade")
        elif frac >= HIGH_RELYABLE_FRACTION:
            grade, rule = ProgrammeReadinessGrade.HIGH, "high_relyable_no_blockers"
            reasons.append(f"{relyable}/{assessable} assessable domain(s) are relyable with no "
                           "recorded blockers")
        elif frac >= MEDIUM_RELYABLE_FRACTION:
            grade, rule = ProgrammeReadinessGrade.MEDIUM, "medium_relyable"
            reasons.append(f"{relyable}/{assessable} assessable domain(s) are relyable")
        else:
            grade, rule = ProgrammeReadinessGrade.LOW, "low_relyable"
            reasons.append(f"only {relyable}/{assessable} assessable domain(s) are relyable")

    return {"grade": grade.value, "counts": counts, "total_domains": total,
            "assessable": assessable, "relyable": relyable, "blocking": blocking,
            "unassessable": unassessable, "rule": rule, "reasons": tuple(reasons)}


def readiness_grade_versions() -> dict:
    return {"readiness_grade": READINESS_GRADE_VERSION}
