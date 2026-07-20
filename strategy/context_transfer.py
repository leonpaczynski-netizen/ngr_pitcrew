"""Cross-context engineering transfer (Engineering Brain Phase 9).

A READ-ONLY OBSERVER that sits ABOVE Phases 1-8. Before a setup experiment is
proposed, it surfaces the lessons already learned in COMPATIBLE contexts — previously
successful/failed experiments, stable working windows, protected behaviours, known
unstable combinations and known ineffective directions — each with a deterministic
match strength and an explicit reason.

Doctrine:
  * Phase 9 makes NO engineering decision. It evaluates no evidence, creates/chooses no
    experiment, modifies no working window and mutates nothing. It only re-projects the
    immutable Phase-8 development records into deterministic transfer objects.
  * Context matching is a fixed hierarchy (never a probability). Incompatible contexts
    NEVER mix; every transfer states WHY it matched and which sessions/experiments
    produced it, and whether it is confirmed or provisional.
  * The per-context lessons are folded with the Phase-8 authorities
    (`build_history` + `build_engineering_memory`) — no engineering logic is duplicated.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock; no statistical inference — only deterministic rule-based classification.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.development_history import (
    DevelopmentRecord, MemoryContextKey, build_history,
)
from strategy.engineering_memory import build_engineering_memory

CONTEXT_TRANSFER_VERSION = "context_transfer_v1"


class TransferStrength(str, Enum):
    DIRECT_MATCH = "direct_match"       # same driver+car+track+layout+discipline+gt7
    STRONG_MATCH = "strong_match"       # same driver+car, different track
    RELATED_MATCH = "related_match"     # same driver+track, similar car class
    WEAK_MATCH = "weak_match"           # same vehicle, different discipline
    UNKNOWN = "unknown"                 # general engineering knowledge (weak commonality)


_STRENGTH_RANK = {
    TransferStrength.DIRECT_MATCH: 4, TransferStrength.STRONG_MATCH: 3,
    TransferStrength.RELATED_MATCH: 2, TransferStrength.WEAK_MATCH: 1,
    TransferStrength.UNKNOWN: 0,
}


class TransferKind(str, Enum):
    SUCCESSFUL_EXPERIMENT = "successful_experiment"
    FAILED_EXPERIMENT = "failed_experiment"
    STABLE_WINDOW = "stable_window"
    PROTECTED_BEHAVIOUR = "protected_behaviour"
    KNOWN_UNSTABLE = "known_unstable"
    INEFFECTIVE_DIRECTION = "ineffective_direction"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _same(a: str, b: str) -> bool:
    return bool(a) and _lc(a) == _lc(b)


# --------------------------------------------------------------------------- #
# Deterministic context matching (fixed hierarchy — never a probability)
# --------------------------------------------------------------------------- #
def classify_context_match(
    query: MemoryContextKey, candidate: MemoryContextKey, *,
    car_class_of: Optional[Mapping[str, str]] = None,
) -> Tuple[Optional[TransferStrength], str]:
    """Classify how a historical ``candidate`` context relates to the ``query``
    context. Returns (strength, reason) — strength is None when the candidate shares
    NOTHING transferable (it is then excluded, never mixed in)."""
    car_class_of = car_class_of or {}
    driver = _same(query.driver, candidate.driver)
    car = _same(query.car, candidate.car)
    track = _same(query.track, candidate.track)
    layout = _same(query.layout_id, candidate.layout_id)
    disc = _same(query.discipline, candidate.discipline)
    gt7_known = bool(_norm(query.gt7_version)) and bool(_norm(candidate.gt7_version))
    gt7_same = (not gt7_known) or _same(query.gt7_version, candidate.gt7_version)
    compound = _same(query.compound, candidate.compound)

    def _reason(parts) -> str:
        return ", ".join(parts)

    # Tier 1 — DIRECT: same driver, car, track, layout, discipline, gt7 version.
    if driver and car and track and layout and disc and gt7_same:
        parts = ["same driver", "car", "track", "layout", "discipline"]
        if gt7_known:
            parts.append("gt7 version")
        if compound:
            parts.append("compound")
        return TransferStrength.DIRECT_MATCH, _reason(parts) + " (direct match)"
    # Tier 2 — STRONG: same driver + car, different track.
    if driver and car and _norm(candidate.track) and not track:
        return (TransferStrength.STRONG_MATCH,
                "same driver and car, different track (strong match)")
    # Tier 3 — RELATED: same driver + track, similar car class (different car).
    q_cls = _lc(car_class_of.get(_norm(query.car), ""))
    c_cls = _lc(car_class_of.get(_norm(candidate.car), ""))
    if driver and track and not car and q_cls and c_cls and q_cls == c_cls:
        return (TransferStrength.RELATED_MATCH,
                f"same driver and track, similar car class '{q_cls}' (related match)")
    # Tier 4 — WEAK: same vehicle, different discipline.
    if car and _norm(candidate.discipline) and not disc:
        return (TransferStrength.WEAK_MATCH,
                "same car, different discipline (weak match)")
    # Tier 5 — UNKNOWN: general engineering knowledge (some weak commonality).
    if car:
        return (TransferStrength.UNKNOWN,
                "same car, general engineering knowledge (unknown-strength match)")
    if driver and (q_cls and c_cls and q_cls == c_cls):
        return (TransferStrength.UNKNOWN,
                "same driver and car class, general knowledge (unknown-strength match)")
    return None, "no compatible context"


# --------------------------------------------------------------------------- #
# Grouping: matched historical contexts (shared by transfers + constraints)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MatchedContext:
    context: MemoryContextKey
    strength: TransferStrength
    reason: str
    records: Tuple[DevelopmentRecord, ...]


def group_matched_records(
    query: MemoryContextKey, records: Sequence, *,
    car_class_of: Optional[Mapping[str, str]] = None,
) -> Tuple[MatchedContext, ...]:
    """Group candidate development records by their context, classify each context's
    match strength vs the query, and drop contexts that share nothing. Deterministic
    order: strongest match first, then by context key."""
    by_ctx: Dict[str, List[DevelopmentRecord]] = {}
    ctx_obj: Dict[str, MemoryContextKey] = {}
    for r in (records or ()):
        rec = r if isinstance(r, DevelopmentRecord) else DevelopmentRecord.from_dict(r)
        key = rec.memory_context_key or rec.context.key()
        by_ctx.setdefault(key, []).append(rec)
        ctx_obj[key] = rec.context
    out = []
    for key, recs in by_ctx.items():
        strength, reason = classify_context_match(
            query, ctx_obj[key], car_class_of=car_class_of)
        if strength is None:
            continue
        ordered = build_history(recs).records     # chronological, deduped
        out.append(MatchedContext(context=ctx_obj[key], strength=strength,
                                  reason=reason, records=ordered))
    out.sort(key=lambda m: (-_STRENGTH_RANK[m.strength], m.context.key()))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Transfer objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EngineeringTransfer:
    kind: TransferKind
    strength: TransferStrength
    source_context: MemoryContextKey
    match_reason: str
    field: str
    direction: str
    value: str
    outcome_status: str
    supporting_sessions: Tuple[str, ...]
    supporting_experiments: Tuple[str, ...]
    confidence: str
    confirmed: bool
    detail: str
    eval_version: str = CONTEXT_TRANSFER_VERSION

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value, "strength": self.strength.value,
            "source_context": self.source_context.to_dict(),
            "match_reason": self.match_reason, "field": self.field,
            "direction": self.direction, "value": self.value,
            "outcome_status": self.outcome_status,
            "supporting_sessions": list(self.supporting_sessions),
            "supporting_experiments": list(self.supporting_experiments),
            "confidence": self.confidence, "confirmed": self.confirmed,
            "detail": self.detail, "eval_version": self.eval_version,
        }

    def sort_key(self) -> tuple:
        return (-_STRENGTH_RANK[self.strength], 0 if self.confirmed else 1,
                -len(self.supporting_sessions), self.kind.value, self.field,
                self.detail)


def _confirmed(confidence: str, sessions) -> bool:
    return _lc(confidence) == "high" and len({s for s in sessions if s}) >= 2


def transfers_for_context(mc: MatchedContext) -> Tuple[EngineeringTransfer, ...]:
    """Emit the transfer objects for ONE matched context, folding the records with the
    Phase-8 memory authority (no duplicated engineering logic)."""
    records = mc.records
    memory = build_engineering_memory(build_history(records))
    out: List[EngineeringTransfer] = []

    def _mk(kind, field, direction, value, status, sessions, experiments,
            confidence, detail):
        sess = tuple(sorted({_norm(s) for s in sessions if _norm(s)}))
        exps = tuple(sorted({_norm(e) for e in experiments if _norm(e)}))
        out.append(EngineeringTransfer(
            kind=kind, strength=mc.strength, source_context=mc.context,
            match_reason=mc.reason, field=field, direction=direction, value=value,
            outcome_status=status, supporting_sessions=sess,
            supporting_experiments=exps, confidence=_norm(confidence),
            confirmed=_confirmed(confidence, sess), detail=detail))

    # successful / failed experiments (per record, with the applied change)
    for rec in records:
        fields = ", ".join(c.get("field", "") for c in rec.changes) or "review"
        direction = "; ".join(c.get("direction", "") for c in rec.changes
                              if c.get("direction"))
        value = "; ".join(c.get("to_value", "") for c in rec.changes
                          if c.get("to_value"))
        if rec.improved:
            resolved = [r["issue_type"] for r in rec.confirmed_improvements]
            detail = (f"{fields} → {', '.join(resolved) or 'improvement'} "
                      f"({rec.outcome_status})")
            _mk(TransferKind.SUCCESSFUL_EXPERIMENT, fields, direction, value,
                rec.outcome_status, [rec.test_session_id], [rec.experiment_id],
                rec.confidence_level, detail)
        if rec.regressed:
            regr = [r["issue_type"] for r in rec.new_regressions]
            detail = (f"{fields} → {', '.join(regr) or 'regression'} "
                      f"({rec.outcome_status})")
            _mk(TransferKind.FAILED_EXPERIMENT, fields, direction, value,
                rec.outcome_status, [rec.test_session_id], [rec.experiment_id],
                rec.confidence_level, detail)

    # stable working windows (converged only)
    sessions_all = [rec.test_session_id for rec in records]
    for w in memory.window_evolution:
        if not w.converged:
            continue
        rng = f"{w.latest_min}..{w.latest_max}"
        _mk(TransferKind.STABLE_WINDOW, w.field, "", rng, "", sessions_all,
            [rec.experiment_id for rec in records], w.latest_confidence,
            f"{w.field} stable in {rng} ({w.latest_confidence})")

    # protected behaviours (preserved)
    for p in memory.protected_behaviours:
        if p.get("verdict") == "preserved":
            _mk(TransferKind.PROTECTED_BEHAVIOUR, p.get("field", ""), "", "",
                "preserved", sessions_all, [], p.get("confidence", ""),
                f"protect: {p.get('behaviour', '')}")

    # known-unstable + ineffective directions (from folded protected knowledge)
    for k in memory.protected_knowledge:
        if k.kind == "known_unstable":
            _mk(TransferKind.KNOWN_UNSTABLE, k.field, k.direction, k.value, "",
                sessions_all, [], k.confidence,
                f"known unstable: {k.field} {k.direction} {k.value}".strip())
        elif k.kind == "never_move_direction":
            _mk(TransferKind.INEFFECTIVE_DIRECTION, k.field, k.direction, k.value, "",
                sessions_all, [], k.confidence,
                f"ineffective: {k.field} {k.direction}".strip())

    return tuple(out)


def build_context_transfers(
    query: MemoryContextKey, records: Sequence, *,
    car_class_of: Optional[Mapping[str, str]] = None,
    matched: Optional[Sequence[MatchedContext]] = None,
) -> Tuple[EngineeringTransfer, ...]:
    """Build the full ranked transfer set for a query context. Deterministic; the
    same records yield the same ordered transfers (strongest match first)."""
    groups = matched if matched is not None else group_matched_records(
        query, records, car_class_of=car_class_of)
    out: List[EngineeringTransfer] = []
    for mc in groups:
        out.extend(transfers_for_context(mc))
    out.sort(key=lambda t: t.sort_key())
    return tuple(out)


def transfer_fingerprint(transfers: Sequence[EngineeringTransfer]) -> str:
    raw = json.dumps([t.to_dict() for t in transfers], sort_keys=True,
                     separators=(",", ":"))
    return f"{CONTEXT_TRANSFER_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
