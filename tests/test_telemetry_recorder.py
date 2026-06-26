"""Unit tests for telemetry.recorder (AC2).

Covers LapTelemetryRecorder (sampling, lap transitions, finalize/query API)
and _compute_stats (lock-up, wheelspin, oversteer, rev-limiter, off-track,
empty frames).
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_packet(**overrides):
    """Return a SimpleNamespace mimicking GT7Packet with sensible defaults."""
    defaults = dict(
        car_on_track=True,
        time_of_day_ms=0,
        speed_kmh=100.0,
        throttle=0.5,
        brake=0.0,
        current_gear=3,
        engine_rpm=5000.0,
        road_distance=0.0,
        wheel_rps=(10.0, 10.0, 10.0, 10.0),
        tyre_radius=(0.3, 0.3, 0.3, 0.3),
        suspension=(0.01, 0.01, 0.01, 0.01),
        angvel_z=0.0,
        vel_x=0.0,
        vel_y=27.7,
        body_height=0.1,
        pos_x=0.0,
        pos_y=0.0,
        pos_z=0.0,
        rev_limiter_active=False,
        brake_raw=0,
        car_max_speed_raw=0,
        road_plane_y=1.0,
        tyre_temp_fl=0.0,
        tyre_temp_fr=0.0,
        tyre_temp_rl=0.0,
        tyre_temp_rr=0.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_frame(**overrides):
    """Return a TelemetryFrame with sensible defaults."""
    from telemetry.recorder import TelemetryFrame
    defaults = dict(
        elapsed_ms=1000,
        speed_kmh=100.0,
        throttle=0.5,
        brake=0.0,
        gear=3,
        rpm=5000.0,
        road_distance=500.0,
        wheel_rps=(10.0, 10.0, 10.0, 10.0),
        tyre_radius=(0.3, 0.3, 0.3, 0.3),
        suspension=(0.01, 0.01, 0.01, 0.01),
    )
    defaults.update(overrides)
    return TelemetryFrame(**defaults)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

class TestSampling:
    def test_only_multiples_of_sample_every_stored(self):
        from telemetry.recorder import LapTelemetryRecorder
        recorder = LapTelemetryRecorder(max_laps=20, sample_every=6)
        pkt = _make_packet(time_of_day_ms=0)
        for i in range(12):
            recorder.record_frame(pkt, lap_num=1)
        # packet_counter goes 1..12; stored when counter % 6 == 0 → at 6, 12
        assert len(recorder._current_frames) == 2

    def test_car_off_track_not_appended(self):
        from telemetry.recorder import LapTelemetryRecorder
        recorder = LapTelemetryRecorder(max_laps=20, sample_every=1)
        pkt = _make_packet(car_on_track=False)
        for _ in range(5):
            recorder.record_frame(pkt, lap_num=1)
        assert len(recorder._current_frames) == 0

    def test_car_on_track_true_frame_is_appended(self):
        from telemetry.recorder import LapTelemetryRecorder
        recorder = LapTelemetryRecorder(max_laps=20, sample_every=1)
        pkt = _make_packet(car_on_track=True)
        for _ in range(3):
            recorder.record_frame(pkt, lap_num=1)
        assert len(recorder._current_frames) == 3


# ---------------------------------------------------------------------------
# Lap transitions
# ---------------------------------------------------------------------------

class TestLapTransitions:
    def test_lap_change_resets_frames(self):
        from telemetry.recorder import LapTelemetryRecorder
        recorder = LapTelemetryRecorder(max_laps=20, sample_every=1)
        pkt = _make_packet(time_of_day_ms=1000)
        for _ in range(3):
            recorder.record_frame(pkt, lap_num=1)
        assert len(recorder._current_frames) == 3
        recorder.record_frame(pkt, lap_num=2)
        # After lap change only 1 frame from new lap
        assert len(recorder._current_frames) == 1


# ---------------------------------------------------------------------------
# Finalize and query API
# ---------------------------------------------------------------------------

class TestFinalizeAndQuery:
    def _fill_recorder(self, n_laps=3, lap_time_base=90000):
        from telemetry.recorder import LapTelemetryRecorder
        recorder = LapTelemetryRecorder(max_laps=20, sample_every=1)
        pkt = _make_packet(speed_kmh=120.0, throttle=0.6, brake=0.0,
                           time_of_day_ms=0)
        for lap in range(1, n_laps + 1):
            recorder.record_frame(pkt, lap_num=lap)
            recorder.finalize_lap(lap, lap_time_base + (lap - 1) * 1000)
        return recorder

    def test_finalize_last_lap_returns_correct_lap_num(self):
        recorder = self._fill_recorder(3)
        last = recorder.last_lap()
        assert last is not None
        assert last.lap_num == 3

    def test_best_lap_has_minimum_lap_time(self):
        recorder = self._fill_recorder(3, lap_time_base=90000)
        best = recorder.best_lap()
        assert best is not None
        assert best.lap_time_ms == 90000  # lap 1 is fastest

    def test_get_lap_returns_correct_lap(self):
        recorder = self._fill_recorder(3)
        lap2 = recorder.get_lap(2)
        assert lap2 is not None
        assert lap2.lap_num == 2

    def test_get_lap_returns_none_for_missing(self):
        recorder = self._fill_recorder(3)
        assert recorder.get_lap(99) is None

    def test_recent_laps_capped_at_requested(self):
        recorder = self._fill_recorder(5)
        assert len(recorder.recent_laps(3)) == 3

    def test_recent_laps_returns_all_when_fewer_than_n(self):
        recorder = self._fill_recorder(5)
        assert len(recorder.recent_laps(10)) == 5

    def test_last_lap_empty_returns_none(self):
        from telemetry.recorder import LapTelemetryRecorder
        recorder = LapTelemetryRecorder()
        assert recorder.last_lap() is None

    def test_lap_count_capped_at_max_laps(self):
        from telemetry.recorder import LapTelemetryRecorder
        max_laps = 5
        recorder = LapTelemetryRecorder(max_laps=max_laps, sample_every=1)
        pkt = _make_packet(speed_kmh=100.0, throttle=0.5, brake=0.0,
                           time_of_day_ms=0)
        for lap in range(1, max_laps + 2):  # one more than max
            recorder.record_frame(pkt, lap_num=lap)
            recorder.finalize_lap(lap, 90000)
        assert recorder.lap_count() == max_laps


# ---------------------------------------------------------------------------
# _compute_stats
# ---------------------------------------------------------------------------

class TestComputeStats:
    """Direct tests of _compute_stats with hand-crafted TelemetryFrame lists."""

    _DEFAULT_RADIUS = (0.3, 0.3, 0.3, 0.3)

    def _wheel_ms_from_car(self, speed_kmh: float, fraction: float = 1.0) -> tuple:
        """Return wheel_rps so wheel_speed = speed_kmh * fraction (in m/s)."""
        target_ms = (speed_kmh / 3.6) * fraction
        # wheel_speed = mean(|rps[i]| * radius[i] * 2pi) = rps * r * 2pi (uniform)
        r = self._DEFAULT_RADIUS[0]
        rps = target_ms / (r * 2 * math.pi)
        return (rps, rps, rps, rps)

    def test_lock_up_detection(self):
        from telemetry.recorder import _compute_stats, TelemetryFrame
        # speed 50 km/h, brake > 0.3, wheel_speed < 50% of car speed
        car_speed = 50.0
        good_rps = self._wheel_ms_from_car(car_speed, 1.0)  # normal
        lockup_rps = self._wheel_ms_from_car(car_speed, 0.3)  # 30% → lock-up

        normal = _make_frame(speed_kmh=car_speed, brake=0.5,
                             wheel_rps=good_rps, tyre_radius=self._DEFAULT_RADIUS)
        lock = _make_frame(speed_kmh=car_speed, brake=0.5,
                           wheel_rps=lockup_rps, tyre_radius=self._DEFAULT_RADIUS)

        stats = _compute_stats([normal, lock, normal], 1, 90000)
        assert stats.lock_up_count >= 1

    def test_wheelspin_detection(self):
        from telemetry.recorder import _compute_stats
        car_speed = 30.0
        spin_rps = self._wheel_ms_from_car(car_speed, 1.5)  # 150% → wheelspin

        frame = _make_frame(speed_kmh=car_speed, throttle=0.9,
                            wheel_rps=spin_rps, tyre_radius=self._DEFAULT_RADIUS)
        stats = _compute_stats([frame, frame], 1, 90000)
        assert stats.wheelspin_count >= 1

    def test_oversteer_detection(self):
        from telemetry.recorder import _compute_stats
        frame = _make_frame(speed_kmh=60.0, angvel_z=1.0)  # > 0.8 threshold
        stats = _compute_stats([frame, frame], 1, 90000)
        assert stats.oversteer_count >= 1

    def test_rev_limiter_by_gear(self):
        from telemetry.recorder import _compute_stats
        # Two consecutive frames with limiter active in gear 4
        f1 = _make_frame(rev_limiter=True, gear=4)
        f2 = _make_frame(rev_limiter=True, gear=4)
        f3 = _make_frame(rev_limiter=False, gear=4)  # ends event
        stats = _compute_stats([f1, f2, f3], 1, 90000)
        assert stats.rev_limiter_count >= 1
        assert stats.rev_limiter_by_gear.get(4, 0) >= 1

    def test_off_track_detection(self):
        from telemetry.recorder import _compute_stats
        # road_plane_y = 0.3 < 0.5 threshold, speed > 20
        f_off = _make_frame(speed_kmh=50.0, road_plane_y=0.3)
        f_on = _make_frame(speed_kmh=50.0, road_plane_y=1.0)
        stats = _compute_stats([f_off, f_on], 1, 90000)
        assert stats.off_track_count >= 1

    def test_empty_frames_all_zeros_no_exception(self):
        from telemetry.recorder import _compute_stats
        stats = _compute_stats([], 1, 90000)
        assert stats.lock_up_count == 0
        assert stats.wheelspin_count == 0
        assert stats.max_speed_kmh == 0.0
        assert stats.avg_throttle_pct == 0.0
        assert stats.avg_brake_pct == 0.0
