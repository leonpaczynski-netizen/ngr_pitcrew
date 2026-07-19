"""Context-Safe Knowledge Activation — Layer 2 of the Race-Engineer Activation (Program 2, Phase 36).

Classifies the programme's recorded evidence relative to the CURRENT canonical context, so no
current-context conclusion is ever driven by incompatible evidence. Every evidence item is placed in
exactly one of five classes, each with an explicit reason:

  * ``EXACT_CONTEXT``           - same driver+car+track+layout+discipline+compound+version. Priority.
  * ``EXPLICITLY_TRANSFERABLE`` - a different-but-compatible context that the Phase-23 transfer
                                  authority licenses (with lower confidence and visible limitations).
  * ``REFERENCE_ONLY``          - related, but transfer is too weak to drive a recommendation.
  * ``EXCLUDED``                - a different programme / non-transferable knowledge; must NOT drive a
                                  current-context recommendation.
  * ``UNVERIFIABLE``            - not enough identity to classify.

Transferable evidence may enter ONLY through the canonical Phase-23 ``evaluate_transfer`` authority -
same driver or same car ALONE is never sufficient. Track-, gearbox- and event-specific knowledge does
not transfer across tracks (the transfer authority already encodes this), so other-track evidence
cannot silently shape a track-specific window.

Required invariant (Phase 36): no current-context engineering conclusion may be driven by incompatible
evidence without an explicit transfer decision and a visible limitation.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value; decides NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.engineering_context_scope import (
    EngineeringContextScope, ContextRelation, relate_context, build_engineering_context_scope,
    ENGINEERING_CONTEXT_SCOPE_VERSION,
)

CONTEXTUAL_KNOWLEDGE_ACTIVATION_VERSION = "contextual_knowledge_activation_v1"
CONTEXTUAL_KNOWLEDGE_ACTIVATION_SCHEMA = 1

_INVARIANT = ("No current-context engineering conclusion may be driven by incompatible evidence "
              "without an explicit transfer decision and a visible limitation. Transferable evidence "
              "enters only through the Phase-23 transfer authority; same driver or same car alone is "
              "never sufficient.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{CONTEXTUAL_KNOWLEDGE_ACTIVATION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class EvidenceClass(str, Enum):
    EXACT_CONTEXT = "exact_context"
    EXPLICITLY_TRANSFERABLE = "explicitly_transferable"
    REFERENCE_ONLY = "reference_only"
    EXCLUDED = "excluded"
    UNVERIFIABLE = "unverifiable"


# canonical presentation order (semantic, fingerprint-material where a list is ordered).
_CLASS_ORDER = (EvidenceClass.EXACT_CONTEXT, EvidenceClass.EXPLICITLY_TRANSFERABLE,
                EvidenceClass.REFERENCE_ONLY, EvidenceClass.EXCLUDED, EvidenceClass.UNVERIFIABLE)

# Phase-23 transfer-level rank -> how strongly it licenses inclusion.
_LEVEL_RANK = {"not_transferable": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4,
               "supported": 5}

# GT7 setup field / subsystem -> canonical Phase-22/23 engineering domain (for transfer eval).
_FIELD_DOMAIN = {
    "ride_height": "ride_height", "ride_height_front": "ride_height",
    "ride_height_rear": "ride_height",
    "natural_frequency": "springs", "natural_frequency_front": "springs",
    "natural_frequency_rear": "springs", "spring_rate": "springs", "spring": "springs",
    "anti_roll_bar": "anti_roll_bars", "anti_roll_bar_front": "anti_roll_bars",
    "anti_roll_bar_rear": "anti_roll_bars", "arb": "anti_roll_bars", "arb_front": "anti_roll_bars",
    "arb_rear": "anti_roll_bars",
    "compression_damping": "dampers", "rebound_damping": "dampers",
    "compression": "dampers", "rebound": "dampers", "damper": "dampers", "damping": "dampers",
    "camber": "alignment", "camber_front": "alignment", "camber_rear": "alignment",
    "toe": "alignment", "toe_front": "alignment", "toe_rear": "alignment",
    "lsd_initial": "differential", "lsd_acceleration": "differential", "lsd_braking": "differential",
    "lsd": "differential", "differential": "differential", "initial_torque": "differential",
    "downforce": "aerodynamics", "downforce_front": "aerodynamics",
    "downforce_rear": "aerodynamics", "wing": "aerodynamics", "aero": "aerodynamics",
    "brake_balance": "brake_balance", "brake_bias": "brake_balance",
    "ballast": "weight_transfer", "ballast_position": "weight_transfer",
    "weight_distribution": "weight_transfer",
    "final_drive": "gearbox", "gear_ratio": "gearbox", "gearbox": "gearbox", "gearing": "gearbox",
    "gear": "gearbox",
    "tyre": "tyres", "tyre_compound": "tyres", "compound": "tyres",
    "fuel": "fuel",
}

# residual/issue family -> domain (secondary evidence of an implicated domain).
_FAMILY_DOMAIN = {
    "understeer": "vehicle_balance", "oversteer": "vehicle_balance", "balance": "vehicle_balance",
    "traction": "weight_transfer", "wheelspin": "differential", "braking": "brake_balance",
    "stability": "vehicle_balance", "gearing": "gearbox", "drive_out": "gearbox",
    "technique": "driver_technique",
}


def _domain_for_field(field: str) -> str:
    f = _lc(field)
    if f in _FIELD_DOMAIN:
        return _FIELD_DOMAIN[f]
    for key, dom in _FIELD_DOMAIN.items():
        if key and key in f:
            return dom
    return ""


def _record_domains(record: Mapping) -> Tuple[str, ...]:
    doms = []
    for c in (record.get("changes") or []):
        d = _domain_for_field(_norm(c.get("field")) or _norm(c.get("subsystem")))
        if d:
            doms.append(d)
    for r in (record.get("residual_states") or []):
        fam = _lc(r.get("family")) or _lc(r.get("issue_type"))
        if fam in _FAMILY_DOMAIN:
            doms.append(_FAMILY_DOMAIN[fam])
    # de-dup preserving deterministic (sorted) order
    return tuple(sorted(set(doms)))


def _corner_tags(record: Mapping) -> Tuple[str, ...]:
    out = []
    for r in (record.get("residual_states") or []):
        tag = _norm(r.get("corner_name")) or _norm(r.get("segment_id"))
        if tag:
            out.append(tag)
    return tuple(sorted(set(out)))


@dataclass(frozen=True)
class EvidenceClassification:
    record_key: str
    context: dict
    relation: str
    classification: str
    reason: str
    outcome_status: str
    confidence_level: str
    fields: Tuple[str, ...]
    domains: Tuple[str, ...]
    corner_tags: Tuple[str, ...]
    transfer_level: str
    limitations: Tuple[str, ...]
    recorded_at: str
    session_date: str
    experiment_id: str

    def to_dict(self) -> dict:
        return {"record_key": self.record_key, "context": dict(self.context),
                "relation": self.relation, "classification": self.classification,
                "reason": self.reason, "outcome_status": self.outcome_status,
                "confidence_level": self.confidence_level, "fields": list(self.fields),
                "domains": list(self.domains), "corner_tags": list(self.corner_tags),
                "transfer_level": self.transfer_level, "limitations": list(self.limitations),
                "recorded_at": self.recorded_at, "session_date": self.session_date,
                "experiment_id": self.experiment_id}


@dataclass(frozen=True)
class ContextActivation:
    scope: dict
    completeness: str
    items: Tuple[dict, ...]
    counts: dict
    contamination_guard: Tuple[str, ...]
    invariant_statement: str
    content_fingerprint: str
    schema_version: int = CONTEXTUAL_KNOWLEDGE_ACTIVATION_SCHEMA
    eval_version: str = CONTEXTUAL_KNOWLEDGE_ACTIVATION_VERSION

    def to_dict(self) -> dict:
        return {"scope": dict(self.scope), "completeness": self.completeness,
                "items": [dict(i) for i in self.items], "counts": dict(self.counts),
                "contamination_guard": list(self.contamination_guard),
                "invariant_statement": self.invariant_statement,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}

    def keys_for(self, cls: str) -> Tuple[str, ...]:
        return tuple(i["record_key"] for i in self.items if i["classification"] == cls)


def _best_transfer(scope: EngineeringContextScope, record: Mapping,
                   domains: Sequence[str]) -> Tuple[int, str, Tuple[str, ...]]:
    """Return (best_rank, best_level, limitations) evaluating transfer of the record's implicated
    domains from the record's context INTO the current scope, via the canonical Phase-23 authority."""
    try:
        from strategy.knowledge_transfer import evaluate_transfer
    except Exception:  # pragma: no cover - defensive
        return 0, "not_transferable", ()
    src_ctx = dict(record.get("context") or {})
    tgt_ctx = {"car": scope.car, "track": scope.track, "layout_id": scope.layout_id,
               "driver": scope.driver, "discipline": scope.discipline.value,
               "gt7_version": scope.gt7_version, "compound": scope.compound}
    conf = _lc(record.get("confidence_level")) or "medium"
    best_rank, best_level, best_lims = -1, "not_transferable", ()
    for dom in (domains or ["vehicle_balance"]):
        source_domain = {"domain": dom, "maturity": {"value": "established"},
                         "confidence": {"value": conf},
                         "supporting_mechanisms": [dom], "supporting_campaigns": ["recorded_evidence"]}
        cand = evaluate_transfer(source_domain, src_ctx, tgt_ctx)
        rank = _LEVEL_RANK.get(_lc(cand.transfer_level), 0)
        if rank > best_rank:
            best_rank, best_level, best_lims = rank, _lc(cand.transfer_level), tuple(cand.limitations)
    return max(best_rank, 0), best_level, best_lims


