"""Preparation activity transitions & scheduling (Program 2, Phase 48).

Deterministic, reasoned transition decisions for every preparation activity, plus pure scheduling
helpers (reschedule / cancel / skip / mark-optional) that return NEW activity values — they never
mutate and never persist. Persistence of an activity state is an explicit write elsewhere
(``SessionDB.upsert_preparation_activity``); this module only computes the *view* of what each activity
is waiting on.

Doctrine: viewing or refreshing must NOT advance the cycle. Every function here is a pure function of
its inputs; recomputing produces the same decisions and changes no stored state. Deterministic,
Qt-free, DB-free, offline, no wall-clock, never raises.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from strategy.event_preparation_cycle import (
    EventFormatProfile, PreparationActivity, PreparationActivityState, PreparationActivityType,
    PreparationTransitionDecision, PreparationPhase, _pick_next_activity, _TERMINAL_STATES,
    _iso, _norm,
)

# activity types that require a session/telemetry to be bound to produce evidence
_RUN_TYPES = frozenset({
    PreparationActivityType.INSTALLATION_RUN,
    PreparationActivityType.BASELINE_PRACTICE,
    PreparationActivityType.SETUP_EXPERIMENT,
    PreparationActivityType.COACHING_RUN,
    PreparationActivityType.TYRE_TEST,
    PreparationActivityType.FUEL_TEST,
    PreparationActivityType.GEARING_TEST,
    PreparationActivityType.QUALIFYING_SIMULATION,
    PreparationActivityType.LONG_RACE_RUN,
    PreparationActivityType.STRATEGY_VALIDATION_RUN,
    PreparationActivityType.FINAL_SETUP_CONFIRMATION,
    PreparationActivityType.FREE_PRACTICE,
    PreparationActivityType.OFFICIAL_PRACTICE,
    PreparationActivityType.QUALIFYING,
    PreparationActivityType.RACE,
})


def _briefing_pending_before(order_index: int, activities: Sequence[PreparationActivity]) -> bool:
    """True if an EVENT_BRIEFING activity earlier in the order is not yet completed."""
    for a in activities:
        if (a.activity_type == PreparationActivityType.EVENT_BRIEFING
                and a.order_index < order_index
                and a.state != PreparationActivityState.COMPLETED):
            return True
    return False


def _race_completed(activities: Sequence[PreparationActivity]) -> bool:
    return any(a.activity_type == PreparationActivityType.RACE
              and a.state == PreparationActivityState.COMPLETED for a in activities)


def evaluate_activity_transition(
    activity: PreparationActivity,
    *,
    activities: Sequence[PreparationActivity],
    profile: EventFormatProfile,
    next_required_id: str = None,
) -> PreparationTransitionDecision:
    """Return the deterministic transition decision for one activity, reasoned from its explicit state,
    the profile's skipped phases, prerequisite briefings, ordering, and session binding. Pure."""
    D = PreparationTransitionDecision
    S = PreparationActivityState
    st = activity.state

    # explicit terminal / operator states map directly
    if st == S.COMPLETED:
        return D.COMPLETED
    if st == S.CANCELLED:
        return D.CANCELLED
    if st == S.RESCHEDULED:
        return D.RESCHEDULED
    if st == S.SKIPPED:
        return D.SKIPPED_BY_PROFILE
    if st == S.BLOCKED:
        return D.BLOCKED
    if st == S.AWAITING_CONFIRMATION:
        return D.AWAITING_DRIVER_CONFIRMATION

    # a phase the profile explicitly skips
    if activity.phase is not None and activity.phase in set(profile.skipped_phases):
        return D.SKIPPED_BY_PROFILE

    # optional & not yet started
    if activity.optional and st in (S.PLANNED, S.OPTIONAL_PENDING):
        return D.OPTIONAL

    # in progress: what is it waiting on?
    if st == S.IN_PROGRESS:
        if activity.activity_type in _RUN_TYPES and not activity.bound_session_ids:
            return D.AWAITING_SESSION_BINDING
        if activity.bound_session_ids:
            return D.AWAITING_FEEDBACK
        return D.AWAITING_TELEMETRY

    # planned / ready
    if next_required_id is None:
        next_required_id = _pick_next_activity(activities)

    if activity.activity_type in _RUN_TYPES and _briefing_pending_before(activity.order_index, activities):
        return D.AWAITING_BRIEFING
    if activity.activity_type == PreparationActivityType.POST_RACE_DEBRIEF and not _race_completed(activities):
        return D.AWAITING_DEBRIEF
    if activity.activity_id == next_required_id:
        return D.READY
    return D.SCHEDULED_LATER


def evaluate_activity_transitions(
    activities: Sequence[PreparationActivity],
    profile: EventFormatProfile,
) -> Tuple[Tuple[str, PreparationTransitionDecision], ...]:
    """Decide every activity's transition. Deterministic ordering by (order_index, activity_id)."""
    ordered = sorted(activities, key=lambda a: (a.order_index, a.activity_id))
    next_required_id = _pick_next_activity(ordered)
    out: List[Tuple[str, PreparationTransitionDecision]] = []
    for a in ordered:
        out.append((a.activity_id,
                    evaluate_activity_transition(a, activities=ordered, profile=profile,
                                                 next_required_id=next_required_id)))
    return tuple(out)


# ---------------------------------------------------------------------------
# Pure scheduling transforms (return NEW activities; never persist)
# ---------------------------------------------------------------------------

def _replace(activity: PreparationActivity, **changes) -> PreparationActivity:
    return PreparationActivity(
        activity_id=changes.get("activity_id", activity.activity_id),
        activity_type=changes.get("activity_type", activity.activity_type),
        title=changes.get("title", activity.title),
        objective=changes.get("objective", activity.objective),
        planned_date=changes.get("planned_date", activity.planned_date),
        state=changes.get("state", activity.state),
        order_index=changes.get("order_index", activity.order_index),
        optional=changes.get("optional", activity.optional),
        bound_session_ids=changes.get("bound_session_ids", activity.bound_session_ids),
        phase=changes.get("phase", activity.phase),
        notes=changes.get("notes", activity.notes),
    )


def reschedule_activity(activity: PreparationActivity, new_date: str) -> PreparationActivity:
    """Return a copy moved to ``new_date`` and marked RESCHEDULED. A rescheduled activity remains part
    of the same cycle and keeps its prior evidence bindings."""
    return _replace(activity, planned_date=_iso(new_date), state=PreparationActivityState.RESCHEDULED)


def cancel_activity(activity: PreparationActivity) -> PreparationActivity:
    """Return a cancelled copy. Cancelling a future activity never rewrites completed-session provenance
    of other activities (each activity's bound sessions are its own)."""
    return _replace(activity, state=PreparationActivityState.CANCELLED)


def skip_activity(activity: PreparationActivity) -> PreparationActivity:
    return _replace(activity, state=PreparationActivityState.SKIPPED)


def mark_optional(activity: PreparationActivity, optional: bool = True) -> PreparationActivity:
    return _replace(activity, optional=bool(optional))


def bind_session(activity: PreparationActivity, session_id: str) -> PreparationActivity:
    """Return a copy with ``session_id`` added to the bound set (idempotent, deterministic order).
    NOTE: this is a pure value transform for building the write payload — the canonical binding write
    is explicit (``SessionDB.bind_session_to_activity``); binding never happens automatically."""
    sid = _norm(session_id)
    if not sid or sid in activity.bound_session_ids:
        return activity
    merged = tuple(sorted(set(activity.bound_session_ids) | {sid}))
    return _replace(activity, bound_session_ids=merged)
