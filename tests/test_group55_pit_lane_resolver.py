"""Group 55 — pure pit-lane resolver tests.

Covers progress normalisation, wrapped ranges, boundaries, invalid inputs,
missing / malformed mapping, the explicit-metadata requirement, and the rule that
a pit lane is NEVER inferred from ordinary racing segments.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.pit_lane_resolver import (  # noqa: E402
    PitLaneMappingConfidence,
    PitLaneResolution,
    PitLaneSegment,
    PitLaneZone,
    build_pit_lane_segments_from_track_context,
    normalise_progress,
    progress_in_wrapped_range,
    resolve_pit_lane_from_track_context,
    resolve_pit_lane_zone,
    segments_mapping_confidence,
)
from strategy.race_strategy_live_replan import fuji_pit_lane_mapping  # noqa: E402


@pytest.fixture()
def fuji_ctx():
    return fuji_pit_lane_mapping()


@pytest.fixture()
def fuji_segments(fuji_ctx):
    return build_pit_lane_segments_from_track_context(fuji_ctx)


# ---------------------------------------------------------------------------
# normalise_progress
# ---------------------------------------------------------------------------

class TestNormaliseProgress:
    def test_in_range(self):
        assert normalise_progress(0.0) == 0.0
        assert normalise_progress(0.5) == 0.5

    def test_wraps_at_one(self):
        assert normalise_progress(1.0) == 0.0
        assert abs(normalise_progress(1.25) - 0.25) < 1e-9

    def test_negative_wraps(self):
        assert abs(normalise_progress(-0.1) - 0.9) < 1e-9

    def test_none_and_garbage(self):
        assert normalise_progress(None) is None
        assert normalise_progress("abc") is None
        assert normalise_progress([1, 2]) is None

    def test_nan_and_inf(self):
        assert normalise_progress(float("nan")) is None
        assert normalise_progress(float("inf")) is None
        assert normalise_progress(float("-inf")) is None


# ---------------------------------------------------------------------------
# progress_in_wrapped_range
# ---------------------------------------------------------------------------

class TestWrappedRange:
    def test_normal_range(self):
        assert progress_in_wrapped_range(0.5, 0.4, 0.6)
        assert not progress_in_wrapped_range(0.7, 0.4, 0.6)

    def test_boundaries_inclusive(self):
        assert progress_in_wrapped_range(0.4, 0.4, 0.6)
        assert progress_in_wrapped_range(0.6, 0.4, 0.6)

    def test_wrapped_range_crossing_start(self):
        # 0.985 → 0.025 wraps the start/finish line.
        assert progress_in_wrapped_range(0.99, 0.985, 0.025)
        assert progress_in_wrapped_range(0.01, 0.985, 0.025)
        assert not progress_in_wrapped_range(0.5, 0.985, 0.025)

    def test_invalid_inputs_false(self):
        assert not progress_in_wrapped_range(None, 0.1, 0.2)
        assert not progress_in_wrapped_range(0.15, None, 0.2)

    def test_zero_width_never_matches(self):
        assert not progress_in_wrapped_range(0.5, 0.5, 0.5)


# ---------------------------------------------------------------------------
# resolve_pit_lane_zone
# ---------------------------------------------------------------------------

class TestResolveZone:
    def test_entry_body_exit(self, fuji_segments):
        assert resolve_pit_lane_zone(0.94, fuji_segments).zone == PitLaneZone.PIT_ENTRY
        assert resolve_pit_lane_zone(0.97, fuji_segments).zone == PitLaneZone.PIT_LANE

    def test_exit_wraps_line(self, fuji_segments):
        assert resolve_pit_lane_zone(0.99, fuji_segments).zone == PitLaneZone.PIT_EXIT
        assert resolve_pit_lane_zone(0.01, fuji_segments).zone == PitLaneZone.PIT_EXIT

    def test_on_track_is_not_pit_lane(self, fuji_segments):
        res = resolve_pit_lane_zone(0.5, fuji_segments)
        assert res.zone == PitLaneZone.NOT_PIT_LANE
        assert not res.is_inside_pit_lane

    def test_progress_unknown_is_unknown(self, fuji_segments):
        res = resolve_pit_lane_zone(None, fuji_segments)
        assert res.zone == PitLaneZone.UNKNOWN
        assert "progress" in res.message.lower()

    def test_no_segments_is_unknown(self):
        res = resolve_pit_lane_zone(0.5, [])
        assert res.zone == PitLaneZone.UNKNOWN
        assert res.confidence == PitLaneMappingConfidence.NONE

    def test_inside_flag(self, fuji_segments):
        assert resolve_pit_lane_zone(0.97, fuji_segments).is_inside_pit_lane
        assert not resolve_pit_lane_zone(0.5, fuji_segments).is_inside_pit_lane

    def test_narrowest_span_wins_on_overlap(self):
        segs = [
            PitLaneSegment(PitLaneZone.PIT_LANE, 0.90, 0.99),   # wide
            PitLaneSegment(PitLaneZone.PIT_ENTRY, 0.935, 0.945),  # narrow
        ]
        assert resolve_pit_lane_zone(0.94, segs).zone == PitLaneZone.PIT_ENTRY


# ---------------------------------------------------------------------------
# build_pit_lane_segments_from_track_context
# ---------------------------------------------------------------------------

class TestBuildSegments:
    def test_fuji_has_three(self, fuji_segments):
        assert len(fuji_segments) == 3
        assert {s.zone for s in fuji_segments} == {
            PitLaneZone.PIT_ENTRY, PitLaneZone.PIT_LANE, PitLaneZone.PIT_EXIT}

    def test_missing_mapping_returns_empty(self):
        assert build_pit_lane_segments_from_track_context(None) == []
        assert build_pit_lane_segments_from_track_context({}) == []
        assert build_pit_lane_segments_from_track_context({"pit_lane": {}}) == []

    def test_available_false_returns_empty(self):
        ctx = {"pit_lane": {"available": False, "segments": [
            {"zone": "pit_lane", "start_progress": 0.9, "end_progress": 0.99}]}}
        assert build_pit_lane_segments_from_track_context(ctx) == []

    def test_malformed_segments_skipped_not_crash(self):
        ctx = {"pit_lane": {"available": True, "segments": [
            "not-a-dict",
            {"zone": "unknown_zone", "start_progress": 0.1, "end_progress": 0.2},   # bad zone
            {"zone": "pit_lane", "start_progress": "x", "end_progress": 0.2},        # bad start
            {"zone": "pit_lane", "start_progress": 0.5, "end_progress": 0.5},        # zero width
            {"zone": "pit_lane", "start_progress": 0.9, "end_progress": 0.99},       # OK
        ]}}
        segs = build_pit_lane_segments_from_track_context(ctx)
        assert len(segs) == 1
        assert segs[0].zone == PitLaneZone.PIT_LANE

    def test_no_inference_from_racing_segments(self):
        # A track context carrying ONLY racing 'sectors'/'corners' yields no pit lane.
        ctx = {"sectors": [{"name": "S1", "start_progress": 0.0, "end_progress": 0.33}],
               "corners": [{"name": "T1", "lap_progress_start": 0.1}]}
        assert build_pit_lane_segments_from_track_context(ctx) == []
        assert resolve_pit_lane_from_track_context(0.2, ctx).zone == PitLaneZone.UNKNOWN

    def test_object_like_context(self):
        class Ctx:
            pit_lane = {"available": True, "segments": [
                {"zone": "pit_lane", "start_progress": 0.9, "end_progress": 0.99}]}
        segs = build_pit_lane_segments_from_track_context(Ctx())
        assert len(segs) == 1


class TestMappingConfidence:
    def test_track_library_is_medium(self, fuji_segments):
        assert segments_mapping_confidence(fuji_segments) == PitLaneMappingConfidence.MEDIUM

    def test_empty_is_none(self):
        assert segments_mapping_confidence([]) == PitLaneMappingConfidence.NONE

    def test_engineer_validated_is_high(self):
        ctx = {"pit_lane": {"available": True, "source": "engineer_validated", "segments": [
            {"zone": "pit_lane", "start_progress": 0.9, "end_progress": 0.99}]}}
        segs = build_pit_lane_segments_from_track_context(ctx)
        assert segments_mapping_confidence(segs) == PitLaneMappingConfidence.HIGH


class TestResolveFromContext:
    def test_attaches_ids(self, fuji_ctx):
        res = resolve_pit_lane_from_track_context(0.97, fuji_ctx)
        assert isinstance(res, PitLaneResolution)
        assert res.zone == PitLaneZone.PIT_LANE
        assert res.track_id == "fuji_speedway"
        assert res.layout_id == "full_course"

    def test_missing_context_unknown(self):
        assert resolve_pit_lane_from_track_context(0.5, None).zone == PitLaneZone.UNKNOWN


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
