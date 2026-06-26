"""Tests for Group 17L — Lap-Start Offset Calibration and Road-Distance Mapping.

Covers:
  - normalise_distance: normal, over-length, negative, zero, raises on bad length
  - calculate_lap_start_offset: zero offset, non-zero, model start offset, raises
  - map_road_distance_to_lap_distance: success, wrap, NO_DISTANCE_DATA, NO_TRACK_LENGTH,
    INVALID_OFFSET, wrap warning text
  - map_road_distance_to_lap_progress: progress range, clamping, wrap
  - LapStartOffsetCalibration creation helpers: create_offset_zero, from_reference_path
  - JSON export/import round-trip
  - packet_to_live_position: road_distance_m populated, paused still None
  - enrich_position_with_road_distance: enrichment, no-op cases
  - resolve_live_segment: road_distance priority, lap_progress preference, safe without calibration
  - Regression: Groups 17A–17K imports still work
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# Group A — normalise_distance
# ===========================================================================

from data.lap_distance_mapper import normalise_distance


def test_normalise_distance_normal():
    assert normalise_distance(500.0, 5800.0) == pytest.approx(500.0)


def test_normalise_distance_over_track_length():
    assert normalise_distance(6200.0, 5800.0) == pytest.approx(400.0)


def test_normalise_distance_exact_track_length_wraps_to_zero():
    assert normalise_distance(5800.0, 5800.0) == pytest.approx(0.0)


def test_normalise_distance_negative_input():
    assert normalise_distance(-100.0, 5800.0) == pytest.approx(5700.0)


def test_normalise_distance_large_negative():
    assert normalise_distance(-5800.0, 5800.0) == pytest.approx(0.0)


def test_normalise_distance_zero_input():
    assert normalise_distance(0.0, 5800.0) == pytest.approx(0.0)


def test_normalise_distance_raises_on_zero_track_length():
    with pytest.raises(ValueError):
        normalise_distance(100.0, 0.0)


def test_normalise_distance_raises_on_negative_track_length():
    with pytest.raises(ValueError):
        normalise_distance(100.0, -500.0)


# ===========================================================================
# Group B — calculate_lap_start_offset
# ===========================================================================

from data.lap_distance_mapper import calculate_lap_start_offset


def test_calculate_offset_both_zero():
    assert calculate_lap_start_offset(0.0, 0.0, 5800.0) == pytest.approx(0.0)


def test_calculate_offset_gt7_start_nonzero():
    # Calibration started where road_distance was 100 m
    assert calculate_lap_start_offset(100.0, 0.0, 5800.0) == pytest.approx(100.0)


def test_calculate_offset_model_start_nonzero_wraps():
    # model_start=100 means our ref path starts 100 m into the track.
    # offset = (0 - 100) % 5800 = 5700
    assert calculate_lap_start_offset(0.0, 100.0, 5800.0) == pytest.approx(5700.0)


def test_calculate_offset_both_equal_gives_zero():
    assert calculate_lap_start_offset(300.0, 300.0, 5800.0) == pytest.approx(0.0)


def test_calculate_offset_raises_on_zero_track_length():
    with pytest.raises(ValueError):
        calculate_lap_start_offset(0.0, 0.0, 0.0)


# ===========================================================================
# Group C — map_road_distance_to_lap_distance
# ===========================================================================

from data.lap_distance_mapper import (
    map_road_distance_to_lap_distance,
    LapDistanceMappingStatus,
)


def test_map_distance_basic_success():
    r = map_road_distance_to_lap_distance(500.0, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.MAPPED
    assert r.distance_along_lap_m == pytest.approx(500.0)
    assert r.wrapped is False
    assert r.lap_progress is None  # not set by this function


def test_map_distance_near_start_no_wrap():
    r = map_road_distance_to_lap_distance(50.0, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.MAPPED
    assert not r.wrapped


def test_map_distance_wrap_at_track_length():
    r = map_road_distance_to_lap_distance(5800.0, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.MAPPED_WITH_WRAP
    assert r.distance_along_lap_m == pytest.approx(0.0)
    assert r.wrapped is True


def test_map_distance_wrap_negative_raw():
    # offset=3200, road_distance=100 → raw = 100-3200 = -3100 → wraps
    r = map_road_distance_to_lap_distance(100.0, 3200.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.MAPPED_WITH_WRAP
    assert r.wrapped is True
    assert r.distance_along_lap_m == pytest.approx((-3100.0) % 5800.0)


def test_map_distance_none_road_distance():
    r = map_road_distance_to_lap_distance(None, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.NO_DISTANCE_DATA
    assert r.distance_along_lap_m is None


def test_map_distance_zero_track_length():
    r = map_road_distance_to_lap_distance(500.0, 0.0, 0.0)
    assert r.status == LapDistanceMappingStatus.NO_TRACK_LENGTH
    assert r.distance_along_lap_m is None


def test_map_distance_below_min_track_length():
    from data.lap_distance_mapper import LapDistanceMapperConfig
    cfg = LapDistanceMapperConfig(min_track_length_m=500.0)
    r = map_road_distance_to_lap_distance(100.0, 0.0, 200.0, config=cfg)
    assert r.status == LapDistanceMappingStatus.NO_TRACK_LENGTH


def test_map_distance_invalid_negative_offset():
    r = map_road_distance_to_lap_distance(500.0, -100.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.INVALID_OFFSET


def test_map_distance_invalid_offset_at_track_length():
    # offset must be in [0, track_length) — exactly track_length is invalid
    r = map_road_distance_to_lap_distance(500.0, 5800.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.INVALID_OFFSET


def test_map_distance_wrap_warning_text():
    r = map_road_distance_to_lap_distance(5900.0, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.MAPPED_WITH_WRAP
    assert any("wrap" in w.lower() or "Wrap" in w for w in r.warnings)


# ===========================================================================
# Group D — map_road_distance_to_lap_progress
# ===========================================================================

from data.lap_distance_mapper import map_road_distance_to_lap_progress


def test_map_progress_basic():
    r = map_road_distance_to_lap_progress(2900.0, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.MAPPED
    assert r.lap_progress == pytest.approx(0.5)
    assert r.distance_along_lap_m == pytest.approx(2900.0)


def test_map_progress_start_is_zero():
    r = map_road_distance_to_lap_progress(0.0, 0.0, 5800.0)
    assert r.lap_progress == pytest.approx(0.0)


def test_map_progress_near_end_clamped_to_one():
    # 5799m of 5800m should be ~0.9998, not > 1.0
    r = map_road_distance_to_lap_progress(5799.0, 0.0, 5800.0)
    assert r.lap_progress is not None
    assert 0.0 <= r.lap_progress <= 1.0


def test_map_progress_wrap_around():
    # road_distance=5900, offset=0, track=5800 → wraps to 100m → progress=100/5800
    r = map_road_distance_to_lap_progress(5900.0, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.MAPPED_WITH_WRAP
    assert r.lap_progress == pytest.approx(100.0 / 5800.0)


def test_map_progress_always_in_zero_to_one():
    for road_d in [-100.0, 0.0, 2900.0, 5800.0, 6000.0, 12000.0]:
        r = map_road_distance_to_lap_progress(road_d, 0.0, 5800.0)
        if r.lap_progress is not None:
            assert 0.0 <= r.lap_progress <= 1.0, (
                f"lap_progress {r.lap_progress} out of range for road_d={road_d}"
            )


def test_map_progress_none_road_distance():
    r = map_road_distance_to_lap_progress(None, 0.0, 5800.0)
    assert r.status == LapDistanceMappingStatus.NO_DISTANCE_DATA
    assert r.lap_progress is None


def test_map_progress_zero_track_length():
    r = map_road_distance_to_lap_progress(500.0, 0.0, 0.0)
    assert r.status == LapDistanceMappingStatus.NO_TRACK_LENGTH
    assert r.lap_progress is None


def test_map_progress_result_fields():
    r = map_road_distance_to_lap_progress(1000.0, 0.0, 5800.0)
    assert r.offset_m == pytest.approx(0.0)
    assert r.track_length_m == pytest.approx(5800.0)


# ===========================================================================
# Group E — Calibration creation helpers
# ===========================================================================

from data.lap_distance_mapper import (
    create_offset_zero,
    create_offset_from_reference_path,
    LapDistanceMappingConfidence,
    LapStartOffsetCalibration,
)


def test_create_offset_zero_basic():
    cal = create_offset_zero("nurburgring", "gp", 5148.0)
    assert cal.track_location_id == "nurburgring"
    assert cal.layout_id == "gp"
    assert cal.track_length_m == pytest.approx(5148.0)
    assert cal.offset_m == pytest.approx(0.0)
    assert cal.gt7_start_distance_m == pytest.approx(0.0)
    assert cal.model_start_distance_m == pytest.approx(0.0)
    assert cal.created_at != ""


def test_create_offset_zero_custom_confidence():
    cal = create_offset_zero("spa", "full", 7004.0, confidence=LapDistanceMappingConfidence.HIGH)
    assert cal.confidence == LapDistanceMappingConfidence.HIGH


def _make_mock_ref_path(loc="suzuka", lay="full", length_m=5807.0):
    """Build a minimal mock ReferencePath with two points."""
    pt_start = MagicMock()
    pt_start.distance_along_lap_m = 0.0
    pt_start.lap_progress = 0.0
    pt_end = MagicMock()
    pt_end.distance_along_lap_m = length_m
    pt_end.lap_progress = 1.0
    ref = MagicMock()
    ref.track_location_id = loc
    ref.layout_id = lay
    ref.points = [pt_start, pt_end]
    return ref


def test_create_offset_from_reference_path_basic():
    ref = _make_mock_ref_path("suzuka", "full", 5807.0)
    cal = create_offset_from_reference_path(ref)
    assert cal is not None
    assert cal.track_location_id == "suzuka"
    assert cal.layout_id == "full"
    assert cal.track_length_m == pytest.approx(5807.0)
    assert cal.offset_m == pytest.approx(0.0)
    assert cal.calibration_source == "reference_path"


def test_create_offset_from_reference_path_nonzero_gt7_start():
    ref = _make_mock_ref_path("monaco", "full", 3337.0)
    cal = create_offset_from_reference_path(ref, gt7_start_distance_m=100.0)
    assert cal is not None
    assert cal.offset_m == pytest.approx(100.0)
    assert any("100" in w for w in cal.warnings)  # warning about non-zero gt7 start


def test_create_offset_from_reference_path_none_returns_none():
    assert create_offset_from_reference_path(None) is None


def test_create_offset_from_reference_path_empty_returns_none():
    ref = MagicMock()
    ref.points = []
    assert create_offset_from_reference_path(ref) is None


def test_create_offset_from_reference_path_zero_length_returns_none():
    ref = _make_mock_ref_path("test", "test", 0.0)
    assert create_offset_from_reference_path(ref) is None


# ===========================================================================
# Group F — JSON persistence
# ===========================================================================

from data.lap_distance_mapper import (
    export_offset_calibration_json,
    import_offset_calibration_json,
)


def _make_calibration(
    loc="le_mans",
    lay="circuit",
    length_m=13626.0,
    offset_m=0.0,
) -> LapStartOffsetCalibration:
    return LapStartOffsetCalibration(
        track_location_id=loc,
        layout_id=lay,
        calibration_source="reference_path",
        track_length_m=length_m,
        gt7_start_distance_m=offset_m,
        model_start_distance_m=0.0,
        offset_m=offset_m,
        confidence=LapDistanceMappingConfidence.MEDIUM,
        sample_count=12,
        source_session_id="sess_abc123",
        created_at="2026-06-24T10:00:00+00:00",
        warnings=["test warning"],
    )


def test_export_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cal = _make_calibration()
        dest = export_offset_calibration_json(cal, output_dir=Path(tmpdir))
        assert dest.exists()
        assert "le_mans__circuit__lap_offset.json" in dest.name


def test_import_reads_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cal = _make_calibration()
        dest = export_offset_calibration_json(cal, output_dir=Path(tmpdir))
        loaded = import_offset_calibration_json(dest)
        assert loaded.track_location_id == "le_mans"
        assert loaded.track_length_m == pytest.approx(13626.0)


def test_json_round_trip_all_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        cal = _make_calibration(offset_m=250.0)
        dest = export_offset_calibration_json(cal, output_dir=Path(tmpdir))
        loaded = import_offset_calibration_json(dest)
        assert loaded.track_location_id == cal.track_location_id
        assert loaded.layout_id == cal.layout_id
        assert loaded.calibration_source == cal.calibration_source
        assert loaded.track_length_m == pytest.approx(cal.track_length_m)
        assert loaded.offset_m == pytest.approx(cal.offset_m)
        assert loaded.confidence == cal.confidence
        assert loaded.sample_count == cal.sample_count
        assert loaded.source_session_id == cal.source_session_id
        assert loaded.created_at == cal.created_at
        assert loaded.warnings == cal.warnings


def test_import_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        import_offset_calibration_json(Path("/nonexistent/path/file.json"))


# ===========================================================================
# Group G — packet_to_live_position (road_distance_m integration)
# ===========================================================================

from data.live_segment_resolver import packet_to_live_position, LivePosition


class _MockPacketWithRoadDist:
    car_on_track = True
    paused = False
    loading = False
    pos_x = 100.0
    pos_y = 5.0
    pos_z = 200.0
    speed_kmh = 180.0
    road_distance = 1500.0


class _MockPacketNoRoadDist:
    car_on_track = True
    paused = False
    loading = False
    pos_x = 100.0
    pos_y = 5.0
    pos_z = 200.0
    speed_kmh = 100.0
    # no road_distance attribute


def test_packet_to_live_position_populates_road_distance_m():
    pos = packet_to_live_position(_MockPacketWithRoadDist())
    assert pos is not None
    assert pos.road_distance_m == pytest.approx(1500.0)


def test_packet_to_live_position_road_distance_none_when_missing():
    pos = packet_to_live_position(_MockPacketNoRoadDist())
    assert pos is not None
    assert pos.road_distance_m is None


def test_packet_to_live_position_distance_along_lap_m_still_none():
    """distance_along_lap_m must NOT be set from road_distance in packet adapter."""
    pos = packet_to_live_position(_MockPacketWithRoadDist())
    assert pos is not None
    assert pos.distance_along_lap_m is None


def test_packet_to_live_position_paused_returns_none():
    pkt = MagicMock()
    pkt.car_on_track = True
    pkt.paused = True
    pkt.loading = False
    assert packet_to_live_position(pkt) is None


# ===========================================================================
# Group H — enrich_position_with_road_distance
# ===========================================================================

from data.live_segment_resolver import enrich_position_with_road_distance


def _make_cal_simple(offset_m=0.0, track_length_m=5800.0) -> LapStartOffsetCalibration:
    return LapStartOffsetCalibration(
        track_location_id="track",
        layout_id="lay",
        calibration_source="manual",
        track_length_m=track_length_m,
        gt7_start_distance_m=offset_m,
        model_start_distance_m=0.0,
        offset_m=offset_m,
        confidence=LapDistanceMappingConfidence.HIGH,
    )


def test_enrich_sets_distance_along_lap_m():
    pos = LivePosition(road_distance_m=1000.0)
    cal = _make_cal_simple(offset_m=0.0, track_length_m=5800.0)
    enriched = enrich_position_with_road_distance(pos, cal)
    assert enriched.distance_along_lap_m == pytest.approx(1000.0)


def test_enrich_no_op_when_distance_already_set():
    pos = LivePosition(road_distance_m=1000.0, distance_along_lap_m=999.0)
    cal = _make_cal_simple()
    enriched = enrich_position_with_road_distance(pos, cal)
    assert enriched.distance_along_lap_m == pytest.approx(999.0)  # unchanged


def test_enrich_no_op_when_no_calibration():
    pos = LivePosition(road_distance_m=1000.0)
    enriched = enrich_position_with_road_distance(pos, None)
    assert enriched.distance_along_lap_m is None


def test_enrich_no_op_when_no_road_distance():
    pos = LivePosition(road_distance_m=None)
    cal = _make_cal_simple()
    enriched = enrich_position_with_road_distance(pos, cal)
    assert enriched.distance_along_lap_m is None


def test_enrich_returns_new_instance_not_mutation():
    pos = LivePosition(road_distance_m=500.0)
    cal = _make_cal_simple()
    enriched = enrich_position_with_road_distance(pos, cal)
    assert enriched is not pos
    assert pos.distance_along_lap_m is None  # original unchanged


# ===========================================================================
# Group I — resolve_live_segment with offset_calibration
# ===========================================================================

def _make_reviewed_segment(
    segment_id="seg_t1",
    segment_type="braking_zone",
    display_name="T1 Braking",
    lap_progress_start=0.05,
    lap_progress_end=0.15,
    lap_progress_mid=0.10,
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


def _make_ref_path_points(n_points=100, track_length=5800.0):
    """Return a list of mock reference path points covering 0.0 to track_length."""
    points = []
    for i in range(n_points):
        pt = MagicMock()
        pt.lap_progress = i / (n_points - 1)
        pt.distance_along_lap_m = pt.lap_progress * track_length
        pt.x = float(i * 10)
        pt.y = 0.0
        pt.z = float(i * 10)
        points.append(pt)
    return points


def _resolver_with_offset_calibration(
    position: LivePosition,
    offset_calibration,
    track_length=5800.0,
):
    """Run resolve_live_segment with a mocked reviewed model and reference path."""
    from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus

    seg = _make_reviewed_segment(
        lap_progress_start=0.08,
        lap_progress_end=0.18,
        lap_progress_mid=0.13,
    )
    ref_pts = _make_ref_path_points(100, track_length)

    mock_ref_path = MagicMock()
    mock_ref_path.points = ref_pts

    mock_rm = MagicMock()
    mock_rm.reviewed_model.segments = [seg]
    mock_rm.resolved_model = MagicMock()
    mock_rm.resolved_model.source_type.value = "ai_ready"
    mock_rm.resolved_model.reviewed_model = MagicMock()
    mock_rm.resolved_model.reviewed_model.segments = [seg]
    mock_rm.warnings = []

    with patch("data.live_segment_resolver._load_reference_path", return_value=mock_ref_path), \
         patch("data.track_model_resolver.resolve_best_track_model", return_value=mock_rm):
        from data.track_model_resolver import TrackModelSourceType
        mock_rm.resolved_model.source_type = TrackModelSourceType.AI_READY_REVIEWED_MODEL
        return resolve_live_segment(
            "test_loc", "test_lay",
            position=position,
            offset_calibration=offset_calibration,
        )


def test_resolver_uses_road_distance_when_lap_progress_missing():
    """Road distance maps to ~0.13 progress → T1 Braking segment."""
    cal = _make_cal_simple(offset_m=0.0, track_length_m=5800.0)
    # 0.13 * 5800 ≈ 754m → segment range [0.08, 0.18] covers 464–1044m
    position = LivePosition(
        pos_x=754.0, pos_y=0.0, pos_z=754.0,
        road_distance_m=754.0,
    )
    result = _resolver_with_offset_calibration(position, cal)
    from data.live_segment_resolver import LiveSegmentResolutionStatus
    assert result.status == LiveSegmentResolutionStatus.MATCHED


def test_resolver_prefers_lap_progress_over_road_distance():
    """If lap_progress is already set, road_distance mapping is skipped."""
    cal = _make_cal_simple(offset_m=0.0, track_length_m=5800.0)
    # lap_progress=0.10 is directly in the segment range [0.08, 0.18]
    position = LivePosition(
        lap_progress=0.10,
        road_distance_m=99999.0,  # huge: would produce wrong result if used
    )
    result = _resolver_with_offset_calibration(position, cal)
    from data.live_segment_resolver import LiveSegmentResolutionStatus
    assert result.status == LiveSegmentResolutionStatus.MATCHED
    if result.match:
        assert result.match.source == "lap_progress"


def test_resolver_safe_when_no_offset_calibration():
    """Without calibration, road_distance_m is ignored — resolver still works via XYZ."""
    position = LivePosition(
        pos_x=754.0, pos_y=0.0, pos_z=754.0,
        road_distance_m=754.0,
    )
    result = _resolver_with_offset_calibration(position, None)
    from data.live_segment_resolver import LiveSegmentResolutionStatus
    # XYZ matching should still work
    assert result.status in (
        LiveSegmentResolutionStatus.MATCHED,
        LiveSegmentResolutionStatus.MATCHED_NEAREST,
    )


def test_resolver_road_distance_warnings_propagated():
    """Wrap-around warning from road_distance mapping should appear in result.warnings."""
    track_length = 5800.0
    cal = _make_cal_simple(offset_m=0.0, track_length_m=track_length)
    # Use a road_distance that triggers wrap-around (> track_length)
    position = LivePosition(
        road_distance_m=track_length + 500.0,  # wraps to 500m
    )
    result = _resolver_with_offset_calibration(position, cal)
    # The mapping wraps; the warning should appear somewhere
    all_warnings = list(result.warnings)
    if result.match:
        all_warnings.extend(result.match.warnings)
    # Look for a wrap-related warning
    wrap_warnings = [w for w in all_warnings if "wrap" in w.lower() or "Wrap" in w]
    assert len(wrap_warnings) > 0, f"Expected wrap warning; got: {all_warnings}"


# ===========================================================================
# Group J — load_offset_calibration_for_track
# ===========================================================================

from data.lap_distance_mapper import load_offset_calibration_for_track


def test_load_offset_calibration_returns_none_when_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_offset_calibration_for_track("nurburgring", "gp", base_dir=Path(tmpdir))
        assert result is None


def test_load_offset_calibration_returns_calibration_when_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        cal = _make_calibration("le_mans", "circuit")
        export_offset_calibration_json(cal, output_dir=Path(tmpdir))
        loaded = load_offset_calibration_for_track("le_mans", "circuit", base_dir=Path(tmpdir))
        assert loaded is not None
        assert loaded.track_location_id == "le_mans"
        assert loaded.track_length_m == pytest.approx(13626.0)


# ===========================================================================
# Group K — LapDistanceMappingResult fields
# ===========================================================================

def test_mapping_result_stores_offset_and_track_length():
    r = map_road_distance_to_lap_distance(500.0, 50.0, 5800.0)
    assert r.offset_m == pytest.approx(50.0)
    assert r.track_length_m == pytest.approx(5800.0)


def test_mapping_result_status_is_str_enum():
    r = map_road_distance_to_lap_distance(500.0, 0.0, 5800.0)
    assert isinstance(r.status, str)
    assert r.status == "mapped"


def test_mapping_status_no_distance_data_is_str():
    r = map_road_distance_to_lap_distance(None, 0.0, 5800.0)
    assert r.status == "no_distance_data"


# ===========================================================================
# Group L — LapStartOffsetCalibration field correctness
# ===========================================================================

def test_calibration_fields_preserved():
    cal = LapStartOffsetCalibration(
        track_location_id="spa",
        layout_id="full",
        calibration_source="calibration_lap",
        track_length_m=7004.0,
        gt7_start_distance_m=0.0,
        model_start_distance_m=0.0,
        offset_m=0.0,
        confidence=LapDistanceMappingConfidence.HIGH,
        sample_count=25,
        source_session_id="sess_xyz",
        created_at="2026-06-24T12:00:00+00:00",
        warnings=["warn1"],
    )
    assert cal.track_length_m == pytest.approx(7004.0)
    assert cal.sample_count == 25
    assert cal.source_session_id == "sess_xyz"
    assert "warn1" in cal.warnings


# ===========================================================================
# Group M — edge cases and config
# ===========================================================================

def test_mapper_config_default_min_track_length():
    from data.lap_distance_mapper import LapDistanceMapperConfig
    cfg = LapDistanceMapperConfig()
    assert cfg.min_track_length_m == pytest.approx(100.0)
    assert cfg.clamp_progress is True


def test_map_progress_clamp_disabled():
    from data.lap_distance_mapper import LapDistanceMapperConfig
    cfg = LapDistanceMapperConfig(clamp_progress=False)
    # Normally clamped to 1.0 — with clamp disabled, exactly 1.0 at track_length
    r = map_road_distance_to_lap_progress(5800.0, 0.0, 5800.0, config=cfg)
    # 5800 % 5800 = 0 / 5800 = 0.0 (wrapped), not > 1
    assert r.lap_progress == pytest.approx(0.0)


def test_normalise_large_multiple_wraps():
    # 3 full laps
    assert normalise_distance(5800.0 * 3, 5800.0) == pytest.approx(0.0)
    # 3.5 laps
    assert normalise_distance(5800.0 * 3.5, 5800.0) == pytest.approx(2900.0)


def test_create_offset_from_reference_path_session_id():
    ref = _make_mock_ref_path()
    cal = create_offset_from_reference_path(ref, source_session_id="sess_test")
    assert cal.source_session_id == "sess_test"


# ===========================================================================
# Regression: Groups 17A–17K imports still work
# ===========================================================================

def test_regression_17a_17k_imports():
    """Confirm all Group 17 modules import without error."""
    import data.track_calibration
    import data.track_calibration_runtime
    import data.track_segment_detection
    import data.track_segment_review
    import data.track_model_resolver
    import data.live_segment_resolver
    import data.live_segment_coaching
    import data.lap_distance_mapper


def test_live_position_has_road_distance_m_field():
    """LivePosition must have road_distance_m field (Group 17L addition)."""
    pos = LivePosition()
    assert hasattr(pos, "road_distance_m")
    assert pos.road_distance_m is None


def test_live_position_road_distance_m_is_optional():
    pos = LivePosition(road_distance_m=1234.5)
    assert pos.road_distance_m == pytest.approx(1234.5)


def test_resolve_live_segment_accepts_offset_calibration_param():
    """resolve_live_segment must accept offset_calibration without error."""
    from data.live_segment_resolver import resolve_live_segment, LiveSegmentResolutionStatus
    with patch("data.track_model_resolver.resolve_best_track_model") as mock_r:
        mock_r.return_value = MagicMock()
        mock_r.return_value.resolved_model = None
        mock_r.return_value.warnings = []
        cal = _make_cal_simple()
        result = resolve_live_segment(
            "loc", "lay",
            offset_calibration=cal,
        )
        assert result.status == LiveSegmentResolutionStatus.NO_REVIEWED_MODEL
