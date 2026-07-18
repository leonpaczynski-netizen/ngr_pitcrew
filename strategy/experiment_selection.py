"""Minimum-effective experiment selection (Engineering Brain Phase 5).

Deterministic candidate generation + 5-stage selection of the SMALLEST justified
next setup experiment, gated by evidence and safety. It generates physics-informed
HYPOTHESES to test (via the existing interaction graph) — never a generic
symptom→value lookup, never a multi-field shotgun, never a universal "best" value.

Doctrine (mandatory):
  * Minimum effective intervention — one field, one legal step, reversible.
  * Protect confirmed-good behaviour — a candidate threatening it is blocked/constrained.
  * Negative outcomes are authoritative — a failed direction is not retried.
  * Dead-end prevention via HARD gates, not invisible score penalties.
  * Honest no-selection when no safe experiment is justified.
  * Subordinate to the canonical Phase-4 setup-decision authority.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random
numbers, no wall-clock, no DB/dict-order dependence (stable documented tie-break).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.setup_synthesis import PARAMETER_INTERACTIONS, _round
from strategy.working_window import (
    LearnedWorkingWindow, Direction, WindowConfidence)


EXPERIMENT_SELECTION_VERSION = "experiment_selection_v1"


class Eligibility(str, Enum):
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    DEFERRED = "deferred"


# Hard-block reason codes (exposed; never invisible score penalties).
B_ILLEGAL_VALUE = "illegal_value"
B_EQUALS_CURRENT = "equals_current_value"
B_NO_MEASURABLE_DELTA = "no_measurable_delta"
B_FAILED_DIRECTION = "repeated_failed_direction"
B_PROTECTED_VIOLATION = "protected_behaviour_violation"
B_OUTSIDE_WINDOW = "outside_evidence_window"
B_DISPROVED = "hypothesis_already_disproved"
B_INEFFECTIVE = "direction_already_ineffective"
B_INVALID_SCOPE = "invalid_scope"
B_NOT_REVERSIBLE = "not_reversible"
B_NO_LEGAL_RANGE = "no_legal_range"


class NoSelectionReason(str, Enum):
    MORE_EVIDENCE_REQUIRED = "more_evidence_required"
    RESOLVE_CONTRADICTION = "resolve_contradiction"
    REPEAT_CONTROLLED_BASELINE = "repeat_controlled_baseline"
    OUTCOME_REVIEW_REQUIRED = "outcome_review_required"
    RETAIN_CURRENT_SETUP = "retain_current_setup"
    TRACK_OR_CORNER_EVIDENCE_INSUFFICIENT = "track_or_corner_evidence_insufficient"
    NO_LEGAL_MINIMUM_EFFECTIVE_EXPERIMENT = "no_legal_minimum_effective_experiment"
    DECISION_AUTHORITY_BLOCKS = "decision_authority_blocks"


# Symptom → (handling axis, desired sign). Physics-informed hypothesis targets; the
# actual field candidates come from the interaction graph, not a fixed value table.
_SYMPTOM_AXIS: dict = {
    "mid_corner_understeer": ("apex_front_support", +1),
    "front_push": ("apex_front_support", +1),
    "entry_understeer": ("entry_rotation", +1),
    "rear_loose_on_exit": ("power_oversteer_resistance", +1),
    "power_oversteer": ("power_oversteer_resistance", +1),
    "exit_wheelspin": ("exit_traction", +1),
    "poor_traction": ("exit_traction", +1),
    "rear_loose_under_braking": ("trail_braking_stability", +1),
    "braking_instability": ("trail_braking_stability", +1),
    "high_speed_instability": ("high_speed_stability", +1),
    "kerb_instability": ("kerb_compliance", +1),
    "front_lock": ("trail_braking_stability", +1),
}


def legal_step(field_name: str) -> float:
    """The field's minimum meaningful legal increment (one step)."""
    f = field_name.lower()
    if f in ("toe_front", "toe_rear"):
        return 0.01
    if f.startswith("gear_") or f == "final_drive":
        return 0.001
    if f in ("springs_front", "springs_rear", "camber_front", "camber_rear"):
        return 0.1
    return 1.0


