"""Group 55 — live pit-lane adapter tests.

Proves ``apply_pit_lane_evidence`` combines Group 54 pit confidence with
pit-lane mapping correctly, and that the tracker path reads ``in_pit`` and never
fabricates a pit stop. Group 54 behaviour is preserved when mapping/progress
is missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_replan import RaceReplanState  # noqa: E402
from strategy.race_strategy_live_state import (  # noqa: E402
    CORR_CONTRADICTED,
    CORR_CORROBORATED,
    CORR_NO_MAPPING,
    CORR_POSITION_UNKNOWN,
    LiveReplanStateResult,
    apply_pit_lane_evidence,
    build_replan_state_from_tracker,
)
from strategy.race_strategy_live_replan import fuji_pit_lane_mapping  # noqa: E402


@pytest.fixture()
def ctx():
    return fuji_pit_lane_mapping()


def _result(conf, *, in_pit=False):
    return LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence=conf,
                                 pit_evidence_confidence=conf, pit_in_progress=in_pit)


class _Tracker:
    """Minimal RaceStateTracker-like object for the adapter."""
    def __init__(self, *, conf="MEDIUM", tyre_age=2, pit_stops=1, in_pit=False):
        self.laps_recorded = 12
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


# ---------------------------------------------------------------------------
# Group 54 preservation
# ---------------------------------------------------------------------------

class TestGroup54Preserved:
    def test_missing_track_context_unchanged(self):
        out = apply_pit_lane_evidence(_result("MEDIUM"), track_context=None, live_progress=0.97)
        assert out.pit_evidence_confidence == "MEDIUM"  # unchanged
        assert out.pit_corroboration == CORR_NO_MAPPING

    def test_missing_progress_unchanged(self, ctx):
        out = apply_pit_lane_evidence(_result("MEDIUM"), track_context=ctx, live_progress=None)
        assert out.pit_evidence_confidence == "MEDIUM"
        assert out.pit_corroboration == CORR_POSITION_UNKNOWN

    def test_does_not_touch_pit_count_or_tyre_age(self, ctx):
        base = LiveReplanStateResult(
            state=RaceReplanState(pit_stops_completed=1, tyre_age_laps=2),
            pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(base, track_context=ctx, live_progress=0.97)
        # Pit count / tyre age come solely from Group 54 — never mutated here.
        assert out.state.pit_stops_completed == 1
        assert out.state.tyre_age_laps == 2


# ---------------------------------------------------------------------------
# Corroboration + upgrades
# ---------------------------------------------------------------------------

class TestCorroboration:
    def test_pit_lane_body_detected(self, ctx):
        out = apply_pit_lane_evidence(_result("HIGH"), track_context=ctx, live_progress=0.97)
        assert out.pit_lane_zone == "PIT_LANE"
        assert out.pit_lane_source  # provenance surfaced

    def test_refuel_pit_upgrades_to_high(self, ctx):
        out = apply_pit_lane_evidence(_result("MEDIUM"), track_context=ctx, live_progress=0.94)
        assert out.pit_evidence_confidence == "HIGH"
        assert out.pit_corroboration == CORR_CORROBORATED

    def test_speed_only_pit_upgrades_to_medium_at_most(self, ctx):
        out = apply_pit_lane_evidence(_result("LOW"), track_context=ctx, live_progress=0.97)
        assert out.pit_evidence_confidence == "MEDIUM"  # NOT high
        assert out.pit_corroboration == CORR_CORROBORATED
        assert any("above MEDIUM" in w for w in out.warnings)

    def test_low_confidence_map_cannot_certify_high(self):
        weak = {"pit_lane": {"available": True, "source": "estimated", "segments": [
            {"zone": "pit_lane", "start_progress": 0.9, "end_progress": 0.99}]}}
        out = apply_pit_lane_evidence(_result("MEDIUM"), track_context=weak, live_progress=0.95)
        assert out.pit_evidence_confidence == "MEDIUM"  # capped, not HIGH
        assert out.pit_lane_mapping_confidence == "LOW"

    def test_contradiction_when_in_pit_but_on_track(self, ctx):
        out = apply_pit_lane_evidence(_result("MEDIUM", in_pit=True),
                                      track_context=ctx, live_progress=0.5)
        assert out.pit_corroboration == CORR_CONTRADICTED
        assert out.pit_evidence_confidence == "MEDIUM"  # NOT upgraded
        assert any("did not match" in w for w in out.warnings)

    def test_on_track_not_in_pit_is_not_contradiction(self, ctx):
        # Car simply on track, not currently pitting — no contradiction warning.
        out = apply_pit_lane_evidence(_result("MEDIUM", in_pit=False),
                                      track_context=ctx, live_progress=0.5)
        assert out.pit_corroboration != CORR_CONTRADICTED
        assert not any("did not match" in w for w in out.warnings)


# ---------------------------------------------------------------------------
# Tracker path
# ---------------------------------------------------------------------------

class TestTrackerPath:
    def test_reads_in_pit_flag(self):
        res = build_replan_state_from_tracker(_Tracker(in_pit=True), packet=_Packet())
        assert res.pit_in_progress is True

    def test_default_not_in_pit(self):
        res = build_replan_state_from_tracker(_Tracker(in_pit=False), packet=_Packet())
        assert res.pit_in_progress is False

    def test_tracker_then_corroborate(self):
        res = build_replan_state_from_tracker(_Tracker(conf="MEDIUM"), packet=_Packet())
        out = apply_pit_lane_evidence(res, track_context=fuji_pit_lane_mapping(),
                                      live_progress=0.97)
        assert out.pit_evidence_confidence == "HIGH"

    def test_real_tracker_exposes_in_pit_property(self):
        # The real tracker must expose the read-only in_pit property (default False).
        import queue
        from telemetry.state import RaceStateTracker, TyreThresholds
        tr = RaceStateTracker(queue.PriorityQueue(), TyreThresholds())
        assert tr.in_pit is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
