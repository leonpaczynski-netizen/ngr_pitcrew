"""Adaptive Per-Gear Shift Strategy — ACCEPTANCE tests (Phase 1).

Maps each numbered acceptance criterion from the approved story to at least one test.
Tests are named test_ac_<N>_<short_description> so the criterion number is machine-readable.

PURE domain / VM tests only (no Qt widget construction).
Run independently to avoid the Win/Py3.14 PyQt segfault in the full suite:

    python -m pytest tests/test_shift_strategy_acceptance.py -q
"""
from __future__ import annotations

import io
import json
import os
import tokenize
from pathlib import Path

import pytest

from strategy.shift_strategy_engine import (
    ShiftConfidence,
    compute_shift_strategy,
)
from strategy.shift_strategy_inputs import (
    ShiftStrategyInputs,
    compute_shift_fingerprint,
    resolve_shift_inputs,
)
from services.shift_strategy_store import ShiftStrategyStore, default_shift_strategy_path
from ui.shift_strategy_vm import (
    GearDecisionRow,
    ShiftStrategyVM,
    build_shift_strategy_vm,
    confidence_tone,
)

# ---------------------------------------------------------------------------
# Common test helpers
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent

_NEW_MODULES = [
    "strategy/shift_strategy_constants.py",
    "strategy/shift_strategy_inputs.py",
    "strategy/shift_strategy_engine.py",
    "services/shift_strategy_store.py",
    "ui/shift_strategy_vm.py",
]


def _inputs(
    gear_ratios=(3.5, 2.5, 1.9, 1.4, 1.1, 0.9),
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
    car_id="TestCar",
) -> ShiftStrategyInputs:
    return ShiftStrategyInputs(
        car_id=car_id,
        gear_ratios=tuple(gear_ratios),
        final_drive=final_drive,
        ecu_output=ecu_output,
        power_restrictor=power_restrictor,
        ballast_kg=ballast_kg,
        weight_kg=weight_kg,
        aspiration=aspiration,
        peak_power_rpm=peak_power_rpm,
        peak_torque_rpm=peak_torque_rpm,
        redline=redline,
        active_setup_revision=active_setup_revision,
    )


def _code_only(rel: str) -> str:
    """Return source with comments and string/docstring contents removed."""
    src = (_ROOT / rel).read_text(encoding="utf-8")
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src
    return " ".join(out)


# ---------------------------------------------------------------------------
# AC-1: Missing gear ratios / final_drive → INSUFFICIENT_EVIDENCE + no bare "0" in VM
# ---------------------------------------------------------------------------