def _classify_record(scope: EngineeringContextScope, record: Mapping) -> EvidenceClassification:
    ctx = dict(record.get("context") or {})
    domains = _record_domains(record)
    fields = tuple(sorted({_norm(c.get("field")) for c in (record.get("changes") or [])
                           if _norm(c.get("field"))}))
    relation = relate_context(scope, ctx)
    base = dict(record_key=_norm(record.get("record_key")), context=ctx, relation=relation.value,
                outcome_status=_norm(record.get("outcome_status")),
                confidence_level=_norm(record.get("confidence_level")), fields=fields,
                domains=domains, corner_tags=_corner_tags(record),
                recorded_at=_norm(record.get("recorded_at")),
                session_date=_norm(record.get("session_date")),
                experiment_id=_norm(record.get("experiment_id")))

    if relation is ContextRelation.UNVERIFIABLE:
        return EvidenceClassification(classification=EvidenceClass.UNVERIFIABLE.value,
                                      reason="insufficient context identity to classify this evidence "
                                             "against the current programme.",
                                      transfer_level="", limitations=(), **base)
    if relation is ContextRelation.EXACT:
        return EvidenceClassification(classification=EvidenceClass.EXACT_CONTEXT.value,
                                      reason="exact-context evidence: same driver, car, track, "
                                             "layout, discipline, compound and version.",
                                      transfer_level="exact", limitations=(), **base)
    if relation is ContextRelation.UNRELATED:
        return EvidenceClassification(classification=EvidenceClass.EXCLUDED.value,
                                      reason="different programme (unrelated context); excluded from "
                                             "driving any current-context recommendation.",
                                      transfer_level="not_transferable", limitations=(), **base)

    # related-but-different: the ONLY route in is the canonical transfer authority.
    rank, level, lims = _best_transfer(scope, record, domains)
    rel_note = {ContextRelation.SAME_CAR_OTHER_TRACK: "same car, different track",
                ContextRelation.SAME_PROGRAMME_OTHER_DISCIPLINE: "same programme, different discipline",
                ContextRelation.SAME_DRIVER_OTHER_CAR: "same driver, different car",
                ContextRelation.DIFFERENT_VERSION: "different GT7 version"}.get(relation, "different context")
    if rank >= _LEVEL_RANK["medium"]:
        cls = EvidenceClass.EXPLICITLY_TRANSFERABLE
        reason = (f"{rel_note}; Phase-23 transfer licenses this knowledge at level '{level}' with "
                  f"lower confidence and visible limitations.")
    elif rank >= _LEVEL_RANK["very_low"]:
        cls = EvidenceClass.REFERENCE_ONLY
        reason = (f"{rel_note}; Phase-23 transfer is weak (level '{level}') - reference only, it does "
                  f"not drive a current-context recommendation.")
    else:
        cls = EvidenceClass.EXCLUDED
        reason = (f"{rel_note}; Phase-23 transfer is not licensed (level '{level}') - excluded from "
                  f"driving any current-context recommendation.")
    return EvidenceClassification(classification=cls.value, reason=reason,
                                  transfer_level=level, limitations=lims, **base)


