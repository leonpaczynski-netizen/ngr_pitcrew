"""Programme Knowledge Report — pure orchestration of the Engineering Knowledge Graph (Phase 22).

Assembles the programme-level knowledge view by rolling up compatible events (multi_event_rollup)
and building the per-domain knowledge graph (engineering_knowledge_graph, with knowledge_maturity)
for the primary compatibility group. It RECOMPUTES no authority - it only rolls up and aggregates
existing per-campaign knowledge (Phase-18 identity + Phase-19 saturation/cost + Phase-20
confidence/ROI + Phase-21 season report). It ranks, schedules, completes and decides NOTHING.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no graph /
network libraries; deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.multi_event_rollup import (
    MULTI_EVENT_ROLLUP_VERSION, build_rollup,
)
from strategy.engineering_knowledge_graph import (
    ENGINEERING_KNOWLEDGE_GRAPH_VERSION, build_knowledge_graph,
)
from strategy.knowledge_maturity import KNOWLEDGE_MATURITY_VERSION

PROGRAMME_KNOWLEDGE_REPORT_VERSION = "programme_knowledge_report_v1"
PROGRAMME_KNOWLEDGE_REPORT_SCHEMA = 1

_SAFETY = ("Read-only programme knowledge graph. It describes what the Engineering Brain knows, "
           "how mature that knowledge is and what remains unknown - organised by engineering "
           "domain and rolled up across compatible events. It ranks, schedules, completes, "
           "applies and decides NOTHING; completion stays governed by Phase 18 and the frozen "
           "Apply gate remains the sole route to the car. Unlike contexts are never merged.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


@dataclass(frozen=True)
class ProgrammeKnowledgeReport:
    context_summary: dict
    compatibility: dict                  # primary group key + tracks + other-group exclusions
    knowledge_graph: dict                # domains + maturity + known/missing
    totals: dict
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = PROGRAMME_KNOWLEDGE_REPORT_SCHEMA
    eval_version: str = PROGRAMME_KNOWLEDGE_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"context_summary": dict(self.context_summary),
                "compatibility": dict(self.compatibility),
                "knowledge_graph": dict(self.knowledge_graph), "totals": dict(self.totals),
                "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def build_programme_knowledge(events: Sequence[Mapping], *,
                              primary_context: Optional[Mapping] = None) -> ProgrammeKnowledgeReport:
    """Roll up the per-event knowledge into the primary compatibility group and build its domain
    knowledge graph. ``events`` = list of ``{"context": {...}, "campaigns": [enriched records]}``.
    Deterministic; never raises."""
    try:
        return _build([e for e in (events or []) if isinstance(e, Mapping)],
                      primary_context if isinstance(primary_context, Mapping) else None)
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeKnowledgeReport(
            context_summary={}, compatibility={}, knowledge_graph={}, totals={},
            safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(events: List[Mapping], primary_context: Optional[Mapping]) -> ProgrammeKnowledgeReport:
    rollup = build_rollup(events, primary_context=primary_context).to_dict()
    primary = rollup.get("primary_group") or {}
    campaigns = primary.get("campaigns") or []
    graph = build_knowledge_graph(campaigns).to_dict()

    compatibility = {
        "primary_key": primary.get("compatibility_key") or {},
        "primary_tracks": primary.get("tracks") or [],
        "events_merged": len(primary.get("contexts") or []),
        "merge_reason": primary.get("merge_reason") or "",
        "other_groups": [{"compatibility_key": g.get("compatibility_key"),
                          "tracks": g.get("tracks")} for g in rollup.get("other_groups") or []],
        "excluded_reasons": rollup.get("excluded_reasons") or [],
    }
    totals = {
        "campaigns": len(campaigns),
        "known_domains": len(graph.get("known_domains") or []),
        "missing_domains": len(graph.get("missing_domains") or []),
        "domain_maturity_counts": graph.get("domain_maturity_counts") or {},
        "events_merged": len(primary.get("contexts") or []),
        "other_programme_groups": len(rollup.get("other_groups") or []),
    }
    kv = knowledge_versions()
    fp = _fp({
        "primary": primary.get("compatibility_key"),
        "tracks": primary.get("tracks"),
        "domains": [(d["domain"], d["maturity"]["value"], d["knowledge_state"]["value"])
                    for d in graph.get("domains") or []],
        "others": [g.get("compatibility_key") for g in rollup.get("other_groups") or []],
        "kv": kv,
    })
    return ProgrammeKnowledgeReport(
        context_summary=_context_summary(primary),
        compatibility=compatibility, knowledge_graph=graph, totals=totals,
        safety_statement=_SAFETY, content_fingerprint=fp, knowledge_versions=kv)


def _context_summary(primary: Mapping) -> dict:
    key = primary.get("compatibility_key") or {}
    return {"car": _norm(key.get("car")), "discipline": _norm(key.get("discipline")),
            "gt7_version": _norm(key.get("gt7_version")), "driver": _norm(key.get("driver")),
            "tracks": list(primary.get("tracks") or [])}


def knowledge_versions() -> dict:
    return {"programme_knowledge_report": PROGRAMME_KNOWLEDGE_REPORT_VERSION,
            "multi_event_rollup": MULTI_EVENT_ROLLUP_VERSION,
            "engineering_knowledge_graph": ENGINEERING_KNOWLEDGE_GRAPH_VERSION,
            "knowledge_maturity": KNOWLEDGE_MATURITY_VERSION,
            "schema": PROGRAMME_KNOWLEDGE_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_KNOWLEDGE_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