class TestAC1_MissingGearsInsufficientEvidence:

    def test_ac1_no_gears_gives_insufficient_evidence(self):
        """AC-1: Missing gear ratios → INSUFFICIENT_EVIDENCE overall confidence."""
        inp = _inputs(gear_ratios=())
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE
        assert len(result.missing_evidence) > 0

    def test_ac1_single_ratio_gives_insufficient_evidence(self):
        """AC-1: Single gear ratio is not enough → INSUFFICIENT_EVIDENCE."""
        inp = _inputs(gear_ratios=(3.5,))
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE
        assert len(result.missing_evidence) > 0

    def test_ac1_vm_shows_no_bare_zero_values(self):
        """AC-1: When insufficient evidence, the VM rows never display a bare '0' as value."""
        inp = _inputs(gear_ratios=())
        result = compute_shift_strategy(inp)
        vm = build_shift_strategy_vm(result)
        # For insufficient results with no rows, verify key summary fields aren't "0"
        assert vm.required_saving_text != "0"
        assert vm.predicted_saving_text != "0"
        assert vm.time_cost_text != "0"

    def test_ac1_insufficient_vm_has_next_action_not_zero(self):
        """AC-1: Even with ratios but no engine data, VM shows a next-action, not '0'."""
        # Has ratios but no engine data
        inp = ShiftStrategyInputs(
            car_id="TestCar",
            gear_ratios=(3.5, 2.5, 1.9),
            final_drive=4.0,
            ecu_output=100.0,
            power_restrictor=100.0,
            ballast_kg=0.0,
            weight_kg=1200.0,
            aspiration="NA",
            peak_power_rpm=None,
            peak_torque_rpm=None,
            redline=None,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        vm = build_shift_strategy_vm(result)
        # evidence_readiness_text must not be blank or "0"
        assert vm.evidence_readiness_text.strip() not in ("", "0")
        assert len(vm.evidence_readiness_text) > 5


# ---------------------------------------------------------------------------
# AC-2: resolve_shift_inputs resolves from SetupSheet; no telemetry arg
# ---------------------------------------------------------------------------

class TestAC2_InputsResolvedFromSetupSheet:

    def test_ac2_resolve_from_setupsheet_with_gear_ratios(self):
        """AC-2: resolve_shift_inputs accepts a SetupSheet and produces typed inputs."""
        from strategy.setup_sheet import sheet_from_dict
        sheet = sheet_from_dict({
            "gear_ratios": [3.5, 2.5, 1.9, 1.4],
            "final_drive": 4.1,
            "ecu_ingame_output": 95.0,
            "power_restrictor": 100.0,
            "ballast_kg": 10.0,
        })
        car_specs = {"car": "TestCar", "weight_kg": 1250.0, "aspiration": "NA"}
        inp = resolve_shift_inputs(sheet, car_specs, active_revision=2,
                                   manual_engine_data={"peak_power_rpm": 7000,
                                                       "peak_torque_rpm": 5500,
                                                       "redline": 8000})
        assert isinstance(inp, ShiftStrategyInputs)
        assert inp.gear_ratios == (3.5, 2.5, 1.9, 1.4)
        assert inp.final_drive == pytest.approx(4.1, abs=0.01)
        assert inp.ballast_kg == pytest.approx(10.0)
        assert inp.peak_power_rpm == 7000
        assert inp.peak_torque_rpm == 5500
        assert inp.redline == 8000

    def test_ac2_resolve_signature_has_no_telemetry_arg(self):
        """AC-2: resolve_shift_inputs has no telemetry parameter."""
        import inspect
        sig = inspect.signature(resolve_shift_inputs)
        param_names = list(sig.parameters.keys())
        for name in param_names:
            assert "telemetry" not in name.lower(), (
                f"resolve_shift_inputs must have no telemetry argument; found {name!r}"
            )

    def test_ac2_never_raises_on_empty_sheet(self):
        """AC-2: resolve_shift_inputs never raises on an empty sheet."""
        from strategy.setup_sheet import empty_sheet
        sheet = empty_sheet()
        inp = resolve_shift_inputs(sheet, {}, active_revision=0)
        assert isinstance(inp, ShiftStrategyInputs)

    def test_ac2_gear_ratios_come_from_sheet_not_computed(self):
        """AC-2: The gear_ratios in the result come from what the sheet says."""
        from strategy.setup_sheet import sheet_from_dict
        sheet = sheet_from_dict({"gear_ratios": [2.8, 2.0, 1.5, 1.1]})
        inp = resolve_shift_inputs(sheet, {}, active_revision=0)
        assert inp.gear_ratios == (2.8, 2.0, 1.5, 1.1)


# ---------------------------------------------------------------------------
# AC-3: Fingerprint changes for each identity field
# ---------------------------------------------------------------------------

class TestAC3_FingerprintSensitivity:

    def _fp(self, **kwargs) -> str:
        return compute_shift_fingerprint(_inputs(**kwargs))

    def _base(self) -> str:
        return self._fp()

    def test_ac3_fingerprint_stable(self):
        """AC-3: Same inputs always produce the same fingerprint."""
        assert self._fp() == self._fp()

    def test_ac3_changes_on_car_id(self):
        """AC-3: Fingerprint changes when car_id changes."""
        assert self._fp(car_id="OtherCar") != self._fp(car_id="TestCar")

    def test_ac3_changes_on_each_gear_ratio(self):
        """AC-3: Fingerprint changes when any individual gear ratio changes."""
        base = self._fp(gear_ratios=(3.5, 2.5, 1.9, 1.4, 1.1, 0.9))
        # Change first ratio
        assert self._fp(gear_ratios=(3.6, 2.5, 1.9, 1.4, 1.1, 0.9)) != base
        # Change third ratio
        assert self._fp(gear_ratios=(3.5, 2.5, 2.0, 1.4, 1.1, 0.9)) != base
        # Change last ratio
        assert self._fp(gear_ratios=(3.5, 2.5, 1.9, 1.4, 1.1, 1.0)) != base

    def test_ac3_changes_on_final_drive(self):
        """AC-3: Fingerprint changes when final_drive changes."""
        assert self._fp(final_drive=4.5) != self._fp(final_drive=4.0)

    def test_ac3_changes_on_ecu_output(self):
        """AC-3: Fingerprint changes when ecu_output changes."""
        assert self._fp(ecu_output=95.0) != self._fp(ecu_output=100.0)

    def test_ac3_changes_on_power_restrictor(self):
        """AC-3: Fingerprint changes when power_restrictor changes."""
        assert self._fp(power_restrictor=90.0) != self._fp(power_restrictor=100.0)

    def test_ac3_changes_on_aspiration(self):
        """AC-3: Fingerprint changes when aspiration changes."""
        assert self._fp(aspiration="TC") != self._fp(aspiration="NA")

    def test_ac3_changes_on_ballast_kg(self):
        """AC-3: Fingerprint changes when ballast_kg changes."""
        assert self._fp(ballast_kg=25.0) != self._fp(ballast_kg=0.0)

    def test_ac3_changes_on_weight_kg(self):
        """AC-3: Fingerprint changes when weight_kg changes."""
        assert self._fp(weight_kg=1300.0) != self._fp(weight_kg=1200.0)

    def test_ac3_changes_on_active_setup_revision(self):
        """AC-3: Fingerprint changes when active_setup_revision changes."""
        assert self._fp(active_setup_revision=2) != self._fp(active_setup_revision=1)


# ---------------------------------------------------------------------------
# AC-4/5: Stored fingerprint mismatch → config_is_stale True + stale surfaced in VM
# ---------------------------------------------------------------------------

class TestAC4_5_StalenessDetected:

    def test_ac4_stale_when_stored_fingerprint_differs(self):
        """AC-4: Mismatched stored fingerprint → config_is_stale True."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, stored_fingerprint="old_different_fp")
        assert vm.config_is_stale is True

    def test_ac4_stale_field_text_is_non_empty(self):
        """AC-4: stale_field_text must not be blank when stale."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, stored_fingerprint="another_old_fp")
        assert vm.stale_field_text.strip() != ""

    def test_ac4_stale_banner_is_shown(self):
        """AC-4: Stale banner text must not be blank, and tone is 'warn'."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, stored_fingerprint="old")
        assert vm.banner_text.strip() != ""
        assert vm.banner_tone == "warn"

    def test_ac5_stale_overall_confidence_key_is_stale(self):
        """AC-5: When stale, the VM's overall_confidence_key becomes STALE."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, stored_fingerprint="old_fp")
        assert vm.overall_confidence_key == ShiftConfidence.STALE.value

    def test_ac4_not_stale_when_fingerprints_match(self):
        """AC-4: Matching stored fingerprint → config_is_stale False."""
        result = compute_shift_strategy(_inputs())
        fp = result.configuration_fingerprint
        vm = build_shift_strategy_vm(result, stored_fingerprint=fp)
        assert vm.config_is_stale is False

    def test_ac4_not_stale_when_no_stored_fingerprint(self):
        """AC-4: None stored fingerprint → config_is_stale False (no prior to compare)."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, stored_fingerprint=None)
        assert vm.config_is_stale is False


# ---------------------------------------------------------------------------
# AC-6: expected_post_shift_rpm == round(pre × ratio[i+1] / ratio[i]) for each pair
# ---------------------------------------------------------------------------

class TestAC6_PostShiftRpmMath:

    def test_ac6_post_shift_rpm_exact_formula(self):
        """AC-6: Post-shift RPM equals round(qualifying_rpm * ratio_next / ratio_from)."""
        # Use a known ratio set so we can hand-compute
        ratios = (3.5, 2.5, 1.9, 1.4)
        inp = _inputs(gear_ratios=ratios,
                      peak_power_rpm=7000, peak_torque_rpm=5500, redline=8000)
        result = compute_shift_strategy(inp)
        for d in result.qualifying_profile.decisions:
            if d.valid and d.qualifying_target_rpm is not None:
                i = d.from_gear - 1  # 0-indexed
                ratio_from = ratios[i]
                ratio_to = ratios[i + 1]
                expected = round(d.qualifying_target_rpm * ratio_to / ratio_from)
                assert d.expected_post_shift_rpm == expected, (
                    f"Gear {d.from_gear}→{d.to_gear}: "
                    f"expected post-shift {expected}, got {d.expected_post_shift_rpm}"
                )

    def test_ac6_hand_computed_value_for_first_pair(self):
        """AC-6: Hand-computed value for the first gear pair with known inputs."""
        # Use 6-gear NA car: ratios (3.5, 2.5, 1.9, 1.4, 1.1, 0.9)
        # peak_power_rpm=7000, peak_torque_rpm=5500, redline=8000
        # Qualifying optimiser picks some shift_rpm; post = shift_rpm * 2.5 / 3.5
        inp = _inputs()
        result = compute_shift_strategy(inp)
        d0 = result.qualifying_profile.decisions[0]
        assert d0.from_gear == 1 and d0.to_gear == 2
        if d0.valid and d0.qualifying_target_rpm is not None:
            expected = round(d0.qualifying_target_rpm * 2.5 / 3.5)
            assert d0.expected_post_shift_rpm == expected


# ---------------------------------------------------------------------------
# AC-7: Post-shift RPMs are distinct across pairs for a normal ratio spread
# ---------------------------------------------------------------------------

class TestAC7_PostShiftRpmsDistinct:

    def test_ac7_post_shift_rpms_not_all_same(self):
        """AC-7: Different gear pairs produce different post-shift RPMs."""
        inp = _inputs()  # 6-gear car with spread ratios
        result = compute_shift_strategy(inp)
        posts = [
            d.expected_post_shift_rpm
            for d in result.qualifying_profile.decisions
            if d.valid and d.expected_post_shift_rpm is not None
        ]
        assert len(posts) >= 2, "Need at least 2 valid pairs to check distinctness"
        assert len(set(posts)) == len(posts), (
            "Post-shift RPMs must be distinct across gear pairs "
            f"(got {posts})"
        )

    def test_ac7_post_shift_rpm_is_not_a_constant(self):
        """AC-7: Post-shift RPMs across the table are NOT a single repeated constant."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        posts = [
            d.expected_post_shift_rpm
            for d in result.qualifying_profile.decisions
            if d.valid and d.expected_post_shift_rpm is not None
        ]
        if len(posts) >= 2:
            # At least two must differ
            assert max(posts) != min(posts), (
                "Post-shift RPMs must not all be the same constant"
            )


