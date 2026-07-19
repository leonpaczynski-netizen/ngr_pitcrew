"""Programme Engineering Assumption Register — pure orchestration (Program 2, Phase 30).

Assembles the read-only register of the assumptions the programme's engineering knowledge relies on.
It joins the Phase-25 convergence, Phase-26 re-validation, Phase-27 coverage and Phase-29
contradiction authorities to surface per-domain assumptions, and reads the Phase-24 playbook
boundaries for programme-level assumptions (unknown vehicle attributes, unverified proxies). It lists
only assumptions - never facts - and records that an assumption can only CAP readiness, never create
it.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.engineering_knowledge_graph import KnowledgeDomain
from strategy.assumption_classification import (
    ASSUMPTION_CLASSIFICATION_VERSION, ASSUMPTION_STATUS_PRIORITY, AssumptionType, AssumptionStatus,
    type_text,
)
from strategy.assumption_impact import (
    ASSUMPTION_IMPACT_VERSION, ASSUMPTION_IMPACT_PRIORITY, AssumptionImpact, impact_text,
    readiness_cap,
)
from strategy.engineering_assumption import (
    ENGINEERING_ASSUMPTION_VERSION, derive_domain_assumptions,
)

PROGRAMME_ASSUMPTION_REGISTER_VERSION = "programme_assumption_register_v1"
PROGRAMME_ASSUMPTION_REGISTER_SCHEMA = 1

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]

_NO_ACTION = ("Assumption register only. It makes explicit what the current knowledge relies on but "
              "has not established - facts are not listed as assumptions. An assumption can only CAP "
              "how ready knowledge may be (never raise it), and a conservative bound is labelled as "
              "such. It carries no setup values and recommends / schedules / applies / mutates "
              "NOTHING. Completion stays governed by Phase 18 and the frozen Apply gate remains the "
              "sole route to the car.")

# Phase-24 boundary types that ARE programme-level assumptions, and the assumption they map to.
_BOUNDARY_ASSUMPTION = {
    "unknown_vehicle_attribute": AssumptionType.UNKNOWN_VEHICLE_ATTRIBUTE_ASSUMED,
    "unverified_transfer_proxy": AssumptionType.UNVERIFIED_PROXY_ASSUMED,
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ProgrammeAssumptionRegister:
    schema_version: int
    source_programme: dict
    generated_from: dict
    assumptions: Tuple[dict, ...]
    blocking: Tuple[dict, ...]
    capping: Tuple[dict, ...]
    narrowing_or_weakening: Tuple[dict, ...]
    informational: Tuple[dict, ...]
    conservative_bounds: Tuple[dict, ...]
    totals: dict
    readiness_cap_note: str
    empty_state: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = PROGRAMME_ASSUMPTION_REGISTER_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from),
                "assumptions": [dict(a) for a in self.assumptions],
                "blocking": [dict(a) for a in self.blocking],
                "capping": [dict(a) for a in self.capping],
                "narrowing_or_weakening": [dict(a) for a in self.narrowing_or_weakening],
                "informational": [dict(a) for a in self.informational],
                "conservative_bounds": [dict(a) for a in self.conservative_bounds],
                "totals": dict(self.totals), "readiness_cap_note": self.readiness_cap_note,
                "empty_state": self.empty_state, "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_programme_assumption_register(
        timeline: Optional[Mapping], revalidation: Optional[Mapping], coverage: Optional[Mapping],
        contradiction: Optional[Mapping], playbook: Optional[Mapping]
) -> ProgrammeAssumptionRegister:
    """Assemble the assumption register. Deterministic; never raises."""
    try:
        return _build(timeline or {}, revalidation or {}, coverage or {}, contradiction or {},
                      playbook or {})
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeAssumptionRegister(
            schema_version=PROGRAMME_ASSUMPTION_REGISTER_SCHEMA, source_programme={},
            generated_from={}, assumptions=(), blocking=(), capping=(), narrowing_or_weakening=(),
            informational=(), conservative_bounds=(), totals={},
            readiness_cap_note="An assumption can only cap readiness, never create it.",
            empty_state="Assumption register unavailable.", safety_statement=_NO_ACTION,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}), knowledge_versions=kv)


def _build(timeline: Mapping, revalidation: Mapping, coverage: Mapping, contradiction: Mapping,
           playbook: Mapping) -> ProgrammeAssumptionRegister:
    source = dict(timeline.get("source_programme") or {})
    reval_by = {_lc(i.get("domain")): i for i in (revalidation.get("items") or [])
                if isinstance(i, Mapping)}
    cov_by = {_lc(c.get("domain")): c for c in (coverage.get("domain_coverage") or [])
              if isinstance(c, Mapping)}
    contra_by = {_lc(c.get("domain")): c for c in (contradiction.get("contradictions") or [])
                 if isinstance(c, Mapping)}

    assumptions: List[dict] = []
    for c in (timeline.get("convergence_summaries") or []):
        if not isinstance(c, Mapping):
            continue
        dom = _lc(c.get("domain"))
        assumptions.extend(derive_domain_assumptions(dom, c, reval_by.get(dom, {}),
                                                     cov_by.get(dom, {}), contra_by.get(dom, {})))

    # programme-level assumptions from the Phase-24 knowledge boundaries.
    seen_boundary = set()
    for b in (playbook.get("knowledge_boundaries") or []):
        if not isinstance(b, Mapping):
            continue
        bt = _lc(b.get("boundary_type"))
        atype = _BOUNDARY_ASSUMPTION.get(bt)
        if not atype:
            continue
        dom = _lc(b.get("domain"))
        key = (bt, dom, _lc(b.get("target_car")))
        if key in seen_boundary:
            continue
        seen_boundary.add(key)
        impact = (AssumptionImpact.BLOCKS_RELIANCE if atype == AssumptionType.UNVERIFIED_PROXY_ASSUMED
                  else AssumptionImpact.CAPS_READINESS)
        assumptions.append({
            "domain": dom or "programme", "assumption_type": atype.value,
            "status": AssumptionStatus.EXPLICIT_AND_LABELLED.value, "impact": impact.value,
            "readiness_cap": readiness_cap(impact.value), "is_conservative_bound": True,
            "rationale": f"{type_text(atype.value)}; {impact_text(impact.value)}. "
                         f"{b.get('reason') or ''}".strip(),
            "what_would_resolve": "recording the real attribute / verifying the proxy directly",
            "no_action_statement": _NO_ACTION})

    assumptions.sort(key=_order)

    def bucket(*impacts):
        return tuple(a for a in assumptions if a["impact"] in impacts)

    blocking = bucket("blocks_reliance")
    capping = bucket("caps_readiness")
    narrow_weak = bucket("narrows_scope", "weakens_confidence")
    info = bucket("informational", "unknown")
    conservative = tuple(a for a in assumptions if a.get("is_conservative_bound"))

    totals = {"assumptions": len(assumptions), "blocking": len(blocking), "capping": len(capping),
              "narrowing_or_weakening": len(narrow_weak), "informational": len(info),
              "conservative_bounds": len(conservative),
              "at_risk_or_contradicted": sum(1 for a in assumptions
                                             if _lc(a.get("status")) in ("at_risk", "contradicted")),
              "domains_with_assumptions": len({a["domain"] for a in assumptions})}

    kv = knowledge_versions()
    fp = _fp({"src": {k: _lc(source.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
              "a": [(a["domain"], a["assumption_type"], a["status"], a["impact"]) for a in
                    assumptions], "kv": kv})
    empty = "" if assumptions else ("No engineering assumptions to register - the established "
                                    "knowledge is directly evidenced, or there is not yet enough "
                                    "knowledge to rely on any assumption.")
    note = ("An assumption can only CAP how ready knowledge may be, never create readiness; a "
            "conservative bound is labelled and is a deliberate caution, not a defect.")
    return ProgrammeAssumptionRegister(
        schema_version=PROGRAMME_ASSUMPTION_REGISTER_SCHEMA,
        source_programme={k: str(source.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase25_fingerprint": _lc(timeline.get("content_fingerprint")),
                        "phase26_fingerprint": _lc(revalidation.get("content_fingerprint")),
                        "phase27_fingerprint": _lc(coverage.get("content_fingerprint")),
                        "phase29_fingerprint": _lc(contradiction.get("content_fingerprint")),
                        "authorities": ["Phase 24 playbook boundaries", "Phase 25 convergence",
                                        "Phase 26 re-validation", "Phase 27 coverage",
                                        "Phase 29 contradiction"]},
        assumptions=tuple(assumptions), blocking=blocking, capping=capping,
        narrowing_or_weakening=narrow_weak, informational=info, conservative_bounds=conservative,
        totals=totals, readiness_cap_note=note, empty_state=empty, safety_statement=_NO_ACTION,
        content_fingerprint=fp, knowledge_versions=kv)


def _order(a: Mapping):
    return (ASSUMPTION_IMPACT_PRIORITY.get(_lc(a.get("impact")), 99),
            ASSUMPTION_STATUS_PRIORITY.get(_lc(a.get("status")), 99),
            _DOMAIN_ORDER.index(_lc(a.get("domain"))) if _lc(a.get("domain")) in _DOMAIN_ORDER
            else 99, _lc(a.get("domain")), _lc(a.get("assumption_type")))


def knowledge_versions() -> dict:
    return {"programme_assumption_register": PROGRAMME_ASSUMPTION_REGISTER_VERSION,
            "engineering_assumption": ENGINEERING_ASSUMPTION_VERSION,
            "assumption_classification": ASSUMPTION_CLASSIFICATION_VERSION,
            "assumption_impact": ASSUMPTION_IMPACT_VERSION,
            "schema": PROGRAMME_ASSUMPTION_REGISTER_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_ASSUMPTION_REGISTER_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
