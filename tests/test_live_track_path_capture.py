"""Tests for data/live_track_path_capture.py (continuous refinement, Phase 1)."""
from __future__ import annotations

import math

from data.live_track_path_capture import LiveTrackPathCapture


class FakePacket:
    """Duck-typed stand-in for a GT7 packet (fields packet_to_calibration_sample reads)."""
    def __init__(self, x, y, z, lap=1, elapsed_ms=0, speed=120.0,
                 car_on_track=True, paused=False, loading=False):
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
        self.speed_kmh = speed
        self.current_gear = 4
        self.engine_rpm = 6000.0
        self.throttle = 1.0
        self.brake = 0.0
        self.time_of_day_ms = elapsed_ms
        self.road_distance = 0.0
        self.angvel_z = 0.0
        self.road_plane_y = 1.0
        # On-track gate (can_capture_calibration_sample)
        self.car_on_track = car_on_track
        self.paused = paused
        self.loading = loading


def _cap():
    return LiveTrackPathCapture("fuji", "fuji__full_course", car_name="Porsche RSR")


def test_matches_identity():
    cap = _cap()
    assert cap.matches("fuji", "fuji__full_course")
    assert cap.matches(" fuji ", " fuji__full_course ")
    assert not cap.matches("fuji", "fuji__short")
    assert not cap.matches("suzuka", "fuji__full_course")


def test_valid_samples_accumulate_into_one_lap():
    cap = _cap()
    for i in range(10):
        assert cap.add_packet(FakePacket(i * 1.0, 0.5, i * 2.0, lap=1, elapsed_ms=i * 100), 1)
    assert cap.accepted_sample_count == 10
    assert cap.rejected_sample_count == 0
    # In-progress lap not counted until finalised.
    assert cap.lap_count() == 0
    session = cap.build_session()
    assert len(session.laps) == 1
    assert len(session.laps[0].samples) == 10
    assert session.laps[0].lap_time_ms == 900  # 9*100
    assert session.track_location_id == "fuji"
    assert session.layout_id == "fuji__full_course"


def test_lap_rollover_splits_laps():
    cap = _cap()
    for i in range(5):
        cap.add_packet(FakePacket(i, 0.5, i, lap=1), 1)
    for i in range(7):
        cap.add_packet(FakePacket(i, 0.5, i, lap=2), 2)
    # Lap 1 finalised on rollover; lap 2 still in-progress.
    assert cap.lap_count() == 1
    session = cap.build_session()
    assert [l.lap_number for l in session.laps] == [1, 2]
    assert [len(l.samples) for l in session.laps] == [5, 7]


def test_rejects_zero_and_nonfinite_xyz():
    cap = _cap()
    assert not cap.add_packet(FakePacket(0.0, 0.0, 0.0, lap=1), 1)          # all-zero
    assert not cap.add_packet(FakePacket(float("nan"), 1.0, 2.0, lap=1), 1)  # NaN
    assert not cap.add_packet(FakePacket(float("inf"), 1.0, 2.0, lap=1), 1)  # inf
    assert not cap.add_packet(FakePacket(None, 1.0, 2.0, lap=1), 1)          # None
    assert cap.rejected_sample_count == 4
    assert cap.accepted_sample_count == 0
    assert cap.build_session().laps == []


def test_offtrack_paused_loading_rejected():
    cap = _cap()
    assert not cap.add_packet(FakePacket(1.0, 0.5, 2.0, car_on_track=False), 1)  # off-track
    assert not cap.add_packet(FakePacket(1.0, 0.5, 2.0, paused=True), 1)          # paused
    assert not cap.add_packet(FakePacket(1.0, 0.5, 2.0, loading=True), 1)         # loading
    assert cap.rejected_sample_count == 3
    assert cap.accepted_sample_count == 0


def test_invalid_lap_number_rejected():
    cap = _cap()
    assert not cap.add_packet(FakePacket(1.0, 0.0, 2.0), lap_number="not-an-int")
    assert cap.rejected_sample_count == 1


def test_pit_lap_flagged_from_in_pit_samples():
    cap = _cap()
    for i in range(5):
        cap.add_packet(FakePacket(i, 0.5, i, lap=1), 1, in_pit=(i >= 2))  # lap 1 hits pit
    for i in range(4):
        cap.add_packet(FakePacket(i, 0.5, i, lap=2), 2)                    # lap 2 clean
    session = cap.build_session()
    flags = {l.lap_number: l.is_pit_lap for l in session.laps}
    assert flags[1] is True
    assert flags[2] is False


def test_build_session_is_repeatable_and_appends():
    cap = _cap()
    for i in range(4):
        cap.add_packet(FakePacket(i, 0.5, i, lap=1), 1)
    s1 = cap.build_session()
    assert len(s1.laps) == 1
    # More packets on a new lap after build_session → next build appends.
    for i in range(3):
        cap.add_packet(FakePacket(i, 0.5, i, lap=2), 2)
    s2 = cap.build_session()
    assert [l.lap_number for l in s2.laps] == [1, 2]
