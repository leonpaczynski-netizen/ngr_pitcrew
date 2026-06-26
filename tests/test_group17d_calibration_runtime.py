"""Tests for Group 17D — Live Telemetry Calibration Session Wiring.

Covers:
  - data.track_calibration_runtime adapter helpers
  - TrackCalibrationCaptureController state machine and lifecycle
  - Status summary completeness
  - File export integration via save_reference_path
  - Regression: all Group 17A / 17B / 17C symbols still importable

No PyQt6 dependency — fully headless.
"""
import math
import tempfile
from pathlib import Path

import pytest

from data.track_calibration_runtime import (
    CalibrationCaptureState,
    TrackCalibrationCaptureController,
    can_capture_calibration_sample,
    infer_lap_number,
    packet_to_calibration_sample,
)
from data.track_calibration import (
    MIN_CALIBRATION_SAMPLES,
    MIN_USABLE_LAPS_FOR_PATH,
    OFF_TRACK_ROAD_PLANE_Y_THRESHOLD,
    PRIMARY_CALIBRATION_CAR_ID,
)


# ---------------------------------------------------------------------------
# Mock packet factory
# ---------------------------------------------------------------------------

class _MockPacket:
    """Duck-typed GT7Packet for testing.  All fields match GT7Packet attribute names."""

    def __init__(
        self,
        *,
        car_on_track: bool = True,
        paused: bool = False,
        loading: bool = False,
        laps_completed: int = 0,
        pos_x: float = 1.0,
        pos_y: float = 1.0,
        pos_z: float = 0.0,
        speed_kmh: float = 150.0,
        current_gear: int = 4,
        engine_rpm: float = 7500.0,
        throttle: float = 0.8,
        brake: float = 0.0,
        road_distance: float = 0.0,
        angvel_z: float = 0.05,
        road_plane_y: float = 1.0,
        time_of_day_ms: int = 0,
    ) -> None:
        self.car_on_track   = car_on_track
        self.paused         = paused
        self.loading        = loading
        self.laps_completed = laps_completed
        self.pos_x          = pos_x
        self.pos_y          = pos_y
        self.pos_z          = pos_z
        self.speed_kmh      = speed_kmh
        self.current_gear   = current_gear
        self.engine_rpm     = engine_rpm
        self.throttle       = throttle
        self.brake          = brake
        self.road_distance  = road_distance
        self.angvel_z       = angvel_z
        self.road_plane_y   = road_plane_y
        self.time_of_day_ms = time_of_day_ms


def _mk(laps_completed: int = 0, x: float = 1.0, t_ms: int = 0, **kwargs) -> _MockPacket:
    return _MockPacket(laps_completed=laps_completed, pos_x=x, time_of_day_ms=t_ms, **kwargs)


def _make_two_good_laps(ctrl: TrackCalibrationCaptureController) -> None:
    """Feed MIN_CALIBRATION_SAMPLES + 10 samples per lap (2 laps) into the controller."""
    n = MIN_CALIBRATION_SAMPLES + 10

    # Lap 1 (laps_completed=0 → lap number 1)
    for i in range(n):
        ctrl.add_sample_from_packet(
            _MockPacket(laps_completed=0, pos_x=float(i) + 1.0, pos_y=1.0, time_of_day_ms=i * 100)
        )

    # Lap 2 (laps_completed=1 → lap number 2); first sample triggers lap boundary
    for i in range(n):
        ctrl.add_sample_from_packet(
            _MockPacket(
                laps_completed=1,
                pos_x=float(i) + 1.0,
                pos_y=1.0,
                time_of_day_ms=(n * 100) + i * 100,
            )
        )


# ---------------------------------------------------------------------------
# TestCanCaptureSample
# ---------------------------------------------------------------------------

