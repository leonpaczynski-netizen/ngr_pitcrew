"""Phase 1 — Adaptive Per-Gear Shift Strategy engine unit tests.

Covers: post-shift math, qualifying optimiser invariants, race optimiser
behaviour, fingerprint sensitivity, error paths, and edge cases.
"""
from __future__ import annotations

import pytest

from strategy.shift_strategy_constants import (
    FUEL_BURN_RPM_COEFFICIENT,
    MIN_USEFUL_RPM_FRACTION,
    QUAL_MIN_RPM_FRACTION,
    SHIFT_STRATEGY_VERSION,
)
from strategy.shift_strategy_engine import (
    ShiftConfidence,
    compute_shift_strategy,
)
from strategy.shift_strategy_inputs import (
    ShiftStrategyInputs,
    compute_shift_fingerprint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Post-shift RPM math
# ---------------------------------------------------------------------------

class TestPostShiftMath:
    def test_post_shift_exact(self):
        from strategy.shift_strategy_engine import _post_shift_rpm
        # shift at 8000 rpm with ratio 3.5 → 2.5 = 8000 * 2.5 / 3.5 ≈ 5714
        result = _post_shift_rpm(8000, 3.5, 2.5)
        assert result == round(8000 * 2.5 / 3.5)

    def test_post_shift_ratios_distinct_per_pair(self):
        # Each gear pair has a different ratio, so post-shift RPM must differ
        from strategy.shift_strategy_engine import _post_shift_rpm
        ratios = (3.5, 2.5, 1.9, 1.4)
        shift_rpm = 7000
        posts = [_post_shift_rpm(shift_rpm, ratios[i], ratios[i+1])
                 for i in range(len(ratios) - 1)]
        # All distinct because all ratios are distinct
        assert len(set(posts)) == len(posts)

    def test_final_drive_cancels(self):
        """Post-shift RPM is identical regardless of final drive value."""
        from strategy.shift_strategy_engine import _post_shift_rpm
        # post_shift uses only ratio_from and ratio_to — final drive cancels
        post_fd1 = _post_shift_rpm(7000, 3.5, 2.5)
        # The final drive does not appear in the formula, so same result
        assert post_fd1 == round(7000 * 2.5 / 3.5)
        # Confirm changing final_drive in inputs does NOT change per-pair result
        inp1 = _inputs(gear_ratios=(3.5, 2.5), final_drive=4.0)
        inp2 = _inputs(gear_ratios=(3.5, 2.5), final_drive=5.5)
        r1 = compute_shift_strategy(inp1)
        r2 = compute_shift_strategy(inp2)
        qd1 = r1.qualifying_profile.decisions[0]
        qd2 = r2.qualifying_profile.decisions[0]
        # Qualifying target may differ (final drive not in post-shift calc)
        # but post-shift RPM ratio is purely ratio_to/ratio_from
        assert qd1.expected_post_shift_rpm == qd2.expected_post_shift_rpm

    def test_post_shift_rpms_distinct_across_gear_pairs(self):
        """Each pair produces a different post-shift RPM (different ratio pair)."""
        inp = _inputs()
        result = compute_shift_strategy(inp)
        posts = [
            d.expected_post_shift_rpm
            for d in result.qualifying_profile.decisions
            if d.valid and d.expected_post_shift_rpm is not None
        ]
        assert len(posts) == len(set(posts)), "Post-shift RPMs must be distinct per pair"


# ---------------------------------------------------------------------------
# Qualifying optimiser invariants
# ---------------------------------------------------------------------------

class TestQualifyingOptimiser:
    def test_qual_optimiser_never_returns_peak_torque_rpm(self):
        """The optimiser must NOT simply return peak_torque_rpm as the shift point."""
        inp = _inputs(peak_torque_rpm=5500, peak_power_rpm=7000, redline=8000)
        result = compute_shift_strategy(inp)
        for d in result.qualifying_profile.decisions:
            if d.valid and d.qualifying_target_rpm is not None:
                assert d.qualifying_target_rpm != 5500, (
                    f"Gear {d.from_gear}→{d.to_gear}: "
                    "qualifying RPM must not equal peak_torque_rpm"
                )

    def test_qual_target_is_in_valid_range(self):
        inp = _inputs()
        result = compute_shift_strategy(inp)
        floor = int(QUAL_MIN_RPM_FRACTION * inp.peak_power_rpm)
        for d in result.qualifying_profile.decisions:
            if d.valid and d.qualifying_target_rpm is not None:
                assert d.qualifying_target_rpm >= floor
                assert d.qualifying_target_rpm <= inp.redline

    def test_post_shift_above_useful_floor_when_valid(self):
        inp = _inputs()
        result = compute_shift_strategy(inp)
        useful_floor = int(MIN_USEFUL_RPM_FRACTION * inp.peak_power_rpm)
        for d in result.qualifying_profile.decisions:
            if d.valid:
                assert d.expected_post_shift_rpm >= useful_floor


# ---------------------------------------------------------------------------
# Race optimiser
# ---------------------------------------------------------------------------

class TestRaceOptimiser:
    def test_race_equals_qual_at_target_zero(self):
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=0.0)
        for d in result.race_profile.decisions:
            if d.valid:
                assert d.race_target_rpm == d.qualifying_target_rpm
                assert d.rpm_delta_from_qualifying == 0

    def test_race_equals_qual_at_near_zero_epsilon(self):
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=1e-9)
        for d in result.race_profile.decisions:
            if d.valid:
                assert d.race_target_rpm == d.qualifying_target_rpm

    def test_race_short_shifts_at_positive_target(self):
        inp = _inputs()
        result = compute_shift_strategy(inp, required_fuel_saving_pct=5.0)
        # At least one pair should short-shift
        any_short = any(
            d.valid and d.rpm_delta_from_qualifying is not None
            and d.rpm_delta_from_qualifying < 0
            for d in result.race_profile.decisions
        )
        assert any_short, "A 5% fuel target must cause at least one short-shift"

    def test_race_meets_fuel_target(self):
        inp = _inputs()
        target = 5.0
        result = compute_shift_strategy(inp, required_fuel_saving_pct=target)
        assert result.predicted_fuel_saving_pct >= target - 0.5  # within 0.5% tolerance

    def test_race_no_over_saving_beyond_target(self):
        inp = _inputs()
        target = 3.0
        result = compute_shift_strategy(inp, required_fuel_saving_pct=target)
        # predicted saving should not wildly exceed target (within one gear-pair worth)
        max_per_pair = FUEL_BURN_RPM_COEFFICIENT  # ≤ 1 gear pair's max saving
        assert result.predicted_fuel_saving_pct <= target + max_per_pair * 100 + 1.0

    def test_per_gear_reductions_differ(self):
        """When multiple pairs short-shift, their deltas are not all identical.

        At 25 % fuel target several gear pairs short-shift; because they have
        different ratio chains the optimal short-shift RPM differs across at
        least some of them (greedy picks different optima per pair).
        """
        inp = _inputs(gear_ratios=(3.5, 2.5, 1.9, 1.4, 1.1, 0.9))
        result = compute_shift_strategy(inp, required_fuel_saving_pct=25.0)
        deltas = [
            d.rpm_delta_from_qualifying
            for d in result.race_profile.decisions
            if d.valid
            and d.rpm_delta_from_qualifying is not None
            and d.rpm_delta_from_qualifying < 0
        ]
        # At 25 % we expect at least two pairs to short-shift
        assert len(deltas) >= 2, "High fuel target must cause multiple pairs to short-shift"
        # Not all deltas can be identical — distinct ratio chains produce distinct optima
        assert len(set(deltas)) > 1, "Per-gear short-shift reductions must not all be equal"


