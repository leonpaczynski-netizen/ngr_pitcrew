"""Phase-2 engine integration: telemetry-calibrated engine data lifts the confidence
ceiling, while the manual path stays byte-identical (golden vectors elsewhere prove it).
"""

import dataclasses

from strategy.shift_strategy_engine import compute_shift_strategy, ShiftConfidence
from strategy.shift_strategy_inputs import (
    ShiftStrategyInputs, resolve_shift_inputs, compute_shift_fingerprint,
)


def _inputs(source="manual", calib="", **kw):
    base = dict(
        car_id="TestCar", gear_ratios=(3.5, 2.5, 1.9, 1.4, 1.1, 0.9),
        final_drive=4.0, ecu_output=100.0, power_restrictor=100.0, ballast_kg=0.0,
        weight_kg=1200.0, aspiration="NA", peak_power_rpm=7000, peak_torque_rpm=5500,
        redline=8000, active_setup_revision=1,
    )
    base.update(kw)
    return ShiftStrategyInputs(engine_data_source=source, calibration_confidence=calib, **base)


class TestConfidenceLift:
    def test_manual_data_is_still_capped_at_provisional(self):
        r = compute_shift_strategy(_inputs())
        assert r.overall_confidence == ShiftConfidence.PROVISIONAL

    def test_telemetry_high_lifts_overall_to_high(self):
        r = compute_shift_strategy(_inputs(source="telemetry", calib="high"))
        assert r.overall_confidence == ShiftConfidence.HIGH
        # every valid decision is relabelled as telemetry-calibrated
        srcs = {d.evidence_source for d in r.qualifying_profile.decisions if d.valid}
        assert srcs == {"telemetry_calibrated"}

    def test_telemetry_medium_lifts_to_medium_not_high(self):
        r = compute_shift_strategy(_inputs(source="telemetry", calib="medium"))
        assert r.overall_confidence == ShiftConfidence.MEDIUM

    def test_unrecognised_calibration_confidence_stays_provisional(self):
        r = compute_shift_strategy(_inputs(source="telemetry", calib="garbage"))
        assert r.overall_confidence == ShiftConfidence.PROVISIONAL

    def test_rpm_numbers_are_identical_only_confidence_changes(self):
        # Same anchors → identical shift RPMs; only provenance/confidence differ.
        man = compute_shift_strategy(_inputs())
        tel = compute_shift_strategy(_inputs(source="telemetry", calib="high"))
        man_rpms = [d.qualifying_target_rpm for d in man.qualifying_profile.decisions]
        tel_rpms = [d.qualifying_target_rpm for d in tel.qualifying_profile.decisions]
        assert man_rpms == tel_rpms
        assert man.overall_confidence != tel.overall_confidence

    def test_a_below_powerband_pair_stays_insufficient_even_with_telemetry(self):
        # Last pair drops far below the powerband → INSUFFICIENT regardless of source.
        r = compute_shift_strategy(
            _inputs(source="telemetry", calib="high", gear_ratios=(3.5, 2.5, 0.3)))
        assert r.overall_confidence == ShiftConfidence.INSUFFICIENT_EVIDENCE

    def test_evidence_summary_names_the_source(self):
        assert "telemetry-calibrated" in compute_shift_strategy(
            _inputs(source="telemetry", calib="high")).evidence_summary
        assert "manually entered" in compute_shift_strategy(_inputs()).evidence_summary


class TestFingerprint:
    def test_telemetry_fingerprint_differs_from_manual(self):
        # Same config + anchors, different provenance → distinct, cache-invalidating fp.
        assert (compute_shift_fingerprint(_inputs())
                != compute_shift_fingerprint(_inputs(source="telemetry", calib="high")))

    def test_recalibration_to_new_anchors_changes_the_fingerprint(self):
        a = compute_shift_fingerprint(_inputs(source="telemetry", calib="high"))
        b = compute_shift_fingerprint(
            _inputs(source="telemetry", calib="high", peak_power_rpm=7200))
        assert a != b


class TestResolveReadsSource:
    def test_engine_data_dict_source_flows_through_resolve(self):
        class _Sheet:
            gear_ratios = (3.5, 2.5, 1.9, 1.4)
            values = {"car": "C"}
            def get(self, k, d=None):
                return {"final_drive": 4.0}.get(k, d)
        engine_data = {"peak_power_rpm": 7000, "peak_torque_rpm": 5500, "redline": 8000,
                       "source": "telemetry", "calibration_confidence": "high"}
        inp = resolve_shift_inputs(_Sheet(), {"weight_kg": 1200, "aspiration": "NA"},
                                   1, engine_data)
        assert inp.engine_data_source == "telemetry"
        assert inp.calibration_confidence == "high"

    def test_absent_source_defaults_to_manual(self):
        class _Sheet:
            gear_ratios = (3.5, 2.5)
            values = {"car": "C"}
            def get(self, k, d=None):
                return {"final_drive": 4.0}.get(k, d)
        inp = resolve_shift_inputs(_Sheet(), {}, 1,
                                   {"peak_power_rpm": 7000, "peak_torque_rpm": 5500,
                                    "redline": 8000})
        assert inp.engine_data_source == "manual"
