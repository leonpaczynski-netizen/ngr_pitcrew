"""Multi-symptom experiment planning (Engineering Brain Phase 6).

Turns a canonical engineering-state snapshot (residual issues) into a deterministic,
ordered engineering development plan: AT MOST ONE immediate setup experiment (via the
Phase 5 selector) plus queued hypotheses, deferred/blocked issues, dependencies,
conflicts, invalidation triggers and honest no-selection.

Doctrine:
  * One controlled experiment at a time — a multi-symptom plan is NOT permission to
    apply several changes; the queue is a living plan of hypotheses.
  * Regressions take priority; damage to confirmed-good behaviour outranks a weak
    pre-existing issue.
  * Repeated valid evidence outweighs one-offs (severity/recurrence from Phase 4/6).
  * Residual problems are not automatically setup problems (gearing / drive-out /
    tyre-fuel / driver-technique / evidence-limited routes exist).
  * Subordinate to the Phase-4 `resolve_setup_decision` authority and every Phase-5
    candidate gate.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock (the caller supplies plan_id + generated_at); stable documented
tie-break.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.setup_synthesis import PARAMETER_INTERACTIONS
from strategy.engineering_issue import (
    ResidualIssue, ResidualState, IssueRelevance, residual_severity_rank)


EXPERIMENT_PLANNING_VERSION = "experiment_planning_v1"


# --------------------------------------------------------------------------- #
# Priority
# --------------------------------------------------------------------------- #
# Precedence tiers (lower number = higher priority). Documented in the Phase 6 doc.
TIER_NEW_REGRESSION = 1          # new serious regression
TIER_DAMAGED_GOOD = 2            # damaged confirmed-good behaviour
TIER_HIGH_RECURRENCE = 3        # high-recurrence control/stability problem still present
TIER_PERSISTENT_DOMINANT = 4    # persistent dominant setup issue
TIER_DRIVE_OUT_GEARING = 5      # drive-out / gearing with repeated evidence
TIER_TYRE_FUEL = 6
TIER_CONSISTENCY = 7
TIER_WEAK = 8                    # weakly-evidenced / isolated
TIER_EVIDENCE = 9               # evidence-gathering only
TIER_NONE = 99                  # excluded / not actionable

# Hard-exclusion reason codes.
X_RESOLVED = "already_resolved"
X_CONFIRMED_GOOD = "confirmed_good"
X_NOT_OBSERVED = "not_observed"
X_INSUFFICIENT = "insufficient_evidence"
X_INVALID = "invalid_comparison"
X_AMBIGUOUS = "ambiguous_evidence"
X_OUT_OF_SCOPE = "out_of_scope"
X_NOT_SETUP = "not_a_setup_issue"
X_DECISION_BLOCKS = "setup_decision_blocks"


class ActionKind(str, Enum):
    SETUP_EXPERIMENT = "setup_experiment"
    GEARING_REVIEW = "gearing_review"
    DRIVE_OUT_REVIEW = "drive_out_review"
    DRIVER_TECHNIQUE_OBSERVATION = "driver_technique_observation"
    CONTROLLED_REPEAT_TEST = "controlled_repeat_test"
    EVIDENCE_REQUEST = "evidence_request"
    RETAIN_SETUP = "retain_setup"
    NONE = "none"


@dataclass(frozen=True)
class IssuePriority:
    issue_key: str
    issue_type: str
    residual_state: str
    tier: int
    action_kind: ActionKind
    actionable_as_setup: bool
    exclusion_reasons: Tuple[str, ...]
    reasoning: str
    severity_rank: int
    test_affected: int

    def to_dict(self) -> dict:
        return {"issue_key": self.issue_key, "issue_type": self.issue_type,
                "residual_state": self.residual_state, "tier": self.tier,
                "action_kind": self.action_kind.value,
                "actionable_as_setup": self.actionable_as_setup,
                "exclusion_reasons": list(self.exclusion_reasons),
                "reasoning": self.reasoning, "severity_rank": self.severity_rank,
                "test_affected": self.test_affected}


_EXCLUDE_STATES = {
    ResidualState.RESOLVED: X_RESOLVED,
    ResidualState.CONFIRMED_GOOD: X_CONFIRMED_GOOD,
    ResidualState.NOT_OBSERVED: X_NOT_OBSERVED,
    ResidualState.INSUFFICIENT_EVIDENCE: X_INSUFFICIENT,
    ResidualState.INVALID_COMPARISON: X_INVALID,
    ResidualState.AMBIGUOUS: X_AMBIGUOUS,
    ResidualState.OUT_OF_SCOPE: X_OUT_OF_SCOPE,
}


def _action_for_relevance(relevance: str) -> ActionKind:
    return {
        IssueRelevance.SETUP.value: ActionKind.SETUP_EXPERIMENT,
        IssueRelevance.GEARING.value: ActionKind.GEARING_REVIEW,
        IssueRelevance.DRIVE_OUT.value: ActionKind.DRIVE_OUT_REVIEW,
        IssueRelevance.DRIVER_TECHNIQUE.value: ActionKind.DRIVER_TECHNIQUE_OBSERVATION,
        IssueRelevance.TYRE_FUEL.value: ActionKind.EVIDENCE_REQUEST,
        IssueRelevance.EVIDENCE_LIMITED.value: ActionKind.EVIDENCE_REQUEST,
    }.get(relevance, ActionKind.EVIDENCE_REQUEST)


def _tier_for(ri: ResidualIssue) -> int:
    st = ri.residual_state
    if st == ResidualState.GOOD_BEHAVIOUR_DAMAGED:
        return TIER_DAMAGED_GOOD
    if st == ResidualState.NEW:
        return TIER_NEW_REGRESSION
    if ri.setup_relevance in (IssueRelevance.GEARING.value, IssueRelevance.DRIVE_OUT.value):
        return TIER_DRIVE_OUT_GEARING
    if ri.setup_relevance == IssueRelevance.TYRE_FUEL.value:
        return TIER_TYRE_FUEL
    if st == ResidualState.WORSENED:
        return TIER_HIGH_RECURRENCE
    if st == ResidualState.UNCHANGED:
        return (TIER_HIGH_RECURRENCE if ri.test_class == "strongly_recurring"
                else TIER_PERSISTENT_DOMINANT)
    if st == ResidualState.IMPROVED_BUT_PRESENT:
        return TIER_PERSISTENT_DOMINANT
    return TIER_WEAK


def prioritise_issues(
    residual_issues: Sequence[ResidualIssue], *, decision_blocks: bool = False,
) -> Tuple[IssuePriority, ...]:
    """Deterministic multi-stage prioritisation with hard exclusion first.

    Stable ordering: (tier, -severity, -test_affected, issue_key). Setup-relevant,
    still-present, sufficiently-evidenced issues are actionable as a setup experiment;
    gearing/drive-out/tyre-fuel/technique issues are actionable only as their own
    review/evidence task (never silently a suspension/LSD experiment)."""
    out = []
    for ri in residual_issues:
        exclude = _EXCLUDE_STATES.get(ri.residual_state)
        if decision_blocks:
            exclude = exclude or X_DECISION_BLOCKS
        relevance = ri.setup_relevance
        setup_actionable = (exclude is None
                            and relevance == IssueRelevance.SETUP.value
                            and ri.still_present)
        action = (ActionKind.NONE if exclude and exclude != X_DECISION_BLOCKS
                  else _action_for_relevance(relevance))
        tier = TIER_NONE if (exclude or not ri.still_present) else _tier_for(ri)
        reasons = ()
        if exclude:
            reasons = (exclude,)
        elif relevance != IssueRelevance.SETUP.value:
            reasons = (X_NOT_SETUP,)
        out.append(IssuePriority(
            issue_key=ri.key, issue_type=ri.identity.issue_type,
            residual_state=ri.residual_state.value, tier=tier, action_kind=action,
            actionable_as_setup=setup_actionable, exclusion_reasons=reasons,
            reasoning=ri.reasoning, severity_rank=residual_severity_rank(ri.residual_state),
            test_affected=ri.test_affected))
    return tuple(sorted(out, key=lambda p: (p.tier, -p.severity_rank,
                                            -p.test_affected, p.issue_key)))


# --------------------------------------------------------------------------- #
# Conflict detection
# --------------------------------------------------------------------------- #
class ConflictType(str, Enum):
    SAME_FIELD_OPPOSITE = "same_field_opposite_directions"
    STRONG_INTERACTION = "strong_field_interaction"
    SHARED_SYMPTOM_DIFFERENT_CAUSE = "shared_symptom_different_cause"
    PROTECTED_GOOD = "protected_good_conflict"


@dataclass(frozen=True)
class ExperimentConflict:
    conflict_type: ConflictType
    field_a: str
    field_b: str
    detail: str

    def to_dict(self) -> dict:
        return {"conflict_type": self.conflict_type.value, "field_a": self.field_a,
                "field_b": self.field_b, "detail": self.detail}


def _shared_axes(field_a: str, field_b: str) -> Tuple[str, ...]:
    a = PARAMETER_INTERACTIONS.get(field_a, {})
    b = PARAMETER_INTERACTIONS.get(field_b, {})
    return tuple(sorted(set(a) & set(b)))


def detect_conflicts(candidates: Sequence[Mapping]) -> Tuple[ExperimentConflict, ...]:
    """Detect conflicts among candidate experiments (each a CandidateExperiment dict).
    Same field opposite directions, and strongly-interacting different fields, are
    surfaced explicitly — the planner must not resolve them arbitrarily."""
    out = []
    seen_pairs = set()
    for i, ca in enumerate(candidates):
        fa, da = str(ca.get("field") or ""), str(ca.get("direction") or "")
        pa = ca.get("protected_behaviours_at_risk") or []
        if pa:
            out.append(ExperimentConflict(
                ConflictType.PROTECTED_GOOD, fa, "",
                f"{fa} risks: {', '.join(str(x) for x in pa)}"))
        for cb in candidates[i + 1:]:
            fb, db = str(cb.get("field") or ""), str(cb.get("direction") or "")
            pair = tuple(sorted((ca.get("candidate_id", ""), cb.get("candidate_id", ""))))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if fa and fa == fb and da != db and da and db:
                out.append(ExperimentConflict(
                    ConflictType.SAME_FIELD_OPPOSITE, fa, fb,
                    f"{fa}: one issue wants {da}, another wants {db}"))
            elif fa and fb and fa != fb:
                shared = _shared_axes(fa, fb)
                if shared:
                    out.append(ExperimentConflict(
                        ConflictType.STRONG_INTERACTION, fa, fb,
                        f"{fa} and {fb} both affect {', '.join(shared)}"))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Issue clustering (transparent, rule-based)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IssueCluster:
    cluster_id: str
    member_keys: Tuple[str, ...]
    grouping_evidence: Tuple[str, ...]
    against_evidence: Tuple[str, ...]
    candidate_shared_causes: Tuple[str, ...]
    confidence: str
    coupled_response_permitted: bool
    isolation_required: bool

    def to_dict(self) -> dict:
        return {"cluster_id": self.cluster_id, "member_keys": list(self.member_keys),
                "grouping_evidence": list(self.grouping_evidence),
                "against_evidence": list(self.against_evidence),
                "candidate_shared_causes": list(self.candidate_shared_causes),
                "confidence": self.confidence,
                "coupled_response_permitted": self.coupled_response_permitted,
                "isolation_required": self.isolation_required}


def cluster_issues(residual_issues: Sequence[ResidualIssue]) -> Tuple[IssueCluster, ...]:
    """Group issues that plausibly share an engineering cause — by (issue_family,
    axle, phase). Rule-based + transparent; NEVER groups on similar wording. A
    cluster always requires an isolated first test (coupled response not permitted
    without proof)."""
    present = [ri for ri in residual_issues if ri.still_present
               and ri.setup_relevance == IssueRelevance.SETUP.value]
    groups: dict = {}
    for ri in present:
        gkey = (ri.identity.issue_family.value, ri.identity.axle, ri.identity.phase)
        groups.setdefault(gkey, []).append(ri)
    out = []
    for gkey, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        fam, axle, phase = gkey
        out.append(IssueCluster(
            cluster_id=f"{fam}:{axle}:{phase}",
            member_keys=tuple(sorted(m.key for m in members)),
            grouping_evidence=(f"same {fam} family",
                               *( (f"same axle {axle}",) if axle else () ),
                               *( (f"same phase {phase}",) if phase else () )),
            against_evidence=tuple(sorted(
                set(m.identity.segment_id for m in members if m.identity.segment_id))),
            candidate_shared_causes=(f"{fam} balance",),
            confidence="medium" if (axle or phase) else "low",
            coupled_response_permitted=False, isolation_required=True))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Development plan
# --------------------------------------------------------------------------- #
class PlanStatus(str, Enum):
    READY = "ready"
    RETAIN_SETUP = "retain_setup"
    EVIDENCE_REQUIRED = "evidence_required"
    BLOCKED = "blocked"
    NO_ACTION = "no_action"


class QueueState(str, Enum):
    READY = "ready"
    WAITING_FOR_CURRENT_EXPERIMENT = "waiting_for_current_experiment"
    WAITING_FOR_EVIDENCE = "waiting_for_evidence"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    RESOLVED_BEFORE_TEST = "resolved_before_test"
    INVALIDATED = "invalidated"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


@dataclass(frozen=True)
class QueuedHypothesis:
    issue_key: str
    issue_type: str
    action_kind: str
    candidate_field: str
    candidate_id: str
    queue_state: str
    reason_queued: str
    depends_on_immediate: bool
    promotion_condition: str
    cancellation_condition: str
    evidence_required: Tuple[str, ...]
    conflicts_with_immediate: bool

    def to_dict(self) -> dict:
        return {"issue_key": self.issue_key, "issue_type": self.issue_type,
                "action_kind": self.action_kind, "candidate_field": self.candidate_field,
                "candidate_id": self.candidate_id, "queue_state": self.queue_state,
                "reason_queued": self.reason_queued,
                "depends_on_immediate": self.depends_on_immediate,
                "promotion_condition": self.promotion_condition,
                "cancellation_condition": self.cancellation_condition,
                "evidence_required": list(self.evidence_required),
                "conflicts_with_immediate": self.conflicts_with_immediate}


@dataclass(frozen=True)
class DevelopmentPlan:
    plan_id: str
    scope_fingerprint: str
    applied_checkpoint_id: str
    snapshot_fingerprint: str
    status: PlanStatus
    immediate_experiment: Optional[dict]        # a Phase-5 CandidateExperiment dict, or None
    immediate_test_protocol: Optional[dict]
    immediate_reason: str
    queued: Tuple[QueuedHypothesis, ...]
    deferred_issues: Tuple[dict, ...]
    blocked_issues: Tuple[dict, ...]
    resolved_issues: Tuple[str, ...]
    protected_good: Tuple[str, ...]
    conflicts: Tuple[ExperimentConflict, ...]
    clusters: Tuple[IssueCluster, ...]
    reassessment_triggers: Tuple[str, ...]
    invalidation_triggers: Tuple[str, ...]
    required_evidence: Tuple[str, ...]
    rollback_target: str
    reasoning: str
    content_fingerprint: str
    generated_at: str = ""
    eval_version: str = EXPERIMENT_PLANNING_VERSION

    @property
    def has_immediate(self) -> bool:
        return self.immediate_experiment is not None

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id, "scope_fingerprint": self.scope_fingerprint,
            "applied_checkpoint_id": self.applied_checkpoint_id,
            "snapshot_fingerprint": self.snapshot_fingerprint, "status": self.status.value,
            "immediate_experiment": self.immediate_experiment,
            "immediate_test_protocol": self.immediate_test_protocol,
            "immediate_reason": self.immediate_reason,
            "queued": [q.to_dict() for q in self.queued],
            "deferred_issues": list(self.deferred_issues),
            "blocked_issues": list(self.blocked_issues),
            "resolved_issues": list(self.resolved_issues),
            "protected_good": list(self.protected_good),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "clusters": [c.to_dict() for c in self.clusters],
            "reassessment_triggers": list(self.reassessment_triggers),
            "invalidation_triggers": list(self.invalidation_triggers),
            "required_evidence": list(self.required_evidence),
            "rollback_target": self.rollback_target, "reasoning": self.reasoning,
            "content_fingerprint": self.content_fingerprint,
            "generated_at": self.generated_at, "eval_version": self.eval_version,
        }


_INVALIDATION_TRIGGERS = (
    "applied setup checkpoint changes", "scope fingerprint changes",
    "track or layout changes", "discipline changes", "driver changes",
    "a new experiment outcome is recorded", "a queued issue resolves",
    "a new regression appears", "working-window evidence changes materially",
    "a failed-direction lockout changes", "the canonical setup-decision state changes",
    "evidence becomes contradictory", "the plan is based on stale telemetry",
)


def build_development_plan(
    snapshot,
    prioritised: Sequence[IssuePriority],
    *,
    immediate_selection: Optional[Mapping] = None,
    queued_candidates: Sequence[Mapping] = (),
    rollback_target: str = "",
    plan_id: str = "",
    generated_at: str = "",
    decision_blocks: bool = False,
) -> DevelopmentPlan:
    """Assemble the deterministic development plan: at most ONE immediate experiment
    (the Phase-5 selection, if any), the rest as queued hypotheses, plus deferred /
    blocked / resolved buckets, conflicts and invalidation triggers.

    ``immediate_selection`` is a Phase-5 ``select_experiment`` result dict (or None);
    ``queued_candidates`` are Phase-5 CandidateExperiment dicts for the next issues.
    """
    issues = list(snapshot.residual_issues)
    by_key = {ri.key: ri for ri in issues}

    resolved = tuple(p.issue_key for p in prioritised
                     if p.residual_state == ResidualState.RESOLVED.value)
    protected_good = snapshot.confirmed_good
    blocked = tuple({"issue_key": p.issue_key, "issue_type": p.issue_type,
                     "residual_state": p.residual_state,
                     "reasons": list(p.exclusion_reasons)}
                    for p in prioritised
                    if p.exclusion_reasons and p.tier == TIER_NONE
                    and p.residual_state not in (ResidualState.RESOLVED.value,
                                                 ResidualState.CONFIRMED_GOOD.value,
                                                 ResidualState.NOT_OBSERVED.value))
    deferred = tuple({"issue_key": p.issue_key, "issue_type": p.issue_type,
                      "action_kind": p.action_kind.value, "reasoning": p.reasoning}
                     for p in prioritised
                     if not p.actionable_as_setup and p.tier != TIER_NONE
                     and p.action_kind not in (ActionKind.SETUP_EXPERIMENT,
                                               ActionKind.NONE))

    # immediate experiment
    immediate = None
    immediate_tp = None
    immediate_reason = ""
    sel = immediate_selection or {}
    selected = sel.get("selected") if isinstance(sel, Mapping) else None
    if selected and not decision_blocks:
        immediate = dict(selected)
        immediate_tp = sel.get("test_protocol")
        immediate_reason = selected.get("selection_rationale", "") \
            or "highest-priority isolated setup experiment"

    # conflicts over immediate + queued candidates
    all_cands = ([immediate] if immediate else []) + list(queued_candidates)
    conflicts = detect_conflicts([c for c in all_cands if c])
    clusters = cluster_issues(issues)

    # queued hypotheses
    queued = []
    immediate_field = (immediate or {}).get("field", "")
    for qc in queued_candidates:
        fld = str(qc.get("field") or "")
        conflicts_immediate = any(
            (c.field_a == fld and c.field_b == immediate_field) or
            (c.field_b == fld and c.field_a == immediate_field) or
            (c.field_a == fld and c.conflict_type == ConflictType.PROTECTED_GOOD)
            for c in conflicts) if immediate_field else False
        qstate = (QueueState.WAITING_FOR_CURRENT_EXPERIMENT if immediate
                  else QueueState.READY)
        if qc.get("hard_blockers"):
            qstate = QueueState.BLOCKED
        queued.append(QueuedHypothesis(
            issue_key=str(qc.get("_issue_key") or ""),
            issue_type=str(qc.get("target_issue") or ""),
            action_kind=ActionKind.SETUP_EXPERIMENT.value,
            candidate_field=fld, candidate_id=str(qc.get("candidate_id") or ""),
            queue_state=qstate.value,
            reason_queued=("only one experiment is actionable at a time"
                           if immediate else "awaiting selection"),
            depends_on_immediate=bool(immediate),
            promotion_condition=("the immediate experiment completes and this issue "
                                 "still recurs"),
            cancellation_condition="this issue resolves or the plan is invalidated",
            evidence_required=tuple(qc.get("supporting_evidence") or ()),
            conflicts_with_immediate=conflicts_immediate))

    # status
    if decision_blocks:
        status = PlanStatus.BLOCKED
        reasoning = "the canonical setup-decision authority blocks setup movement"
    elif immediate:
        status = PlanStatus.READY
        reasoning = (f"one isolated experiment selected; {len(queued)} hypothesis(es) "
                     "queued; regressions prioritised")
    elif deferred:
        status = PlanStatus.EVIDENCE_REQUIRED
        reasoning = "no setup experiment justified; review/evidence tasks identified"
    elif any(p.actionable_as_setup for p in prioritised):
        status = PlanStatus.EVIDENCE_REQUIRED
        reasoning = ("actionable setup issues exist but no safe minimum-effective "
                     "experiment was selected — gather more evidence")
    else:
        status = PlanStatus.RETAIN_SETUP
        reasoning = "no actionable setup issue — retain the current setup"

    required_evidence = tuple(dict.fromkeys(snapshot.evidence_gaps))
    reassessment = ("after the immediate experiment is applied and tested",
                    "after more valid laps are recorded")

    payload = {
        "scope": snapshot.scope_fingerprint, "checkpoint": snapshot.applied_checkpoint_id,
        "snapshot": snapshot.content_fingerprint, "status": status.value,
        "immediate": (immediate or {}).get("candidate_id", ""),
        "queued": sorted(q.candidate_id for q in queued),
        "resolved": sorted(resolved),
        "blocked": sorted(b["issue_key"] for b in blocked),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    fingerprint = f"{EXPERIMENT_PLANNING_VERSION}:{hashlib.sha256(raw).hexdigest()[:24]}"

    return DevelopmentPlan(
        plan_id=plan_id or fingerprint, scope_fingerprint=snapshot.scope_fingerprint,
        applied_checkpoint_id=snapshot.applied_checkpoint_id,
        snapshot_fingerprint=snapshot.content_fingerprint, status=status,
        immediate_experiment=immediate, immediate_test_protocol=immediate_tp,
        immediate_reason=immediate_reason, queued=tuple(queued),
        deferred_issues=deferred, blocked_issues=blocked, resolved_issues=resolved,
        protected_good=protected_good, conflicts=conflicts, clusters=clusters,
        reassessment_triggers=reassessment,
        invalidation_triggers=_INVALIDATION_TRIGGERS,
        required_evidence=required_evidence,
        rollback_target=rollback_target or "parent setup", reasoning=reasoning,
        content_fingerprint=fingerprint, generated_at=generated_at)
