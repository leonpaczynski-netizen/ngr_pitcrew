"""Canonical setup-decision status authority (Engineering Brain Phase 4).

ONE pure authority for the driver-facing ENGINEERING DECISION STATE — the single
answer the UI renders instead of re-deriving status strings in several places.

It does NOT replace the Phase 2 experiment lifecycle or the Phase 3 outcome status
(those own transitions + evidence judgement). It COMPOSES their states plus the
recommendation status and the saved-vs-applied-in-GT7 apply state into one
driver-facing decision, and makes contradictions explicit (INVALID / inconsistent)
rather than papering over them.

This authority is advisory/derivative: it never applies or reverts a setup. The
frozen Apply-gate predicate (`_status_approved` in the Setup Builder) is unchanged;
this authority reads the same inputs but adds no new gate.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Tuple


SETUP_DECISION_VERSION = "setup_decision_status_v1"


class SetupDecisionState(str, Enum):
    NO_RECOMMENDATION = "no_recommendation"
    EVIDENCE_REQUIRED = "evidence_required"
    RECOMMENDATION_READY = "recommendation_ready"
    READY_FOR_APPLY = "ready_for_apply"
    APPLIED = "applied"
    TEST_REQUIRED = "test_required"
    READY_FOR_REVIEW = "ready_for_review"
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    REVERTED = "reverted"
    INVALID = "invalid"


class DecisionAction(str, Enum):
    ANALYSE = "analyse"
    APPLY_IN_GT7 = "apply_in_game"
    DRIVE_TEST_LAPS = "drive_test_laps"
    REVIEW_OUTCOME = "review_outcome"
    RETAIN = "retain"
    PROTECT_WINDOW = "protect_working_window"
    REVERT = "revert_to_parent"
    ISOLATE_FIELD = "isolate_field"
    GATHER_MORE_EVIDENCE = "gather_more_evidence"


@dataclass(frozen=True)
class SetupDecisionResult:
    state: SetupDecisionState
    message_key: str
    reason_codes: Tuple[str, ...] = ()
    allowed_actions: Tuple[str, ...] = ()
    blocked_actions: Tuple[str, ...] = ()
    confidence: str = ""
    source_states: Mapping[str, str] = field(default_factory=dict)
    inconsistencies: Tuple[str, ...] = ()
    eval_version: str = SETUP_DECISION_VERSION

    @property
    def is_inconsistent(self) -> bool:
        return bool(self.inconsistencies)

    def to_dict(self) -> dict:
        return {
            "state": self.state.value, "message_key": self.message_key,
            "reason_codes": list(self.reason_codes),
            "allowed_actions": list(self.allowed_actions),
            "blocked_actions": list(self.blocked_actions),
            "confidence": self.confidence, "source_states": dict(self.source_states),
            "inconsistencies": list(self.inconsistencies),
            "eval_version": self.eval_version,
        }


# Allowed/blocked driver actions per state (deterministic; never automatic).
_ACTIONS = {
    SetupDecisionState.NO_RECOMMENDATION: ((DecisionAction.ANALYSE,), (DecisionAction.APPLY_IN_GT7, DecisionAction.REVIEW_OUTCOME)),
    SetupDecisionState.EVIDENCE_REQUIRED: ((DecisionAction.GATHER_MORE_EVIDENCE, DecisionAction.ANALYSE), (DecisionAction.APPLY_IN_GT7,)),
    SetupDecisionState.RECOMMENDATION_READY: ((DecisionAction.APPLY_IN_GT7,), (DecisionAction.REVIEW_OUTCOME,)),
    SetupDecisionState.READY_FOR_APPLY: ((DecisionAction.APPLY_IN_GT7,), (DecisionAction.REVIEW_OUTCOME,)),
    SetupDecisionState.APPLIED: ((DecisionAction.DRIVE_TEST_LAPS, DecisionAction.REVIEW_OUTCOME), (DecisionAction.APPLY_IN_GT7,)),
    SetupDecisionState.TEST_REQUIRED: ((DecisionAction.DRIVE_TEST_LAPS, DecisionAction.REVIEW_OUTCOME), (DecisionAction.APPLY_IN_GT7,)),
    SetupDecisionState.READY_FOR_REVIEW: ((DecisionAction.REVIEW_OUTCOME,), (DecisionAction.APPLY_IN_GT7,)),
    SetupDecisionState.CONFIRMED: ((DecisionAction.RETAIN, DecisionAction.PROTECT_WINDOW), (DecisionAction.REVERT,)),
    SetupDecisionState.PARTIAL: ((DecisionAction.DRIVE_TEST_LAPS, DecisionAction.ISOLATE_FIELD, DecisionAction.RETAIN), ()),
    SetupDecisionState.REJECTED: ((DecisionAction.REVERT, DecisionAction.ANALYSE), (DecisionAction.RETAIN,)),
    SetupDecisionState.INCONCLUSIVE: ((DecisionAction.DRIVE_TEST_LAPS, DecisionAction.GATHER_MORE_EVIDENCE), ()),
    SetupDecisionState.REVERTED: ((DecisionAction.ANALYSE,), (DecisionAction.RETAIN,)),
    SetupDecisionState.INVALID: ((), (DecisionAction.APPLY_IN_GT7, DecisionAction.RETAIN, DecisionAction.REVERT)),
}


def _actions_for(state: SetupDecisionState) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    allowed, blocked = _ACTIONS.get(state, ((), ()))
    return tuple(a.value for a in allowed), tuple(b.value for b in blocked)


# Phase 3 outcome status → driver-facing decision.
_OUTCOME_MAP = {
    "confirmed_improvement": SetupDecisionState.CONFIRMED,
    "partial_improvement": SetupDecisionState.PARTIAL,
    "regression": SetupDecisionState.REJECTED,
    "no_meaningful_change": SetupDecisionState.INCONCLUSIVE,
    "confounded": SetupDecisionState.INCONCLUSIVE,
    "insufficient_evidence": SetupDecisionState.INCONCLUSIVE,
}

# Phase 2 lifecycle → driver-facing decision (before an outcome exists).
_LIFECYCLE_MAP = {
    "draft": SetupDecisionState.RECOMMENDATION_READY,
    "ready_for_apply": SetupDecisionState.READY_FOR_APPLY,
    "applied": SetupDecisionState.TEST_REQUIRED,
    "test_in_progress": SetupDecisionState.TEST_REQUIRED,
    "ready_for_review": SetupDecisionState.READY_FOR_REVIEW,
    "completed": SetupDecisionState.CONFIRMED,     # only valid WITH an outcome
    "rejected": SetupDecisionState.REJECTED,
    "reverted": SetupDecisionState.REVERTED,
    "cancelled": SetupDecisionState.INVALID,
    "invalid": SetupDecisionState.INVALID,
}


def resolve_setup_decision(
    *,
    recommendation_status: str = "",
    approved_statuses: Optional[frozenset] = None,
    experiment_status: str = "",
    apply_state: str = "",
    applied_match_state: str = "",
    outcome_status: str = "",
    outcome_confidence_level: str = "",
    rollback_eligible: bool = False,
    evidence_ready: Optional[bool] = None,
) -> SetupDecisionResult:
    """Resolve the single driver-facing setup-decision state from the composed
    inputs. Precedence: a persisted Phase-3 OUTCOME wins; else the Phase-2 LIFECYCLE;
    else the recommendation status. Contradictions become INVALID / inconsistent."""
    if approved_statuses is None:
        try:
            from strategy._setup_constants import APPROVED_STATUSES, EVIDENCE_REQUIRED_STATUS
            approved_statuses = APPROVED_STATUSES
            evidence_required = EVIDENCE_REQUIRED_STATUS
        except Exception:
            approved_statuses = frozenset()
            evidence_required = "evidence_required"
    else:
        evidence_required = "evidence_required"

    sources = {
        "recommendation_status": recommendation_status or "",
        "experiment_status": experiment_status or "",
        "apply_state": apply_state or "",
        "applied_match_state": applied_match_state or "",
        "outcome_status": outcome_status or "",
    }
    inconsistencies = []
    reasons = []

    # --- contradiction checks ------------------------------------------------
    if experiment_status == "applied" and apply_state and apply_state == "not_saved":
        inconsistencies.append("experiment marked APPLIED but no setup is saved")
    if applied_match_state == "mismatch":
        reasons.append("applied values differ from the recommendation")
    if experiment_status == "completed" and not outcome_status:
        inconsistencies.append("experiment COMPLETED without a persisted outcome")

    # --- resolve state (outcome > lifecycle > recommendation) ----------------
    if outcome_status:
        state = _OUTCOME_MAP.get(outcome_status, SetupDecisionState.INCONCLUSIVE)
        if experiment_status == "reverted":
            state = SetupDecisionState.REVERTED
        confidence = outcome_confidence_level or ""
    elif experiment_status:
        state = _LIFECYCLE_MAP.get(experiment_status, SetupDecisionState.INVALID)
        if experiment_status == "completed" and not outcome_status:
            state = SetupDecisionState.INVALID       # honest: no outcome backs it
        confidence = ""
    elif recommendation_status:
        if recommendation_status in approved_statuses:
            state = SetupDecisionState.RECOMMENDATION_READY
        elif recommendation_status == evidence_required:
            state = SetupDecisionState.EVIDENCE_REQUIRED
        else:
            state = SetupDecisionState.NO_RECOMMENDATION
        confidence = ""
    else:
        state = SetupDecisionState.NO_RECOMMENDATION
        confidence = ""

    if inconsistencies:
        state = SetupDecisionState.INVALID

    allowed, blocked = _actions_for(state)
    if rollback_eligible and DecisionAction.REVERT.value not in allowed \
            and state not in (SetupDecisionState.CONFIRMED,):
        allowed = allowed + (DecisionAction.REVERT.value,)

    return SetupDecisionResult(
        state=state, message_key=f"setup_decision.{state.value}",
        reason_codes=tuple(reasons), allowed_actions=allowed, blocked_actions=blocked,
        confidence=confidence, source_states=sources,
        inconsistencies=tuple(inconsistencies))