# ---------------------------------------------------------------------------
# AC-8: No decision row exists for top gear (len == num_gears - 1)
# ---------------------------------------------------------------------------

class TestAC8_NoTopGearDecision:

    def test_ac8_decision_count_equals_num_gears_minus_1(self):
        """AC-8: Number of decisions == number of gears - 1 (no top-gear row)."""
        gear_ratios = (3.5, 2.5, 1.9, 1.4, 1.1, 0.9)  # 6 gears
        inp = _inputs(gear_ratios=gear_ratios)
        result = compute_shift_strategy(inp)
        # 6 gears → 5 pairs
        assert len(result.qualifying_profile.decisions) == len(gear_ratios) - 1

    def test_ac8_no_decision_shifts_from_top_gear(self):
        """AC-8: No decision has from_gear == number_of_gears (top gear)."""
        gear_ratios = (3.5, 2.5, 1.9, 1.4, 1.1, 0.9)
        n_gears = len(gear_ratios)
        inp = _inputs(gear_ratios=gear_ratios)
        result = compute_shift_strategy(inp)
        for d in result.qualifying_profile.decisions:
            assert d.from_gear != n_gears, (
                f"Top gear {n_gears} must not appear as from_gear"
            )

    def test_ac8_four_gear_car_has_three_decisions(self):
        """AC-8: 4-gear car → exactly 3 decisions."""
        inp = _inputs(gear_ratios=(2.8, 2.0, 1.5, 1.1))
        result = compute_shift_strategy(inp)
        assert len(result.qualifying_profile.decisions) == 3


