"""Group 56 — live replan snapshot progress integration + rendering tests.

Proves the full ``build_live_replan_snapshot`` path resolves live position into
track progress, surfaces it in the rendered text, and keeps the overall replan
confidence unchanged (progress is supporting evidence, not a strategy author).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from strategy.race_strategy_replan import ReplanConfidence  # noqa: E402
from data.live_track_progress import TrackProgressConfidence  # noqa: E402
from strategy.race_strategy_live_replan import (  # noqa: E402
    build_live_replan_snapshot,
    render_live_replan_text,
    fuji_pit_lane_mapping,
    fuji_position_at_progress,
    fuji_reference_path,
)


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


@pytest.fixture()
def ctx():
    c = dict(fuji_pit_lane_mapping())
    c["reference_path"] = fuji_reference_path()["reference_path"]
    return c


class _Tracker:
    """Minimal tracker exposing live_world_position + Group 54 pit state."""
    def __init__(self, *, progress=0.5, conf="MEDIUM", in_pit=False):
        self.laps_recorded = 18
        self.laps_remaining = 0
        self._current_compound = "RM"
        self.avg_fuel_per_lap = 4.0
        self.timed_duration_minutes = 50.0
        self.pit_state_confidence = conf
        self.tyre_age_laps = 2
        self.pit_stops_completed = 1
        self.in_pit = in_pit
        x, _y, z = fuji_position_at_progress(progress)
        self.live_world_position = (x, 0.0, z, 200.0)

    def computed_remaining_ms(self):
        return 1800000


class _Packet:
    fuel_level = 60.0
    fuel_capacity = 100.0


class TestProgressAppears:
    def test_snapshot_carries_progress(self, pre_race, ctx):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_source=_Tracker(progress=0.5),
            track_context=ctx)
        assert r.track_progress is not None
        assert r.track_progress.confidence in (
            TrackProgressConfidence.HIGH, TrackProgressConfidence.MEDIUM)
        assert abs(r.track_progress.progress - 0.5) < 0.02

    def test_render_shows_progress_lines(self, pre_race, ctx):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_source=_Tracker(progress=0.5),
            track_context=ctx)
        text = render_live_replan_text(r)
        assert "track progress" in text
        assert "distance along lap" in text
        assert "position match" in text

    def test_progress_in_pit_lane_corroborates(self, pre_race, ctx):
        # Position at 0.97 = inside pit-lane body; refuel pit (MEDIUM) → HIGH evidence.
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_source=_Tracker(progress=0.97, conf="MEDIUM"),
            track_context=ctx)
        assert r.pit_lane_zone == "PIT_LANE"
        assert r.pit_evidence_confidence == "HIGH"
        text = render_live_replan_text(r)
        assert "pit-lane map used live track progress" in text


class TestGracefulDegrade:
    def test_no_position_falls_back(self, pre_race, ctx):
        class NoPos(_Tracker):
            def __init__(self):
                super().__init__()
                self.live_world_position = None
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_source=NoPos(), track_context=ctx)
        assert r.track_progress is None or not r.track_progress.has_progress
        text = render_live_replan_text(r)
        assert "live world position unavailable" in text or "track progress unavailable" in text

    def test_no_reference_path_falls_back(self, pre_race):
        # Only pit-lane mapping, no reference path → no progress resolution.
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_source=_Tracker(progress=0.5),
            track_context=fuji_pit_lane_mapping())
        assert r.track_progress is None


class TestOverallConfidenceUnchanged:
    def test_progress_does_not_force_overall_high(self, pre_race, ctx):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_source=_Tracker(progress=0.97, conf="MEDIUM"),
            track_context=ctx)
        assert r.confidence in (ReplanConfidence.MEDIUM, ReplanConfidence.LOW,
                                ReplanConfidence.INSUFFICIENT_EVIDENCE)
        assert r.confidence != getattr(ReplanConfidence, "HIGH", object())


class TestNoCommandWording:
    def test_render_never_says_pit_now(self, pre_race, ctx):
        r = build_live_replan_snapshot(
            pre_race_result=pre_race, live_source=_Tracker(progress=0.97),
            track_context=ctx)
        text = render_live_replan_text(r).lower()
        for banned in ("pit now", "box now", "box box", "come in"):
            assert banned not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
