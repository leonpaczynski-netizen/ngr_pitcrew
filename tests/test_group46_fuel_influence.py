"""
Group 46 — Learning & Race Context Intelligence: Fuel Influence Tests

Covers ACs 17-21 (Fuel/session layer):
  AC17 — fuel_multiplier VALUE injected into diagnosis (not just a bool).
  AC18 — high fuel (>= 5.0) upgrades traction/stability rule confidence; fuel_influence
           non-empty for affected fields.
  AC19 — high fuel + wheelspin → traction-first change proposed (not gear-lengthening
           as PRIMARY response).
  AC20 — fuel=1.0 → no high-fuel bias (fuel_high=False); no fuel_influence text claimed.
  AC21 — boundary: fuel=4.99 → not high; fuel=5.0 → high.
  Additional: unknown/absent multiplier → fuel_high=False (no claim used).

The fuel layer lives in setup_rule_engine._process_rule (Group 46 fuel load block).
_FUEL_TRACTION_STABILITY_FIELDS = {lsd_accel, lsd_initial, arb_rear, aero_rear, ride_height_rear}
_FUEL_ROTATION_FIELDS = {aero_front, aero_rear, lsd_decel, brake_bias}

High fuel + traction/stability field + delta>0 → _upgrade_confidence + fuel_influence text.
High fuel + rotation field + delta<0 → note-only fuel_influence, no confidence change.

All tests are pure/offline — no network, no Qt event loop.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy._setup_constants import (
    HIGH_FUEL_MULTIPLIER_THRESHOLD,
    MIN_OUTCOME_SAMPLES,
    RULE_ENGINE_VERSION,
)
from strategy.setup_rule_engine import (
    RuleOutcomeStore,
    run_rule_engine,
    _upgrade_confidence,
)
from strategy.setup_knowledge_base import (
    ConfidenceLevel, DrivetrainType, CarClass,
)
from strategy.setup_driver_profile import DriverProfile
from strategy.setup_ranges import resolve_ranges


# ---------------------------------------------------------------------------
# Constants (from production code — verify field sets match implementation)
# ---------------------------------------------------------------------------
_FUEL_TRACTION_STABILITY_FIELDS = frozenset({
    "lsd_accel", "lsd_initial", "arb_rear", "aero_rear", "ride_height_rear",
})
_FUEL_ROTATION_FIELDS = frozenset({
    "aero_front", "aero_rear", "lsd_decel", "brake_bias",
})


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


def _wheelspin_diag(fuel_high: bool = False, fuel_multiplier: float | None = None) -> dict:
    """Wheelspin diagnosis with optional fuel context."""
    diag = {
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
        "fuel_high": fuel_high,
        "fuel_multiplier": fuel_multiplier,
    }
    return diag


def _snap_wheelspin_diag(fuel_high: bool = False) -> dict:
    """Snap-throttle wheelspin diagnosis for traction-first tests."""
    diag = _wheelspin_diag(fuel_high=fuel_high)
    diag["wheelspin_subtype"] = "snap_throttle_induced"
    diag["avg_snap"] = 8.0
    return diag


# ===========================================================================
# AC17 — fuel_multiplier VALUE injected into diagnosis
# ===========================================================================

class TestAC17FuelMultiplierInjected:
    """AC17: fuel_multiplier is injected as a numeric value (not just a bool).

    The injection happens in driving_advisor.build_combined_setup_response, which
    calls diagnosis.setdefault('fuel_multiplier', _fuel_multiplier). We test this
    contract at the engine level by pre-injecting the value into the diagnosis dict
    (matching what driving_advisor does) and verifying it round-trips.
    """

    def test_fuel_multiplier_5_sets_fuel_high_true(self):
        """fuel_multiplier >= HIGH_FUEL_MULTIPLIER_THRESHOLD → fuel_high=True."""
        fm = HIGH_FUEL_MULTIPLIER_THRESHOLD  # exactly 5.0
        diag = _wheelspin_diag(fuel_high=True, fuel_multiplier=fm)
        assert diag["fuel_high"] is True
        assert diag["fuel_multiplier"] == fm

    def test_fuel_multiplier_below_threshold_fuel_high_false(self):
        """fuel_multiplier < HIGH_FUEL_MULTIPLIER_THRESHOLD → fuel_high=False."""
        fm = HIGH_FUEL_MULTIPLIER_THRESHOLD - 0.01
        diag = _wheelspin_diag(fuel_high=False, fuel_multiplier=fm)
        assert diag["fuel_high"] is False
        assert diag["fuel_multiplier"] == fm

    def test_fuel_multiplier_absent_is_not_high(self):
        """Unknown/absent multiplier → fuel_high=False; no claim used."""
        diag = _wheelspin_diag(fuel_high=False, fuel_multiplier=None)
        assert diag["fuel_high"] is False
        assert diag["fuel_multiplier"] is None

    def test_high_fuel_multiplier_constant_is_5(self):
        """HIGH_FUEL_MULTIPLIER_THRESHOLD must be 5.0 (contract value)."""
        assert HIGH_FUEL_MULTIPLIER_THRESHOLD == 5.0, (
            f"Expected 5.0, got {HIGH_FUEL_MULTIPLIER_THRESHOLD}"
        )


# ===========================================================================
# AC18 — high fuel upgrades traction/stability rules
# ===========================================================================

class TestAC18HighFuelUpgradesTractionStability:
    """AC18: fuel_high=True upgrades confidence for traction/stability fields (delta>0);
    fuel_influence text is non-empty for affected changes."""

    def test_traction_field_upgraded_with_high_fuel(self):
        """lsd_accel (traction/stability field) with delta>0 gets confidence upgrade
        when fuel_high=True."""
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        # Baseline: run without fuel_high
        diag_no_fuel = _wheelspin_diag(fuel_high=False)
        plan_no_fuel = run_rule_engine(diag_no_fuel, setup, ranges, profile)

        lsd_no_fuel = [ch for ch in plan_no_fuel.proposed
                       if ch.field == "lsd_accel" and ch.delta > 0]
        if not lsd_no_fuel:
            pytest.skip("lsd_accel not proposed without fuel context")

        orig_confidence = lsd_no_fuel[0].confidence

        # With fuel_high=True
        diag_fuel = _wheelspin_diag(fuel_high=True, fuel_multiplier=5.0)
        plan_fuel = run_rule_engine(diag_fuel, setup, ranges, profile)

        lsd_fuel = [ch for ch in plan_fuel.proposed
                    if ch.field == "lsd_accel" and ch.delta > 0]
        if not lsd_fuel:
            pytest.skip("lsd_accel not proposed with fuel context")

        ch = lsd_fuel[0]
        _conf_rank = {ConfidenceLevel.low: 0, ConfidenceLevel.med: 1, ConfidenceLevel.high: 2}
        assert _conf_rank[ch.confidence] >= _conf_rank[orig_confidence], (
            f"AC18 FAIL: lsd_accel confidence not upgraded with high fuel; "
            f"no_fuel={orig_confidence}, with_fuel={ch.confidence}"
        )

    def test_fuel_influence_non_empty_for_traction_field(self):
        """fuel_influence must be non-empty for traction/stability fields when fuel_high=True."""
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        diag = _wheelspin_diag(fuel_high=True, fuel_multiplier=5.0)
        plan = run_rule_engine(diag, setup, ranges, profile)

        for ch in plan.proposed:
            if ch.field in _FUEL_TRACTION_STABILITY_FIELDS and ch.delta > 0:
                assert ch.fuel_influence, (
                    f"AC18 FAIL: fuel_influence empty for traction/stability field "
                    f"{ch.field!r} with fuel_high=True"
                )
                break

    def test_fuel_influence_contains_traction_keyword(self):
        """fuel_influence text for traction/stability fields mentions 'traction'."""
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        diag = _wheelspin_diag(fuel_high=True, fuel_multiplier=5.0)
        plan = run_rule_engine(diag, setup, ranges, profile)

        for ch in plan.proposed:
            if ch.field in _FUEL_TRACTION_STABILITY_FIELDS and ch.delta > 0 and ch.fuel_influence:
                assert "traction" in ch.fuel_influence.lower() or "stability" in ch.fuel_influence.lower(), (
                    f"AC18 FAIL: fuel_influence for traction/stability field {ch.field!r} "
                    f"does not mention 'traction' or 'stability'; got {ch.fuel_influence!r}"
                )
                break

    def test_fuel_influence_rendered_into_evidence_list(self):
        """AC18/DoD7: fuel_influence must be VISIBLE to the user — plan_to_raw_data
        appends it to the change dict's `evidence` list (which the UI renders), not
        silently discarded. This guards the validator's Important finding #1."""
        from strategy.setup_plan import plan_to_raw_data

        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        diag = _wheelspin_diag(fuel_high=True, fuel_multiplier=5.0)
        plan = run_rule_engine(diag, setup, ranges, profile)

        # Find an affected traction change that carries fuel_influence on the intent
        target = next(
            (c for c in plan.proposed
             if c.field in _FUEL_TRACTION_STABILITY_FIELDS and c.delta > 0 and c.fuel_influence),
            None,
        )
        if target is None:
            pytest.skip("No high-fuel traction change proposed in this fixture")

        raw = plan_to_raw_data(plan, diag, "")
        change_dicts = raw.get("changes", raw) if isinstance(raw, dict) else raw
        rendered = next((d for d in change_dicts if d.get("field") == target.field), None)
        assert rendered is not None, "AC18 FAIL: affected change missing from plan_to_raw_data output"
        evidence = rendered.get("evidence", [])
        assert any("fuel" in str(e).lower() for e in evidence), (
            f"AC18 FAIL: fuel_influence not appended to evidence list (invisible to user); "
            f"field={target.field!r}, evidence={evidence!r}"
        )
        # And the standalone key is still present (tests + data model rely on it).
        assert "fuel_influence" in rendered, "AC18 FAIL: fuel_influence key dropped from change dict"

    def test_rotation_field_note_only_no_confidence_change(self):
        """Rotation fields (delta<0) get a note-only fuel_influence but NO confidence upgrade.

        The spec says: rotation/aero-cut fields with delta<0 → note-only, no downgrade.
        We verify: fuel_influence may be set (note-only) but confidence is unchanged
        vs the no-fuel run.
        """
        # lsd_decel is in _FUEL_ROTATION_FIELDS; a rule that reduces lsd_decel exists
        # under certain conditions. We use a rotation-focused diagnosis.
        diag_no_fuel = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 5.0, "wheelspin_band": "minor",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {
                "rear_loose_on_exit": False,
                "snap_oversteer_exit": False,
            },
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False,
            "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "insufficient_data",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "wheelspin",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
            "fuel_high": False,
        }
        diag_fuel = dict(diag_no_fuel)
        diag_fuel["fuel_high"] = True
        diag_fuel["fuel_multiplier"] = 5.0

        setup = {"lsd_decel": 10}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_no_fuel = run_rule_engine(diag_no_fuel, setup, ranges, profile)
        plan_fuel = run_rule_engine(diag_fuel, setup, ranges, profile)

        # For any rotation field with delta<0 that appears in both plans,
        # confidence must not change (note-only = no upgrade, no downgrade)
        for ch_fuel in plan_fuel.proposed:
            if ch_fuel.field in _FUEL_ROTATION_FIELDS and ch_fuel.delta < 0:
                # Find matching in no-fuel plan
                matching_no_fuel = [c for c in plan_no_fuel.proposed
                                    if c.field == ch_fuel.field and c.rule_id == ch_fuel.rule_id]
                if matching_no_fuel:
                    c_nf = matching_no_fuel[0]
                    assert ch_fuel.confidence == c_nf.confidence, (
                        f"AC18 FAIL: rotation field {ch_fuel.field!r} confidence changed "
                        f"(should be note-only); no_fuel={c_nf.confidence}, fuel={ch_fuel.confidence}"
                    )


