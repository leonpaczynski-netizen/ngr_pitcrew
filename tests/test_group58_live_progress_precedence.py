"""Group 58 — live progress precedence tests.

Proves approved reference-path map matching wins over the road-distance fallback,
the fallback activates only when the primary is unusable, and fallback progress
never lifts pit confidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from data.live_track_progress import build_track_path_stations, TrackProgressConfidence  # noqa: E402
from data.live_track_progress_fallback import FALLBACK_SOURCE  # noqa: E402
from strategy.race_strategy_live_replan import (  # noqa: E402
    build_live_replan_snapshot,
    fuji_pit_lane_mapping,
    fuji_position_at_progress,
    fuji_reference_path,
    fuji_live_state_pre_pit_healthy,
)

LAP = 4563.0


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


@pytest.fixture()
def ctx():
    c = dict(fuji_pit_lane_mapping())
    c["reference_path"] = fuji_reference_path()["reference_path"]
    return c


@pytest.fixture()
def stations():
    return build_track_path_stations(fuji_reference_path())


class TestPrecedence:
    def test_approved_path_wins_over_fallback(self, pre_race, ctx, stations):
        # Usable map match (HIGH) must win even when fallback inputs are present.
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx, live_position=fuji_position_at_progress(0.40),
            reference_stations=stations,
            lap_distance_m=LAP * 0.9, road_distance=LAP * 0.9, lap_length_m=LAP)
        assert r.track_progress.source != FALLBACK_SOURCE
        assert r.track_progress.confidence in (TrackProgressConfidence.HIGH,
                                               TrackProgressConfidence.MEDIUM)

    def test_fallback_activates_when_no_approved_path(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),   # pit-lane only, no reference path
            live_position=None, reference_stations=None,
            lap_distance_m=LAP / 2, lap_length_m=LAP)
        assert r.track_progress.source == FALLBACK_SOURCE
        assert r.track_progress.confidence == TrackProgressConfidence.MEDIUM

    def test_fallback_not_activated_on_invalid_road_distance(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=None, reference_stations=None,
            lap_distance_m=float("nan"), road_distance=-10.0, lap_length_m=LAP)
        # No usable progress at all.
        assert (r.track_progress is None) or (not r.track_progress.has_progress)

    def test_fallback_not_activated_without_lap_length(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=None, reference_stations=None,
            lap_distance_m=LAP / 2, lap_length_m=None)
        assert (r.track_progress is None) or (not r.track_progress.has_progress)

    def test_unusable_primary_falls_back(self, pre_race, ctx, stations):
        # Live position far off the path (LOW/UNKNOWN map match) → fallback used.
        near = fuji_position_at_progress(0.5)
        far = (near[0] + 500.0, near[1], near[2])   # way off the reference circle
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx, live_position=far, reference_stations=stations,
            lap_distance_m=LAP / 4, lap_length_m=LAP)
        assert r.track_progress.source == FALLBACK_SOURCE


class TestFallbackNeverLiftsPit:
    def test_fallback_progress_does_not_corroborate_pit(self, pre_race):
        # Fallback progress near the pit-lane body must NOT corroborate a refuel pit.
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=None, reference_stations=None,
            lap_distance_m=LAP * 0.97, lap_length_m=LAP)
        assert r.track_progress.source == FALLBACK_SOURCE
        # Pit was not corroborated by the fallback position.
        assert r.pit_corroboration in ("position_unknown", "none")
        assert r.pit_evidence_confidence != "HIGH"

    def test_fallback_never_high_confidence(self, pre_race):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=fuji_pit_lane_mapping(),
            live_position=None, reference_stations=None,
            lap_distance_m=LAP / 3, lap_length_m=LAP)
        assert r.track_progress.confidence != TrackProgressConfidence.HIGH


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
