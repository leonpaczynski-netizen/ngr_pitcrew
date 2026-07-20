"""Engineering constraints surfacing (Engineering Brain Phase 9).

A READ-ONLY OBSERVER that re-projects the per-record protected-knowledge ALREADY
derived by Phase 8 (learned minimums/maximums, failed directions, known-unstable
combinations, protected behaviours, preferred ranges) into deterministic
``EngineeringConstraint`` objects, ENRICHED with their evidence provenance: which
sessions and experiments produced them, and whether they are confirmed or provisional.

It surfaces constraints; it NEVER enforces or blocks them. Authority to accept or
reject a change always remains with Phases 3 / 5 / 6.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock; deterministic.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.development_history import ConstraintKind, DevelopmentRecord, MemoryContextKey
from strategy.context_transfer import (
    MatchedContext, TransferStrength, group_matched_records,
)

ENGINEERING_CONSTRAINTS_VERSION = "engineering_constraints_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


_CONF_RANK = {"high": 3, "medium": 2, "low": 1, "provisional": 1, "": 0}


@dataclass(frozen=True)
class EngineeringConstraint:
    """A durable engineering constraint with its evidence provenance."""

    kind: str                           # ConstraintKind value
    field: str
    direction: str
    value: str
    strongest_match: str                # TransferStrength value of its best source
    evidence_source: str                # human label of where it came from
    supporting_sessions: Tuple[str, ...]
    supporting_experiments: Tuple[str, ...]
    times_reinforced: int
    confidence: str
    confirmed: bool                     # confirmed vs provisional
    detail: str
    eval_version: str = ENGINEERING_CONSTRAINTS_VERSION

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "field": self.field, "direction": self.direction,
            "value": self.value, "strongest_match": self.strongest_match,
            "evidence_source": self.evidence_source,
            "supporting_sessions": list(self.supporting_sessions),
            "supporting_experiments": list(self.supporting_experiments),
            "times_reinforced": self.times_reinforced, "confidence": self.confidence,
            "confirmed": self.confirmed, "detail": self.detail,
            "eval_version": self.eval_version,
        }

    def sort_key(self) -> tuple:
        return (0 if self.confirmed else 1, self.kind, self.field, self.direction,
                self.value)


_SOURCE_LABEL = {
    "phase3_failed_direction": "failed-direction lockout (Phase 3)",
    "regression_outcome": "regression outcome",
    "learned_working_window": "learned working window (Phase 5)",
    "converged_working_window": "converged working window (Phase 5)",
    "protected_behaviour": "protected behaviour",
}


class _Acc:
    __slots__ = ("kind", "field", "direction", "value", "sessions", "experiments",
                 "reinforced", "confidence", "best_strength", "source")

    def __init__(self):
        self.kind = self.field = self.direction = self.value = ""
        self.sessions = set()
        self.experiments = set()
        self.reinforced = 0
        self.confidence = ""
        self.best_strength = TransferStrength.UNKNOWN
        self.source = ""


_STRENGTH_RANK = {
    TransferStrength.DIRECT_MATCH: 4, TransferStrength.STRONG_MATCH: 3,
    TransferStrength.RELATED_MATCH: 2, TransferStrength.WEAK_MATCH: 1,
    TransferStrength.UNKNOWN: 0,
}


def derive_constraints(
    query: MemoryContextKey, records: Sequence, *,
    car_class_of: Optional[Mapping[str, str]] = None,
    matched: Optional[Sequence[MatchedContext]] = None,
) -> Tuple[EngineeringConstraint, ...]:
    """Fold the per-record Phase-8 protected knowledge from all COMPATIBLE contexts
    into de-duplicated constraints with provenance. Deterministic; confirmed-first
    order. A constraint is CONFIRMED when high-confidence and supported by >= 2
    sessions AND it comes from at least a STRONG match; otherwise provisional."""
    groups = matched if matched is not None else group_matched_records(
        query, records, car_class_of=car_class_of)
    acc: Dict[Tuple[str, str, str, str], _Acc] = {}
    def _fold(kind, field, direction, value, source, confidence, rec, strength):
        if not kind or not (field or value):
            return
        key = (kind, field, direction, value)
        a = acc.get(key)
        if a is None:
            a = acc[key] = _Acc()
            a.kind, a.field, a.direction, a.value = kind, field, direction, value
            a.source = _norm(source)
        a.reinforced += 1
        if _norm(rec.test_session_id):
            a.sessions.add(_norm(rec.test_session_id))
        if _norm(rec.experiment_id):
            a.experiments.add(_norm(rec.experiment_id))
        if _CONF_RANK.get(_lc(confidence), 0) > _CONF_RANK.get(_lc(a.confidence), 0):
            a.confidence = _norm(confidence)
        if _STRENGTH_RANK[strength] > _STRENGTH_RANK[a.best_strength]:
            a.best_strength = strength

    for mc in groups:
        for rec in mc.records:
            # per-record derived protected knowledge (windows / failed directions /
            # known-unstable) — already computed by Phase 8.
            for k in rec.protected_knowledge:
                _fold(_norm(k.get("kind")), _norm(k.get("field")),
                      _norm(k.get("direction")), _norm(k.get("value")),
                      k.get("source"), k.get("confidence"), rec, mc.strength)
            # protected behaviours are stored separately on the record → surface them
            # as PROTECTED_BEHAVIOUR constraints keyed by the protected field.
            for p in rec.protected_behaviours:
                if _norm(p.get("verdict")) != "preserved":
                    continue
                _fold(ConstraintKind.PROTECTED_BEHAVIOUR.value, _norm(p.get("field")),
                      "", _norm(p.get("behaviour")), "protected_behaviour",
                      p.get("confidence"), rec, mc.strength)

    out = []
    for a in acc.values():
        sessions = tuple(sorted(a.sessions))
        confirmed = (_lc(a.confidence) == "high" and len(sessions) >= 2
                     and _STRENGTH_RANK[a.best_strength] >= _STRENGTH_RANK[TransferStrength.STRONG_MATCH])
        out.append(EngineeringConstraint(
            kind=a.kind, field=a.field, direction=a.direction, value=a.value,
            strongest_match=a.best_strength.value,
            evidence_source=_SOURCE_LABEL.get(a.source, a.source or "development history"),
            supporting_sessions=sessions,
            supporting_experiments=tuple(sorted(a.experiments)),
            times_reinforced=a.reinforced, confidence=a.confidence,
            confirmed=confirmed, detail=_constraint_detail(a)))
    out.sort(key=lambda c: c.sort_key())
    return tuple(out)


def _constraint_detail(a: _Acc) -> str:
    k = a.kind
    if k == ConstraintKind.NEVER_BELOW.value:
        return f"never reduce {a.field} below {a.value}"
    if k == ConstraintKind.NEVER_ABOVE.value:
        return f"never raise {a.field} above {a.value}"
    if k == ConstraintKind.NEVER_MOVE_DIRECTION.value:
        return f"avoid moving {a.field} {a.direction} (proven ineffective)".strip()
    if k == ConstraintKind.PREFERRED_RANGE.value:
        return f"keep {a.field} within {a.value}"
    if k == ConstraintKind.KNOWN_UNSTABLE.value:
        return f"known unstable: {a.field} {a.direction} {a.value}".strip()
    if k == ConstraintKind.PROTECTED_BEHAVIOUR.value:
        return f"protect: {a.value}"
    return f"{a.field} {a.direction} {a.value}".strip()


def constraints_fingerprint(constraints: Sequence[EngineeringConstraint]) -> str:
    raw = json.dumps([c.to_dict() for c in constraints], sort_keys=True,
                     separators=(",", ":"))
    return f"{ENGINEERING_CONSTRAINTS_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
