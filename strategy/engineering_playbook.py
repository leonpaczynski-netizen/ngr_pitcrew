"""Engineering Playbook — cross-programme engineering investigation playbook (Program 2, Phase 24).

Pure orchestration that assembles the reusable engineering knowledge across the driver's car
stable into a deterministic, read-only INVESTIGATION playbook (never a baseline setup). It joins
the Phase-22 programme knowledge graph with the Phase-23 transfer report into one normalised
per-domain record, then runs the Phase-24 layers: stable themes, investigation priorities,
knowledge boundaries and per-target new-programme briefs.

It assembles / ranks / classifies / explains existing knowledge only. It generates NO setup
values, copies NO fields, recommends NO starting setup, applies / schedules / persists NOTHING,
recreates NO knowledge graph and reuses Phase-23 transfer decisions EXACTLY. Purity: Qt-free,
DB-free, UI-free, network-free, AI-free; no random, no wall-clock (no timestamps in the
fingerprint); no ML / optimisation; deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.engineering_knowledge_graph import (
    KnowledgeDomain, ENGINEERING_KNOWLEDGE_GRAPH_VERSION,
)
from strategy.transfer_rules import domain_transfer_class
from strategy.stable_themes import STABLE_THEMES_VERSION, build_stable_themes
from strategy.investigation_priority import (
    INVESTIGATION_PRIORITY_VERSION, classify_priorities, CATEGORY_PRIORITY,
)
from strategy.knowledge_boundary import KNOWLEDGE_BOUNDARY_VERSION, build_boundaries
from strategy.new_programme_brief import NEW_PROGRAMME_BRIEF_VERSION, build_briefs

ENGINEERING_PLAYBOOK_VERSION = "engineering_playbook_v1"
ENGINEERING_PLAYBOOK_SCHEMA = 1

_ESTABLISHED = ("established", "mature", "complete")
_CONFIRMED_STATES = ("engineering_complete", "well_understood")
_CONFIDENT = ("high", "very_high")
_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]
_MATURITY_RANK = {"unknown": 0, "emerging": 1, "developing": 2, "established": 3, "mature": 4,
                  "complete": 5, "plateaued": 3}
_CONFIDENCE_RANK = {"unknown": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4, "very_high": 5}

_SAFETY = ("Read-only engineering INVESTIGATION playbook. It assembles, ranks, classifies and "
           "explains existing engineering knowledge across the car stable - it is NOT a baseline "
           "setup. No setup values are generated, copied, recommended or applied; no experiment "
           "or campaign is created or scheduled; nothing is optimised, mutated or persisted. All "
           "knowledge requires validation in the target context; completion stays governed by "
           "Phase 18 and the frozen Apply gate remains the sole route to the car.")

_LIMITATIONS = (
    "Knowledge is assembled for the current (primary) programme and its transfer to the other "
    "compatibility groups; it is not a full all-pairs stable matrix.",
    "Confirmed-good is a domain-level proxy from the Phase-22 knowledge state + confidence, not a "
    "per-corner driver-confirmed behaviour.",
    "Suspension compatibility across manufacturers is a manufacturer+category PROXY (Phase 23), "
    "not confirmed geometry; unknown vehicle attributes are left unknown and never inferred.",
    "Transfer levels are reused verbatim from Phase 23 and mean 'usable as a hypothesis', never "
    "'copy the source setup'.",
)


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class EngineeringPlaybook:
    schema_version: int
    programme_identity: dict
    generated_from: dict
    stable_themes: Tuple[dict, ...]
    investigation_priorities: Tuple[dict, ...]
    knowledge_boundaries: Tuple[dict, ...]
    new_programme_briefs: Tuple[dict, ...]
    global_stable_summary: dict
    evidence_coverage: dict
    limitations: Tuple[str, ...]
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = ENGINEERING_PLAYBOOK_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "programme_identity": dict(self.programme_identity),
                "generated_from": dict(self.generated_from),
                "stable_themes": [dict(t) for t in self.stable_themes],
                "investigation_priorities": [dict(p) for p in self.investigation_priorities],
                "knowledge_boundaries": [dict(b) for b in self.knowledge_boundaries],
                "new_programme_briefs": [dict(b) for b in self.new_programme_briefs],
                "global_stable_summary": dict(self.global_stable_summary),
                "evidence_coverage": dict(self.evidence_coverage),
                "limitations": list(self.limitations), "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_engineering_playbook(programme_knowledge: Optional[Mapping],
                               transfer_report: Optional[Mapping]) -> EngineeringPlaybook:
    """Assemble the cross-programme engineering playbook from the Phase-22 programme knowledge
    report + the Phase-23 transfer report. Deterministic; carries no setup values; never raises."""
    try:
        return _build(programme_knowledge or {}, transfer_report or {})
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return EngineeringPlaybook(
            schema_version=ENGINEERING_PLAYBOOK_SCHEMA, programme_identity={}, generated_from={},
            stable_themes=(), investigation_priorities=(), knowledge_boundaries=(),
            new_programme_briefs=(), global_stable_summary={}, evidence_coverage={},
            limitations=_LIMITATIONS, safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(programme: Mapping, transfer: Mapping) -> EngineeringPlaybook:
    graph = programme.get("knowledge_graph") or {}
    compatibility = programme.get("compatibility") or {}
    source_key = dict(compatibility.get("primary_key") or {})

    # index Phase-23 candidates by domain (transfer decisions reused verbatim).
    cands_by_domain: dict = {}
    for c in (transfer.get("candidates") or []):
        if isinstance(c, Mapping):
            cands_by_domain.setdefault(_lc(c.get("engineering_domain")), []).append(c)

    domain_records = _normalize_domains(graph, source_key, cands_by_domain)

    themes = _order_themes(build_stable_themes(domain_records, source_key))
    priorities = _order_priorities(classify_priorities(domain_records))
    boundaries = build_boundaries(domain_records)      # already deterministically ordered
    targets = [dict(g.get("compatibility_key") or {})
               for g in (compatibility.get("other_groups") or [])
               if isinstance(g, Mapping) and (g.get("compatibility_key") or {})]
    briefs = build_briefs(domain_records, source_key, targets, boundaries)

    summary = _global_summary(themes, priorities, targets)
    coverage = _evidence_coverage(graph, domain_records)
    kv = knowledge_versions()
    fp = _fp({
        "src": {k: _lc(source_key.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
        "themes": [(t["engineering_domain"], t["recurrence_count"], t["evidence_count"],
                    t["transfer_eligibility_summary"]["best_level"]) for t in themes],
        "priorities": [(p["domain"], p["category"], p["engineering_score"]) for p in priorities],
        "boundaries": [(b["boundary_type"], b["domain"], b["target_car"]) for b in boundaries],
        "briefs": [b["target_programme"].get("car") for b in briefs],
        "kv": kv,
    })
    return EngineeringPlaybook(
        schema_version=ENGINEERING_PLAYBOOK_SCHEMA,
        programme_identity={k: str(source_key.get(k, "") or "")
                            for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase22_fingerprint": _lc(programme.get("content_fingerprint")),
                        "phase23_fingerprint": _lc(transfer.get("content_fingerprint")),
                        "authorities": ["Phase 17 value", "Phase 18 campaigns",
                                        "Phase 19 saturation/cost", "Phase 20 confidence/ROI",
                                        "Phase 21 season report", "Phase 22 knowledge graph",
                                        "Phase 23 transfer eligibility"]},
        stable_themes=tuple(themes), investigation_priorities=tuple(priorities),
        knowledge_boundaries=tuple(boundaries), new_programme_briefs=tuple(briefs),
        global_stable_summary=summary, evidence_coverage=coverage, limitations=_LIMITATIONS,
        safety_statement=_SAFETY, content_fingerprint=fp, knowledge_versions=kv)


def _normalize_domains(graph: Mapping, source_key: dict, cands_by_domain: dict) -> List[dict]:
    records: List[dict] = []
    for d in (graph.get("domains") or []):
        if not isinstance(d, Mapping):
            continue
        domain = _lc(d.get("domain"))
        ev = d.get("supporting_evidence") or {}
        limits = [str(x) for x in (d.get("known_limitations") or [])]
        conflicting = any("conflict" in _lc(x) for x in limits)
        maturity = _lc((d.get("maturity") or {}).get("value"))
        confidence = _lc((d.get("confidence") or {}).get("value"))
        state = _lc((d.get("knowledge_state") or {}).get("value"))
        confirmations = _int(ev.get("confirmations"))
        established = maturity in _ESTABLISHED and bool(d.get("supporting_campaigns"))
        confirmed_good = (state in _CONFIRMED_STATES and confidence in _CONFIDENT
                          and confirmations >= 1 and not conflicting
                          and _int(ev.get("regressions")) == 0)
        transfers = [{"target": dict(c.get("target_context") or {}),
                      "transfer_level": _lc(c.get("transfer_level")),
                      "reason": c.get("reason"),
                      "limitations": list(c.get("limitations") or []),
                      "rules_satisfied": list(c.get("rules_satisfied") or []),
                      "domain_transfer_class": _lc((c.get("supporting_evidence") or {})
                                                   .get("domain_transfer_class"))}
                     for c in cands_by_domain.get(domain, []) if isinstance(c, Mapping)]
        records.append({
            "domain": domain, "mechanisms": [_lc(m) for m in (d.get("supporting_mechanisms") or [])],
            "maturity": maturity, "confidence": confidence, "knowledge_state": state,
            "remaining_uncertainty": _lc((d.get("remaining_uncertainty") or {}).get("value")),
            "confirmations": confirmations, "regressions": _int(ev.get("regressions")),
            "executed": _int(ev.get("executed")), "conflicting": conflicting,
            "supporting_campaigns": list(d.get("supporting_campaigns") or []),
            "known_limitations": limits, "established": established,
            "confirmed_good": confirmed_good,
            "domain_transfer_class": domain_transfer_class(domain),
            "source_programme": dict(source_key), "transfers": transfers,
        })
    return records


def _order_themes(themes) -> List[dict]:
    def key(t):
        return (-_int(t.get("recurrence_count")), -_int(t.get("evidence_count")),
                -_MATURITY_RANK.get(_lc(t.get("maturity_summary")), 0),
                -_CONFIDENCE_RANK.get(_lc(t.get("confidence_summary")), 0),
                _DOMAIN_ORDER.index(_lc(t.get("engineering_domain")))
                if _lc(t.get("engineering_domain")) in _DOMAIN_ORDER else 99,
                str(t.get("theme_id")))
    return sorted([t for t in themes if isinstance(t, Mapping)], key=key)


def _order_priorities(priorities) -> List[dict]:
    def key(p):
        return (CATEGORY_PRIORITY.get(_lc(p.get("category")), 99),
                -float(p.get("engineering_score") or 0),
                _DOMAIN_ORDER.index(_lc(p.get("domain")))
                if _lc(p.get("domain")) in _DOMAIN_ORDER else 99,
                _lc(p.get("domain")))
    return sorted([p for p in priorities if isinstance(p, Mapping)], key=key)


def _global_summary(themes, priorities, targets) -> dict:
    cat_counts: dict = {}
    for p in priorities:
        cat_counts[p.get("category")] = cat_counts.get(p.get("category"), 0) + 1
    return {"stable_themes": len(themes),
            "themes_reusable_across_programmes": sum(
                1 for t in themes if t.get("compatible_target_programmes")),
            "confirmed_good_themes": sum(1 for t in themes if t.get("confirmed_good_protections")),
            "themes_with_negative_history": sum(1 for t in themes
                                                if t.get("known_negative_outcomes")),
            "target_programmes": len(targets),
            "priority_category_counts": cat_counts}


def _evidence_coverage(graph: Mapping, records: List[dict]) -> dict:
    return {"known_domains": len(graph.get("known_domains") or []),
            "missing_domains": len(graph.get("missing_domains") or []),
            "established_domains": sum(1 for r in records if r.get("established")),
            "total_confirmations": sum(_int(r.get("confirmations")) for r in records),
            "total_regressions": sum(_int(r.get("regressions")) for r in records),
            "domains_with_conflict": sum(1 for r in records if r.get("conflicting")),
            "source": "Phase 22 knowledge graph"}


def knowledge_versions() -> dict:
    return {"engineering_playbook": ENGINEERING_PLAYBOOK_VERSION,
            "stable_themes": STABLE_THEMES_VERSION,
            "investigation_priority": INVESTIGATION_PRIORITY_VERSION,
            "knowledge_boundary": KNOWLEDGE_BOUNDARY_VERSION,
            "new_programme_brief": NEW_PROGRAMME_BRIEF_VERSION,
            "knowledge_graph": ENGINEERING_KNOWLEDGE_GRAPH_VERSION,
            "schema": ENGINEERING_PLAYBOOK_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{ENGINEERING_PLAYBOOK_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
