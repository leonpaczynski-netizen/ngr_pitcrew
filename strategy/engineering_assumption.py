"""Engineering Assumption — derive a domain's relied-upon assumptions from the authorities (Phase 30).

For ONE knowledge domain it reads the Phase-25 convergence, Phase-26 re-validation, Phase-27 coverage
and Phase-29 contradiction signals and surfaces the ASSUMPTIONS the current knowledge depends on -
things relied upon that are not themselves directly established by evidence. A directly-evidenced
conclusion (independent, confirmed, current, in-context, uncontradicted) is a FACT and produces NO
assumption. An assumption can only limit reliance (cap / narrow / weaken / block), never create it.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Tuple

from strategy.assumption_classification import (
    ASSUMPTION_CLASSIFICATION_VERSION, AssumptionType, AssumptionStatus, type_text,
)
from strategy.assumption_impact import (
    ASSUMPTION_IMPACT_VERSION, AssumptionImpact, impact_text, readiness_cap,
)

ENGINEERING_ASSUMPTION_VERSION = "engineering_assumption_v1"

_NO_ACTION = ("Assumption register only - it makes explicit what the current knowledge relies on but "
              "has not established. An assumption never creates readiness (it can only cap it), and "
              "it triggers no test, experiment or setup change.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class EngineeringAssumption:
    domain: str
    assumption_type: str
    status: str
    impact: str
    readiness_cap: str
    is_conservative_bound: bool
    rationale: str
    what_would_resolve: str
    no_action_statement: str
    eval_version: str = ENGINEERING_ASSUMPTION_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "assumption_type": self.assumption_type,
                "status": self.status, "impact": self.impact, "readiness_cap": self.readiness_cap,
                "is_conservative_bound": self.is_conservative_bound, "rationale": self.rationale,
                "what_would_resolve": self.what_would_resolve,
                "no_action_statement": self.no_action_statement, "eval_version": self.eval_version}


def _dim_status(coverage: Mapping, dimension: str) -> str:
    for d in (coverage.get("dimensions") or []):
        if isinstance(d, Mapping) and _lc(d.get("dimension")) == dimension:
            return _lc(d.get("status"))
    return ""


def _mk(domain, atype, status, impact, rationale, resolve, conservative=False):
    return EngineeringAssumption(
        domain=domain, assumption_type=atype.value, status=status.value, impact=impact.value,
        readiness_cap=readiness_cap(impact.value), is_conservative_bound=conservative,
        rationale=f"{type_text(atype.value)}; {impact_text(impact.value)}. {rationale}".strip(),
        what_would_resolve=resolve, no_action_statement=_NO_ACTION)


def is_factual(convergence: Mapping, coverage: Mapping, revalidation_item: Mapping,
               contradiction_item: Mapping) -> bool:
    """A domain is factual (no assumptions) when the evidence directly supports it: strong
    convergence, current, no coverage gaps, and no open contradiction. Never raises."""
    conv = _lc(convergence.get("convergence_status"))
    fresh = _lc(revalidation_item.get("freshness_status"))
    gaps = int((coverage or {}).get("gap_count") or 0)
    open_contra = bool((contradiction_item or {}).get("is_open"))
    return (conv in ("strongly_converged", "stable_confirmed_good") and fresh in ("current", "")
            and gaps == 0 and not open_contra)


def derive_domain_assumptions(domain: str, convergence: Mapping, revalidation_item: Mapping,
                              coverage_item: Mapping, contradiction_item: Mapping
                              ) -> Tuple[dict, ...]:
    """Surface the assumptions ONE domain's knowledge relies on. Empty when the domain is factual.
    Deterministic; never raises."""
    try:
        return _derive(_lc(domain), convergence or {}, revalidation_item or {}, coverage_item or {},
                       contradiction_item or {})
    except Exception:
        return ()


def _derive(domain: str, conv: Mapping, reval: Mapping, cov: Mapping,
            contra: Mapping) -> Tuple[dict, ...]:
    if is_factual(conv, cov, reval, contra):
        return ()

    out: List[EngineeringAssumption] = []
    fresh = _lc(reval.get("freshness_status"))
    conv_status = _lc(conv.get("convergence_status"))
    confirmed_good = bool(conv.get("confirmed_good"))
    transfer_limits = [_lc(t) for t in (conv.get("transfer_limitations") or [])]
    version_sensitive = any("version" in t for t in transfer_limits)

    indep = _dim_status(cov, "independent_replication")
    track = _dim_status(cov, "track_variety")
    transfer = _dim_status(cov, "transfer_validation")

    # generalisation from a single context.
    if track == "single_context_only" or transfer == "single_context_only" \
            or conv_status == "stable_but_context_bound":
        out.append(_mk(domain, AssumptionType.GENERALISATION_FROM_SINGLE_CONTEXT,
                       AssumptionStatus.UNVERIFIED, AssumptionImpact.NARROWS_SCOPE,
                       "observed in a single context.",
                       "an independent observation in another context"))

    # dependent evidence relied on as if independent.
    if indep == "dependent_evidence_only":
        out.append(_mk(domain, AssumptionType.INDEPENDENCE_ASSUMED, AssumptionStatus.UNVERIFIED,
                       AssumptionImpact.CAPS_READINESS,
                       "the supporting evidence is dependent, not independent.",
                       "a genuinely independent confirmation"))

    # currency: relied on without re-validation.
    if fresh in ("revalidation_advised",):
        out.append(_mk(domain, AssumptionType.CURRENCY_ASSUMED,
                       AssumptionStatus.EVIDENCE_BACKED_PARTIALLY, AssumptionImpact.WEAKENS_CONFIDENCE,
                       "re-validation is advised.", "a current-context re-observation"))
    elif fresh in ("revalidation_required", "invalidated_by_version_change"):
        out.append(_mk(domain, AssumptionType.CURRENCY_ASSUMED, AssumptionStatus.AT_RISK,
                       AssumptionImpact.CAPS_READINESS,
                       "context or version changed and re-validation is required.",
                       "a current-context / current-version confirmation"))

    # confirmed-good assumed to persist without a current re-observation.
    if confirmed_good and fresh not in ("current", ""):
        out.append(_mk(domain, AssumptionType.CONFIRMED_GOOD_PERSISTS_ASSUMED,
                       AssumptionStatus.UNVERIFIED, AssumptionImpact.CAPS_READINESS,
                       "confirmed-good has not been re-observed in the current context.",
                       "an independent re-observation of the confirmed-good behaviour"))

    # version stability assumed for version-sensitive knowledge not re-validated at the version.
    if version_sensitive and fresh not in ("current", "invalidated_by_version_change"):
        out.append(_mk(domain, AssumptionType.VERSION_STABILITY_ASSUMED, AssumptionStatus.UNVERIFIED,
                       AssumptionImpact.WEAKENS_CONFIDENCE,
                       "the knowledge is version-sensitive and has not been re-confirmed at the "
                       "current version.", "a confirmation at the current GT7 version"))

    # an open contradiction whose standing side is being assumed.
    if bool(contra.get("is_open")) and _lc(contra.get("standing_conclusion")) \
            and "no single conclusion" not in _lc(contra.get("standing_conclusion")):
        out.append(_mk(domain, AssumptionType.CONTRADICTION_SIDE_ASSUMED,
                       AssumptionStatus.CONTRADICTED, AssumptionImpact.BLOCKS_RELIANCE,
                       "one side of an unresolved contradiction is being taken as correct.",
                       "a discriminating observation to resolve the contradiction"))

    # deterministic order: by impact severity then type.
    from strategy.assumption_impact import ASSUMPTION_IMPACT_PRIORITY
    out.sort(key=lambda a: (ASSUMPTION_IMPACT_PRIORITY.get(a.impact, 99), a.assumption_type))
    return tuple(a.to_dict() for a in out)


def engineering_assumption_versions() -> dict:
    return {"engineering_assumption": ENGINEERING_ASSUMPTION_VERSION,
            "assumption_classification": ASSUMPTION_CLASSIFICATION_VERSION,
            "assumption_impact": ASSUMPTION_IMPACT_VERSION}