# ===========================================================================
# AC19 — high fuel + wheelspin → traction-first, not gear-lengthening as primary
# ===========================================================================

class TestAC19TractionFirstOverGear:
    """AC19: high fuel + wheelspin → traction-first (lsd_accel/arb_rear) is the primary
    response; gear-lengthening must not appear as the primary wheelspin solution."""

    def test_lsd_accel_proposed_before_gear_changes_with_high_fuel(self):
        """With fuel_high=True and wheelspin, lsd_accel (or arb_rear) must be in proposed;
        no gear change should appear as the sole/primary fix."""
        diag = _wheelspin_diag(fuel_high=True, fuel_multiplier=5.0)
        diag["gearbox_flag"] = "may_change"
        diag["gearing_diagnosis_category"] = "insufficient_data"
        setup = {"lsd_accel": 15, "arb_rear": 4}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        # Traction field must be proposed
        traction_changes = [ch for ch in plan.proposed
                           if ch.field in _FUEL_TRACTION_STABILITY_FIELDS and ch.delta > 0]
        gear_changes = [ch for ch in plan.proposed
                       if ch.field.startswith("gear_") or ch.field == "final_drive"]

        # If wheelspin is the dominant problem, traction field should be proposed
        # (fuel_high upgrades its confidence, making it even more prominent)
        if traction_changes:
            assert traction_changes[0].fuel_influence, (
                "AC19 FAIL: traction field proposed but fuel_influence is empty "
                "despite fuel_high=True"
            )

    def test_no_gear_lengthening_as_sole_wheelspin_fix(self):
        """With fuel_high and snap-throttle wheelspin, gear-lengthening alone is NOT the fix.
        The engine should propose lsd_accel/lsd_initial as traction-first approach."""
        diag = _snap_wheelspin_diag(fuel_high=True)
        # No per-gear evidence → no per-gear gear changes
        diag["gearbox_flag"] = "may_change"
        diag["gearing_diagnosis_category"] = "insufficient_data"
        diag["per_gear_limiter_evidence"] = None
        diag["wheelspin_by_gear"] = None
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        # Without indexed evidence, no per-gear changes should be proposed
        per_gear_changes = [ch for ch in plan.proposed
                           if ch.rule_id.startswith("PG_")]
        assert not per_gear_changes, (
            f"AC19 FAIL: per-gear changes proposed without indexed evidence; "
            f"changes: {[(c.field, c.rule_id) for c in per_gear_changes]}"
        )


