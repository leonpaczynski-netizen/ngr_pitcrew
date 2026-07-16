"""Sprint 10 — guided-UI backbone: workflow stepper, saved/applied state,
structured advice rendering (all pure, Qt-free)."""
from __future__ import annotations

from ui.workflow_stepper import (
    WorkflowInputs, build_workflow_state, StageStatus,
)
from data.applied_checkpoint import (
    compute_apply_status, make_checkpoint, compute_setup_hash, SetupApplyState,
)
from ui.setup_advice_render import render_setup_decision, TONE_OK, TONE_WARN, TONE_DANGER
from strategy.setup_decision import (
    arbitrate_setup_decision, DriverFeedback,
)
from strategy.cross_lap_persistence import (
    PersistenceClass, CornerIssueSignature, IssuePersistenceResult,
)
from strategy.tyre_curves import build_compound_curves, compute_crossovers


# --------------------------------------------------------------------------- #
# Workflow stepper
# --------------------------------------------------------------------------- #
def test_fresh_state_current_is_event_car():
    st = build_workflow_state(WorkflowInputs())
    assert st.current_index == 0
    assert st.stage("event_car").status is StageStatus.CURRENT
    assert "Event Planner" in st.next_action
    assert st.next_tab == "event_planner"


def test_track_not_ready_blocks_stage_2():
    st = build_workflow_state(WorkflowInputs(event_ready=True, track_ready=False,
                                             track_blocker="No station map"))
    assert st.stage("event_car").status is StageStatus.DONE
    assert st.stage("track_ready").status is StageStatus.BLOCKED
    assert "No station map" in st.stage("track_ready").blocker


def test_saved_not_applied_is_current_apply_stage_with_pending():
    st = build_workflow_state(WorkflowInputs(
        event_ready=True, track_ready=True, setup_saved=True,
        setup_applied_in_gt7=False, setup_pending_changes=3))
    apply = st.stage("apply_setup")
    assert apply.status is StageStatus.CURRENT or apply.status is StageStatus.BLOCKED
    assert "3 change" in apply.blocker


def test_bouncing_ball_first_incomplete_is_current():
    st = build_workflow_state(WorkflowInputs(
        event_ready=True, track_ready=True, setup_saved=True,
        setup_applied_in_gt7=True, practice_captured=True, feedback_present=False))
    assert st.stage("driver_feedback").status is StageStatus.CURRENT
    # 5 sequential stages done + controlled_test auto-satisfied (not required).
    assert st.done_count == 6


def test_all_complete():
    st = build_workflow_state(WorkflowInputs(
        event_ready=True, track_ready=True, setup_saved=True, setup_applied_in_gt7=True,
        practice_captured=True, feedback_present=True, engineering_reviewed=True,
        controlled_test_required=False, race_setup_locked=True,
        strategy_evidence_ready=True, race_plan_built=True, live_review_available=True))
    assert st.complete
    assert st.next_action == "All stages complete."


def test_controlled_test_optional_when_not_required():
    st = build_workflow_state(WorkflowInputs(
        event_ready=True, track_ready=True, setup_saved=True, setup_applied_in_gt7=True,
        practice_captured=True, feedback_present=True, engineering_reviewed=True,
        controlled_test_required=False, race_setup_locked=True))
    assert st.stage("controlled_test").status is StageStatus.DONE


# --------------------------------------------------------------------------- #
# Saved vs applied-in-GT7
# --------------------------------------------------------------------------- #
def test_not_saved_when_no_fields():
    assert compute_apply_status({}, None).state is SetupApplyState.NOT_SAVED


def test_saved_but_never_confirmed_is_changed():
    s = compute_apply_status({"ride_height_rear": 60}, None)
    assert s.state is SetupApplyState.CHANGED_SINCE_GT7
    assert "ride_height_rear" in s.pending_fields
    assert s.has_pending


def test_confirmed_when_matches_checkpoint():
    fields = {"ride_height_rear": 60, "arb_rear": 5}
    cp = make_checkpoint(setup_id="s1", fields=fields, confirmed_at="8:42 PM")
    s = compute_apply_status(fields, cp)
    assert s.state is SetupApplyState.CONFIRMED_IN_GT7
    assert s.is_confirmed
    assert "8:42 PM" in s.message


def test_changed_since_checkpoint_lists_pending_fields():
    cp = make_checkpoint(setup_id="s1", fields={"ride_height_rear": 60, "arb_rear": 5})
    s = compute_apply_status({"ride_height_rear": 62, "arb_rear": 5}, cp)
    assert s.state is SetupApplyState.CHANGED_SINCE_GT7
    assert s.pending_fields == ("ride_height_rear",)
    assert "1 change" in s.message


def test_setup_hash_order_independent_and_deterministic():
    a = compute_setup_hash({"a": 1, "b": 2})
    b = compute_setup_hash({"b": 2, "a": 1})
    assert a == b


# --------------------------------------------------------------------------- #
# Structured advice rendering
# --------------------------------------------------------------------------- #
def _pres(issue_type, cls, eligible, pct=0.75, affected=6, total=8):
    sig = CornerIssueSignature("fuji", "fuji__full", "cp1", "T3", "exit",
                               issue_type, "rear", "power_traction")
    return IssuePersistenceResult(
        classification=cls, signature=sig, affected_representative_laps=affected,
        total_representative_laps=total, recurrence_pct=pct, sessions=1,
        median_severity=0.3, median_duration_s=0.3, confidence=0.6,
        eligible_for_setup=eligible, excluded_laps=(), reason="", next_action="")


def test_render_approved_decision_has_banner_and_approved_table():
    persistence = [_pres("wheelspin", PersistenceClass.PERSISTENT_PATTERN, True)]
    d = arbitrate_setup_decision([{"field": "lsd_accel"}], persistence, DriverFeedback())
    cards = render_setup_decision(d, persistence)
    kinds = [c.kind for c in cards]
    assert kinds[0] == "banner"
    assert cards[0].tone == TONE_OK
    assert "approved" in kinds
    assert "recurring" in kinds  # cross-lap evidence table present


def test_render_evidence_conflict_has_conflict_card():
    persistence = [_pres("wheelspin", PersistenceClass.EMERGING_PATTERN, False,
                         pct=0.25, affected=2)]
    d = arbitrate_setup_decision([{"field": "lsd_accel"}], persistence,
                                 DriverFeedback(traction="good"))
    cards = render_setup_decision(d, persistence)
    kinds = [c.kind for c in cards]
    assert "conflict" in kinds
    assert cards[0].tone == TONE_WARN


def test_render_engineering_failure_is_danger_and_not_approved():
    d = arbitrate_setup_decision([{"field": "lsd_accel"}], [], DriverFeedback(),
                                 validation_failed=True, validation_errors=["x"])
    cards = render_setup_decision(d)
    assert cards[0].kind == "banner" and cards[0].tone == TONE_DANGER
    assert "approved" not in [c.kind for c in cards]


def test_render_crossovers_when_provided():
    curves = build_compound_curves({"RS": [98000] * 4 + [100000] * 4,
                                    "RM": [99000] * 8})
    crossovers = compute_crossovers(curves)
    d = arbitrate_setup_decision([], [], DriverFeedback(traction="good"))
    cards = render_setup_decision(d, [], crossovers)
    assert "crossover" in [c.kind for c in cards]
