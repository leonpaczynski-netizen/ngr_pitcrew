"""Programme Evidence Coverage Report — pure orchestration (Program 2, Phase 27).

Assembles the read-only evidence-coverage & blind-spot view from the Phase-25 knowledge timeline
(convergence authority), the Phase-26 re-validation report (freshness), and the bounded evidence
records (context breadth). It reuses the CANONICAL Phase-25 record→domain mapping verbatim (it
invents no new mapping and no new domains), assesses each grounded domain's coverage across the
visible dimensions, and ranks the resulting blind spots by severity.

It reports coverage only: it recommends no setup, schedules no test, creates no experiment/campaign,
and never treats the absence of evidence as a negative result.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.engineering_knowledge_graph import KnowledgeDomain
from strategy.programme_timeline_report import _record_domains   # canonical mapping (reused verbatim)
from strategy.coverage_dimension import (
    COVERAGE_DIMENSION_VERSION, BLIND_SPOT_SEVERITY_PRIORITY, BlindSpotSeverity,
)
from strategy.evidence_coverage import (
    EVIDENCE_COVERAGE_VERSION, assess_domain_coverage,
)
from strategy.knowledge_blind_spot import (
    KNOWLEDGE_BLIND_SPOT_VERSION, classify_blind_spot,
)

PROGRAMME_COVERAGE_REPORT_VERSION = "programme_coverage_report_v1"
PROGRAMME_COVERAGE_REPORT_SCHEMA = 1

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]
_MATURITY_RANK = {"unknown": 0, "emerging": 1, "developing": 2, "established": 3, "mature": 4,
                  "complete": 5, "plateaued": 3}

# Severities that are surfaced as actionable blind spots (INFORMATIONAL/UNKNOWN are listed separately).
_RAISED_SEVERITIES = (BlindSpotSeverity.CRITICAL.value, BlindSpotSeverity.MATERIAL.value,
                      BlindSpotSeverity.MODERATE.value)

_SAFETY = ("Read-only evidence coverage & blind-spot map. It reports where knowledge is well "
           "supported and where more evidence would help - a blind spot is NOT a fault or a "
           "negative result, and missing coverage means untested, never wrong. It reuses the "
           "Phase-23 transfer, Phase-25 convergence and Phase-26 re-validation authorities, invents "
           "no domains, carries no setup values, and recommends / schedules / applies / mutates "
           "NOTHING. Completion stays governed by Phase 18 and the frozen Apply gate remains the "
           "sole route to the car.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ProgrammeCoverageReport:
    schema_version: int
    source_programme: dict
    generated_from: dict
    domain_coverage: Tuple[dict, ...]
    blind_spots: Tuple[dict, ...]              # raised (critical/material/moderate), ranked
    early_stage_gaps: Tuple[dict, ...]         # informational (expected; not a concern)
    unassessable: Tuple[dict, ...]             # unknown reliance
    well_covered_domains: Tuple[str, ...]
    totals: dict
    empty_state: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = PROGRAMME_COVERAGE_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from),
                "domain_coverage": [dict(d) for d in self.domain_coverage],
                "blind_spots": [dict(b) for b in self.blind_spots],
                "early_stage_gaps": [dict(b) for b in self.early_stage_gaps],
                "unassessable": [dict(b) for b in self.unassessable],
                "well_covered_domains": list(self.well_covered_domains),
                "totals": dict(self.totals), "empty_state": self.empty_state,
                "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_programme_evidence_coverage_report(
        timeline: Optional[Mapping], programme_knowledge: Optional[Mapping],
        revalidation: Optional[Mapping], evidence_records: Optional[Sequence[Mapping]]
) -> ProgrammeCoverageReport:
    """Assemble the evidence coverage & blind-spot report. Deterministic; never raises."""
    try:
        return _build(timeline or {}, programme_knowledge or {}, revalidation or {},
                      [r for r in (evidence_records or []) if isinstance(r, Mapping)])
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeCoverageReport(
            schema_version=PROGRAMME_COVERAGE_REPORT_SCHEMA, source_programme={}, generated_from={},
            domain_coverage=(), blind_spots=(), early_stage_gaps=(), unassessable=(),
            well_covered_domains=(), totals={}, empty_state="Coverage report unavailable.",
            safety_statement=_SAFETY, content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(timeline: Mapping, programme: Mapping, revalidation: Mapping,
           records: List[Mapping]) -> ProgrammeCoverageReport:
    source = dict(timeline.get("source_programme") or {})

    # bucket records per domain via the CANONICAL Phase-25 mapping (reused, not re-implemented).
    records_by_domain: dict = {}
    for r in records:
        for dom in _record_domains(r):
            records_by_domain.setdefault(dom, []).append(r)

    reval_by_domain: dict = {}
    for it in (revalidation.get("items") or []):
        if isinstance(it, Mapping):
            reval_by_domain[_lc(it.get("domain"))] = it

    coverages: List[dict] = []
    blind: List[dict] = []
    for c in (timeline.get("convergence_summaries") or []):
        if not isinstance(c, Mapping):
            continue
        domain = _lc(c.get("domain"))
        cov = assess_domain_coverage(domain, records_by_domain.get(domain, []), c,
                                     reval_by_domain.get(domain, {})).to_dict()
        coverages.append(cov)
        blind.append(classify_blind_spot(cov).to_dict())

    coverages.sort(key=lambda cov: _domain_sort(cov))
    # only domains with an actual gap become a blind-spot entry.
    raised, early, unassess = [], [], []
    for b in blind:
        if not (b.get("gap_dimensions") or []):
            continue
        sev = _lc(b.get("severity"))
        if sev in _RAISED_SEVERITIES:
            raised.append(b)
        elif sev == BlindSpotSeverity.UNKNOWN.value:
            unassess.append(b)
        else:
            early.append(b)
    raised.sort(key=_blind_sort)
    early.sort(key=_blind_sort)
    unassess.sort(key=_blind_sort)

    well_covered = tuple(sorted(
        (cov["domain"] for cov in coverages if cov.get("gap_count", 0) == 0 and cov.get("dimensions")),
        key=lambda d: (_DOMAIN_ORDER.index(d) if d in _DOMAIN_ORDER else 99, d)))

    totals = {
        "domains_assessed": len(coverages),
        "blind_spots_raised": len(raised),
        "critical": sum(1 for b in raised if _lc(b["severity"]) == "critical"),
        "material": sum(1 for b in raised if _lc(b["severity"]) == "material"),
        "moderate": sum(1 for b in raised if _lc(b["severity"]) == "moderate"),
        "early_stage_gaps": len(early),
        "unassessable": len(unassess),
        "well_covered": len(well_covered),
        "total_gap_dimensions": sum(int(cov.get("gap_count", 0)) for cov in coverages),
    }

    kv = knowledge_versions()
    fp = _fp({
        "src": {k: _lc(source.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
        "cov": [(cov["domain"], cov["covered_count"], cov["gap_count"],
                 [(d["dimension"], d["status"]) for d in cov["dimensions"]]) for cov in coverages],
        "blind": [(b["domain"], b["severity"], b["reliance"], b["evidence_robustness"])
                  for b in raised + early + unassess],
        "kv": kv,
    })
    empty = "" if coverages else ("No evidence coverage to map yet - it appears once the programme "
                                  "has recorded evidence for known engineering domains.")
    return ProgrammeCoverageReport(
        schema_version=PROGRAMME_COVERAGE_REPORT_SCHEMA,
        source_programme={k: str(source.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase25_fingerprint": _lc(timeline.get("content_fingerprint")),
                        "phase26_fingerprint": _lc(revalidation.get("content_fingerprint")),
                        "authorities": ["Phase 22 knowledge graph", "Phase 25 convergence/timeline",
                                        "Phase 26 re-validation", "immutable development records"]},
        domain_coverage=tuple(coverages), blind_spots=tuple(raised), early_stage_gaps=tuple(early),
        unassessable=tuple(unassess), well_covered_domains=well_covered, totals=totals,
        empty_state=empty, safety_statement=_SAFETY, content_fingerprint=fp, knowledge_versions=kv)


def _domain_sort(cov: Mapping):
    return (-int(cov.get("gap_count", 0)),
            -_MATURITY_RANK.get(_lc(cov.get("current_maturity")), 0),
            _DOMAIN_ORDER.index(_lc(cov.get("domain"))) if _lc(cov.get("domain")) in _DOMAIN_ORDER
            else 99, _lc(cov.get("domain")))


def _blind_sort(b: Mapping):
    return (BLIND_SPOT_SEVERITY_PRIORITY.get(_lc(b.get("severity")), 99),
            _DOMAIN_ORDER.index(_lc(b.get("domain"))) if _lc(b.get("domain")) in _DOMAIN_ORDER
            else 99, _lc(b.get("domain")))


def knowledge_versions() -> dict:
    return {"programme_coverage_report": PROGRAMME_COVERAGE_REPORT_VERSION,
            "evidence_coverage": EVIDENCE_COVERAGE_VERSION,
            "knowledge_blind_spot": KNOWLEDGE_BLIND_SPOT_VERSION,
            "coverage_dimension": COVERAGE_DIMENSION_VERSION,
            "schema": PROGRAMME_COVERAGE_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_COVERAGE_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