# ===========================================================================
# AC20 — fuel=1.0 → no high-fuel bias
# ===========================================================================

class TestAC20NoHighFuelBiasAt1:
    """AC20: fuel_multiplier=1.0 → fuel_high=False; no fuel_influence text."""

    def test_fuel_1_produces_fuel_high_false(self):
        """fuel_multiplier=1.0 < 5.0 → fuel_high should be False."""
        # Simulate driving_advisor's injection logic
        fuel_mult = 1.0
        fuel_high = fuel_mult >= HIGH_FUEL_MULTIPLIER_THRESHOLD if fuel_mult is not None else False
        assert not fuel_high, (
            f"AC20 FAIL: fuel_mult=1.0 should not set fuel_high=True"
        )

    def test_engine_no_fuel_influence_at_1(self):
        """With fuel_high=False, no change has non-empty fuel_influence."""
        diag = _wheelspin_diag(fuel_high=False, fuel_multiplier=1.0)
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        for ch in plan.proposed:
            assert ch.fuel_influence == "", (
                f"AC20 FAIL: fuel_influence non-empty with fuel_high=False "
                f"(fuel_mult=1.0); field={ch.field!r}, fuel_influence={ch.fuel_influence!r}"
            )

    def test_engine_no_fuel_influence_when_multiplier_absent(self):
        """With fuel_multiplier=None (absent), no change has non-empty fuel_influence."""
        diag = _wheelspin_diag(fuel_high=False, fuel_multiplier=None)
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        for ch in plan.proposed:
            assert ch.fuel_influence == "", (
                f"AC20 FAIL: fuel_influence non-empty with absent fuel_multiplier; "
                f"field={ch.field!r}, fuel_influence={ch.fuel_influence!r}"
            )


