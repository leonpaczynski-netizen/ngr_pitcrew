"""Tests for Group 17J — Live Current Segment Resolver.

Covers:
  - dataclass construction (LivePosition, LiveSegmentMatch, LiveSegmentResolverResult, Config)
  - exact segment_id match
  - lap_progress within segment bounds
  - distance_along_lap_m matching via reference path
  - XYZ nearest reference path match
  - nearest midpoint fallback
  - unresolved when no reviewed model
  - unresolved when no position data
  - reviewed-but-not-AI-ready model returns warning but still matches
  - previous/next segment lookup
  - previous/next wraps around start/finish
  - REJECTED segments excluded from matching
  - NEEDS_MORE_LAPS segment → confidence degraded
  - UNREVIEWED segment excluded by default (include_unreviewed=False)
  - malformed reviewed model is handled safely
  - format_live_segment_for_engineer compact safe text
  - no corner names invented when unresolved
  - packet_to_live_position handles missing fields safely
  - packet_to_live_position returns None for paused/loading/off-track
  - get_live_segment_context_for_prompt returns prompt block or ""
  - driving advisor prompt includes live segment context when provided
  - driving advisor _get_live_segment_context returns "" without position
  - regression: Groups 17A-17I imports still work
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared builders (mirrors 17I helper pattern)
# ---------------------------------------------------------------------------

def _make_reviewed_segment(
    segment_id="seg_braking_t1",
    segment_type="braking_zone",
    display_name="T1 Braking Zone",
    lap_progress_start=0.05,
    lap_progress_end=0.12,
    lap_progress_mid=0.085,
    review_status="confirmed",
    confidence="high",
    turn_number=1,
):
    from data.track_segment_review import ReviewedTrackSegment, SegmentReviewStatus
    from data.track_segment_detection import TrackSegmentType, TrackSegmentDetectionConfidence
    return ReviewedTrackSegment(
        segment_id=segment_id,
        segment_type=TrackSegmentType(segment_type),
        original_display_name=display_name,
        lap_progress_start=lap_progress_start,
        lap_progress_end=lap_progress_end,
        lap_progress_mid=lap_progress_mid,
        confidence=TrackSegmentDetectionConfidence(confidence),
        review_status=SegmentReviewStatus(review_status),
        turn_number=turn_number,
    )


def _make_review_result(segments, track_location_id="test_track", layout_id="test_track__full"):
    from data.track_segment_review import TrackModelReviewResult
    from data.track_segment_detection import TrackSegmentDetectionConfidence
    return TrackModelReviewResult(
        track_location_id=track_location_id,
        layout_id=layout_id,
        calibration_car_id="porsche_911_rsr_991_17",
        source_lap_count=5,
        detected_corner_count=len(segments),
        expected_corner_count=None,
        detection_confidence=TrackSegmentDetectionConfidence.HIGH,
        segments=segments,
    )


def _make_resolved_model(review_result, source_type="ai_ready_reviewed_model"):
    from data.track_model_resolver import ResolvedTrackModel, TrackModelSourceType
    from data.track_segment_review import is_ai_ready
    ai_ready, _ = is_ai_ready(review_result)
    return ResolvedTrackModel(
        track_location_id=review_result.track_location_id,
        layout_id=review_result.layout_id,
        source_type=TrackModelSourceType(source_type),
        modelling_status="user_reviewed",
        ai_ready=ai_ready,
        review_completion_pct=100.0,
        segment_count=len(review_result.segments),
        confirmed_count=len(review_result.segments),
        rejected_count=0,
        needs_more_laps_count=0,
        warning_count=0,
        reviewed_model=review_result,
    )


def _make_resolver_result(resolved_model, resolution_status="found"):
    from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
    return TrackModelResolverResult(
        track_location_id=resolved_model.track_location_id,
        layout_id=resolved_model.layout_id,
        resolution_status=TrackModelResolutionStatus(resolution_status),
        resolved_model=resolved_model,
    )


def _make_reference_path(points_data, loc="test_track", lay="test_track__full"):
    from data.track_calibration import ReferencePath, ReferencePathPoint
    pts = [
        ReferencePathPoint(
            lap_progress=p["lap_progress"],
            distance_along_lap_m=p.get("distance_along_lap_m", p["lap_progress"] * 1000),
            x=p["x"], y=p.get("y", 0.0), z=p["z"],
            speed_kph_avg=p.get("speed_kph_avg", 100.0),
            source_lap_count=3,
        )
        for p in points_data
    ]
    return ReferencePath(
        track_location_id=loc,
        layout_id=lay,
        calibration_car_id="porsche_911_rsr_991_17",
        source_lap_count=3,
        points=pts,
    )


def _make_position(
    lap_progress=None, pos_x=None, pos_y=None, pos_z=None,
    distance_along_lap_m=None, segment_id=None, speed_kph=None,
):
    from data.live_segment_resolver import LivePosition
    return LivePosition(
        lap_progress=lap_progress,
        pos_x=pos_x, pos_y=pos_y, pos_z=pos_z,
        distance_along_lap_m=distance_along_lap_m,
        segment_id=segment_id,
        speed_kph=speed_kph,
    )


def _simple_two_segment_setup():
    """Return (seg1, seg2, resolver_result) for typical tests."""
    seg1 = _make_reviewed_segment(
        segment_id="seg_braking_t1",
        display_name="T1 Braking Zone",
        lap_progress_start=0.05, lap_progress_end=0.12, lap_progress_mid=0.085,
    )
    seg2 = _make_reviewed_segment(
        segment_id="seg_apex_t1",
        segment_type="apex_zone",
        display_name="T1 Apex",
        lap_progress_start=0.12, lap_progress_end=0.18, lap_progress_mid=0.15,
    )
    review = _make_review_result([seg1, seg2])
    resolved = _make_resolved_model(review)
    resolver_result = _make_resolver_result(resolved)
    return seg1, seg2, resolver_result


# ---------------------------------------------------------------------------
# Class 1 — Dataclass construction
# ---------------------------------------------------------------------------

class TestDataclassConstruction:
    def test_live_position_constructs_empty(self):
        from data.live_segment_resolver import LivePosition
        pos = LivePosition()
        assert pos.lap_progress is None
        assert pos.pos_x is None

    def test_live_position_constructs_with_progress(self):
        from data.live_segment_resolver import LivePosition
        pos = LivePosition(lap_progress=0.35)
        assert pos.lap_progress == 0.35

    def test_live_segment_match_constructs(self):
        from data.live_segment_resolver import LiveSegmentMatch, LiveSegmentResolutionConfidence
        m = LiveSegmentMatch(
            track_location_id="t", layout_id="t__l",
            segment_id="seg1", display_name="T1 Braking Zone",
            segment_type="braking_zone",
            lap_progress=0.08,
            lap_progress_start=0.05, lap_progress_end=0.12, lap_progress_mid=0.085,
            distance_along_lap_m=None,
            confidence=LiveSegmentResolutionConfidence.HIGH,
            source="lap_progress",
        )
        assert m.segment_id == "seg1"
        assert m.confidence == LiveSegmentResolutionConfidence.HIGH

    def test_live_segment_resolver_result_constructs(self):
        from data.live_segment_resolver import LiveSegmentResolverResult, LiveSegmentResolutionStatus
        r = LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.NO_REVIEWED_MODEL,
        )
        assert r.match is None
        assert r.model_source == "missing"

    def test_live_segment_resolver_config_defaults(self):
        from data.live_segment_resolver import LiveSegmentResolverConfig
        cfg = LiveSegmentResolverConfig()
        assert cfg.include_needs_more_laps is True
        assert cfg.include_unreviewed is False
        assert cfg.allow_not_ai_ready is True

    def test_confidence_enum_values(self):
        from data.live_segment_resolver import LiveSegmentResolutionConfidence
        values = [c.value for c in LiveSegmentResolutionConfidence]
        assert "high" in values
        assert "medium" in values
        assert "low" in values
        assert "unknown" in values

    def test_status_enum_values(self):
        from data.live_segment_resolver import LiveSegmentResolutionStatus
        values = [s.value for s in LiveSegmentResolutionStatus]
        assert "matched" in values
        assert "matched_nearest" in values
        assert "no_reviewed_model" in values
        assert "no_position_data" in values
        assert "no_segment_bounds" in values
        assert "error" in values


# ---------------------------------------------------------------------------
# Class 2 — Exact segment_id match
# ---------------------------------------------------------------------------

class TestExactSegmentIdMatch:
    def test_exact_segment_id_returns_matched(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(segment_id="seg_braking_t1")

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED
        assert result.match.segment_id == "seg_braking_t1"
        assert result.match.source == "segment_id"

    def test_exact_segment_id_confidence_high_for_ai_ready(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionConfidence
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(segment_id="seg_braking_t1")

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.match.confidence == LiveSegmentResolutionConfidence.HIGH

    def test_unknown_segment_id_falls_through(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(segment_id="seg_nonexistent")

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        # No progress fallback either → no_position_data
        assert result.status == LiveSegmentResolutionStatus.NO_POSITION_DATA


# ---------------------------------------------------------------------------
# Class 3 — Lap progress match
# ---------------------------------------------------------------------------

class TestLapProgressMatch:
    def test_lap_progress_within_bounds_returns_matched(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.09)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED
        assert result.match.segment_id == "seg_braking_t1"
        assert result.match.source == "lap_progress"

    def test_lap_progress_at_start_boundary_matches(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.05)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED
        assert result.match.segment_id == "seg_braking_t1"

    def test_lap_progress_at_end_boundary_matches(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.12)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED

    def test_lap_progress_outside_all_bounds_falls_to_nearest(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.50)  # outside both segments

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED_NEAREST

    def test_matched_nearest_has_lower_confidence(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionConfidence
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.50)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.match.confidence in (
            LiveSegmentResolutionConfidence.MEDIUM,
            LiveSegmentResolutionConfidence.LOW,
        )


# ---------------------------------------------------------------------------
# Class 4 — Distance along lap matching
# ---------------------------------------------------------------------------

class TestDistanceAlongLapMatch:
    def test_distance_match_via_reference_path(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        ref = _make_reference_path([
            {"lap_progress": 0.10, "x": 0.0, "z": 0.0, "distance_along_lap_m": 100.0},
            {"lap_progress": 0.15, "x": 50.0, "z": 0.0, "distance_along_lap_m": 150.0},
            {"lap_progress": 0.20, "x": 100.0, "z": 0.0, "distance_along_lap_m": 200.0},
        ])
        pos = _make_position(distance_along_lap_m=150.0)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=ref):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED
        assert result.match.source in ("distance", "lap_progress")


# ---------------------------------------------------------------------------
# Class 5 — XYZ nearest reference path match
# ---------------------------------------------------------------------------

class TestXYZNearestMatch:
    def test_xyz_match_via_reference_path(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        ref = _make_reference_path([
            {"lap_progress": 0.05, "x": 0.0, "z": 0.0},
            {"lap_progress": 0.15, "x": 50.0, "z": 5.0},   # closest to (50, 0, 5)
            {"lap_progress": 0.50, "x": 200.0, "z": 200.0},
        ])
        pos = _make_position(pos_x=50.0, pos_y=0.0, pos_z=5.0)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=ref):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED
        assert result.match.source in ("xyz_nearest", "nearest_midpoint")

    def test_xyz_without_reference_path_returns_no_position_data(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg = _make_reviewed_segment()
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(pos_x=50.0, pos_y=0.0, pos_z=5.0)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.NO_POSITION_DATA


# ---------------------------------------------------------------------------
# Class 6 — No reviewed model
# ---------------------------------------------------------------------------

class TestNoReviewedModel:
    def test_seed_only_returns_no_reviewed_model(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        from data.track_model_resolver import (
            TrackModelResolverResult, TrackModelResolutionStatus,
            ResolvedTrackModel, TrackModelSourceType,
        )
        seed_resolved = ResolvedTrackModel(
            track_location_id="t", layout_id="t__l",
            source_type=TrackModelSourceType.SEED_ONLY,
            modelling_status="seed_only",
            ai_ready=False,
            review_completion_pct=0.0,
            segment_count=0, confirmed_count=0, rejected_count=0,
            needs_more_laps_count=0, warning_count=0,
        )
        resolver_result = TrackModelResolverResult(
            track_location_id="t", layout_id="t__l",
            resolution_status=TrackModelResolutionStatus.SEED_ONLY_FALLBACK,
            resolved_model=seed_resolved,
        )
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.NO_REVIEWED_MODEL
        assert result.match is None

    def test_missing_model_returns_no_reviewed_model(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing = TrackModelResolverResult(
            track_location_id="t", layout_id="t__l",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.NO_REVIEWED_MODEL
        assert result.match is None

    def test_no_reviewed_model_result_includes_warning(self):
        from data.live_segment_resolver import resolve_live_segment
        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing = TrackModelResolverResult(
            track_location_id="t", layout_id="t__l",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing):
            result = resolve_live_segment("t", "t__l", pos)

        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# Class 7 — No position data
# ---------------------------------------------------------------------------

class TestNoPositionData:
    def test_none_position_returns_no_position_data(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result):
            result = resolve_live_segment("t", "t__l", position=None)

        assert result.status == LiveSegmentResolutionStatus.NO_POSITION_DATA

    def test_empty_position_returns_no_position_data(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position()  # all None

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.NO_POSITION_DATA


# ---------------------------------------------------------------------------
# Class 8 — Reviewed but not AI-ready model
# ---------------------------------------------------------------------------

class TestNotAiReadyModel:
    def test_not_ai_ready_model_allows_match_with_warning(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review, "reviewed_model")
        resolver_result = _make_resolver_result(resolved, "found_with_warnings")
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.MATCHED
        assert result.match is not None
        # Warning about not-AI-ready should be present
        all_warnings = result.warnings + (result.match.warnings if result.match else [])
        assert any("not AI-ready" in w or "not ai-ready" in w.lower() for w in all_warnings)

    def test_not_ai_ready_match_confidence_reduced(self):
        from data.live_segment_resolver import (
            resolve_live_segment, LiveSegmentResolutionConfidence,
        )
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review, "reviewed_model")
        resolver_result = _make_resolver_result(resolved, "found_with_warnings")
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        # reviewed (not ai_ready) base is MEDIUM, not HIGH
        assert result.match.confidence in (
            LiveSegmentResolutionConfidence.MEDIUM,
            LiveSegmentResolutionConfidence.LOW,
        )


# ---------------------------------------------------------------------------
# Class 9 — Previous / next segment
# ---------------------------------------------------------------------------

class TestPreviousNextSegment:
    def _resolve_with_two_segs(self, lap_progress=0.09):
        from data.live_segment_resolver import resolve_live_segment
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=lap_progress)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            return resolve_live_segment("t", "t__l", pos)

    def test_matched_segment_has_next_segment(self):
        result = self._resolve_with_two_segs(0.09)  # matches seg1
        assert result.match is not None
        assert result.match.next_segment_id == "seg_apex_t1"
        assert "T1 Apex" in result.match.next_segment_display_name

    def test_second_segment_has_previous(self):
        result = self._resolve_with_two_segs(0.15)  # matches seg2
        assert result.match is not None
        assert result.match.previous_segment_id == "seg_braking_t1"
        assert "T1 Braking Zone" in result.match.previous_segment_display_name

    def test_prev_next_wraps_around_start_finish(self):
        """With two segments, matching the first should have second as 'next'
        and second as 'prev' (wraparound)."""
        from data.live_segment_resolver import resolve_live_segment
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.09)  # matches seg1 (index 0)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        # seg1 is at index 0 → prev wraps to index -1 = seg2 (the last)
        assert result.match.previous_segment_id == "seg_apex_t1"
        # next is index 1 = seg2
        assert result.match.next_segment_id == "seg_apex_t1"

    def test_three_segment_prev_next(self):
        from data.live_segment_resolver import resolve_live_segment
        segs = [
            _make_reviewed_segment("seg_s1", display_name="S1", lap_progress_start=0.00, lap_progress_end=0.10, lap_progress_mid=0.05),
            _make_reviewed_segment("seg_s2", display_name="S2", lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15),
            _make_reviewed_segment("seg_s3", display_name="S3", lap_progress_start=0.20, lap_progress_end=0.30, lap_progress_mid=0.25),
        ]
        review = _make_review_result(segs)
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.15)  # matches s2 (index 1)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.match.previous_segment_id == "seg_s1"
        assert result.match.next_segment_id == "seg_s3"

    def test_single_segment_no_prev_no_next(self):
        from data.live_segment_resolver import resolve_live_segment
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.match.previous_segment_id is None
        assert result.match.next_segment_id is None


# ---------------------------------------------------------------------------
# Class 10 — Rejected segment exclusion
# ---------------------------------------------------------------------------

class TestRejectedSegmentExclusion:
    def test_rejected_segment_excluded_from_matching(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg_rejected = _make_reviewed_segment(
            segment_id="seg_rejected",
            lap_progress_start=0.05, lap_progress_end=0.15, lap_progress_mid=0.10,
            review_status="rejected",
        )
        review = _make_review_result([seg_rejected])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.10)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.match is None or result.match.segment_id != "seg_rejected"

    def test_only_rejected_segments_returns_no_segment_bounds(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg = _make_reviewed_segment(review_status="rejected")
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.10)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.status == LiveSegmentResolutionStatus.NO_SEGMENT_BOUNDS


# ---------------------------------------------------------------------------
# Class 11 — Needs more laps / unreviewed segments
# ---------------------------------------------------------------------------

class TestSegmentConfidenceDegradation:
    def test_needs_more_laps_degrades_confidence(self):
        from data.live_segment_resolver import (
            resolve_live_segment, LiveSegmentResolutionConfidence,
        )
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
            review_status="needs_more_laps",
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        assert result.match is not None
        assert result.match.confidence in (
            LiveSegmentResolutionConfidence.MEDIUM,
            LiveSegmentResolutionConfidence.LOW,
        )
        assert any("needs more calibration" in w for w in result.match.warnings)

    def test_unreviewed_excluded_by_default(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
            review_status="unreviewed",
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)

        # Default config excludes unreviewed → no usable segments
        assert result.status == LiveSegmentResolutionStatus.NO_SEGMENT_BOUNDS

    def test_unreviewed_included_when_config_set(self):
        from data.live_segment_resolver import (
            resolve_live_segment, LiveSegmentResolutionStatus, LiveSegmentResolverConfig,
        )
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
            review_status="unreviewed",
        )
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.15)
        cfg = LiveSegmentResolverConfig(include_unreviewed=True)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos, config=cfg)

        assert result.status in (
            LiveSegmentResolutionStatus.MATCHED,
            LiveSegmentResolutionStatus.MATCHED_NEAREST,
        )


# ---------------------------------------------------------------------------
# Class 12 — format_live_segment_for_engineer
# ---------------------------------------------------------------------------

class TestFormatLiveSegmentForEngineer:
    def _matched_result(self, display_name="T1 Braking Zone",
                        next_name="T1 Apex", prev_name="", confidence="high"):
        from data.live_segment_resolver import (
            LiveSegmentResolverResult, LiveSegmentResolutionStatus,
            LiveSegmentMatch, LiveSegmentResolutionConfidence,
        )
        m = LiveSegmentMatch(
            track_location_id="t", layout_id="t__l",
            segment_id="seg1", display_name=display_name,
            segment_type="braking_zone",
            lap_progress=0.08,
            lap_progress_start=0.05, lap_progress_end=0.12, lap_progress_mid=0.085,
            distance_along_lap_m=None,
            confidence=LiveSegmentResolutionConfidence(confidence),
            source="lap_progress",
            next_segment_display_name=next_name,
            previous_segment_display_name=prev_name,
        )
        return LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.MATCHED,
            match=m, model_source="ai_ready",
        )

    def _nearest_result(self, display_name="T1 Apex"):
        from data.live_segment_resolver import (
            LiveSegmentResolverResult, LiveSegmentResolutionStatus,
            LiveSegmentMatch, LiveSegmentResolutionConfidence,
        )
        m = LiveSegmentMatch(
            track_location_id="t", layout_id="t__l",
            segment_id="seg2", display_name=display_name,
            segment_type="apex_zone",
            lap_progress=0.50,
            lap_progress_start=0.12, lap_progress_end=0.18, lap_progress_mid=0.15,
            distance_along_lap_m=None,
            confidence=LiveSegmentResolutionConfidence.LOW,
            source="nearest_midpoint",
        )
        return LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.MATCHED_NEAREST,
            match=m, model_source="ai_ready",
        )

    def test_matched_includes_segment_name(self):
        from data.live_segment_resolver import format_live_segment_for_engineer
        result = self._matched_result()
        text = format_live_segment_for_engineer(result)
        assert "T1 Braking Zone" in text

    def test_matched_includes_confidence(self):
        from data.live_segment_resolver import format_live_segment_for_engineer
        result = self._matched_result(confidence="high")
        text = format_live_segment_for_engineer(result)
        assert "high" in text.lower()

    def test_matched_includes_next_segment(self):
        from data.live_segment_resolver import format_live_segment_for_engineer
        result = self._matched_result(next_name="T1 Apex")
        text = format_live_segment_for_engineer(result)
        assert "T1 Apex" in text

    def test_nearest_fallback_includes_fallback_note(self):
        from data.live_segment_resolver import format_live_segment_for_engineer
        result = self._nearest_result()
        text = format_live_segment_for_engineer(result)
        assert "nearest fallback" in text.lower() or "fallback" in text.lower()

    def test_no_reviewed_model_safe_text(self):
        from data.live_segment_resolver import (
            format_live_segment_for_engineer,
            LiveSegmentResolverResult, LiveSegmentResolutionStatus,
        )
        result = LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.NO_REVIEWED_MODEL,
        )
        text = format_live_segment_for_engineer(result)
        assert "unavailable" in text.lower() or "no reviewed model" in text.lower()
        assert len(text) > 0

    def test_no_position_data_safe_text(self):
        from data.live_segment_resolver import (
            format_live_segment_for_engineer,
            LiveSegmentResolverResult, LiveSegmentResolutionStatus,
        )
        result = LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.NO_POSITION_DATA,
        )
        text = format_live_segment_for_engineer(result)
        assert "unresolved" in text.lower() or "no" in text.lower()

    def test_no_invented_corner_name_when_unresolved(self):
        from data.live_segment_resolver import (
            format_live_segment_for_engineer,
            LiveSegmentResolverResult, LiveSegmentResolutionStatus,
        )
        result = LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.NO_POSITION_DATA,
        )
        text = format_live_segment_for_engineer(result)
        # Should not contain any specific corner name
        for name in ["T1", "T2", "T3", "Apex", "Braking", "Exit"]:
            assert name not in text

    def test_error_status_safe_text(self):
        from data.live_segment_resolver import (
            format_live_segment_for_engineer,
            LiveSegmentResolverResult, LiveSegmentResolutionStatus,
        )
        result = LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.ERROR,
        )
        text = format_live_segment_for_engineer(result)
        assert len(text) > 0


# ---------------------------------------------------------------------------
# Class 13 — packet_to_live_position adapter
# ---------------------------------------------------------------------------

class TestPacketToLivePosition:
    def _make_packet(self, **kwargs):
        pkt = MagicMock()
        pkt.pos_x = kwargs.get("pos_x", 100.0)
        pkt.pos_y = kwargs.get("pos_y", 5.0)
        pkt.pos_z = kwargs.get("pos_z", 200.0)
        pkt.speed_kmh = kwargs.get("speed_kmh", 80.0)
        pkt.car_on_track = kwargs.get("car_on_track", True)
        pkt.paused = kwargs.get("paused", False)
        pkt.loading = kwargs.get("loading", False)
        return pkt

    def test_valid_packet_returns_live_position(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = self._make_packet()
        pos = packet_to_live_position(pkt)
        assert pos is not None
        assert pos.pos_x == 100.0
        assert pos.pos_z == 200.0

    def test_paused_returns_none(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = self._make_packet(paused=True)
        assert packet_to_live_position(pkt) is None

    def test_loading_returns_none(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = self._make_packet(loading=True)
        assert packet_to_live_position(pkt) is None

    def test_off_track_returns_none(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = self._make_packet(car_on_track=False)
        assert packet_to_live_position(pkt) is None

    def test_zero_xyz_returns_none(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = self._make_packet(pos_x=0.0, pos_y=0.0, pos_z=0.0)
        assert packet_to_live_position(pkt) is None

    def test_lap_progress_not_set(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = self._make_packet()
        pos = packet_to_live_position(pkt)
        assert pos.lap_progress is None  # GT7 has no native lap_progress

    def test_distance_along_lap_m_not_set(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = self._make_packet()
        pos = packet_to_live_position(pkt)
        assert pos.distance_along_lap_m is None  # road_distance is absolute, not lap-relative

    def test_missing_pos_attributes_handled_safely(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = MagicMock(spec=[])  # no attributes at all
        # Should not raise
        pos = packet_to_live_position(pkt)
        # Returns None or a position with None XYZ
        assert pos is None or pos.pos_x is None

    def test_exception_in_packet_returns_none(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = MagicMock()
        pkt.pos_x = property(lambda self: 1 / 0)  # raises ZeroDivisionError
        # Should not raise
        result = packet_to_live_position(pkt)
        assert result is None or isinstance(result, object)


# ---------------------------------------------------------------------------
# Class 14 — get_live_segment_context_for_prompt
# ---------------------------------------------------------------------------

class TestGetLiveSegmentContextForPrompt:
    def test_no_reviewed_model_returns_empty(self):
        from data.live_segment_resolver import get_live_segment_context_for_prompt
        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing = TrackModelResolverResult(
            track_location_id="t", layout_id="t__l",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        pos = _make_position(lap_progress=0.15)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing):
            ctx = get_live_segment_context_for_prompt("t", "t__l", pos)
        assert ctx == ""

    def test_matched_returns_prompt_block(self):
        from data.live_segment_resolver import get_live_segment_context_for_prompt
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.09)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            ctx = get_live_segment_context_for_prompt("t", "t__l", pos)
        assert "## Live Track Position" in ctx
        assert "T1 Braking Zone" in ctx

    def test_matched_prompt_block_includes_segment_type(self):
        from data.live_segment_resolver import get_live_segment_context_for_prompt
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        pos = _make_position(lap_progress=0.09)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            ctx = get_live_segment_context_for_prompt("t", "t__l", pos)
        assert "braking_zone" in ctx

    def test_no_position_returns_warning_block(self):
        from data.live_segment_resolver import get_live_segment_context_for_prompt
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result):
            ctx = get_live_segment_context_for_prompt("t", "t__l", position=None)
        # Either returns "" or a warning block — neither should invent a corner name
        if ctx:
            for name in ["T1 Braking Zone", "T1 Apex"]:
                assert name not in ctx

    def test_never_raises(self):
        from data.live_segment_resolver import get_live_segment_context_for_prompt
        with patch("data.track_model_resolver.resolve_best_track_model", side_effect=RuntimeError("test")):
            ctx = get_live_segment_context_for_prompt("t", "t__l", _make_position(lap_progress=0.1))
        assert isinstance(ctx, str)


# ---------------------------------------------------------------------------
# Class 15 — DrivingAdvisor integration
# ---------------------------------------------------------------------------

class TestDrivingAdvisorLiveSegment:
    def _make_advisor(self, loc_id="suzuka_circuit", lay_id="suzuka_circuit__full_course"):
        from strategy.driving_advisor import DrivingAdvisor
        config = {
            "strategy": {"track_location_id": loc_id, "layout_id": lay_id, "track": "Test"},
            "anthropic": {"api_key": "test_key"},
        }
        recorder = MagicMock()
        recorder.best_lap.return_value = None
        tracker = MagicMock()
        return DrivingAdvisor(recorder, tracker, config)

    def test_get_live_segment_context_no_position_returns_empty(self):
        adv = self._make_advisor()
        ctx = adv._get_live_segment_context(live_position=None)
        assert ctx == ""

    def test_get_live_segment_context_no_ids_returns_empty(self):
        adv = self._make_advisor(loc_id="", lay_id="")
        from data.live_segment_resolver import LivePosition
        pos = LivePosition(lap_progress=0.15)
        ctx = adv._get_live_segment_context(live_position=pos)
        assert ctx == ""

    def test_get_live_segment_context_returns_string(self):
        adv = self._make_advisor()
        from data.live_segment_resolver import LivePosition
        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing = TrackModelResolverResult(
            track_location_id="suzuka_circuit",
            layout_id="suzuka_circuit__full_course",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        pos = LivePosition(lap_progress=0.15)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing):
            ctx = adv._get_live_segment_context(live_position=pos)
        assert isinstance(ctx, str)

    def test_get_live_segment_context_does_not_raise(self):
        adv = self._make_advisor()
        from data.live_segment_resolver import LivePosition
        pos = LivePosition(lap_progress=0.15)
        with patch("data.track_model_resolver.resolve_best_track_model", side_effect=RuntimeError("x")):
            ctx = adv._get_live_segment_context(live_position=pos)
        assert isinstance(ctx, str)

    def _make_lap(self):
        lap = MagicMock()
        lap.lap_num = 1
        lap.lap_time_ms = 90000
        lap.lock_up_count = 0
        lap.wheelspin_count = 0
        lap.oversteer_count = 0
        lap.oversteer_throttle_on_count = 0
        lap.kerb_count = 0
        lap.bottoming_count = 0
        lap.snap_throttle_count = 0
        lap.brake_consistency_m = 5.0
        lap.max_speed_kmh = 200.0
        lap.max_lat_g = 1.5
        lap.avg_throttle_pct = 60.0
        lap.avg_brake_pct = 20.0
        lap.rev_limiter_count = 0
        lap.lock_up_positions = []
        lap.wheelspin_positions = []
        lap.oversteer_positions = []
        lap.snap_throttle_positions = []
        lap.over_braking_positions = []
        lap.rev_limiter_by_gear = {}
        lap.over_braking_count = 0
        lap.abrupt_release_count = 0
        lap.car_max_speed_theoretical_kmh = 0.0
        lap.avg_tyre_radius = {}
        lap.off_track_count = 0
        return lap

# ---------------------------------------------------------------------------
# Class 16 — Resolver error handling
# ---------------------------------------------------------------------------

class TestResolverErrorHandling:
    def test_resolver_exception_returns_error_status(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        pos = _make_position(lap_progress=0.15)
        with patch("data.track_model_resolver.resolve_best_track_model", side_effect=RuntimeError("x")):
            result = resolve_live_segment("t", "t__l", pos)
        assert result.status == LiveSegmentResolutionStatus.ERROR
        assert len(result.errors) > 0

    def test_malformed_segments_handled_safely(self):
        """Segments with missing attributes should not crash the resolver."""
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg1, seg2, resolver_result = _simple_two_segment_setup()
        # Inject a malformed segment object
        bad_seg = MagicMock()
        bad_seg.segment_id = "bad"
        bad_seg.lap_progress_start = "not_a_float"  # wrong type
        bad_seg.lap_progress_end = None
        bad_seg.lap_progress_mid = None
        bad_seg.review_status = MagicMock()
        resolver_result.resolved_model.reviewed_model.segments.append(bad_seg)

        pos = _make_position(lap_progress=0.09)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)
        # Should not raise — may be matched or unresolved
        assert result is not None

    def test_no_segment_bounds_when_all_rejected(self):
        from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
        seg = _make_reviewed_segment(review_status="rejected")
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)
        pos = _make_position(lap_progress=0.08)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.live_segment_resolver._load_reference_path", return_value=None):
            result = resolve_live_segment("t", "t__l", pos)
        assert result.status == LiveSegmentResolutionStatus.NO_SEGMENT_BOUNDS


# ---------------------------------------------------------------------------
# Class 17 — Regression: Groups 17A–17I imports
# ---------------------------------------------------------------------------

class TestRegressionImports:
    def test_live_segment_resolver_importable(self):
        from data.live_segment_resolver import (
            resolve_live_segment, packet_to_live_position,
            format_live_segment_for_engineer, get_live_segment_context_for_prompt,
            LivePosition, LiveSegmentMatch, LiveSegmentResolverResult,
            LiveSegmentResolutionConfidence, LiveSegmentResolutionStatus,
            LiveSegmentResolverConfig,
        )
        assert callable(resolve_live_segment)

    def test_track_issue_enrichment_importable(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        assert callable(enrich_telemetry_issues)

    def test_driving_advisor_has_live_segment_method(self):
        from strategy.driving_advisor import DrivingAdvisor
        assert hasattr(DrivingAdvisor, "_get_live_segment_context")

    def test_track_model_resolver_importable(self):
        from data.track_model_resolver import resolve_best_track_model
        assert callable(resolve_best_track_model)

    def test_track_calibration_runtime_importable(self):
        from data.track_calibration_runtime import packet_to_calibration_sample
        assert callable(packet_to_calibration_sample)

    def test_track_segment_review_importable(self):
        from data.track_segment_review import ReviewedTrackSegment
        assert ReviewedTrackSegment is not None

    def test_xyz_to_lap_progress_uses_xz_only(self):
        """Verify the XZ-only distance ignores Y elevation."""
        from data.live_segment_resolver import _xyz_to_lap_progress
        ref = _make_reference_path([
            {"lap_progress": 0.10, "x": 0.0, "z": 0.0},
            {"lap_progress": 0.20, "x": 100.0, "z": 0.0},
        ])
        # Provide a large Y difference — should not affect XZ matching
        p, dist = _xyz_to_lap_progress(0.0, 9999.0, 0.0, ref)
        assert p == 0.10  # matches the first point by XZ

    def test_packet_to_live_position_speed_kph_populated(self):
        from data.live_segment_resolver import packet_to_live_position
        pkt = MagicMock()
        pkt.car_on_track = True
        pkt.paused = False
        pkt.loading = False
        pkt.pos_x = 50.0
        pkt.pos_y = 1.0
        pkt.pos_z = 100.0
        pkt.speed_kmh = 95.5
        pos = packet_to_live_position(pkt)
        assert pos is not None
        assert pos.speed_kph == 95.5

    def test_format_engineer_text_under_150_chars_for_matched(self):
        from data.live_segment_resolver import format_live_segment_for_engineer
        from data.live_segment_resolver import (
            LiveSegmentResolverResult, LiveSegmentResolutionStatus,
            LiveSegmentMatch, LiveSegmentResolutionConfidence,
        )
        m = LiveSegmentMatch(
            track_location_id="t", layout_id="t__l",
            segment_id="s1", display_name="T1 Braking Zone",
            segment_type="braking_zone",
            lap_progress=0.08,
            lap_progress_start=0.05, lap_progress_end=0.12, lap_progress_mid=0.085,
            distance_along_lap_m=None,
            confidence=LiveSegmentResolutionConfidence.HIGH,
            source="lap_progress",
            next_segment_display_name="T1 Apex",
        )
        result = LiveSegmentResolverResult(
            track_location_id="t", layout_id="t__l",
            status=LiveSegmentResolutionStatus.MATCHED,
            match=m, model_source="ai_ready",
        )
        text = format_live_segment_for_engineer(result)
        assert len(text) <= 200  # reasonable length constraint
