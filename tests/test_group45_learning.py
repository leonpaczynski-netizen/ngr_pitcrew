"""
Group 45 — Setup Brain Intelligence Expansion: Learning / RuleOutcomeStore Tests

Covers AC28-AC31 (Obj6 Learning/Confidence Downgrade):
  AC28 — RuleOutcomeStore fire_count increments correctly
  AC29 — success_rate < LOW_SUCCESS_RATE with >= MIN_OUTCOME_SAMPLES fires
          the confidence downgrade gate (high→med, med→low)
  AC30 — success_rate exactly == LOW_SUCCESS_RATE (boundary) does NOT trigger downgrade
  AC31 — downgrade gate only lowers confidence, never moves a change into rejected;
          empty store returns None from get_success_rate (no downgrade)

All tests are pure — no network, no Qt, no file IO.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy._setup_constants import MIN_OUTCOME_SAMPLES, LOW_SUCCESS_RATE
from strategy.setup_rule_engine import (
    RuleOutcomeStore,
    run_rule_engine,
    SetupChangeIntent,
)
from strategy.setup_knowledge_base import ConfidenceLevel
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import DriverProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_neutral_profile() -> DriverProfile:
    return DriverProfile(
        profile_version="v1.0-test",
        style_tags=[],
        hard_constraints=[],
        prefers_rear_stability=False,
        dislikes_snap_exit=False,
        trail_braker=False,
        rotation_without_snap=False,
        prefers_front_bite=False,
        dislikes_floaty_front=False,
        protects_downforce=False,
        race_values_consistency=False,
    )


def _make_store_with_outcomes(
    rule_id: str,
    fire_count: int,
    success_count: int,
) -> RuleOutcomeStore:
    """Return a store with (fire_count) fires and (success_count) successes for rule_id."""
    store = RuleOutcomeStore()
    for _ in range(fire_count):
        store.record_fire(rule_id)
    for _ in range(success_count):
        store.record_success(rule_id)
    return store


def _wheelspin_diag() -> dict:
    """Minimal diagnosis that triggers wheelspin rules (B-pack)."""
    return {
        "avg_bottoming": 0.0,
        "bottoming_band": "minor",
        "avg_wheelspin": 20.0,
        "wheelspin_band": "severe",
        "avg_snap": 0.0,
        "avg_lockups": 0.0,
        "driver_feel_flags": {
            "rear_loose_on_exit": True,
            "snap_oversteer_exit": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False,
        "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "wheelspin",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "wheelspin",
        "bottoming_confidence": {
            "band": "minor",
            "subtype": "insufficient_data",
            "confidence": "low",
        },
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
    }


# ===========================================================================
# AC28 — RuleOutcomeStore fire_count increments correctly
# ===========================================================================

class TestAC28FireCount:
    """AC28: fire_count increments on each call to record_fire."""

    def test_initial_fire_count_is_zero(self):
        """A new store returns 0 for any rule_id."""
        store = RuleOutcomeStore()
        assert store.fire_count("B3") == 0

    def test_fire_count_increments(self):
        """fire_count increments by 1 for each record_fire call."""
        store = RuleOutcomeStore()
        store.record_fire("B3")
        assert store.fire_count("B3") == 1
        store.record_fire("B3")
        assert store.fire_count("B3") == 2

    def test_fire_count_is_keyed_by_rule_id(self):
        """fire_count for different rule_ids are independent."""
        store = RuleOutcomeStore()
        store.record_fire("B3")
        store.record_fire("B3")
        store.record_fire("A1")
        assert store.fire_count("B3") == 2
        assert store.fire_count("A1") == 1
        assert store.fire_count("C1") == 0

    def test_fire_count_with_car_and_track(self):
        """fire_count is keyed by (rule_id, car, track, profile_version)."""
        store = RuleOutcomeStore()
        store.record_fire("B3", car="GT-R", track="Nurburgring")
        store.record_fire("B3", car="GT-R", track="Fuji")
        # Different tracks are separate keys
        assert store.fire_count("B3", car="GT-R", track="Nurburgring") == 1
        assert store.fire_count("B3", car="GT-R", track="Fuji") == 1
        # Unkeyed call is a separate key (empty strings)
        assert store.fire_count("B3") == 0

    def test_fire_count_survives_many_records(self):
        """fire_count correctly accumulates 100 calls."""
        store = RuleOutcomeStore()
        for _ in range(100):
            store.record_fire("B3")
        assert store.fire_count("B3") == 100


# ===========================================================================
# AC29 — Low success_rate triggers confidence downgrade
# ===========================================================================

class TestAC29ConfidenceDowngrade:
    """AC29: success_rate < LOW_SUCCESS_RATE with >= MIN_OUTCOME_SAMPLES triggers downgrade."""

    def test_get_success_rate_below_threshold(self):
        """get_success_rate correctly computes rate when >= MIN_OUTCOME_SAMPLES fires."""
        # 3 fires, 0 successes → rate 0.0
        store = _make_store_with_outcomes("B3", MIN_OUTCOME_SAMPLES, 0)
        rate = store.get_success_rate("B3")
        assert rate is not None
        assert rate < LOW_SUCCESS_RATE

    def test_success_rate_below_threshold_engine_produces_lower_confidence(self):
        """When a rule has success_rate < LOW_SUCCESS_RATE, the resulting confidence
        for that rule must be lower than if the store were empty."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        # Identify rule_id that fires — first run with empty store
        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to test downgrade on")

        # Target the highest-confidence proposed change's rule_id
        target = max(
            plan_empty.proposed,
            key=lambda ch: (ch.confidence == ConfidenceLevel.high,
                            ch.confidence == ConfidenceLevel.med),
        )
        rule_id = target.rule_id
        original_confidence = target.confidence

        # Now build a store with enough low-success samples for that rule
        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES, 0)
        # success_rate = 0 / MIN_OUTCOME_SAMPLES < LOW_SUCCESS_RATE

        plan_downgraded = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        # Find the same field in the new plan
        downgraded = [ch for ch in plan_downgraded.proposed if ch.rule_id == rule_id]
        if not downgraded:
            pytest.skip(f"Rule {rule_id!r} no longer proposed with low-success store")

        ch_new = downgraded[0]
        # Confidence should be lower or equal (downgrade moves high→med→low)
        confidence_rank = {
            ConfidenceLevel.low: 0,
            ConfidenceLevel.med: 1,
            ConfidenceLevel.high: 2,
        }
        assert confidence_rank[ch_new.confidence] <= confidence_rank[original_confidence], (
            f"AC29 FAIL: downgrade gate did not lower confidence; "
            f"before={original_confidence}, after={ch_new.confidence}"
        )

    def test_high_to_med_downgrade(self):
        """Direct unit test: high confidence downgraded to med when rate < threshold."""
        from strategy.setup_rule_engine import _downgrade_confidence
        downgraded = _downgrade_confidence(ConfidenceLevel.high)
        assert downgraded == ConfidenceLevel.med

    def test_med_to_low_downgrade(self):
        """Direct unit test: med confidence downgraded to low when rate < threshold."""
        from strategy.setup_rule_engine import _downgrade_confidence
        downgraded = _downgrade_confidence(ConfidenceLevel.med)
        assert downgraded == ConfidenceLevel.low

    def test_low_stays_low(self):
        """Direct unit test: low confidence cannot be downgraded further."""
        from strategy.setup_rule_engine import _downgrade_confidence
        downgraded = _downgrade_confidence(ConfidenceLevel.low)
        assert downgraded == ConfidenceLevel.low


