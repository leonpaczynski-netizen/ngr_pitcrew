"""Assurance-Driven Engineering Priority — pure deterministic domain (Program 2, Phase 32).

Converts the Phase-31 assurance audit findings into a prioritised list of EVIDENCE INVESTIGATIONS
that would most efficiently improve programme assurance. It answers "given the current assurance
verdict, what evidence should the programme collect next, and why?".

It is deterministic, offline, read-only and ADVISORY ONLY. It produces a priority ORDER, never a
schedule; it names no dates, sessions, drivers, cars, tracks or resources; it creates no experiment,
campaign or setup; it carries no setup values; and it never claims a proposed investigation
guarantees an assurance-grade increase (impact is always expressed as potential).

Transparent valuation: every priority dimension exposes raw value, visible weight, contribution and
rationale - the priority score is a visible weighted sum, never a hidden number. The information-gain
dimension is weighted highest, mirroring the Phase-17 experiment-portfolio doctrine
(``DIMENSION_WEIGHTS["information_gain"] = 3.0``); this module reuses that DOCTRINE with an
assurance-specific data model (it does not import Phase-17 setup-experiment candidates or mutate a
portfolio).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.engineering_knowledge_graph import KnowledgeDomain

ASSURANCE_ENGINEERING_PRIORITY_VERSION = "assurance_engineering_priority_v1"
ASSURANCE_ENGINEERING_PRIORITY_SCHEMA = 1

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]

# feasibility threshold: below this an investigation is not currently actionable -> deferred.
FEASIBILITY_THRESHOLD = 0.5


class InvestigationPriorityBand(str, Enum):
    BLOCKING = "blocking"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DEFER = "defer"
    NO_ACTION = "no_action"


# lower = ranked first.
_BAND_ORDER = {"blocking": 0, "high": 1, "medium": 2, "low": 3, "defer": 4, "no_action": 5}
_ACTIONABLE_BANDS = ("blocking", "high", "medium", "low")


class InvestigationType(str, Enum):
    REVALIDATION = "revalidation"
    CONTRADICTION_DISCRIMINATION = "contradiction_discrimination"
    INDEPENDENCE_IMPROVEMENT = "independence_improvement"
    CONTEXT_EXPANSION = "context_expansion"
    REPEATED_CONFIRMATION = "repeated_confirmation"
    ASSUMPTION_ESTABLISHMENT = "assumption_establishment"
    MISSING_DOMAIN_COVERAGE = "missing_domain_coverage"
    VERSION_SENSITIVE_CONFIRMATION = "version_sensitive_confirmation"
    CONVERGENCE_CONFIRMATION = "convergence_confirmation"
    PROVENANCE_IMPROVEMENT = "provenance_improvement"


_TYPE_ORDER = [t.value for t in InvestigationType]

# ---- transparent valuation dimensions (visible weights; information-gain highest, per Phase 17) ---
# value dimensions add priority; penalty dimensions subtract it. Every weight is visible.
VALUE_DIMENSION_WEIGHTS = {
    "information_gain": 3.0,               # PRIMARY objective (aligned with Phase-17 doctrine)
    "blocker_clearance": 2.5,
    "cross_finding_leverage": 2.0,
    "contradiction_discrimination": 2.0,
    "independence_gain": 1.75,
    "assumption_reduction": 1.5,
    "freshness_value": 1.5,
    "context_relevance": 1.25,
    "evidence_availability": 1.0,          # feasibility
}
PENALTY_DIMENSION_WEIGHTS = {
    "duplication_penalty": 1.5,
    "dependency_penalty": 1.5,
    "collection_cost": 1.0,
}
DIMENSION_WEIGHTS = {**VALUE_DIMENSION_WEIGHTS, **PENALTY_DIMENSION_WEIGHTS}

# per-type base information-gain (0..1) — discrimination / independence / version are most valuable.
_TYPE_INFO_GAIN = {
    "contradiction_discrimination": 1.0, "independence_improvement": 0.9,
    "version_sensitive_confirmation": 0.85, "assumption_establishment": 0.8,
    "convergence_confirmation": 0.7, "context_expansion": 0.7, "revalidation": 0.65,
    "missing_domain_coverage": 0.6, "repeated_confirmation": 0.35, "provenance_improvement": 0.5,
}
# per-type base collection effort (0..1) — audit fixes are cheap; new contexts/discrimination dear.
_TYPE_EFFORT = {
    "provenance_improvement": 0.2, "repeated_confirmation": 0.3, "revalidation": 0.4,
    "assumption_establishment": 0.5, "independence_improvement": 0.5, "missing_domain_coverage": 0.55,
    "convergence_confirmation": 0.6, "version_sensitive_confirmation": 0.6, "context_expansion": 0.7,
    "contradiction_discrimination": 0.75,
}

# finding_type -> investigation_type (grounded in the Phase-31 finding taxonomy).
_FINDING_TO_TYPE = {
    "open_contradiction": InvestigationType.CONTRADICTION_DISCRIMINATION,
    "unresolved_regression": InvestigationType.INDEPENDENCE_IMPROVEMENT,
    "stale_knowledge": InvestigationType.REVALIDATION,
    "version_sensitivity_unaddressed": InvestigationType.VERSION_SENSITIVE_CONFIRMATION,
    "single_context_reliance": InvestigationType.CONTEXT_EXPANSION,
    "dependent_evidence_reliance": InvestigationType.INDEPENDENCE_IMPROVEMENT,
    "critical_blind_spot": InvestigationType.MISSING_DOMAIN_COVERAGE,
    "confirmed_good_unverified": InvestigationType.INDEPENDENCE_IMPROVEMENT,
    "unknown_attribute_reliance": InvestigationType.ASSUMPTION_ESTABLISHMENT,
    "unverified_proxy_reliance": InvestigationType.ASSUMPTION_ESTABLISHMENT,
    "blocking_assumption_present": InvestigationType.ASSUMPTION_ESTABLISHMENT,
    "assumption_caps_readiness_mismatch": InvestigationType.ASSUMPTION_ESTABLISHMENT,
    "readiness_without_coverage": InvestigationType.REPEATED_CONFIRMATION,
    "conflicting_maturity_signals": InvestigationType.CONVERGENCE_CONFIRMATION,
    "superseded_still_referenced": InvestigationType.PROVENANCE_IMPROVEMENT,
    "missing_transfer_boundary": InvestigationType.PROVENANCE_IMPROVEMENT,
    "non_deterministic_output": InvestigationType.PROVENANCE_IMPROVEMENT,
    "data_mutation_detected": InvestigationType.PROVENANCE_IMPROVEMENT,
    "insufficient_evidence_for_grade": InvestigationType.CONVERGENCE_CONFIRMATION,
    # no_known_knowledge / clean produce no investigation.
}

# deterministic prerequisite pairs (within a domain): (prerequisite_type, dependent_type).
_PREREQUISITE_PAIRS = frozenset({
    ("independence_improvement", "contradiction_discrimination"),
    ("independence_improvement", "convergence_confirmation"),
    ("version_sensitive_confirmation", "context_expansion"),
    ("version_sensitive_confirmation", "convergence_confirmation"),
    ("context_expansion", "convergence_confirmation"),
    ("revalidation", "convergence_confirmation"),
    ("missing_domain_coverage", "independence_improvement"),
    ("missing_domain_coverage", "repeated_confirmation"),
})

_SEVERITY_RANK = {"blocking": 4, "major": 3, "moderate": 2, "minor": 1, "informational": 0}
_SEVERITY_BAND = {"blocking": InvestigationPriorityBand.BLOCKING,
                  "major": InvestigationPriorityBand.HIGH,
                  "moderate": InvestigationPriorityBand.MEDIUM,
                  "minor": InvestigationPriorityBand.LOW,
                  "informational": InvestigationPriorityBand.DEFER}

_ADVISORY = ("Advisory only: this is the highest-priority EVIDENCE to collect, not an approved "
             "experiment, not a setup recommendation, and not permission to Apply. It creates no "
             "experiment, campaign or schedule, allocates no resources, and does not guarantee an "
             "assurance-grade increase.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else round(float(x), 6))


def finding_id(finding: Mapping) -> str:
    """Stable, timestamp-free id for a Phase-31 finding (findings carry no id of their own)."""
    payload = {"t": _lc(finding.get("finding_type")), "d": _lc(finding.get("domain")),
               "p": _lc(finding.get("source_phase"))}
    return "af_" + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class PriorityDimension:
    name: str
    raw: float          # 0..1 magnitude on this axis
    weight: float       # visible weight
    contribution: float # signed contribution to the priority score (value +, penalty -)
    rationale: str

    def to_dict(self) -> dict:
        return {"name": self.name, "raw": self.raw, "weight": self.weight,
                "contribution": self.contribution, "rationale": self.rationale}


@dataclass(frozen=True)
class InvestigationDependency:
    prerequisite_candidate_id: str
    prerequisite_type: str
    reason: str

    def to_dict(self) -> dict:
        return {"prerequisite_candidate_id": self.prerequisite_candidate_id,
                "prerequisite_type": self.prerequisite_type, "reason": self.reason}


@dataclass(frozen=True)
class InvestigationCandidate:
    candidate_id: str
    domains: Tuple[str, ...]
    investigation_type: str
    linked_finding_ids: Tuple[str, ...]
    finding_types: Tuple[str, ...]
    max_severity: str
    evidence_requested: str
    why_needed: str
    current_evidence_state: str
    discriminating_requirement: str
    expected_assurance_impact: str
    impact_limitations: str
    dimensions: Tuple[dict, ...]
    priority_score: float
    priority_band: str
    dependencies: Tuple[dict, ...]
    defer_conditions: str
    rationale: str
    advisory_statement: str
    eval_version: str = ASSURANCE_ENGINEERING_PRIORITY_VERSION

    def dimension(self, name: str) -> Optional[dict]:
        for d in self.dimensions:
            if d.get("name") == name:
                return d
        return None

    def to_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "domains": list(self.domains),
                "investigation_type": self.investigation_type,
                "linked_finding_ids": list(self.linked_finding_ids),
                "finding_types": list(self.finding_types), "max_severity": self.max_severity,
                "evidence_requested": self.evidence_requested, "why_needed": self.why_needed,
                "current_evidence_state": self.current_evidence_state,
                "discriminating_requirement": self.discriminating_requirement,
                "expected_assurance_impact": self.expected_assurance_impact,
                "impact_limitations": self.impact_limitations,
                "dimensions": [dict(d) for d in self.dimensions],
                "priority_score": self.priority_score, "priority_band": self.priority_band,
                "dependencies": [dict(d) for d in self.dependencies],
                "defer_conditions": self.defer_conditions, "rationale": self.rationale,
                "advisory_statement": self.advisory_statement, "eval_version": self.eval_version}


# ---------------------------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------------------------

def _index_by_domain(rep: Mapping, key: str) -> dict:
    out: dict = {}
    for it in ((rep or {}).get(key) or []):
        if isinstance(it, Mapping):
            out.setdefault(_lc(it.get("domain")), []).append(it)
    return out


def _candidate_id(domain: str, itype: str, finding_ids: Sequence[str]) -> str:
    payload = {"d": domain, "t": itype, "f": sorted(_lc(f) for f in finding_ids)}
    return "aei_" + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()[:12]


def _evidence_request(itype: InvestigationType, domain: str, ctx: Mapping) -> Tuple[str, str, str]:
    """Return (evidence_requested, why_needed, discriminating_requirement) for a candidate.
    Strings only; never names dates/sessions/resources; never emits setup values."""
    d = domain or "programme"
    t = itype
    if t == InvestigationType.CONTRADICTION_DISCRIMINATION:
        return ("an observation designed to distinguish the competing explanations for this domain "
                "(the confirming vs the regressing conclusion)",
                f"the {d} evidence contradicts itself and no single conclusion currently stands",
                "the new evidence must vary the factor that separates the two claims (e.g. a "
                "controlled independent re-observation under the disputed condition) - a generic "
                "'collect more laps' does not discriminate")
    if t == InvestigationType.INDEPENDENCE_IMPROVEMENT:
        return ("a genuinely INDEPENDENT confirmation from a separate session / source",
                f"the {d} conclusion currently rests on dependent or correlated evidence",
                "the new evidence must be independent of the existing source - repeated correlated "
                "observations do not add independence")
    if t == InvestigationType.VERSION_SENSITIVE_CONFIRMATION:
        return ("a confirmation at the current GT7 version",
                f"the {d} knowledge is version-sensitive and has not been re-confirmed at the "
                "current version",
                "the observation must be taken under the current version to restore validity")
    if t == InvestigationType.REVALIDATION:
        return ("a current-context re-observation",
                f"the {d} knowledge needs re-validation before it can be relied upon", "")
    if t == InvestigationType.CONTEXT_EXPANSION:
        return ("an observation in a second, compatible context",
                f"the {d} conclusion has only been observed in a single context",
                "the observation must be in a genuinely different but compatible context to test "
                "generalisation - not a repeat of the same context")
    if t == InvestigationType.CONVERGENCE_CONFIRMATION:
        return ("further independent evidence across compatible contexts",
                f"the {d} evidence has not yet converged",
                "convergence requires INDEPENDENT repeated evidence, not duplicated observations")
    if t == InvestigationType.ASSUMPTION_ESTABLISHMENT:
        return ("evidence that would establish or reject the relied-upon assumption",
                f"reliance on {d} rests on an assumption that is not established",
                "the evidence must directly test the assumption; until then it remains an "
                "assumption, never a fact")
    if t == InvestigationType.MISSING_DOMAIN_COVERAGE:
        return ("evidence covering the untested dimension(s) of this domain",
                f"the {d} domain has a critical coverage blind spot",
                "note: absence of evidence is not evidence of absence - the blind spot is untested, "
                "not disproven")
    if t == InvestigationType.REPEATED_CONFIRMATION:
        return ("an additional confirming observation",
                f"the {d} readiness rests on evidence with open coverage gaps", "")
    if t == InvestigationType.PROVENANCE_IMPROVEMENT:
        return ("an audit-quality / provenance improvement (a stable identity or a resolved "
                "reference), not new track evidence",
                f"an audit-chain deficiency prevents assuring {d}", "")
    return ("further evidence", f"{d} needs stronger evidence", "")


def _build_candidate(domain: str, itype: InvestigationType, findings: Sequence[Mapping],
                     ctx_by_domain: dict) -> InvestigationCandidate:
    finding_ids = tuple(finding_id(f) for f in findings)
    finding_types = tuple(sorted({_lc(f.get("finding_type")) for f in findings}))
    max_sev = max((_lc(f.get("severity")) for f in findings),
                  key=lambda s: _SEVERITY_RANK.get(s, 0)) if findings else "informational"

    cov = (ctx_by_domain.get("coverage") or {}).get(domain, [{}])
    cov0 = cov[0] if cov else {}
    ev = (cov0.get("evidence_totals") or {}) if isinstance(cov0, Mapping) else {}
    independent = int(ev.get("independent") or 0)
    dependent = int(ev.get("dependent") or 0)
    record_count = int(ev.get("record_count") or 0)
    reval = (ctx_by_domain.get("revalidation") or {}).get(domain, [{}])
    contra = (ctx_by_domain.get("contradiction") or {}).get(domain, [{}])

    evidence_requested, why_needed, discriminating = _evidence_request(itype, domain, cov0)
    current_state = (f"{independent} independent line(s), {dependent} dependent, "
                     f"{record_count} record(s) on this domain")

    n_linked = len(finding_ids)
    n_blocking = sum(1 for f in findings if _lc(f.get("severity")) == "blocking")

    # ---- transparent value dimensions ----
    tval = itype.value
    info_gain = _TYPE_INFO_GAIN.get(tval, 0.5)
    blocker = 1.0 if n_blocking > 0 else (0.6 if max_sev == "major" else
                                          0.3 if max_sev == "moderate" else
                                          0.1 if max_sev == "minor" else 0.0)
    leverage = _clamp((n_linked - 1) * 0.34)
    discrimination = 1.0 if itype == InvestigationType.CONTRADICTION_DISCRIMINATION else 0.0
    # independence gain: high when the domain is dependent-heavy and the investigation adds independence.
    dependent_heavy = independent < 2 and (dependent > 0 or record_count > 0)
    indep_gain = (0.9 if itype in (InvestigationType.INDEPENDENCE_IMPROVEMENT,
                                   InvestigationType.CONTRADICTION_DISCRIMINATION,
                                   InvestigationType.CONVERGENCE_CONFIRMATION) and dependent_heavy
                  else 0.4 if itype in (InvestigationType.INDEPENDENCE_IMPROVEMENT,
                                        InvestigationType.CONVERGENCE_CONFIRMATION) else 0.0)
    assumption_red = 1.0 if itype == InvestigationType.ASSUMPTION_ESTABLISHMENT else 0.0
    freshness = 1.0 if itype in (InvestigationType.REVALIDATION,
                                 InvestigationType.VERSION_SENSITIVE_CONFIRMATION) else 0.0
    context_rel = 1.0 if itype == InvestigationType.CONTEXT_EXPANSION else (
        0.5 if itype == InvestigationType.CONVERGENCE_CONFIRMATION else 0.0)

    # feasibility: lower when a domain has no evidence yet (except coverage bootstrap) — prereq
    # gating is applied later at ranking, but availability already reflects a bootstrap gap.
    availability = 1.0
    if record_count == 0 and itype not in (InvestigationType.MISSING_DOMAIN_COVERAGE,
                                           InvestigationType.PROVENANCE_IMPROVEMENT):
        availability = 0.4   # cannot strengthen a domain that has no recorded evidence yet
    availability = _clamp(availability)

    # ---- penalties ----
    # duplication: requesting repeated confirmation where independence is already adequate.
    duplication = 0.6 if (itype == InvestigationType.REPEATED_CONFIRMATION and independent >= 2) \
        else 0.0
    effort = _TYPE_EFFORT.get(tval, 0.5)
    # dependency penalty is set later once prerequisites are known; start at 0.
    dependency = 0.0

    dims = _dimensions(info_gain, blocker, leverage, discrimination, indep_gain, assumption_red,
                       freshness, context_rel, availability, duplication, dependency, effort,
                       itype, dependent_heavy)
    score = round(sum(d["contribution"] for d in dims), 6)

    band = _SEVERITY_BAND.get(max_sev, InvestigationPriorityBand.DEFER)
    if availability < FEASIBILITY_THRESHOLD:
        band = InvestigationPriorityBand.DEFER

    expected = _expected_impact(itype, n_blocking, n_linked)
    limits = ("Expected/potential only - it does not guarantee an assurance-grade increase; an "
              "assumption stays an assumption until independently established; missing evidence is "
              "untested, not disproven.")
    defer_conditions = ("Defer while a listed prerequisite is unmet, while the evidence cannot be "
                        "collected independently, or if it would only add correlated repetition.")
    rationale = (f"{itype.value.replace('_', ' ')} for {domain or 'programme'} addressing "
                 f"{n_linked} finding(s) (max severity {max_sev}); priority score {score}.")

    return InvestigationCandidate(
        candidate_id=_candidate_id(domain, tval, finding_ids), domains=(domain,) if domain else (),
        investigation_type=tval, linked_finding_ids=finding_ids, finding_types=finding_types,
        max_severity=max_sev, evidence_requested=evidence_requested, why_needed=why_needed,
        current_evidence_state=current_state, discriminating_requirement=discriminating,
        expected_assurance_impact=expected, impact_limitations=limits, dimensions=tuple(dims),
        priority_score=score, priority_band=band.value, dependencies=(),
        defer_conditions=defer_conditions, rationale=rationale, advisory_statement=_ADVISORY)


def _dimensions(info_gain, blocker, leverage, discrimination, indep_gain, assumption_red, freshness,
                context_rel, availability, duplication, dependency, effort, itype, dependent_heavy
                ) -> List[dict]:
    def v(name, raw, why):
        w = VALUE_DIMENSION_WEIGHTS[name]
        return {"name": name, "raw": _clamp(raw), "weight": w,
                "contribution": round(_clamp(raw) * w, 6), "rationale": why}

    def p(name, raw, why):
        w = PENALTY_DIMENSION_WEIGHTS[name]
        return {"name": name, "raw": _clamp(raw), "weight": w,
                "contribution": round(-_clamp(raw) * w, 6), "rationale": why}

    return [
        v("information_gain", info_gain, f"{itype.value} carries this base information gain"),
        v("blocker_clearance", blocker, "share of linked assurance blockers this would address"),
        v("cross_finding_leverage", leverage, "how many distinct findings one investigation clears"),
        v("contradiction_discrimination", discrimination,
          "whether the evidence can distinguish competing explanations"),
        v("independence_gain", indep_gain,
          "adds genuine independence" if dependent_heavy else "limited independence gain"),
        v("assumption_reduction", assumption_red, "would establish or reject a relied-upon assumption"),
        v("freshness_value", freshness, "restores currency / version validity"),
        v("context_relevance", context_rel, "broadens the context in which the knowledge holds"),
        v("evidence_availability", availability, "whether the evidence is currently collectable"),
        p("duplication_penalty", duplication, "requests evidence largely redundant with existing"),
        p("dependency_penalty", dependency, "an unresolved prerequisite blocks this investigation"),
        p("collection_cost", effort, "relative effort to collect the evidence"),
    ]


def _expected_impact(itype: InvestigationType, n_blocking: int, n_linked: int) -> str:
    parts = []
    if n_blocking:
        parts.append(f"may clear up to {n_blocking} assurance blocker(s)")
    if itype == InvestigationType.CONTRADICTION_DISCRIMINATION:
        parts.append("may resolve an open contradiction")
    if itype == InvestigationType.INDEPENDENCE_IMPROVEMENT:
        parts.append("may replace dependent evidence with an independent line")
    if itype == InvestigationType.ASSUMPTION_ESTABLISHMENT:
        parts.append("may establish or reject an assumption that currently caps readiness")
    if itype in (InvestigationType.REVALIDATION, InvestigationType.VERSION_SENSITIVE_CONFIRMATION):
        parts.append("may restore currency / version validity")
    if itype in (InvestigationType.CONTEXT_EXPANSION, InvestigationType.CONVERGENCE_CONFIRMATION):
        parts.append("may move the domain toward multi-context convergence")
    if not parts:
        parts.append("may strengthen the evidence for this domain")
    return "; ".join(parts) + " (potential, not guaranteed)."


# ---------------------------------------------------------------------------------------------
# Dependencies + ranking
# ---------------------------------------------------------------------------------------------

def _apply_dependencies(candidates: List[InvestigationCandidate]
                        ) -> List[InvestigationCandidate]:
    by_domain_type = {(c.domains[0] if c.domains else "", c.investigation_type): c
                      for c in candidates}
    out: List[InvestigationCandidate] = []
    for c in candidates:
        dom = c.domains[0] if c.domains else ""
        deps: List[dict] = []
        for pre_type, dep_type in sorted(_PREREQUISITE_PAIRS):
            if c.investigation_type != dep_type:
                continue
            pre = by_domain_type.get((dom, pre_type))
            if pre is not None:
                deps.append(InvestigationDependency(
                    prerequisite_candidate_id=pre.candidate_id, prerequisite_type=pre_type,
                    reason=(f"{pre_type.replace('_', ' ')} must be collected for {dom or 'programme'} "
                            f"before {dep_type.replace('_', ' ')} is useful")).to_dict())
        if not deps:
            out.append(c)
            continue
        # re-score with dependency penalty and downgrade band to DEFER (a dependent candidate must
        # not outrank its unresolved prerequisite).
        dims = [dict(d) for d in c.dimensions]
        for d in dims:
            if d["name"] == "dependency_penalty":
                d["raw"] = 0.8
                d["contribution"] = round(-0.8 * PENALTY_DIMENSION_WEIGHTS["dependency_penalty"], 6)
                d["rationale"] = "an unresolved prerequisite blocks this investigation"
        score = round(sum(d["contribution"] for d in dims), 6)
        out.append(InvestigationCandidate(
            candidate_id=c.candidate_id, domains=c.domains, investigation_type=c.investigation_type,
            linked_finding_ids=c.linked_finding_ids, finding_types=c.finding_types,
            max_severity=c.max_severity, evidence_requested=c.evidence_requested,
            why_needed=c.why_needed, current_evidence_state=c.current_evidence_state,
            discriminating_requirement=c.discriminating_requirement,
            expected_assurance_impact=c.expected_assurance_impact,
            impact_limitations=c.impact_limitations, dimensions=tuple(dims), priority_score=score,
            priority_band=InvestigationPriorityBand.DEFER.value, dependencies=tuple(deps),
            defer_conditions=c.defer_conditions, rationale=c.rationale,
            advisory_statement=c.advisory_statement))
    return out


def _contribution(c: InvestigationCandidate, name: str) -> float:
    d = c.dimension(name)
    return float(d["contribution"]) if d else 0.0


def _rank_key(c: InvestigationCandidate):
    dom = c.domains[0] if c.domains else ""
    return (_BAND_ORDER.get(c.priority_band, 9),
            -c.priority_score,
            -_contribution(c, "blocker_clearance"),
            -_contribution(c, "cross_finding_leverage"),
            -_contribution(c, "information_gain"),
            _contribution(c, "collection_cost"),   # less-negative (cheaper) first
            _DOMAIN_ORDER.index(dom) if dom in _DOMAIN_ORDER else 99,
            _TYPE_ORDER.index(c.investigation_type) if c.investigation_type in _TYPE_ORDER else 99,
            c.candidate_id)


def build_investigation_candidates(assurance: Mapping, revalidation: Mapping, coverage: Mapping,
                                   contradiction: Mapping, assumptions: Mapping
                                   ) -> Tuple[InvestigationCandidate, ...]:
    """Generate, dedup, add dependencies to and rank the investigation candidates. Deterministic;
    never raises."""
    try:
        return _generate(assurance or {}, revalidation or {}, coverage or {}, contradiction or {},
                         assumptions or {})
    except Exception:
        return ()


def _generate(assurance: Mapping, revalidation: Mapping, coverage: Mapping, contradiction: Mapping,
              assumptions: Mapping) -> Tuple[InvestigationCandidate, ...]:
    ctx_by_domain = {"coverage": _index_by_domain(coverage, "domain_coverage"),
                     "revalidation": _index_by_domain(revalidation, "items"),
                     "contradiction": _index_by_domain(contradiction, "contradictions")}

    # group findings by (domain, investigation_type) -> merge (dedup + cross-finding leverage).
    groups: dict = {}
    for f in (assurance.get("findings") or []):
        if not isinstance(f, Mapping):
            continue
        itype = _FINDING_TO_TYPE.get(_lc(f.get("finding_type")))
        if itype is None:
            continue   # no_known_knowledge / clean / unmapped -> no investigation
        key = (_lc(f.get("domain")), itype.value)
        groups.setdefault(key, []).append(f)

    candidates = [_build_candidate(dom, InvestigationType(itype), fs, ctx_by_domain)
                  for (dom, itype), fs in groups.items()]
    candidates = _apply_dependencies(candidates)
    candidates.sort(key=_rank_key)
    return tuple(candidates)


# ---------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class AssuranceEngineeringPriorityReport:
    schema_version: int
    source_programme: dict
    generated_from: dict
    assurance_grade: str
    assurance_summary: str
    total_findings: int
    blocking_finding_count: int
    major_finding_count: int
    candidate_count: int
    prioritised_candidates: Tuple[dict, ...]
    deferred_candidates: Tuple[dict, ...]
    unresolved_prerequisites: Tuple[dict, ...]
    ordering: dict
    no_action_statement: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = ASSURANCE_ENGINEERING_PRIORITY_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from), "assurance_grade": self.assurance_grade,
                "assurance_summary": self.assurance_summary, "total_findings": self.total_findings,
                "blocking_finding_count": self.blocking_finding_count,
                "major_finding_count": self.major_finding_count,
                "candidate_count": self.candidate_count,
                "prioritised_candidates": [dict(c) for c in self.prioritised_candidates],
                "deferred_candidates": [dict(c) for c in self.deferred_candidates],
                "unresolved_prerequisites": [dict(p) for p in self.unresolved_prerequisites],
                "ordering": dict(self.ordering), "no_action_statement": self.no_action_statement,
                "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


_ORDERING = {"tie_break": ["priority_band", "priority_score_desc", "blocker_clearance_desc",
                           "cross_finding_leverage_desc", "information_gain_desc",
                           "collection_cost_asc", "canonical_domain_order", "investigation_type_order",
                           "stable_candidate_id"],
             "note": "deterministic; no timestamp affects ordering or the fingerprint"}

_SAFETY = ("Read-only, advisory-only evidence-priority planning. It ranks the evidence the programme "
           "should collect next to improve assurance - it creates no experiment, campaign or "
           "schedule, allocates no dates/sessions/drivers/cars/tracks/resources, carries no setup "
           "values, exposes no Apply control, and never guarantees an assurance-grade increase. "
           "Completion stays governed by Phase 18 and the frozen Apply gate remains the sole route "
           "to the car.")


def build_assurance_engineering_priority(assurance: Optional[Mapping],
                                         revalidation: Optional[Mapping],
                                         coverage: Optional[Mapping],
                                         contradiction: Optional[Mapping],
                                         assumptions: Optional[Mapping],
                                         source_programme: Optional[Mapping] = None
                                         ) -> AssuranceEngineeringPriorityReport:
    """Pure builder: accepts already-built Phase-26..31 products in memory and returns the priority
    report. Never queries the DB, mutates inputs, writes files, uses the clock or randomness.
    Deterministic; never raises."""
    try:
        return _build_report(assurance or {}, revalidation or {}, coverage or {},
                             contradiction or {}, assumptions or {}, source_programme or {})
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return AssuranceEngineeringPriorityReport(
            schema_version=ASSURANCE_ENGINEERING_PRIORITY_SCHEMA, source_programme={},
            generated_from={}, assurance_grade="insufficient_evidence", assurance_summary="",
            total_findings=0, blocking_finding_count=0, major_finding_count=0, candidate_count=0,
            prioritised_candidates=(), deferred_candidates=(), unresolved_prerequisites=(),
            ordering=dict(_ORDERING),
            no_action_statement="Priority report unavailable.", safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}), knowledge_versions=kv)


def _build_report(assurance: Mapping, revalidation: Mapping, coverage: Mapping,
                  contradiction: Mapping, assumptions: Mapping,
                  source_hint: Mapping) -> AssuranceEngineeringPriorityReport:
    source = dict((assurance.get("source_programme") or source_hint) or {})
    grade = _lc(assurance.get("assurance_grade")) or "insufficient_evidence"
    totals = assurance.get("totals") or {}
    findings = [f for f in (assurance.get("findings") or []) if isinstance(f, Mapping)]
    n_blocking = int(totals.get("blocking") or sum(1 for f in findings
                                                   if _lc(f.get("severity")) == "blocking"))
    n_major = int(totals.get("major") or sum(1 for f in findings
                                             if _lc(f.get("severity")) == "major"))

    candidates = list(build_investigation_candidates(assurance, revalidation, coverage,
                                                     contradiction, assumptions))
    prioritised = tuple(c.to_dict() for c in candidates
                        if c.priority_band in _ACTIONABLE_BANDS)
    deferred = tuple(c.to_dict() for c in candidates
                     if c.priority_band not in _ACTIONABLE_BANDS)

    # unresolved prerequisite summary (deterministic).
    prereqs = []
    seen = set()
    for c in candidates:
        for dep in c.dependencies:
            k = (dep["prerequisite_candidate_id"], c.candidate_id)
            if k in seen:
                continue
            seen.add(k)
            prereqs.append({"dependent_candidate_id": c.candidate_id,
                            "prerequisite_candidate_id": dep["prerequisite_candidate_id"],
                            "prerequisite_type": dep["prerequisite_type"], "reason": dep["reason"]})

    no_action = ""
    if not candidates:
        if grade in ("assured",) or _lc(assurance.get("grade_detail", {}).get("rule")) in (
                "no_findings_above_informational",):
            no_action = ("The programme is assured - no assurance-improving evidence investigation is "
                         "needed at this time. Existing knowledge should be protected, not disturbed.")
        elif not findings:
            no_action = ("No assurance findings to act on yet - there is not enough established "
                         "knowledge to prioritise evidence.")
        else:
            no_action = ("No actionable evidence investigation was derived from the current findings.")

    kv = knowledge_versions()
    fp = _fp({"src": {k: _lc(source.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
              "grade": grade, "n_blocking": n_blocking, "n_major": n_major,
              "cands": [(c["candidate_id"], c["investigation_type"], c["priority_band"],
                         c["priority_score"], list(c["linked_finding_ids"]),
                         [(d["name"], d["raw"], d["weight"], d["contribution"]) for d in c["dimensions"]],
                         [dep["prerequisite_candidate_id"] for dep in c["dependencies"]])
                        for c in (prioritised + deferred)],
              "kv": kv})

    summary = (f"Assurance grade {grade.replace('_', ' ').upper()}: {len(findings)} finding(s) "
               f"({n_blocking} blocking, {n_major} major); {len(prioritised)} prioritised "
               f"investigation(s), {len(deferred)} deferred. Advisory only - this is evidence to "
               "collect, not an experiment, setup or Apply.")

    return AssuranceEngineeringPriorityReport(
        schema_version=ASSURANCE_ENGINEERING_PRIORITY_SCHEMA,
        source_programme={k: str(source.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase31_fingerprint": _lc(assurance.get("content_fingerprint")),
                        "phase26_fingerprint": _lc(revalidation.get("content_fingerprint")),
                        "phase27_fingerprint": _lc(coverage.get("content_fingerprint")),
                        "phase29_fingerprint": _lc(contradiction.get("content_fingerprint")),
                        "phase30_fingerprint": _lc(assumptions.get("content_fingerprint")),
                        "authorities": ["Phase 17 information-gain doctrine (reused, not imported)",
                                        "Phase 31 assurance findings", "Phase 26-30 subordinate "
                                        "products"]},
        assurance_grade=grade, assurance_summary=summary, total_findings=len(findings),
        blocking_finding_count=n_blocking, major_finding_count=n_major,
        candidate_count=len(candidates), prioritised_candidates=prioritised,
        deferred_candidates=deferred, unresolved_prerequisites=tuple(prereqs), ordering=dict(_ORDERING),
        no_action_statement=no_action, safety_statement=_SAFETY, content_fingerprint=fp,
        knowledge_versions=kv)


def knowledge_versions() -> dict:
    return {"assurance_engineering_priority": ASSURANCE_ENGINEERING_PRIORITY_VERSION,
            "schema": ASSURANCE_ENGINEERING_PRIORITY_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{ASSURANCE_ENGINEERING_PRIORITY_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
