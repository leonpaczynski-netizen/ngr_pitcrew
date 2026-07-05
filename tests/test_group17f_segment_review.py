"""Group 17F — Segment Review and Track Model Approval tests.

99 tests covering:
  - SegmentReviewStatus / SegmentReviewAction enums
  - ReviewedTrackSegment / TrackModelReviewResult dataclasses
  - create_review_from_detection
  - confirm / rename / reject / mark_* / promote_engineer_validated actions
  - review_completion_pct
  - is_ai_ready (all blocker branches)
  - export_review_json / import_review_json (JSON round-trip)
  - View-model helpers: format_segment_row, format_review_summary, get_review_button_states
  - Regression: Groups 17A–17F all importable
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

from data.track_segment_review import (
    SegmentReviewStatus,
    SegmentReviewAction,
    ReviewedTrackSegment,
    TrackModelReviewResult,
    create_review_from_detection,
    confirm_segment,
    rename_segment,
    reject_segment,
    mark_needs_more_laps,
    mark_split_required,
    mark_merge_required,
    promote_engineer_validated,
    review_completion_pct,
    is_ai_ready,
    export_review_json,
    import_review_json,
)
from data.track_segment_detection import (
    DetectedTrackSegment,
    SegmentDetectionResult,
    TrackSegmentType,
    TrackSegmentDirection,
    TrackSegmentDetectionConfidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_detection_result(
    n_corners: int = 2,
    include_straight: bool = True,
    include_braking: bool = True,
    include_exit: bool = True,
    success: bool = True,
    track_loc: str = "suzuka",
    layout: str = "full",
) -> SegmentDetectionResult:
    """Build a minimal SegmentDetectionResult for testing."""
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
                warnings=["Car-specific braking point — Porsche RSR, not universal"],
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
        success=success,
        track_location_id=track_loc,
        layout_id=layout,
        segments=segments,
        detected_corner_count=n_corners,
        source_lap_count=3,
        confidence=TrackSegmentDetectionConfidence.HIGH,
        calibration_car_id="porsche_911_rsr_991_2017",
        warnings=["Test warning from detection"],
    )


def _make_review(n_corners: int = 2) -> TrackModelReviewResult:
    result = _make_detection_result(n_corners=n_corners)
    return create_review_from_detection(result)


def _apex_ids(review: TrackModelReviewResult) -> list[str]:
    return [s.segment_id for s in review.segments
            if s.segment_type == TrackSegmentType.APEX_ZONE]


# ===========================================================================
# TestSegmentReviewStatus
# ===========================================================================

class TestSegmentReviewStatus:
    def test_has_eight_values(self):
        assert len(SegmentReviewStatus) == 8

    def test_str_comparable(self):
        assert SegmentReviewStatus.UNREVIEWED == "unreviewed"
        assert SegmentReviewStatus.CONFIRMED == "confirmed"

    def test_all_string_values(self):
        for s in SegmentReviewStatus:
            assert isinstance(s.value, str)

    def test_specific_statuses_exist(self):
        expected = {
            "unreviewed", "confirmed", "renamed", "split_required",
            "merge_required", "rejected", "needs_more_laps", "engineer_validated",
        }
        assert {s.value for s in SegmentReviewStatus} == expected

    def test_enum_is_str_subclass(self):
        assert isinstance(SegmentReviewStatus.CONFIRMED, str)


# ===========================================================================
# TestSegmentReviewAction
# ===========================================================================

class TestSegmentReviewAction:
    def test_has_seven_values(self):
        assert len(SegmentReviewAction) == 7

    def test_str_comparable(self):
        assert SegmentReviewAction.CONFIRM == "confirm"
        assert SegmentReviewAction.RENAME == "rename"

    def test_all_actions_exist(self):
        expected = {
            "confirm", "rename", "reject", "mark_needs_more_laps",
            "mark_split_required", "mark_merge_required",
            "promote_engineer_validated",
        }
        assert {a.value for a in SegmentReviewAction} == expected

    def test_enum_is_str_subclass(self):
        assert isinstance(SegmentReviewAction.REJECT, str)


# ===========================================================================
# TestReviewedTrackSegment
# ===========================================================================

class TestReviewedTrackSegment:
    def _make(self, **kwargs) -> ReviewedTrackSegment:
        defaults = dict(
            segment_id="seg_001",
            segment_type=TrackSegmentType.APEX_ZONE,
            original_display_name="T1 Apex",
            lap_progress_start=0.10,
            lap_progress_end=0.12,
            lap_progress_mid=0.11,
            confidence=TrackSegmentDetectionConfidence.MEDIUM,
        )
        defaults.update(kwargs)
        return ReviewedTrackSegment(**defaults)

    def test_default_status_is_unreviewed(self):
        seg = self._make()
        assert seg.review_status == SegmentReviewStatus.UNREVIEWED

    def test_is_reviewed_false_when_unreviewed(self):
        seg = self._make()
        assert seg.is_reviewed is False

    def test_is_reviewed_true_when_confirmed(self):
        seg = self._make(review_status=SegmentReviewStatus.CONFIRMED)
        assert seg.is_reviewed is True

    def test_display_name_returns_original_when_no_override(self):
        seg = self._make()
        assert seg.display_name == "T1 Apex"

    def test_display_name_returns_reviewed_name_when_set(self):
        seg = self._make(reviewed_display_name="Turn 1 Apex (hairpin)")
        assert seg.display_name == "Turn 1 Apex (hairpin)"

    def test_default_evidence_empty(self):
        seg = self._make()
        assert seg.evidence == []

    def test_default_warnings_empty(self):
        seg = self._make()
        assert seg.warnings == []


# ===========================================================================
# TestTrackModelReviewResult
# ===========================================================================

class TestTrackModelReviewResult:
    def test_construction(self):
        r = TrackModelReviewResult(
            track_location_id="suzuka",
            layout_id="full",
            calibration_car_id="porsche",
            source_lap_count=3,
            detected_corner_count=16,
            expected_corner_count=18,
            detection_confidence=TrackSegmentDetectionConfidence.HIGH,
        )
        assert r.track_location_id == "suzuka"
        assert r.detected_corner_count == 16

    def test_segments_default_empty(self):
        r = TrackModelReviewResult(
            track_location_id="nurburgring",
            layout_id="gp",
            calibration_car_id=None,
            source_lap_count=2,
            detected_corner_count=0,
            expected_corner_count=None,
            detection_confidence=TrackSegmentDetectionConfidence.INSUFFICIENT,
        )
        assert r.segments == []

    def test_detection_warnings_default_empty(self):
        r = TrackModelReviewResult(
            track_location_id="x",
            layout_id="y",
            calibration_car_id=None,
            source_lap_count=0,
            detected_corner_count=0,
            expected_corner_count=None,
            detection_confidence=TrackSegmentDetectionConfidence.INSUFFICIENT,
        )
        assert r.detection_warnings == []

    def test_created_at_is_set(self):
        r = TrackModelReviewResult(
            track_location_id="x",
            layout_id="y",
            calibration_car_id=None,
            source_lap_count=0,
            detected_corner_count=0,
            expected_corner_count=None,
            detection_confidence=TrackSegmentDetectionConfidence.INSUFFICIENT,
        )
        assert r.created_at != ""


# ===========================================================================
# TestCreateReviewFromDetection
# ===========================================================================

class TestCreateReviewFromDetection:
    def test_creates_successfully(self):
        result = _make_detection_result()
        review = create_review_from_detection(result)
        assert isinstance(review, TrackModelReviewResult)

    def test_all_segments_start_unreviewed(self):
        review = _make_review(n_corners=3)
        assert all(s.review_status == SegmentReviewStatus.UNREVIEWED
                   for s in review.segments)

    def test_segment_count_matches_detection(self):
        result = _make_detection_result(n_corners=2)
        review = create_review_from_detection(result)
        assert len(review.segments) == len(result.segments)

    def test_track_location_id_preserved(self):
        result = _make_detection_result(track_loc="spa")
        review = create_review_from_detection(result)
        assert review.track_location_id == "spa"

    def test_layout_id_preserved(self):
        result = _make_detection_result(layout="full_layout")
        review = create_review_from_detection(result)
        assert review.layout_id == "full_layout"

    def test_detection_warnings_preserved(self):
        result = _make_detection_result()
        review = create_review_from_detection(result)
        assert "Test warning from detection" in review.detection_warnings

    def test_calibration_car_id_preserved(self):
        result = _make_detection_result()
        review = create_review_from_detection(result)
        assert review.calibration_car_id == "porsche_911_rsr_991_2017"

    def test_empty_segments_from_failed_detection(self):
        result = _make_detection_result(success=False)
        result.segments = []
        review = create_review_from_detection(result)
        assert review.segments == []

    def test_direction_preserved_as_string(self):
        result = _make_detection_result()
        review = create_review_from_detection(result)
        apex = next(s for s in review.segments
                    if s.segment_type == TrackSegmentType.APEX_ZONE)
        assert apex.direction in ("left", "right", "unknown", None)


# ===========================================================================
# TestConfirmSegment
# ===========================================================================

class TestConfirmSegment:
    def test_status_changes_to_confirmed(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        confirm_segment(review, seg_id)
        assert review.segments[0].review_status == SegmentReviewStatus.CONFIRMED

    def test_reviewed_at_is_set(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        confirm_segment(review, seg_id)
        assert review.segments[0].reviewed_at is not None

    def test_unknown_segment_id_is_safe(self):
        review = _make_review()
        confirm_segment(review, "does_not_exist")  # must not raise
        assert all(s.review_status == SegmentReviewStatus.UNREVIEWED
                   for s in review.segments)

    def test_last_action_is_confirm(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        confirm_segment(review, seg_id)
        assert review.segments[0].last_action == SegmentReviewAction.CONFIRM

    def test_display_name_unchanged(self):
        review = _make_review()
        seg = review.segments[0]
        original_name = seg.display_name
        confirm_segment(review, seg.segment_id)
        assert seg.display_name == original_name

    def test_notes_stored(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        confirm_segment(review, seg_id, notes="Looks good")
        assert review.segments[0].review_notes == "Looks good"

    def test_returns_review_object(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        ret = confirm_segment(review, seg_id)
        assert ret is review


# ===========================================================================
# TestRenameSegment
# ===========================================================================

class TestRenameSegment:
    def test_status_changes_to_renamed(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        rename_segment(review, seg_id, "Spoon Curve Entry")
        assert review.segments[0].review_status == SegmentReviewStatus.RENAMED

    def test_reviewed_display_name_changes(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        rename_segment(review, seg_id, "Degner 2")
        assert review.segments[0].reviewed_display_name == "Degner 2"

    def test_display_name_property_returns_new_name(self):
        review = _make_review()
        seg = review.segments[0]
        rename_segment(review, seg.segment_id, "130R Braking")
        assert seg.display_name == "130R Braking"

    def test_unknown_segment_id_is_safe(self):
        review = _make_review()
        rename_segment(review, "ghost_id", "Name")  # must not raise

    def test_blank_name_does_not_rename(self):
        review = _make_review()
        seg = review.segments[0]
        original = seg.display_name
        rename_segment(review, seg.segment_id, "   ")
        assert seg.review_status == SegmentReviewStatus.UNREVIEWED
        assert seg.display_name == original

    def test_last_action_is_rename(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        rename_segment(review, seg_id, "Chicane")
        assert review.segments[0].last_action == SegmentReviewAction.RENAME

    def test_reviewed_at_is_set(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        rename_segment(review, seg_id, "Chicane")
        assert review.segments[0].reviewed_at is not None


# ===========================================================================
# TestRejectSegment
# ===========================================================================

class TestRejectSegment:
    def test_status_changes_to_rejected(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        reject_segment(review, seg_id)
        assert review.segments[0].review_status == SegmentReviewStatus.REJECTED

    def test_reviewed_at_is_set(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        reject_segment(review, seg_id)
        assert review.segments[0].reviewed_at is not None

    def test_unknown_segment_id_is_safe(self):
        review = _make_review()
        reject_segment(review, "nope")  # must not raise

    def test_last_action_is_reject(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        reject_segment(review, seg_id)
        assert review.segments[0].last_action == SegmentReviewAction.REJECT


# ===========================================================================
# TestMarkNeedsMoreLaps
# ===========================================================================

class TestMarkNeedsMoreLaps:
    def test_status_changes_to_needs_more_laps(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        mark_needs_more_laps(review, seg_id)
        assert review.segments[0].review_status == SegmentReviewStatus.NEEDS_MORE_LAPS

    def test_reviewed_at_is_set(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        mark_needs_more_laps(review, seg_id)
        assert review.segments[0].reviewed_at is not None

    def test_unknown_segment_id_is_safe(self):
        review = _make_review()
        mark_needs_more_laps(review, "ghost")  # must not raise

    def test_last_action_correct(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        mark_needs_more_laps(review, seg_id)
        assert review.segments[0].last_action == SegmentReviewAction.MARK_NEEDS_MORE_LAPS


# ===========================================================================
# TestMarkSplitRequired
# ===========================================================================

class TestMarkSplitRequired:
    def test_status_changes(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        mark_split_required(review, seg_id)
        assert review.segments[0].review_status == SegmentReviewStatus.SPLIT_REQUIRED

    def test_unknown_id_safe(self):
        review = _make_review()
        mark_split_required(review, "ghost")  # must not raise

    def test_last_action_correct(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        mark_split_required(review, seg_id)
        assert review.segments[0].last_action == SegmentReviewAction.MARK_SPLIT_REQUIRED


# ===========================================================================
# TestMarkMergeRequired
# ===========================================================================

class TestMarkMergeRequired:
    def test_status_changes(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        mark_merge_required(review, seg_id)
        assert review.segments[0].review_status == SegmentReviewStatus.MERGE_REQUIRED

    def test_unknown_id_safe(self):
        review = _make_review()
        mark_merge_required(review, "ghost")  # must not raise

    def test_last_action_correct(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        mark_merge_required(review, seg_id)
        assert review.segments[0].last_action == SegmentReviewAction.MARK_MERGE_REQUIRED


# ===========================================================================
# TestPromoteEngineerValidated
# ===========================================================================

class TestPromoteEngineerValidated:
    def test_confirmed_promotes_to_validated(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        confirm_segment(review, seg_id)
        promote_engineer_validated(review, seg_id)
        assert review.segments[0].review_status == SegmentReviewStatus.ENGINEER_VALIDATED

    def test_unreviewed_not_promoted(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        promote_engineer_validated(review, seg_id)
        assert review.segments[0].review_status == SegmentReviewStatus.UNREVIEWED

    def test_unknown_id_safe(self):
        review = _make_review()
        promote_engineer_validated(review, "ghost")  # must not raise

    def test_last_action_correct(self):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        confirm_segment(review, seg_id)
        promote_engineer_validated(review, seg_id)
        assert review.segments[0].last_action == SegmentReviewAction.PROMOTE_ENGINEER_VALIDATED


# ===========================================================================
# TestReviewCompletionPct
# ===========================================================================

class TestReviewCompletionPct:
    def test_zero_reviewed_of_three(self):
        review = _make_review()
        pct = review_completion_pct(review)
        assert pct == pytest.approx(0.0)

    def test_one_reviewed_of_several(self):
        review = _make_review(n_corners=2)
        confirm_segment(review, review.segments[0].segment_id)
        pct = review_completion_pct(review)
        total = len(review.segments)
        assert pct == pytest.approx(1.0 / total * 100.0)

    def test_all_reviewed(self):
        review = _make_review()
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        assert review_completion_pct(review) == pytest.approx(100.0)

    def test_empty_review_returns_100(self):
        result = _make_detection_result()
        result.segments = []
        review = create_review_from_detection(result)
        assert review_completion_pct(review) == pytest.approx(100.0)

    def test_mixed_statuses_counted(self):
        review = _make_review(n_corners=2)
        ids = [s.segment_id for s in review.segments]
        confirm_segment(review, ids[0])
        reject_segment(review, ids[1])
        pct = review_completion_pct(review)
        total = len(review.segments)
        assert pct == pytest.approx(2.0 / total * 100.0)


# ===========================================================================
# TestIsAIReady
# ===========================================================================

class TestIsAIReady:
    def test_false_when_no_segments(self):
        result = _make_detection_result()
        result.segments = []
        review = create_review_from_detection(result)
        ready, blockers = is_ai_ready(review)
        assert ready is False
        assert blockers

    def test_false_when_unreviewed_apex_zones(self):
        review = _make_review(n_corners=2)
        # Confirm all non-apex
        for seg in review.segments:
            if seg.segment_type != TrackSegmentType.APEX_ZONE:
                confirm_segment(review, seg.segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is False
        assert any("apex" in b for b in blockers)

    def test_true_after_all_required_reviewed(self):
        review = _make_review(n_corners=2)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is True
        assert blockers == []

    def test_false_when_needs_more_laps(self):
        review = _make_review(n_corners=2)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        mark_needs_more_laps(review, review.segments[0].segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is False
        assert any("needs more laps" in b.lower() for b in blockers)

    def test_false_when_split_required(self):
        review = _make_review(n_corners=2)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        mark_split_required(review, review.segments[0].segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is False

    def test_false_when_merge_required(self):
        review = _make_review(n_corners=2)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        mark_merge_required(review, review.segments[0].segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is False

    def test_false_when_missing_key_types(self):
        result = _make_detection_result(include_straight=False, include_braking=False)
        review = create_review_from_detection(result)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is False
        assert any("not detected" in b for b in blockers)

    def test_ready_when_apex_rejected_others_confirmed(self):
        review = _make_review(n_corners=1)
        apex_ids = _apex_ids(review)
        for seg in review.segments:
            if seg.segment_id in apex_ids:
                reject_segment(review, seg.segment_id)
            else:
                confirm_segment(review, seg.segment_id)
        ready, blockers = is_ai_ready(review)
        # Apex is rejected (reviewed, not unreviewed) — apex_zone type present in detection
        assert ready is True

    def test_blockers_list_populated_when_not_ready(self):
        result = _make_detection_result()
        result.segments = []
        review = create_review_from_detection(result)
        _, blockers = is_ai_ready(review)
        assert len(blockers) > 0

    def test_empty_blockers_when_ready(self):
        review = _make_review(n_corners=1)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        _, blockers = is_ai_ready(review)
        assert blockers == []


# ===========================================================================
# TestAIReadyMissingTypes
# ===========================================================================

class TestAIReadyMissingTypes:
    def test_missing_straight_blocks(self):
        result = _make_detection_result(include_straight=False)
        review = create_review_from_detection(result)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is False
        assert any("straight" in b for b in blockers)

    def test_missing_braking_zone_does_not_block(self):
        # braking_zone is no longer a required AI-ready type — it is inferred from
        # a speed-drop threshold and is the least reliably detected, so its
        # absence must NOT block an otherwise-good model.
        result = _make_detection_result(include_braking=False)
        review = create_review_from_detection(result)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is True
        assert not any("braking_zone" in b for b in blockers)

    def test_missing_corner_exit_blocks(self):
        result = _make_detection_result(include_exit=False)
        review = create_review_from_detection(result)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        ready, blockers = is_ai_ready(review)
        assert ready is False
        assert any("corner_exit" in b for b in blockers)

    def test_all_types_present_no_type_blocker(self):
        review = _make_review(n_corners=1)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        _, blockers = is_ai_ready(review)
        type_blockers = [b for b in blockers if "not detected" in b]
        assert type_blockers == []


# ===========================================================================
# TestExportImportJSON
# ===========================================================================

class TestExportImportJSON:
    def test_creates_file(self, tmp_path):
        review = _make_review()
        out = export_review_json(review, output_dir=tmp_path, session_id="test01")
        assert out.exists()

    def test_filename_contains_location_and_layout(self, tmp_path):
        result = _make_detection_result(track_loc="monza", layout="full")
        review = create_review_from_detection(result)
        out = export_review_json(review, output_dir=tmp_path, session_id="s1")
        assert "monza" in out.name
        assert "full" in out.name

    def test_schema_in_json(self, tmp_path):
        review = _make_review()
        out = export_review_json(review, output_dir=tmp_path, session_id="s1")
        doc = json.loads(out.read_text())
        assert doc["schema"] == "track_model_review_result_v1"

    def test_roundtrip_track_location_id(self, tmp_path):
        result = _make_detection_result(track_loc="brands_hatch")
        review = create_review_from_detection(result)
        out = export_review_json(review, output_dir=tmp_path)
        loaded = import_review_json(out)
        assert loaded.track_location_id == "brands_hatch"

    def test_roundtrip_review_status(self, tmp_path):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        confirm_segment(review, seg_id)
        out = export_review_json(review, output_dir=tmp_path)
        loaded = import_review_json(out)
        first = next(s for s in loaded.segments if s.segment_id == seg_id)
        assert first.review_status == SegmentReviewStatus.CONFIRMED

    def test_roundtrip_reviewed_display_name(self, tmp_path):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        rename_segment(review, seg_id, "Spoon Curve")
        out = export_review_json(review, output_dir=tmp_path)
        loaded = import_review_json(out)
        first = next(s for s in loaded.segments if s.segment_id == seg_id)
        assert first.reviewed_display_name == "Spoon Curve"

    def test_roundtrip_detection_warnings(self, tmp_path):
        review = _make_review()
        out = export_review_json(review, output_dir=tmp_path)
        loaded = import_review_json(out)
        assert "Test warning from detection" in loaded.detection_warnings

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            import_review_json(tmp_path / "does_not_exist.json")

    def test_wrong_schema_raises_value_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"schema": "something_else", "segments": []}))
        with pytest.raises(ValueError, match="Unexpected schema"):
            import_review_json(bad)

    def test_roundtrip_last_action(self, tmp_path):
        review = _make_review()
        seg_id = review.segments[0].segment_id
        reject_segment(review, seg_id)
        out = export_review_json(review, output_dir=tmp_path)
        loaded = import_review_json(out)
        first = next(s for s in loaded.segments if s.segment_id == seg_id)
        assert first.last_action == SegmentReviewAction.REJECT


# ===========================================================================
# TestViewModelSegmentRow
# ===========================================================================

class TestViewModelSegmentRow:
    from ui.track_modelling_vm import format_segment_row as _fmt

    def _make_seg(self, **kwargs) -> ReviewedTrackSegment:
        defaults = dict(
            segment_id="s1",
            segment_type=TrackSegmentType.APEX_ZONE,
            original_display_name="T1 Apex",
            lap_progress_start=0.10,
            lap_progress_end=0.12,
            lap_progress_mid=0.11,
            confidence=TrackSegmentDetectionConfidence.HIGH,
        )
        defaults.update(kwargs)
        return ReviewedTrackSegment(**defaults)

    def test_returns_dict_with_required_keys(self):
        from ui.track_modelling_vm import format_segment_row
        seg = self._make_seg()
        row = format_segment_row(seg)
        assert set(row.keys()) >= {"name", "turn", "type", "progress", "confidence", "laps", "status", "warnings"}

    def test_unreviewed_status_label(self):
        from ui.track_modelling_vm import format_segment_row
        seg = self._make_seg()
        row = format_segment_row(seg)
        assert "Unreviewed" in row["status"]

    def test_confirmed_status_label(self):
        from ui.track_modelling_vm import format_segment_row
        seg = self._make_seg(review_status=SegmentReviewStatus.CONFIRMED)
        row = format_segment_row(seg)
        assert "Confirmed" in row["status"]

    def test_turn_number_formatted(self):
        from ui.track_modelling_vm import format_segment_row
        seg = self._make_seg(turn_number=3)
        row = format_segment_row(seg)
        assert row["turn"] == "T3"

    def test_progress_formatted(self):
        from ui.track_modelling_vm import format_segment_row
        seg = self._make_seg(lap_progress_start=0.10, lap_progress_end=0.20)
        row = format_segment_row(seg)
        assert "10.0%" in row["progress"]
        assert "20.0%" in row["progress"]

    def test_no_turn_number_is_empty_string(self):
        from ui.track_modelling_vm import format_segment_row
        seg = self._make_seg(turn_number=None)
        row = format_segment_row(seg)
        assert row["turn"] == ""

    def test_warnings_joined(self):
        from ui.track_modelling_vm import format_segment_row
        seg = self._make_seg(warnings=["W1", "W2"])
        row = format_segment_row(seg)
        assert "W1" in row["warnings"]
        assert "W2" in row["warnings"]


# ===========================================================================
# TestViewModelReviewSummary
# ===========================================================================

class TestViewModelReviewSummary:
    def test_none_returns_dashes(self):
        from ui.track_modelling_vm import format_review_summary
        summary = format_review_summary(None)
        assert summary["detected"] == "—"
        assert summary["ai_ready"] == "—"

    def test_detected_count(self):
        from ui.track_modelling_vm import format_review_summary
        review = _make_review(n_corners=2)
        summary = format_review_summary(review)
        assert summary["detected"] == str(len(review.segments))

    def test_confirmed_count(self):
        from ui.track_modelling_vm import format_review_summary
        review = _make_review(n_corners=1)
        confirm_segment(review, review.segments[0].segment_id)
        summary = format_review_summary(review)
        assert int(summary["confirmed"]) >= 1

    def test_rejected_count(self):
        from ui.track_modelling_vm import format_review_summary
        review = _make_review(n_corners=1)
        reject_segment(review, review.segments[0].segment_id)
        summary = format_review_summary(review)
        assert int(summary["rejected"]) >= 1

    def test_completion_pct_shown(self):
        from ui.track_modelling_vm import format_review_summary
        review = _make_review()
        summary = format_review_summary(review)
        assert "%" in summary["completion_pct"]

    def test_ai_ready_shown(self):
        from ui.track_modelling_vm import format_review_summary
        review = _make_review()
        summary = format_review_summary(review)
        assert summary["ai_ready"] in ("Yes", "No")

    def test_blockers_populated_when_not_ready(self):
        from ui.track_modelling_vm import format_review_summary
        review = _make_review()
        summary = format_review_summary(review)
        assert summary["blockers"] != ""


# ===========================================================================
# TestReviewButtonStates
# ===========================================================================

class TestReviewButtonStates:
    def test_none_review_all_false(self):
        from ui.track_modelling_vm import get_review_button_states
        states = get_review_button_states(None, None)
        assert all(v is False for v in states.values())

    def test_no_selection_action_buttons_false(self):
        from ui.track_modelling_vm import get_review_button_states
        review = _make_review()
        states = get_review_button_states(review, None)
        for k in ("confirm", "rename", "reject", "needs_more_laps"):
            assert states[k] is False

    def test_with_selection_action_buttons_true(self):
        from ui.track_modelling_vm import get_review_button_states
        review = _make_review()
        seg_id = review.segments[0].segment_id
        states = get_review_button_states(review, seg_id)
        assert states["confirm"] is True
        assert states["rename"] is True
        assert states["reject"] is True

    def test_save_disabled_when_none_reviewed(self):
        from ui.track_modelling_vm import get_review_button_states
        review = _make_review()
        states = get_review_button_states(review, None)
        assert states["save"] is False

    def test_save_enabled_after_one_reviewed(self):
        from ui.track_modelling_vm import get_review_button_states
        review = _make_review()
        confirm_segment(review, review.segments[0].segment_id)
        states = get_review_button_states(review, None)
        assert states["save"] is True

    def test_split_and_merge_enabled_with_selection(self):
        from ui.track_modelling_vm import get_review_button_states
        review = _make_review()
        seg_id = review.segments[0].segment_id
        states = get_review_button_states(review, seg_id)
        assert states["split_required"] is True
        assert states["merge_required"] is True

    def test_all_buttons_covered(self):
        from ui.track_modelling_vm import get_review_button_states
        review = _make_review()
        states = get_review_button_states(review, None)
        expected_keys = {"confirm", "rename", "reject", "needs_more_laps",
                         "split_required", "merge_required", "save"}
        assert set(states.keys()) == expected_keys


# ===========================================================================
# TestDetectionWarningsPreserved
# ===========================================================================

class TestDetectionWarningsPreserved:
    def test_detection_warnings_visible_in_review(self):
        result = _make_detection_result()
        result.warnings.append("Corner count mismatch warning")
        review = create_review_from_detection(result)
        assert "Corner count mismatch warning" in review.detection_warnings

    def test_car_specific_warnings_on_segments_preserved(self):
        result = _make_detection_result(include_braking=True)
        review = create_review_from_detection(result)
        braking_segs = [s for s in review.segments
                        if s.segment_type == TrackSegmentType.BRAKING_ZONE]
        assert braking_segs, "Expected braking zone segments"
        assert any("Porsche RSR" in w
                   for seg in braking_segs
                   for w in seg.warnings), "Car-specific warning should be preserved"

    def test_review_all_confirmed_warnings_still_present(self):
        result = _make_detection_result()
        review = create_review_from_detection(result)
        for seg in review.segments:
            confirm_segment(review, seg.segment_id)
        assert review.detection_warnings  # not cleared by confirmation


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

    def test_review_status_values_are_strings(self):
        for s in SegmentReviewStatus:
            assert isinstance(s, str)

    def test_review_action_values_are_strings(self):
        for a in SegmentReviewAction:
            assert isinstance(a, str)
