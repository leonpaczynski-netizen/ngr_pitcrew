"""Assurance Finding — the visible taxonomy of knowledge-assurance findings (Program 2, Phase 31).

Enumerates the assurance findings the audit can raise about the programme's engineering knowledge and
their severity. A finding is a defect or observation that bears on whether the knowledge can be
ASSURED. Hidden assumptions, unresolved conflicts, regressions, missing transfer boundaries,
non-determinism and data mutation are defects.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic.
"""
from __future__ import annotations

from enum import Enum

ASSURANCE_FINDING_VERSION = "assurance_finding_v1"


class AssuranceSeverity(str, Enum):
    BLOCKING = "blocking"
    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"
    INFORMATIONAL = "informational"


ASSURANCE_SEVERITY_PRIORITY = {
    "blocking": 0, "major": 1, "moderate": 2, "minor": 3, "informational": 4,
}


class AssuranceFindingType(str, Enum):
    OPEN_CONTRADICTION = "open_contradiction"
    UNRESOLVED_REGRESSION = "unresolved_regression"
    BLOCKING_ASSUMPTION_PRESENT = "blocking_assumption_present"
    ASSUMPTION_CAPS_READINESS_MISMATCH = "assumption_caps_readiness_mismatch"
    HIDDEN_ASSUMPTION = "hidden_assumption"
    STALE_KNOWLEDGE = "stale_knowledge"
    VERSION_SENSITIVITY_UNADDRESSED = "version_sensitivity_unaddressed"
    SINGLE_CONTEXT_RELIANCE = "single_context_reliance"
    DEPENDENT_EVIDENCE_RELIANCE = "dependent_evidence_reliance"
    CRITICAL_BLIND_SPOT = "critical_blind_spot"
    MISSING_TRANSFER_BOUNDARY = "missing_transfer_boundary"
    CONFIRMED_GOOD_UNVERIFIED = "confirmed_good_unverified"
    CONFLICTING_MATURITY_SIGNALS = "conflicting_maturity_signals"
    SUPERSEDED_STILL_REFERENCED = "superseded_still_referenced"
    READINESS_WITHOUT_COVERAGE = "readiness_without_coverage"
    UNKNOWN_ATTRIBUTE_RELIANCE = "unknown_attribute_reliance"
    UNVERIFIED_PROXY_RELIANCE = "unverified_proxy_reliance"
    INSUFFICIENT_EVIDENCE_FOR_GRADE = "insufficient_evidence_for_grade"
    NO_KNOWN_KNOWLEDGE = "no_known_knowledge"
    NON_DETERMINISTIC_OUTPUT = "non_deterministic_output"
    DATA_MUTATION_DETECTED = "data_mutation_detected"
    CLEAN = "clean"


# default severity per finding type (the audit may raise a specific instance at this severity).
_DEFAULT_SEVERITY = {
    AssuranceFindingType.OPEN_CONTRADICTION: AssuranceSeverity.BLOCKING,
    AssuranceFindingType.UNRESOLVED_REGRESSION: AssuranceSeverity.BLOCKING,
    AssuranceFindingType.BLOCKING_ASSUMPTION_PRESENT: AssuranceSeverity.BLOCKING,
    AssuranceFindingType.ASSUMPTION_CAPS_READINESS_MISMATCH: AssuranceSeverity.MAJOR,
    AssuranceFindingType.HIDDEN_ASSUMPTION: AssuranceSeverity.MAJOR,
    AssuranceFindingType.STALE_KNOWLEDGE: AssuranceSeverity.MAJOR,
    AssuranceFindingType.VERSION_SENSITIVITY_UNADDRESSED: AssuranceSeverity.MAJOR,
    AssuranceFindingType.SINGLE_CONTEXT_RELIANCE: AssuranceSeverity.MODERATE,
    AssuranceFindingType.DEPENDENT_EVIDENCE_RELIANCE: AssuranceSeverity.MODERATE,
    AssuranceFindingType.CRITICAL_BLIND_SPOT: AssuranceSeverity.MAJOR,
    AssuranceFindingType.MISSING_TRANSFER_BOUNDARY: AssuranceSeverity.MAJOR,
    AssuranceFindingType.CONFIRMED_GOOD_UNVERIFIED: AssuranceSeverity.MODERATE,
    AssuranceFindingType.CONFLICTING_MATURITY_SIGNALS: AssuranceSeverity.MODERATE,
    AssuranceFindingType.SUPERSEDED_STILL_REFERENCED: AssuranceSeverity.MINOR,
    AssuranceFindingType.READINESS_WITHOUT_COVERAGE: AssuranceSeverity.MAJOR,
    AssuranceFindingType.UNKNOWN_ATTRIBUTE_RELIANCE: AssuranceSeverity.MODERATE,
    AssuranceFindingType.UNVERIFIED_PROXY_RELIANCE: AssuranceSeverity.MAJOR,
    AssuranceFindingType.INSUFFICIENT_EVIDENCE_FOR_GRADE: AssuranceSeverity.INFORMATIONAL,
    AssuranceFindingType.NO_KNOWN_KNOWLEDGE: AssuranceSeverity.INFORMATIONAL,
    AssuranceFindingType.NON_DETERMINISTIC_OUTPUT: AssuranceSeverity.BLOCKING,
    AssuranceFindingType.DATA_MUTATION_DETECTED: AssuranceSeverity.BLOCKING,
    AssuranceFindingType.CLEAN: AssuranceSeverity.INFORMATIONAL,
}

