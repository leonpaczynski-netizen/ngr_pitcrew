"""Programme Assurance Grade — a rule-based, transparent assurance grade (Program 2, Phase 31).

Grades whether the programme's engineering knowledge can be assured, from the severities of the
audit findings. It is NOT an opaque score: the grade is decided by a small set of visible rules over
severity counts, and the report always exposes the counts. A single BLOCKING finding prevents ASSURED
(and ASSURED_WITH_LIMITATIONS); too little established knowledge yields INSUFFICIENT_EVIDENCE rather
than a falsely clean or failing grade.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Mapping, Sequence

ASSURANCE_GRADE_VERSION = "assurance_grade_v1"


class ProgrammeAssuranceGrade(str, Enum):
    ASSURED = "assured"
    ASSURED_WITH_LIMITATIONS = "assured_with_limitations"
    PARTIALLY_ASSURED = "partially_assured"
    NOT_ASSURED = "not_assured"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def grade_assurance(findings: Sequence[Mapping], has_known_knowledge: bool) -> dict:
    """Return the rule-based assurance grade + the visible severity counts + the fired rule. Never
    raises. ``findings`` are audit finding dicts with a ``severity`` field."""
    try:
        return _grade([f for f in (findings or []) if isinstance(f, Mapping)],
                      bool(has_known_knowledge))
    except Exception:
        return {"grade": ProgrammeAssuranceGrade.INSUFFICIENT_EVIDENCE.value, "counts": {},
                "rule": "error", "reasons": ()}


def _grade(findings: List[Mapping], has_known: bool) -> dict:
    counts = {"blocking": 0, "major": 0, "moderate": 0, "minor": 0, "informational": 0}
    for f in findings:
        sev = _lc(f.get("severity"))
        if sev in counts:
            counts[sev] += 1

    reasons: List[str] = []
    if not has_known:
        grade, rule = ProgrammeAssuranceGrade.INSUFFICIENT_EVIDENCE, "no_known_knowledge"
        reasons.append("no established engineering knowledge to assure yet")
    elif counts["blocking"] > 0:
        grade, rule = ProgrammeAssuranceGrade.NOT_ASSURED, "blocking_finding_present"
        reasons.append(f"{counts['blocking']} blocking finding(s) prevent assurance")
    elif counts["major"] > 0:
        grade, rule = ProgrammeAssuranceGrade.PARTIALLY_ASSURED, "major_findings_present"
        reasons.append(f"{counts['major']} major finding(s) - partial assurance only")
    elif counts["moderate"] > 0 or counts["minor"] > 0:
        grade, rule = ProgrammeAssuranceGrade.ASSURED_WITH_LIMITATIONS, "only_moderate_or_minor"
        reasons.append(f"{counts['moderate']} moderate + {counts['minor']} minor finding(s) - "
                       "assured within limits")
    else:
        grade, rule = ProgrammeAssuranceGrade.ASSURED, "no_findings_above_informational"
        reasons.append("no assurance defects found")

    return {"grade": grade.value, "counts": counts, "total_findings": len(findings),
            "rule": rule, "reasons": tuple(reasons)}


def assurance_grade_versions() -> dict:
    return {"assurance_grade": ASSURANCE_GRADE_VERSION}
