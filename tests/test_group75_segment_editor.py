"""UAT Finding 4 completion — interactive segment-editor operations (pure)."""
from __future__ import annotations

from data.track_segment_review import (
    TrackModelReviewResult, ReviewedTrackSegment, SegmentReviewStatus,
    SegmentReviewAction, renumber_segment, merge_segments, split_segment,
    rename_segment, reject_segment, confirm_segment,
)
from data.track_segment_detection import (
    TrackSegmentType, TrackSegmentDetectionConfidence,
)


def _seg(seg_id, stype, lo, hi, name, turn=None):
    return ReviewedTrackSegment(
        segment_id=seg_id, segment_type=stype, original_display_name=name,
        lap_progress_start=lo, lap_progress_end=hi, lap_progress_mid=(lo + hi) / 2,
        confidence=TrackSegmentDetectionConfidence.MEDIUM, turn_number=turn)


def _review():
    return TrackModelReviewResult(
        track_location_id="fuji", layout_id="full_course", calibration_car_id=None,
        source_lap_count=5, detected_corner_count=2, expected_corner_count=2,
        detection_confidence=TrackSegmentDetectionConfidence.MEDIUM,
        segments=[
            _seg("t1", TrackSegmentType.APEX_ZONE, 0.10, 0.18, "Turn 1", 1),
            _seg("t1b", TrackSegmentType.APEX_ZONE, 0.18, 0.24, "Turn 1b", 1),
            _seg("t2", TrackSegmentType.APEX_ZONE, 0.40, 0.50, "Turn 2", 2),
        ])


def test_renumber():
    r = _review()
    renumber_segment(r, "t2", 3)
    seg = next(s for s in r.segments if s.segment_id == "t2")
    assert seg.turn_number == 3
    assert seg.review_status is SegmentReviewStatus.RENAMED
    assert seg.last_action is SegmentReviewAction.RENUMBER


def test_rename_and_reject_and_confirm():
    r = _review()
    rename_segment(r, "t1", "Hairpin")
    assert next(s for s in r.segments if s.segment_id == "t1").display_name == "Hairpin"
    reject_segment(r, "t1b")
    assert next(s for s in r.segments if s.segment_id == "t1b").review_status is SegmentReviewStatus.REJECTED
    confirm_segment(r, "t2")
    assert next(s for s in r.segments if s.segment_id == "t2").review_status is SegmentReviewStatus.CONFIRMED


def test_merge_adjacent_segments():
    r = _review()
    n_before = len(r.segments)
    merge_segments(r, "t1", "t1b")
    assert len(r.segments) == n_before - 1
    assert not any(s.segment_id == "t1b" for s in r.segments)
    kept = next(s for s in r.segments if s.segment_id == "t1")
    # Span now covers both.
    assert kept.lap_progress_start == 0.10
    assert kept.lap_progress_end == 0.24
    assert kept.review_status is SegmentReviewStatus.CONFIRMED
    assert kept.last_action is SegmentReviewAction.MERGE


def test_merge_noops_on_missing_or_same():
    r = _review()
    n = len(r.segments)
    merge_segments(r, "t1", "t1")        # same id
    merge_segments(r, "t1", "nope")       # missing
    assert len(r.segments) == n


def test_split_segment():
    r = _review()
    idx = [s.segment_id for s in r.segments].index("t2")
    split_segment(r, "t2", 0.45, first_name="Turn 2 entry", second_name="Turn 2 exit")
    ids = [s.segment_id for s in r.segments]
    assert "t2" not in ids
    assert "t2__a" in ids and "t2__b" in ids
    a = next(s for s in r.segments if s.segment_id == "t2__a")
    b = next(s for s in r.segments if s.segment_id == "t2__b")
    assert a.lap_progress_start == 0.40 and a.lap_progress_end == 0.45
    assert b.lap_progress_start == 0.45 and b.lap_progress_end == 0.50
    assert a.display_name == "Turn 2 entry" and b.display_name == "Turn 2 exit"
    assert a.last_action is SegmentReviewAction.SPLIT
    # New segments inserted where the original was.
    assert [s.segment_id for s in r.segments][idx:idx + 2] == ["t2__a", "t2__b"]


def test_split_rejects_out_of_span():
    r = _review()
    n = len(r.segments)
    split_segment(r, "t2", 0.99)   # outside [0.40, 0.50]
    assert len(r.segments) == n
    assert any(s.segment_id == "t2" for s in r.segments)
