"""Learned working-window domain (Engineering Brain Phase 5).

A LEARNED working window is the durable, evidence-backed record of what has
actually worked for a setup field in a specific context (driver + car + track +
layout + discipline), accumulated from completed, canonically-evaluated setup
experiments. It is the durable evidence layer BENEATH the per-analysis
`strategy/setup_engineering_context.WorkingWindow` (which is derived each analysis
from history priors) — Phase 5 does not create a competing per-analysis window; it
produces the persisted evidence that a history prior can consume.

Doctrine (mandatory):
  * Evidence before adjustment — a value is "successful" only when the Phase 3
    OUTCOME authority says the experiment improved the car.
  * One successful experiment must not create a broad high-confidence window.
  * A confirmed regression is authoritative and is never averaged away.
  * Inconclusive / invalid / insufficient outcomes teach nothing about values.
  * No universal "best" value — everything is context-keyed and evidence-graded.
  * Compound (multi-field) experiments carry low attribution confidence.

The window state is a DETERMINISTIC FUNCTION of an append-only evidence ledger
(one contribution per experiment-outcome), so replay is idempotent and order
cannot change the result.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises. It
consumes the Phase 3 outcome authority — it never reinterprets telemetry.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from statistics import median as _median
from typing import Mapping, Optional, Sequence, Tuple


WORKING_WINDOW_VERSION = "working_window_v1"

# A direction repeatedly worsening a target, with no compatible improvement, locks
# out further movement that way — mirrors setup_lineage.LOCKOUT_MIN_WORSENED. A
# single STRONG (single-field) regression is already authoritative (Phase 3 emits a
# LOCKOUT failed-direction), so one strong regression locks; weak evidence needs 2.
LOCKOUT_MIN_STRONG_REGRESSIONS = 1
LOCKOUT_MIN_WEAK_REGRESSIONS = 2


class WindowContribution(str, Enum):
    """What one experiment outcome taught about the tested value."""

    SUCCESSFUL = "successful"        # confirmed improvement → the value worked
    UNSUCCESSFUL = "unsuccessful"    # confirmed regression → the value/direction failed
    INEFFECTIVE = "ineffective"      # no meaningful change → value didn't control the issue
    NONE = "none"                    # confounded/insufficient/invalid → no value learning


class WindowConfidence(str, Enum):
    NONE = "none"                    # no valid contributing experiments
    PROVISIONAL = "provisional"      # exactly one valid experiment
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Direction(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NONE = "none"


class DirectionEffect(str, Enum):
    IMPROVED = "improved"
    WORSENED = "worsened"
    NO_EFFECT = "no_effect"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def _as_float(v) -> Optional[float]:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _direction(from_v, to_v) -> Direction:
    a, b = _as_float(from_v), _as_float(to_v)
    if a is None or b is None:
        return Direction.NONE
    if b > a:
        return Direction.INCREASE
    if b < a:
        return Direction.DECREASE
    return Direction.NONE


# --------------------------------------------------------------------------- #
# Context key
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WindowContextKey:
    """Context a learned window is keyed to. driver/gt7 may be unknown ('')."""

    scope_fingerprint: str = ""
    driver: str = ""
    car: str = ""
    track: str = ""
    layout_id: str = ""
    discipline: str = ""
    field: str = ""

    def key(self) -> str:
        raw = "|".join((self.scope_fingerprint, self.driver.lower(), self.car.lower(),
                        self.track.lower(), self.layout_id.lower(),
                        self.discipline.lower(), self.field.lower()))
        return f"{WORKING_WINDOW_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"

    def to_dict(self) -> dict:
        return {"scope_fingerprint": self.scope_fingerprint, "driver": self.driver,
                "car": self.car, "track": self.track, "layout_id": self.layout_id,
                "discipline": self.discipline, "field": self.field}


# --------------------------------------------------------------------------- #
# One experiment's contribution (append-only evidence ledger row)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WindowEvidence:
    """One completed experiment's contribution to a field's learned window.

    The tuple (context_key, experiment_id, outcome_id) is the idempotency key —
    replaying the same outcome contributes exactly once.
    """

    context_key: str
    experiment_id: str
    outcome_id: str
    field: str
    from_value: Optional[str]
    to_value: Optional[str]
    direction: Direction
    magnitude: Optional[float]
    outcome_status: str                 # OutcomeStatus value
    contribution: WindowContribution
    is_compound: bool                   # experiment changed >1 field → low attribution
    attribution_confidence: str         # high / low
    symptom: str = ""
    corners: Tuple[str, ...] = ()
    checkpoint_id: str = ""
    session_id: str = ""
    is_direct: bool = True              # False = inherited cross-context prior
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "context_key": self.context_key, "experiment_id": self.experiment_id,
            "outcome_id": self.outcome_id, "field": self.field,
            "from_value": self.from_value, "to_value": self.to_value,
            "direction": self.direction.value, "magnitude": self.magnitude,
            "outcome_status": self.outcome_status,
            "contribution": self.contribution.value, "is_compound": self.is_compound,
            "attribution_confidence": self.attribution_confidence,
            "symptom": self.symptom, "corners": list(self.corners),
            "checkpoint_id": self.checkpoint_id, "session_id": self.session_id,
            "is_direct": self.is_direct, "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DirectionalEvidence:
    direction: str
    effect: DirectionEffect
    improved_count: int
    worsened_count: int
    no_effect_count: int
    locked_out: bool
    lockout_reason: str = ""

    def to_dict(self) -> dict:
        return {"direction": self.direction, "effect": self.effect.value,
                "improved_count": self.improved_count,
                "worsened_count": self.worsened_count,
                "no_effect_count": self.no_effect_count, "locked_out": self.locked_out,
                "lockout_reason": self.lockout_reason}


@dataclass(frozen=True)
class LearnedWorkingWindow:
    """The materialised learned window — a deterministic function of its evidence."""

    context: WindowContextKey
    field: str
    successful_values: Tuple[float, ...]
    unsuccessful_values: Tuple[float, ...]
    ineffective_values: Tuple[float, ...]
    low_bound: Optional[float]
    high_bound: Optional[float]
    preferred_center: Optional[float]
    valid_experiment_count: int
    improvement_count: int
    regression_count: int
    unchanged_count: int
    inconclusive_count: int
    confidence: WindowConfidence
    provenance: Tuple[str, ...]
    supporting_experiment_ids: Tuple[str, ...]
    supporting_checkpoint_ids: Tuple[str, ...]
    supporting_session_ids: Tuple[str, ...]
    corners: Tuple[str, ...]
    directional: Tuple[DirectionalEvidence, ...]
    contradiction: bool
    has_direct_evidence: bool
    warnings: Tuple[str, ...]
    eval_version: str = WORKING_WINDOW_VERSION

    @property
    def is_evidenced(self) -> bool:
        return self.valid_experiment_count > 0

    def locked_directions(self) -> Tuple[str, ...]:
        return tuple(d.direction for d in self.directional if d.locked_out)

    def to_dict(self) -> dict:
        return {
            "context": self.context.to_dict(), "field": self.field,
            "successful_values": list(self.successful_values),
            "unsuccessful_values": list(self.unsuccessful_values),
            "ineffective_values": list(self.ineffective_values),
            "low_bound": self.low_bound, "high_bound": self.high_bound,
            "preferred_center": self.preferred_center,
            "valid_experiment_count": self.valid_experiment_count,
            "improvement_count": self.improvement_count,
            "regression_count": self.regression_count,
            "unchanged_count": self.unchanged_count,
            "inconclusive_count": self.inconclusive_count,
            "confidence": self.confidence.value, "provenance": list(self.provenance),
            "supporting_experiment_ids": list(self.supporting_experiment_ids),
            "supporting_checkpoint_ids": list(self.supporting_checkpoint_ids),
            "supporting_session_ids": list(self.supporting_session_ids),
            "corners": list(self.corners),
            "directional": [d.to_dict() for d in self.directional],
            "contradiction": self.contradiction,
            "has_direct_evidence": self.has_direct_evidence,
            "warnings": list(self.warnings), "eval_version": self.eval_version,
        }


# --------------------------------------------------------------------------- #
# Outcome → evidence mapping (consumes the Phase 3 authority verbatim)
# --------------------------------------------------------------------------- #
_STATUS_CONTRIB = {
    "confirmed_improvement": WindowContribution.SUCCESSFUL,
    "partial_improvement": WindowContribution.SUCCESSFUL,   # weaker; low attribution
    "regression": WindowContribution.UNSUCCESSFUL,
    "no_meaningful_change": WindowContribution.INEFFECTIVE,
    "confounded": WindowContribution.NONE,
    "insufficient_evidence": WindowContribution.NONE,
}


def outcome_to_window_evidence(
    experiment: Mapping,
    outcome: Mapping,
    *,
    context: Optional[WindowContextKey] = None,
    created_at: str = "",
) -> Tuple[WindowEvidence, ...]:
    """Map a completed Phase-2 experiment + its Phase-3 outcome dict → per-field
    window-evidence contributions. Only actionable (primary/supporting) changes
    contribute. Confounded/insufficient outcomes contribute NONE (metadata only).

    ``experiment`` = get_setup_experiment(...) dict; ``outcome`` =
    get_latest_experiment_outcome(...) dict.
    """
    if not isinstance(experiment, Mapping) or not isinstance(outcome, Mapping):
        return ()
    status = str(outcome.get("status") or "")
    base_contrib = _STATUS_CONTRIB.get(status, WindowContribution.NONE)
    exp_id = str(experiment.get("id") or "")
    outcome_id = str(outcome.get("id") or "")
    scope = str(experiment.get("scope_fingerprint") or "")
    checkpoint = str(experiment.get("applied_checkpoint_id") or "")
    changes = [c for c in (experiment.get("changes") or [])
               if str(c.get("role", "")) in ("primary", "supporting")]
    is_compound = len(changes) > 1
    # partial improvement is a weak positive → treat attribution as low even when
    # single-field (some targets improved, others not).
    weak_positive = status == "partial_improvement"

    # regressing corners for provenance
    regr_corners = tuple(
        str(c.get("corner_name") or c.get("segment_id") or "")
        for c in (outcome.get("corners") or [])
        if str(c.get("verdict")) == "regressed")

    out = []
    for c in changes:
        fld = str(c.get("field") or "")
        if not fld:
            continue
        ctx = context or WindowContextKey(
            scope_fingerprint=scope, field=fld)
        ctx = WindowContextKey(
            scope_fingerprint=ctx.scope_fingerprint, driver=ctx.driver, car=ctx.car,
            track=ctx.track, layout_id=ctx.layout_id, discipline=ctx.discipline,
            field=fld)
        from_v = c.get("from_value")
        to_v = c.get("to_value")
        direction = _direction(from_v, to_v)
        attribution = "low" if (is_compound or weak_positive) else "high"
        out.append(WindowEvidence(
            context_key=ctx.key(), experiment_id=exp_id, outcome_id=outcome_id,
            field=fld, from_value=(None if from_v is None else str(from_v)),
            to_value=(None if to_v is None else str(to_v)), direction=direction,
            magnitude=_as_float(c.get("delta_magnitude")), outcome_status=status,
            contribution=base_contrib, is_compound=is_compound,
            attribution_confidence=attribution,
            symptom=str(c.get("symptom") or ""), corners=regr_corners,
            checkpoint_id=checkpoint,
            session_id=str(outcome.get("test_session_id") or ""),
            is_direct=True, created_at=created_at))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Deterministic window recompute (window = f(evidence ledger))
# --------------------------------------------------------------------------- #
def _grade(valid_count: int, contradiction: bool, improvement: int) -> WindowConfidence:
    if valid_count <= 0:
        return WindowConfidence.NONE
    if valid_count == 1:
        return WindowConfidence.PROVISIONAL
    if valid_count == 2:
        return WindowConfidence.LOW
    if contradiction:
        return WindowConfidence.LOW
    if valid_count >= 5 and improvement >= 3:
        return WindowConfidence.HIGH
    return WindowConfidence.MEDIUM


def recompute_working_window(
    evidence: Sequence[WindowEvidence],
    context: WindowContextKey,
    *,
    legal_low: Optional[float] = None,
    legal_high: Optional[float] = None,
) -> LearnedWorkingWindow:
    """Recompute a field's learned window from its append-only evidence ledger.

    Deterministic + order-independent + idempotent (duplicate (experiment,outcome)
    rows are de-duplicated by identity here as a safety net). The legal range
    (from `setup_ranges`) is the outer bound; unsuccessful values NARROW the window
    where they lie beyond the successful region."""
    # de-dupe by (experiment_id, outcome_id) — idempotent replay safety net
    seen = {}
    for e in evidence:
        if e.field != context.field:
            continue
        seen[(e.experiment_id, e.outcome_id)] = e
    rows = sorted(seen.values(), key=lambda e: (e.experiment_id, e.outcome_id))

    successful, unsuccessful, ineffective = [], [], []
    exp_ids, cp_ids, sess_ids, corners, provenance = [], [], [], [], []
    improvement = regression = unchanged = inconclusive = valid = 0
    # directional tallies
    dir_imp = {"increase": 0, "decrease": 0}
    dir_wor = {"increase": 0, "decrease": 0}
    dir_none = {"increase": 0, "decrease": 0}
    dir_strong_wor = {"increase": 0, "decrease": 0}
    has_direct = False

    for e in rows:
        tv = _as_float(e.to_value)
        if e.contribution == WindowContribution.NONE:
            inconclusive += 1
            continue
        valid += 1
        exp_ids.append(e.experiment_id)
        if e.checkpoint_id:
            cp_ids.append(e.checkpoint_id)
        if e.session_id:
            sess_ids.append(e.session_id)
        corners.extend(e.corners)
        if e.is_direct:
            has_direct = True
        d = e.direction.value if e.direction in (Direction.INCREASE, Direction.DECREASE) else None
        if e.contribution == WindowContribution.SUCCESSFUL:
            improvement += 1
            if tv is not None:
                successful.append(tv)
            if d:
                dir_imp[d] += 1
            provenance.append(f"improved:{e.outcome_status}:{e.experiment_id}")
        elif e.contribution == WindowContribution.UNSUCCESSFUL:
            regression += 1
            if tv is not None:
                unsuccessful.append(tv)
            if d:
                dir_wor[d] += 1
                if e.attribution_confidence == "high":
                    dir_strong_wor[d] += 1
            provenance.append(f"regressed:{e.experiment_id}")
        elif e.contribution == WindowContribution.INEFFECTIVE:
            unchanged += 1
            if tv is not None:
                ineffective.append(tv)
            if d:
                dir_none[d] += 1
            provenance.append(f"unchanged:{e.experiment_id}")

    # contradiction: a value/direction both improved and regressed
    contradiction = any(dir_imp[d] > 0 and dir_wor[d] > 0 for d in ("increase", "decrease"))

    # bounds: start from legal range, narrow by regressions beyond the successful region
    low, high = legal_low, legal_high
    center = _median(sorted(successful)) if successful else None
    warnings = []
    if unsuccessful and center is not None:
        for uv in unsuccessful:
            if uv > center and (high is None or uv < high):
                high = uv               # a higher value regressed → cap above center
            elif uv < center and (low is None or uv > low):
                low = uv                # a lower value regressed → cap below center
    if not has_direct and valid > 0:
        warnings.append("only inherited cross-context evidence (lower confidence)")

    directional = []
    for d in ("increase", "decrease"):
        imp, wor, non = dir_imp[d], dir_wor[d], dir_none[d]
        if imp and wor:
            eff = DirectionEffect.MIXED
        elif imp:
            eff = DirectionEffect.IMPROVED
        elif wor:
            eff = DirectionEffect.WORSENED
        elif non:
            eff = DirectionEffect.NO_EFFECT
        else:
            eff = DirectionEffect.UNKNOWN
        # a direction locks when it repeatedly regressed with no compatible improvement
        strong = dir_strong_wor[d]
        locked = (imp == 0) and (
            strong >= LOCKOUT_MIN_STRONG_REGRESSIONS or wor >= LOCKOUT_MIN_WEAK_REGRESSIONS)
        reason = ""
        if locked:
            reason = (f"{d} worsened the target {wor}× "
                      f"({strong} strong) with no confirmed improvement")
        directional.append(DirectionalEvidence(
            direction=d, effect=eff, improved_count=imp, worsened_count=wor,
            no_effect_count=non, locked_out=locked, lockout_reason=reason))

    confidence = _grade(valid, contradiction, improvement)
    if valid == 1:
        warnings.append("single experiment — window is provisional, not proven")

    return LearnedWorkingWindow(
        context=context, field=context.field,
        successful_values=tuple(sorted(successful)),
        unsuccessful_values=tuple(sorted(unsuccessful)),
        ineffective_values=tuple(sorted(ineffective)),
        low_bound=low, high_bound=high, preferred_center=center,
        valid_experiment_count=valid, improvement_count=improvement,
        regression_count=regression, unchanged_count=unchanged,
        inconclusive_count=inconclusive, confidence=confidence,
        provenance=tuple(provenance),
        supporting_experiment_ids=tuple(dict.fromkeys(exp_ids)),
        supporting_checkpoint_ids=tuple(dict.fromkeys(cp_ids)),
        supporting_session_ids=tuple(dict.fromkeys(sess_ids)),
        corners=tuple(dict.fromkeys(c for c in corners if c)),
        directional=tuple(directional), contradiction=contradiction,
        has_direct_evidence=has_direct, warnings=tuple(dict.fromkeys(warnings)))
