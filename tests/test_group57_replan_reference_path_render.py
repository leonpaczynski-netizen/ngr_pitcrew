"""Group 57 — live replan reference-path render tests.

Proves the loaded reference path appears in Found lines, missing/malformed paths
appear honestly in Missing/Warnings, and no command wording ever appears.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from data.reference_path_loader import (  # noqa: E402
    load_reference_path_for_layout,
    reference_path_to_track_stations,
)
from strategy.race_strategy_live_replan import (  # noqa: E402
    build_live_replan_snapshot,
    render_live_replan_text,
    fuji_pit_lane_mapping,
    fuji_live_state_pre_pit_healthy,
)


FUJI_TRACK = "fuji_international_speedway"
FUJI_LAYOUT = "fuji_international_speedway__full_course"


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


@pytest.fixture(scope="module")
def fuji():
    res = load_reference_path_for_layout(FUJI_TRACK, FUJI_LAYOUT)
    return res, reference_path_to_track_stations(res.asset)


def _pos(asset, i):
    p = asset.stations[i]
    return (p["x"], p["y"], p["z"], 200.0)


class TestFoundLines:
    def test_reference_path_loaded_appears(self, pre_race, fuji):
        res, stations = fuji
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=_pos(res.asset, 100), reference_stations=stations,
            reference_path_source=res.source, reference_path_warnings=res.warnings)
        text = render_live_replan_text(r)
        assert "reference path: loaded" in text
        assert "track progress" in text
        assert "position match" in text


class TestMissingLines:
    def test_missing_path_shows_unavailable(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=(0.0, 0.0, 0.0), reference_stations=None,
            reference_path_source="", reference_path_warnings=())
        text = render_live_replan_text(r)
        # No reference path loaded → progress unavailable degrades honestly.
        assert "reference path: loaded" not in text

    def test_no_stations_warning_surfaced(self, pre_race, fuji):
        _res, stations = fuji
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=(0.0, 0.0, 0.0), reference_stations=None,
            reference_path_source="",
            reference_path_warnings=("reference path has no usable stations",))
        text = render_live_replan_text(r)
        assert "reference path has no usable stations" in text


class TestWarnings:
    def test_mismatch_warning_surfaced(self, pre_race, fuji):
        res, stations = fuji
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=_pos(res.asset, 100), reference_stations=stations,
            identity_ok=False, reference_path_source=res.source,
            reference_path_warnings=("reference path track/layout mismatch",))
        text = render_live_replan_text(r)
        assert "Warning:" in text
        assert "track/layout mismatch" in text


class TestNoCommandWording:
    def test_no_pit_now(self, pre_race, fuji):
        res, stations = fuji
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=_pos(res.asset, 190), reference_stations=stations,
            reference_path_source=res.source)
        text = render_live_replan_text(r).lower()
        for banned in ("pit now", "box now", "box box", "come in", "make the call"):
            assert banned not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
