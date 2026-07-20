"""Phase 48 — activity transitions & scheduling tests.

Covers task test items: optional (8), skipped (9), rescheduled (10) activities, scheduling and
transition rules (task section 20 commit 3), and the invariant that viewing does not advance state.
"""
from __future__ import annotations

from strategy.event_preparation_cycle import (
    PreparationActivity, PreparationActivityType, PreparationActivityState,
    PreparationTransitionDecision, PreparationPhase, multiweek_profile, single_evening_profile,
)
from strategy.preparation_transitions import (
    evaluate_activity_transition, evaluate_activity_transitions, reschedule_activity,
    cancel_activity, skip_activity, mark_optional, bind_session,
)

T = PreparationActivityType
S = PreparationActivityState
D = PreparationTransitionDecision


def _act(aid, atype, order, **kw):
    return PreparationActivity(activity_id=aid, activity_type=atype, order_index=order, **kw)


def test_next_required_activity_is_ready_others_scheduled_later():
    acts = [_act("a", T.BASELINE_PRACTICE, 0), _act("b", T.SETUP_EXPERIMENT, 1)]
    decisions = dict(evaluate_activity_transitions(acts, multiweek_profile()))
    assert decisions["a"] == D.READY
    assert decisions["b"] == D.SCHEDULED_LATER


def test_run_awaits_briefing_until_briefing_completed():
    acts = [_act("brief", T.EVENT_BRIEFING, 0), _act("run", T.BASELINE_PRACTICE, 1)]
    decisions = dict(evaluate_activity_transitions(acts, multiweek_profile()))
    # briefing is next -> READY; the run cannot be ready until the briefing is done
    assert decisions["brief"] == D.READY
    assert decisions["run"] == D.AWAITING_BRIEFING
    # complete the briefing -> run becomes ready
    acts2 = [_act("brief", T.EVENT_BRIEFING, 0, state=S.COMPLETED), _act("run", T.BASELINE_PRACTICE, 1)]
    decisions2 = dict(evaluate_activity_transitions(acts2, multiweek_profile()))
    assert decisions2["run"] == D.READY


def test_optional_activity_is_optional_not_blocking():
    acts = [_act("opt", T.COACHING_RUN, 0, optional=True), _act("req", T.SETUP_EXPERIMENT, 1)]
    decisions = dict(evaluate_activity_transitions(acts, multiweek_profile()))
    assert decisions["opt"] == D.OPTIONAL
    # the required activity is still the next actionable one (optional does not block)
    assert decisions["req"] == D.READY


def test_skipped_phase_yields_skipped_by_profile():
    a = _act("dev", T.SETUP_EXPERIMENT, 0, phase=PreparationPhase.SETUP_DEVELOPMENT)
    decision = evaluate_activity_transition(a, activities=[a], profile=single_evening_profile())
    assert decision == D.SKIPPED_BY_PROFILE  # single-evening profile skips SETUP_DEVELOPMENT


def test_in_progress_run_awaits_session_binding_then_feedback():
    a = _act("run", T.LONG_RACE_RUN, 0, state=S.IN_PROGRESS)
    assert evaluate_activity_transition(a, activities=[a], profile=multiweek_profile()) \
        == D.AWAITING_SESSION_BINDING
    bound = bind_session(a, "sess-42")
    assert evaluate_activity_transition(bound, activities=[bound], profile=multiweek_profile()) \
        == D.AWAITING_FEEDBACK


def test_post_race_debrief_awaits_debrief_until_race_done():
    acts = [_act("race", T.RACE, 0), _act("debrief", T.POST_RACE_DEBRIEF, 1)]
    decisions = dict(evaluate_activity_transitions(acts, multiweek_profile()))
    assert decisions["debrief"] == D.AWAITING_DEBRIEF
    acts2 = [_act("race", T.RACE, 0, state=S.COMPLETED), _act("debrief", T.POST_RACE_DEBRIEF, 1)]
    decisions2 = dict(evaluate_activity_transitions(acts2, multiweek_profile()))
    assert decisions2["debrief"] == D.READY


def test_explicit_states_map_directly():
    for st, expect in [(S.CANCELLED, D.CANCELLED), (S.RESCHEDULED, D.RESCHEDULED),
                       (S.BLOCKED, D.BLOCKED), (S.AWAITING_CONFIRMATION, D.AWAITING_DRIVER_CONFIRMATION),
                       (S.COMPLETED, D.COMPLETED)]:
        a = _act("x", T.SETUP_EXPERIMENT, 0, state=st)
        assert evaluate_activity_transition(a, activities=[a], profile=multiweek_profile()) == expect


# --- scheduling transforms are pure -----------------------------------------

def test_reschedule_returns_new_value_and_does_not_mutate():
    a = _act("a", T.TYRE_TEST, 0, planned_date="2026-06-05")
    b = reschedule_activity(a, "2026-06-12")
    assert a.planned_date == "2026-06-05"   # original untouched
    assert b.planned_date == "2026-06-12" and b.state == S.RESCHEDULED
    assert a is not b


def test_cancel_and_skip_are_pure():
    a = _act("a", T.SETUP_EXPERIMENT, 0)
    assert cancel_activity(a).state == S.CANCELLED
    assert skip_activity(a).state == S.SKIPPED
    assert a.state == S.PLANNED  # unchanged


def test_bind_session_is_idempotent_and_sorted():
    a = _act("a", T.LONG_RACE_RUN, 0)
    a1 = bind_session(a, "s2")
    a2 = bind_session(a1, "s1")
    a3 = bind_session(a2, "s1")  # duplicate ignored
    assert a2.bound_session_ids == ("s1", "s2")
    assert a3.bound_session_ids == ("s1", "s2")


def test_transitions_are_deterministic_and_view_only():
    acts = [_act("b", T.SETUP_EXPERIMENT, 1), _act("a", T.BASELINE_PRACTICE, 0)]
    r1 = evaluate_activity_transitions(acts, multiweek_profile())
    r2 = evaluate_activity_transitions(list(reversed(acts)), multiweek_profile())
    assert r1 == r2  # order-independent, deterministic
    # inputs unchanged (no mutation / no advance)
    assert acts[0].state == S.PLANNED and acts[1].state == S.PLANNED
