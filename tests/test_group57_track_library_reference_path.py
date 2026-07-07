"""Group 57 — track-library reference-path metadata (backward-compatible) tests.

Proves the optional manifest ``reference_path`` block parses, older manifests
without it still parse, and the loader returns None safely when absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.track_library import (  # noqa: E402
    load_track_reference_path,
    resolve_track_layout_manifest,
)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _layout_dir(base: Path, track_id: str, layout_id: str) -> Path:
    return base / "tracks" / track_id / "layouts" / layout_id


_REF_BLOCK = {
    "available": True,
    "file": "reference_path.json",
    "source": "approved_track_model",
    "notes": "Approved reference path used for live progress matching.",
}


class TestManifestReferencePath:
    def test_parses_inline_block(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "manifest.json", {
            "schema": "track_layout_manifest_v1", "track_id": "fuji", "layout_id": "full",
            "display_name": "Fuji Full", "lap_length_m": 4563.0, "reference_path": _REF_BLOCK,
        })
        m = resolve_track_layout_manifest("fuji", "full", base_dir=tmp_path)
        assert m is not None
        assert m.reference_path.get("available") is True
        assert m.reference_path.get("file") == "reference_path.json"

    def test_older_manifest_without_block(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "manifest.json", {
            "schema": "track_layout_manifest_v1", "track_id": "fuji", "layout_id": "full",
            "display_name": "Fuji Full", "lap_length_m": 4563.0,
        })
        m = resolve_track_layout_manifest("fuji", "full", base_dir=tmp_path)
        assert m is not None
        assert m.reference_path == {}     # backward compatible

    def test_pit_lane_and_reference_path_coexist(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "manifest.json", {
            "schema": "track_layout_manifest_v1", "track_id": "fuji", "layout_id": "full",
            "display_name": "Fuji Full", "lap_length_m": 4563.0,
            "reference_path": _REF_BLOCK,
            "pit_lane": {"available": True, "segments": [
                {"zone": "pit_lane", "start_progress": 0.9, "end_progress": 0.99}]},
        })
        m = resolve_track_layout_manifest("fuji", "full", base_dir=tmp_path)
        assert m.reference_path.get("available") is True
        assert m.pit_lane.get("available") is True


class TestLoadTrackReferencePath:
    def test_returns_block(self, tmp_path):
        ldir = _layout_dir(tmp_path, "fuji", "full")
        _write(ldir / "manifest.json", {
            "schema": "track_layout_manifest_v1", "track_id": "fuji", "layout_id": "full",
            "display_name": "Fuji Full", "lap_length_m": 4563.0, "reference_path": _REF_BLOCK,
        })
        block = load_track_reference_path("fuji", "full", base_dir=tmp_path)
        assert block is not None
        assert block["source"] == "approved_track_model"

    def test_missing_returns_none(self, tmp_path):
        assert load_track_reference_path("nope", "nope", base_dir=tmp_path) is None

    def test_daytona_real_library_no_reference_path_block(self):
        # The shipped Daytona library entry has no reference_path manifest block —
        # that is fine (the real path lives in data/track_models/), and must be safe.
        block = load_track_reference_path(
            "daytona_international_speedway", "daytona_international_speedway__road_course")
        assert block is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
