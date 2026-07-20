"""Evidence Coverage — per-domain, per-dimension coverage assessment (Program 2, Phase 27).

Given the evidence records that map to ONE knowledge domain (bucketed upstream via the canonical
Phase-25 record→domain mapping), plus that domain's Phase-25 convergence summary and its Phase-26
re-validation item, it reports how well each visible coverage DIMENSION is supported — as a
``CoverageStatus`` per dimension. It reports coverage only: it decides nothing about the car, invents
no evidence, and never treats the absence of evidence as a negative result.

Key rules encoded:
- MISSING (no evidence) is distinct from REGRESSION_ONLY (a negative result was recorded).
- A large DEPENDENT evidence count is never strong coverage (independent lines are what count).
- One distinct track / car / driver / compound / discipline / version is SINGLE_CONTEXT_ONLY.
- Confirmed-good resting on <2 independent lines is a thin-evidence coverage gap, not a fact.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

from strategy.coverage_dimension import (
    COVERAGE_DIMENSION_VERSION, CoverageDimension, CoverageStatus, BREADTH_DIMENSION_FIELD,
    BREADTH_WELL_COVERED, BREADTH_ADEQUATE, MIN_INDEPENDENT_FOR_ROBUST,
    REPEATED_CONFIRMATION_WELL, REPEATED_CONFIRMATION_ADEQUATE, DIMENSION_ORDER,
)

EVIDENCE_COVERAGE_VERSION = "evidence_coverage_v1"

_POSITIVE = ("confirmed_improvement", "partial_improvement")
_HIGH_CONF = ("high", "very_high")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class DomainCoverage:
    domain: str
    dimensions: Tuple[dict, ...]          # per-dimension {dimension, status, detail}
    covered_count: int
    gap_count: int
    context_breadth: dict                 # distinct-value counts per breadth field
    evidence_totals: dict                 # confirmations/regressions/independent/dependent/etc
    convergence_status: str
    freshness_status: str
    confirmed_good: bool
    current_maturity: str
    current_confidence: str
    eval_version: str = EVIDENCE_COVERAGE_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "dimensions": [dict(d) for d in self.dimensions],
                "covered_count": self.covered_count, "gap_count": self.gap_count,
                "context_breadth": dict(self.context_breadth),
                "evidence_totals": dict(self.evidence_totals),
                "convergence_status": self.convergence_status,
                "freshness_status": self.freshness_status, "confirmed_good": self.confirmed_good,
                "current_maturity": self.current_maturity,
                "current_confidence": self.current_confidence, "eval_version": self.eval_version}


def coverage_signals(domain_records: Sequence[Mapping]) -> dict:
    """Extract the visible coverage signals from ONE domain's evidence records. Never raises."""
    recs = [r for r in (domain_records or []) if isinstance(r, Mapping)]
    breadth = {field: set() for field in BREADTH_DIMENSION_FIELD.values()}
    phases, corners = set(), set()
    confirms = regressions = high_conf_positive = 0
    for r in recs:
        ctx = r.get("context") or {}
        for field in breadth:
            val = _lc(ctx.get(field))
            if val:
                breadth[field].add(val)
        for rs in (r.get("residual_states") or []):
            if isinstance(rs, Mapping):
                ph = _lc(rs.get("phase"))
                if ph:
                    phases.add(ph)
                seg = _lc(rs.get("segment_id")) or _lc(rs.get("corner_name")) or _lc(rs.get("family"))
                if seg:
                    corners.add(seg)
        outcome = _lc(r.get("outcome_status"))
        if outcome in _POSITIVE:
            confirms += 1
            if _lc(r.get("confidence_level")) in _HIGH_CONF:
                high_conf_positive += 1
        elif outcome == "regression":
            regressions += 1
    return {"breadth": {k: len(v) for k, v in breadth.items()},
            "phase_count": len(phases), "corner_count": len(corners),
            "record_confirmations": confirms, "record_regressions": regressions,
            "high_confidence_positive": high_conf_positive, "record_count": len(recs)}


def _breadth_status(distinct: int) -> CoverageStatus:
    if distinct >= BREADTH_WELL_COVERED:
        return CoverageStatus.WELL_COVERED
    if distinct >= BREADTH_ADEQUATE:
        return CoverageStatus.ADEQUATELY_COVERED
    if distinct == 1:
        return CoverageStatus.SINGLE_CONTEXT_ONLY
    return CoverageStatus.MISSING


def _count_status(count: int, well: int, adequate: int, has_regression: bool) -> CoverageStatus:
    if count >= well:
        return CoverageStatus.WELL_COVERED
    if count >= adequate:
        return CoverageStatus.ADEQUATELY_COVERED
    if count >= 1:
        return CoverageStatus.PARTIALLY_COVERED
    return CoverageStatus.REGRESSION_ONLY if has_regression else CoverageStatus.MISSING


