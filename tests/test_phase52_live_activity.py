"""Phase 52 — activity start-readiness + completion gate (task items 12, 19)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.live_activity import (
    ActivityExecutionContext, StartCheckStatus as S, assess_start_readiness, requires_telemetry,
    assess_completion, LiveActivityState as L,
)


def _ctx(atype=T.SETUP_EXPERIMENT, **kw):
    base = dict(cycle_id="c1", activity_id="a1", activity_type=atype, track="Fuji", car="Porsche",
                discipline="race", run_plan_present=True, telemetry_available=True,
                expected_setup_fingerprint="fp-exp", applied_setup_fingerprint="fp-exp",
                setup_delta_present=True, preflight_done=True)
    base.update(kw)
    return ActivityExecutionContext(**base)


def _status(readiness, name):
    for c in readiness.checks:
        if c.name == name:
            return c.status
    return None


# --- start readiness -------------------------------------------------------

def test_fully_ready_setup_experiment_can_start():
    r = assess_start_readiness(_ctx())
    assert r.can_start is True and not r.blocking_reasons


def test_missing_run_plan_blocks_start():
    r = assess_start_readiness(_ctx(run_plan_present=False))
    assert r.can_start is False and "run_plan" in r.blocking_reasons


def test_applied_setup_mismatch_blocks_start():
    r = assess_start_readiness(_ctx(applied_setup_fingerprint="fp-other"))
    assert r.can_start is False
    assert _status(r, "applied_setup") == S.MISMATCH


def test_stale_plan_blocks_start():
    r = assess_start_readiness(_ctx(plan_stale=True))
    assert r.can_start is False and "plan_fresh" in r.blocking_reasons


def test_setup_restriction_violation_blocks():
    r = assess_start_readiness(_ctx(setup_restrictions_ok=False))
    assert r.can_start is False and "setup_restrictions" in r.blocking_reasons


def test_setup_experiment_requires_delta_and_preflight():
    r = assess_start_readiness(_ctx(setup_delta_present=False, preflight_done=False))
    assert "setup_delta" in r.blocking_reasons and "preflight" in r.blocking_reasons


def test_coaching_requires_held_constant_and_one_objective():
    r = assess_start_readiness(_ctx(atype=T.COACHING_RUN, expected_setup_fingerprint="",
                                    held_constant=False, coaching_objective_count=2))
    assert "held_constant_setup" in r.blocking_reasons
    assert "coaching_objective" in r.blocking_reasons
    ok = assess_start_readiness(_ctx(atype=T.COACHING_RUN, expected_setup_fingerprint="",
                                     held_constant=True, coaching_objective_count=1))
    assert ok.can_start is True


def test_tyre_test_requires_compatible_compound_and_multiplier():
    r = assess_start_readiness(_ctx(atype=T.TYRE_TEST, expected_setup_fingerprint="",
                                    compound_compatible=False, tyre_multiplier_known=False))
    assert "compound_compatible" in r.blocking_reasons and "tyre_multiplier_known" in r.blocking_reasons


def test_fuel_test_requires_multiplier_and_fuel_window():
    r = assess_start_readiness(_ctx(atype=T.FUEL_TEST, expected_setup_fingerprint="",
                                    fuel_multiplier_known=False, starting_fuel_window_ok=False))
    assert "fuel_multiplier_known" in r.blocking_reasons and "starting_fuel_window" in r.blocking_reasons


def test_race_sim_requires_race_setup_and_strategy_objective():
    r = assess_start_readiness(_ctx(atype=T.LONG_RACE_RUN, strategy_objective_present=False))
    assert "strategy_objective" in r.blocking_reasons


def test_voice_and_tyre_are_non_blocking():
    r = assess_start_readiness(_ctx(voice_ready=False, selected_tyre=""))
    assert r.can_start is True  # voice off + tyre unknown never block
    assert _status(r, "voice_ready") == S.NOT_APPLICABLE


def test_start_readiness_is_deterministic():
    a = assess_start_readiness(_ctx())
    b = assess_start_readiness(_ctx())
    assert a.fingerprint == b.fingerprint


# --- completion gate -------------------------------------------------------

def test_completion_requires_all_explicit_confirmations():
    d = assess_completion(T.SETUP_EXPERIMENT, session_bound=False, evidence_classified=False,
                          feedback_present=False, debrief_confirmed=False)
    assert d.can_complete is False and d.resulting_state == L.BINDING_REQUIRED
    assert "explicit session binding" in d.missing


def test_completion_blocked_on_missing_debrief():
    d = assess_completion(T.SETUP_EXPERIMENT, session_bound=True, evidence_classified=True,
                          feedback_present=True, debrief_confirmed=False)
    assert d.can_complete is False and d.resulting_state == L.DEBRIEF_REQUIRED
    assert "explicit debrief / outcome confirmation" in d.missing


def test_completion_succeeds_with_all_confirmations():
    d = assess_completion(T.SETUP_EXPERIMENT, session_bound=True, evidence_classified=True,
                          feedback_present=True, debrief_confirmed=True)
    assert d.can_complete is True and d.resulting_state == L.COMPLETED


def test_abandoned_and_invalid_short_circuit():
    assert assess_completion(T.SETUP_EXPERIMENT, session_bound=True, evidence_classified=True,
                             feedback_present=True, debrief_confirmed=True, abandoned=True).resulting_state \
        == L.ABANDONED
    assert assess_completion(T.SETUP_EXPERIMENT, session_bound=True, evidence_classified=True,
                             feedback_present=True, debrief_confirmed=True, invalid=True).resulting_state \
        == L.INVALID


def test_non_telemetry_activity_does_not_require_binding():
    assert requires_telemetry(T.RACE_STRATEGY_MEETING) is False
    d = assess_completion(T.RACE_STRATEGY_MEETING, session_bound=False, evidence_classified=True,
                          feedback_present=True, debrief_confirmed=True)
    assert d.can_complete is True
