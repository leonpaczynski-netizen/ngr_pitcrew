"""Live Activation 3 — the Race activation gate, race-plan coherence guard, and race engineer
phase machine (pure decisions). Offline, deterministic; no DB, no Qt."""
from __future__ import annotations

import pytest

from strategy.live_practice_activation import (
    RACE, ActivationVerdict, RacePlanContextVerdict, resolve_live_race_activation,
    validate_race_plan_context,
)
from strategy.race_engineer_state_machine import (
    RaceEngineerEvent, RaceEngineerPhase, RaceEngineerState, apply_event,
    events_from_race_signals, on_finish, on_lap_completed, race_cue,
)


# --- full canonical race context (every REQUIRED_CONTEXT field resolved) --------
def _race_ctx(**over):
    ctx = dict(
        event_programme_id="ep1", event_id="7", session_plan_id="sp1", car_id="42",
        car_spec_revision_id="csr1", driver_profile_version_id="dpv1", context_revision_id="fp1",
        planned_session_type="Race",
        race_plan_id="rp1", plan_event_id="7", plan_car_id="42",
        plan_track_id="wg", plan_layout_id="full", track_id="wg", layout_id="full",
    )
    ctx.update(over)
    return ctx


# =============================== activation gate ==============================
def test_race_constant():
    assert RACE == "race"


def test_valid_race_context_activates():
    act = resolve_live_race_activation(_race_ctx(), planned_session_type="Race")
    assert act.ok and act.verdict == ActivationVerdict.ACTIVATED
    assert act.identity["session_type"] == "race"
    assert act.identity["car_id"] == "42"


def test_car_id_zero_blocks():
    act = resolve_live_race_activation(_race_ctx(car_id="0"), planned_session_type="Race")
    assert not act.ok
    assert act.verdict == ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT
    assert "car_id" in act.missing


def test_missing_car_blocks():
    act = resolve_live_race_activation(_race_ctx(car_id=""), planned_session_type="Race")
    assert act.verdict == ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT
    assert "car_id" in act.missing


def test_stale_practice_plan_blocks_race():
    # A planned Practice session can never activate a live Race, however complete the context.
    act = resolve_live_race_activation(
        _race_ctx(planned_session_type="Practice"), planned_session_type="Practice")
    assert act.verdict == ActivationVerdict.BLOCKED_WRONG_SESSION_TYPE


def test_race_never_inferred_from_missing_plan():
    # Empty planned type (GT7 said "race" but the app has no planned race) → blocked, not inferred.
    act = resolve_live_race_activation(_race_ctx(planned_session_type=""), planned_session_type="")
    assert act.verdict == ActivationVerdict.BLOCKED_WRONG_SESSION_TYPE


# ========================= race-plan coherence guard =========================
def test_plan_context_ok():
    assert validate_race_plan_context(_race_ctx()).ok


def test_plan_context_missing_plan():
    d = validate_race_plan_context(_race_ctx(race_plan_id=""))
    assert d.verdict == RacePlanContextVerdict.MISSING_PLAN


@pytest.mark.parametrize("axis,label", [
    ("plan_event_id", "event"), ("plan_car_id", "car"),
    ("plan_track_id", "track"), ("plan_layout_id", "layout"),
])
def test_plan_context_mismatch_each_axis(axis, label):
    d = validate_race_plan_context(_race_ctx(**{axis: "999"}))
    assert d.verdict == RacePlanContextVerdict.MISMATCH
    assert label in d.mismatched


def test_plan_axis_unknown_is_not_a_contradiction():
    # The plan not being scoped to an axis is fine (unscoped, not conflicting).
    assert validate_race_plan_context(_race_ctx(plan_track_id="", plan_layout_id="")).ok


def test_unknown_live_identity_never_matches_known_plan():
    # Plan asserts a car; the live identity is unknown → conservative MISMATCH, never silent-ok.
    d = validate_race_plan_context(_race_ctx(car_id=""))
    assert d.verdict == RacePlanContextVerdict.MISMATCH
    assert "car" in d.mismatched


