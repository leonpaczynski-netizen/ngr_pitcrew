"""Knowledge Assurance — audit the knowledge products for assurance defects (Program 2, Phase 31).

Given the Phase-26 re-validation, Phase-27 coverage, Phase-28 readiness, Phase-29 contradiction and
Phase-30 assumption products, it derives the assurance FINDINGS: unresolved contradictions and
regressions, blocking / capping assumptions relied upon, stale knowledge, single-context or dependent
reliance, critical blind spots, unverified confirmed-good, unknown-attribute / unverified-proxy
reliance, and structural defects (missing deterministic identity). It reports findings only; it
authors no setup and changes nothing.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Tuple

from strategy.assurance_finding import (
    ASSURANCE_FINDING_VERSION, ASSURANCE_SEVERITY_PRIORITY, AssuranceFindingType, AssuranceSeverity,
    default_severity, finding_text,
)

KNOWLEDGE_ASSURANCE_VERSION = "knowledge_assurance_v1"


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class AssuranceFinding:
    finding_type: str
    severity: str
    domain: str
    detail: str
    source_phase: str
    eval_version: str = KNOWLEDGE_ASSURANCE_VERSION

    def to_dict(self) -> dict:
        return {"finding_type": self.finding_type, "severity": self.severity, "domain": self.domain,
                "detail": self.detail, "source_phase": self.source_phase,
                "eval_version": self.eval_version}


def _f(ftype: AssuranceFindingType, domain: str, source_phase: str, detail: str = "",
       severity: str = "") -> AssuranceFinding:
    return AssuranceFinding(finding_type=ftype.value,
                            severity=severity or default_severity(ftype.value), domain=domain or "",
                            detail=detail or finding_text(ftype.value), source_phase=source_phase)


# assumption type -> (finding type) mapping for reliance defects.
_ASSUMPTION_FINDING = {
    "unverified_proxy_assumed": AssuranceFindingType.UNVERIFIED_PROXY_RELIANCE,
    "unknown_vehicle_attribute_assumed": AssuranceFindingType.UNKNOWN_ATTRIBUTE_RELIANCE,
    "generalisation_from_single_context": AssuranceFindingType.SINGLE_CONTEXT_RELIANCE,
    "independence_assumed": AssuranceFindingType.DEPENDENT_EVIDENCE_RELIANCE,
    "version_stability_assumed": AssuranceFindingType.VERSION_SENSITIVITY_UNADDRESSED,
    "confirmed_good_persists_assumed": AssuranceFindingType.CONFIRMED_GOOD_UNVERIFIED,
}


def audit(readiness: Mapping, contradiction: Mapping, assumptions: Mapping, coverage: Mapping,
          revalidation: Mapping) -> Tuple[Tuple[dict, ...], bool]:
    """Derive the assurance findings from the knowledge products. Returns (findings,
    has_known_knowledge). Deterministic; never raises."""
    try:
        return _audit(readiness or {}, contradiction or {}, assumptions or {}, coverage or {},
                      revalidation or {})
    except Exception:
        return ((), False)


def _audit(readiness: Mapping, contradiction: Mapping, assumptions: Mapping, coverage: Mapping,
           revalidation: Mapping) -> Tuple[Tuple[dict, ...], bool]:
    findings: List[AssuranceFinding] = []

    readiness_items = [i for i in (readiness.get("items") or []) if isinstance(i, Mapping)]
    has_known = bool(readiness_items)

    # coverage gap-count by domain (for the readiness-vs-coverage consistency check).
    gap_by_domain = {}
    for c in (coverage.get("domain_coverage") or []):
        if isinstance(c, Mapping):
            gap_by_domain[_lc(c.get("domain"))] = int(c.get("gap_count") or 0)

    # 1) readiness-driven findings.
    ready_domains = set()
    for i in readiness_items:
        dom = _lc(i.get("domain"))
        st = _lc(i.get("readiness_status"))
        if st == "ready":
            ready_domains.add(dom)
            if gap_by_domain.get(dom, 0) > 0:
                findings.append(_f(AssuranceFindingType.READINESS_WITHOUT_COVERAGE, dom, "Phase 28"))
        elif st == "conflicted":
            findings.append(_f(AssuranceFindingType.OPEN_CONTRADICTION, dom, "Phase 28"))
        elif st == "regressed":
            findings.append(_f(AssuranceFindingType.UNRESOLVED_REGRESSION, dom, "Phase 28"))
        elif st == "needs_revalidation":
            findings.append(_f(AssuranceFindingType.STALE_KNOWLEDGE, dom, "Phase 28"))
        elif st == "superseded":
            findings.append(_f(AssuranceFindingType.SUPERSEDED_STILL_REFERENCED, dom, "Phase 28"))
        elif st == "insufficient_evidence":
            findings.append(_f(AssuranceFindingType.INSUFFICIENT_EVIDENCE_FOR_GRADE, dom, "Phase 28"))
        if _lc(i.get("blind_spot_severity")) == "critical":
            findings.append(_f(AssuranceFindingType.CRITICAL_BLIND_SPOT, dom, "Phase 27"))

    # 2) contradiction-driven findings (open contradictions).
    for c in (contradiction.get("open_contradictions") or []):
        if isinstance(c, Mapping):
            findings.append(_f(AssuranceFindingType.OPEN_CONTRADICTION, _lc(c.get("domain")),
                               "Phase 29", detail=c.get("rationale") or ""))

    # 3) assumption-driven findings.
    for a in (assumptions.get("assumptions") or []):
        if not isinstance(a, Mapping):
            continue
        dom = _lc(a.get("domain"))
        atype = _lc(a.get("assumption_type"))
        impact = _lc(a.get("impact"))
        ftype = _ASSUMPTION_FINDING.get(atype)
        if ftype is not None:
            findings.append(_f(ftype, dom, "Phase 30"))
        elif impact == "blocks_reliance":
            findings.append(_f(AssuranceFindingType.BLOCKING_ASSUMPTION_PRESENT, dom, "Phase 30"))
        # consistency: a fully-ready domain must not carry a readiness-capping/blocking assumption.
        if dom in ready_domains and impact in ("blocks_reliance", "caps_readiness", "narrows_scope"):
            findings.append(_f(AssuranceFindingType.ASSUMPTION_CAPS_READINESS_MISMATCH, dom,
                               "Phase 28/30"))

    # 4) version-sensitivity from re-validation (invalidated by version change).
    for it in (revalidation.get("items") or []):
        if isinstance(it, Mapping) and _lc(it.get("freshness_status")) == \
                "invalidated_by_version_change":
            findings.append(_f(AssuranceFindingType.VERSION_SENSITIVITY_UNADDRESSED,
                               _lc(it.get("domain")), "Phase 26"))

    # 5) structural self-check: each present sub-report must carry a stable deterministic identity.
    for name, rep in (("readiness", readiness), ("coverage", coverage),
                      ("contradiction", contradiction), ("assumptions", assumptions),
                      ("revalidation", revalidation)):
        if _has_content(rep) and not _lc(rep.get("content_fingerprint")):
            findings.append(_f(AssuranceFindingType.NON_DETERMINISTIC_OUTPUT, "", name,
                               detail=f"the {name} product lacks a content fingerprint"))

    # dedup by (finding_type, domain), keeping the most severe.
    best: dict = {}
    for f in findings:
        key = (f.finding_type, f.domain)
        cur = best.get(key)
        if cur is None or ASSURANCE_SEVERITY_PRIORITY.get(f.severity, 9) < \
                ASSURANCE_SEVERITY_PRIORITY.get(cur.severity, 9):
            best[key] = f
    deduped = list(best.values())

    if not has_known:
        deduped.append(_f(AssuranceFindingType.NO_KNOWN_KNOWLEDGE, "", "Phase 22"))

    # CLEAN when nothing above informational was found.
    if has_known and not any(ASSURANCE_SEVERITY_PRIORITY.get(f.severity, 9)
                             < ASSURANCE_SEVERITY_PRIORITY["informational"] for f in deduped):
        deduped.append(_f(AssuranceFindingType.CLEAN, "", "audit"))

    deduped.sort(key=lambda f: (ASSURANCE_SEVERITY_PRIORITY.get(f.severity, 9), f.finding_type,
                                f.domain))
    return tuple(f.to_dict() for f in deduped), has_known


def _has_content(rep: Mapping) -> bool:
    if not isinstance(rep, Mapping):
        return False
    for key in ("items", "domain_coverage", "contradictions", "assumptions"):
        if rep.get(key):
            return True
    return False


def knowledge_assurance_versions() -> dict:
    return {"knowledge_assurance": KNOWLEDGE_ASSURANCE_VERSION,
            "assurance_finding": ASSURANCE_FINDING_VERSION}
