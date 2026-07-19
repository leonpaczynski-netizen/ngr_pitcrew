"""Setup Outcome & Lineage Learning — Layer 3 of the Race-Engineer Activation (Program 2, Phase 37).

A deterministic, read-only interpretation of the EXACT-CONTEXT setup lineage: for the current
programme it walks the ordered applied setups (each an immutable Phase-8 development record), reads
each applied delta and its observed outcome, and derives - per changed field/direction - whether the
change should be repeated, held, reversed or blocked, which confirmed-good behaviours must be
protected, and what the rollback target is when a change worsened the car.

Doctrine:
  * "Worse than the previous setup" is AUTHORITATIVE regression evidence against the immediately
    preceding applied delta (when the context and attribution are valid). A worsened direction is
    BLOCKED - it must NOT be repeated merely because a generic rule still recommends it. It unblocks
    only when a LATER exact-context record repeats the same field+direction and improves with equal or
    stronger confidence (the no-repeat guard, Phase 37 invariant).
  * Only EXACT-CONTEXT evidence drives the lineage (context safety, Phase 36). Transferable evidence is
    noted as lower-confidence context, never as the lineage itself.
  * Newer is never "better" merely because it is newer - only the observed outcome decides.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value; applies NOTHING; creates no experiment.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

SETUP_OUTCOME_LEARNING_VERSION = "setup_outcome_learning_v1"
SETUP_OUTCOME_LEARNING_SCHEMA = 1

_INVARIANT = ("A failed setup experiment alters future advice: a worsened change direction is blocked "
              "and is not recommended again without stronger new evidence. Confirmed-good behaviour is "
              "protected; a worsened change has an explicit rollback target.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{SETUP_OUTCOME_LEARNING_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class OutcomeVerdict(str, Enum):
    IMPROVED = "improved"
    WORSENED = "worsened"
    UNCHANGED = "unchanged"
    INCONCLUSIVE = "inconclusive"


class DirectionAction(str, Enum):
    REPEAT = "repeat"            # proven-good direction; may be pursued further
    HOLD = "hold"               # keep as-is; no evidence to move
    REVERSE = "reverse"         # this direction worsened the car; go the other way
    BLOCKED = "blocked"         # do NOT repeat this direction without stronger new evidence
    INSUFFICIENT = "insufficient"  # inconclusive; needs more evidence


_CONF_RANK = {"": 0, "low": 1, "medium": 2, "high": 3, "very_high": 4}
_IMPROVED = ("confirmed_improvement", "partial_improvement", "improvement", "improved")
_UNCHANGED = ("no_change", "neutral", "unchanged")
_INCONCLUSIVE = ("insufficient_evidence", "confounded", "inconclusive", "")


def _verdict(record: Mapping) -> OutcomeVerdict:
    status = _lc(record.get("outcome_status"))
    regressions = record.get("new_regressions") or []
    if status == "regression" or regressions:
        return OutcomeVerdict.WORSENED
    if status in _IMPROVED:
        return OutcomeVerdict.IMPROVED
    if status in _UNCHANGED:
        return OutcomeVerdict.UNCHANGED
    return OutcomeVerdict.INCONCLUSIVE


def _deltas(record: Mapping) -> Tuple[dict, ...]:
    out = []
    for c in (record.get("changes") or []):
        fld = _norm(c.get("field"))
        if not fld:
            continue
        out.append({"field": fld, "direction": _lc(c.get("direction")),
                    "from_value": _norm(c.get("from_value")), "to_value": _norm(c.get("to_value")),
                    "subsystem": _norm(c.get("subsystem"))})
    return tuple(out)


@dataclass(frozen=True)
class LineageStep:
    seq: int
    record_key: str
    experiment_id: str
    recorded_at: str
    session_date: str
    delta: Tuple[dict, ...]
    outcome_status: str
    verdict: str
    confidence: str
    is_regression: bool
    rollback_target: str        # record_key of the state to return to (or "baseline")
    rollback_note: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "record_key": self.record_key,
                "experiment_id": self.experiment_id, "recorded_at": self.recorded_at,
                "session_date": self.session_date, "delta": [dict(d) for d in self.delta],
                "outcome_status": self.outcome_status, "verdict": self.verdict,
                "confidence": self.confidence, "is_regression": self.is_regression,
                "rollback_target": self.rollback_target, "rollback_note": self.rollback_note}


@dataclass(frozen=True)
class DirectionGuidance:
    field: str
    direction: str
    action: str
    confidence: str
    evidence_count: int
    reason: str
    source_experiments: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"field": self.field, "direction": self.direction, "action": self.action,
                "confidence": self.confidence, "evidence_count": self.evidence_count,
                "reason": self.reason, "source_experiments": list(self.source_experiments)}


@dataclass(frozen=True)
class SetupOutcomeLearning:
    scope_fingerprint: str
    lineage: Tuple[dict, ...]
    current_state: dict
    directional_guidance: Tuple[dict, ...]
    blocked_directions: Tuple[dict, ...]
    protected_behaviours: Tuple[dict, ...]
    rollback_plan: dict
    empty_state: str
    invariant_statement: str
    content_fingerprint: str
    schema_version: int = SETUP_OUTCOME_LEARNING_SCHEMA
    eval_version: str = SETUP_OUTCOME_LEARNING_VERSION

    def to_dict(self) -> dict:
        return {"scope_fingerprint": self.scope_fingerprint,
                "lineage": [dict(s) for s in self.lineage], "current_state": dict(self.current_state),
                "directional_guidance": [dict(g) for g in self.directional_guidance],
                "blocked_directions": [dict(b) for b in self.blocked_directions],
                "protected_behaviours": [dict(p) for p in self.protected_behaviours],
                "rollback_plan": dict(self.rollback_plan), "empty_state": self.empty_state,
                "invariant_statement": self.invariant_statement,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def _order_key(rec: Mapping) -> Tuple[str, str, str]:
    return (_norm(rec.get("recorded_at")), _norm(rec.get("outcome_id")).rjust(12, "0"),
            _norm(rec.get("record_key")))


def build_setup_outcome_learning(scope_fingerprint: str,
                                 exact_records: Optional[Sequence[Mapping]]) -> SetupOutcomeLearning:
    """Interpret the ordered EXACT-CONTEXT setup lineage. ``exact_records`` are the immutable Phase-8
    development-record dicts whose context is EXACT for the current scope (already filtered by the
    Phase-36 activation). Deterministic; order-independent input (re-sorted internally); never raises."""
    try:
        return _build(_norm(scope_fingerprint),
                      [r for r in (exact_records or []) if isinstance(r, Mapping)])
    except Exception:  # pragma: no cover - defensive
        return SetupOutcomeLearning(
            scope_fingerprint=_norm(scope_fingerprint), lineage=(), current_state={},
            directional_guidance=(), blocked_directions=(), protected_behaviours=(),
            rollback_plan={}, empty_state="Setup lineage unavailable.",
            invariant_statement=_INVARIANT, content_fingerprint=_fp({"error": True}))


def _build(scope_fp: str, records: List[Mapping]) -> SetupOutcomeLearning:
    ordered = sorted(records, key=_order_key)
    lineage: List[LineageStep] = []
    # (field, direction) -> aggregate guidance state
    guidance: "Dict[Tuple[str, str], dict]" = {}
    protected: Dict[Tuple[str, str], dict] = {}

    prev_good_key = "baseline"   # last non-worsening applied state = current rollback anchor
    for seq, rec in enumerate(ordered):
        v = _verdict(rec)
        deltas = _deltas(rec)
        conf = _lc(rec.get("confidence_level"))
        exp = _norm(rec.get("experiment_id"))
        is_reg = v is OutcomeVerdict.WORSENED
        rollback_target = prev_good_key if is_reg else ""
        rollback_note = ("" if not is_reg else
                         (f"return to prior applied state {prev_good_key}" if prev_good_key != "baseline"
                          else "return to the baseline (no prior applied setup)"))
        lineage.append(LineageStep(
            seq=seq, record_key=_norm(rec.get("record_key")), experiment_id=exp,
            recorded_at=_norm(rec.get("recorded_at")), session_date=_norm(rec.get("session_date")),
            delta=deltas, outcome_status=_lc(rec.get("outcome_status")), verdict=v.value,
            confidence=conf, is_regression=is_reg, rollback_target=rollback_target,
            rollback_note=rollback_note))

        # per-field/direction guidance with the no-repeat guard.
        for d in deltas:
            key = (d["field"], d["direction"])
            cur = guidance.get(key)
            if v is OutcomeVerdict.WORSENED:
                guidance[key] = {"action": DirectionAction.BLOCKED, "confidence": conf,
                                 "count": (cur or {}).get("count", 0) + 1,
                                 "reason": "this direction worsened the car; blocked - do not repeat "
                                           "without stronger new evidence.",
                                 "exps": tuple(sorted(set((cur or {}).get("exps", ()) + (exp,))))}
            elif v is OutcomeVerdict.IMPROVED:
                # unblock only if strictly/equally stronger than a prior block.
                if cur and cur["action"] is DirectionAction.BLOCKED and \
                        _CONF_RANK.get(conf, 0) < _CONF_RANK.get(cur["confidence"], 0):
                    # weaker than the block -> the block stands.
                    cur["count"] = cur.get("count", 0) + 1
                    cur["exps"] = tuple(sorted(set(cur.get("exps", ()) + (exp,))))
                    cur["reason"] = ("a later improvement was seen but was weaker than the blocking "
                                     "regression; the block stands until stronger evidence appears.")
                    guidance[key] = cur
                else:
                    action = (DirectionAction.REPEAT if not cur or cur["action"] is not DirectionAction.BLOCKED
                              else DirectionAction.REPEAT)
                    guidance[key] = {"action": action, "confidence": conf,
                                     "count": (cur or {}).get("count", 0) + 1,
                                     "reason": ("proven-good direction; may be repeated / held."
                                                if not (cur and cur["action"] is DirectionAction.BLOCKED)
                                                else "stronger new evidence overturned the earlier block; "
                                                     "proven-good and may be repeated."),
                                     "exps": tuple(sorted(set((cur or {}).get("exps", ()) + (exp,))))}
            elif v is OutcomeVerdict.UNCHANGED:
                if not cur:
                    guidance[key] = {"action": DirectionAction.HOLD, "confidence": conf, "count": 1,
                                     "reason": "no measured effect; hold - do not move without a reason.",
                                     "exps": (exp,)}
                else:
                    cur["count"] = cur.get("count", 0) + 1
                    guidance[key] = cur
            else:  # inconclusive
                if not cur:
                    guidance[key] = {"action": DirectionAction.INSUFFICIENT, "confidence": conf,
                                     "count": 1,
                                     "reason": "inconclusive / confounded; insufficient evidence to "
                                               "repeat or reverse.", "exps": (exp,)}
                else:
                    cur["count"] = cur.get("count", 0) + 1
                    guidance[key] = cur

        # protected behaviours: confirmed-good behaviours to keep (from the outcome + protected_knowledge)
        for p in (rec.get("protected_behaviours") or []):
            beh = _norm(p.get("behaviour"))
            if beh and _lc(p.get("verdict")) not in ("material_regression", "minor_regression"):
                protected[(beh, _norm(p.get("field")))] = {
                    "behaviour": beh, "field": _norm(p.get("field")),
                    "confidence": _norm(p.get("confidence")), "source": "confirmed_good_outcome"}
        for imp in (rec.get("confirmed_improvements") or []):
            it = _norm(imp.get("issue_type"))
            cn = _norm(imp.get("corner_name")) or _norm(imp.get("segment_id"))
            if it:
                protected[("resolved:" + it, cn)] = {
                    "behaviour": f"resolved {it}" + (f" @ {cn}" if cn else ""), "field": "",
                    "confidence": _norm(imp.get("confidence")), "source": "resolved_issue"}

        # a non-worsening applied state becomes the new rollback anchor.
        if v is not OutcomeVerdict.WORSENED:
            prev_good_key = _norm(rec.get("record_key")) or prev_good_key

    # fold authoritative Phase-3 failed directions from protected_knowledge into blocked set.
    for rec in ordered:
        for k in (rec.get("protected_knowledge") or []):
            if _lc(k.get("kind")) in ("never_move_direction", "known_unstable"):
                key = (_norm(k.get("field")), _lc(k.get("direction")))
                if key[0]:
                    cur = guidance.get(key)
                    if not cur or cur["action"] is not DirectionAction.REPEAT:
                        guidance[key] = {"action": DirectionAction.BLOCKED,
                                         "confidence": _norm(k.get("confidence")) or (cur or {}).get(
                                             "confidence", ""),
                                         "count": (cur or {}).get("count", 0),
                                         "reason": "canonical protected knowledge: this direction is a "
                                                   "recorded failed/unstable direction - blocked.",
                                         "exps": (cur or {}).get("exps", ())}

    guidance_out = tuple(DirectionGuidance(
        field=k[0], direction=k[1], action=g["action"].value if isinstance(g["action"], DirectionAction)
        else str(g["action"]), confidence=g.get("confidence", ""), evidence_count=int(g.get("count", 0)),
        reason=g.get("reason", ""), source_experiments=tuple(g.get("exps", ())))
        for k, g in sorted(guidance.items()))
    blocked = tuple(d.to_dict() for d in guidance_out
                    if d.action in (DirectionAction.BLOCKED.value, DirectionAction.REVERSE.value))
    protected_out = tuple(protected[q] for q in sorted(protected))

    latest = ordered[-1] if ordered else None
    current_state = {}
    rollback_plan = {}
    if latest is not None:
        lv = _verdict(latest)
        current_state = {
            "record_key": _norm(latest.get("record_key")),
            "experiment_id": _norm(latest.get("experiment_id")),
            "outcome_status": _lc(latest.get("outcome_status")),
            "verdict": lv.value, "confidence": _lc(latest.get("confidence_level")),
            "delta": [dict(d) for d in _deltas(latest)],
            "recorded_at": _norm(latest.get("recorded_at"))}
        if lv is OutcomeVerdict.WORSENED:
            rollback_plan = {"needed": True, "target": lineage[-1].rollback_target,
                             "note": lineage[-1].rollback_note,
                             "failed_delta": [dict(d) for d in _deltas(latest)],
                             "recommendation": "roll back or reverse the failed delta, or test a "
                                               "different bounded hypothesis; do not re-apply the "
                                               "blocked direction."}
        else:
            rollback_plan = {"needed": False, "target": "",
                             "note": "current applied state is not a regression; no rollback required.",
                             "failed_delta": [], "recommendation": ""}

    empty = "" if ordered else ("No exact-context setup lineage yet - nothing has been applied and "
                                "reviewed in this exact context.")
    fp = _fp({"scope": scope_fp,
              "lineage": [(s.seq, s.record_key, s.verdict, s.rollback_target) for s in lineage],
              "guidance": [(g.field, g.direction, g.action, g.confidence) for g in guidance_out],
              "protected": [(p["behaviour"], p["field"]) for p in protected_out]})
    return SetupOutcomeLearning(
        scope_fingerprint=scope_fp, lineage=tuple(s.to_dict() for s in lineage),
        current_state=current_state, directional_guidance=tuple(g.to_dict() for g in guidance_out),
        blocked_directions=blocked, protected_behaviours=protected_out, rollback_plan=rollback_plan,
        empty_state=empty, invariant_statement=_INVARIANT, content_fingerprint=fp)


def outcome_learning_versions() -> dict:
    return {"setup_outcome_learning": SETUP_OUTCOME_LEARNING_VERSION,
            "schema": SETUP_OUTCOME_LEARNING_SCHEMA}
