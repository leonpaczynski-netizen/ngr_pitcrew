"""Knowledge Blind-Spots — where evidence coverage is thin relative to reliance (Phase 27).

A blind spot is a place where MORE evidence would strengthen confidence — it is NOT a defect, a
problem, or a negative result. Its severity reflects the GAP between how much a conclusion is relied
upon (its Phase-22 maturity / confidence / confirmed-good standing) and how broad / independent the
evidence supporting it actually is. A strong claim resting on thin, single-context or dependent-only
evidence is the important blind spot; an emerging domain with missing coverage is simply early-stage
and is flagged INFORMATIONAL, not as a concern.

The absence of evidence (MISSING) is never described as a negative outcome; a recorded regression is
the only negative, and it is labelled as such.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Tuple

from strategy.coverage_dimension import (
    BlindSpotSeverity, CoverageStatus, GAP_STATUSES, COVERAGE_STATUS_PRIORITY,
)

KNOWLEDGE_BLIND_SPOT_VERSION = "knowledge_blind_spot_v1"

_MATURITY_RANK = {"unknown": 0, "emerging": 1, "developing": 2, "established": 3, "mature": 4,
                  "complete": 5, "plateaued": 3}
_CONFIDENCE_RANK = {"unknown": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4, "very_high": 5}

_NOT_A_PROBLEM = ("A blind spot marks where additional evidence would strengthen confidence - it is "
                  "not a fault, a failure, or a negative result. Missing coverage means untested, "
                  "never wrong.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class KnowledgeBlindSpot:
    domain: str
    severity: str
    reliance: str                # how much the conclusion is relied upon (none/low/medium/high)
    evidence_robustness: str      # how broad/independent the support is (thin/limited/broad/unknown)
    gap_dimensions: Tuple[dict, ...]     # the dimensions that are coverage gaps
    missing_dimensions: Tuple[str, ...]  # dimensions with NO evidence (untested, not negative)
    rationale: str
    recommended_evidence: str            # what evidence would close it (NOT a setup instruction)
    note: str
    eval_version: str = KNOWLEDGE_BLIND_SPOT_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "severity": self.severity, "reliance": self.reliance,
                "evidence_robustness": self.evidence_robustness,
                "gap_dimensions": [dict(g) for g in self.gap_dimensions],
                "missing_dimensions": list(self.missing_dimensions), "rationale": self.rationale,
                "recommended_evidence": self.recommended_evidence, "note": self.note,
                "eval_version": self.eval_version}


def _reliance_rank(coverage: Mapping) -> int:
    mat = _MATURITY_RANK.get(_lc(coverage.get("current_maturity")), 0)
    conf = _CONFIDENCE_RANK.get(_lc(coverage.get("current_confidence")), 0)
    cg = bool(coverage.get("confirmed_good"))
    if mat == 0 and conf == 0 and not cg:
        return 0                              # unknown reliance
    score = 0
    if cg:
        score = max(score, 3)                 # confirmed-good is actively relied upon
    if mat >= 4 or conf >= 4:
        score = max(score, 3)                 # mature / high-confidence -> high reliance
    elif mat >= 3 or conf >= 3:
        score = max(score, 2)                 # established / medium
    elif mat >= 1 or conf >= 1:
        score = max(score, 1)                 # emerging / low
    return score


def _robustness_rank(coverage: Mapping) -> int:
    ev = coverage.get("evidence_totals") or {}
    independent = int(ev.get("independent") or 0)
    contexts = int(ev.get("compatible_contexts") or 0)
    conv = _lc(coverage.get("convergence_status"))
    if conv in ("strongly_converged", "stable_confirmed_good") and independent >= 2 and contexts >= 2:
        return 3                              # broad
    if independent >= 2 or contexts >= 2:
        return 2                              # limited-to-broad
    if independent >= 1 or int(ev.get("dependent") or 0) > 0 or int(ev.get("record_count") or 0) > 0:
        return 1                              # thin
    return 0                                  # unknown / none


_RELIANCE_LABEL = {0: "unknown", 1: "low", 2: "medium", 3: "high"}
_ROBUST_LABEL = {0: "unknown", 1: "thin", 2: "limited", 3: "broad"}


def classify_blind_spot(coverage: Mapping) -> KnowledgeBlindSpot:
    """Classify a domain's blind-spot severity from its coverage vs reliance. Returns a blind spot
    even when severity is INFORMATIONAL / UNKNOWN; the report decides what to surface. Never raises."""
    try:
        return _classify(coverage if isinstance(coverage, Mapping) else {})
    except Exception:
        return KnowledgeBlindSpot(domain=_lc((coverage or {}).get("domain")),
                                  severity=BlindSpotSeverity.UNKNOWN.value, reliance="unknown",
                                  evidence_robustness="unknown", gap_dimensions=(),
                                  missing_dimensions=(), rationale="", recommended_evidence="",
                                  note=_NOT_A_PROBLEM)


def _classify(coverage: Mapping) -> KnowledgeBlindSpot:
    domain = _lc(coverage.get("domain"))
    dims = [d for d in (coverage.get("dimensions") or []) if isinstance(d, Mapping)]
    gaps = [d for d in dims if _lc(d.get("status")) in GAP_STATUSES]
    gaps.sort(key=lambda d: (COVERAGE_STATUS_PRIORITY.get(_lc(d.get("status")), 99),
                             _lc(d.get("dimension"))))
    missing = tuple(_lc(d.get("dimension")) for d in dims
                    if _lc(d.get("status")) == CoverageStatus.MISSING.value)

    reliance = _reliance_rank(coverage)
    robustness = _robustness_rank(coverage)

    has_conflict = any(_lc(d.get("status")) == CoverageStatus.CONFLICTED_COVERAGE.value for d in dims)

    # severity ladder: gap between reliance and robustness (visible rules).
    if not gaps:
        severity = BlindSpotSeverity.INFORMATIONAL   # fully covered -> nothing to raise (filtered)
    elif reliance == 0:
        severity = BlindSpotSeverity.UNKNOWN         # can't judge reliance -> can't rank the gap
    elif has_conflict and reliance >= 2:
        severity = BlindSpotSeverity.CRITICAL        # relied upon AND internally contradicted
    elif reliance >= 3 and robustness <= 1:
        severity = BlindSpotSeverity.CRITICAL        # strong claim on thin evidence
    elif reliance >= 3 and robustness == 2:
        severity = BlindSpotSeverity.MATERIAL
    elif reliance == 2 and robustness <= 1:
        severity = BlindSpotSeverity.MATERIAL
    elif reliance == 2:
        severity = BlindSpotSeverity.MODERATE
    else:
        severity = BlindSpotSeverity.INFORMATIONAL   # low reliance / early stage -> expected

    rationale = (f"Reliance {_RELIANCE_LABEL[reliance]} vs evidence robustness "
                 f"{_ROBUST_LABEL[robustness]}: {len(gaps)} coverage gap(s)"
                 + (", including an unresolved conflict" if has_conflict else "")
                 + (f"; {len(missing)} dimension(s) untested (no evidence, not a negative result)."
                    if missing else "."))
    recommended = _recommended_evidence(gaps, missing)

    return KnowledgeBlindSpot(
        domain=domain, severity=severity.value, reliance=_RELIANCE_LABEL[reliance],
        evidence_robustness=_ROBUST_LABEL[robustness], gap_dimensions=tuple(gaps),
        missing_dimensions=missing, rationale=rationale, recommended_evidence=recommended,
        note=_NOT_A_PROBLEM)


def _recommended_evidence(gaps: List[Mapping], missing: Tuple[str, ...]) -> str:
    if not gaps:
        return ""
    top = _lc(gaps[0].get("dimension"))
    hints = {
        "independent_replication": "an independent observation in a fresh session would strengthen it",
        "track_variety": "evidence at another track would broaden it",
        "car_variety": "evidence on another car would broaden it",
        "transfer_validation": "confirmation in a second context would validate transfer",
        "confirmed_good_verification": "an independent re-observation would verify the confirmed-good",
        "conflict_resolution": "a discriminating observation would resolve the conflict",
        "regression_check": "probing the failure boundary would reveal the downside",
        "revalidation_currency": "a current-context observation would refresh it",
    }
    return hints.get(top, "additional independent evidence would strengthen this dimension") + "."


def blind_spot_versions() -> dict:
    return {"knowledge_blind_spot": KNOWLEDGE_BLIND_SPOT_VERSION}