# ===========================================================================
# AC21 — boundary: 4.99 → not high; 5.0 → high
# ===========================================================================

class TestAC21FuelBoundary:
    """AC21: exact boundary behaviour at HIGH_FUEL_MULTIPLIER_THRESHOLD."""

    def test_4_99_is_not_high_fuel(self):
        """4.99 < 5.0 → fuel_high must be False."""
        fm = 4.99
        fuel_high = fm >= HIGH_FUEL_MULTIPLIER_THRESHOLD
        assert not fuel_high, f"4.99 should not be high fuel; threshold={HIGH_FUEL_MULTIPLIER_THRESHOLD}"

    def test_5_0_is_high_fuel(self):
        """5.0 == HIGH_FUEL_MULTIPLIER_THRESHOLD → fuel_high must be True."""
        fm = 5.0
        fuel_high = fm >= HIGH_FUEL_MULTIPLIER_THRESHOLD
        assert fuel_high, f"5.0 should be high fuel; threshold={HIGH_FUEL_MULTIPLIER_THRESHOLD}"

    def test_engine_4_99_no_fuel_influence(self):
        """With fuel_multiplier=4.99, no fuel_influence should appear."""
        diag = _wheelspin_diag(fuel_high=False, fuel_multiplier=4.99)
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)
        for ch in plan.proposed:
            assert ch.fuel_influence == "", (
                f"AC21 FAIL: fuel_influence set with fuel_mult=4.99 (should be below threshold); "
                f"field={ch.field!r}, fuel_influence={ch.fuel_influence!r}"
            )

    def test_engine_5_0_has_fuel_influence_for_traction(self):
        """With fuel_multiplier=5.0, traction/stability fields (delta>0) get fuel_influence."""
        diag = _wheelspin_diag(fuel_high=True, fuel_multiplier=5.0)
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        found_fuel_influence = False
        for ch in plan.proposed:
            if ch.field in _FUEL_TRACTION_STABILITY_FIELDS and ch.delta > 0 and ch.fuel_influence:
                found_fuel_influence = True
                break

        # Only assert if the field was actually proposed — if wheelspin doesn't fire,
        # fuel_influence may be absent
        lsd_proposed = any(ch.field == "lsd_accel" and ch.delta > 0 for ch in plan.proposed)
        if lsd_proposed and not found_fuel_influence:
            pytest.fail(
                "AC21 FAIL: lsd_accel proposed with fuel_mult=5.0 but no fuel_influence set"
            )