def activate_context_knowledge(scope, records: Optional[Sequence[Mapping]]) -> ContextActivation:
    """Classify each development record against the current scope. ``scope`` may be an
    ``EngineeringContextScope`` or a context mapping. Deterministic; order-independent; never raises."""
    try:
        sc = scope if isinstance(scope, EngineeringContextScope) else build_engineering_context_scope(
            scope if isinstance(scope, Mapping) else {})
        recs = [r for r in (records or []) if isinstance(r, Mapping)]
        classified = [_classify_record(sc, r) for r in recs]
        # deterministic canonical order: by class order, then recorded_at, then record_key.
        order_index = {c.value: i for i, c in enumerate(_CLASS_ORDER)}
        classified.sort(key=lambda e: (order_index.get(e.classification, 99), e.recorded_at,
                                       e.record_key))
        counts = {c.value: 0 for c in _CLASS_ORDER}
        for e in classified:
            counts[e.classification] = counts.get(e.classification, 0) + 1
        guard: List[str] = []
        for e in classified:
            if e.classification in (EvidenceClass.EXCLUDED.value, EvidenceClass.REFERENCE_ONLY.value):
                trk = _norm(e.context.get("track")) or "unknown track"
                guard.append(f"{e.classification}: {trk} / {', '.join(e.domains) or 'no-domain'} - "
                             f"{e.reason}")
        items = tuple(e.to_dict() for e in classified)
        fp = _fp({"scope": sc.context_fingerprint(),
                  "items": [(i["record_key"], i["classification"], i["transfer_level"]) for i in items],
                  "counts": counts})
        return ContextActivation(scope=sc.to_dict(), completeness=sc.completeness().value,
                                 items=items, counts=counts, contamination_guard=tuple(guard),
                                 invariant_statement=_INVARIANT, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return ContextActivation(scope={}, completeness="insufficient", items=(), counts={},
                                 contamination_guard=(), invariant_statement=_INVARIANT,
                                 content_fingerprint=_fp({"error": True}))


def activation_versions() -> dict:
    return {"contextual_knowledge_activation": CONTEXTUAL_KNOWLEDGE_ACTIVATION_VERSION,
            "engineering_context_scope": ENGINEERING_CONTEXT_SCOPE_VERSION,
            "schema": CONTEXTUAL_KNOWLEDGE_ACTIVATION_SCHEMA}
