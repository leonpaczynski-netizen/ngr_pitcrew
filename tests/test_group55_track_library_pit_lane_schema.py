"""Group 55 — track-library pit-lane schema (backward-compatible) tests.

Proves optional pit-lane metadata parses from a manifest / dedicated file, that
tracks WITHOUT pit-lane data remain valid (None), and that malformed data never
crashes the loader. Uses a temporary library dir — no production data added.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.track_library import (  # noqa: E402
    load_track_pit_lane,
    resolve_track_layout_manifest,
)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _layout_dir(base: Path, track_id: str, layout_id: str) -> Path:
    return base / "tracks" / track_id / "layouts" / layout_id


_PIT_LANE = {
    "available": True,
    "source": "track_library",
    "segments": [
        {"zone": "pit_entry", "start_progress": 0.935, "end_progress": 0.955, "label": "Pit entry"},
        {"zone": "pit_lane", "start_progress": 0.955, "end_progress": 0.985, "label": "Pit lane"},
        {"zone": "pit_exit", "start_progress": 0.985, "end_progress": 0.025, "label": "Pit exit"},
    ],
}


class TestManifestPitLane:
    def test_manifest_parses_inline_pit_lane(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "manifest.json", {
            "schema": "track_layout_manifest_v1", "track_id": "fuji", "layout_id": "full",
            "display_name": "Fuji Full", "lap_length_m": 4563.0, "pit_lane": _PIT_LANE,
        })
        m = resolve_track_layout_manifest("fuji", "full", base_dir=tmp_path)
        assert m is not None
        assert m.pit_lane.get("available") is True
        assert len(m.pit_lane["segments"]) == 3

    def test_manifest_without_pit_lane_is_empty_dict(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "manifest.json", {
            "schema": "track_layout_manifest_v1", "track_id": "fuji", "layout_id": "full",
            "display_name": "Fuji Full", "lap_length_m": 4563.0,
        })
        m = resolve_track_layout_manifest("fuji", "full", base_dir=tmp_path)
        assert m is not None
        assert m.pit_lane == {}   # backward compatible: absent → {}


class TestLoadTrackPitLane:
    def test_from_dedicated_file(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "pit_lane.json", _PIT_LANE)
        block = load_track_pit_lane("fuji", "full", base_dir=tmp_path)
        assert block is not None
        assert block["segments"][0]["zone"] == "pit_entry"

    def test_from_manifest_when_no_file(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "manifest.json", {
            "schema": "track_layout_manifest_v1", "track_id": "fuji", "layout_id": "full",
            "display_name": "Fuji Full", "lap_length_m": 4563.0, "pit_lane": _PIT_LANE,
        })
        block = load_track_pit_lane("fuji", "full", base_dir=tmp_path)
        assert block is not None
        assert len(block["segments"]) == 3

    def test_missing_returns_none(self, tmp_path):
        assert load_track_pit_lane("nope", "nope", base_dir=tmp_path) is None

    def test_malformed_file_never_crashes(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        ldir.mkdir(parents=True, exist_ok=True)
        (ldir / "pit_lane.json").write_text("{ this is not json", encoding="utf-8")
        # Should fall through gracefully (no manifest either) → None.
        assert load_track_pit_lane("fuji", "full", base_dir=tmp_path) is None

    def test_resolver_consumes_loaded_block(self, tmp_path):
        from data.pit_lane_resolver import resolve_pit_lane_from_track_context, PitLaneZone
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "pit_lane.json", _PIT_LANE)
        block = load_track_pit_lane("fuji", "full", base_dir=tmp_path)
        res = resolve_pit_lane_from_track_context(0.97, {"pit_lane": block})
        assert res.zone == PitLaneZone.PIT_LANE

    def test_real_daytona_has_no_pit_lane(self):
        # The only shipped library track must NOT be broken by Group 55 (no pit_lane).
        block = load_track_pit_lane("daytona_international_speedway", "road_course")
        assert block is None  # graceful — degrades to Group 54 behaviour


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
