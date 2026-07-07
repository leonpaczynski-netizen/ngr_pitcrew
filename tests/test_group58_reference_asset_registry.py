"""Group 58 — reference-path asset registry foundation tests.

Proves the registry helpers list real shipped assets, summarise availability
honestly, and resolve a trusted lap length without inventing one.
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
    reference_path_asset_summary,
    resolve_trusted_lap_length,
)

FUJI_TRACK = "fuji_international_speedway"
FUJI_LAYOUT = "fuji_international_speedway__full_course"


def _v1(track, layout, n=5, lap=100.0):
    return {
        "schema_version": "reference_path_v1", "track_id": track, "layout_id": layout,
        "source": "approved_track_model", "lap_length_m": lap,
        "stations": [{"index": i, "x": i * 10.0, "y": 0.0, "z": 0.0,
                      "distance_along_lap_m": i * 10.0, "progress": i / (n - 1)}
                     for i in range(n)],
    }


class TestRegistry:
    def test_lists_real_shipped_assets(self):
        assets = list_available_reference_paths()
        ids = {(a["track_id"], a["layout_id"]) for a in assets}
        # The repo ships real Fuji + Daytona reference paths.
        assert any("fuji" in t for t, _l in ids)
        assert any("daytona" in t for t, _l in ids)
        for a in assets:
            assert a["station_count"] > 0

    def test_deterministic_order(self):
        a1 = list_available_reference_paths()
        a2 = list_available_reference_paths()
        assert [x["path"] for x in a1] == [x["path"] for x in a2]

    def test_scoped_search_root(self, tmp_path):
        (tmp_path / "t__t__lay.reference_path.json").write_text(
            json.dumps(_v1("t", "t__lay")), encoding="utf-8")
        assets = list_available_reference_paths(search_roots=[tmp_path])
        assert len(assets) == 1
        assert assets[0]["track_id"] == "t"


class TestSummary:
    def test_available_for_fuji(self):
        s = reference_path_asset_summary(FUJI_TRACK, FUJI_LAYOUT)
        assert s["available"] is True
        assert s["station_count"] > 0
        assert "available" in s["message"].lower()

    def test_unavailable_is_honest(self, tmp_path):
        s = reference_path_asset_summary("spa", "spa__gp", search_roots=[tmp_path])
        assert s["available"] is False
        assert "unavailable" in s["message"].lower()
        assert "road-distance fallback" in s["message"].lower()


class TestTrustedLapLength:
    def test_fuji_lap_length_from_asset(self):
        lap = resolve_trusted_lap_length(FUJI_TRACK, FUJI_LAYOUT)
        assert lap is not None and lap > 1000.0

    def test_missing_returns_none_not_invented(self, tmp_path):
        lap = resolve_trusted_lap_length("nope", "nope__x", search_roots=[tmp_path])
        assert lap is None

    def test_from_scoped_asset(self, tmp_path):
        (tmp_path / "t__t__lay.reference_path.json").write_text(
            json.dumps(_v1("t", "t__lay", lap=1234.0)), encoding="utf-8")
        lap = resolve_trusted_lap_length("t", "t__lay", search_roots=[tmp_path])
        assert lap == 1234.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
