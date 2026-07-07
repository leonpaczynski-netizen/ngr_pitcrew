"""Group 55 — live replan pit-confidence integration + rendering tests.

Proves the full ``build_live_replan_snapshot`` path corroborates pit evidence via
pit-lane mapping, keeps the OVERALL replan confidence capped (never HIGH from
proxy tyre/pace evidence), and renders the pit-lane evidence honestly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from strategy.race_strategy_replan import ReplanConfidence  # noqa: E402
from strategy.race_strategy_live_replan import (  # noqa: E402
    build_live_replan_snapshot,
    fuji_pit_lane_mapping,
    render_live_replan_text,
)


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


@pytest.fixture()
def ctx():
    return fuji_pit_lane_mapping()


class _Tracker:
    def __init__(self, *, conf="MEDIUM", tyre_age=2, pit_stops=1, in_pit=False):
        self.laps_recorded = 18
        self.laps_remaining = 0
        self._current_compound = "RM"
        self.avg_fuel_per_lap = 4.0
        self.timed_duration_minutes = 50.0
        self.pit_state_confidence = conf
        self.tyre_age_laps = tyre_age
        self.pit_stops_completed = pit_stops
        self.in_pit = in_pit

    def computed_remaining_ms(self):
        return 1800000


class _Packet:
    fuel_level = 60.0
    fuel_capacity = 100.0


def _snap(pre_race, tracker, *, ctx=None, progress=None):
    return build_live_replan_snapshot(
        pre_race_result=pre_race, live_source=tracker,
        track_context=ctx, live_progress=progress)


class TestPitEvidenceUpgrade:
    def test_refuel_pit_in_lane_reaches_high_evidence(self, pre_race, ctx):
        r = _snap(pre_race, _Tracker(conf="MEDIUM"), ctx=ctx, progress=0.94)
        assert r.pit_evidence_confidence == "HIGH"
        assert r.pit_corroboration == "corroborated"

    def test_speed_only_pit_capped_at_medium(self, pre_race, ctx):
        r = _snap(pre_race, _Tracker(conf="LOW"), ctx=ctx, progress=0.97)
        assert r.pit_evidence_confidence == "MEDIUM"

    def test_no_mapping_preserves_group54(self, pre_race):
        r = _snap(pre_race, _Tracker(conf="MEDIUM"), ctx=None, progress=0.97)
        assert r.pit_evidence_confidence == "MEDIUM"  # unchanged
        assert r.pit_corroboration == "no_mapping"


class TestOverallConfidenceCap:
    def test_overall_never_forced_high(self, pre_race, ctx):
        # Even with a HIGH pit-evidence signal, the OVERALL replan confidence
        # obeys the existing cap (MEDIUM at best for a live snapshot).
        r = _snap(pre_race, _Tracker(conf="MEDIUM", tyre_age=2, pit_stops=1),
                  ctx=ctx, progress=0.94)
        assert r.pit_evidence_confidence == "HIGH"
        assert r.confidence in (ReplanConfidence.MEDIUM, ReplanConfidence.LOW,
                                ReplanConfidence.INSUFFICIENT_EVIDENCE)
        assert r.confidence != getattr(ReplanConfidence, "HIGH", object())


class TestRendering:
    def test_render_shows_zone_and_corroboration(self, pre_race, ctx):
        r = _snap(pre_race, _Tracker(conf="MEDIUM"), ctx=ctx, progress=0.94)
        text = render_live_replan_text(r)
        assert "pit lane zone" in text
        assert "corroborated by pit-lane map" in text
        assert "pit confidence: high" in text

    def test_render_shows_missing_map(self, pre_race):
        r = _snap(pre_race, _Tracker(conf="MEDIUM"), ctx=None, progress=0.97)
        text = render_live_replan_text(r)
        assert "pit-lane map unavailable" in text

    def test_render_shows_missing_progress(self, pre_race, ctx):
        r = _snap(pre_race, _Tracker(conf="MEDIUM"), ctx=ctx, progress=None)
        text = render_live_replan_text(r)
        assert "live track progress unavailable" in text

    def test_render_shows_contradiction_warning(self, pre_race, ctx):
        r = _snap(pre_race, _Tracker(conf="MEDIUM", in_pit=True), ctx=ctx, progress=0.5)
        text = render_live_replan_text(r)
        assert "did not match pit-lane mapping" in text

    def test_render_never_says_pit_now(self, pre_race, ctx):
        r = _snap(pre_race, _Tracker(conf="MEDIUM"), ctx=ctx, progress=0.94)
        text = render_live_replan_text(r).lower()
        assert "pit now" not in text
        assert "box now" not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