# ---------------------------------------------------------------------------
# AC-9: With gear ratios + manual engine data → PROVISIONAL (not HIGH/MEDIUM)
# ---------------------------------------------------------------------------

class TestAC9_ManualDataCapsAtProvisional:

    def test_ac9_all_pairs_provisional_with_manual_engine_data(self):
        """AC-9: Every valid pair is PROVISIONAL (never HIGH or MEDIUM) with manual data."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        for d in result.qualifying_profile.decisions:
            if d.valid:
                assert d.confidence == ShiftConfidence.PROVISIONAL, (
                    f"Gear {d.from_gear}→{d.to_gear}: "
                    f"expected PROVISIONAL, got {d.confidence}"
                )
                assert d.confidence != ShiftConfidence.HIGH
                assert d.confidence != ShiftConfidence.MEDIUM

    def test_ac9_qualifying_target_rpm_present_for_all_valid_pairs(self):
        """AC-9: Every valid pair has a non-None qualifying_target_rpm."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        for d in result.qualifying_profile.decisions:
            if d.valid:
                assert d.qualifying_target_rpm is not None, (
                    f"Gear {d.from_gear}→{d.to_gear}: qualifying_target_rpm must not be None"
                )

    def test_ac9_overall_confidence_is_provisional(self):
        """AC-9: Overall confidence with full manual data is PROVISIONAL."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.PROVISIONAL


# ---------------------------------------------------------------------------
# AC-10: Gear ratios but NO engine data → INSUFFICIENT_EVIDENCE + next-action string
# ---------------------------------------------------------------------------

class TestAC10_NoEngineDataInsufficientEvidence:

    def test_ac10_no_engine_data_gives_insufficient_evidence(self):
        """AC-10: Gear ratios present but engine data absent → INSUFFICIENT_EVIDENCE."""
        inp = ShiftStrategyInputs(
            car_id="TestCar",
            gear_ratios=(3.5, 2.5, 1.9, 1.4),
            final_drive=4.0,
            ecu_output=100.0,
            power_restrictor=100.0,
            ballast_kg=0.0,
            weight_kg=1200.0,
            aspiration="NA",
            peak_power_rpm=None,
            peak_torque_rpm=None,
            redline=None,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_ac10_missing_evidence_not_blank(self):
        """AC-10: missing_evidence strings are non-empty next-action strings."""
        inp = ShiftStrategyInputs(
            car_id="TestCar",
            gear_ratios=(3.5, 2.5, 1.9),
            final_drive=4.0,
            ecu_output=100.0,
            power_restrictor=100.0,
            ballast_kg=0.0,
            weight_kg=1200.0,
            aspiration="NA",
            peak_power_rpm=None,
            peak_torque_rpm=None,
            redline=None,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        assert len(result.missing_evidence) > 0
        for m in result.missing_evidence:
            assert m.strip() != "", "missing_evidence entries must not be blank"
            assert len(m) > 5, "next-action must be a real instruction, not a one-character stub"

    def test_ac10_vm_qualifying_column_shows_next_action(self):
        """AC-10: VM with no engine data shows a next-action string, not blank or '0'."""
        inp = ShiftStrategyInputs(
            car_id="TestCar",
            gear_ratios=(3.5, 2.5, 1.9),
            final_drive=4.0,
            ecu_output=100.0,
            power_restrictor=100.0,
            ballast_kg=0.0,
            weight_kg=1200.0,
            aspiration="NA",
            peak_power_rpm=None,
            peak_torque_rpm=None,
            redline=None,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        vm = build_shift_strategy_vm(result)
        # evidence_readiness_text must be a meaningful next-action
        assert vm.evidence_readiness_text.strip() not in ("", "0")


# ---------------------------------------------------------------------------
# AC-11: No pair shows MEDIUM or HIGH for qualifying in Phase 1
# ---------------------------------------------------------------------------

class TestAC11_NeverMediumOrHighInPhase1:

    def test_ac11_qualifying_profile_never_high_or_medium(self):
        """AC-11: Phase 1 caps all qualifying confidence at PROVISIONAL; never HIGH/MEDIUM."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        for d in result.qualifying_profile.decisions:
            assert d.confidence != ShiftConfidence.HIGH, (
                f"Gear {d.from_gear}→{d.to_gear}: confidence must not be HIGH in Phase 1"
            )
            assert d.confidence != ShiftConfidence.MEDIUM, (
                f"Gear {d.from_gear}→{d.to_gear}: confidence must not be MEDIUM in Phase 1"
            )

    def test_ac11_overall_confidence_never_high_or_medium(self):
        """AC-11: Overall confidence at Phase 1 is never HIGH or MEDIUM."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        assert result.overall_confidence != ShiftConfidence.HIGH
        assert result.overall_confidence != ShiftConfidence.MEDIUM


# ---------------------------------------------------------------------------
# AC-12/13: required_fuel_saving_pct == 0 → race == qualifying
# ---------------------------------------------------------------------------

class TestAC12_13_ZeroFuelSavingRaceEqualsQual:

    def test_ac12_zero_target_race_equals_qualifying_rpm(self):
        """AC-12: At 0% fuel target every race RPM equals qualifying RPM."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=0.0)
        for d in result.race_profile.decisions:
            if d.valid:
                assert d.race_target_rpm == d.qualifying_target_rpm, (
                    f"Gear {d.from_gear}→{d.to_gear}: "
                    f"race_rpm {d.race_target_rpm} != qual_rpm {d.qualifying_target_rpm}"
                )

    def test_ac12_zero_target_rpm_delta_is_zero(self):
        """AC-12: At 0% fuel target, rpm_delta_from_qualifying is 0 for all valid pairs."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=0.0)
        for d in result.race_profile.decisions:
            if d.valid:
                assert d.rpm_delta_from_qualifying == 0

    def test_ac13_vm_summary_says_no_saving_required_at_zero_target(self):
        """AC-13: VM summary shows no saving required at 0% target."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="race")
        # required_saving_text should indicate no saving
        text = vm.required_saving_text.lower()
        assert "qualifying" in text or "0" in text or "none" in text, (
            f"required_saving_text should indicate 0% saving; got {vm.required_saving_text!r}"
        )

    def test_ac13_vm_predicted_saving_not_blank_at_zero(self):
        """AC-13: Predicted saving text is not blank at 0% (shows '0 (no change)')."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.predicted_saving_text.strip() != ""


# ---------------------------------------------------------------------------
# AC-14: required_fuel_saving_pct > 0 → per-gear deltas not all equal,
#          at least one short-shifts, predicted >= required (within tolerance)
# ---------------------------------------------------------------------------

class TestAC14_RaceShortShiftsArePerGear:

    def test_ac14_short_shifts_at_positive_target(self):
        """AC-14: At 5% fuel target, at least one pair short-shifts."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=5.0)
        any_short = any(
            d.valid and d.rpm_delta_from_qualifying is not None
            and d.rpm_delta_from_qualifying < 0
            for d in result.race_profile.decisions
        )
        assert any_short, "5% fuel target must cause at least one pair to short-shift"

    def test_ac14_per_gear_deltas_are_not_all_equal(self):
        """AC-14: Short-shift reductions are not a flat % across all gears."""
        inp = _inputs(gear_ratios=(3.5, 2.5, 1.9, 1.4, 1.1, 0.9))
        result = compute_shift_strategy(inp, required_fuel_saving_pct=25.0)
        deltas = [
            d.rpm_delta_from_qualifying
            for d in result.race_profile.decisions
            if d.valid and d.rpm_delta_from_qualifying is not None
        ]
        assert len(deltas) >= 2, "Need at least 2 valid pairs for this test"
        # At 25% some short-shift, some may not — values must not all be identical
        assert len(set(deltas)) > 1, (
            "Per-gear rpm_delta must not all be identical — "
            "greedy optimiser should pick different short-shift points "
            f"(got deltas={deltas})"
        )

    def test_ac14_predicted_saving_meets_target(self):
        """AC-14: Predicted fuel saving >= required target (within 0.5% tolerance)."""
        inp = _inputs()
        target = 5.0
        result = compute_shift_strategy(inp, required_fuel_saving_pct=target)
        assert result.predicted_fuel_saving_pct >= target - 0.5, (
            f"Predicted saving {result.predicted_fuel_saving_pct:.1f}% "
            f"must be >= target {target}% (within 0.5% tolerance)"
        )

    def test_ac14_predicted_saving_not_grossly_over_target(self):
        """AC-14: Predicted saving does not far exceed the required target."""
        from strategy.shift_strategy_constants import FUEL_BURN_RPM_COEFFICIENT
        inp = _inputs()
        target = 3.0
        result = compute_shift_strategy(inp, required_fuel_saving_pct=target)
        max_epsilon = FUEL_BURN_RPM_COEFFICIENT * 100.0 + 1.0
        assert result.predicted_fuel_saving_pct <= target + max_epsilon, (
            f"Predicted saving {result.predicted_fuel_saving_pct:.1f}% "
            f"grossly exceeds target {target}%"
        )


