"""Programme Knowledge Readiness Report — pure orchestration (Program 2, Phase 28).

The executive-summary capstone of Program 2: for each known engineering domain it states whether the
knowledge is READY to rely on, ready only within limits, provisional, or not yet ready (and why), and
grades the whole programme with a transparent, rule-based grade. It joins the Phase-25 convergence,
Phase-26 re-validation and Phase-27 coverage/blind-spot authorities verbatim - it re-derives none of
them, invents no domains, carries no setup values, and never marks unvalidated knowledge ready.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.engineering_knowledge_graph import KnowledgeDomain
from strategy.knowledge_readiness import (
    KNOWLEDGE_READINESS_VERSION, READINESS_PRIORITY, RELYABLE_STATUSES, classify_readiness,
)
from strategy.readiness_grade import (
    READINESS_GRADE_VERSION, grade_programme,
)

PROGRAMME_READINESS_REPORT_VERSION = "programme_readiness_report_v1"
PROGRAMME_READINESS_REPORT_SCHEMA = 1

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]
_MATURITY_RANK = {"unknown": 0, "emerging": 1, "developing": 2, "established": 3, "mature": 4,
                  "complete": 5, "plateaued": 3}

_SAFETY = ("Read-only engineering knowledge readiness report. It states whether the evidence "
           "supports relying on each domain's knowledge for a decision - 'ready' never means 'apply "
           "this setup'. It reuses the Phase-25 convergence, Phase-26 re-validation and Phase-27 "
           "coverage authorities, marks no unvalidated knowledge ready, carries no setup values, and "
           "recommends / schedules / applies / mutates NOTHING. Completion stays governed by Phase "
           "18 and the frozen Apply gate remains the sole route to the car.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ProgrammeKnowledgeReadinessReport:
    schema_version: int
    source_programme: dict
    generated_from: dict
    programme_grade: str
    grade_detail: dict
    items: Tuple[dict, ...]
    ready: Tuple[dict, ...]
    ready_with_limitations: Tuple[dict, ...]
    not_yet_ready: Tuple[dict, ...]
    blocked: Tuple[dict, ...]
    executive_summary: str
    totals: dict
    empty_state: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = PROGRAMME_READINESS_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from),
                "programme_grade": self.programme_grade, "grade_detail": dict(self.grade_detail),
                "items": [dict(i) for i in self.items], "ready": [dict(i) for i in self.ready],
                "ready_with_limitations": [dict(i) for i in self.ready_with_limitations],
                "not_yet_ready": [dict(i) for i in self.not_yet_ready],
                "blocked": [dict(i) for i in self.blocked],
                "executive_summary": self.executive_summary, "totals": dict(self.totals),
                "empty_state": self.empty_state, "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_programme_knowledge_readiness_report(
        timeline: Optional[Mapping], programme_knowledge: Optional[Mapping],
        revalidation: Optional[Mapping], coverage: Optional[Mapping]
) -> ProgrammeKnowledgeReadinessReport:
    """Assemble the programme knowledge readiness report. Deterministic; never raises."""
    try:
        return _build(timeline or {}, programme_knowledge or {}, revalidation or {}, coverage or {})
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeKnowledgeReadinessReport(
            schema_version=PROGRAMME_READINESS_REPORT_SCHEMA, source_programme={}, generated_from={},
            programme_grade="insufficient_evidence", grade_detail={}, items=(), ready=(),
            ready_with_limitations=(), not_yet_ready=(), blocked=(),
            executive_summary="Readiness report unavailable.", totals={},
            empty_state="Readiness report unavailable.", safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}), knowledge_versions=kv)


def _coverage_index(coverage: Mapping) -> dict:
    """Map domain -> {gap_count, blind_spot_severity} from the Phase-27 coverage report."""
    idx: dict = {}
    for cov in (coverage.get("domain_coverage") or []):
        if isinstance(cov, Mapping):
            idx[_lc(cov.get("domain"))] = {"gap_count": int(cov.get("gap_count") or 0),
                                           "blind_spot_severity": ""}
    for bucket in ("blind_spots", "early_stage_gaps", "unassessable"):
        for b in (coverage.get(bucket) or []):
            if isinstance(b, Mapping):
                d = _lc(b.get("domain"))
                idx.setdefault(d, {"gap_count": 0, "blind_spot_severity": ""})
                idx[d]["blind_spot_severity"] = _lc(b.get("severity"))
    return idx


def _build(timeline: Mapping, programme: Mapping, revalidation: Mapping,
           coverage: Mapping) -> ProgrammeKnowledgeReadinessReport:
    source = dict(timeline.get("source_programme") or {})
    reval_by_domain = {_lc(it.get("domain")): it for it in (revalidation.get("items") or [])
                       if isinstance(it, Mapping)}
    cov_idx = _coverage_index(coverage)

    items: List[dict] = []
    for c in (timeline.get("convergence_summaries") or []):
        if not isinstance(c, Mapping):
            continue
        domain = _lc(c.get("domain"))
        items.append(classify_readiness(c, reval_by_domain.get(domain, {}),
                                        cov_idx.get(domain, {})).to_dict())
    items.sort(key=_order)

    grade_detail = grade_programme(items)

    def bucket(*statuses):
        return tuple(i for i in items if i["readiness_status"] in statuses)

    ready = bucket("ready")
    ready_lim = bucket("ready_with_limitations", "context_bound_only")
    blocked = bucket("conflicted", "regressed", "superseded")
    not_yet = bucket("needs_revalidation", "needs_more_evidence", "provisional",
                     "insufficient_evidence", "unknown")

    relyable = sum(1 for i in items if i["readiness_status"] in RELYABLE_STATUSES)
    totals = {"domains": len(items), "ready": len(ready),
              "ready_with_limitations": len(ready_lim), "relyable": relyable,
              "not_yet_ready": len(not_yet), "blocked": len(blocked),
              "grade": grade_detail.get("grade")}

    summary = _executive_summary(source, grade_detail, totals)

    kv = knowledge_versions()
    fp = _fp({"src": {k: _lc(source.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
              "grade": grade_detail.get("grade"), "rule": grade_detail.get("rule"),
              "items": [(i["domain"], i["readiness_status"]) for i in items], "kv": kv})
    empty = "" if items else ("No engineering knowledge readiness to report yet - it appears once "
                              "the programme has recorded evidence for known domains.")
    return ProgrammeKnowledgeReadinessReport(
        schema_version=PROGRAMME_READINESS_REPORT_SCHEMA,
        source_programme={k: str(source.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase25_fingerprint": _lc(timeline.get("content_fingerprint")),
                        "phase26_fingerprint": _lc(revalidation.get("content_fingerprint")),
                        "phase27_fingerprint": _lc(coverage.get("content_fingerprint")),
                        "authorities": ["Phase 25 convergence/timeline", "Phase 26 re-validation",
                                        "Phase 27 evidence coverage"]},
        programme_grade=grade_detail.get("grade"), grade_detail=grade_detail, items=tuple(items),
        ready=ready, ready_with_limitations=ready_lim, not_yet_ready=not_yet, blocked=blocked,
        executive_summary=summary, totals=totals, empty_state=empty, safety_statement=_SAFETY,
        content_fingerprint=fp, knowledge_versions=kv)


def _order(i: Mapping):
    return (READINESS_PRIORITY.get(_lc(i.get("readiness_status")), 99),
            -_MATURITY_RANK.get(_lc(i.get("current_maturity")), 0),
            _DOMAIN_ORDER.index(_lc(i.get("domain"))) if _lc(i.get("domain")) in _DOMAIN_ORDER
            else 99, _lc(i.get("domain")))


def _executive_summary(source: Mapping, grade_detail: Mapping, totals: Mapping) -> str:
    grade = _lc(grade_detail.get("grade")).replace("_", " ")
    reasons = "; ".join(grade_detail.get("reasons") or []) or "no assessable knowledge yet"
    return (f"Programme readiness: {grade.upper()}. {totals.get('relyable')} of "
            f"{totals.get('domains')} domain(s) are ready to rely on "
            f"({totals.get('ready')} fully, {totals.get('ready_with_limitations')} within limits); "
            f"{totals.get('blocked')} blocked by a recorded conflict/regression; "
            f"{totals.get('not_yet_ready')} not yet ready. Grade basis: {reasons}. Advisory only - "
            "'ready' means the evidence supports relying on it, not 'apply this setup'.")


def knowledge_versions() -> dict:
    return {"programme_readiness_report": PROGRAMME_READINESS_REPORT_VERSION,
            "knowledge_readiness": KNOWLEDGE_READINESS_VERSION,
            "readiness_grade": READINESS_GRADE_VERSION,
            "schema": PROGRAMME_READINESS_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_READINESS_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