def assess_domain_coverage(domain: str, domain_records: Sequence[Mapping],
                           convergence: Mapping, revalidation_item: Mapping) -> DomainCoverage:
    """Assess one domain's coverage across every dimension. Deterministic; never raises."""
    try:
        return _assess(_lc(domain), domain_records, convergence or {}, revalidation_item or {})
    except Exception:   # never raise into the caller
        return DomainCoverage(domain=_lc(domain), dimensions=(), covered_count=0, gap_count=0,
                              context_breadth={}, evidence_totals={}, convergence_status="unknown",
                              freshness_status="unknown", confirmed_good=False,
                              current_maturity="unknown", current_confidence="unknown")


def _assess(domain: str, domain_records: Sequence[Mapping], conv: Mapping,
            reval: Mapping) -> DomainCoverage:
    sig = coverage_signals(domain_records)
    breadth = sig["breadth"]
    independent = _int(conv.get("independent_support_count"))
    dependent = _int(conv.get("dependent_support_count"))
    conflict_count = _int(conv.get("conflict_count"))
    regression_count = _int(conv.get("regression_count"))
    conv_status = _lc(conv.get("convergence_status"))
    confirmed_good = bool(conv.get("confirmed_good"))
    compatible_contexts = _int(conv.get("compatible_contexts"))
    maturity = _lc(conv.get("current_maturity"))
    confidence = _lc(conv.get("current_confidence"))
    freshness = _lc(reval.get("freshness_status"))
    confirms = sig["record_confirmations"]
    regressions = sig["record_regressions"]
    has_regression = regressions > 0 or regression_count > 0

    rows: List[dict] = []

    def add(dim: CoverageDimension, status: CoverageStatus, detail: str):
        rows.append({"dimension": dim.value, "status": status.value, "detail": detail})

    # --- context-breadth dimensions ---
    for dim, field in BREADTH_DIMENSION_FIELD.items():
        distinct = breadth.get(field, 0)
        add(dim, _breadth_status(distinct),
            f"{distinct} distinct {field.replace('_', ' ')} value(s) with evidence")
    add(CoverageDimension.CORNER_PHASE_COVERAGE, _breadth_status(sig["phase_count"]),
        f"{sig['phase_count']} distinct corner phase(s) observed")
    add(CoverageDimension.CORNER_TYPE_COVERAGE, _breadth_status(sig["corner_count"]),
        f"{sig['corner_count']} distinct corner(s)/segment(s) observed")

    # --- independent replication ---
    if independent >= MIN_INDEPENDENT_FOR_ROBUST:
        st = CoverageStatus.WELL_COVERED
    elif independent == 1 and dependent == 0:
        st = CoverageStatus.PARTIALLY_COVERED
    elif independent >= 1 or dependent > 0:
        st = CoverageStatus.DEPENDENT_EVIDENCE_ONLY   # <2 independent lines, propped by dependents
    else:
        st = CoverageStatus.REGRESSION_ONLY if has_regression else CoverageStatus.MISSING
    add(CoverageDimension.INDEPENDENT_REPLICATION, st,
        f"{independent} independent line(s), {dependent} dependent")

    # --- repeated confirmation ---
    add(CoverageDimension.REPEATED_CONFIRMATION,
        _count_status(confirms, REPEATED_CONFIRMATION_WELL, REPEATED_CONFIRMATION_ADEQUATE,
                      has_regression),
        f"{confirms} positive confirmation record(s)")

    # --- high-confidence evidence ---
    hc = sig["high_confidence_positive"]
    hc_status = (CoverageStatus.WELL_COVERED if hc >= 2 else
                 CoverageStatus.ADEQUATELY_COVERED if hc == 1 else
                 CoverageStatus.PARTIALLY_COVERED if confirms > 0 else
                 CoverageStatus.REGRESSION_ONLY if has_regression else CoverageStatus.MISSING)
    add(CoverageDimension.HIGH_CONFIDENCE_EVIDENCE, hc_status,
        f"{hc} high-confidence positive record(s)")

    # --- regression check (has the downside/failure boundary been observed?) ---
    if has_regression:
        rc_status, rc_detail = CoverageStatus.WELL_COVERED, "a failure/regression has been observed"
    elif confirms > 0:
        rc_status, rc_detail = (CoverageStatus.PARTIALLY_COVERED,
                                "only positive outcomes seen; the failure boundary is untested")
    else:
        rc_status, rc_detail = CoverageStatus.MISSING, "no outcome evidence"
    add(CoverageDimension.REGRESSION_CHECK, rc_status, rc_detail)

    # --- confirmed-good verification ---
    if not confirmed_good:
        cg_status, cg_detail = CoverageStatus.UNKNOWN, "no confirmed-good behaviour claimed"
    elif independent >= MIN_INDEPENDENT_FOR_ROBUST:
        cg_status, cg_detail = (CoverageStatus.WELL_COVERED,
                                "confirmed-good backed by independent evidence")
    elif independent == 1:
        cg_status, cg_detail = (CoverageStatus.SINGLE_CONTEXT_ONLY,
                                "confirmed-good rests on a single independent line")
    elif dependent > 0:
        cg_status, cg_detail = (CoverageStatus.DEPENDENT_EVIDENCE_ONLY,
                                "confirmed-good rests on dependent evidence only")
    else:
        cg_status, cg_detail = CoverageStatus.MISSING, "confirmed-good lacks direct evidence"
    add(CoverageDimension.CONFIRMED_GOOD_VERIFICATION, cg_status, cg_detail)

    # --- conflict resolution ---
    if conv_status == "conflicting" or (conflict_count > 0 and conv_status in ("mixed", "unknown")):
        cf_status, cf_detail = CoverageStatus.CONFLICTED_COVERAGE, "an unresolved conflict remains"
    elif conflict_count > 0:
        cf_status, cf_detail = (CoverageStatus.ADEQUATELY_COVERED,
                                "a past conflict was resolved by later evidence")
    else:
        cf_status, cf_detail = CoverageStatus.WELL_COVERED, "no conflicting evidence"
    add(CoverageDimension.CONFLICT_RESOLUTION, cf_status, cf_detail)

    # --- convergence achieved (Phase-25 authority) ---
    conv_map = {
        "strongly_converged": (CoverageStatus.WELL_COVERED, "strongly converged"),
        "stable_confirmed_good": (CoverageStatus.WELL_COVERED, "stable confirmed-good"),
        "converging": (CoverageStatus.ADEQUATELY_COVERED, "converging"),
        "stable_but_context_bound": (CoverageStatus.SINGLE_CONTEXT_ONLY, "stable but context-bound"),
        "mixed": (CoverageStatus.PARTIALLY_COVERED, "mixed evidence"),
        "conflicting": (CoverageStatus.CONFLICTED_COVERAGE, "conflicting"),
        "regressed": (CoverageStatus.REGRESSION_ONLY, "regressed"),
        "superseded": (CoverageStatus.PARTIALLY_COVERED, "superseded"),
        "insufficient_evidence": (CoverageStatus.MISSING, "insufficient evidence"),
    }
    cv_status, cv_detail = conv_map.get(conv_status, (CoverageStatus.UNKNOWN, "unknown convergence"))
    add(CoverageDimension.CONVERGENCE_ACHIEVED, cv_status, f"convergence: {cv_detail}")

    # --- transfer validation (validated across contexts vs single-context hypothesis) ---
    tv_status = _breadth_status(compatible_contexts)
    if tv_status == CoverageStatus.WELL_COVERED and compatible_contexts < BREADTH_WELL_COVERED:
        tv_status = CoverageStatus.ADEQUATELY_COVERED
    add(CoverageDimension.TRANSFER_VALIDATION, tv_status,
        f"confirmed in {compatible_contexts} distinct context(s)")

    # --- re-validation currency (Phase-26 authority) ---
    reval_map = {
        "current": (CoverageStatus.WELL_COVERED, "current"),
        "current_but_context_bound": (CoverageStatus.SINGLE_CONTEXT_ONLY, "current but context-bound"),
        "revalidation_advised": (CoverageStatus.ADEQUATELY_COVERED, "re-validation advised"),
        "revalidation_required": (CoverageStatus.PARTIALLY_COVERED, "re-validation required"),
        "invalidated_by_version_change": (CoverageStatus.PARTIALLY_COVERED, "version change"),
        "weakened_by_conflict": (CoverageStatus.CONFLICTED_COVERAGE, "weakened by conflict"),
        "weakened_by_regression": (CoverageStatus.REGRESSION_ONLY, "weakened by regression"),
        "superseded": (CoverageStatus.PARTIALLY_COVERED, "superseded"),
        "retired": (CoverageStatus.PARTIALLY_COVERED, "retired"),
        "insufficient_date_evidence": (CoverageStatus.MISSING, "insufficient date evidence"),
        "insufficient_context_evidence": (CoverageStatus.MISSING, "insufficient context evidence"),
    }
    rv_status, rv_detail = reval_map.get(freshness, (CoverageStatus.UNKNOWN, "unknown"))
    add(CoverageDimension.REVALIDATION_CURRENCY, rv_status, f"freshness: {rv_detail}")

    rows.sort(key=lambda r: DIMENSION_ORDER.index(r["dimension"])
              if r["dimension"] in DIMENSION_ORDER else 99)

    from strategy.coverage_dimension import GAP_STATUSES
    covered = sum(1 for r in rows if r["status"] in ("well_covered", "adequately_covered"))
    gaps = sum(1 for r in rows if r["status"] in GAP_STATUSES)

    return DomainCoverage(
        domain=domain, dimensions=tuple(rows), covered_count=covered, gap_count=gaps,
        context_breadth=dict(breadth),
        evidence_totals={"independent": independent, "dependent": dependent,
                         "record_confirmations": confirms, "record_regressions": regressions,
                         "conflict_count": conflict_count, "regression_count": regression_count,
                         "compatible_contexts": compatible_contexts,
                         "high_confidence_positive": sig["high_confidence_positive"],
                         "record_count": sig["record_count"]},
        convergence_status=conv_status, freshness_status=freshness, confirmed_good=confirmed_good,
        current_maturity=maturity, current_confidence=confidence)


def evidence_coverage_versions() -> dict:
    return {"evidence_coverage": EVIDENCE_COVERAGE_VERSION}
