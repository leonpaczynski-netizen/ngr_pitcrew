"""Season Engineering Report — pure orchestration of the season-level view (Phase 21).

Assembles the Engineering Director's read-only picture of the whole programme by joining the
existing per-campaign authorities (Phase-18 identity/objective/experiments + Phase-19
saturation/cost + Phase-20 confidence/ROI/opportunity) into one normalised record per campaign,
then running the three Phase-21 layers:

  1. season_development     - programme-wide summary
  2. cross_campaign_map     - engineering relationships between campaigns
  3. season_knowledge_map   - per-campaign knowledge state

It RECOMPUTES no authority - it only joins and aggregates. It ranks, prioritises, schedules,
completes and decides NOTHING; it preserves the incoming campaign order. Purity: Qt-free,
DB-free, UI-free, network-free, AI-free; no random, no wall-clock (dates are data);
deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.season_development import (
    SEASON_DEVELOPMENT_VERSION, summarize_season,
)
from strategy.cross_campaign_map import (
    CROSS_CAMPAIGN_MAP_VERSION, build_cross_campaign_map,
)
from strategy.season_knowledge_map import (
    SEASON_KNOWLEDGE_MAP_VERSION, classify_campaign_knowledge,
)

SEASON_ENGINEERING_REPORT_VERSION = "season_engineering_report_v1"
SEASON_ENGINEERING_REPORT_SCHEMA = 1

_SAFETY = ("Read-only Engineering Director's view. The season summary, cross-campaign map and "
           "knowledge map only EXPLAIN the current state of engineering - they schedule, rank, "
           "prioritise, complete, apply and decide NOTHING. Completion stays governed by Phase "
           "18 and the frozen Apply gate remains the sole route to the car.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _round(v) -> float:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class SeasonEngineeringReport:
    context_summary: dict
    development: dict                    # season_development summary
    relationships: dict                  # cross_campaign_map
    knowledge_map: Tuple[dict, ...]      # per-campaign knowledge states
    campaigns: Tuple[dict, ...]          # normalised per-campaign records (traceable)
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = SEASON_ENGINEERING_REPORT_SCHEMA
    eval_version: str = SEASON_ENGINEERING_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"context_summary": dict(self.context_summary), "development": dict(self.development),
                "relationships": dict(self.relationships),
                "knowledge_map": [dict(k) for k in self.knowledge_map],
                "campaigns": [dict(c) for c in self.campaigns],
                "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def build_season_report(programme: Optional[Mapping],
                        efficiency: Optional[Mapping],
                        quality: Optional[Mapping]) -> SeasonEngineeringReport:
    """Assemble the season report from the Phase-18 programme + Phase-19 efficiency + Phase-20
    knowledge-quality views. Deterministic; preserves campaign order; never raises."""
    try:
        return _build(programme or {}, efficiency or {}, quality or {})
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return SeasonEngineeringReport(
            context_summary={}, development={}, relationships={}, knowledge_map=(),
            campaigns=(), safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(programme: Mapping, efficiency: Mapping, quality: Mapping) -> SeasonEngineeringReport:
    prog_campaigns = list(programme.get("campaigns") or [])
    eff_by_id = _by_id(efficiency.get("campaigns") or [])
    qual_by_id = _by_id(quality.get("campaigns") or [])

    records: List[dict] = []
    for pc in prog_campaigns:
        pc = pc if isinstance(pc, Mapping) else {}
        ident = pc.get("identity") or {}
        cid = _norm(ident.get("campaign_id"))
        eff = eff_by_id.get(cid, {})
        qual = qual_by_id.get(cid, {})
        records.append(_normalize(cid, pc, ident, eff, qual))

    knowledge_states = [classify_campaign_knowledge(r).to_dict() for r in records]
    relationships = build_cross_campaign_map(records).to_dict()
    development = summarize_season(records, knowledge_states).to_dict()

    kv = knowledge_versions()
    fp = _fp({
        "prog": _norm(programme.get("content_fingerprint")),
        "eff": _norm(efficiency.get("content_fingerprint")),
        "qual": _norm(quality.get("content_fingerprint")),
        "states": [(k["campaign_id"], k["state"]) for k in knowledge_states],
        "edges": [(e["from_campaign_id"], e["to_campaign_id"], e["relationship"])
                  for e in relationships.get("edges") or []],
        "kv": kv,
    })
    return SeasonEngineeringReport(
        context_summary=dict(programme.get("context_summary")
                             or quality.get("context_summary") or {}),
        development=development, relationships=relationships,
        knowledge_map=tuple(knowledge_states), campaigns=tuple(records),
        safety_statement=_SAFETY, content_fingerprint=fp, knowledge_versions=kv)


def _by_id(campaigns) -> dict:
    out = {}
    for c in campaigns or []:
        if isinstance(c, Mapping):
            out[_norm(c.get("campaign_id"))] = c
    return out


def _normalize(cid: str, pc: Mapping, ident: Mapping, eff: Mapping, qual: Mapping) -> dict:
    objective = _norm((pc.get("objective") or {}).get("title")) or _norm(eff.get("objective"))
    experiments = [e for e in (pc.get("experiments") or []) if isinstance(e, Mapping)]
    fields = sorted({_lc(e.get("field")) for e in experiments if _lc(e.get("field"))})
    mechanisms = sorted({_lc(m) for m in ((pc.get("objective") or {}).get("source_mechanisms")
                                          or []) if _lc(m)})

    sat = eff.get("saturation") or {}
    sig = (sat.get("signals") or {}) if isinstance(sat, Mapping) else {}
    costs = [c for c in (eff.get("experiment_costs") or []) if isinstance(c, Mapping)]
    total_value = _round(sum(_round(c.get("engineering_value")) for c in costs))
    remaining_value = _round(sum(_round(c.get("engineering_value")) for c in costs
                                 if c.get("testable")))
    testable = any(bool(c.get("testable")) for c in costs)

    conf = qual.get("confidence") or {}
    roi = qual.get("roi") or {}
    opp = qual.get("opportunity") or {}

    return {
        "campaign_id": cid, "objective": objective, "status": _lc(pc.get("status")),
        "family": _lc(ident.get("objective_family")), "region": _lc(ident.get("objective_region")),
        "car": _norm(ident.get("car")), "track": _norm(ident.get("track")),
        "layout": _norm(ident.get("layout")), "discipline": _norm(ident.get("discipline")),
        "fields": fields, "mechanisms": mechanisms,
        "confidence_level": _lc(conf.get("overall_level")) or "unknown",
        "confidence_score": conf.get("overall_score"),
        "opportunity": _lc(opp.get("opportunity")), "worthwhile": bool(opp.get("worthwhile")),
        "knowledge_gap": roi.get("knowledge_gap"),
        "confirmations": _int(sig.get("confirmations")), "regressions": _int(sig.get("regressions")),
        "conflicting": bool(sig.get("conflicting_evidence")),
        "unresolved_mechanisms": _int(sig.get("unresolved_mechanisms")),
        "executed": _int(sig.get("executed")),
        "remaining_information_gain": _lc(eff.get("remaining_information_gain")),
        "total_value": total_value, "remaining_value": remaining_value, "testable": testable,
        "remaining_laps": _int(eff.get("estimated_remaining_laps")),
        "remaining_tyre_sets": _round(eff.get("estimated_remaining_tyre_sets")),
        "remaining_minutes": _round(eff.get("estimated_remaining_time_minutes")),
    }


def knowledge_versions() -> dict:
    return {"season_engineering_report": SEASON_ENGINEERING_REPORT_VERSION,
            "season_development": SEASON_DEVELOPMENT_VERSION,
            "cross_campaign_map": CROSS_CAMPAIGN_MAP_VERSION,
            "season_knowledge_map": SEASON_KNOWLEDGE_MAP_VERSION,
            "schema": SEASON_ENGINEERING_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{SEASON_ENGINEERING_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
