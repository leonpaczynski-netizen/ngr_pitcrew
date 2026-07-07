"""Group 58 — live replan fallback render tests.

Proves fallback progress is clearly labelled approximate / lower confidence, the
approved-path state is distinguished from fallback, and no command wording appears.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from data.live_track_progress import build_track_path_stations  # noqa: E402
from strategy.race_strategy_live_replan import (  # noqa: E402
    build_live_replan_snapshot,
    render_live_replan_text,
    fuji_pit_lane_mapping,
    fuji_position_at_progress,
    fuji_reference_path,
    fuji_live_state_pre_pit_healthy,
)

LAP = 4563.0


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


class TestFallbackRender:
    def test_fallback_labelled_approximate(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=None, reference_stations=None,
            lap_distance_m=LAP / 2, lap_length_m=LAP)
        text = render_live_replan_text(r)
        assert "via GT7 road-distance fallback" in text
        assert "approximate and lower confidence than map matching" in text
        assert "approved reference path unavailable" in text
        # Never implies certainty.
        assert "via approved reference path" not in text

    def test_approved_path_not_labelled_fallback(self, pre_race):
        stations = build_track_path_stations(fuji_reference_path())
        ctx = dict(fuji_pit_lane_mapping())
        ctx["reference_path"] = fuji_reference_path()["reference_path"]
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx, live_position=fuji_position_at_progress(0.4),
            reference_stations=stations)
        text = render_live_replan_text(r)
        assert "road-distance fallback" not in text
        assert "track progress" in text

    def test_no_progress_at_all(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=None, reference_stations=None,
            lap_distance_m=None, road_distance=None, lap_length_m=None)
        text = render_live_replan_text(r)
        assert "road-distance fallback" not in text

    def test_no_command_wording(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=None, reference_stations=None,
            lap_distance_m=LAP / 2, lap_length_m=LAP)
        text = render_live_replan_text(r).lower()
        for banned in ("pit now", "box now", "box box", "come in", "make the call"):
            assert banned not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
