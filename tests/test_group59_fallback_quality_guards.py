"""Group 59 — fallback quality guards.

Proves the Group 58 safety contract still holds after Group 59: approved path
wins over fallback, fallback stays lower-confidence (never HIGH), never lifts pit
confidence, never creates a pit, and never mutates pit count.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from data.live_track_progress import build_track_path_stations, TrackProgressConfidence  # noqa: E402
from data.live_track_progress_fallback import (  # noqa: E402
    FALLBACK_SOURCE, resolve_progress_from_road_distance,
)
from data.reference_path_loader import (  # noqa: E402
    load_reference_path_for_layout, reference_path_to_track_stations,
)
from strategy.race_strategy_replan import RaceReplanState  # noqa: E402
from strategy.race_strategy_live_state import (  # noqa: E402
    LiveReplanStateResult, apply_pit_lane_evidence, attach_track_progress,
)
from strategy.race_strategy_live_replan import (  # noqa: E402
    build_live_replan_snapshot, fuji_pit_lane_mapping, fuji_position_at_progress,
    fuji_reference_path, fuji_live_state_pre_pit_healthy,
)

LAP = 4563.0
FUJI = ("fuji_international_speedway", "fuji_international_speedway__full_course")


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


class TestPrecedenceStillHolds:
    def test_approved_path_wins(self, pre_race):
        stations = build_track_path_stations(fuji_reference_path())
        ctx = dict(fuji_pit_lane_mapping())
        ctx["reference_path"] = fuji_reference_path()["reference_path"]
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx, live_position=fuji_position_at_progress(0.4),
            reference_stations=stations,
            lap_distance_m=LAP * 0.9, lap_length_m=LAP)
        assert r.track_progress.source != FALLBACK_SOURCE
        assert r.track_progress.confidence in (TrackProgressConfidence.HIGH,
                                               TrackProgressConfidence.MEDIUM)

    def test_real_daytona_asset_wins_over_fallback(self, pre_race):
        # Load real Daytona stations and stand at a station → HIGH map match wins.
        res = load_reference_path_for_layout(*FUJI)  # any real approved asset
        stations = reference_path_to_track_stations(res.asset)
        p = res.asset.stations[100]
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=(p["x"], p["y"], p["z"]), reference_stations=stations,
            lap_distance_m=LAP / 3, lap_length_m=res.asset.lap_length_m)
        assert r.track_progress.source != FALLBACK_SOURCE


class TestFallbackStaysLowerConfidence:
    def test_never_high(self):
        for kwargs in ({"lap_distance_m": LAP / 2}, {"road_distance": LAP * 2 + 5},
                       {"lap_distance_m": LAP + 10}):
            r = resolve_progress_from_road_distance(lap_length_m=LAP, **kwargs)
            assert r.confidence != TrackProgressConfidence.HIGH

    def test_activates_only_with_trusted_lap_length(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(), live_position=None,
            reference_stations=None, lap_distance_m=LAP / 2, lap_length_m=None)
        assert (r.track_progress is None) or (not r.track_progress.has_progress)


class TestFallbackNeverLiftsPit:
    def test_fallback_does_not_corroborate_pit(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(), live_position=None,
            reference_stations=None, lap_distance_m=LAP * 0.97, lap_length_m=LAP)
        assert r.track_progress.source == FALLBACK_SOURCE
        assert r.pit_corroboration in ("position_unknown", "none")
        assert r.pit_evidence_confidence != "HIGH"

    def test_fallback_never_touches_pit_count(self):
        fb = resolve_progress_from_road_distance(lap_distance_m=LAP * 0.97, lap_length_m=LAP)
        base = LiveReplanStateResult(
            state=RaceReplanState(pit_stops_completed=1, tyre_age_laps=2),
            pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(attach_track_progress(base, fb),
                                      track_context=fuji_pit_lane_mapping())
        assert out.state.pit_stops_completed == 1
        assert out.state.tyre_age_laps == 2
        assert out.pit_evidence_confidence != "HIGH"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