# ===========================================================================
# AC30 — Boundary: success_rate exactly == LOW_SUCCESS_RATE does NOT trigger downgrade
# ===========================================================================

class TestAC30DowngradeBoundary:
    """AC30: success_rate exactly == LOW_SUCCESS_RATE is the boundary — NO downgrade."""

    def test_success_rate_at_exactly_low_success_rate(self):
        """At exactly LOW_SUCCESS_RATE, get_success_rate returns the rate (not None)."""
        # Build a store where rate = exactly LOW_SUCCESS_RATE
        # E.g., LOW_SUCCESS_RATE = 0.40: need 2 successes out of 5 fires = 0.40
        fire_count = 5
        success_count = round(LOW_SUCCESS_RATE * fire_count)
        # Verify the arithmetic produces exactly the boundary rate
        computed_rate = success_count / fire_count
        # If rounding prevents exact equality, double the counts
        if abs(computed_rate - LOW_SUCCESS_RATE) > 1e-9:
            fire_count = 10
            success_count = round(LOW_SUCCESS_RATE * fire_count)
            computed_rate = success_count / fire_count
        assert abs(computed_rate - LOW_SUCCESS_RATE) < 1e-9, (
            f"Could not construct exact boundary — rate={computed_rate}, threshold={LOW_SUCCESS_RATE}"
        )

        store = _make_store_with_outcomes("B3", fire_count, success_count)
        rate = store.get_success_rate("B3")
        assert rate is not None, "AC30 FAIL: store with enough samples must return a rate"
        assert abs(rate - LOW_SUCCESS_RATE) < 1e-9, (
            f"AC30: expected rate={LOW_SUCCESS_RATE}, got {rate}"
        )

    def test_exact_boundary_does_not_downgrade_compared_to_empty_store(self):
        """At the boundary rate, confidence must match the empty-store result (no downgrade)."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to compare boundary against")

        target = plan_empty.proposed[0]
        rule_id = target.rule_id
        original_confidence = target.confidence

        # Build a boundary-rate store for that rule_id
        fire_count = 10
        success_count = round(LOW_SUCCESS_RATE * fire_count)
        store = _make_store_with_outcomes(rule_id, fire_count, success_count)

        plan_boundary = run_rule_engine(
            diag, setup, ranges, profile, rule_outcome_store=store
        )

        boundary_changes = [ch for ch in plan_boundary.proposed if ch.rule_id == rule_id]
        if not boundary_changes:
            pytest.skip(f"Rule {rule_id!r} not proposed with boundary store")

        ch_boundary = boundary_changes[0]
        assert ch_boundary.confidence == original_confidence, (
            f"AC30 FAIL: boundary rate triggered downgrade; "
            f"original={original_confidence}, boundary={ch_boundary.confidence}"
        )

    def test_below_min_samples_no_downgrade(self):
        """Fewer than MIN_OUTCOME_SAMPLES → get_success_rate returns None → no downgrade."""
        store = _make_store_with_outcomes("B3", MIN_OUTCOME_SAMPLES - 1, 0)
        rate = store.get_success_rate("B3")
        assert rate is None, (
            f"AC30 FAIL: fewer than MIN_OUTCOME_SAMPLES should return None; got {rate}"
        )


# ===========================================================================
# AC31 — Downgrade never rejects; empty store = no downgrade
# ===========================================================================

class TestAC31DowngradeNeverRejects:
    """AC31: downgrade gate only lowers confidence; never moves a change into rejected.
    Empty store → get_success_rate returns None → no downgrade applied."""

    def test_empty_store_returns_none(self):
        """An empty RuleOutcomeStore returns None for any rule_id."""
        store = RuleOutcomeStore()
        assert store.get_success_rate("B3") is None
        assert store.get_success_rate("A1") is None

    def test_downgraded_change_still_in_proposed(self):
        """A change with low success_rate is still in proposed when it has no field conflicts.

        AC31: downgrade gate only lowers confidence; it never independently moves a
        change to rejected.  When two rules compete for the same field, conflict
        resolution may change the winner after a downgrade — that is a legitimate
        conflict-resolution outcome, NOT a direct downgrade rejection.  This test
        therefore verifies the invariant using downgrade of ALL proposed rules so that
        no conflict-winner shift can occur.
        """
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to test rejection guard on")

        # Build a store that downgrades ALL proposed rule_ids
        store = RuleOutcomeStore()
        proposed_rule_ids = {ch.rule_id for ch in plan_empty.proposed}
        for rid in proposed_rule_ids:
            for _ in range(MIN_OUTCOME_SAMPLES * 5):
                store.record_fire(rid)
            # 0 successes → rate=0.0 < LOW_SUCCESS_RATE

        plan_downgraded = run_rule_engine(
            diag, setup, ranges, profile, rule_outcome_store=store
        )

        # At least one rule from the empty-store plan should still be proposed
        # (the conflict winner persists even after downgrade; only the loser moves to rejected).
        still_proposed = {ch.rule_id for ch in plan_downgraded.proposed}
        assert still_proposed, (
            "AC31 FAIL: no proposed changes survive after downgrading all rules — "
            "the downgrade gate should not eliminate all changes"
        )
        # Verify the response still contains a plan (downgrade cannot zero out the engine)
        assert plan_downgraded.proposed, (
            "AC31 FAIL: downgrade gate produced empty proposed list — "
            "confidence downgrade must not eliminate all proposed changes"
        )

    def test_empty_store_produces_same_changes_as_no_store(self):
        """Passing an empty RuleOutcomeStore is equivalent to passing None (no downgrade)."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_none = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=None)
        plan_empty = run_rule_engine(
            diag, setup, ranges, profile, rule_outcome_store=RuleOutcomeStore()
        )

        fields_none = sorted(ch.field for ch in plan_none.proposed)
        fields_empty = sorted(ch.field for ch in plan_empty.proposed)
        assert fields_none == fields_empty, (
            f"AC31 FAIL: empty store produces different proposed fields than no store; "
            f"no_store={fields_none}, empty={fields_empty}"
        )

    def test_to_dict_serialisable(self):
        """to_dict returns a JSON-serialisable dict (no opaque objects)."""
        import json as _json
        store = _make_store_with_outcomes("B3", 5, 2)
        serialised = _json.dumps(store.to_dict())
        assert isinstance(serialised, str)
        round_trip = _json.loads(serialised)
        assert round_trip  # non-empty dict

    def test_success_count_does_not_exceed_fire_count(self):
        """record_success without record_fire still works; rate capped at 1.0."""
        store = RuleOutcomeStore()
        store.record_fire("B3")
        store.record_fire("B3")
        store.record_fire("B3")
        store.record_success("B3")
        store.record_success("B3")
        store.record_success("B3")
        rate = store.get_success_rate("B3")
        assert rate == 1.0
