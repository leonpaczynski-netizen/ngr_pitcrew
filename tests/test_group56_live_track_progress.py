"""Group 56 — pure live-track-progress resolver tests.

Covers nearest-station matching, progress normalisation (incl. wrap), lateral
offset, HIGH/MEDIUM/LOW/UNKNOWN thresholds, far-off-track, and every malformed /
missing / NaN / duplicate / zero-lap-length edge without crashing.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import (  # noqa: E402
    CONF_HIGH_M,
    CONF_LOW_M,
    CONF_MED_M,
    LiveTrackProgressResult,
    TrackPathStation,
    TrackProgressConfidence,
    build_track_path_stations,
    estimate_lateral_offset,
    format_live_track_progress_evidence,
    nearest_station,
    normalise_distance_to_progress,
    resolve_live_track_progress,
)
from strategy.race_strategy_live_replan import (  # noqa: E402
    fuji_position_at_progress,
    fuji_reference_path,
)


def _straight_path(n=11, spacing=10.0):
    """A straight path along +x, lap length = (n-1)*spacing."""
    pts = [{"x": i * spacing, "y": 0.0, "z": 0.0,
            "distance_along_lap_m": i * spacing, "lap_progress": i / (n - 1)}
           for i in range(n)]
    return build_track_path_stations({"reference_path": {"points": pts}})


class TestBuildStations:
    def test_from_reference_path_points(self):
        st = _straight_path()
        assert len(st) == 11
        assert all(isinstance(s, TrackPathStation) for s in st)
        assert st[3].distance_along_lap_m == 30.0
        assert abs(st[3].progress - 0.3) < 1e-9

    def test_from_station_map_progress_pct(self):
        sts = [{"x": 0.0, "z": 0.0, "station_m": 0.0, "progress_pct": 0.0},
               {"x": 10.0, "z": 0.0, "station_m": 10.0, "progress_pct": 50.0}]
        st = build_track_path_stations({"stations": sts})
        assert len(st) == 2
        assert abs(st[1].progress - 0.5) < 1e-9  # pct → fraction

    def test_missing_and_malformed(self):
        assert build_track_path_stations(None) == []
        assert build_track_path_stations({}) == []
        assert build_track_path_stations({"reference_path": {"points": []}}) == []
        # Malformed points skipped, not crashing.
        pts = [{"x": "bad", "z": 0.0}, {"x": 1.0, "z": 2.0, "distance_along_lap_m": 5.0}]
        st = build_track_path_stations({"reference_path": {"points": pts}})
        assert len(st) == 1


class TestNormalise:
    def test_basic(self):
        assert normalise_distance_to_progress(50, 100) == 0.5
        assert normalise_distance_to_progress(0, 100) == 0.0

    def test_wraps_past_lap_start(self):
        assert abs(normalise_distance_to_progress(150, 100) - 0.5) < 1e-9
        assert abs(normalise_distance_to_progress(250, 100) - 0.5) < 1e-9

    def test_zero_or_missing_lap_length(self):
        assert normalise_distance_to_progress(50, 0) is None
        assert normalise_distance_to_progress(50, None) is None
        assert normalise_distance_to_progress(None, 100) is None

    def test_nan_inf(self):
        assert normalise_distance_to_progress(float("nan"), 100) is None
        assert normalise_distance_to_progress(50, float("inf")) is None


class TestNearestStation:
    def test_exact_match(self):
        st = _straight_path()
        idx, d = nearest_station((30.0, 0.0, 0.0), st)
        assert idx == 3
        assert d == 0.0

    def test_nearest_between(self):
        st = _straight_path()
        idx, d = nearest_station((32.0, 0.0, 1.0), st)
        assert idx == 3
        assert d == pytest.approx(math.hypot(2.0, 1.0))

    def test_empty_or_bad(self):
        assert nearest_station((0, 0, 0), []) is None
        assert nearest_station(None, _straight_path()) is None

    def test_ignores_elevation(self):
        # A big Y difference must not change the XZ nearest station.
        st = _straight_path()
        idx, d = nearest_station((30.0, 999.0, 0.0), st)
        assert idx == 3 and d == 0.0

    def test_duplicate_distances_no_crash(self):
        pts = [{"x": 0.0, "z": 0.0, "distance_along_lap_m": 5.0, "lap_progress": 0.0},
               {"x": 10.0, "z": 0.0, "distance_along_lap_m": 5.0, "lap_progress": 0.5}]
        st = build_track_path_stations({"reference_path": {"points": pts}})
        assert nearest_station((10.0, 0.0, 0.0), st)[0] == 1


class TestLateralOffset:
    def test_offset_sign(self):
        st = _straight_path()
        # Travelling +x; +z is right of centreline → negative offset.
        off = estimate_lateral_offset((30.0, 0.0, 3.0), st[3], st[4])
        assert off is not None and off < 0
        off2 = estimate_lateral_offset((30.0, 0.0, -3.0), st[3], st[4])
        assert off2 is not None and off2 > 0

    def test_no_orientation_returns_none(self):
        s = TrackPathStation(index=0, x=0, y=0, z=0, distance_along_lap_m=0.0)
        assert estimate_lateral_offset((1, 0, 1), s, None) is None


class TestConfidenceThresholds:
    def test_high(self):
        st = _straight_path()
        r = resolve_live_track_progress((30.0, 0.0, CONF_HIGH_M - 1), st, lap_length_m=100.0)
        assert r.confidence == TrackProgressConfidence.HIGH
        assert r.has_progress and abs(r.progress - 0.3) < 1e-9

    def test_medium(self):
        st = _straight_path()
        r = resolve_live_track_progress((30.0, 0.0, CONF_MED_M - 1), st)
        assert r.confidence == TrackProgressConfidence.MEDIUM

    def test_low(self):
        st = _straight_path()
        r = resolve_live_track_progress((30.0, 0.0, CONF_LOW_M - 1), st)
        assert r.confidence == TrackProgressConfidence.LOW
        assert not r.usable_for_pit

    def test_far_off_unknown(self):
        st = _straight_path()
        r = resolve_live_track_progress((30.0, 0.0, CONF_LOW_M + 50), st)
        assert r.confidence == TrackProgressConfidence.UNKNOWN
        assert r.progress is None
        assert any("far from the reference path" in w for w in r.warnings)

    def test_identity_mismatch_caps_confidence(self):
        st = _straight_path()
        r = resolve_live_track_progress((30.0, 0.0, 0.0), st, identity_ok=False)
        assert r.confidence == TrackProgressConfidence.LOW
        assert any("does not match current track" in w for w in r.warnings)


class TestMissingInputs:
    def test_no_path(self):
        r = resolve_live_track_progress((0, 0, 0), [])
        assert r.confidence == TrackProgressConfidence.UNKNOWN
        assert "reference path unavailable" in r.message.lower()

    def test_no_position(self):
        r = resolve_live_track_progress(None, _straight_path())
        assert r.confidence == TrackProgressConfidence.UNKNOWN
        assert "world position unavailable" in r.message.lower()

    def test_nan_position(self):
        r = resolve_live_track_progress((float("nan"), 0, 0), _straight_path())
        assert r.confidence == TrackProgressConfidence.UNKNOWN

    def test_partial_dict_station_no_crash(self):
        st = build_track_path_stations({"reference_path": {"points": [{"x": 1.0}]}})
        assert st == []  # z missing → skipped
        r = resolve_live_track_progress((1, 0, 0), st)
        assert r.confidence == TrackProgressConfidence.UNKNOWN


class TestFujiFixture:
    def test_progress_round_trips(self):
        ctx = fuji_reference_path()
        st = build_track_path_stations(ctx)
        assert len(st) > 100
        pos = fuji_position_at_progress(0.5)
        r = resolve_live_track_progress(pos, st, track_id="fuji_speedway")
        assert r.confidence in (TrackProgressConfidence.HIGH, TrackProgressConfidence.MEDIUM)
        assert abs(r.progress - 0.5) < 0.02


class TestRendering:
    def test_found_lines(self):
        st = _straight_path()
        r = resolve_live_track_progress((30.0, 0.0, 3.0), st)
        ev = format_live_track_progress_evidence(r)
        assert any("track progress" in f for f in ev["found"])
        assert any("position match" in f for f in ev["found"])

    def test_missing_lines_honest(self):
        r = resolve_live_track_progress((0, 0, 0), [])
        ev = format_live_track_progress_evidence(r)
        assert any("reference path unavailable" in m for m in ev["missing"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