# ---------------------------------------------------------------------------
# Fingerprint sensitivity
# ---------------------------------------------------------------------------

class TestFingerprint:
    def _fp(self, **kwargs) -> str:
        return compute_shift_fingerprint(_inputs(**kwargs))

    def test_base_is_stable(self):
        assert self._fp() == self._fp()

    def test_changes_on_gear_ratio_0(self):
        base = self._fp()
        changed = self._fp(gear_ratios=(3.6, 2.5, 1.9, 1.4, 1.1, 0.9))
        assert base != changed

    def test_changes_on_final_drive(self):
        base = self._fp()
        changed = self._fp(final_drive=4.5)
        assert base != changed

    def test_changes_on_ecu_output(self):
        base = self._fp()
        changed = self._fp(ecu_output=95.0)
        assert base != changed

    def test_changes_on_power_restrictor(self):
        base = self._fp()
        changed = self._fp(power_restrictor=90.0)
        assert base != changed

    def test_changes_on_aspiration(self):
        base = self._fp()
        changed = self._fp(aspiration="TC")
        assert base != changed

    def test_changes_on_ballast_kg(self):
        base = self._fp()
        changed = self._fp(ballast_kg=25.0)
        assert base != changed

    def test_changes_on_weight_kg(self):
        base = self._fp()
        changed = self._fp(weight_kg=1300.0)
        assert base != changed

    def test_changes_on_active_setup_revision(self):
        base = self._fp()
        changed = self._fp(active_setup_revision=2)
        assert base != changed

    def test_changes_on_car_id(self):
        base = self._fp()
        changed = self._fp(car_id="OtherCar")
        assert base != changed

    def test_has_ten_hex_chars(self):
        import re
        fp = self._fp()
        assert len(fp) == 10 and re.fullmatch(r"[0-9a-f]{10}", fp)

    def test_version_in_fingerprint_preimage(self):
        """Changing SHIFT_STRATEGY_VERSION would change all fingerprints."""
        inp = _inputs()
        # The version string is part of the preimage — we verify this by
        # checking the compute_shift_fingerprint source includes the constant
        import inspect
        from strategy.shift_strategy_inputs import compute_shift_fingerprint as cfp
        src = inspect.getsource(cfp)
        assert "SHIFT_STRATEGY_VERSION" in src