def _as_float(v) -> Optional[float]:
    try:
        if v is None or (isinstance(v, str) and not v.strip()) or isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Candidate model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CandidateExperiment:
    candidate_id: str
    target_issue: str
    target_phase: str
    target_corners: Tuple[str, ...]
    field: str
    subsystem: str
    current_value: Optional[float]
    proposed_value: Optional[float]
    delta: Optional[float]
    direction: str
    legal_low: Optional[float]
    legal_high: Optional[float]
    legal_increment: float
    hypothesis: str
    expected_positive_effect: str
    expected_negative_effects: Tuple[str, ...]
    protected_behaviours_at_risk: Tuple[str, ...]
    supporting_evidence: Tuple[str, ...]
    window_relationship: str
    prior_experiment_relationship: str
    directional_relationship: str
    evidence_grade: str
    reversible: bool
    eligibility: Eligibility
    hard_blockers: Tuple[str, ...]
    warnings: Tuple[str, ...]
    isolation_score: int          # 1 = single field (best isolation)
    selection_rationale: str = ""
    rejection_rationale: str = ""
    eval_version: str = EXPERIMENT_SELECTION_VERSION

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id, "target_issue": self.target_issue,
            "target_phase": self.target_phase,
            "target_corners": list(self.target_corners), "field": self.field,
            "subsystem": self.subsystem, "current_value": self.current_value,
            "proposed_value": self.proposed_value, "delta": self.delta,
            "direction": self.direction, "legal_low": self.legal_low,
            "legal_high": self.legal_high, "legal_increment": self.legal_increment,
            "hypothesis": self.hypothesis,
            "expected_positive_effect": self.expected_positive_effect,
            "expected_negative_effects": list(self.expected_negative_effects),
            "protected_behaviours_at_risk": list(self.protected_behaviours_at_risk),
            "supporting_evidence": list(self.supporting_evidence),
            "window_relationship": self.window_relationship,
            "prior_experiment_relationship": self.prior_experiment_relationship,
            "directional_relationship": self.directional_relationship,
            "evidence_grade": self.evidence_grade, "reversible": self.reversible,
            "eligibility": self.eligibility.value,
            "hard_blockers": list(self.hard_blockers), "warnings": list(self.warnings),
            "isolation_score": self.isolation_score,
            "selection_rationale": self.selection_rationale,
            "rejection_rationale": self.rejection_rationale,
            "eval_version": self.eval_version,
        }


@dataclass(frozen=True)
class SelectionContext:
    """Structured inputs for candidate generation (built by the DB orchestrator)."""

    scope_fingerprint: str
    car: str = ""
    track: str = ""
    layout_id: str = ""
    discipline: str = ""
    dominant_issue: str = ""
    target_phase: str = ""
    target_corners: Tuple[str, ...] = ()
    recurrence_class: str = ""           # isolated/emerging/recurring/strongly_recurring
    valid_lap_count: int = 0
    current_setup: Mapping = field(default_factory=dict)   # {field: value}
    ranges: Mapping = field(default_factory=dict)          # {field: (lo, hi)}
    working_windows: Mapping = field(default_factory=dict)  # {field: LearnedWorkingWindow}
    failed_directions: Tuple[Tuple[str, str], ...] = ()    # (field, direction)
    ineffective_directions: Tuple[Tuple[str, str], ...] = ()
    protected_behaviours: Tuple[dict, ...] = ()            # {behaviour, field, corners}
    already_applied_experiment: bool = False


# --------------------------------------------------------------------------- #
# Candidate generation
# --------------------------------------------------------------------------- #
def _axis_fields(axis: str, sign: int) -> Tuple[Tuple[str, int], ...]:
    """Fields that move ``axis`` in the desired ``sign`` direction, with the field
    move-direction (+1 raise / -1 lower) needed to achieve it."""
    out = []
    for fld, inter in PARAMETER_INTERACTIONS.items():
        eff = inter.get(axis)
        if not eff:
            continue
        # to move axis by +sign, move the field by sign/eff (both ±1)
        move = sign * eff        # +1 → raise field, -1 → lower field
        out.append((fld, 1 if move > 0 else -1))
    return tuple(sorted(out))


def _protected_fields(protected: Sequence[Mapping]) -> frozenset:
    return frozenset(str(p.get("field") or "") for p in protected if p.get("field"))


def _negative_effects(field_name: str, move_dir: int) -> Tuple[str, ...]:
    """Axes this field move WORSENS (interaction sign opposite to the move)."""
    out = []
    for axis, eff in PARAMETER_INTERACTIONS.get(field_name, {}).items():
        signed = move_dir * eff
        if signed < 0:
            out.append(f"may reduce {axis.replace('_', ' ')}")
    return tuple(out)


