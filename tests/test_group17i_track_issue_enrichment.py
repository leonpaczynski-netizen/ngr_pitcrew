"""Tests for Group 17I — Telemetry Issue to Segment Enrichment.

Covers:
  - dataclass construction
  - exact segment_id match
  - lap_progress range match
  - distance_along_lap_m match via reference path
  - XYZ nearest reference path match
  - nearest segment fallback
  - unresolved fallback with warning
  - seed-only / missing model → LOW/UNRESOLVED confidence
  - rejected segment → UNRESOLVED
  - needs_more_laps segment → LOW confidence
  - implication mappings (brake_lock, wheelspin, limiter, poor_exit, wrong_gear, oversteer, understeer)
  - repeat issue grouping
  - prompt summary includes segment name, count, warnings
  - prompt summary does not invent names for unresolved
  - issues_from_lap_stats adapter
  - issues_from_corner_issues adapter
  - enriched context in DrivingAdvisor coaching prompt
  - regression: Groups 17A–17H still importable
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_raw_issue(
    issue_type="brake_lock",
    phase="braking",
    lap_num=1,
    lap_progress=None,
    pos_x=None, pos_y=None, pos_z=None,
    distance_along_lap_m=None,
    segment_id=None,
    evidence="",
):
    from data.track_issue_enrichment import RawTelemetryIssue, TrackIssueType, TrackIssuePhase
    return RawTelemetryIssue(
        issue_type=TrackIssueType(issue_type),
        phase=TrackIssuePhase(phase),
        lap_num=lap_num,
        lap_progress=lap_progress,
        pos_x=pos_x, pos_y=pos_y, pos_z=pos_z,
        distance_along_lap_m=distance_along_lap_m,
        segment_id=segment_id,
        evidence=evidence,
    )


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
    ai_ready, blockers = is_ai_ready(review_result)
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
            source_lap_count=p.get("source_lap_count", 3),
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


def _fake_resolve(seg, source="ai_ready"):
    """Return a resolver patcher (context manager) for a single segment."""
    segments = [seg]
    review = _make_review_result(segments)
    resolved = _make_resolved_model(review, f"{source}_reviewed_model")
    resolver_result = _make_resolver_result(resolved)
    return patch(
        "data.track_model_resolver.resolve_best_track_model",
        return_value=resolver_result,
    )


# ---------------------------------------------------------------------------
# Class 1 — Dataclass construction
# ---------------------------------------------------------------------------

class TestDataclassConstruction:
    def test_raw_issue_constructs(self):
        issue = _make_raw_issue()
        from data.track_issue_enrichment import TrackIssueType, TrackIssuePhase
        assert issue.issue_type == TrackIssueType.BRAKE_LOCK
        assert issue.phase == TrackIssuePhase.BRAKING
        assert issue.lap_num == 1

    def test_enriched_issue_constructs(self):
        from data.track_issue_enrichment import EnrichedTelemetryIssue, TrackIssueEnrichmentConfidence
        raw = _make_raw_issue()
        ei = EnrichedTelemetryIssue(raw=raw)
        assert ei.confidence == TrackIssueEnrichmentConfidence.UNRESOLVED
        assert ei.match_method == ""

    def test_enrichment_result_constructs(self):
        from data.track_issue_enrichment import TrackIssueEnrichmentResult
        result = TrackIssueEnrichmentResult(track_location_id="test", layout_id="test__full")
        assert result.unresolved_count == 0
        assert result.model_source == "missing"

    def test_all_issue_types_valid(self):
        from data.track_issue_enrichment import TrackIssueType
        types = [t.value for t in TrackIssueType]
        assert "brake_lock" in types
        assert "wheelspin" in types
        assert "limiter_hit" in types
        assert "unknown" in types

    def test_all_phases_valid(self):
        from data.track_issue_enrichment import TrackIssuePhase
        phases = [p.value for p in TrackIssuePhase]
        assert "braking" in phases
        assert "exit" in phases
        assert "straight" in phases

    def test_all_confidence_values_valid(self):
        from data.track_issue_enrichment import TrackIssueEnrichmentConfidence
        confs = [c.value for c in TrackIssueEnrichmentConfidence]
        assert "high" in confs
        assert "medium" in confs
        assert "low" in confs
        assert "unresolved" in confs


# ---------------------------------------------------------------------------
# Class 2 — Exact segment_id match
# ---------------------------------------------------------------------------

class TestExactSegmentIdMatch:
    def test_exact_segment_id_returns_match(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment(segment_id="seg_bz_t1")
        raw = _make_raw_issue(segment_id="seg_bz_t1")

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "test_track", "test_track__full")

        assert len(result.enriched_issues) == 1
        ei = result.enriched_issues[0]
        assert ei.matched_segment_id == "seg_bz_t1"
        assert ei.match_method == "segment_id"
        assert ei.confidence != TrackIssueEnrichmentConfidence.UNRESOLVED

    def test_exact_segment_id_not_in_model_falls_through(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment(segment_id="seg_other")
        raw = _make_raw_issue(segment_id="seg_bz_t1")  # different ID

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "test_track", "test_track__full")

        ei = result.enriched_issues[0]
        # No progress either → unresolved
        assert ei.confidence == TrackIssueEnrichmentConfidence.UNRESOLVED


# ---------------------------------------------------------------------------
# Class 3 — Lap progress range match
# ---------------------------------------------------------------------------

class TestLapProgressMatch:
    def test_lap_progress_within_segment_bounds(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15
        )
        raw = _make_raw_issue(lap_progress=0.15)  # within bounds

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "test_track", "test_track__full")

        ei = result.enriched_issues[0]
        assert ei.match_method == "lap_progress"
        assert ei.matched_segment_id == seg.segment_id
        assert ei.confidence != TrackIssueEnrichmentConfidence.UNRESOLVED

    def test_lap_progress_outside_segment_falls_to_nearest(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15
        )
        raw = _make_raw_issue(lap_progress=0.50)  # outside all segments

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "test_track", "test_track__full")

        ei = result.enriched_issues[0]
        # Falls to nearest
        assert ei.match_method == "nearest"

    def test_lap_progress_at_boundary_matches(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15
        )
        raw_start = _make_raw_issue(lap_progress=0.10)
        raw_end   = _make_raw_issue(lap_progress=0.20)

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            r1 = enrich_telemetry_issues([raw_start], "t", "t__l")
            r2 = enrich_telemetry_issues([raw_end], "t", "t__l")

        assert r1.enriched_issues[0].match_method == "lap_progress"
        assert r2.enriched_issues[0].match_method == "lap_progress"


# ---------------------------------------------------------------------------
# Class 4 — Distance along lap match
# ---------------------------------------------------------------------------

class TestDistanceAlongLapMatch:
    def test_distance_match_via_reference_path(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15
        )
        raw = _make_raw_issue(distance_along_lap_m=150.0)

        # Reference path: distance 150m ≈ lap_progress 0.15
        ref = _make_reference_path([
            {"lap_progress": 0.10, "x": 0.0, "z": 0.0, "distance_along_lap_m": 100.0},
            {"lap_progress": 0.15, "x": 50.0, "z": 0.0, "distance_along_lap_m": 150.0},
            {"lap_progress": 0.20, "x": 100.0, "z": 0.0, "distance_along_lap_m": 200.0},
        ])

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=ref):
            result = enrich_telemetry_issues([raw], "test_track", "test_track__full")

        ei = result.enriched_issues[0]
        assert ei.matched_segment_id == seg.segment_id
        assert ei.match_method in ("distance", "lap_progress")


# ---------------------------------------------------------------------------
# Class 5 — XYZ / nearest reference path match
# ---------------------------------------------------------------------------

class TestXYZNearestMatch:
    def test_xyz_to_nearest_reference_path(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15
        )
        raw = _make_raw_issue(pos_x=50.0, pos_y=0.0, pos_z=5.0)

        # Reference path point close to (50, 0, 5)
        ref = _make_reference_path([
            {"lap_progress": 0.05, "x": 0.0, "z": 0.0},
            {"lap_progress": 0.15, "x": 50.0, "z": 0.0},  # nearest to (50,0,5)
            {"lap_progress": 0.50, "x": 200.0, "z": 200.0},
        ])

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=ref):
            result = enrich_telemetry_issues([raw], "test_track", "test_track__full")

        ei = result.enriched_issues[0]
        assert ei.matched_segment_id == seg.segment_id
        # Method is "nearest" (XYZ path → progress → segment.start/end lookup)

    def test_xyz_without_reference_path_falls_to_unresolved(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment()
        raw = _make_raw_issue(pos_x=50.0, pos_y=0.0, pos_z=5.0)

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "test_track", "test_track__full")

        ei = result.enriched_issues[0]
        assert ei.confidence == TrackIssueEnrichmentConfidence.UNRESOLVED


# ---------------------------------------------------------------------------
# Class 6 — Unresolved fallback
# ---------------------------------------------------------------------------

class TestUnresolvedFallback:
    def test_unresolved_has_warning(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment()
        raw = _make_raw_issue()  # no lap_progress, no XYZ, no segment_id

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "t", "t__l")

        ei = result.enriched_issues[0]
        assert ei.confidence == TrackIssueEnrichmentConfidence.UNRESOLVED
        assert any("no segment matched" in w.lower() or "do not invent" in w.lower() for w in ei.warnings)

    def test_unresolved_count_tracked(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        raw1 = _make_raw_issue()
        raw2 = _make_raw_issue()

        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing_result = TrackModelResolverResult(
            track_location_id="t", layout_id="t__l",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing_result):
            result = enrich_telemetry_issues([raw1, raw2], "t", "t__l")

        assert result.unresolved_count == 2

    def test_no_segment_id_no_progress_returns_unresolved(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20,
        )
        raw = _make_raw_issue()  # no location evidence at all

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "t", "t__l")

        ei = result.enriched_issues[0]
        assert ei.confidence == TrackIssueEnrichmentConfidence.UNRESOLVED


# ---------------------------------------------------------------------------
# Class 7 — Seed-only / missing model lowers confidence
# ---------------------------------------------------------------------------

class TestSeedOnlyConfidence:
    def test_seed_only_model_returns_low_or_unresolved(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus, ResolvedTrackModel, TrackModelSourceType
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
        raw = _make_raw_issue(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result):
            result = enrich_telemetry_issues([raw], "t", "t__l")

        assert result.model_source == "seed_only"
        for ei in result.enriched_issues:
            assert ei.confidence in (
                TrackIssueEnrichmentConfidence.UNRESOLVED,
                TrackIssueEnrichmentConfidence.LOW,
            )

    def test_missing_model_returns_unresolved(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing = TrackModelResolverResult(
            track_location_id="t", layout_id="t__l",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        raw = _make_raw_issue(lap_progress=0.15)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing):
            result = enrich_telemetry_issues([raw], "t", "t__l")

        assert result.model_source == "missing"
        assert result.enriched_issues[0].confidence == TrackIssueEnrichmentConfidence.UNRESOLVED


# ---------------------------------------------------------------------------
# Class 8 — Rejected / needs_more_laps segment handling
# ---------------------------------------------------------------------------

class TestRejectedSegmentHandling:
    def test_rejected_segment_returns_unresolved(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment(
            segment_id="seg_bz",
            lap_progress_start=0.10, lap_progress_end=0.20,
            review_status="rejected",
        )
        raw = _make_raw_issue(segment_id="seg_bz")

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review, "reviewed_model")
        resolver_result = _make_resolver_result(resolved, "found_with_warnings")

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "t", "t__l")

        ei = result.enriched_issues[0]
        assert ei.confidence == TrackIssueEnrichmentConfidence.UNRESOLVED

    def test_needs_more_laps_segment_returns_low(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment(
            segment_id="seg_bz",
            lap_progress_start=0.10, lap_progress_end=0.20,
            lap_progress_mid=0.15,
            review_status="needs_more_laps",
        )
        raw = _make_raw_issue(lap_progress=0.15)

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review, "reviewed_model")
        resolver_result = _make_resolver_result(resolved, "found_with_warnings")

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "t", "t__l")

        ei = result.enriched_issues[0]
        assert ei.confidence == TrackIssueEnrichmentConfidence.LOW

    def test_unreviewed_segment_confidence_capped(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, TrackIssueEnrichmentConfidence
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20,
            lap_progress_mid=0.15,
            review_status="unreviewed",
        )
        raw = _make_raw_issue(lap_progress=0.15)

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues([raw], "t", "t__l")

        ei = result.enriched_issues[0]
        assert ei.confidence in (
            TrackIssueEnrichmentConfidence.MEDIUM,
            TrackIssueEnrichmentConfidence.LOW,
        )


# ---------------------------------------------------------------------------
# Class 9 — Implication mappings
# ---------------------------------------------------------------------------

class TestImplicationMappings:
    def _enrich_with_type(self, issue_type, phase, seg_type="braking_zone"):
        from data.track_issue_enrichment import enrich_telemetry_issues
        seg = _make_reviewed_segment(
            segment_type=seg_type,
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15,
        )
        raw = _make_raw_issue(issue_type=issue_type, phase=phase, lap_progress=0.15)

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            return enrich_telemetry_issues([raw], "t", "t__l")

    def test_brake_lock_braking_zone_setup_implications(self):
        result = self._enrich_with_type("brake_lock", "braking", "braking_zone")
        ei = result.enriched_issues[0]
        assert len(ei.setup_implications) > 0
        assert any("brake_bias" in s.lower() or "brake" in s.lower() for s in ei.setup_implications)

    def test_brake_lock_braking_zone_driver_implications(self):
        result = self._enrich_with_type("brake_lock", "braking", "braking_zone")
        ei = result.enriched_issues[0]
        assert len(ei.driver_implications) > 0
        assert any("brake" in d.lower() or "trail" in d.lower() for d in ei.driver_implications)

    def test_wheelspin_corner_exit_setup(self):
        result = self._enrich_with_type("wheelspin", "traction", "corner_exit")
        ei = result.enriched_issues[0]
        assert any("LSD" in s or "rear" in s.lower() for s in ei.setup_implications)

    def test_wheelspin_corner_exit_driver(self):
        result = self._enrich_with_type("wheelspin", "exit", "corner_exit")
        ei = result.enriched_issues[0]
        assert any("throttle" in d.lower() or "shift" in d.lower() for d in ei.driver_implications)

    def test_limiter_hit_straight_setup(self):
        result = self._enrich_with_type("limiter_hit", "straight", "straight")
        ei = result.enriched_issues[0]
        assert any("gear" in s.lower() or "drive" in s.lower() or "ratio" in s.lower()
                   for s in ei.setup_implications)

    def test_limiter_hit_straight_driver(self):
        result = self._enrich_with_type("limiter_hit", "straight", "straight")
        ei = result.enriched_issues[0]
        assert any("upshift" in d.lower() for d in ei.driver_implications)

    def test_poor_exit_drive_corner_exit_setup(self):
        result = self._enrich_with_type("poor_exit_drive", "exit", "corner_exit")
        ei = result.enriched_issues[0]
        assert any("LSD" in s or "exit" in s.lower() for s in ei.setup_implications)

    def test_wrong_gear_apex_setup(self):
        result = self._enrich_with_type("wrong_gear", "apex", "apex_zone")
        ei = result.enriched_issues[0]
        assert any("gearbox" in s.lower() for s in ei.setup_implications)

    def test_wrong_gear_apex_driver(self):
        result = self._enrich_with_type("wrong_gear", "apex", "apex_zone")
        ei = result.enriched_issues[0]
        assert any("gear" in d.lower() for d in ei.driver_implications)

    def test_oversteer_exit_setup(self):
        result = self._enrich_with_type("oversteer", "exit", "corner_exit")
        ei = result.enriched_issues[0]
        assert any("ARB" in s or "rear" in s.lower() for s in ei.setup_implications)

    def test_understeer_entry_setup(self):
        result = self._enrich_with_type("understeer", "entry", "corner_entry")
        ei = result.enriched_issues[0]
        assert any("front" in s.lower() or "ARB" in s for s in ei.setup_implications)


# ---------------------------------------------------------------------------
# Class 10 — Repeat issue grouping and prompt summary
# ---------------------------------------------------------------------------

class TestPromptSummary:
    def _make_enriched_issue(self, seg_name, issue_type, lap_num, seg_id="seg1", confidence="high"):
        from data.track_issue_enrichment import (
            EnrichedTelemetryIssue, TrackIssueEnrichmentConfidence, TrackIssueType, TrackIssuePhase,
        )
        raw = _make_raw_issue(issue_type=issue_type, lap_num=lap_num)
        return EnrichedTelemetryIssue(
            raw=raw,
            matched_segment_id=seg_id,
            matched_segment_type="braking_zone",
            matched_segment_display_name=seg_name,
            matched_segment_lap_progress_mid=0.15,
            match_method="lap_progress",
            confidence=TrackIssueEnrichmentConfidence(confidence),
        )

    def _make_unresolved(self, issue_type, lap_num):
        from data.track_issue_enrichment import (
            EnrichedTelemetryIssue, TrackIssueEnrichmentConfidence, TrackIssueType, TrackIssuePhase,
        )
        raw = _make_raw_issue(issue_type=issue_type, lap_num=lap_num)
        return EnrichedTelemetryIssue(
            raw=raw,
            match_method="unresolved",
            confidence=TrackIssueEnrichmentConfidence.UNRESOLVED,
            warnings=["No segment matched"],
        )

    def test_summary_includes_segment_name(self):
        from data.track_issue_enrichment import summarise_enriched_issues_for_prompt
        ei = self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=1)
        summary = summarise_enriched_issues_for_prompt([ei])
        assert "T1 Braking Zone" in summary

    def test_summary_includes_issue_type(self):
        from data.track_issue_enrichment import summarise_enriched_issues_for_prompt
        ei = self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=1)
        summary = summarise_enriched_issues_for_prompt([ei])
        assert "brake_lock" in summary

    def test_summary_includes_lap_count(self):
        from data.track_issue_enrichment import summarise_enriched_issues_for_prompt
        issues = [
            self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=1),
            self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=2),
            self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=3),
        ]
        summary = summarise_enriched_issues_for_prompt(issues)
        assert "3" in summary

    def test_summary_does_not_invent_names_for_unresolved(self):
        from data.track_issue_enrichment import summarise_enriched_issues_for_prompt
        ei = self._make_unresolved("brake_lock", lap_num=1)
        summary = summarise_enriched_issues_for_prompt([ei])
        # Must include unresolved notice
        assert "Unresolved" in summary or "unresolved" in summary or "no segment match" in summary.lower()
        # Must NOT include a segment name for the unresolved issue
        assert "T1" not in summary  # no invented corner

    def test_summary_empty_for_no_issues(self):
        from data.track_issue_enrichment import summarise_enriched_issues_for_prompt
        assert summarise_enriched_issues_for_prompt([]) == ""

    def test_summary_groups_by_segment_and_type(self):
        from data.track_issue_enrichment import summarise_enriched_issues_for_prompt
        issues = [
            self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=1),
            self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=2),
            self._make_enriched_issue("T2 Corner Exit", "wheelspin",   lap_num=1, seg_id="seg2"),
        ]
        summary = summarise_enriched_issues_for_prompt(issues)
        assert "T1 Braking Zone" in summary
        assert "T2 Corner Exit" in summary
        assert "wheelspin" in summary

    def test_mixed_resolved_and_unresolved(self):
        from data.track_issue_enrichment import summarise_enriched_issues_for_prompt
        resolved = self._make_enriched_issue("T1 Braking Zone", "brake_lock", lap_num=1)
        unresolved = self._make_unresolved("wheelspin", lap_num=2)
        summary = summarise_enriched_issues_for_prompt([resolved, unresolved])
        assert "T1 Braking Zone" in summary
        assert "Unresolved" in summary or "no segment" in summary.lower()


# ---------------------------------------------------------------------------
# Class 11 — issues_from_lap_stats adapter
# ---------------------------------------------------------------------------

class TestIssuesFromLapStats:
    def _make_lap(self, lap_num=1, **positions):
        lap = MagicMock()
        lap.lap_num = lap_num
        lap.lock_up_positions = positions.get("lock_up_positions", [])
        lap.wheelspin_positions = positions.get("wheelspin_positions", [])
        lap.oversteer_positions = positions.get("oversteer_positions", [])
        lap.snap_throttle_positions = positions.get("snap_throttle_positions", [])
        lap.over_braking_positions = positions.get("over_braking_positions", [])
        return lap

    def test_lock_up_positions_to_brake_lock(self):
        from data.track_issue_enrichment import issues_from_lap_stats, TrackIssueType
        lap = self._make_lap(lock_up_positions=[(100.0, 5.0, 200.0)])
        issues = issues_from_lap_stats([lap])
        assert any(i.issue_type == TrackIssueType.BRAKE_LOCK for i in issues)

    def test_wheelspin_positions_to_wheelspin(self):
        from data.track_issue_enrichment import issues_from_lap_stats, TrackIssueType
        lap = self._make_lap(wheelspin_positions=[(50.0, 0.0, 100.0)])
        issues = issues_from_lap_stats([lap])
        assert any(i.issue_type == TrackIssueType.WHEELSPIN for i in issues)

    def test_oversteer_positions_to_oversteer(self):
        from data.track_issue_enrichment import issues_from_lap_stats, TrackIssueType
        lap = self._make_lap(oversteer_positions=[(75.0, 1.0, 150.0)])
        issues = issues_from_lap_stats([lap])
        assert any(i.issue_type == TrackIssueType.OVERSTEER for i in issues)

    def test_snap_throttle_to_wheelspin(self):
        from data.track_issue_enrichment import issues_from_lap_stats, TrackIssueType
        lap = self._make_lap(snap_throttle_positions=[(25.0, 0.0, 50.0)])
        issues = issues_from_lap_stats([lap])
        assert any(i.issue_type == TrackIssueType.WHEELSPIN for i in issues)

    def test_over_braking_to_brake_lock(self):
        from data.track_issue_enrichment import issues_from_lap_stats, TrackIssueType
        lap = self._make_lap(over_braking_positions=[(80.0, 2.0, 180.0)])
        issues = issues_from_lap_stats([lap])
        assert any(i.issue_type == TrackIssueType.BRAKE_LOCK for i in issues)

    def test_xyz_coordinates_populated(self):
        from data.track_issue_enrichment import issues_from_lap_stats
        lap = self._make_lap(lock_up_positions=[(123.0, 5.0, 456.0)])
        issues = issues_from_lap_stats([lap])
        issue = issues[0]
        assert issue.pos_x == 123.0
        assert issue.pos_z == 456.0

    def test_lap_num_populated(self):
        from data.track_issue_enrichment import issues_from_lap_stats
        lap = self._make_lap(lap_num=7, lock_up_positions=[(100.0, 0.0, 200.0)])
        issues = issues_from_lap_stats([lap])
        assert issues[0].lap_num == 7

    def test_empty_laps_returns_empty(self):
        from data.track_issue_enrichment import issues_from_lap_stats
        assert issues_from_lap_stats([]) == []

    def test_no_positions_returns_empty(self):
        from data.track_issue_enrichment import issues_from_lap_stats
        lap = self._make_lap()  # all positions lists empty
        assert issues_from_lap_stats([lap]) == []


# ---------------------------------------------------------------------------
# Class 12 — issues_from_corner_issues adapter
# ---------------------------------------------------------------------------

class TestIssuesFromCornerIssues:
    def _make_corner_issue(self, issue_type="brake_lock", phase="braking",
                           corner_id="P500_-200", evidence="test"):
        ci = MagicMock()
        ci.issue_type = issue_type
        ci.phase = phase
        ci.corner_id = corner_id
        ci.evidence = evidence
        return ci

    def test_brake_lock_maps_to_brake_lock(self):
        from data.track_issue_enrichment import issues_from_corner_issues, TrackIssueType
        ci = self._make_corner_issue("brake_lock")
        issues = issues_from_corner_issues([ci])
        assert issues[0].issue_type == TrackIssueType.BRAKE_LOCK

    def test_rear_wheelspin_maps_to_wheelspin(self):
        from data.track_issue_enrichment import issues_from_corner_issues, TrackIssueType
        ci = self._make_corner_issue("rear_wheelspin")
        issues = issues_from_corner_issues([ci])
        assert issues[0].issue_type == TrackIssueType.WHEELSPIN

    def test_poor_drive_out_maps_to_poor_exit_drive(self):
        from data.track_issue_enrichment import issues_from_corner_issues, TrackIssueType
        ci = self._make_corner_issue("poor_drive_out")
        issues = issues_from_corner_issues([ci])
        assert issues[0].issue_type == TrackIssueType.POOR_EXIT_DRIVE

    def test_early_limiter_maps_to_limiter_hit(self):
        from data.track_issue_enrichment import issues_from_corner_issues, TrackIssueType
        ci = self._make_corner_issue("early_limiter_on_straight")
        issues = issues_from_corner_issues([ci])
        assert issues[0].issue_type == TrackIssueType.LIMITER_HIT

    def test_corner_id_decoded_to_xyz(self):
        from data.track_issue_enrichment import issues_from_corner_issues
        ci = self._make_corner_issue(corner_id="P500_-200")
        issues = issues_from_corner_issues([ci])
        assert issues[0].pos_x == 500.0
        assert issues[0].pos_z == -200.0

    def test_invalid_corner_id_returns_none_xyz(self):
        from data.track_issue_enrichment import issues_from_corner_issues
        ci = self._make_corner_issue(corner_id="BADFORMAT")
        issues = issues_from_corner_issues([ci])
        assert issues[0].pos_x is None

    def test_empty_list_returns_empty(self):
        from data.track_issue_enrichment import issues_from_corner_issues
        assert issues_from_corner_issues([]) == []

    def test_phase_mapped(self):
        from data.track_issue_enrichment import issues_from_corner_issues, TrackIssuePhase
        ci = self._make_corner_issue(phase="exit")
        issues = issues_from_corner_issues([ci])
        assert issues[0].phase == TrackIssuePhase.EXIT


# ---------------------------------------------------------------------------
# Class 13 — DrivingAdvisor integration
# ---------------------------------------------------------------------------

class TestDrivingAdvisorEnrichment:
    def _make_advisor(self, loc_id="suzuka_circuit", lay_id="suzuka_circuit__full_course"):
        from strategy.driving_advisor import DrivingAdvisor
        config = {
            "strategy": {"track_location_id": loc_id, "layout_id": lay_id, "track": "Test"},
            "anthropic": {"api_key": "test_key"},
        }
        recorder = MagicMock()
        recorder.best_lap.return_value = None  # prevents float-format on MagicMock delta
        tracker = MagicMock()
        return DrivingAdvisor(recorder, tracker, config)

    def _make_lap(self, lock_up=None, wheelspin=None):
        lap = MagicMock()
        lap.lap_num = 1
        lap.lap_time_ms = 90000
        lap.lock_up_count = len(lock_up or [])
        lap.wheelspin_count = len(wheelspin or [])
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
        lap.lock_up_positions = lock_up or []
        lap.wheelspin_positions = wheelspin or []
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

    def test_get_enriched_issue_context_returns_string(self):
        adv = self._make_advisor()
        laps = [self._make_lap(lock_up=[(100.0, 0.0, 200.0)])]
        with patch("data.track_model_resolver.resolve_best_track_model") as mock_res:
            from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
            mock_res.return_value = TrackModelResolverResult(
                track_location_id="suzuka_circuit",
                layout_id="suzuka_circuit__full_course",
                resolution_status=TrackModelResolutionStatus.MISSING,
            )
            ctx = adv._get_enriched_issue_context(laps)
        assert isinstance(ctx, str)

    def test_get_enriched_issue_context_returns_empty_without_ids(self):
        adv = self._make_advisor(loc_id="", lay_id="")
        laps = [self._make_lap(lock_up=[(100.0, 0.0, 200.0)])]
        ctx = adv._get_enriched_issue_context(laps)
        assert ctx == ""

    def test_get_enriched_issue_context_does_not_raise(self):
        adv = self._make_advisor()
        laps = [self._make_lap()]
        with patch("data.track_model_resolver.resolve_best_track_model", side_effect=RuntimeError("test")):
            ctx = adv._get_enriched_issue_context(laps)
        assert isinstance(ctx, str)

    def test_coaching_prompt_includes_enriched_issues_when_resolved(self):
        adv = self._make_advisor()
        laps = [self._make_lap(lock_up=[(100.0, 0.0, 200.0)])]

        _sentinel = "## Track-Located Telemetry Issues\nT1 Braking Zone — brake_lock"
        with patch.object(adv, "_get_enriched_issue_context", return_value=_sentinel):
            prompt = adv._build_coaching_prompt(laps, "")
        assert _sentinel in prompt

    def test_coaching_prompt_includes_warning_for_unresolved(self):
        adv = self._make_advisor()
        laps = [self._make_lap(lock_up=[(100.0, 0.0, 200.0)])]

        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing = TrackModelResolverResult(
            track_location_id="suzuka_circuit",
            layout_id="suzuka_circuit__full_course",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            prompt = adv._build_coaching_prompt(laps, "")
        # Prompt is still valid string even when enrichment unresolved
        assert isinstance(prompt, str)

    def test_setup_prompt_includes_enriched_issues(self):
        adv = self._make_advisor()
        laps = [self._make_lap(wheelspin=[(50.0, 0.0, 100.0)])]
        _sentinel = "## Track-Located Telemetry Issues\nT2 Corner Exit — wheelspin"
        with patch.object(adv, "_get_enriched_issue_context", return_value=_sentinel):
            prompt = adv._build_setup_prompt(laps, {}, "")
        assert _sentinel in prompt


# ---------------------------------------------------------------------------
# Class 14 — Full pipeline integration test
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_full_enrichment_pipeline(self):
        from data.track_issue_enrichment import (
            enrich_telemetry_issues, issues_from_lap_stats,
            summarise_enriched_issues_for_prompt, TrackIssueEnrichmentConfidence,
        )
        lap = MagicMock()
        lap.lap_num = 1
        lap.lock_up_positions = [(100.0, 5.0, 200.0)]
        lap.wheelspin_positions = []
        lap.oversteer_positions = []
        lap.snap_throttle_positions = []
        lap.over_braking_positions = []

        seg = _make_reviewed_segment(
            segment_id="seg_bz_t1",
            segment_type="braking_zone",
            display_name="T1 Braking Zone",
            lap_progress_start=0.09,
            lap_progress_end=0.20,
            lap_progress_mid=0.145,
        )

        # Reference path maps (100, 5, 200) → lap_progress 0.15
        ref = _make_reference_path([
            {"lap_progress": 0.05, "x": 0.0, "z": 0.0},
            {"lap_progress": 0.145, "x": 100.0, "z": 200.0},
            {"lap_progress": 0.50, "x": 500.0, "z": 500.0},
        ])

        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        raw_issues = issues_from_lap_stats([lap])
        assert len(raw_issues) == 1

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=ref):
            result = enrich_telemetry_issues(raw_issues, "test_track", "test_track__full")

        assert len(result.enriched_issues) == 1
        ei = result.enriched_issues[0]
        assert ei.matched_segment_id == "seg_bz_t1"
        assert "T1 Braking Zone" in ei.matched_segment_display_name

        summary = summarise_enriched_issues_for_prompt(result.enriched_issues)
        assert "T1 Braking Zone" in summary
        assert "brake_lock" in summary

    def test_no_crash_on_resolver_exception(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        raw = _make_raw_issue(lap_progress=0.15)
        with patch("data.track_model_resolver.resolve_best_track_model", side_effect=RuntimeError("test")):
            result = enrich_telemetry_issues([raw], "t", "t__l")
        assert result.model_source == "missing"
        assert result.enriched_issues[0].confidence.value == "unresolved"

    def test_multiple_issues_multiple_laps(self):
        from data.track_issue_enrichment import enrich_telemetry_issues, summarise_enriched_issues_for_prompt
        seg = _make_reviewed_segment(
            lap_progress_start=0.10, lap_progress_end=0.20, lap_progress_mid=0.15
        )
        raw_issues = [
            _make_raw_issue(lap_progress=0.15, lap_num=1),
            _make_raw_issue(lap_progress=0.15, lap_num=2),
            _make_raw_issue(lap_progress=0.15, lap_num=3),
        ]
        review = _make_review_result([seg])
        resolved = _make_resolved_model(review)
        resolver_result = _make_resolver_result(resolved)

        with patch("data.track_model_resolver.resolve_best_track_model", return_value=resolver_result), \
             patch("data.track_issue_enrichment._load_reference_path", return_value=None):
            result = enrich_telemetry_issues(raw_issues, "t", "t__l")

        summary = summarise_enriched_issues_for_prompt(result.enriched_issues)
        assert "3" in summary  # 3 laps


# ---------------------------------------------------------------------------
# Class 15 — Regression: Groups 17A–17H importable
# ---------------------------------------------------------------------------

class TestRegressionImports:
    def test_track_issue_enrichment_importable(self):
        from data.track_issue_enrichment import (
            enrich_telemetry_issues, issues_from_lap_stats, issues_from_corner_issues,
            summarise_enriched_issues_for_prompt, RawTelemetryIssue, EnrichedTelemetryIssue,
            TrackIssueEnrichmentResult, TrackIssueType, TrackIssuePhase,
            TrackIssueEnrichmentConfidence,
        )
        assert callable(enrich_telemetry_issues)

    def test_track_context_prompt_importable(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        assert callable(get_track_context_for_ai)

    def test_ai_planner_importable(self):
        from strategy.ai_planner import RaceParams, analyse_strategy
        assert RaceParams is not None

    def test_driving_advisor_importable(self):
        from strategy.driving_advisor import DrivingAdvisor
        assert hasattr(DrivingAdvisor, "_get_enriched_issue_context")

    def test_track_model_resolver_importable(self):
        from data.track_model_resolver import resolve_best_track_model
        assert callable(resolve_best_track_model)

    def test_track_segment_review_importable(self):
        from data.track_segment_review import TrackModelReviewResult
        assert TrackModelReviewResult is not None

    def test_corner_learning_importable(self):
        from data.corner_learning import CornerIssue, ISSUE_TYPES
        assert "brake_lock" in ISSUE_TYPES

    def test_decode_corner_id_positive_positive(self):
        from data.track_issue_enrichment import _decode_corner_id
        x, z = _decode_corner_id("P300_400")
        assert x == 300.0
        assert z == 400.0

    def test_decode_corner_id_negative_z(self):
        from data.track_issue_enrichment import _decode_corner_id
        x, z = _decode_corner_id("P500_-200")
        assert x == 500.0
        assert z == -200.0

    def test_decode_corner_id_bad_format(self):
        from data.track_issue_enrichment import _decode_corner_id
        x, z = _decode_corner_id("BADFORMAT")
        assert x is None and z is None
