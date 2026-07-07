"""Group 57 — pure reference-path loader tests.

Covers loading the explicit reference_path_v1 shape and the existing Group 17
calibration shape, station conversion, identity validation, and every malformed /
missing / NaN / duplicate / zero-lap-length edge without crashing or writing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import TrackPathStation  # noqa: E402
from data.reference_path_loader import (  # noqa: E402
    ReferencePathAsset,
    ReferencePathLoadResult,
    find_reference_path_candidates,
    load_reference_path_file,
    load_reference_path_for_layout,
    reference_path_to_track_stations,
    validate_reference_path_identity,
)


def _v1(n=11, lap=100.0):
    return {
        "schema_version": "reference_path_v1",
        "track_id": "test_track", "layout_id": "test_track__test_layout",
        "source": "approved_track_model", "lap_length_m": lap,
        "stations": [{"index": i, "x": i * 10.0, "y": 0.0, "z": 0.0,
                      "distance_along_lap_m": i * 10.0, "progress": i / (n - 1)}
                     for i in range(n)],
    }


def _g17(n=11):
    return {
        "track_location_id": "g17_track", "layout_id": "g17_track__lay",
        "calibration_car_id": "porsche_911_rsr_991_2017",
        "source_lap_count": 5, "confidence": 1.0, "built_at": "2026-07-04T00:00:00Z",
        "warnings": ["Lap 1 excluded: partial start lap"],
        "points": [{"lap_progress": i / (n - 1), "distance_along_lap_m": i * 10.0,
                    "x": i * 10.0, "y": 1.0, "z": 2.0, "speed_kph_avg": 100.0,
                    "source_lap_count": 5} for i in range(n)],
    }


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestLoadV1:
    def test_loads_valid_v1(self, tmp_path):
        p = _write(tmp_path, "a.reference_path.json", _v1())
        res = load_reference_path_file(p)
        assert res.available and res.has_stations
        assert res.asset.station_count == 11
        assert res.asset.lap_length_m == 100.0
        assert res.asset.source == "approved_track_model"

    def test_converts_to_track_stations(self, tmp_path):
        res = load_reference_path_file(_write(tmp_path, "a.reference_path.json", _v1()))
        st = reference_path_to_track_stations(res.asset)
        assert len(st) == 11
        assert all(isinstance(s, TrackPathStation) for s in st)
        assert abs(st[3].progress - 0.3) < 1e-9


class TestLoadGroup17:
    def test_loads_calibration_shape(self, tmp_path):
        res = load_reference_path_file(_write(tmp_path, "g.reference_path.json", _g17()))
        assert res.available and res.has_stations
        assert res.asset.track_id == "g17_track"
        assert res.asset.source == "calibration_reference_path"

    def test_build_warnings_not_surfaced_as_live(self, tmp_path):
        # Historical calibration notes live in metadata, NOT result.warnings.
        res = load_reference_path_file(_write(tmp_path, "g.reference_path.json", _g17()))
        assert res.warnings == ()
        assert res.asset.metadata.get("build_warnings")


class TestIdentity:
    def test_exact_match(self, tmp_path):
        res = load_reference_path_file(_write(tmp_path, "a.reference_path.json", _v1()))
        ok, msg = validate_reference_path_identity(res.asset, "test_track", "test_track__test_layout")
        assert ok

    def test_mismatch(self, tmp_path):
        res = load_reference_path_file(_write(tmp_path, "a.reference_path.json", _v1()))
        ok, msg = validate_reference_path_identity(res.asset, "spa", "spa__gp")
        assert not ok
        assert "mismatch" in msg

    def test_display_name_tolerant(self, tmp_path):
        res = load_reference_path_file(_write(tmp_path, "a.reference_path.json", _v1()))
        # Empty expected → not a mismatch (nothing to contradict).
        ok, _ = validate_reference_path_identity(res.asset, "", "")
        assert ok


class TestEdgeCases:
    def test_missing_file(self, tmp_path):
        res = load_reference_path_file(tmp_path / "nope.json")
        assert not res.available and not res.has_stations
        assert any("unavailable" in w for w in res.warnings)

    def test_malformed_json(self, tmp_path):
        p = tmp_path / "bad.reference_path.json"
        p.write_text("{ not json", encoding="utf-8")
        res = load_reference_path_file(p)
        assert not res.has_stations
        assert res.source == "malformed"
        assert any("malformed" in w for w in res.warnings)

    def test_missing_stations(self, tmp_path):
        res = load_reference_path_file(_write(tmp_path, "x.reference_path.json",
                                              {"track_id": "t", "layout_id": "l"}))
        assert not res.has_stations
        assert any("no usable stations" in w for w in res.warnings)

    def test_bad_station_values_skipped(self, tmp_path):
        d = _v1()
        d["stations"] = [
            {"x": "bad", "z": 0.0},                                  # non-numeric
            {"x": 1.0},                                             # z missing
            {"x": 1.0, "y": 0.0, "z": 2.0, "distance_along_lap_m": 5.0, "progress": 0.5},  # OK
        ]
        res = load_reference_path_file(_write(tmp_path, "x.reference_path.json", d))
        assert res.asset.station_count == 1
        assert any("malformed station" in w for w in res.warnings)

    def test_nan_inf_rejected(self, tmp_path):
        d = _v1(n=3)
        d["stations"][0]["x"] = float("nan")
        d["stations"][1]["z"] = float("inf")
        res = load_reference_path_file(_write(tmp_path, "x.reference_path.json", d))
        assert res.asset.station_count == 1  # only the finite one survives

    def test_zero_negative_lap_length(self, tmp_path):
        d = _v1()
        d["lap_length_m"] = 0.0
        res = load_reference_path_file(_write(tmp_path, "x.reference_path.json", d))
        # Still usable (stations carry explicit progress), but lap length warned.
        assert res.has_stations
        assert any("no usable lap length" in w for w in res.warnings)

    def test_duplicate_distances_ok(self, tmp_path):
        d = _v1(n=3)
        for s in d["stations"]:
            s["distance_along_lap_m"] = 5.0
        res = load_reference_path_file(_write(tmp_path, "x.reference_path.json", d))
        assert res.has_stations and res.asset.station_count == 3

    def test_never_writes_files(self, tmp_path):
        before = set(p.name for p in tmp_path.iterdir())
        _write(tmp_path, "a.reference_path.json", _v1())
        load_reference_path_file(tmp_path / "a.reference_path.json")
        after = set(p.name for p in tmp_path.iterdir())
        assert after == before | {"a.reference_path.json"}  # only our fixture


class TestDiscovery:
    def test_finds_and_loads_by_identity(self, tmp_path):
        _write(tmp_path, "test_track__test_track__test_layout.reference_path.json", _v1())
        _write(tmp_path, "other__other__lay.reference_path.json",
               {**_v1(), "track_id": "other", "layout_id": "other__lay"})
        cands = find_reference_path_candidates(
            "test_track", "test_track__test_layout", search_roots=[tmp_path])
        assert len(cands) == 1
        res = load_reference_path_for_layout(
            "test_track", "test_track__test_layout", search_roots=[tmp_path])
        assert res.has_stations

    def test_missing_layout_returns_unavailable(self, tmp_path):
        res = load_reference_path_for_layout("nope", "nope__x", search_roots=[tmp_path])
        assert not res.available
        assert any("unavailable" in w for w in res.warnings)


class TestRealFujiAsset:
    def test_ships_and_loads(self):
        # The repo ships a real calibration-sourced Fuji reference path.
        res = load_reference_path_for_layout(
            "fuji_international_speedway", "fuji_international_speedway__full_course")
        assert res.has_stations
        assert res.asset.station_count >= 100
        assert res.asset.lap_length_m > 1000.0
        st = reference_path_to_track_stations(res.asset)
        assert len(st) == res.asset.station_count


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
