"""Programme Knowledge Contradiction Report — pure orchestration (Program 2, Phase 29).

Finds, per known engineering domain, where the evidence contradicts itself (a confirming and a
regressing conclusion for the same domain) and characterises each disagreement: its visible causes
and whether it is resolved by context, resolved by stronger independent evidence, or genuinely open.
It reuses the CANONICAL Phase-25 record→domain mapping verbatim (invents no domains), grounds every
contradiction in real records (never in a flag alone), and never resolves by majority or recency.

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
from strategy.contradiction_resolution_status import (
    CONTRADICTION_STATUS_PRIORITY, RESOLVED_STATUSES, ContradictionStatus,
)
from strategy.knowledge_contradiction import (
    KNOWLEDGE_CONTRADICTION_VERSION, detect_contradiction,
)

PROGRAMME_CONTRADICTION_REPORT_VERSION = "programme_contradiction_report_v1"
PROGRAMME_CONTRADICTION_REPORT_SCHEMA = 1

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]
_POSITIVE = ("confirmed_improvement", "partial_improvement")

_SAFETY = ("Read-only contradiction report. It explains where the evidence disagrees and whether "
           "each disagreement is context-explained, resolved by stronger independent evidence, or "
           "genuinely open - it NEVER resolves by majority vote or by recency, never lets dependent "
           "evidence defeat independent evidence, carries no setup values, and recommends / "
           "schedules / applies / mutates NOTHING. A contradiction is allowed to remain unresolved. "
           "Completion stays governed by Phase 18 and the frozen Apply gate remains the sole route "
           "to the car.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ProgrammeContradictionReport:
    schema_version: int
    source_programme: dict
    generated_from: dict
    contradictions: Tuple[dict, ...]
    open_contradictions: Tuple[dict, ...]
    resolved_contradictions: Tuple[dict, ...]
    totals: dict
    empty_state: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = PROGRAMME_CONTRADICTION_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from),
                "contradictions": [dict(c) for c in self.contradictions],
                "open_contradictions": [dict(c) for c in self.open_contradictions],
                "resolved_contradictions": [dict(c) for c in self.resolved_contradictions],
                "totals": dict(self.totals), "empty_state": self.empty_state,
                "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_programme_contradiction_report(
        timeline: Optional[Mapping], programme_knowledge: Optional[Mapping],
        evidence_records: Optional[Sequence[Mapping]]) -> ProgrammeContradictionReport:
    """Assemble the contradiction report. Deterministic; never raises."""
    try:
        return _build(timeline or {}, programme_knowledge or {},
                      [r for r in (evidence_records or []) if isinstance(r, Mapping)])
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeContradictionReport(
            schema_version=PROGRAMME_CONTRADICTION_REPORT_SCHEMA, source_programme={},
            generated_from={}, contradictions=(), open_contradictions=(),
            resolved_contradictions=(), totals={}, empty_state="Contradiction report unavailable.",
            safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}), knowledge_versions=kv)


def _build(timeline: Mapping, programme: Mapping,
           records: List[Mapping]) -> ProgrammeContradictionReport:
    source = dict(timeline.get("source_programme") or {})

    # bucket positive vs negative records per domain (canonical mapping, reused).
    pos_by_domain: dict = {}
    neg_by_domain: dict = {}
    for r in records:
        outcome = _lc(r.get("outcome_status"))
        if outcome in _POSITIVE:
            target = pos_by_domain
        elif outcome == "regression":
            target = neg_by_domain
        else:
            continue
        for dom in _record_domains(r):
            target.setdefault(dom, []).append(r)

    # a contradiction exists only where a domain has BOTH confirming and regressing records.
    domains = sorted(set(pos_by_domain) & set(neg_by_domain),
                     key=lambda d: (_DOMAIN_ORDER.index(d) if d in _DOMAIN_ORDER else 99, d))

    contradictions: List[dict] = []
    for dom in domains:
        contradictions.append(detect_contradiction(dom, pos_by_domain.get(dom, []),
                                                    neg_by_domain.get(dom, [])).to_dict())
    contradictions.sort(key=_order)

    open_c = tuple(c for c in contradictions if c.get("is_open"))
    resolved_c = tuple(c for c in contradictions if not c.get("is_open"))

    totals = {"contradictions": len(contradictions), "open": len(open_c),
              "resolved": len(resolved_c),
              "unresolved_genuine": sum(1 for c in contradictions
                                        if _lc(c.get("status")) == ContradictionStatus.UNRESOLVED.value),
              "resolved_by_context": sum(1 for c in contradictions
                                         if _lc(c.get("status")) == "resolved_by_context")}

    kv = knowledge_versions()
    fp = _fp({"src": {k: _lc(source.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
              "c": [(c["domain"], c["status"], c["is_open"],
                     [x["cause"] for x in c["causes"]]) for c in contradictions], "kv": kv})
    empty = "" if contradictions else ("No evidence contradictions found - no domain has both a "
                                       "confirming and a regressing conclusion on record.")
    return ProgrammeContradictionReport(
        schema_version=PROGRAMME_CONTRADICTION_REPORT_SCHEMA,
        source_programme={k: str(source.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase25_fingerprint": _lc(timeline.get("content_fingerprint")),
                        "phase22_fingerprint": _lc(programme.get("content_fingerprint")),
                        "authorities": ["Phase 22 knowledge graph", "Phase 25 convergence/timeline",
                                        "immutable development records"]},
        contradictions=tuple(contradictions), open_contradictions=open_c,
        resolved_contradictions=resolved_c, totals=totals, empty_state=empty,
        safety_statement=_SAFETY, content_fingerprint=fp, knowledge_versions=kv)


def _order(c: Mapping):
    return (CONTRADICTION_STATUS_PRIORITY.get(_lc(c.get("status")), 99),
            _DOMAIN_ORDER.index(_lc(c.get("domain"))) if _lc(c.get("domain")) in _DOMAIN_ORDER
            else 99, _lc(c.get("domain")))


def knowledge_versions() -> dict:
    return {"programme_contradiction_report": PROGRAMME_CONTRADICTION_REPORT_VERSION,
            "knowledge_contradiction": KNOWLEDGE_CONTRADICTION_VERSION,
            "schema": PROGRAMME_CONTRADICTION_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_CONTRADICTION_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
