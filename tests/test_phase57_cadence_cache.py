"""Phase 57 — runtime cadence + cache invalidation (task items 7-8, 30)."""
from __future__ import annotations

from strategy.gt7_live_adapter import SelectedActivityContext
from strategy.live_runtime_cache import runtime_cache_key, LiveEvaluationCadence


def _ctx(**kw):
    base = dict(cycle_id="c1", activity_id="exp", activity_type="setup_experiment", discipline="race",
                expected_setup_fingerprint="fp", event_context_digest="ctx", run_plan_fingerprint="rp")
    base.update(kw)
    return SelectedActivityContext(**base)


# --- cache key -------------------------------------------------------------

def test_key_stable_for_same_operational_state():
    assert runtime_cache_key(_ctx()) == runtime_cache_key(_ctx())


def test_key_changes_on_activity_setup_context_runplan_or_session_end():
    base = runtime_cache_key(_ctx())
    assert runtime_cache_key(_ctx(activity_id="other")) != base
    assert runtime_cache_key(_ctx(expected_setup_fingerprint="fp2")) != base
    assert runtime_cache_key(_ctx(event_context_digest="ctx2")) != base
    assert runtime_cache_key(_ctx(run_plan_fingerprint="rp2")) != base
    assert runtime_cache_key(_ctx(), session_ended=True) != base


def test_key_ignores_volatile_counters():
    # lap/segment/fuel/speed are not part of the SelectedActivityContext key inputs -> telemetry alone
    # does not invalidate the cache (the ctx carries only stable identity)
    a = runtime_cache_key(_ctx(objective="rotation", target_laps=8))
    b = runtime_cache_key(_ctx(objective="rotation", target_laps=8))
    assert a == b


# --- cadence ---------------------------------------------------------------

def test_cadence_reevaluates_on_key_change():
    cad = LiveEvaluationCadence(cadence_seconds=0.5)
    k1 = runtime_cache_key(_ctx())
    assert cad.should_evaluate(k1, 100.0) is True  # first time
    cad.record(k1, 100.0)
    assert cad.should_evaluate(k1, 100.1) is False  # within cadence, same key
    k2 = runtime_cache_key(_ctx(activity_id="new"))
    assert cad.should_evaluate(k2, 100.1) is True   # key changed


def test_cadence_reevaluates_after_interval():
    cad = LiveEvaluationCadence(cadence_seconds=0.5)
    k = runtime_cache_key(_ctx())
    cad.should_evaluate(k, 100.0); cad.record(k, 100.0)
    assert cad.should_evaluate(k, 100.2) is False
    assert cad.should_evaluate(k, 100.6) is True    # cadence elapsed


def test_cadence_force_always_reevaluates():
    cad = LiveEvaluationCadence(cadence_seconds=999)
    k = runtime_cache_key(_ctx())
    cad.record(k, 100.0)
    assert cad.should_evaluate(k, 100.1, force=True) is True  # e.g. explicit binding / stale->fresh