def generate_candidates(ctx: SelectionContext) -> Tuple[CandidateExperiment, ...]:
    """Generate minimum-effective single-field candidate experiments for the
    dominant issue. Each proposes ONE legal step of ONE field, in the direction the
    interaction graph says serves the target — gated by evidence + safety."""
    issue = str(ctx.dominant_issue or "").lower()
    axis_sign = _SYMPTOM_AXIS.get(issue)
    if axis_sign is None:
        return ()
    axis, sign = axis_sign
    protected_fields = _protected_fields(ctx.protected_behaviours)
    protected_by_field = {str(p.get("field") or ""): p for p in ctx.protected_behaviours}
    failed = set(ctx.failed_directions)
    ineffective = set(ctx.ineffective_directions)

    candidates = []
    for fld, move_dir in _axis_fields(axis, sign):
        if fld not in ctx.current_setup:
            continue
        cur = _as_float(ctx.current_setup.get(fld))
        rng = ctx.ranges.get(fld)
        lo = hi = None
        if isinstance(rng, (tuple, list)) and len(rng) == 2:
            lo, hi = _as_float(rng[0]), _as_float(rng[1])
        step = legal_step(fld)
        direction = "increase" if move_dir > 0 else "decrease"
        proposed = None if cur is None else _round(fld, cur + move_dir * step)
        delta = None if (proposed is None or cur is None) else round(proposed - cur, 4)

        win: Optional[LearnedWorkingWindow] = ctx.working_windows.get(fld)
        blockers = []
        warnings = []

        # --- hard gates -----------------------------------------------------
        if lo is None or hi is None:
            blockers.append(B_NO_LEGAL_RANGE)
        if proposed is not None and lo is not None and hi is not None \
                and (proposed < lo or proposed > hi):
            blockers.append(B_ILLEGAL_VALUE)
        if delta is not None and abs(delta) < 1e-9:
            blockers.append(B_EQUALS_CURRENT)
        if delta is not None and abs(delta) < step * 0.5:
            blockers.append(B_NO_MEASURABLE_DELTA)
        if (fld, direction) in failed:
            blockers.append(B_FAILED_DIRECTION)
        if (fld, direction) in ineffective:
            blockers.append(B_INEFFECTIVE)
        if fld in protected_fields:
            blockers.append(B_PROTECTED_VIOLATION)
        # window lockout / disproved direction
        window_rel = "no learned window"
        directional_rel = "unknown direction"
        if win is not None:
            if direction in win.locked_directions():
                blockers.append(B_DISPROVED)
                directional_rel = f"{direction} is locked out by prior regression"
            elif proposed is not None and win.unsuccessful_values \
                    and proposed in win.unsuccessful_values:
                blockers.append(B_DISPROVED)
                directional_rel = "value already failed"
            else:
                for d in win.directional:
                    if d.direction == direction:
                        directional_rel = f"{direction}: {d.effect.value}"
            if win.preferred_center is not None:
                if proposed is not None and win.low_bound is not None \
                        and win.high_bound is not None \
                        and not (win.low_bound <= proposed <= win.high_bound):
                    warnings.append("proposed value outside the evidence-backed window")
                window_rel = (f"center {win.preferred_center}, "
                              f"window [{win.low_bound},{win.high_bound}], "
                              f"{win.confidence.value}")
            elif win.is_evidenced:
                window_rel = f"{win.confidence.value} (no proven center)"

        # protected-behaviour RISK (coupled negative effects that touch a protected corner/field)
        neg = _negative_effects(fld, move_dir)
        at_risk = []
        for p in ctx.protected_behaviours:
            beh = str(p.get("behaviour") or "")
            # a coupled negative on the axis that this protected behaviour represents
            if beh and neg:
                at_risk.append(beh)
        # constrain (warn) rather than hard-block unless the field IS the protected field
        if at_risk and B_PROTECTED_VIOLATION not in blockers:
            warnings.append("may affect a confirmed-good behaviour — monitor closely")

        eligibility = Eligibility.BLOCKED if blockers else Eligibility.ELIGIBLE
        grade = _candidate_grade(ctx, win)
        supporting = _supporting_evidence(ctx, win)
        prior_rel = _prior_relationship(ctx, fld, direction)

        candidates.append(CandidateExperiment(
            candidate_id=f"{fld}:{direction}",
            target_issue=ctx.dominant_issue, target_phase=ctx.target_phase,
            target_corners=ctx.target_corners, field=fld,
            subsystem=_subsystem(fld), current_value=cur, proposed_value=proposed,
            delta=delta, direction=direction, legal_low=lo, legal_high=hi,
            legal_increment=step,
            hypothesis=(f"one {direction} step of {fld.replace('_',' ')} should "
                        f"improve {axis.replace('_',' ')} to address {ctx.dominant_issue}"),
            expected_positive_effect=f"improve {axis.replace('_',' ')}",
            expected_negative_effects=neg,
            protected_behaviours_at_risk=tuple(dict.fromkeys(at_risk)),
            supporting_evidence=supporting, window_relationship=window_rel,
            prior_experiment_relationship=prior_rel,
            directional_relationship=directional_rel, evidence_grade=grade,
            reversible=True, eligibility=eligibility,
            hard_blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            isolation_score=1))
    return tuple(candidates)


