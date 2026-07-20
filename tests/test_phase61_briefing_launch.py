"""Phase 61 — activity briefing + explicit launch (task items 14-15)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.live_activity import ActivityExecutionContext, assess_start_readiness
from strategy.driver_event_loop import (
    build_activity_briefing, decide_activity_launch, EventLoopStage as ES, EventLoopSignals,
    advance_event_loop,
)


def _readiness(**kw):
    base = dict(cycle_id="c1", activity_id="a1", activity_type=T.SETUP_EXPERIMENT, track="Fuji",
                car="Porsche", discipline="race", run_plan_present=True, telemetry_available=True,
                expected_setup_fingerprint="fp", applied_setup_fingerprint="fp", setup_delta_present=True,
                preflight_done=True)
    base.update(kw)
    return assess_start_readiness(ActivityExecutionContext(**base))


# --- briefing --------------------------------------------------------------

def test_briefing_assembles_fields():
    b = build_activity_briefing(event="Cup R3", activity="Setup exp 1", objective="rotation",
                                setup="Race baseline+1F", target_laps=8, target_corners=("T1", "T13"),
                                evidence_required=("consistency",), held_constant=("aero",),
                                stop_conditions=("return after 8 clean laps",))
    assert b.event == "Cup R3" and b.target_laps == 8 and "T1" in b.target_corners
    assert b.fingerprint.startswith("driver_event_loop_v1:")


# --- launch ----------------------------------------------------------------

def test_launch_requires_readiness_and_confirmation():
    r = _readiness()
    assert r.can_start is True
    assert decide_activity_launch(r, confirmed=False).can_launch is False   # opening briefing never launches
    assert decide_activity_launch(r, confirmed=False).requires_confirmation is True
    assert decide_activity_launch(r, confirmed=True).can_launch is True


def test_blocked_readiness_never_launches_even_when_confirmed():
    r = _readiness(applied_setup_fingerprint="other")  # mismatch -> not ready
    assert r.can_start is False
    d = decide_activity_launch(r, confirmed=True)
    assert d.can_launch is False and d.blockers


# --- loop transitions ------------------------------------------------------

def test_loop_never_skips_binding_or_debrief():
    # LIVE -> SESSION_END -> BINDING (not straight to debrief)
    assert advance_event_loop(ES.LIVE, EventLoopSignals(session_ended=True)).stage == ES.SESSION_END
    assert advance_event_loop(ES.SESSION_END, EventLoopSignals(bound=False)).stage == ES.BINDING
    assert advance_event_loop(ES.BINDING, EventLoopSignals(bound=True)).stage == ES.DEBRIEF


def test_loop_requires_confirmed_outcome_for_cumulative_update():
    # debrief without confirmed outcome holds; with it -> cumulative update
    assert advance_event_loop(ES.DEBRIEF, EventLoopSignals(bound=True)).stage == ES.DEBRIEF
    assert advance_event_loop(ES.DEBRIEF, EventLoopSignals(debrief_confirmed=True, outcome_recorded=True)).stage == ES.CUMULATIVE_UPDATE


def test_loop_returns_to_command_centre_after_update():
    assert advance_event_loop(ES.CUMULATIVE_UPDATE, EventLoopSignals()).stage == ES.COMMAND_CENTRE_RETURN


def test_briefing_holds_until_launch():
    assert advance_event_loop(ES.BRIEFING, EventLoopSignals()).stage == ES.BRIEFING
    assert advance_event_loop(ES.BRIEFING, EventLoopSignals(launched=True)).stage == ES.READINESS


def test_loop_transition_deterministic():
    a = advance_event_loop(ES.LIVE, EventLoopSignals(session_ended=True))
    b = advance_event_loop(ES.LIVE, EventLoopSignals(session_ended=True))
    assert a.fingerprint == b.fingerprint
