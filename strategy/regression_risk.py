"""Regression-risk intelligence (Engineering Brain Phase 9).

Before Phase 5 candidate selection is DISPLAYED, this READ-ONLY OBSERVER flags the
regression risks a proposed change would run into, drawn entirely from the immutable
development history (via the Phase-9 transfers + constraints): a known failed
direction, a previously unstable range, a protected-field conflict, a working-window
edge, a repeated regression, or weak supporting confidence.

THIS PHASE NEVER BLOCKS AND NEVER DECIDES. It only reports. Authority to accept or
reject a change always remains with Phases 3 / 5 / 6.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock; no probability — deterministic rule-based flagging only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.context_transfer import EngineeringTransfer, TransferKind, TransferStrength
from strategy.engineering_constraints import EngineeringConstraint
from strategy.development_history import ConstraintKind

REGRESSION_RISK_VERSION = "regression_risk_v1"


class RiskKind(str, Enum):
    KNOWN_FAILED_DIRECTION = "known_failed_direction"
    PREVIOUSLY_UNSTABLE_RANGE = "previously_unstable_range"
    PROTECTED_FIELD_CONFLICT = "protected_field_conflict"
    WORKING_WINDOW_EDGE = "working_window_edge"
    REPEATED_REGRESSION = "repeated_regression"
    CONFIDENCE_WEAKNESS = "confidence_weakness"


class RiskSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _to_float(v) -> Optional[float]:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RegressionRisk:
    kind: str                           # RiskKind value
    severity: str                       # RiskSeverity value
    field: str
    direction: str
    value: str
    reason: str
    evidence_source: str
    supporting_sessions: Tuple[str, ...]
    supporting_experiments: Tuple[str, ...]
    confidence: str
    confirmed: bool
    eval_version: str = REGRESSION_RISK_VERSION

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "severity": self.severity, "field": self.field,
            "direction": self.direction, "value": self.value, "reason": self.reason,
            "evidence_source": self.evidence_source,
            "supporting_sessions": list(self.supporting_sessions),
            "supporting_experiments": list(self.supporting_experiments),
            "confidence": self.confidence, "confirmed": self.confirmed,
            "eval_version": self.eval_version,
        }

    def sort_key(self) -> tuple:
        order = {RiskSeverity.HIGH.value: 0, RiskSeverity.MEDIUM.value: 1,
                 RiskSeverity.LOW.value: 2, RiskSeverity.INFO.value: 3}
        return (order.get(self.severity, 4), 0 if self.confirmed else 1, self.kind,
                self.field, self.direction, self.value)


def _sev(confirmed: bool, high: bool = True) -> RiskSeverity:
    if not high:
        return RiskSeverity.LOW
    return RiskSeverity.HIGH if confirmed else RiskSeverity.MEDIUM


def assess_regression_risk(
    constraints: Sequence[EngineeringConstraint],
    transfers: Sequence[EngineeringTransfer],
    *,
    proposed_change: Optional[Mapping] = None,
) -> Tuple[RegressionRisk, ...]:
    """Flag regression risks for a proposed change (``{field, direction, value}``) or,
    when no change is supplied, surface the standing risks (protected fields, known
    failed directions, known-unstable ranges) for the context. Deterministic; NEVER
    blocks — it only reports. Authority remains with Phases 3/5/6."""
    out: List[RegressionRisk] = []
    pf = _lc((proposed_change or {}).get("field"))
    pdir = _lc((proposed_change or {}).get("direction"))
    pval = _to_float((proposed_change or {}).get("value"))
    scoped = bool(proposed_change)

    def _emit(kind, severity, c: EngineeringConstraint, reason):
        out.append(RegressionRisk(
            kind=kind.value, severity=severity.value, field=c.field,
            direction=c.direction, value=c.value, reason=reason,
            evidence_source=c.evidence_source,
            supporting_sessions=c.supporting_sessions,
            supporting_experiments=c.supporting_experiments,
            confidence=c.confidence, confirmed=c.confirmed))

    for c in constraints:
        cf = _lc(c.field)
        field_hit = (not scoped) or (cf == pf)
        if not field_hit:
            continue

        # 1) known failed direction — flag when the proposed direction matches
        if c.kind == ConstraintKind.NEVER_MOVE_DIRECTION.value:
            dir_hit = (not scoped) or (not pdir) or (_lc(c.direction) == pdir)
            if dir_hit:
                _emit(RiskKind.KNOWN_FAILED_DIRECTION, _sev(c.confirmed), c,
                      f"moving {c.field} {c.direction} was proven ineffective before")

        # 2) previously unstable range
        elif c.kind == ConstraintKind.KNOWN_UNSTABLE.value:
            _emit(RiskKind.PREVIOUSLY_UNSTABLE_RANGE, _sev(c.confirmed), c,
                  f"{c.field} {c.direction} {c.value} previously produced a regression")

        # 3) protected-field conflict
        elif c.kind == ConstraintKind.PROTECTED_BEHAVIOUR.value:
            _emit(RiskKind.PROTECTED_FIELD_CONFLICT, _sev(c.confirmed, high=scoped), c,
                  f"{c.field or c.value} is a protected behaviour — changing it risks it")

        # 4) working-window edge (never_below / never_above)
        elif c.kind in (ConstraintKind.NEVER_BELOW.value, ConstraintKind.NEVER_ABOVE.value):
            bound = _to_float(c.value)
            edge = False
            if scoped and pval is not None and bound is not None:
                if c.kind == ConstraintKind.NEVER_BELOW.value and pval <= bound:
                    edge = True
                if c.kind == ConstraintKind.NEVER_ABOVE.value and pval >= bound:
                    edge = True
            elif not scoped:
                edge = True            # standing edge advisory
            if edge:
                rel = "below" if c.kind == ConstraintKind.NEVER_BELOW.value else "above"
                _emit(RiskKind.WORKING_WINDOW_EDGE,
                      _sev(c.confirmed) if scoped else RiskSeverity.INFO, c,
                      f"proposed value is at/{rel} the learned working-window edge "
                      f"({c.value})")

    # 5) repeated regression — same field failed in >= 2 experiments (from transfers)
    failed_by_field: dict = {}
    for t in transfers:
        if t.kind == TransferKind.FAILED_EXPERIMENT.value if isinstance(t.kind, str) \
                else t.kind == TransferKind.FAILED_EXPERIMENT:
            key = _lc(t.field)
            failed_by_field.setdefault(key, set()).update(t.supporting_experiments)
    for field_key, exps in sorted(failed_by_field.items()):
        if (not scoped or field_key == pf) and len(exps) >= 2:
            out.append(RegressionRisk(
                kind=RiskKind.REPEATED_REGRESSION.value,
                severity=RiskSeverity.HIGH.value, field=field_key, direction="",
                value="", reason=f"{field_key} regressed in {len(exps)} prior experiments",
                evidence_source="development history",
                supporting_sessions=(), supporting_experiments=tuple(sorted(exps)),
                confidence="high", confirmed=True))

    # 6) confidence weakness — the strongest supporting evidence is weak/provisional
    if scoped and pf:
        field_transfers = [t for t in transfers if _lc(t.field) == pf]
        if field_transfers:
            best_confirmed = any(t.confirmed for t in field_transfers)
            best_strength = max(
                (t.strength if isinstance(t.strength, str) else t.strength.value)
                for t in field_transfers)
            if not best_confirmed:
                out.append(RegressionRisk(
                    kind=RiskKind.CONFIDENCE_WEAKNESS.value,
                    severity=RiskSeverity.LOW.value, field=pf, direction="", value="",
                    reason="prior evidence for this field is provisional (not confirmed)",
                    evidence_source="development history",
                    supporting_sessions=(),
                    supporting_experiments=tuple(sorted(
                        {e for t in field_transfers for e in t.supporting_experiments})),
                    confidence="low", confirmed=False))

    # de-dup (kind, field, direction, value) keeping the most-severe/confirmed
    best: dict = {}
    for r in out:
        key = (r.kind, r.field, r.direction, r.value)
        prev = best.get(key)
        if prev is None or r.sort_key() < prev.sort_key():
            best[key] = r
    return tuple(sorted(best.values(), key=lambda r: r.sort_key()))


def risk_fingerprint(risks: Sequence[RegressionRisk]) -> str:
    raw = json.dumps([r.to_dict() for r in risks], sort_keys=True,
                     separators=(",", ":"))
    return f"{REGRESSION_RISK_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