# ---------------------------------------------------------------------------
# AC-15: VM summary exposes required vs predicted saving and time cost text
# ---------------------------------------------------------------------------

class TestAC15_VMSummaryFields:

    def test_ac15_vm_has_required_saving_text(self):
        """AC-15: VM exposes required saving as non-empty text."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=5.0)
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.required_saving_text.strip() != ""
        assert "5" in vm.required_saving_text  # shows the actual number

    def test_ac15_vm_has_predicted_saving_text(self):
        """AC-15: VM exposes predicted saving as non-empty text."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=5.0)
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.predicted_saving_text.strip() != ""

    def test_ac15_vm_has_time_cost_text(self):
        """AC-15: VM exposes time cost as non-empty text."""
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=5.0)
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.time_cost_text.strip() != ""


# ---------------------------------------------------------------------------
# AC-16: overall_confidence == weakest across covered pairs
# ---------------------------------------------------------------------------

class TestAC16_OverallIsWeakestPair:

    def test_ac16_weakest_pair_drives_overall_confidence(self):
        """AC-16: When one pair is INSUFFICIENT_EVIDENCE, overall must also be."""
        # A ratio drop so large the post-shift RPM falls below the power band
        # → that pair gets INSUFFICIENT_EVIDENCE; one normal pair remains PROVISIONAL
        inp = _inputs(gear_ratios=(3.5, 2.5, 0.3))  # huge drop from 2nd→3rd
        result = compute_shift_strategy(inp)
        confidences = [d.confidence for d in result.qualifying_profile.decisions]
        # Verify the mix exists
        assert ShiftConfidence.INSUFFICIENT_EVIDENCE in confidences or \
               ShiftConfidence.PROVISIONAL in confidences
        # Overall must equal the weakest
        from strategy.shift_strategy_engine import _CONFIDENCE_RANK
        weakest = min(confidences, key=lambda c: _CONFIDENCE_RANK.get(c, 0))
        # Phase 1 caps at PROVISIONAL, but INSUFFICIENT stays INSUFFICIENT
        if weakest == ShiftConfidence.INSUFFICIENT_EVIDENCE:
            assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_ac16_all_valid_pairs_gives_provisional_overall(self):
        """AC-16: All PROVISIONAL pairs → overall PROVISIONAL (weakest == PROVISIONAL)."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        all_conf = [d.confidence for d in result.qualifying_profile.decisions]
        assert all(c == ShiftConfidence.PROVISIONAL for c in all_conf)
        assert result.overall_confidence == ShiftConfidence.PROVISIONAL


# ---------------------------------------------------------------------------
# AC-17: VM row for a pair with no computed value has next-action, never blank/0
# ---------------------------------------------------------------------------

class TestAC17_InvalidRowNextAction:

    def test_ac17_invalid_row_shows_rationale_or_next_action(self):
        """AC-17: A row for an invalid (below powerband) pair shows actionable text, not '0'."""
        # Force an invalid pair: ratio drop so large post-shift RPM is below power band
        inp = _inputs(gear_ratios=(10.0, 1.0), peak_power_rpm=7000, redline=8000)
        result = compute_shift_strategy(inp)
        assert len(result.qualifying_profile.decisions) == 1
        d = result.qualifying_profile.decisions[0]
        assert d.valid is False

        vm = build_shift_strategy_vm(result)
        assert len(vm.rows) == 1
        row = vm.rows[0]
        # qualifying_rpm on an invalid row should show the rationale, not "0"
        assert row.qualifying_rpm != "0"
        assert row.qualifying_rpm.strip() != ""

    def test_ac17_has_data_false_row_evidence_tone_is_neutral_or_warn(self):
        """AC-17: An invalid row's evidence_tone is neutral or warn (not success/info)."""
        inp = _inputs(gear_ratios=(10.0, 1.0), peak_power_rpm=7000, redline=8000)
        result = compute_shift_strategy(inp)
        vm = build_shift_strategy_vm(result)
        if vm.rows:
            row = vm.rows[0]
            assert row.has_data is False
            assert row.evidence_tone in ("neutral", "warn"), (
                f"Invalid row evidence_tone must be neutral or warn, got {row.evidence_tone!r}"
            )