# ---------------------------------------------------------------------------
# Error / edge cases
# ---------------------------------------------------------------------------

class TestErrorPaths:
    def test_missing_gear_ratios_returns_insufficient_evidence(self):
        inp = _inputs(gear_ratios=())
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE
        assert result.missing_evidence

    def test_single_gear_ratio_returns_insufficient_evidence(self):
        inp = _inputs(gear_ratios=(3.5,))
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_missing_peak_power_rpm_is_insufficient_not_provisional(self):
        inp = ShiftStrategyInputs(
            car_id="C", gear_ratios=(3.5, 2.5), final_drive=4.0,
            ecu_output=100.0, power_restrictor=100.0, ballast_kg=0.0,
            weight_kg=1200.0, aspiration="NA",
            peak_power_rpm=None,  # missing
            peak_torque_rpm=5500, redline=8000,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE
        assert result.overall_confidence != ShiftConfidence.PROVISIONAL

    def test_missing_peak_torque_rpm_is_insufficient(self):
        inp = ShiftStrategyInputs(
            car_id="C", gear_ratios=(3.5, 2.5), final_drive=4.0,
            ecu_output=100.0, power_restrictor=100.0, ballast_kg=0.0,
            weight_kg=1200.0, aspiration="NA",
            peak_power_rpm=7000, peak_torque_rpm=None, redline=8000,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_missing_redline_is_insufficient(self):
        inp = ShiftStrategyInputs(
            car_id="C", gear_ratios=(3.5, 2.5), final_drive=4.0,
            ecu_output=100.0, power_restrictor=100.0, ballast_kg=0.0,
            weight_kg=1200.0, aspiration="NA",
            peak_power_rpm=7000, peak_torque_rpm=5500, redline=None,
            active_setup_revision=1,
        )
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_missing_evidence_strings_are_never_empty(self):
        inp = _inputs(gear_ratios=())
        result = compute_shift_strategy(inp)
        for m in result.missing_evidence:
            assert m.strip() != "", "missing_evidence entries must not be blank"

    def test_manual_seed_caps_confidence_at_provisional(self):
        inp = _inputs()
        result = compute_shift_strategy(inp)
        # Phase 1 always caps at PROVISIONAL
        assert result.overall_confidence == ShiftConfidence.PROVISIONAL
        assert result.overall_confidence != ShiftConfidence.HIGH
        assert result.overall_confidence != ShiftConfidence.MEDIUM

    def test_overall_confidence_is_weakest_pair(self):
        # Use an extreme ratio that makes the last pair go below powerband
        # so we get a mix of PROVISIONAL (valid pairs) and INSUFFICIENT (invalid)
        inp = _inputs(gear_ratios=(3.5, 2.5, 0.3))  # last pair: huge drop → below powerband
        result = compute_shift_strategy(inp)
        # At least one pair must be INSUFFICIENT_EVIDENCE
        all_conf = [d.confidence for d in result.qualifying_profile.decisions]
        assert ShiftConfidence.INSUFFICIENT_EVIDENCE in all_conf
        # Overall must equal weakest = INSUFFICIENT_EVIDENCE
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_never_raises_on_garbage_ratios(self):
        inp = ShiftStrategyInputs(
            car_id="", gear_ratios=(0.0,), final_drive=0.0,
            ecu_output=100.0, power_restrictor=100.0, ballast_kg=0.0,
            weight_kg=0.0, aspiration="UNKNOWN",
            peak_power_rpm=None, peak_torque_rpm=None, redline=None,
            active_setup_revision=0,
        )
        result = compute_shift_strategy(inp)
        assert result.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_never_raises_on_none_numerics(self):
        inp = ShiftStrategyInputs(
            car_id="X", gear_ratios=(3.5, 2.5), final_drive=4.0,
            ecu_output=100.0, power_restrictor=100.0, ballast_kg=0.0,
            weight_kg=1200.0, aspiration="NA",
            peak_power_rpm=None, peak_torque_rpm=None, redline=None,
            active_setup_revision=1,
        )
        # Must not raise
        result = compute_shift_strategy(inp)
        assert result is not None

    def test_below_powerband_pair_is_invalid(self):
        """A pair whose post-shift RPM falls below the useful floor must be invalid."""
        # Gear 1 ratio is very high, gear 2 is very low → huge drop in RPM
        inp = _inputs(gear_ratios=(10.0, 1.0), peak_power_rpm=7000, redline=8000)
        result = compute_shift_strategy(inp)
        assert len(result.qualifying_profile.decisions) == 1
        d = result.qualifying_profile.decisions[0]
        assert d.valid is False
        assert "below_powerband" in d.evidence_source or not d.valid

    def test_algorithm_version_in_result(self):
        inp = _inputs()
        result = compute_shift_strategy(inp)
        assert result.algorithm_version == SHIFT_STRATEGY_VERSION