# ========================== race engineer machine ============================
def test_events_from_signals_start_and_pit_and_finish():
    assert events_from_race_signals("idle", "racing") == (RaceEngineerEvent.LIGHTS_OUT,)
    assert events_from_race_signals("racing", "in_pit") == (RaceEngineerEvent.PIT_ENTRY,)
    assert events_from_race_signals("in_pit", "racing") == (RaceEngineerEvent.PIT_EXIT,)
    assert events_from_race_signals("racing", "finished") == (RaceEngineerEvent.FINISH,)
    assert events_from_race_signals("racing", "racing") == ()  # no edge, no event


def test_phase_progression_grid_to_finish():
    s = RaceEngineerState.initial()
    assert s.phase == RaceEngineerPhase.WAITING
    s = apply_event(s, RaceEngineerEvent.LIGHTS_OUT)
    assert s.phase == RaceEngineerPhase.RACE_START and s.started
    s = on_lap_completed(s, 95000, lap_number=1)
    assert s.phase == RaceEngineerPhase.RACING and s.completed_laps == 1
    s = apply_event(s, RaceEngineerEvent.PIT_ENTRY)
    assert s.phase == RaceEngineerPhase.PIT_ENTRY
    s = apply_event(s, RaceEngineerEvent.PIT_STOPPED)
    s = apply_event(s, RaceEngineerEvent.PIT_EXIT)
    assert s.phase == RaceEngineerPhase.PIT_EXIT and s.pit_stops_completed == 1
    s = apply_event(s, RaceEngineerEvent.REJOINED)
    assert s.phase == RaceEngineerPhase.RACING
    s = on_finish(s)
    assert s.phase == RaceEngineerPhase.FINISHED and s.finished


def test_spurious_pit_exit_does_not_count_a_stop():
    s = apply_event(RaceEngineerState.initial(), RaceEngineerEvent.LIGHTS_OUT)
    s = apply_event(s, RaceEngineerEvent.PIT_EXIT)  # no preceding entry/stop
    assert s.pit_stops_completed == 0


def test_lights_out_is_idempotent():
    s = apply_event(RaceEngineerState.initial(), RaceEngineerEvent.LIGHTS_OUT)
    again = apply_event(s, RaceEngineerEvent.LIGHTS_OUT)
    assert again.phase == RaceEngineerPhase.RACE_START


def test_finished_is_terminal_for_phase_events():
    s = on_finish(apply_event(RaceEngineerState.initial(), RaceEngineerEvent.LIGHTS_OUT))
    s2 = apply_event(s, RaceEngineerEvent.PIT_ENTRY)
    assert s2.phase == RaceEngineerPhase.FINISHED  # no reopening after the flag


def test_best_lap_tracked():
    s = apply_event(RaceEngineerState.initial(), RaceEngineerEvent.LIGHTS_OUT)
    s = on_lap_completed(s, 95000, lap_number=1)
    s = on_lap_completed(s, 94000, lap_number=2)
    s = on_lap_completed(s, 96000, lap_number=3)
    assert s.best_lap_ms == 94000 and s.completed_laps == 3


def test_cue_lines_are_phase_appropriate_and_never_raise():
    s = RaceEngineerState.initial()
    assert "grid" in race_cue(s).lower()
    s = apply_event(s, RaceEngineerEvent.LIGHTS_OUT)
    assert "lights out" in race_cue(s).lower()
    s = apply_event(s, RaceEngineerEvent.PIT_ENTRY)
    assert "pit" in race_cue(s).lower()
    s = on_finish(s)
    assert "chequered" in race_cue(s).lower()


def test_cue_relays_advisory_verbatim_while_racing():
    s = on_lap_completed(apply_event(RaceEngineerState.initial(), RaceEngineerEvent.LIGHTS_OUT),
                         95000, lap_number=1)
    assert race_cue(s, advisory="Save half a litre a lap.") == "Save half a litre a lap."
