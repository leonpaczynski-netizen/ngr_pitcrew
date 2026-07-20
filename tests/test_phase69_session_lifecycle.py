"""Phase 69 — session-transition hardening: transient vs preserved key sets are disjoint; a reset clears
transient live-runtime state and never touches persistent engineering knowledge."""
from __future__ import annotations

from strategy.live_session_lifecycle import (
    SESSION_RESET_PLAN, SessionResetPlan, TRANSIENT_LIVE_RUNTIME_KEYS, PRESERVED_KEYS,
    reset_live_runtime_state, reset_live_runtime_attrs,
)


def test_reset_plan_is_disjoint():
    assert SESSION_RESET_PLAN.disjoint()
    assert not (set(TRANSIENT_LIVE_RUNTIME_KEYS) & set(PRESERVED_KEYS))


def test_transient_keys_cover_required_state():
    # spec 6.3: cadence, fuel/pace evidence, pit history, last recommendation, spoken cooldown,
    # pending recognition/confirmation, driver-report candidate, certification runtime observations
    for k in ("_live_fuel_samples", "_live_clean_lap_times", "_live_last_recommendation_fp",
              "_live_last_spoken_mono", "_ptt_pending_intent", "_ptt_pending_confirmation",
              "_ptt_driver_report_candidate", "_live_uat_runtime_observations", "_live_eval_cadence"):
        assert SESSION_RESET_PLAN.is_transient(k)


def test_persistent_keys_preserved():
    for k in ("_db", "_config", "_event_preparation_cycle", "_manual_uat_store"):
        assert SESSION_RESET_PLAN.is_preserved(k)
        assert not SESSION_RESET_PLAN.is_transient(k)


def test_reset_clears_transient_preserves_persistent():
    state = {"_live_fuel_samples": [3.1, 3.2], "_live_clean_lap_times": [88.0],
             "_live_last_recommendation_fp": "prev", "_ptt_pending_intent": {"a": 1},
             "_db": "PERSIST", "_config": {"x": 1}, "_manual_uat_store": "STORE"}
    cleared = reset_live_runtime_state(state)
    assert set(cleared) == {"_live_fuel_samples", "_live_clean_lap_times",
                            "_live_last_recommendation_fp", "_ptt_pending_intent"}
    assert all(state[k] is None for k in cleared)
    assert state["_db"] == "PERSIST"
    assert state["_config"] == {"x": 1}
    assert state["_manual_uat_store"] == "STORE"


def test_reset_attrs_on_object():
    class Obj:
        def __init__(self):
            self._live_fuel_samples = [1, 2]
            self._db = "keep"
    o = Obj()
    cleared = reset_live_runtime_attrs(o)
    assert "_live_fuel_samples" in cleared
    assert o._live_fuel_samples is None
    assert o._db == "keep"


def test_reset_never_raises_on_bad_input():
    assert reset_live_runtime_state(None) == {}
    assert reset_live_runtime_attrs(None) == ()


def test_double_guard_never_clears_a_preserved_key():
    # even a hand-built (invalid) plan that lists a preserved key as transient must not clear it
    bad = SessionResetPlan(transient_keys=("_db",), preserved_keys=("_db",))
    state = {"_db": "PERSIST"}
    cleared = reset_live_runtime_state(state, bad)
    assert state["_db"] == "PERSIST"
    assert "_db" not in cleared
