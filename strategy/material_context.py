"""Material Context Trust & Legacy Evidence (Program 2, Phase 42).

Determines, per material context field and per knowledge domain, how much a piece of evidence can be
trusted for the CURRENT context. The governing doctrine:

    Unknown never proves a DIFFERENCE, and unknown never proves exact EQUIVALENCE.

A field is `KNOWN_MATCH` only when both sides are known and equal. Missing material fields CAP or BLOCK
exact-context use for the conclusions that depend on them (never silently treated as a match). Evidence
enters exact-context maturity / convergence / working windows / promotion / confirmed direction /
best-known selection only when every field required by that conclusion's domain is `KNOWN_MATCH`.

Legacy records (which lack the event-condition material fields) stay VISIBLE with explicit limitations;
they are never discarded for missing new fields and never upgraded by assumption.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value; fabricates NO context.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

MATERIAL_CONTEXT_VERSION = "material_context_v1"
MATERIAL_CONTEXT_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return f"{MATERIAL_CONTEXT_VERSION}:" + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24]


class ContextFieldTrust(str, Enum):
    KNOWN_MATCH = "known_match"
    KNOWN_DIFFERENT = "known_different"
    UNKNOWN_CURRENT = "unknown_current"
    UNKNOWN_HISTORICAL = "unknown_historical"
    UNKNOWN_BOTH = "unknown_both"
    NOT_APPLICABLE = "not_applicable"
    INFERRED_WITH_LIMITATIONS = "inferred_with_limitations"


class ContextTrust(str, Enum):
    EXACT_VERIFIED = "exact_verified"
    EQUIVALENT_VERIFIED = "equivalent_verified"
    PARTIAL_CONTEXT = "partial_context"
    TRANSFER_ONLY = "transfer_only"
    REFERENCE_ONLY = "reference_only"
    INCOMPATIBLE = "incompatible"
    UNVERIFIABLE = "unverifiable"


class KnowledgeDomain(str, Enum):
    SETUP_WORKING_WINDOWS = "setup_working_windows"
    TYRE_DEGRADATION = "tyre_degradation"
    FUEL_USE = "fuel_use"
    GEARING_AERO = "gearing_aero"
    DRIVER_TECHNIQUE = "driver_technique"
    VEHICLE_DYNAMICS = "vehicle_dynamics"


# field -> class (drives how a KNOWN_DIFFERENT is treated).
_IDENTITY = {"driver", "car", "car_variant", "discipline", "gt7_version"}
_TRACK = {"track", "layout_id", "track_direction"}
_EVENT_CONDITION = {"compound", "compound_policy", "bop_state", "tuning_permitted", "power_restriction",
                    "weight_restriction", "tyre_multiplier", "fuel_multiplier", "refuel_rate",
                    "race_objective", "weather", "grip_state"}
_ADMINISTRATIVE = {"event_id"}

# the full material field list (order is canonical for display / fingerprint).
MATERIAL_FIELDS: Tuple[str, ...] = (
    "driver", "car", "car_variant", "track", "layout_id", "track_direction", "discipline",
    "compound", "compound_policy", "bop_state", "tuning_permitted", "power_restriction",
    "weight_restriction", "tyre_multiplier", "fuel_multiplier", "refuel_rate", "race_objective",
    "weather", "grip_state", "gt7_version", "rule_engine_version", "data_schema_version",
    "applied_setup_id", "setup_fingerprint", "session_purpose", "event_id")

# knowledge domain -> the material fields REQUIRED for an exact conclusion in that domain.
DOMAIN_REQUIRED: Dict[str, Tuple[str, ...]] = {
    KnowledgeDomain.SETUP_WORKING_WINDOWS.value: (
        "driver", "car", "car_variant", "track", "layout_id", "discipline", "tuning_permitted",
        "bop_state", "power_restriction", "weight_restriction", "gt7_version", "applied_setup_id"),
    KnowledgeDomain.TYRE_DEGRADATION.value: (
        "car", "track", "layout_id", "compound", "tyre_multiplier", "discipline"),
    KnowledgeDomain.FUEL_USE.value: (
        "car", "track", "layout_id", "fuel_multiplier", "race_objective"),
    KnowledgeDomain.GEARING_AERO.value: (
        "car", "track", "layout_id", "bop_state", "power_restriction", "weight_restriction",
        "discipline", "gt7_version"),
    KnowledgeDomain.DRIVER_TECHNIQUE.value: ("driver", "car", "track"),
    KnowledgeDomain.VEHICLE_DYNAMICS.value: ("car", "gt7_version"),
}


def field_trust(current_val, evidence_val, *, applicable: bool = True,
                inferred: bool = False) -> ContextFieldTrust:
    """Per-field trust. Unknown proves neither a match nor a difference. Deterministic."""
    if not applicable:
        return ContextFieldTrust.NOT_APPLICABLE
    if inferred:
        return ContextFieldTrust.INFERRED_WITH_LIMITATIONS
    c, e = _lc(current_val), _lc(evidence_val)
    if c and e:
        return ContextFieldTrust.KNOWN_MATCH if c == e else ContextFieldTrust.KNOWN_DIFFERENT
    if not c and e:
        return ContextFieldTrust.UNKNOWN_CURRENT
    if c and not e:
        return ContextFieldTrust.UNKNOWN_HISTORICAL
    return ContextFieldTrust.UNKNOWN_BOTH


_UNKNOWN_STATES = {ContextFieldTrust.UNKNOWN_CURRENT, ContextFieldTrust.UNKNOWN_HISTORICAL,
                   ContextFieldTrust.UNKNOWN_BOTH, ContextFieldTrust.INFERRED_WITH_LIMITATIONS}


@dataclass(frozen=True)
class FieldTrust:
    field: str
    field_class: str
    trust: str
    current_known: bool
    evidence_known: bool
    required: bool

    def to_dict(self) -> dict:
        return {"field": self.field, "field_class": self.field_class, "trust": self.trust,
                "current_known": self.current_known, "evidence_known": self.evidence_known,
                "required": self.required}


@dataclass(frozen=True)
class MaterialContextTrust:
    domain: str
    overall_trust: str
    exact_eligible: bool
    field_trust: Tuple[dict, ...]
    limiting_fields: Tuple[dict, ...]
    limitation_explanation: str
    context_snapshot: dict
    doctrine: str
    content_fingerprint: str
    schema_version: int = MATERIAL_CONTEXT_SCHEMA
    eval_version: str = MATERIAL_CONTEXT_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "overall_trust": self.overall_trust,
                "exact_eligible": self.exact_eligible,
                "field_trust": [dict(f) for f in self.field_trust],
                "limiting_fields": [dict(f) for f in self.limiting_fields],
                "limitation_explanation": self.limitation_explanation,
                "context_snapshot": dict(self.context_snapshot), "doctrine": self.doctrine,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_DOCTRINE = ("Unknown never proves a difference and never proves exact equivalence. Exact-context use "
             "requires every field a domain needs to be a known match; a missing required field caps "
             "the trust to partial. Legacy evidence stays visible with explicit limitations and is "
             "never upgraded by assumption.")


def _field_class(field: str) -> str:
    if field in _IDENTITY:
        return "identity_critical"
    if field in _TRACK:
        return "track_critical"
    if field in _EVENT_CONDITION:
        return "event_condition"
    if field in _ADMINISTRATIVE:
        return "administrative"
    return "version_or_setup"


def build_material_context_trust(current: Optional[Mapping], evidence: Optional[Mapping],
                                 domain: str, *, inferred_fields: Optional[Sequence[str]] = None
                                 ) -> MaterialContextTrust:
    """Assess how much ``evidence`` can be trusted for ``domain`` in the ``current`` context. Both are
    material-field mappings. Deterministic; never raises."""
    try:
        cur = current if isinstance(current, Mapping) else {}
        ev = evidence if isinstance(evidence, Mapping) else {}
        dom = _lc(domain)
        required = set(DOMAIN_REQUIRED.get(dom, ()))
        inferred = {_lc(f) for f in (inferred_fields or [])}

        fields: List[FieldTrust] = []
        for f in MATERIAL_FIELDS:
            applicable = f in required or f in _IDENTITY or f in _TRACK or f == "event_id"
            t = field_trust(cur.get(f), ev.get(f), applicable=applicable, inferred=f in inferred)
            fields.append(FieldTrust(field=f, field_class=_field_class(f), trust=t.value,
                                     current_known=bool(_lc(cur.get(f))),
                                     evidence_known=bool(_lc(ev.get(f))), required=f in required))

        # cannot even compare without car/track identity
        if not (_lc(cur.get("car")) and _lc(ev.get("car"))) and not (_lc(cur.get("track"))
                                                                     and _lc(ev.get("track"))):
            overall = ContextTrust.UNVERIFIABLE
        else:
            req_states = {f.field: ContextFieldTrust(f.trust) for f in fields if f.required}
            id_diff = any(_field_class(k) == "identity_critical"
                          and v is ContextFieldTrust.KNOWN_DIFFERENT for k, v in req_states.items())
            track_diff = any(_field_class(k) == "track_critical"
                             and v is ContextFieldTrust.KNOWN_DIFFERENT for k, v in req_states.items())
            cond_diff = any(_field_class(k) == "event_condition"
                            and v is ContextFieldTrust.KNOWN_DIFFERENT for k, v in req_states.items())
            unknown_required = any(v in _UNKNOWN_STATES for v in req_states.values())
            all_match = all(v is ContextFieldTrust.KNOWN_MATCH for v in req_states.values()) \
                and bool(req_states)
            event_id_diff = ContextFieldTrust(next((f.trust for f in fields if f.field == "event_id"),
                                                   ContextFieldTrust.UNKNOWN_BOTH.value)) \
                is ContextFieldTrust.KNOWN_DIFFERENT

            if id_diff:
                overall = ContextTrust.INCOMPATIBLE
            elif track_diff:
                overall = ContextTrust.TRANSFER_ONLY
            elif cond_diff:
                overall = ContextTrust.REFERENCE_ONLY
            elif all_match:
                overall = ContextTrust.EQUIVALENT_VERIFIED if event_id_diff \
                    else ContextTrust.EXACT_VERIFIED
            elif unknown_required:
                overall = ContextTrust.PARTIAL_CONTEXT
            else:
                overall = ContextTrust.PARTIAL_CONTEXT

        exact_eligible = overall in (ContextTrust.EXACT_VERIFIED, ContextTrust.EQUIVALENT_VERIFIED)
        limiting = [f.to_dict() for f in fields if f.required
                    and ContextFieldTrust(f.trust) in (_UNKNOWN_STATES | {ContextFieldTrust.KNOWN_DIFFERENT})]
        if not limiting:
            explanation = ("all fields required for the " + dom.replace("_", " ")
                           + " domain are a known match.") if exact_eligible else \
                ("no required fields are known for this domain.")
        else:
            explanation = ("the following required field(s) limit " + dom.replace("_", " ")
                           + " confidence: "
                           + ", ".join(f"{f['field']} ({f['trust'].replace('_', ' ')})"
                                       for f in limiting) + ".")
        snapshot = {f: _lc(cur.get(f)) for f in MATERIAL_FIELDS if _lc(cur.get(f))}
        fp = _fp({"domain": dom, "overall": overall.value,
                  "required": sorted(required),
                  "trust": [(f.field, f.trust) for f in fields if f.required],
                  "snapshot": snapshot})
        return MaterialContextTrust(
            domain=dom, overall_trust=overall.value, exact_eligible=exact_eligible,
            field_trust=tuple(f.to_dict() for f in fields), limiting_fields=tuple(limiting),
            limitation_explanation=explanation, context_snapshot=snapshot, doctrine=_DOCTRINE,
            content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return MaterialContextTrust(domain=_lc(domain), overall_trust=ContextTrust.UNVERIFIABLE.value,
                                    exact_eligible=False, field_trust=(), limiting_fields=(),
                                    limitation_explanation="unavailable.", context_snapshot={},
                                    doctrine=_DOCTRINE, content_fingerprint=_fp({"e": 1}))


def context_snapshot_fingerprint(current: Optional[Mapping]) -> str:
    """A pure semantic context-snapshot fingerprint over the current material fields (references, not a
    persisted copy). Excludes wall-clock / identity / paths. Deterministic."""
    cur = current if isinstance(current, Mapping) else {}
    snap = {f: _lc(cur.get(f)) for f in MATERIAL_FIELDS if _lc(cur.get(f))}
    return _fp({"snapshot": snap})


def material_context_versions() -> dict:
    return {"material_context": MATERIAL_CONTEXT_VERSION, "schema": MATERIAL_CONTEXT_SCHEMA}
