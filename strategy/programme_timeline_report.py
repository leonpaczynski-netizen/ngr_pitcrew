"""Programme Knowledge Timeline — pure orchestration of the temporal knowledge layer (Phase 25).

Assembles the read-only Engineering Knowledge Timeline: how each domain's understanding evolved
across compatible events, where evidence genuinely converged, where it remains unresolved, and
where apparent repetition is only duplicated / dependent evidence.

It consumes the existing HIGHEST-level products: the Phase-22 programme knowledge graph (per-domain
maturity/confidence/evidence — the authority), the Phase-24 engineering playbook (confirmed-good,
boundaries, transfer limits) and one bounded historical evidence retrieval (the immutable
development records). It RECOMPUTES no lower-level intelligence, reuses the Phase-23 TransferLevel
semantics via the playbook, carries NO setup values, and treats dates as data (never "latest is
best").

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.engineering_knowledge_graph import (
    KnowledgeDomain, FIELD_DOMAIN_KEYWORDS, FAMILY_DOMAIN_KEYWORDS, MECHANISM_DOMAIN_KEYWORDS,
    ENGINEERING_KNOWLEDGE_GRAPH_VERSION,
)
from strategy.transfer_rules import domain_transfer_class
from strategy.knowledge_timeline import (
    KNOWLEDGE_TIMELINE_VERSION, build_timeline,
)
from strategy.knowledge_convergence import (
    KNOWLEDGE_CONVERGENCE_VERSION, CONVERGENCE_PRIORITY, assess_convergence,
)
from strategy.evidence_independence import EVIDENCE_INDEPENDENCE_VERSION

PROGRAMME_TIMELINE_REPORT_VERSION = "programme_timeline_report_v1"
PROGRAMME_TIMELINE_REPORT_SCHEMA = 1

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]
_MATURITY_RANK = {"unknown": 0, "emerging": 1, "developing": 2, "established": 3, "mature": 4,
                  "complete": 5, "plateaued": 3}
_CONFIDENCE_RANK = {"unknown": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4, "very_high": 5}

_SAFETY = ("Read-only engineering knowledge timeline. It explains how understanding evolved and "
           "where evidence genuinely converged - dates are evidence data, never authority, and a "
           "newer observation never automatically overrides an older stronger finding. It reuses "
           "the Phase-23 transfer semantics (SUPPORTED = hypothesis / investigation aid only), "
           "carries no setup values, and recommends / schedules / applies / mutates NOTHING. "
           "Completion stays governed by Phase 18 and the frozen Apply gate remains the sole "
           "route to the car.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class ProgrammeKnowledgeTimeline:
    schema_version: int
    source_programme: dict
    generated_from: dict
    timeline_points: Tuple[dict, ...]
    convergence_summaries: Tuple[dict, ...]
    stable_confirmed_good: Tuple[dict, ...]
    unresolved_conflicts: Tuple[dict, ...]
    regressions_and_retired: Tuple[dict, ...]
    superseded_conclusions: Tuple[dict, ...]
    knowledge_boundaries: Tuple[dict, ...]
    transfer_limitations: Tuple[dict, ...]
    evidence_independence_summary: dict
    empty_state: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = PROGRAMME_TIMELINE_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from),
                "timeline_points": [dict(p) for p in self.timeline_points],
                "convergence_summaries": [dict(c) for c in self.convergence_summaries],
                "stable_confirmed_good": [dict(x) for x in self.stable_confirmed_good],
                "unresolved_conflicts": [dict(x) for x in self.unresolved_conflicts],
                "regressions_and_retired": [dict(x) for x in self.regressions_and_retired],
                "superseded_conclusions": [dict(x) for x in self.superseded_conclusions],
                "knowledge_boundaries": [dict(x) for x in self.knowledge_boundaries],
                "transfer_limitations": [dict(x) for x in self.transfer_limitations],
                "evidence_independence_summary": dict(self.evidence_independence_summary),
                "empty_state": self.empty_state, "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_programme_timeline(programme_knowledge: Optional[Mapping],
                             playbook: Optional[Mapping],
                             evidence_records: Optional[Sequence[Mapping]]
                             ) -> ProgrammeKnowledgeTimeline:
    """Assemble the programme knowledge timeline from the Phase-22 programme knowledge report, the
    Phase-24 playbook, and the bounded historical evidence records. Deterministic; never raises."""
    try:
        return _build(programme_knowledge or {}, playbook or {},
                      [e for e in (evidence_records or []) if isinstance(e, Mapping)])
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeKnowledgeTimeline(
            schema_version=PROGRAMME_TIMELINE_REPORT_SCHEMA, source_programme={}, generated_from={},
            timeline_points=(), convergence_summaries=(), stable_confirmed_good=(),
            unresolved_conflicts=(), regressions_and_retired=(), superseded_conclusions=(),
            knowledge_boundaries=(), transfer_limitations=(), evidence_independence_summary={},
            empty_state="Timeline unavailable.", safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _record_domains(rec: Mapping) -> set:
    """Map ONE development record to engineering domains using the VISIBLE Phase-22 keyword maps
    (fields from changes, families from residual states) - no new mapping logic, no inference."""
    domains = set()
    for c in (rec.get("changes") or []):
        f = _lc((c or {}).get("field")) if isinstance(c, Mapping) else ""
        for dom, kws in FIELD_DOMAIN_KEYWORDS.items():
            if f and any(kw in f for kw in kws):
                domains.add(dom.value)
    for r in (rec.get("residual_states") or []):
        fam = _lc((r or {}).get("family")) if isinstance(r, Mapping) else ""
        for dom, kws in FAMILY_DOMAIN_KEYWORDS.items():
            if fam and any(kw in fam for kw in kws):
                domains.add(dom.value)
    return domains


def _sequence_keys(records: List[Mapping]) -> dict:
    """Assign a deterministic sequence index to each (session_date, session_id) pair - unknown
    dates sort last. Insertion order is NOT used as the authority."""
    pairs = set()
    for r in records:
        date = _norm(r.get("session_date")) or "9999-99-99"
        pairs.add((date, _lc(r.get("test_session_id"))))
    ordered = sorted(pairs)
    return {pair: i for i, pair in enumerate(ordered)}


def _build(programme: Mapping, playbook: Mapping, records: List[Mapping]
           ) -> ProgrammeKnowledgeTimeline:
    graph = programme.get("knowledge_graph") or {}
    compatibility = programme.get("compatibility") or {}
    source_key = dict(compatibility.get("primary_key") or {})
    known_domains = set(_lc(d) for d in (graph.get("known_domains") or []))

    graph_by_domain = {}
    for d in (graph.get("domains") or []):
        if isinstance(d, Mapping):
            graph_by_domain[_lc(d.get("domain"))] = d

    # playbook signals per domain (confirmed-good, boundaries, transfer limits).
    cg_domains = set()
    for t in (playbook.get("stable_themes") or []):
        if isinstance(t, Mapping) and t.get("confirmed_good_protections"):
            cg_domains.add(_lc(t.get("engineering_domain")))
    boundaries_by_domain: dict = {}
    for b in (playbook.get("knowledge_boundaries") or []):
        if isinstance(b, Mapping):
            boundaries_by_domain.setdefault(_lc(b.get("domain")), []).append(b)

    seq = _sequence_keys(records)

    # bucket evidence per domain (only domains the Phase-22 graph knows).
    evidence_by_domain: dict = {}
    for r in records:
        date = _norm(r.get("session_date")) or ""
        session = _lc(r.get("test_session_id"))
        scope = _lc(r.get("scope_fingerprint"))
        ref = _lc(r.get("record_key")) or _lc(r.get("scope_fingerprint")) + "|" + session
        ctx = r.get("context") or {}
        ev = {"record_ref": ref, "session_id": session, "scope_fingerprint": scope,
              "evidence_date": date, "sequence_key": seq.get((date or "9999-99-99", session), 0),
              "outcome_status": _lc(r.get("outcome_status")),
              "confidence_level": _lc(r.get("confidence_level")),
              "is_failed_direction": _lc(r.get("outcome_status")) == "regression",
              "event": {"car": _norm(ctx.get("car")), "track": _norm(ctx.get("track")),
                        "layout": _norm(ctx.get("layout_id")),
                        "discipline": _norm(ctx.get("discipline")), "session_id": session}}
        for dom in _record_domains(r):
            # include every record-mapped domain that the Phase-22 graph knows about (all 17
            # appear in the graph) - a domain retired by a regression must keep its negative
            # history visible, so it is NOT filtered out to `known_domains` only.
            if dom in graph_by_domain:
                evidence_by_domain.setdefault(dom, []).append(ev)

    # deterministic per-domain evidence order (sequence, then record ref).
    domain_entries = []
    for dom in sorted(evidence_by_domain, key=lambda d: (_DOMAIN_ORDER.index(d)
                                                         if d in _DOMAIN_ORDER else 99, d)):
        evs = sorted(evidence_by_domain[dom], key=lambda e: (int(e["sequence_key"]),
                                                             e["record_ref"]))
        auth = _authority(dom, graph_by_domain.get(dom, {}), cg_domains,
                          boundaries_by_domain.get(dom, []), records)
        domain_entries.append({"domain": dom, "evidence": evs, "authority": auth})

    points, indep_by_domain = build_timeline(domain_entries, source_key)

    # convergence per domain.
    points_by_domain: dict = {}
    for p in points:
        points_by_domain.setdefault(_lc(p.get("knowledge_domain")), []).append(p)
    convergences = []
    for entry in domain_entries:
        dom = entry["domain"]
        conv = assess_convergence(dom, points_by_domain.get(dom, []),
                                  indep_by_domain.get(dom, {}), entry["authority"]).to_dict()
        convergences.append(conv)
    convergences.sort(key=_convergence_order)

    # derived summary buckets.
    stable_cg = [c for c in convergences if c["confirmed_good"]]
    conflicts = [c for c in convergences if c["convergence_status"] == "conflicting"]
    regressions = [c for c in convergences
                   if c["convergence_status"] in ("regressed",) or c["regression_count"] > 0
                   or c["retired_directions"]]
    superseded = [c for c in convergences if c["convergence_status"] == "superseded"]
    all_boundaries = _dedup_boundaries(boundaries_by_domain)
    transfer_limits = _transfer_limits(convergences)
    indep_summary = _global_independence(indep_by_domain)

    empty = ("No engineering evidence timeline yet for this programme - it appears once the "
             "programme has recorded evidence across events."
             if not points else "")

    kv = knowledge_versions()
    fp = _fp({
        "src": {k: _lc(source_key.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
        "points": [(p["knowledge_domain"], p["evidence_date"], p["sequence_key"],
                    p["transition_type"], p["evidence_independence"],
                    p["evidence_references"]) for p in points],
        "conv": [(c["domain"], c["convergence_status"], c["independent_support_count"]) for c in
                 convergences],
        "kv": kv,
    })
    return ProgrammeKnowledgeTimeline(
        schema_version=PROGRAMME_TIMELINE_REPORT_SCHEMA,
        source_programme={k: str(source_key.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase22_fingerprint": _lc(programme.get("content_fingerprint")),
                        "phase24_fingerprint": _lc(playbook.get("content_fingerprint")),
                        "authorities": ["Phase 22 knowledge graph", "Phase 23 transfer (via P24)",
                                        "Phase 24 engineering playbook",
                                        "immutable development records"]},
        timeline_points=tuple(points), convergence_summaries=tuple(convergences),
        stable_confirmed_good=tuple(stable_cg), unresolved_conflicts=tuple(conflicts),
        regressions_and_retired=tuple(regressions), superseded_conclusions=tuple(superseded),
        knowledge_boundaries=tuple(all_boundaries), transfer_limitations=tuple(transfer_limits),
        evidence_independence_summary=indep_summary, empty_state=empty, safety_statement=_SAFETY,
        content_fingerprint=fp, knowledge_versions=kv)


def _authority(domain: str, graph_domain: Mapping, cg_domains: set, boundaries: List[Mapping],
               records: List[Mapping]) -> dict:
    ev = graph_domain.get("supporting_evidence") or {}
    limits = [str(x) for x in (graph_domain.get("known_limitations") or [])]
    conflicting = any("conflict" in _lc(x) for x in limits)
    transfer_limit_types = ("gt7_version_specific", "manufacturer_specific", "drivetrain_specific",
                            "category_specific", "unverified_transfer_proxy", "car_specific")
    context_types = ("track_specific", "track_layout_specific", "discipline_specific",
                     "fuel_rule_specific", "driver_specific")
    transfer_limits = [f"{_lc(b.get('boundary_type'))}: {b.get('reason')}"
                       for b in boundaries if _lc(b.get("boundary_type")) in transfer_limit_types]
    context_limits = [f"{_lc(b.get('boundary_type'))}: {b.get('reason')}"
                      for b in boundaries if _lc(b.get("boundary_type")) in context_types]
    retired = [b.get("reason") for b in boundaries
               if _lc(b.get("boundary_type")) == "failed_historical_outcome"]
    unresolved = [b.get("reason") for b in boundaries
                  if _lc(b.get("boundary_type")) in ("conflicting_evidence", "insufficient_evidence")]
    # compatible vs context-limited observations for this domain.
    dom_records = [r for r in records if domain in _record_domains(r)]
    tracks = set(_lc((r.get("context") or {}).get("track")) for r in dom_records)
    # confirmation / regression counts derived DIRECTLY from the raw records so negative learning
    # stays visible even when the Phase-22 graph retired the direction (grounds the timeline).
    rec_confirms = sum(1 for r in dom_records
                       if _lc(r.get("outcome_status")) in ("confirmed_improvement",
                                                           "partial_improvement"))
    rec_regress = sum(1 for r in dom_records if _lc(r.get("outcome_status")) == "regression")
    graph_confirms = _int(ev.get("confirmations"))
    graph_regress = _int(ev.get("regressions"))
    confirmations = max(graph_confirms, rec_confirms)
    regressions = max(graph_regress, rec_regress)
    conflicting = conflicting or (confirmations > 0 and regressions > 0)
    return {"maturity": _lc((graph_domain.get("maturity") or {}).get("value")),
            "confidence": _lc((graph_domain.get("confidence") or {}).get("value")),
            "confirmations": confirmations, "regressions": regressions,
            "conflicting": conflicting, "confirmed_good": domain in cg_domains,
            "transfer_class": domain_transfer_class(domain),
            "transfer_limitations": transfer_limits, "context_limitations": context_limits,
            "retired_directions": retired, "unresolved_boundaries": unresolved,
            "compatible_contexts": len([t for t in tracks if t]),
            "context_limited_observations": len(context_limits)}


def _convergence_order(c: Mapping):
    return (CONVERGENCE_PRIORITY.get(_lc(c.get("convergence_status")), 99),
            0 if c.get("confirmed_good") else 1,
            -_int(c.get("independent_support_count")),
            -_MATURITY_RANK.get(_lc(c.get("current_maturity")), 0),
            -_CONFIDENCE_RANK.get(_lc(c.get("current_confidence")), 0),
            _DOMAIN_ORDER.index(_lc(c.get("domain"))) if _lc(c.get("domain")) in _DOMAIN_ORDER
            else 99, _lc(c.get("domain")))


def _dedup_boundaries(boundaries_by_domain: dict) -> List[dict]:
    seen = set()
    out = []
    for dom in sorted(boundaries_by_domain):
        for b in boundaries_by_domain[dom]:
            key = (_lc(b.get("boundary_type")), _lc(b.get("domain")), _lc(b.get("target_car")))
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(b))
    return out


def _transfer_limits(convergences: List[Mapping]) -> List[dict]:
    out = []
    for c in convergences:
        for lim in c.get("transfer_limitations") or []:
            out.append({"domain": c.get("domain"), "limitation": lim})
    return out


def _global_independence(indep_by_domain: dict) -> dict:
    total_ind = total_partial = total_same_session = total_same_record = 0
    for s in indep_by_domain.values():
        if isinstance(s, Mapping):
            total_ind += _int(s.get("independent_groups"))
            total_partial += _int(s.get("partially_independent"))
            total_same_session += _int(s.get("same_session"))
            total_same_record += _int(s.get("same_source_record"))
    return {"independent_groups": total_ind, "partially_independent": total_partial,
            "same_session": total_same_session, "same_source_record": total_same_record,
            "note": "Phase-22/23/24 re-statements of a conclusion are one lineage, not extra "
                    "independent confirmations."}


def knowledge_versions() -> dict:
    return {"programme_timeline_report": PROGRAMME_TIMELINE_REPORT_VERSION,
            "knowledge_timeline": KNOWLEDGE_TIMELINE_VERSION,
            "knowledge_convergence": KNOWLEDGE_CONVERGENCE_VERSION,
            "evidence_independence": EVIDENCE_INDEPENDENCE_VERSION,
            "knowledge_graph": ENGINEERING_KNOWLEDGE_GRAPH_VERSION,
            "schema": PROGRAMME_TIMELINE_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_TIMELINE_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