class TestCanCaptureSample:

    def test_valid_packet_returns_true(self):
        assert can_capture_calibration_sample(_mk()) is True

    def test_not_on_track_returns_false(self):
        assert can_capture_calibration_sample(_mk(car_on_track=False)) is False

    def test_paused_returns_false(self):
        assert can_capture_calibration_sample(_mk(paused=True)) is False

    def test_loading_returns_false(self):
        assert can_capture_calibration_sample(_mk(loading=True)) is False

    def test_paused_overrides_on_track(self):
        assert can_capture_calibration_sample(_mk(car_on_track=True, paused=True)) is False

    def test_missing_attribute_returns_false(self):
        class _Empty:
            pass
        assert can_capture_calibration_sample(_Empty()) is False

    def test_exception_in_attribute_returns_false(self):
        class _Bad:
            @property
            def car_on_track(self):
                raise RuntimeError("boom")
        assert can_capture_calibration_sample(_Bad()) is False


# ---------------------------------------------------------------------------
# TestInferLapNumber
# ---------------------------------------------------------------------------

class TestInferLapNumber:

    def test_zero_completed_gives_lap_one(self):
        assert infer_lap_number(_mk(laps_completed=0)) == 1

    def test_one_completed_gives_lap_two(self):
        assert infer_lap_number(_mk(laps_completed=1)) == 2

    def test_five_completed_gives_lap_six(self):
        assert infer_lap_number(_mk(laps_completed=5)) == 6

    def test_negative_one_returns_fallback(self):
        assert infer_lap_number(_mk(laps_completed=-1), fallback=3) == 3

    def test_negative_one_without_fallback_returns_none(self):
        assert infer_lap_number(_mk(laps_completed=-1)) is None

    def test_missing_attribute_returns_fallback(self):
        class _NpPkt:
            pass
        assert infer_lap_number(_NpPkt(), fallback=7) == 7

    def test_exception_returns_fallback(self):
        class _Bad:
            @property
            def laps_completed(self):
                raise RuntimeError("boom")
        assert infer_lap_number(_Bad(), fallback=2) == 2


# ---------------------------------------------------------------------------
# TestPacketToCalibrationSample
# ---------------------------------------------------------------------------

class TestPacketToCalibrationSample:

    def test_maps_basic_fields(self):
        pkt = _mk(laps_completed=0, x=10.0)
        pkt.pos_x = 10.0; pkt.pos_y = 5.0; pkt.pos_z = 3.0
        pkt.speed_kmh = 120.0; pkt.engine_rpm = 6000.0
        pkt.throttle = 0.7; pkt.brake = 0.1
        pkt.current_gear = 3; pkt.road_distance = 42.0
        pkt.angvel_z = 0.3; pkt.road_plane_y = 1.2
        pkt.time_of_day_ms = 99000

        s = packet_to_calibration_sample(pkt, lap_number=1)
        assert s is not None
        assert s.x == pytest.approx(10.0)
        assert s.y == pytest.approx(5.0)
        assert s.z == pytest.approx(3.0)
        assert s.speed_kph == pytest.approx(120.0)
        assert s.rpm == pytest.approx(6000.0)
        assert s.throttle == pytest.approx(0.7)
        assert s.brake == pytest.approx(0.1)
        assert s.gear == 3
        assert s.road_distance == pytest.approx(42.0)
        assert s.yaw_rate == pytest.approx(0.3)
        assert s.road_plane_y == pytest.approx(1.2)
        assert s.timestamp_ms == 99000
        assert s.lap_number == 1

    def test_steering_is_always_none(self):
        s = packet_to_calibration_sample(_mk(), lap_number=1)
        assert s is not None
        assert s.steering is None

    def test_is_in_pit_lane_is_always_none(self):
        s = packet_to_calibration_sample(_mk(), lap_number=1)
        assert s is not None
        assert s.is_in_pit_lane is None

    def test_off_track_when_low_road_plane_and_high_speed(self):
        pkt = _mk(road_plane_y=0.1, speed_kmh=80.0)
        s = packet_to_calibration_sample(pkt, lap_number=1)
        assert s is not None
        assert s.is_off_track is True

    def test_not_off_track_when_road_plane_high(self):
        pkt = _mk(road_plane_y=1.5, speed_kmh=200.0)
        s = packet_to_calibration_sample(pkt, lap_number=1)
        assert s is not None
        assert s.is_off_track is False

    def test_not_off_track_when_speed_below_20(self):
        pkt = _mk(road_plane_y=0.1, speed_kmh=10.0)
        s = packet_to_calibration_sample(pkt, lap_number=1)
        assert s is not None
        assert s.is_off_track is False

    def test_off_track_threshold_at_boundary(self):
        # road_plane_y exactly at threshold should NOT be off-track (< not <=)
        pkt = _mk(road_plane_y=OFF_TRACK_ROAD_PLANE_Y_THRESHOLD, speed_kmh=100.0)
        s = packet_to_calibration_sample(pkt, lap_number=1)
        assert s is not None
        assert s.is_off_track is False

    def test_returns_none_for_paused_packet(self):
        assert packet_to_calibration_sample(_mk(paused=True), lap_number=1) is None

    def test_returns_none_for_off_car_on_track(self):
        assert packet_to_calibration_sample(_mk(car_on_track=False), lap_number=1) is None

    def test_returns_none_for_malformed_packet(self):
        class _Bad:
            @property
            def car_on_track(self):
                raise TypeError("cannot convert")
        assert packet_to_calibration_sample(_Bad(), lap_number=1) is None