def _subsystem(field_name: str) -> str:
    f = field_name.lower()
    for k, s in (("arb", "anti_roll_bar"), ("aero", "aero"), ("lsd", "lsd"),
                 ("toe", "alignment"), ("camber", "alignment"), ("brake", "brakes"),
                 ("spring", "suspension"), ("ride_height", "ride_height"),
                 ("gear", "gearbox"), ("final_drive", "gearbox")):
        if k in f:
            return s
    return ""


def _candidate_grade(ctx: SelectionContext, win) -> str:
    rc = str(ctx.recurrence_class or "")
    if rc in ("strongly_recurring", "recurring") and ctx.valid_lap_count >= 4:
        base = "high"
    elif rc in ("recurring", "emerging"):
        base = "medium"
    else:
        base = "low"
    if win is not None and win.confidence == WindowConfidence.HIGH and base != "low":
        return "high"
    return base


def _supporting_evidence(ctx: SelectionContext, win) -> Tuple[str, ...]:
    ev = []
    if ctx.recurrence_class:
        ev.append(f"target issue {ctx.recurrence_class} over {ctx.valid_lap_count} valid laps")
    if win is not None and win.is_evidenced:
        ev.append(f"learned window: {win.confidence.value} "
                  f"({win.improvement_count}↑/{win.regression_count}↓)")
    return tuple(ev)


def _prior_relationship(ctx: SelectionContext, fld: str, direction: str) -> str:
    if (fld, direction) in set(ctx.failed_directions):
        return "same direction previously worsened the car"
    if (fld, direction) in set(ctx.ineffective_directions):
        return "same direction previously had no effect"
    win = ctx.working_windows.get(fld)
    if win is not None and win.is_evidenced:
        return f"field has {win.valid_experiment_count} prior valid experiment(s)"
    return "not previously isolated in this context"


# --------------------------------------------------------------------------- #
# 5-stage deterministic selection
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SelectionResult:
    selected: Optional[CandidateExperiment]
    no_selection_reason: Optional[NoSelectionReason]
    considered: Tuple[CandidateExperiment, ...]
    eligible: Tuple[CandidateExperiment, ...]
    rejected: Tuple[CandidateExperiment, ...]
    rationale: str
    eval_version: str = EXPERIMENT_SELECTION_VERSION

    @property
    def has_selection(self) -> bool:
        return self.selected is not None

    def to_dict(self) -> dict:
        return {
            "selected": (self.selected.to_dict() if self.selected else None),
            "no_selection_reason": (self.no_selection_reason.value
                                    if self.no_selection_reason else None),
            "considered": [c.to_dict() for c in self.considered],
            "eligible": [c.to_dict() for c in self.eligible],
            "rejected": [c.to_dict() for c in self.rejected],
            "rationale": self.rationale, "eval_version": self.eval_version,
        }


# Deterministic tie-break key: fewer negative effects, fewer at-risk behaviours,
# stronger evidence grade, then stable field-name order.
_GRADE_RANK = {"high": 0, "medium": 1, "low": 2, "": 3}


def _tiebreak_key(c: CandidateExperiment):
    return (c.isolation_score,                       # 1 field first
            len(c.protected_behaviours_at_risk),      # least risk to protected
            len(c.expected_negative_effects),         # fewest coupled negatives
            _GRADE_RANK.get(c.evidence_grade, 3),     # strongest evidence
            c.field, c.direction)                     # stable name order