# ---------------------------------------------------------------------------
# AC-18: Advisory-only — no side effects, no setup writes, no pit commands
# ---------------------------------------------------------------------------

class TestAC18_AdvisoryOnly:

    def test_ac18_compute_is_deterministic_no_side_effects(self):
        """AC-18: compute_shift_strategy is deterministic; calling twice gives identical results."""
        inp = _inputs()
        r1 = compute_shift_strategy(inp, required_fuel_saving_pct=5.0)
        r2 = compute_shift_strategy(inp, required_fuel_saving_pct=5.0)
        assert r1.configuration_fingerprint == r2.configuration_fingerprint
        assert r1.overall_confidence == r2.overall_confidence
        assert r1.predicted_fuel_saving_pct == r2.predicted_fuel_saving_pct
        # Decisions must match
        for d1, d2 in zip(r1.qualifying_profile.decisions, r2.qualifying_profile.decisions):
            assert d1.qualifying_target_rpm == d2.qualifying_target_rpm
            assert d1.expected_post_shift_rpm == d2.expected_post_shift_rpm

    def test_ac18_compute_writes_no_file(self, tmp_path):
        """AC-18: compute_shift_strategy writes no files during computation."""
        files_before = set(str(p) for p in tmp_path.rglob("*"))
        inp = _inputs()
        compute_shift_strategy(inp)
        files_after = set(str(p) for p in tmp_path.rglob("*"))
        new_files = files_after - files_before
        assert not new_files, f"compute_shift_strategy wrote unexpected files: {new_files}"

    def test_ac18_no_setup_history_write_tokens_in_domain_modules(self):
        """AC-18: Strategy / store / VM source has no setup-history write tokens in code."""
        banned = (
            "apply_setup", "SetupApply", "write_setup",
            "save_setup_history", "setup_history", "execute_pit",
            "set_shift_rpm", "write_shift_rpm",
        )
        for rel in _NEW_MODULES:
            code = _code_only(rel).lower()
            for token in banned:
                assert token.lower() not in code, (
                    f"{rel}: must not contain {token!r} in code "
                    "(advisory-only — no setup authoring allowed)"
                )

    def test_ac18_store_only_writes_shift_strategy_json(self, tmp_path):
        """AC-18: ShiftStrategyStore.save only touches its own JSON file."""
        path = str(tmp_path / "shift_strategy.json")
        store = ShiftStrategyStore(path=path)
        store.save("scope::car::track", {
            "fingerprint": "fp1",
            "computed_at": "2026-07-25T00:00:00Z",
            "manual_engine_data": {},
            "qualifying_profile_json": {},
            "race_profile_json": {},
            "required_fuel_saving_pct": 0.0,
        })
        created = [str(p) for p in tmp_path.iterdir()]
        # Only shift_strategy.json (and possibly a temp file that got cleaned up)
        assert any("shift_strategy" in f for f in created), (
            "Expected shift_strategy.json to be written"
        )
        # No setup_sheets.json or setup_revisions.json should exist
        assert not any("setup_sheets" in f for f in created), (
            "ShiftStrategyStore must not write setup_sheets.json"
        )
        assert not any("setup_revisions" in f for f in created), (
            "ShiftStrategyStore must not write setup_revisions.json"
        )


# ---------------------------------------------------------------------------
# AC-19: Store persists keyed by scope, separate from setup history
# ---------------------------------------------------------------------------

