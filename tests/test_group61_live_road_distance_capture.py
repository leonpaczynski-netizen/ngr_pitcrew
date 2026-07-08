"""Group 61 — raw live-packet road-distance capture tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_road_distance_capture import (  # noqa: E402
    LiveRoadDistanceCapture, RawRoadDistanceSample, analyse_live_capture,
)

LAP = 4563.0


def _pkt(rd, x=0.0, y=0.0, z=0.0, spd=200.0):
    return type("P", (), {"road_distance": rd, "pos_x": x, "pos_y": y, "pos_z": z,
                          "speed_kmh": spd})()


class TestAccumulation:
    def test_captures_raw_samples(self):
        cap = LiveRoadDistanceCapture(track_id="t", layout_id="t__l", car_id="c")
        for lap in range(1, 4):
            for j in range(11):
                cap.add_packet(_pkt((lap - 1) * LAP + LAP * j / 10), lap_number=lap)
        s = cap.summary()
        assert s["valid_count"] == 33 and s["packet_count"] == 33
        assert s["lap_count"] == 3 and s["laps_seen"] == [1, 2, 3]
        assert len(cap.samples) == 33
        assert all(isinstance(x, RawRoadDistanceSample) for x in cap.samples)

    def test_records_metadata_and_position(self):
        cap = LiveRoadDistanceCapture(track_id="fuji", layout_id="fuji__full", car_id="rsr",
                                      session_id="s1")
        cap.add_packet(_pkt(10.0, x=1.0, y=2.0, z=3.0, spd=180.0), lap_number=1)
        d = cap.to_capture_dict()
        assert d["track_location_id"] == "fuji" and d["session_id"] == "s1"
        assert cap.samples[0].pos_x == 1.0 and cap.samples[0].speed_kph == 180.0


class TestImpossibleValues:
    def test_nan_inf_none_negative(self):
        cap = LiveRoadDistanceCapture()
        assert cap.add_sample(road_distance=float("nan")) is False
        assert cap.add_sample(road_distance=float("inf")) is False
        assert cap.add_sample(road_distance=None) is False
        assert cap.add_sample(road_distance=-5.0) is True   # negative kept + flagged
        s = cap.summary()
        assert s["invalid_count"] == 2   # nan + inf
        assert s["missing_count"] == 1   # None
        assert s["negative_count"] == 1

    def test_packet_without_road_distance(self):
        cap = LiveRoadDistanceCapture()
        assert cap.add_packet(type("P", (), {"pos_x": 0, "pos_y": 0, "pos_z": 0})()) is False
        assert cap.summary()["missing_count"] == 1

    def test_never_raises_on_garbage(self):
        cap = LiveRoadDistanceCapture()
        for bad in (object(), "x", 123, {"road_distance": "z"}):
            cap.add_packet(bad)
        assert cap.summary()["valid_count"] == 0


class TestLapHandling:
    def test_lap_number_changes_group_correctly(self):
        cap = LiveRoadDistanceCapture()
        cap.add_sample(road_distance=0.0, lap_number=1)
        cap.add_sample(road_distance=100.0, lap_number=1)
        cap.add_sample(road_distance=0.0, lap_number=2)
        cap.add_sample(road_distance=100.0, lap_number=2)
        laps = cap.to_laps()
        assert len(laps) == 2
        assert laps[0]["lap_number"] == 1 and len(laps[0]["samples"]) == 2

    def test_missing_lap_markers_grouped(self):
        cap = LiveRoadDistanceCapture()
        cap.add_sample(road_distance=0.0)
        cap.add_sample(road_distance=100.0)
        laps = cap.to_laps()
        assert len(laps) == 1 and len(laps[0]["samples"]) == 2
        assert cap.summary()["no_lap_number_count"] == 2

    def test_insufficient_laps(self):
        cap = LiveRoadDistanceCapture(track_id="t", layout_id="l")
        for j in range(11):
            cap.add_sample(road_distance=LAP * j / 10, lap_number=1)
        r = analyse_live_capture(cap, lap_length_m=LAP)
        assert r.status.value in ("INSUFFICIENT_EVIDENCE", "UNKNOWN")


class TestAnalysisDelegation:
    def test_cumulative_confirmed_from_capture(self):
        cap = LiveRoadDistanceCapture(track_id="t", layout_id="l")
        for lap in range(1, 4):
            for j in range(21):
                cap.add_sample(road_distance=(lap - 1) * LAP + LAP * j / 20, lap_number=lap)
        r = analyse_live_capture(cap, lap_length_m=LAP)
        assert r.capture_status.value == "CUMULATIVE_CONFIRMED" and r.confirmed

    def test_non_distance_like_from_small_span(self):
        cap = LiveRoadDistanceCapture(track_id="t", layout_id="l")
        for lap in range(1, 4):
            for j in range(21):
                cap.add_sample(road_distance=-16.0 + 100.0 * j / 20, lap_number=lap)  # ~100 m span
        r = analyse_live_capture(cap, lap_length_m=LAP)
        assert r.capture_status.value == "NON_DISTANCE_LIKE"
        assert r.confirmed is False


class TestNoFileWrites:
    def test_module_writes_no_files(self):
        # The capture module is pure: no file I/O anywhere in its source.
        src = (ROOT / "data" / "live_road_distance_capture.py").read_text(encoding="utf-8")
        assert ".write_text(" not in src and ".write(" not in src
        assert "json.dump" not in src and "open(" not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
