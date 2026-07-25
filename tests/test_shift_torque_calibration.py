"""Tests for Phase-2 telemetry torque calibration (strategy/shift_torque_calibration.py).

A synthetic wide-open-throttle pull with a KNOWN torque shape is generated, and the
calibration is asserted to recover the peak-torque / peak-power / redline anchors and
report an honest confidence. Everything is pure — no Qt/DB.
"""

from strategy.shift_torque_calibration import (
    calibrate_torque_from_laps, TorqueCalibration,
    WOT_THROTTLE_MIN, MIN_TOTAL_SAMPLES,
)


# --- synthetic engine: torque shape peaks at 4000, power peaks ~5500, redline 7500 ---
def _torque_frac(rpm: float) -> float:
    if rpm <= 2000:
        return 0.40
    if rpm <= 4000:
        return 0.40 + 0.60 * (rpm - 2000) / 2000      # rise to 1.0 at 4000
    if rpm <= 6000:
        return 1.00 - 0.30 * (rpm - 4000) / 2000      # gentle fall
    if rpm <= 7500:
        return 0.70 - 0.30 * (rpm - 6000) / 1500      # steeper fall
    return 0.40


_PEAK_A = 4.0   # m/s^2 at peak torque


def _frame(t_ms, speed_ms, gear, rpm, throttle=1.0, brake=0.0, limiter=False):
    return {"elapsed_ms": t_ms, "speed_kmh": speed_ms * 3.6, "throttle": throttle,
            "brake": brake, "gear": gear, "rpm": rpm, "rev_limiter": limiter}


def _wot_pull(gear=3, rpm_per_ms=200.0, rpm_start=2000, redline=7500, dt_ms=100,
              throttle=1.0, brake=0.0, add_limiter=True):
    """One clean full-throttle pull in a fixed gear, sampled at 1000/dt_ms Hz."""
    frames = []
    t = 0
    speed_ms = rpm_start / rpm_per_ms
    rpm = speed_ms * rpm_per_ms
    while rpm < redline:
        frames.append(_frame(t, speed_ms, gear, rpm, throttle=throttle, brake=brake))
        a = _PEAK_A * _torque_frac(rpm)
        speed_ms += a * dt_ms / 1000.0
        rpm = speed_ms * rpm_per_ms
        t += dt_ms
    if add_limiter:
        for _ in range(4):
            frames.append(_frame(t, redline / rpm_per_ms, gear, redline, limiter=True))
            t += dt_ms
    return frames


def _lap(frames):
    return {"frames": frames}


class TestRecoversAnchors:
    def test_clean_pull_recovers_peak_torque_power_and_redline(self):
        cal = calibrate_torque_from_laps([_lap(_wot_pull())])
        assert isinstance(cal, TorqueCalibration)
        assert cal.ok is True
        # Peak torque near 4000, peak power in the mid-power band, redline at the limiter.
        assert 3500 <= cal.peak_torque_rpm <= 4500
        assert 5000 <= cal.peak_power_rpm <= 6500
        assert cal.peak_torque_rpm < cal.peak_power_rpm < cal.redline
        assert cal.redline == 7500                      # min limiter rpm

    def test_a_full_clean_pull_reports_high_confidence(self):
        cal = calibrate_torque_from_laps([_lap(_wot_pull())])
        assert cal.confidence == "high"
        assert cal.sample_count >= MIN_TOTAL_SAMPLES
        assert cal.gear_used == 3

    def test_engine_data_dict_carries_telemetry_provenance(self):
        cal = calibrate_torque_from_laps([_lap(_wot_pull())])
        ed = cal.to_engine_data()
        assert ed["source"] == "telemetry"
        assert ed["calibration_confidence"] == "high"
        assert ed["peak_power_rpm"] == cal.peak_power_rpm
        assert ed["redline"] == cal.redline


class TestGearSelection:
    def test_prefers_the_lowest_gear_at_or_above_second(self):
        # A 2nd-gear pull and a 4th-gear pull — calibration should use 2nd (least drag).
        laps = [_lap(_wot_pull(gear=2, rpm_per_ms=300.0)
                     + _wot_pull(gear=4, rpm_per_ms=150.0))]
        cal = calibrate_torque_from_laps(laps)
        assert cal.gear_used == 2

    def test_skips_first_gear_when_a_higher_gear_qualifies(self):
        laps = [_lap(_wot_pull(gear=1, rpm_per_ms=400.0)
                     + _wot_pull(gear=3, rpm_per_ms=200.0))]
        cal = calibrate_torque_from_laps(laps)
        assert cal.gear_used == 3


class TestEvidenceHonesty:
    def test_no_laps_is_insufficient(self):
        cal = calibrate_torque_from_laps([])
        assert cal.ok is False
        assert cal.confidence == "insufficient"
        assert cal.peak_power_rpm is None

    def test_part_throttle_only_is_insufficient(self):
        # Never at wide-open throttle → no calibration evidence.
        frames = _wot_pull(throttle=0.5)
        cal = calibrate_torque_from_laps([_lap(frames)])
        assert cal.confidence == "insufficient"

    def test_braking_frames_are_rejected(self):
        # Full brake throughout → no valid acceleration samples.
        frames = _wot_pull(brake=1.0)
        cal = calibrate_torque_from_laps([_lap(frames)])
        assert cal.confidence == "insufficient"

    def test_a_short_pull_is_not_high_confidence(self):
        # Only a narrow RPM slice covered → at best medium, never high.
        short = _wot_pull(rpm_start=3500, redline=4300, add_limiter=False)
        cal = calibrate_torque_from_laps([_lap(short)])
        assert cal.confidence in ("insufficient", "medium")
        assert cal.confidence != "high"

    def test_never_raises_on_garbage(self):
        for bad in (None, [None], [{"frames": None}], [{"frames": [{"rpm": "x"}]}],
                    [{"nope": 1}], "garbage"):
            cal = calibrate_torque_from_laps(bad)
            assert isinstance(cal, TorqueCalibration)
            assert cal.confidence == "insufficient"


class TestFrameShapes:
    def test_accepts_object_frames_not_just_dicts(self):
        class _F:
            def __init__(self, d):
                self.__dict__.update(d)
        frames = [_F(f) for f in _wot_pull()]
        cal = calibrate_torque_from_laps([{"frames": frames}])
        assert cal.ok is True

    def test_accepts_a_bare_list_of_frames_as_a_lap(self):
        cal = calibrate_torque_from_laps([_wot_pull()])
        assert cal.ok is True