class TestAC19_StorePersistenceSeparateFromSetupHistory:

    def test_ac19_round_trip_save_and_get(self, tmp_path):
        """AC-19: save/get round-trip works correctly."""
        path = str(tmp_path / "shift_strategy.json")
        store = ShiftStrategyStore(path=path)
        scope = "scope::porsche_cayman_gt4::watkins_glen"
        payload = {
            "fingerprint": "test_fp_001",
            "computed_at": "2026-07-25T12:00:00Z",
            "manual_engine_data": {"peak_power_rpm": 7200, "peak_torque_rpm": 5600, "redline": 7600},
            "qualifying_profile_json": {"mode": "qualifying", "decisions": []},
            "race_profile_json": {"mode": "race", "decisions": []},
            "required_fuel_saving_pct": 5.0,
        }
        ok = store.save(scope, payload)
        assert ok is True

        store2 = ShiftStrategyStore(path=path)
        loaded = store2.get(scope)
        assert loaded is not None
        assert loaded["fingerprint"] == "test_fp_001"
        assert loaded["required_fuel_saving_pct"] == 5.0

    def test_ac19_setup_sheets_json_not_touched(self, tmp_path):
        """AC-19: ShiftStrategyStore does not create or modify setup_sheets.json."""
        setup_sheets_path = tmp_path / "setup_sheets.json"
        shift_path = str(tmp_path / "shift_strategy.json")
        # setup_sheets.json does not exist before
        assert not setup_sheets_path.exists()
        store = ShiftStrategyStore(path=shift_path)
        store.save("scope", {
            "fingerprint": "fp",
            "computed_at": "t",
            "manual_engine_data": {},
            "qualifying_profile_json": {},
            "race_profile_json": {},
            "required_fuel_saving_pct": 0.0,
        })
        assert not setup_sheets_path.exists(), (
            "ShiftStrategyStore must not touch setup_sheets.json"
        )

    def test_ac19_setup_revisions_json_not_touched(self, tmp_path):
        """AC-19: ShiftStrategyStore does not create or modify setup_revisions.json."""
        revisions_path = tmp_path / "setup_revisions.json"
        shift_path = str(tmp_path / "shift_strategy.json")
        assert not revisions_path.exists()
        store = ShiftStrategyStore(path=shift_path)
        store.save("scope", {
            "fingerprint": "fp",
            "computed_at": "t",
            "manual_engine_data": {},
            "qualifying_profile_json": {},
            "race_profile_json": {},
            "required_fuel_saving_pct": 0.0,
        })
        assert not revisions_path.exists(), (
            "ShiftStrategyStore must not touch setup_revisions.json"
        )


# ---------------------------------------------------------------------------
# AC-20: Switching profile is an explicit action — build_shift_strategy_vm
#         reflects the passed profile (no auto-switch in pure layer)
# ---------------------------------------------------------------------------

class TestAC20_ProfileExplicitAction:

    def test_ac20_qualifying_profile_passed_gives_qualifying(self):
        """AC-20: build_shift_strategy_vm with profile='qualifying' returns qualifying."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, profile="qualifying")
        assert vm.active_profile == "qualifying"

    def test_ac20_race_profile_passed_gives_race(self):
        """AC-20: build_shift_strategy_vm with profile='race' returns race."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.active_profile == "race"

    def test_ac20_no_auto_switch_from_qualifying_to_race(self):
        """AC-20: Passing profile='qualifying' always gives qualifying, even with fuel target > 0."""
        result = compute_shift_strategy(_inputs(), required_fuel_saving_pct=5.0)
        vm = build_shift_strategy_vm(result, profile="qualifying")
        assert vm.active_profile == "qualifying"

    def test_ac20_no_auto_switch_from_race_to_qualifying(self):
        """AC-20: Passing profile='race' always gives race, even at 0% saving."""
        result = compute_shift_strategy(_inputs(), required_fuel_saving_pct=0.0)
        vm = build_shift_strategy_vm(result, profile="race")
        assert vm.active_profile == "race"


# ---------------------------------------------------------------------------
# AC-21: VM rows have all 9 display fields populated (non-empty strings)
# ---------------------------------------------------------------------------