def select_experiment(
    candidates: Sequence[CandidateExperiment],
    *,
    decision_state: str = "",
    decision_blocks: bool = False,
    recurrence_class: str = "",
    valid_lap_count: int = 0,
    min_valid_laps: int = 3,
    min_recurrence: str = "recurring",
) -> SelectionResult:
    """Deterministic 5-stage selection. Hard gates run first; the smallest,
    best-isolated, lowest-risk eligible candidate wins with a stable tie-break;
    honest no-selection when nothing is justified."""
    considered = tuple(candidates)

    # Stage 0: subordinate to the canonical decision authority.
    if decision_blocks:
        return SelectionResult(
            None, NoSelectionReason.DECISION_AUTHORITY_BLOCKS, considered, (), considered,
            "the canonical setup-decision authority blocks setup movement")

    # Stage 1: hard eligibility.
    eligible = tuple(c for c in considered if c.eligibility == Eligibility.ELIGIBLE)
    rejected = tuple(c for c in considered if c.eligibility != Eligibility.ELIGIBLE)
    if not eligible:
        reason = (NoSelectionReason.NO_LEGAL_MINIMUM_EFFECTIVE_EXPERIMENT
                  if considered else NoSelectionReason.RETAIN_CURRENT_SETUP)
        return SelectionResult(
            None, reason, considered, (), rejected,
            "no candidate passed the hard eligibility gates")

    # Stage 2: evidence sufficiency (defer if the target isn't repeatable enough).
    rank = {"isolated": 0, "emerging": 1, "recurring": 2, "strongly_recurring": 3}
    if (rank.get(recurrence_class, 0) < rank.get(min_recurrence, 2)
            or valid_lap_count < min_valid_laps):
        return SelectionResult(
            None, NoSelectionReason.TRACK_OR_CORNER_EVIDENCE_INSUFFICIENT,
            considered, eligible, rejected,
            f"target evidence ({recurrence_class or 'unknown'}, "
            f"{valid_lap_count} valid laps) is below the threshold to justify a change")

    # Stage 3+4: experiment quality + stable deterministic tie-break.
    ordered = sorted(eligible, key=_tiebreak_key)
    winner = ordered[0]
    selected = _stamp(winner, selection_rationale=(
        f"smallest reversible test targeting {winner.target_issue}: "
        f"{winner.field} {winner.direction} one step "
        f"({winner.current_value}→{winner.proposed_value}); "
        f"best isolation, lowest risk, {winner.evidence_grade} evidence"))
    rejected_stamped = tuple(
        _stamp(c, rejection_rationale=(
            "; ".join(c.hard_blockers) if c.hard_blockers
            else "a more isolated / lower-risk candidate was preferred"))
        for c in considered if c.candidate_id != winner.candidate_id)
    return SelectionResult(
        selected, None, considered, ordered, rejected_stamped,
        selected.selection_rationale)


def _stamp(c: CandidateExperiment, *, selection_rationale="", rejection_rationale=""):
    from dataclasses import replace
    return replace(c, selection_rationale=selection_rationale or c.selection_rationale,
                   rejection_rationale=rejection_rationale or c.rejection_rationale)


# --------------------------------------------------------------------------- #
# Test protocol generation
# --------------------------------------------------------------------------- #
def build_test_protocol(
    candidate: CandidateExperiment, *,
    parent_setup_id: str = "", rollback_target: str = "",
    min_valid_laps: int = 4, compound: str = "",
) -> dict:
    """Deterministic structured test protocol for the selected candidate. Invents no
    GT7 environmental data it does not expose."""
    return {
        "field": candidate.field,
        "value_change": {"from": candidate.current_value,
                         "to": candidate.proposed_value, "delta": candidate.delta,
                         "direction": candidate.direction},
        "parent_setup_id": parent_setup_id,
        "rollback_target": rollback_target or parent_setup_id or "parent setup",
        "tyre_compound": compound,
        "min_valid_laps": min_valid_laps,
        "target_corners": list(candidate.target_corners),
        "target_phase": candidate.target_phase,
        "lap_invalidation_conditions": [
            "pit / out / in lap", "off-track excursion", "major incident",
            "pace outlier beyond the clean-lap threshold"],
        "behaviours_to_monitor": list(candidate.protected_behaviours_at_risk)
        or ["target issue recurrence"],
        "success_criteria": [
            f"reduced recurrence of {candidate.target_issue} at the target corners"],
        "regression_criteria": [
            "target issue unchanged or worse",
            *[f"{e}" for e in candidate.expected_negative_effects],
            *[f"protected behaviour '{b}' worsens"
              for b in candidate.protected_behaviours_at_risk]],
        "rollback_conditions": [
            "target issue worse", "a protected behaviour materially regresses"],
        "further_evidence_conditions": [
            f"fewer than {min_valid_laps} valid laps", "ambiguous baseline"],
        "driver_questions": [
            f"did {candidate.target_issue.replace('_',' ')} improve at the target corners?",
            "did braking / rotation / traction feel worse anywhere?"],
        "required_evidence": [
            "checkpoint-tagged per-corner test evidence", "valid clean laps",
            "driver review of the target and protected behaviours"],
        "eval_version": EXPERIMENT_SELECTION_VERSION,
    }
