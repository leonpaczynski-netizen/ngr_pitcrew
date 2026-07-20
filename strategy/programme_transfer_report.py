"""Programme Transfer Report — pure orchestration of knowledge transfer (Program 2, Phase 23).

Assembles the read-only knowledge-transfer view: for every ESTABLISHED domain in the source
programme's knowledge graph (Phase 22) and every candidate target context, it evaluates whether
the knowledge is reusable (Phase-23 ``knowledge_transfer`` + ``transfer_rules``) and summarises
the result (``engineering_reuse``). It RECOMPUTES no authority - the source knowledge, its
maturity and confidence come verbatim from Phase 22 (which reuses Phases 17-21).

It transfers NO setup values, recommends applying NOTHING, and decides NOTHING. Purity: Qt-free,
DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no ML / optimisation;
deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.knowledge_transfer import (
    KNOWLEDGE_TRANSFER_VERSION, evaluate_transfer,
)
from strategy.engineering_reuse import (
    ENGINEERING_REUSE_VERSION, summarise_reuse,
)
from strategy.transfer_rules import TRANSFER_RULES_VERSION, rule_catalogue

PROGRAMME_TRANSFER_REPORT_VERSION = "programme_transfer_report_v1"
PROGRAMME_TRANSFER_REPORT_SCHEMA = 1

# Only source domains at least this mature are worth evaluating for transfer.
_ESTABLISHED = ("established", "mature", "complete")

_SAFETY = ("Read-only knowledge-transfer view. It reasons about whether established ENGINEERING "
           "KNOWLEDGE (mechanisms, handling behaviour) is likely reusable in another compatible "
           "context - it transfers NO setup values, recommends applying NOTHING, imports "
           "NOTHING, and decides NOTHING. Every transfer level is fixed by visible deterministic "
           "rules; unlike contexts never transfer. Completion stays governed by Phase 18 and the "
           "frozen Apply gate remains the sole route to the car.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


@dataclass(frozen=True)
class ProgrammeTransferReport:
    source_context: dict
    target_contexts: Tuple[dict, ...]
    candidates: Tuple[dict, ...]
    reuse_summary: dict
    rule_catalogue: Tuple[dict, ...]
    totals: dict
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = PROGRAMME_TRANSFER_REPORT_SCHEMA
    eval_version: str = PROGRAMME_TRANSFER_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"source_context": dict(self.source_context),
                "target_contexts": [dict(t) for t in self.target_contexts],
                "candidates": [dict(c) for c in self.candidates],
                "reuse_summary": dict(self.reuse_summary),
                "rule_catalogue": [dict(r) for r in self.rule_catalogue],
                "totals": dict(self.totals), "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def build_transfer_report(source_graph: Optional[Mapping], source_context: Optional[Mapping],
                          target_contexts: Optional[Sequence[Mapping]]) -> ProgrammeTransferReport:
    """Evaluate transfer of every established source-domain to every target context and summarise
    reuse. ``source_graph`` is the Phase-22 knowledge graph (its ``domains``). Deterministic;
    preserves domain and target order; never raises."""
    try:
        return _build(source_graph or {}, source_context or {},
                      [t for t in (target_contexts or []) if isinstance(t, Mapping)])
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeTransferReport(
            source_context={}, target_contexts=(), candidates=(), reuse_summary={},
            rule_catalogue=rule_catalogue(), totals={}, safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(source_graph: Mapping, source_ctx: Mapping,
           targets: List[Mapping]) -> ProgrammeTransferReport:
    domains = [d for d in (source_graph.get("domains") or []) if isinstance(d, Mapping)]
    established = [d for d in domains
                   if _lc((d.get("maturity") or {}).get("value")) in _ESTABLISHED
                   and (d.get("supporting_campaigns") or [])]

    candidates: List[dict] = []
    for tgt in targets:
        for d in established:
            cand = evaluate_transfer(d, source_ctx, tgt).to_dict()
            candidates.append(cand)

    reuse = summarise_reuse(candidates).to_dict()

    kv = knowledge_versions()
    level_counts: dict = {}
    for c in candidates:
        lvl = c.get("transfer_level") or "unknown"
        level_counts[lvl] = level_counts.get(lvl, 0) + 1
    totals = {
        "established_source_domains": len(established),
        "target_contexts": len(targets),
        "candidates": len(candidates),
        "transfer_level_counts": level_counts,
        "reusable": reuse.get("counts", {}).get("reusable", 0),
        "not_reusable": reuse.get("counts", {}).get("not_reusable", 0),
        "needs_more_evidence": reuse.get("counts", {}).get("needs_more_evidence", 0),
        "isolated_targets": reuse.get("counts", {}).get("isolated_targets", 0),
    }
    fp = _fp({
        "src": {k: _norm(source_ctx.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
        "domains": [_lc(d.get("domain")) for d in established],
        "cands": [(c["engineering_domain"], _lc(c["target_context"].get("car")),
                   c["transfer_level"]) for c in candidates],
        "kv": kv,
    })
    return ProgrammeTransferReport(
        source_context=_ctx(source_ctx), target_contexts=tuple(_ctx(t) for t in targets),
        candidates=tuple(candidates), reuse_summary=reuse, rule_catalogue=rule_catalogue(),
        totals=totals, safety_statement=_SAFETY, content_fingerprint=fp, knowledge_versions=kv)


def _ctx(ctx: Mapping) -> dict:
    return {k: _norm(ctx.get(k)) for k in ("car", "discipline", "gt7_version", "driver")}


def knowledge_versions() -> dict:
    return {"programme_transfer_report": PROGRAMME_TRANSFER_REPORT_VERSION,
            "knowledge_transfer": KNOWLEDGE_TRANSFER_VERSION,
            "engineering_reuse": ENGINEERING_REUSE_VERSION,
            "transfer_rules": TRANSFER_RULES_VERSION,
            "schema": PROGRAMME_TRANSFER_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_TRANSFER_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