_FINDING_TEXT = {
    AssuranceFindingType.OPEN_CONTRADICTION: "an unresolved contradiction remains in the evidence",
    AssuranceFindingType.UNRESOLVED_REGRESSION: "a regression has not been reconciled",
    AssuranceFindingType.BLOCKING_ASSUMPTION_PRESENT: "reliance rests on an assumption that, if "
                                                      "wrong, makes the conclusion unusable",
    AssuranceFindingType.ASSUMPTION_CAPS_READINESS_MISMATCH: "a domain is graded more ready than a "
                                                             "recorded assumption permits",
    AssuranceFindingType.HIDDEN_ASSUMPTION: "a relied-upon assumption is not surfaced",
    AssuranceFindingType.STALE_KNOWLEDGE: "knowledge requires re-validation before it can be assured",
    AssuranceFindingType.VERSION_SENSITIVITY_UNADDRESSED: "version-sensitive knowledge has not been "
                                                          "re-confirmed at the current version",
    AssuranceFindingType.SINGLE_CONTEXT_RELIANCE: "reliance rests on a single context",
    AssuranceFindingType.DEPENDENT_EVIDENCE_RELIANCE: "reliance rests on dependent evidence only",
    AssuranceFindingType.CRITICAL_BLIND_SPOT: "a critical coverage blind spot is present",
    AssuranceFindingType.MISSING_TRANSFER_BOUNDARY: "a transfer is relied on without a stated "
                                                    "boundary",
    AssuranceFindingType.CONFIRMED_GOOD_UNVERIFIED: "a confirmed-good behaviour is not independently "
                                                    "verified",
    AssuranceFindingType.CONFLICTING_MATURITY_SIGNALS: "the maturity signals for a domain conflict",
    AssuranceFindingType.SUPERSEDED_STILL_REFERENCED: "superseded knowledge is still referenced",
    AssuranceFindingType.READINESS_WITHOUT_COVERAGE: "a domain is graded ready despite open coverage "
                                                     "gaps",
    AssuranceFindingType.UNKNOWN_ATTRIBUTE_RELIANCE: "reliance rests on an unknown vehicle attribute",
    AssuranceFindingType.UNVERIFIED_PROXY_RELIANCE: "reliance rests on an unverified proxy",
    AssuranceFindingType.INSUFFICIENT_EVIDENCE_FOR_GRADE: "there is too little evidence to assure a "
                                                          "grade",
    AssuranceFindingType.NO_KNOWN_KNOWLEDGE: "no established engineering knowledge to assure yet",
    AssuranceFindingType.NON_DETERMINISTIC_OUTPUT: "a knowledge product lacks a stable deterministic "
                                                   "identity",
    AssuranceFindingType.DATA_MUTATION_DETECTED: "a read-only knowledge build mutated data",
    AssuranceFindingType.CLEAN: "no assurance defects were found",
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def default_severity(finding_type) -> str:
    for f in AssuranceFindingType:
        if f.value == _lc(finding_type):
            return _DEFAULT_SEVERITY.get(f, AssuranceSeverity.MODERATE).value
    return AssuranceSeverity.MODERATE.value


def finding_text(finding_type) -> str:
    for f in AssuranceFindingType:
        if f.value == _lc(finding_type):
            return _FINDING_TEXT.get(f, f.value)
    return _lc(finding_type)


def assurance_finding_versions() -> dict:
    return {"assurance_finding": ASSURANCE_FINDING_VERSION}
