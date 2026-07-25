"""Adaptive Per-Gear Shift Strategy — view-model unit tests."""
from __future__ import annotations

import pytest

from strategy.shift_strategy_engine import (
    ShiftConfidence,
    ShiftProfile,
    ShiftStrategyResult,
    PerGearShiftDecision,
)
from strategy.shift_strategy_inputs import ShiftStrategyInputs, compute_shift_fingerprint
from strategy.shift_strategy_engine import compute_shift_strategy
from strategy.shift_strategy_constants import SHIFT_STRATEGY_VERSION
from ui.shift_strategy_vm import (
    GearDecisionRow,
    ShiftStrategyVM,
    build_shift_strategy_vm,
    confidence_tone,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inputs_full() -> ShiftStrategyInputs:
    return ShiftStrategyInputs(
        car_id="TestCar",
        gear_ratios=(3.5, 2.5, 1.9),
        final_drive=4.0,
        ecu_output=100.0,
        power_restrictor=100.0,
        ballast_kg=0.0,
        weight_kg=1200.0,
        aspiration="NA",
        peak_power_rpm=7000,
        peak_torque_rpm=5500,
        redline=8000,
        active_setup_revision=1,
    )


def _result_full(req_pct=0.0) -> ShiftStrategyResult:
    return compute_shift_strategy(_inputs_full(), required_fuel_saving_pct=req_pct)


def _result_insufficient() -> ShiftStrategyResult:
    inp = ShiftStrategyInputs(
        car_id="", gear_ratios=(), final_drive=0.0,
        ecu_output=100.0, power_restrictor=100.0, ballast_kg=0.0,
        weight_kg=0.0, aspiration="NA",
        peak_power_rpm=None, peak_torque_rpm=None, redline=None,
        active_setup_revision=0,
    )
    return compute_shift_strategy(inp)


# ---------------------------------------------------------------------------
# Never bare "0"
# ---------------------------------------------------------------------------

class TestNoBareZero:
    def test_rpm_delta_zero_shown_as_no_change(self):
        result = _result_full(req_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="qualifying")
        for row in vm.rows:
            if row.has_data:
                # At 0% target, delta should be 0 (no change) not bare "0"
                assert row.rpm_delta != "0", (
                    f"rpm_delta must not be bare '0'; got {row.rpm_delta!r}"
                )

    def test_time_cost_zero_shown_as_no_change(self):
        result = _result_full(req_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="race")
        for row in vm.rows:
            if row.has_data:
                assert row.time_cost != "0"

    def test_fuel_saving_zero_shown_as_no_change(self):
        result = _result_full(req_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="race")
        for row in vm.rows:
            if row.has_data:
                assert row.fuel_saving != "0"

    def test_predicted_saving_zero_not_bare_zero(self):
        result = _result_full(req_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.predicted_saving_text != "0"

    def test_time_cost_text_zero_not_bare_zero(self):
        result = _result_full(req_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.time_cost_text != "0"


# ---------------------------------------------------------------------------
# Missing data → next-action text
# ---------------------------------------------------------------------------

class TestMissingNextAction:
    def test_none_result_gives_next_action(self):
        vm = build_shift_strategy_vm(None)
        assert vm.banner_text
        assert vm.stepper_blocker_text
        assert "gear ratio" in vm.stepper_blocker_text.lower() or "Transmission" in vm.stepper_go_to_tab

    def test_insufficient_evidence_gives_next_action(self):
        result = _result_insufficient()
        vm = build_shift_strategy_vm(result)
        assert vm.evidence_readiness_text
        assert vm.evidence_readiness_text.strip() != ""
        # Should mention what's missing, not be blank
        assert len(vm.evidence_readiness_text) > 5

    def test_missing_engine_data_banner_not_blank(self):
        result = _result_insufficient()
        vm = build_shift_strategy_vm(result)
        assert vm.banner_text.strip() != ""

    def test_stepper_blocker_not_blank_when_missing(self):
        result = _result_insufficient()
        vm = build_shift_strategy_vm(result)
        assert vm.stepper_blocker_text.strip() != ""

    def test_rows_missing_show_next_action_not_empty_string(self):
        result = _result_insufficient()
        vm = build_shift_strategy_vm(result)
        # No rows from an insufficient result (no gear ratios)
        # The evidence_readiness_text must have something meaningful
        assert vm.evidence_readiness_text != ""


# ---------------------------------------------------------------------------
# Provisional badge
# ---------------------------------------------------------------------------

class TestProvisionalBadge:
    def test_provisional_badge_in_fuel_saving(self):
        result = _result_full(req_pct=5.0)
        vm = build_shift_strategy_vm(result, profile="race")
        # Find a row with actual fuel saving
        saving_rows = [r for r in vm.rows if r.has_data and "0 (no change)" not in r.fuel_saving and r.fuel_saving != "—"]
        if saving_rows:
            assert any("PROVISIONAL" in r.fuel_saving for r in saving_rows), (
                "Fuel saving text must carry PROVISIONAL badge"
            )

    def test_banner_advisory_when_provisional(self):
        result = _result_full(req_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="qualifying")
        # A valid result with manual engine data is always PROVISIONAL
        assert vm.overall_confidence_key == ShiftConfidence.PROVISIONAL.value
        assert vm.banner_tone == "advisory"

    def test_predicted_saving_has_provisional_badge_when_nonzero(self):
        result = _result_full(req_pct=5.0)
        vm = build_shift_strategy_vm(result, profile="race")
        if vm.predicted_saving_text not in ("—", "0 (no change)"):
            assert "PROVISIONAL" in vm.predicted_saving_text


# ---------------------------------------------------------------------------
# Stale precedence
# ---------------------------------------------------------------------------

class TestStalePrecedence:
    def test_stale_fingerprint_sets_stale_state(self):
        result = _result_full()
        fp = result.configuration_fingerprint
        # Pass a different stored fingerprint → stale
        vm = build_shift_strategy_vm(result, stored_fingerprint="different_fp")
        assert vm.config_is_stale is True
        assert vm.overall_confidence_key == ShiftConfidence.STALE.value

    def test_stale_banner_tone_is_warn(self):
        result = _result_full()
        vm = build_shift_strategy_vm(result, stored_fingerprint="old_fp")
        assert vm.banner_tone == "warn"

    def test_stale_overrides_provisional(self):
        result = _result_full()
        vm_provisional = build_shift_strategy_vm(result, stored_fingerprint=None)
        vm_stale = build_shift_strategy_vm(result, stored_fingerprint="old_fp")
        assert vm_provisional.overall_confidence_key == ShiftConfidence.PROVISIONAL.value
        assert vm_stale.overall_confidence_key == ShiftConfidence.STALE.value

    def test_matching_fingerprint_is_not_stale(self):
        result = _result_full()
        vm = build_shift_strategy_vm(result, stored_fingerprint=result.configuration_fingerprint)
        assert vm.config_is_stale is False

    def test_none_stored_fingerprint_is_not_stale(self):
        result = _result_full()
        vm = build_shift_strategy_vm(result, stored_fingerprint=None)
        assert vm.config_is_stale is False


# ---------------------------------------------------------------------------
# Confidence key → tone mapping
# ---------------------------------------------------------------------------

class TestConfidenceToneMapping:
    @pytest.mark.parametrize("key,expected_tone", [
        (ShiftConfidence.HIGH.value,                  "success"),
        (ShiftConfidence.MEDIUM.value,                "info"),
        (ShiftConfidence.LOW.value,                   "warn"),
        (ShiftConfidence.PROVISIONAL.value,           "advisory"),
        (ShiftConfidence.INSUFFICIENT_EVIDENCE.value, "neutral"),
        (ShiftConfidence.STALE.value,                 "warn"),
    ])
    def test_confidence_tone_mapping(self, key, expected_tone):
        assert confidence_tone(key) == expected_tone

    def test_unknown_key_defaults_to_neutral(self):
        assert confidence_tone("not_a_real_key") == "neutral"

    def test_insufficient_evidence_label_is_needs_data(self):
        result = _result_insufficient()
        vm = build_shift_strategy_vm(result)
        # The confidence label for INSUFFICIENT_EVIDENCE must be "NEEDS DATA"
        from ui.shift_strategy_vm import _CONF_DISPLAY
        assert _CONF_DISPLAY[ShiftConfidence.INSUFFICIENT_EVIDENCE.value] == "NEEDS DATA"


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_build_vm_never_raises_on_none(self):
        vm = build_shift_strategy_vm(None)
        assert vm is not None

    def test_build_vm_never_raises_on_bad_result(self):
        vm = build_shift_strategy_vm("not a result", profile="qualifying")
        assert vm is not None

    def test_build_vm_never_raises_on_empty_profile(self):
        result = _result_insufficient()
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm is not None


# ---------------------------------------------------------------------------
# Row structure
# ---------------------------------------------------------------------------

class TestRowStructure:
    def test_row_count_matches_gear_pairs(self):
        result = _result_full()
        vm = build_shift_strategy_vm(result, profile="qualifying")
        # 3 gear ratios → 2 pairs
        assert len(vm.rows) == 2

    def test_row_labels_format(self):
        result = _result_full()
        vm = build_shift_strategy_vm(result, profile="qualifying")
        assert vm.rows[0].label == "1 → 2"
        assert vm.rows[1].label == "2 → 3"

    def test_valid_rows_have_data(self):
        result = _result_full()
        vm = build_shift_strategy_vm(result, profile="qualifying")
        for row in vm.rows:
            assert row.has_data is True  # all valid with this config

    def test_no_rows_for_insufficient_result(self):
        result = _result_insufficient()
        vm = build_shift_strategy_vm(result, profile="qualifying")
        assert len(vm.rows) == 0
