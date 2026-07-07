"""Group 56 — track-progress adapter tests.

Proves the strategy-layer adapter resolves live progress from position + path,
the tracker exposes a read-only live world position, and Group 55 fallback is
preserved when position or path is missing.
"""
from __future__ import annotations

import queue
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import TrackProgressConfidence  # noqa: E402
from strategy.race_strategy_replan import RaceReplanState  # noqa: E402
from strategy.race_strategy_live_state import (  # noqa: E402
    LiveReplanStateResult,
    apply_pit_lane_evidence,
    attach_track_progress,
    resolve_live_progress_evidence,
)
from strategy.race_strategy_live_replan import (  # noqa: E402
    fuji_pit_lane_mapping,
    fuji_position_at_progress,
    fuji_reference_path,
)


@pytest.fixture()
def ctx():
    c = dict(fuji_pit_lane_mapping())
    c["reference_path"] = fuji_reference_path()["reference_path"]
    return c


class TestResolveEvidence:
    def test_valid_position_produces_progress(self, ctx):
        pos = fuji_position_at_progress(0.42)
        r = resolve_live_progress_evidence(position=pos, track_context=ctx)
        assert r.confidence in (TrackProgressConfidence.HIGH, TrackProgressConfidence.MEDIUM)
        assert abs(r.progress - 0.42) < 0.02
        assert r.track_id == "fuji_speedway"

    def test_missing_position_unknown(self, ctx):
        r = resolve_live_progress_evidence(position=None, track_context=ctx)
        assert r.confidence == TrackProgressConfidence.UNKNOWN

    def test_missing_path_unknown(self):
        pos = fuji_position_at_progress(0.42)
        r = resolve_live_progress_evidence(position=pos, track_context={"track_id": "x"})
        assert r.confidence == TrackProgressConfidence.UNKNOWN

    def test_identity_mismatch_warns(self, ctx):
        pos = fuji_position_at_progress(0.42)
        r = resolve_live_progress_evidence(position=pos, track_context=ctx, identity_ok=False)
        assert r.confidence == TrackProgressConfidence.LOW
        assert any("does not match" in w for w in r.warnings)


class TestTrackerLiveWorldPosition:
    def test_property_default_none(self):
        from telemetry.state import RaceStateTracker, TyreThresholds
        tr = RaceStateTracker(queue.PriorityQueue(), TyreThresholds())
        assert tr.live_world_position is None

    def test_property_reads_last_packet(self):
        from telemetry.state import RaceStateTracker, TyreThresholds
        tr = RaceStateTracker(queue.PriorityQueue(), TyreThresholds())

        class P:
            pos_x, pos_y, pos_z = 12.0, 3.0, -4.0
            speed_kmh = 180.0
        tr._prev = P()
        pos = tr.live_world_position
        assert pos == (12.0, 3.0, -4.0, 180.0)


class TestGroup55FallbackPreserved:
    def test_no_track_progress_behaves_like_group55(self, ctx):
        # Without an attached track progress, an explicit None progress → position_unknown.
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(base, track_context=ctx, live_progress=None)
        assert out.pit_corroboration == "position_unknown"
        assert out.pit_evidence_confidence == "MEDIUM"  # unchanged

    def test_low_progress_not_used(self, ctx):
        # A far-off (LOW) progress must NOT feed the pit-lane resolver.
        far = (fuji_position_at_progress(0.97)[0] + 40.0, 0.0,
               fuji_position_at_progress(0.97)[2])
        prog = resolve_live_progress_evidence(position=far, track_context=ctx)
        assert prog.confidence == TrackProgressConfidence.LOW
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        res = attach_track_progress(base, prog)
        out = apply_pit_lane_evidence(res, track_context=ctx, live_progress=None)
        assert out.pit_corroboration == "position_unknown"  # progress not used
        assert out.pit_evidence_confidence == "MEDIUM"

    def test_medium_high_progress_feeds_resolver(self, ctx):
        pos = fuji_position_at_progress(0.97)  # inside the pit-lane body
        prog = resolve_live_progress_evidence(position=pos, track_context=ctx)
        assert prog.usable_for_pit
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        res = attach_track_progress(base, prog)
        out = apply_pit_lane_evidence(res, track_context=ctx, live_progress=None)
        assert out.pit_lane_zone == "PIT_LANE"
        assert out.pit_evidence_confidence == "HIGH"
        assert out.pit_corroboration == "corroborated"

    def test_explicit_progress_overrides_attached(self, ctx):
        # An explicit live_progress wins over an attached (even usable) track progress.
        pos = fuji_position_at_progress(0.5)  # on track, NOT_PIT_LANE
        prog = resolve_live_progress_evidence(position=pos, track_context=ctx)
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        res = attach_track_progress(base, prog)
        out = apply_pit_lane_evidence(res, track_context=ctx, live_progress=0.97)
        assert out.pit_lane_zone == "PIT_LANE"  # used the explicit 0.97, not 0.5


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
