"""Group 59 — approved reference-path asset registry + candidate validation tests.

Proves the shipped Fuji + Daytona approved paths still load and resolve identity,
the registry lists them, trusted lap length resolves only for known identity, and
the new candidate validator gives clear errors for malformed/incomplete assets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.reference_path_loader import (  # noqa: E402
    list_available_reference_paths,
    load_reference_path_for_layout,
    reference_path_asset_summary,
    resolve_trusted_lap_length,
    validate_reference_path_candidate,
    validate_reference_path_identity,
)

FUJI = ("fuji_international_speedway", "fuji_international_speedway__full_course")
DAYTONA = ("daytona_international_speedway", "daytona_international_speedway__road_course")


class TestShippedAssetsLoad:
    def test_fuji_loads_and_validates(self):
        res = load_reference_path_for_layout(*FUJI)
        assert res.has_stations and res.asset.station_count >= 100
        ok, _ = validate_reference_path_identity(res.asset, *FUJI)
        assert ok

    def test_daytona_loads_and_validates(self):
        res = load_reference_path_for_layout(*DAYTONA)
        assert res.has_stations and res.asset.station_count >= 100
        ok, _ = validate_reference_path_identity(res.asset, *DAYTONA)
        assert ok

    def test_registry_lists_both(self):
        assets = list_available_reference_paths()
        tracks = {a["track_id"] for a in assets}
        assert any("fuji" in t for t in tracks)
        assert any("daytona" in t for t in tracks)
        assert all(a["station_count"] > 0 for a in assets)


class TestTrustedLapLength:
    def test_fuji_and_daytona_have_trusted_length(self):
        assert (resolve_trusted_lap_length(*FUJI) or 0) > 1000.0
        assert (resolve_trusted_lap_length(*DAYTONA) or 0) > 1000.0

    def test_unknown_track_no_trusted_length(self, tmp_path):
        assert resolve_trusted_lap_length("spa", "spa__gp", search_roots=[tmp_path]) is None

    def test_summary_available_for_known(self):
        s = reference_path_asset_summary(*DAYTONA)
        assert s["available"] is True
        assert s["lap_length_m"] > 1000.0

    def test_summary_unavailable_honest(self, tmp_path):
        s = reference_path_asset_summary("spa", "spa__gp", search_roots=[tmp_path])
        assert s["available"] is False
        assert "unavailable" in s["message"].lower()


class TestCandidateValidation:
    def _v1(self, track, layout, n=5, lap=100.0):
        return {"schema_version": "reference_path_v1", "track_id": track,
                "layout_id": layout, "source": "approved_track_model", "lap_length_m": lap,
                "stations": [{"index": i, "x": i * 1.0, "y": 0.0, "z": 0.0,
                              "distance_along_lap_m": i * 1.0, "progress": i / (n - 1)}
                             for i in range(n)]}

    def test_valid_candidate_ok(self, tmp_path):
        p = tmp_path / "t__t__lay.reference_path.json"
        p.write_text(json.dumps(self._v1("t", "t__lay")), encoding="utf-8")
        v = validate_reference_path_candidate(p)
        assert v["ok"] is True and v["errors"] == []
        assert v["track_id"] == "t" and v["station_count"] == 5

    def test_missing_file(self, tmp_path):
        v = validate_reference_path_candidate(tmp_path / "nope.json")
        assert v["ok"] is False
        assert any("not found" in e for e in v["errors"])

    def test_malformed_json(self, tmp_path):
        p = tmp_path / "bad.reference_path.json"
        p.write_text("{ not json", encoding="utf-8")
        v = validate_reference_path_candidate(p)
        assert v["ok"] is False
        assert any("malformed" in e.lower() for e in v["errors"])

    def test_missing_stations(self, tmp_path):
        p = tmp_path / "x.reference_path.json"
        p.write_text(json.dumps({"track_id": "t", "layout_id": "l"}), encoding="utf-8")
        v = validate_reference_path_candidate(p)
        assert v["ok"] is False

    def test_identity_mismatch_is_error(self, tmp_path):
        p = tmp_path / "t__t__lay.reference_path.json"
        p.write_text(json.dumps(self._v1("t", "t__lay")), encoding="utf-8")
        v = validate_reference_path_candidate(p, expected_track_id="spa",
                                              expected_layout_id="spa__gp")
        assert v["ok"] is False
        assert any("mismatch" in e.lower() for e in v["errors"])

    def test_real_fuji_asset_is_valid_candidate(self):
        f = (ROOT / "data" / "track_models" /
             "fuji_international_speedway__fuji_international_speedway__full_course.reference_path.json")
        v = validate_reference_path_candidate(f, expected_track_id=FUJI[0],
                                              expected_layout_id=FUJI[1])
        assert v["ok"] is True
        assert v["lap_length_m"] > 1000.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
