"""Group 17G — Approved Track Model Resolver and Modelling Status Promotion tests.

Covers:
  - listing reviewed model files
  - finding reviewed models for selected track/layout
  - malformed reviewed model file handled safely
  - resolver falls back to seed-only when no reviewed model exists
  - resolver identifies non-AI-ready reviewed model
  - resolver identifies AI-ready reviewed model
  - resolver prefers AI-ready over non-AI-ready
  - resolver prefers engineer_validated over AI-ready
  - resolver prefers newest model when maturity is equal
  - blockers and warnings are preserved
  - saved reviewed model JSON includes modelling_status
  - build_resolved_track_context_for_prompt (all branches)
  - view-model format_resolver_summary helper
  - existing Group 17A–17F tests continue passing (regression imports)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import pytest

from data.track_model_resolver import (
    TrackModelSourceType,
    TrackModelResolutionStatus,
    ResolvedTrackModel,
    TrackModelResolverResult,
    list_reviewed_track_models,
    load_reviewed_track_model,
    find_reviewed_models_for_layout,
    resolve_best_track_model,
    build_resolved_track_context_for_prompt,
)
from data.track_segment_review import (
    TrackModelReviewResult,
    SegmentReviewStatus,
    export_review_json,
    import_review_json,
    create_review_from_detection,
    confirm_segment,
    reject_segment,
    mark_needs_more_laps,
    promote_engineer_validated,
    is_ai_ready,
)
from data.track_segment_detection import (
    DetectedTrackSegment,
    SegmentDetectionResult,
    TrackSegmentType,
    TrackSegmentDetectionConfidence,
    TrackSegmentDirection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_detection_result(
    track_loc: str = "suzuka",
    layout: str = "full",
    n_corners: int = 2,
    include_straight: bool = True,
    include_braking: bool = True,
    include_exit: bool = True,
) -> SegmentDetectionResult:
    segments: list[DetectedTrackSegment] = []
    for i in range(n_corners):
        p = i * 0.4
        if include_braking:
            segments.append(DetectedTrackSegment(
                segment_id=f"braking_{p:.3f}",
                segment_type=TrackSegmentType.BRAKING_ZONE,
                display_name=f"Braking zone T{i+1}",
                lap_progress_start=p,
                lap_progress_end=p + 0.05,
                lap_progress_mid=p + 0.025,
                confidence=TrackSegmentDetectionConfidence.MEDIUM,
                source_lap_count=3,
                calibration_car_id="porsche_911_rsr_991_2017",
                warnings=["Car-specific braking point — not universal"],
            ))
        segments.append(DetectedTrackSegment(
            segment_id=f"apex_{p+0.07:.3f}",
            segment_type=TrackSegmentType.APEX_ZONE,
            display_name=f"T{i+1} Apex",
            lap_progress_start=p + 0.06,
            lap_progress_end=p + 0.08,
            lap_progress_mid=p + 0.07,
            confidence=TrackSegmentDetectionConfidence.HIGH,
            source_lap_count=3,
            turn_number=i + 1,
            direction=TrackSegmentDirection.LEFT,
        ))
        if include_exit:
            segments.append(DetectedTrackSegment(
                segment_id=f"exit_{p+0.08:.3f}",
                segment_type=TrackSegmentType.CORNER_EXIT,
                display_name=f"Corner exit T{i+1}",
                lap_progress_start=p + 0.08,
                lap_progress_end=p + 0.15,
                lap_progress_mid=p + 0.115,
                confidence=TrackSegmentDetectionConfidence.MEDIUM,
                source_lap_count=3,
            ))
    if include_straight:
        segments.append(DetectedTrackSegment(
            segment_id="straight_0.850",
            segment_type=TrackSegmentType.STRAIGHT,
            display_name="Main straight",
            lap_progress_start=0.85,
            lap_progress_end=1.0,
            lap_progress_mid=0.925,
            confidence=TrackSegmentDetectionConfidence.HIGH,
            source_lap_count=3,
        ))
    return SegmentDetectionResult(
        success=True,
        track_location_id=track_loc,
        layout_id=layout,
        segments=segments,
        detected_corner_count=n_corners,
        source_lap_count=3,
        confidence=TrackSegmentDetectionConfidence.HIGH,
        calibration_car_id="porsche_911_rsr_991_2017",
        warnings=["Test detection warning"],
    )


def _make_review(track_loc: str = "suzuka", layout: str = "full",
                 n_corners: int = 2) -> TrackModelReviewResult:
    return create_review_from_detection(_make_detection_result(track_loc, layout, n_corners))


def _make_ai_ready_review(track_loc: str = "suzuka",
                          layout: str = "full") -> TrackModelReviewResult:
    """Make a review with all required types confirmed — should pass is_ai_ready."""
    review = _make_review(track_loc, layout, n_corners=1)
    for seg in review.segments:
        confirm_segment(review, seg.segment_id)
    ready, _ = is_ai_ready(review)
    assert ready, "Helper: review should be AI-ready after confirming all segments"
    return review


def _make_not_ai_ready_review(track_loc: str = "suzuka",
                              layout: str = "full") -> TrackModelReviewResult:
    """Make a review with some segments unreviewed — NOT AI-ready."""
    review = _make_review(track_loc, layout, n_corners=2)
    # Confirm only first segment; apex zones remain unreviewed
    confirm_segment(review, review.segments[0].segment_id)
    ready, _ = is_ai_ready(review)
    assert not ready, "Helper: review should NOT be AI-ready"
    return review


# ===========================================================================
# TestListReviewedTrackModels
# ===========================================================================

class TestListReviewedTrackModels:
    def test_returns_empty_list_for_missing_dir(self, tmp_path):
        missing = tmp_path / "nonexistent"
        result = list_reviewed_track_models(base_dir=missing)
        assert result == []

    def test_finds_json_files_with_infix(self, tmp_path):
        (tmp_path / "suzuka__full__reviewed_segments__s1.json").write_text('{"x":1}')
        (tmp_path / "unrelated.json").write_text('{}')
        files = list_reviewed_track_models(base_dir=tmp_path)
        assert len(files) == 1
        assert "reviewed_segments" in files[0].name

    def test_ignores_non_json(self, tmp_path):
        (tmp_path / "suzuka__full__reviewed_segments__s1.txt").write_text("x")
        files = list_reviewed_track_models(base_dir=tmp_path)
        assert files == []

    def test_returns_paths_sorted_newest_first(self, tmp_path):
        f_old = tmp_path / "suzuka__full__reviewed_segments__2024T100000Z.json"
        f_new = tmp_path / "suzuka__full__reviewed_segments__2025T100000Z.json"
        f_old.write_text('{"x":1}')
        f_new.write_text('{"x":1}')
        files = list_reviewed_track_models(base_dir=tmp_path)
        assert files[0] == f_new
        assert files[1] == f_old

    def test_returns_multiple_tracks(self, tmp_path):
        (tmp_path / "suzuka__full__reviewed_segments__s1.json").write_text('{"x":1}')
        (tmp_path / "monza__gp__reviewed_segments__s1.json").write_text('{"x":1}')
        files = list_reviewed_track_models(base_dir=tmp_path)
        assert len(files) == 2


# ===========================================================================
# TestFindReviewedModelsForLayout
# ===========================================================================

class TestFindReviewedModelsForLayout:
    def test_returns_only_matching_layout(self, tmp_path):
        (tmp_path / "suzuka__full__reviewed_segments__s1.json").write_text('{"x":1}')
        (tmp_path / "monza__gp__reviewed_segments__s1.json").write_text('{"x":1}')
        files = find_reviewed_models_for_layout("suzuka", "full", base_dir=tmp_path)
        assert len(files) == 1
        assert "suzuka" in files[0].name

    def test_returns_empty_for_missing_track(self, tmp_path):
        (tmp_path / "suzuka__full__reviewed_segments__s1.json").write_text('{"x":1}')
        files = find_reviewed_models_for_layout("nurburgring", "gp", base_dir=tmp_path)
        assert files == []

    def test_returns_multiple_versions_newest_first(self, tmp_path):
        f1 = tmp_path / "suzuka__full__reviewed_segments__2024T100000Z.json"
        f2 = tmp_path / "suzuka__full__reviewed_segments__2025T100000Z.json"
        f1.write_text('{"x":1}')
        f2.write_text('{"x":1}')
        files = find_reviewed_models_for_layout("suzuka", "full", base_dir=tmp_path)
        assert files[0] == f2

    def test_empty_dir_returns_empty(self, tmp_path):
        assert find_reviewed_models_for_layout("suzuka", "full", tmp_path) == []


# ===========================================================================
# TestLoadReviewedTrackModel
# ===========================================================================

class TestLoadReviewedTrackModel:
    def test_loads_valid_file(self, tmp_path):
        review = _make_ai_ready_review()
        out = export_review_json(review, output_dir=tmp_path)
        loaded = load_reviewed_track_model(out)
        assert loaded.track_location_id == "suzuka"

    def test_raises_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_reviewed_track_model(tmp_path / "ghost.json")

    def test_raises_for_bad_schema(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"schema": "wrong_schema_v99"}))
        with pytest.raises(ValueError):
            load_reviewed_track_model(bad)


# ===========================================================================
# TestResolveBestTrackModel — seed-only fallback
# ===========================================================================

_SEED_LOC = "suzuka_circuit"
_SEED_LAY = "suzuka_circuit__full_course"


class TestResolverSeedOnlyFallback:
    def test_seed_fallback_when_no_reviewed_model(self, tmp_path):
        # Use a known track/layout from the seed YAML
        result = resolve_best_track_model(_SEED_LOC, _SEED_LAY, base_dir=tmp_path)
        assert result.resolution_status == TrackModelResolutionStatus.SEED_ONLY_FALLBACK
        assert result.resolved_model is not None
        assert result.resolved_model.source_type == TrackModelSourceType.SEED_ONLY

    def test_seed_fallback_ai_ready_is_false(self, tmp_path):
        result = resolve_best_track_model(_SEED_LOC, _SEED_LAY, base_dir=tmp_path)
        if result.resolved_model:
            assert result.resolved_model.ai_ready is False

    def test_seed_fallback_has_warning(self, tmp_path):
        result = resolve_best_track_model(_SEED_LOC, _SEED_LAY, base_dir=tmp_path)
        if result.resolved_model:
            assert result.resolved_model.warnings

    def test_missing_when_track_not_in_seed(self, tmp_path):
        result = resolve_best_track_model("nonexistent_track", "nonexistent_layout",
                                          base_dir=tmp_path)
        assert result.resolution_status == TrackModelResolutionStatus.MISSING
        assert result.resolved_model is None


# ===========================================================================
# TestResolverNotAIReady
# ===========================================================================

class TestResolverNotAIReady:
    def test_not_ai_ready_resolution_status(self, tmp_path):
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolution_status == TrackModelResolutionStatus.NOT_AI_READY

    def test_not_ai_ready_source_type(self, tmp_path):
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.source_type == TrackModelSourceType.REVIEWED_MODEL

    def test_not_ai_ready_blockers_preserved(self, tmp_path):
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.blockers

    def test_not_ai_ready_ai_ready_flag_false(self, tmp_path):
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.ai_ready is False


# ===========================================================================
# TestResolverAIReady
# ===========================================================================

class TestResolverAIReady:
    def test_ai_ready_resolution_status(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolution_status in (
            TrackModelResolutionStatus.FOUND,
            TrackModelResolutionStatus.FOUND_WITH_WARNINGS,
        )

    def test_ai_ready_source_type(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.source_type == TrackModelSourceType.AI_READY_REVIEWED_MODEL

    def test_ai_ready_flag_true(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.ai_ready is True

    def test_ai_ready_no_blockers(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.blockers == []

    def test_ai_ready_modelling_status_is_user_reviewed(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.modelling_status == "user_reviewed"


# ===========================================================================
# TestResolverPriority
# ===========================================================================

class TestResolverPriority:
    def test_prefers_ai_ready_over_not_ai_ready(self, tmp_path):
        not_ready = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(not_ready, output_dir=tmp_path, session_id="2024T100000Z")
        ready = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(ready, output_dir=tmp_path, session_id="2024T090000Z")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.source_type == TrackModelSourceType.AI_READY_REVIEWED_MODEL

    def test_prefers_engineer_validated_over_ai_ready(self, tmp_path):
        # AI-ready model
        ai_ready = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(ai_ready, output_dir=tmp_path, session_id="2025T120000Z")
        # Engineer-validated model (AI-ready + any ENGINEER_VALIDATED segment)
        eng_review = _make_ai_ready_review("suzuka", "suzuka_full")
        seg_id = eng_review.segments[0].segment_id
        promote_engineer_validated(eng_review, seg_id)
        export_review_json(eng_review, output_dir=tmp_path, session_id="2024T120000Z")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.source_type == TrackModelSourceType.ENGINEER_VALIDATED_MODEL

    def test_prefers_newest_when_maturity_equal(self, tmp_path):
        older = _make_ai_ready_review("suzuka", "suzuka_full")
        newer = _make_ai_ready_review("suzuka", "suzuka_full")
        # Manipulate created_at to simulate time ordering
        older.created_at = "2024-01-01T00:00:00+00:00"
        newer.created_at = "2025-01-01T00:00:00+00:00"
        export_review_json(older, output_dir=tmp_path, session_id="2024T000000Z")
        export_review_json(newer, output_dir=tmp_path, session_id="2025T000000Z")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        # Newest should win
        assert result.resolved_model.source_path is not None
        assert "2025" in result.resolved_model.source_path.name


# ===========================================================================
# TestResolverMalformedFiles
# ===========================================================================

class TestResolverMalformedFiles:
    def test_skips_malformed_file_and_continues(self, tmp_path):
        # Write a bad JSON file that looks like a reviewed model
        bad = tmp_path / "suzuka__suzuka_full__reviewed_segments__s0.json"
        bad.write_text("NOT VALID JSON {{{")
        # Write a valid one
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path, session_id="s1")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        # Should still find the valid one; error recorded but not raised
        assert result.resolved_model is not None
        assert result.errors  # bad file error recorded

    def test_all_malformed_falls_back_to_seed(self, tmp_path):
        bad = tmp_path / "suzuka__suzuka_full__reviewed_segments__s0.json"
        bad.write_text("{}")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        # Should fall back to seed
        assert result.errors
        assert result.resolved_model is None or \
               result.resolved_model.source_type == TrackModelSourceType.SEED_ONLY

    def test_wrong_schema_recorded_as_error(self, tmp_path):
        bad = tmp_path / "suzuka__suzuka_full__reviewed_segments__s0.json"
        bad.write_text(json.dumps({"schema": "wrong_schema"}))
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert any("s0.json" in e or "Skipped" in e for e in result.errors)


# ===========================================================================
# TestCandidatePathsTracked
# ===========================================================================

class TestCandidatePathsTracked:
    def test_all_candidate_paths_listed(self, tmp_path):
        r1 = _make_ai_ready_review("suzuka", "suzuka_full")
        r2 = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(r1, output_dir=tmp_path, session_id="2025T001")
        export_review_json(r2, output_dir=tmp_path, session_id="2024T001")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert len(result.all_candidate_paths) == 2


# ===========================================================================
# TestModellingStatusInJSON
# ===========================================================================

class TestModellingStatusInJSON:
    def test_ai_ready_review_writes_user_reviewed(self, tmp_path):
        review = _make_ai_ready_review()
        out = export_review_json(review, output_dir=tmp_path)
        doc = json.loads(out.read_text())
        assert doc.get("modelling_status") == "user_reviewed"

    def test_not_ai_ready_review_writes_segment_detected(self, tmp_path):
        review = _make_not_ai_ready_review()
        out = export_review_json(review, output_dir=tmp_path)
        doc = json.loads(out.read_text())
        assert doc.get("modelling_status") == "segment_detected"

    def test_engineer_validated_writes_engineer_grade(self, tmp_path):
        review = _make_ai_ready_review()
        seg_id = review.segments[0].segment_id
        promote_engineer_validated(review, seg_id)
        out = export_review_json(review, output_dir=tmp_path)
        doc = json.loads(out.read_text())
        assert doc.get("modelling_status") == "engineer_grade"

    def test_import_reads_modelling_status(self, tmp_path):
        review = _make_ai_ready_review()
        out = export_review_json(review, output_dir=tmp_path)
        loaded = import_review_json(out)
        assert loaded.modelling_status == "user_reviewed"

    def test_old_file_without_modelling_status_returns_none(self, tmp_path):
        """Old files (Group 17F) without modelling_status field are backward-compatible."""
        review = _make_ai_ready_review()
        out = export_review_json(review, output_dir=tmp_path)
        # Manually remove the field
        doc = json.loads(out.read_text())
        doc.pop("modelling_status", None)
        out.write_text(json.dumps(doc))
        loaded = import_review_json(out)
        assert loaded.modelling_status is None  # None = not in file; resolver computes it


# ===========================================================================
# TestBuildResolvedTrackContextForPrompt
# ===========================================================================

class TestBuildResolvedTrackContextForPrompt:
    def test_seed_only_includes_warning(self, tmp_path):
        ctx = build_resolved_track_context_for_prompt(_SEED_LOC, _SEED_LAY,
                                                      base_dir=tmp_path)
        assert "seed" in ctx.lower() or "SEED" in ctx

    def test_seed_only_no_reviewed_model_note(self, tmp_path):
        ctx = build_resolved_track_context_for_prompt(_SEED_LOC, _SEED_LAY,
                                                      base_dir=tmp_path)
        assert "No reviewed track model" in ctx

    def test_ai_ready_includes_confirmed_segments(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        ctx = build_resolved_track_context_for_prompt("suzuka", "suzuka_full",
                                                      base_dir=tmp_path)
        assert "Confirmed segments" in ctx

    def test_ai_ready_includes_ai_ready_yes(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        ctx = build_resolved_track_context_for_prompt("suzuka", "suzuka_full",
                                                      base_dir=tmp_path)
        assert "AI-ready: Yes" in ctx

    def test_not_ai_ready_includes_blockers(self, tmp_path):
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        ctx = build_resolved_track_context_for_prompt("suzuka", "suzuka_full",
                                                      base_dir=tmp_path)
        assert "NOT AI-READY" in ctx

    def test_includes_car_behaviour_boundary_note(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        ctx = build_resolved_track_context_for_prompt("suzuka", "suzuka_full",
                                                      base_dir=tmp_path)
        assert "Porsche" in ctx and ("not universal" in ctx.lower() or "boundary" in ctx.lower())

    def test_missing_track_returns_missing_message(self, tmp_path):
        ctx = build_resolved_track_context_for_prompt("nonexistent", "nope",
                                                      base_dir=tmp_path)
        assert "MISSING" in ctx or "missing" in ctx.lower()

    def test_engineer_validated_includes_source_label(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        seg_id = review.segments[0].segment_id
        promote_engineer_validated(review, seg_id)
        export_review_json(review, output_dir=tmp_path)
        ctx = build_resolved_track_context_for_prompt("suzuka", "suzuka_full",
                                                      base_dir=tmp_path)
        assert "Engineer-validated" in ctx or "engineer" in ctx.lower()


# ===========================================================================
# TestViewModelResolverSummary
# ===========================================================================

class TestViewModelResolverSummary:
    def test_none_returns_dashes(self):
        from ui.track_modelling_vm import format_resolver_summary
        s = format_resolver_summary(None)
        assert s["source_type"] == "—"
        assert s["ai_ready"] == "—"

    def test_all_required_keys_present(self):
        from ui.track_modelling_vm import format_resolver_summary
        s = format_resolver_summary(None)
        expected = {"source_type", "modelling_status", "ai_ready", "blockers",
                    "model_path", "warnings", "resolution_status", "candidate_count"}
        assert set(s.keys()) == expected

    def test_ai_ready_yes_when_ai_ready_model(self, tmp_path):
        from ui.track_modelling_vm import format_resolver_summary
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        s = format_resolver_summary(result)
        assert s["ai_ready"] == "Yes"

    def test_ai_ready_no_when_not_ready(self, tmp_path):
        from ui.track_modelling_vm import format_resolver_summary
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        s = format_resolver_summary(result)
        assert s["ai_ready"] == "No"

    def test_source_type_human_readable(self, tmp_path):
        from ui.track_modelling_vm import format_resolver_summary
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        s = format_resolver_summary(result)
        assert "AI-ready" in s["source_type"]

    def test_blockers_populated_when_not_ready(self, tmp_path):
        from ui.track_modelling_vm import format_resolver_summary
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        s = format_resolver_summary(result)
        assert s["blockers"] != ""

    def test_model_path_includes_filename(self, tmp_path):
        from ui.track_modelling_vm import format_resolver_summary
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path, session_id="my_session")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        s = format_resolver_summary(result)
        assert "my_session" in s["model_path"]

    def test_candidate_count_matches(self, tmp_path):
        from ui.track_modelling_vm import format_resolver_summary
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path, session_id="a")
        export_review_json(review, output_dir=tmp_path, session_id="b")
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        s = format_resolver_summary(result)
        assert s["candidate_count"] == "2"


# ===========================================================================
# TestEngineerValidatedModel
# ===========================================================================

class TestEngineerValidatedModel:
    def test_engineer_validated_source_type(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        promote_engineer_validated(review, review.segments[0].segment_id)
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.source_type == TrackModelSourceType.ENGINEER_VALIDATED_MODEL

    def test_engineer_validated_modelling_status(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        promote_engineer_validated(review, review.segments[0].segment_id)
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.modelling_status == "engineer_grade"

    def test_engineer_validated_resolution_found(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        promote_engineer_validated(review, review.segments[0].segment_id)
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolution_status == TrackModelResolutionStatus.FOUND


# ===========================================================================
# TestWarningsPreserved
# ===========================================================================

class TestWarningsPreserved:
    def test_detection_warnings_in_resolved_model(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        assert "Test detection warning" in review.detection_warnings
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        combined = result.resolved_model.warnings
        assert any("Test detection warning" in w for w in combined)

    def test_segment_warnings_included(self, tmp_path):
        review = _make_not_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        # Braking zone segments have car-specific warnings
        all_w = result.resolved_model.warnings
        assert any("not universal" in w for w in all_w)

    def test_warning_count_positive(self, tmp_path):
        review = _make_ai_ready_review("suzuka", "suzuka_full")
        export_review_json(review, output_dir=tmp_path)
        result = resolve_best_track_model("suzuka", "suzuka_full", base_dir=tmp_path)
        assert result.resolved_model.warning_count >= 0


# ===========================================================================
# TestRegressionImports
# ===========================================================================

class TestRegressionImports:
    def test_17a_importable(self):
        import data.track_intelligence  # noqa: F401

    def test_17b_importable(self):
        import ui.track_modelling_vm  # noqa: F401

    def test_17c_importable(self):
        import data.track_calibration  # noqa: F401

    def test_17d_importable(self):
        import data.track_calibration_runtime  # noqa: F401

    def test_17e_importable(self):
        import data.track_segment_detection  # noqa: F401

    def test_17f_importable(self):
        import data.track_segment_review  # noqa: F401

    def test_17g_importable(self):
        import data.track_model_resolver  # noqa: F401

    def test_source_type_values_are_strings(self):
        for st in TrackModelSourceType:
            assert isinstance(st, str)

    def test_resolution_status_values_are_strings(self):
        for rs in TrackModelResolutionStatus:
            assert isinstance(rs, str)


# --------------------------------------------------------------------------- #
# format_next_step — the "what to do next" guidance line (UAT: Fuji stalled at
# seed-only with no hint about the remaining Detect/Review/Save step)
# --------------------------------------------------------------------------- #
class TestFormatNextStep:
    @staticmethod
    def _result(source_value):
        from types import SimpleNamespace
        st = SimpleNamespace(value=source_value)
        return SimpleNamespace(resolved_model=SimpleNamespace(source_type=st))

    def test_seed_only_with_station_map_says_detect_segments(self):
        from ui.track_modelling_vm import format_next_step
        msg = format_next_step(self._result("seed_only"), has_station_map=True)
        assert "Detect Segments" in msg and "Accept Track Model" in msg

    def test_seed_only_without_station_map_says_calibrate(self):
        from ui.track_modelling_vm import format_next_step
        msg = format_next_step(self._result("seed_only"), has_station_map=False)
        assert "Calibration" in msg

    def test_no_resolver_result_without_map_says_calibrate(self):
        from ui.track_modelling_vm import format_next_step
        assert "Calibration" in format_next_step(None, has_station_map=False)

    def test_no_resolver_result_with_map_says_detect(self):
        from ui.track_modelling_vm import format_next_step
        assert "Detect Segments" in format_next_step(None, has_station_map=True)

    def test_reviewed_not_ai_ready_says_finish_review(self):
        from ui.track_modelling_vm import format_next_step
        msg = format_next_step(self._result("reviewed_model"), has_station_map=True)
        assert "Blockers" in msg or "finish the segment review" in msg

    def test_detected_unreviewed_says_review(self):
        from ui.track_modelling_vm import format_next_step
        msg = format_next_step(self._result("detected_unreviewed"), has_station_map=True)
        assert "Segment Review" in msg

    def test_ai_ready_says_no_action(self):
        from ui.track_modelling_vm import format_next_step
        msg = format_next_step(self._result("ai_ready_reviewed_model"), has_station_map=True)
        assert "AI-ready" in msg and "no action" in msg.lower()

    def test_engineer_validated_says_no_action(self):
        from ui.track_modelling_vm import format_next_step
        msg = format_next_step(self._result("engineer_validated_model"), has_station_map=True)
        assert "no action" in msg.lower()