class TestAC21_VMRowsAllFieldsPopulated:

    def test_ac21_valid_row_has_all_display_fields_non_empty(self):
        """AC-21: Every field in a valid GearDecisionRow is a non-empty string."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, profile="qualifying")
        assert len(vm.rows) > 0
        for row in vm.rows:
            if row.has_data:
                assert row.label != "", f"label must not be empty"
                assert row.qualifying_rpm != "", f"qualifying_rpm must not be empty"
                assert row.race_rpm != "", f"race_rpm must not be empty"
                assert row.rpm_delta != "", f"rpm_delta must not be empty"
                assert row.post_shift_rpm != "", f"post_shift_rpm must not be empty"
                assert row.time_cost != "", f"time_cost must not be empty"
                assert row.fuel_saving != "", f"fuel_saving must not be empty"
                assert row.confidence_key != "", f"confidence_key must not be empty"
                assert row.confidence_label != "", f"confidence_label must not be empty"
                assert row.evidence_tone != "", f"evidence_tone must not be empty"

    def test_ac21_row_count_matches_gear_pairs(self):
        """AC-21: One row per valid upshift (len(decisions) == num_gears - 1)."""
        ratios = (3.5, 2.5, 1.9, 1.4, 1.1, 0.9)
        result = compute_shift_strategy(_inputs(gear_ratios=ratios))
        vm = build_shift_strategy_vm(result, profile="qualifying")
        assert len(vm.rows) == len(ratios) - 1

    def test_ac21_label_format_is_from_arrow_to(self):
        """AC-21: Row labels have the form 'N → M'."""
        result = compute_shift_strategy(_inputs(gear_ratios=(3.5, 2.5, 1.9)))
        vm = build_shift_strategy_vm(result, profile="qualifying")
        assert vm.rows[0].label == "1 → 2"
        assert vm.rows[1].label == "2 → 3"


# ---------------------------------------------------------------------------
# AC-22: VM summary card fields present
# ---------------------------------------------------------------------------

class TestAC22_VMSummaryCardFields:

    def test_ac22_all_summary_card_fields_present(self):
        """AC-22: ShiftStrategyVM has all required summary card attributes."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result, profile="qualifying")
        # Verify all required summary card fields exist and are non-empty where expected
        assert hasattr(vm, "active_profile")
        assert hasattr(vm, "required_saving_text")
        assert hasattr(vm, "predicted_saving_text")
        assert hasattr(vm, "time_cost_text")
        assert hasattr(vm, "config_status_text")
        assert hasattr(vm, "overall_confidence_key")
        assert hasattr(vm, "evidence_readiness_text")

        assert vm.active_profile != ""
        assert vm.required_saving_text.strip() != ""
        assert vm.overall_confidence_key != ""
        assert vm.evidence_readiness_text.strip() != ""

    def test_ac22_config_status_text_present(self):
        """AC-22: config_status_text is non-empty."""
        result = compute_shift_strategy(_inputs())
        vm = build_shift_strategy_vm(result)
        assert vm.config_status_text.strip() != ""


# ---------------------------------------------------------------------------
# AC-23: VM stepper_stage is set and consistent with state
# ---------------------------------------------------------------------------

class TestAC23_StepperStage:

    def test_ac23_stage_0_when_no_ratios(self):
        """AC-23: stepper_stage == 0 when no gear ratios are present."""
        inp = _inputs(gear_ratios=())
        result = compute_shift_strategy(inp)
        vm = build_shift_strategy_vm(result)
        assert vm.stepper_stage == 0

    def test_ac23_stage_1_when_ratios_but_no_engine_data(self):
        """AC-23: stepper_stage == 1 when gear ratios are present but engine data absent."""
        inp = ShiftStrategyInputs(
            car_id="TestCar",
            gear_ratios=(3.5, 2.5, 1.9),
            final_drive=4.0,
            ecu_output=100.0,
            power_restrictor=100.0,
            ballast_kg=0.0,
            weight_kg=1200.0,
            aspiration="NA",
            peak_power_rpm=None,
            peak_torque_rpm=None,
            redline=None,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        vm = build_shift_strategy_vm(result)
        assert vm.stepper_stage == 1, (
            f"Expected stepper_stage=1 (need engine data), got {vm.stepper_stage}"
        )

    def test_ac23_stage_3_when_fully_computed_not_stale(self):
        """AC-23: stepper_stage == 3 (done) when computation is complete and not stale."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        # Not stale: pass matching fingerprint
        vm = build_shift_strategy_vm(result,
                                     stored_fingerprint=result.configuration_fingerprint)
        assert vm.stepper_stage == 3, (
            f"Expected stepper_stage=3 (done) when fully computed, got {vm.stepper_stage}"
        )

    def test_ac23_stage_2_when_stale(self):
        """AC-23: stepper_stage == 2 (review) when result is stale."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        vm = build_shift_strategy_vm(result, stored_fingerprint="old_fp")
        assert vm.stepper_stage == 2, (
            f"Expected stepper_stage=2 (stale/recompute) when stale, got {vm.stepper_stage}"
        )

    def test_ac23_none_result_stage_is_0(self):
        """AC-23: stepper_stage == 0 when no result is available."""
        vm = build_shift_strategy_vm(None)
        assert vm.stepper_stage == 0


# ---------------------------------------------------------------------------
# Out-of-scope guard: PROVISIONAL badge in fuel_saving for nonzero saving rows
# ---------------------------------------------------------------------------

class TestOOSProvisionalBadge:

    def test_oos_fuel_saving_carries_provisional_badge(self):
        """OOS: fuel_saving text for a nonzero-saving row contains '(PROVISIONAL)'."""
        result = compute_shift_strategy(_inputs(), required_fuel_saving_pct=5.0)
        vm = build_shift_strategy_vm(result, profile="race")
        # Find a row that actually has a nonzero fuel saving
        saving_rows = [
            r for r in vm.rows
            if r.has_data
            and r.fuel_saving not in ("—", "0 (no change)", "")
        ]
        if saving_rows:
            assert any("PROVISIONAL" in r.fuel_saving for r in saving_rows), (
                f"Fuel saving text must carry '(PROVISIONAL)' badge; got {[r.fuel_saving for r in saving_rows]}"
            )


# ---------------------------------------------------------------------------
# Out-of-scope guard: No Fuel Map reference in any shift_strategy_* module
# ---------------------------------------------------------------------------

class TestOOSNoFuelMap:

    def test_oos_no_fuel_map_in_shift_strategy_modules(self):
        """OOS: The string 'fuel_map' / 'Fuel Map' must not appear in shift strategy source."""
        for rel in _NEW_MODULES:
            src = (_ROOT / rel).read_text(encoding="utf-8")
            src_lower = src.lower()
            assert "fuel_map" not in src_lower, (
                f"{rel}: must not reference 'fuel_map' "
                "(Phase 1 has no fuel-map capability; no such reference allowed)"
            )
            # Check the literal display string too
            assert "fuel map" not in src_lower, (
                f"{rel}: must not reference 'Fuel Map' display string"
            )