# ---------------------------------------------------------------------------
# TestCalibrationCaptureState
# ---------------------------------------------------------------------------

class TestCalibrationCaptureState:

    def test_values(self):
        assert CalibrationCaptureState.INACTIVE  == "inactive"
        assert CalibrationCaptureState.RECORDING == "recording"
        assert CalibrationCaptureState.STOPPED   == "stopped"
        assert CalibrationCaptureState.BUILT     == "built"
        assert CalibrationCaptureState.ERROR     == "error"


# ---------------------------------------------------------------------------
# TestControllerStart
# ---------------------------------------------------------------------------

class TestControllerStart:

    def test_starts_inactive(self):
        ctrl = TrackCalibrationCaptureController()
        assert ctrl.can_start is True
        assert ctrl.can_stop is False
        assert ctrl.is_recording is False

    def test_start_requires_track_location(self):
        ctrl = TrackCalibrationCaptureController()
        ok = ctrl.start_session("", "layout_full")
        assert ok is False
        assert ctrl._state == CalibrationCaptureState.ERROR

    def test_start_requires_layout(self):
        ctrl = TrackCalibrationCaptureController()
        ok = ctrl.start_session("fuji", "")
        assert ok is False
        assert ctrl._state == CalibrationCaptureState.ERROR

    def test_start_with_blanks_only_fails(self):
        ctrl = TrackCalibrationCaptureController()
        assert ctrl.start_session("  ", "  ") is False

    def test_start_with_valid_ids_succeeds(self):
        ctrl = TrackCalibrationCaptureController()
        ok = ctrl.start_session("fuji", "fuji__full")
        assert ok is True
        assert ctrl._state == CalibrationCaptureState.RECORDING
        assert ctrl.is_recording is True
        assert ctrl.can_stop is True
        assert ctrl.can_start is False

    def test_start_uses_porsche_as_default_car(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        assert ctrl._session is not None
        assert ctrl._session.calibration_car_id == PRIMARY_CALIBRATION_CAR_ID

    def test_start_allows_custom_car_id(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full", calibration_car_id="my_custom_car")
        assert ctrl._session.calibration_car_id == "my_custom_car"

    def test_start_resets_previous_state(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.add_sample_from_packet(_mk())
        ctrl.stop_session()

        # Restart
        ctrl.start_session("fuji", "fuji__full")
        assert ctrl._total_samples == 0
        assert ctrl._current_lap_samples == []
        assert ctrl._session.laps == []


# ---------------------------------------------------------------------------
# TestControllerSampling
# ---------------------------------------------------------------------------

class TestControllerSampling:

    def test_captures_when_recording(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        accepted = ctrl.add_sample_from_packet(_mk())
        assert accepted is True
        assert ctrl._total_samples == 1

    def test_ignores_when_inactive(self):
        ctrl = TrackCalibrationCaptureController()
        accepted = ctrl.add_sample_from_packet(_mk())
        assert accepted is False
        assert ctrl._total_samples == 0

    def test_ignores_when_stopped(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.stop_session()
        accepted = ctrl.add_sample_from_packet(_mk())
        assert accepted is False

    def test_ignores_paused_packet(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.add_sample_from_packet(_mk())                   # accepted
        ctrl.add_sample_from_packet(_mk(paused=True))        # rejected
        assert ctrl._total_samples == 1

    def test_ignores_off_track_packet(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.add_sample_from_packet(_mk(car_on_track=False))
        assert ctrl._total_samples == 0


# ---------------------------------------------------------------------------
# TestControllerLapGrouping
# ---------------------------------------------------------------------------

class TestControllerLapGrouping:

    def test_samples_grouped_by_lap_number(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")

        # 3 samples on lap 1
        for _ in range(3):
            ctrl.add_sample_from_packet(_mk(laps_completed=0))

        assert ctrl._current_lap_number == 1
        assert len(ctrl._current_lap_samples) == 3
        assert len(ctrl._session.laps) == 0  # no closed lap yet

    def test_lap_boundary_closes_previous_lap(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")

        # 3 samples on lap 1
        for _ in range(3):
            ctrl.add_sample_from_packet(_mk(laps_completed=0))

        # First sample of lap 2 triggers close of lap 1
        ctrl.add_sample_from_packet(_mk(laps_completed=1))

        assert len(ctrl._session.laps) == 1
        assert ctrl._session.laps[0].lap_number == 1
        assert len(ctrl._session.laps[0].samples) == 3
        assert ctrl._current_lap_number == 2
        assert len(ctrl._current_lap_samples) == 1

    def test_multiple_lap_transitions(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")

        for i in range(5):
            ctrl.add_sample_from_packet(_mk(laps_completed=0))
        for i in range(5):
            ctrl.add_sample_from_packet(_mk(laps_completed=1))
        for i in range(5):
            ctrl.add_sample_from_packet(_mk(laps_completed=2))

        ctrl.stop_session()

        assert len(ctrl._session.laps) == 3
        assert ctrl._session.laps[0].lap_number == 1
        assert ctrl._session.laps[1].lap_number == 2
        assert ctrl._session.laps[2].lap_number == 3

    def test_stop_flushes_partial_lap(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")

        for _ in range(5):
            ctrl.add_sample_from_packet(_mk(laps_completed=0))

        ctrl.stop_session()

        assert len(ctrl._session.laps) == 1
        assert len(ctrl._session.laps[0].samples) == 5

    def test_lap_time_computed_from_timestamps(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")

        for i in range(5):
            ctrl.add_sample_from_packet(_mk(laps_completed=0, t_ms=i * 1000))

        ctrl.stop_session()

        assert ctrl._session.laps[0].lap_time_ms == 4000  # 4000 - 0

    def test_practice_mode_negative_laps_uses_fallback(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")

        # Simulate practice mode: laps_completed = -1
        ctrl.add_sample_from_packet(_mk(laps_completed=-1))
        # Fallback should be 1 (default when no previous lap number set)
        assert ctrl._current_lap_number == 1
        assert ctrl._total_samples == 1


# ---------------------------------------------------------------------------
# TestControllerStop
# ---------------------------------------------------------------------------

class TestControllerStop:

    def test_stop_changes_state_to_stopped(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ok = ctrl.stop_session()
        assert ok is True
        assert ctrl._state == CalibrationCaptureState.STOPPED

    def test_stop_fails_when_not_recording(self):
        ctrl = TrackCalibrationCaptureController()
        ok = ctrl.stop_session()
        assert ok is False

    def test_stop_twice_fails(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.stop_session()
        ok = ctrl.stop_session()
        assert ok is False

    def test_can_build_only_after_stop_with_enough_laps(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        assert ctrl.can_build is False  # still recording
        ctrl.stop_session()
        assert ctrl.can_build is True


# ---------------------------------------------------------------------------
# TestControllerBuild
# ---------------------------------------------------------------------------

class TestControllerBuild:

    def test_build_fails_while_recording(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        result = ctrl.build_reference_path()
        assert result.success is False
        assert any("recording" in e.lower() for e in result.errors)

    def test_build_fails_without_session(self):
        ctrl = TrackCalibrationCaptureController()
        result = ctrl.build_reference_path()
        assert result.success is False

    def test_build_fails_with_no_laps(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.stop_session()
        result = ctrl.build_reference_path()
        assert result.success is False

    def test_build_fails_with_only_one_lap(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        for i in range(MIN_CALIBRATION_SAMPLES + 5):
            ctrl.add_sample_from_packet(_MockPacket(
                laps_completed=0, pos_x=float(i) + 1.0, pos_y=1.0, time_of_day_ms=i * 100
            ))
        ctrl.stop_session()
        result = ctrl.build_reference_path()
        assert result.success is False

    def test_build_succeeds_with_two_good_laps(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        result = ctrl.build_reference_path()
        assert result.success is True
        assert result.reference_path is not None
        assert len(result.reference_path.points) > 0

    def test_build_sets_state_to_built(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        ctrl.build_reference_path()
        assert ctrl._state == CalibrationCaptureState.BUILT

    def test_can_save_only_after_successful_build(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        assert ctrl.can_save is False
        ctrl.build_reference_path()
        assert ctrl.can_save is True

    def test_build_can_be_called_again_after_built(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        r1 = ctrl.build_reference_path()
        r2 = ctrl.build_reference_path()
        assert r1.success is True
        assert r2.success is True


# ---------------------------------------------------------------------------
# TestControllerSave
# ---------------------------------------------------------------------------

class TestControllerSave:

    def test_save_returns_none_before_build(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.stop_session()
        assert ctrl.save_reference_path() is None

    def test_save_to_temp_dir_returns_path(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        ctrl.build_reference_path()

        with tempfile.TemporaryDirectory() as tmpdir:
            saved = ctrl.save_reference_path(Path(tmpdir))
            assert saved is not None
            assert saved.exists()
            assert saved.suffix == ".json"

    def test_saved_path_appears_in_status_summary(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        ctrl.build_reference_path()

        with tempfile.TemporaryDirectory() as tmpdir:
            saved = ctrl.save_reference_path(Path(tmpdir))
            s = ctrl.get_status_summary()
            assert s["saved_path"] == str(saved)


# ---------------------------------------------------------------------------
# TestControllerStatusSummary
# ---------------------------------------------------------------------------

class TestControllerStatusSummary:

    def test_initial_summary_fields_present(self):
        ctrl = TrackCalibrationCaptureController()
        s = ctrl.get_status_summary()
        required_keys = {
            "state", "track_location_id", "layout_id", "total_samples",
            "lap_count", "current_lap_number", "in_progress_samples",
            "usable_laps", "rejected_laps", "low_confidence_laps",
            "reference_path_points", "confidence", "warnings",
            "saved_path", "error",
        }
        assert required_keys.issubset(set(s.keys()))

    def test_initial_state_is_inactive(self):
        ctrl = TrackCalibrationCaptureController()
        s = ctrl.get_status_summary()
        assert s["state"] == "inactive"
        assert s["total_samples"] == 0
        assert s["lap_count"] == 0

    def test_recording_state_in_summary(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        for _ in range(5):
            ctrl.add_sample_from_packet(_mk())
        s = ctrl.get_status_summary()
        assert s["state"] == "recording"
        assert s["total_samples"] == 5
        assert s["in_progress_samples"] == 5
        assert s["track_location_id"] == "fuji"
        assert s["layout_id"] == "fuji__full"

    def test_stopped_state_in_summary(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.add_sample_from_packet(_mk())
        ctrl.stop_session()
        s = ctrl.get_status_summary()
        assert s["state"] == "stopped"
        assert s["lap_count"] == 1

    def test_built_state_in_summary_with_path_points(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        ctrl.build_reference_path()
        s = ctrl.get_status_summary()
        assert s["state"] == "built"
        assert s["reference_path_points"] > 0
        assert s["confidence"] > 0.0

    def test_error_state_in_summary(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("", "")
        s = ctrl.get_status_summary()
        assert s["state"] == "error"
        assert s["error"] != ""


# ---------------------------------------------------------------------------
# TestCanStartStopBuildSaveProperties
# ---------------------------------------------------------------------------

class TestButtonStateProperties:

    def test_can_start_true_initially(self):
        ctrl = TrackCalibrationCaptureController()
        assert ctrl.can_start is True

    def test_can_start_false_while_recording(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        assert ctrl.can_start is False

    def test_can_start_true_after_stop(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.stop_session()
        assert ctrl.can_start is True

    def test_can_stop_false_initially(self):
        ctrl = TrackCalibrationCaptureController()
        assert ctrl.can_stop is False

    def test_can_stop_true_while_recording(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        assert ctrl.can_stop is True

    def test_can_stop_false_after_stop(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.stop_session()
        assert ctrl.can_stop is False

    def test_can_build_false_without_enough_laps(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.add_sample_from_packet(_mk())
        ctrl.stop_session()
        assert ctrl.can_build is False  # only 1 closed lap (< MIN_USABLE_LAPS_FOR_PATH)

    def test_can_build_true_with_enough_laps(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        assert ctrl.can_build is True

    def test_can_save_false_before_build(self):
        ctrl = TrackCalibrationCaptureController()
        assert ctrl.can_save is False

    def test_can_save_false_after_failed_build(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        ctrl.stop_session()
        ctrl.build_reference_path()  # no laps → fails
        assert ctrl.can_save is False


# ---------------------------------------------------------------------------
# TestControllerEvaluateLaps
# ---------------------------------------------------------------------------

class TestControllerEvaluateLaps:

    def test_evaluate_returns_empty_without_session(self):
        ctrl = TrackCalibrationCaptureController()
        assert ctrl.evaluate_laps() == []

    def test_evaluate_returns_results_per_lap(self):
        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session("fuji", "fuji__full")
        _make_two_good_laps(ctrl)
        ctrl.stop_session()
        results = ctrl.evaluate_laps()
        assert len(results) == MIN_USABLE_LAPS_FOR_PATH


# ---------------------------------------------------------------------------
# Regression: Group 17A / 17B / 17C symbols importable
# ---------------------------------------------------------------------------

class TestRegressionImports:

    def test_17a_track_intelligence_importable(self):
        from data.track_intelligence import (
            TrackLocationSeed, TrackLayoutSeed, TrackSeedLoadResult,
            load_track_seed, get_track_locations, search_track_layouts,
        )
        assert TrackLocationSeed is not None

    def test_17b_track_modelling_vm_importable(self):
        from ui.track_modelling_vm import (
            format_layout_facts, format_readiness, format_calibration_car,
            build_location_display_items, build_layout_display_items,
        )
        assert format_layout_facts is not None

    def test_17c_track_calibration_importable(self):
        from data.track_calibration import (
            TelemetrySample, CalibrationLap, CalibrationSession,
            CalibrationBuildResult, ReferencePath,
            build_reference_path, export_reference_path_json,
            import_reference_path_json, assess_session_laps,
        )
        assert TelemetrySample is not None

    def test_17d_runtime_importable(self):
        from data.track_calibration_runtime import (
            can_capture_calibration_sample, infer_lap_number,
            packet_to_calibration_sample, CalibrationCaptureState,
            TrackCalibrationCaptureController,
        )
        assert TrackCalibrationCaptureController is not None
