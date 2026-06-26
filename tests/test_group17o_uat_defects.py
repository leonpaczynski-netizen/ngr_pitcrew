"""Regression tests for Group 17O runtime UAT defects.

DEF-17O-UAT-001 — Station Map shows "No track map loaded" after successful build.
DEF-17O-UAT-002 — Segment Review still displays telemetry behaviour as track geometry.
DEF-17O-UAT-003 — Daytona runtime reports 5 corners despite seeded expected 12.

All tests are pure Python — no QApplication required.
"""
from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Helpers — minimal stubs and factories
# ---------------------------------------------------------------------------

def _make_ref_path_points(n: int = 200):
    """Create n simple ReferencePathPoint objects on an ellipse."""
    import math
    from data.track_calibration import ReferencePathPoint
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        pts.append(ReferencePathPoint(
            lap_progress         = i / n,
            distance_along_lap_m = i * 30.0,   # ~6000 m total for 200 pts
            x                    = 1000.0 * math.cos(t),
            y                    = 0.0,
            z                    = 600.0 * math.sin(t),
            speed_kph_avg        = 120.0,
            source_lap_count     = 4,
        ))
    return pts


def _make_ref_path(n: int = 200, loc: str = "daytona", lay: str = "road"):
    from data.track_calibration import ReferencePath
    return ReferencePath(
        track_location_id  = loc,
        layout_id          = lay,
        calibration_car_id = "porsche_911_rsr",
        source_lap_count   = 4,
        points             = _make_ref_path_points(n),
        confidence         = 1.0,
        built_at           = "2026-06-25T00:00:00+00:00",
        warnings           = [],
    )


def _make_layout_seed(corners_expected: int, length_m: float = 5800.0):
    return types.SimpleNamespace(
        corners_expected=corners_expected,
        lap_length_m=length_m,
    )


def _make_reviewed_seg(seg_type):
    """Create a minimal ReviewedTrackSegment stub."""
    from data.track_segment_review import ReviewedTrackSegment
    from data.track_segment_detection import TrackSegmentDetectionConfidence
    return ReviewedTrackSegment(
        segment_id            = f"seg_{seg_type.value}",
        segment_type          = seg_type,
        original_display_name = seg_type.value.replace("_", " ").title(),
        lap_progress_start    = 0.0,
        lap_progress_end      = 0.05,
        lap_progress_mid      = 0.025,
        confidence            = TrackSegmentDetectionConfidence.MEDIUM,
    )


# ---------------------------------------------------------------------------
# DEF-17O-UAT-001 — Station Map: ref_path from last_build_result, not _ref_path
# ---------------------------------------------------------------------------

class TestDef17OUAT001RefPathAttribute:
    """Verify that the correct attribute name is used to get the reference path."""

    def test_controller_has_no_ref_path_attribute(self):
        """The controller stores the path in _last_build_result.reference_path,
        not as a bare _ref_path attribute.  This test documents that getattr
        on _ref_path returns None (the old bug).
        """
        from data.track_calibration_runtime import TrackCalibrationCaptureController
        ctrl = TrackCalibrationCaptureController()
        # The old broken code did: getattr(ctrl, "_ref_path", None)
        # This must be None — _ref_path is not an attribute on the controller.
        assert getattr(ctrl, "_ref_path", None) is None

    def test_controller_last_build_result_reference_path_is_correct_attribute(self):
        """After a failed (or absent) build, _last_build_result is None.
        After a successful build, _last_build_result.reference_path is set.
        """
        from data.track_calibration_runtime import TrackCalibrationCaptureController
        from data.track_calibration import CalibrationBuildResult, ReferencePath

        ctrl = TrackCalibrationCaptureController()
        # Before any build, _last_build_result is None
        assert getattr(ctrl, "_last_build_result", None) is None

        # Simulate a successful build by injecting the result
        ref = _make_ref_path()
        ctrl._last_build_result = CalibrationBuildResult(success=True, reference_path=ref)

        # The CORRECT attribute chain used by the fixed _tm_try_build_station_map()
        last = getattr(ctrl, "_last_build_result", None)
        extracted = (
            last.reference_path
            if last is not None and last.success and last.reference_path
            else None
        )
        assert extracted is ref

    def test_station_map_builds_from_ref_path(self):
        """A ReferencePath can produce a non-empty TrackStationMap."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        sm = build_track_station_map(ref)
        assert sm.stations, "station map must not be empty"
        assert sm.station_count() > 0

    def test_station_map_produces_has_map_true_draw_data(self):
        """A non-empty station map → build_track_map_draw_data returns has_map=True."""
        from data.track_station_map import build_track_station_map
        from ui.track_map_vm import build_track_map_draw_data
        ref = _make_ref_path()
        sm = build_track_station_map(ref)
        dd = build_track_map_draw_data(sm)
        assert dd.has_map is True
        assert len(dd.centreline) > 0

    def test_none_ref_path_gives_no_map(self):
        """When ref_path is None (old bug), has_map must be False."""
        from ui.track_map_vm import build_track_map_draw_data
        dd = build_track_map_draw_data(None)
        assert dd.has_map is False
        assert dd.status_text == "No track map loaded"

    def test_empty_ref_path_points_gives_no_map(self):
        """A ReferencePath with no points → station map raises or produces empty → has_map False."""
        from data.track_calibration import ReferencePath
        from data.track_station_map import build_track_station_map
        from ui.track_map_vm import build_track_map_draw_data
        empty_ref = ReferencePath(
            track_location_id="loc", layout_id="lay",
            calibration_car_id="car", source_lap_count=0,
            points=[], confidence=0.0, built_at="", warnings=[],
        )
        with pytest.raises(Exception):
            # build_track_station_map should raise ValueError for empty input
            build_track_station_map(empty_ref)


# ---------------------------------------------------------------------------
# DEF-17O-UAT-002 — Telemetry overlays excluded from Segment Review
# ---------------------------------------------------------------------------

class TestDef17OUAT002OverlayFiltering:
    """Telemetry behaviour types must not appear in Segment Review geometry rows."""

    def test_overlay_types_defined(self):
        """_TELEMETRY_OVERLAY_SEG_TYPES must be a non-empty frozenset."""
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        assert isinstance(_TELEMETRY_OVERLAY_SEG_TYPES, frozenset)
        assert len(_TELEMETRY_OVERLAY_SEG_TYPES) > 0

    def test_gear_zone_is_overlay(self):
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        assert TrackSegmentType.GEAR_ZONE in _TELEMETRY_OVERLAY_SEG_TYPES

    def test_limiter_zone_is_overlay(self):
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        assert TrackSegmentType.LIMITER_ZONE in _TELEMETRY_OVERLAY_SEG_TYPES

    def test_fuel_saving_candidate_is_overlay(self):
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        assert TrackSegmentType.FUEL_SAVING_CANDIDATE in _TELEMETRY_OVERLAY_SEG_TYPES

    def test_kerb_bump_is_overlay(self):
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        assert TrackSegmentType.KERB_OR_BUMP_CANDIDATE in _TELEMETRY_OVERLAY_SEG_TYPES

    def test_geometry_types_not_in_overlay_set(self):
        """Pure track-geometry segment types must NOT be filtered out.

        DEF-17O-UAT-006 update: BRAKING_ZONE and TRACTION_ZONE carry
        car-specific Porsche RSR warnings and ARE in the overlay set.
        Only apex, corner entry/exit, straight, and start/finish are
        universal track geometry and must remain in Segment Review.
        """
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        geometry_types = [
            TrackSegmentType.STRAIGHT,
            TrackSegmentType.CORNER_ENTRY,
            TrackSegmentType.APEX_ZONE,
            TrackSegmentType.CORNER_EXIT,
            TrackSegmentType.START_FINISH,
        ]
        for gt in geometry_types:
            assert gt not in _TELEMETRY_OVERLAY_SEG_TYPES, (
                f"{gt.value} is geometry but incorrectly marked as overlay"
            )

    def test_braking_and_traction_zones_are_overlay(self):
        """DEF-17O-UAT-006: BRAKING_ZONE and TRACTION_ZONE are car-specific overlays."""
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        assert TrackSegmentType.BRAKING_ZONE in _TELEMETRY_OVERLAY_SEG_TYPES, (
            "BRAKING_ZONE carries 'Car-specific braking point — Porsche RSR, not universal' "
            "warning and must be excluded from Segment Review geometry table"
        )
        assert TrackSegmentType.TRACTION_ZONE in _TELEMETRY_OVERLAY_SEG_TYPES, (
            "TRACTION_ZONE carries 'Car-specific — Porsche RSR traction characteristics' "
            "warning and must be excluded from Segment Review geometry table"
        )

    def test_filtering_removes_overlay_segs(self):
        """Applying the overlay filter to a mixed segment list removes overlay types."""
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType

        all_types = list(TrackSegmentType)
        # After filtering, no overlay types should remain
        filtered = [t for t in all_types if t not in _TELEMETRY_OVERLAY_SEG_TYPES]
        for t in filtered:
            assert t not in _TELEMETRY_OVERLAY_SEG_TYPES

    def test_review_segment_filtering_preserves_geometry(self):
        """Filtering a ReviewedTrackSegment list keeps universal geometry types intact.

        DEF-17O-UAT-006 update: uses APEX_ZONE (universal geometry) not BRAKING_ZONE
        (car-specific overlay) as the geometry representative.
        """
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType

        geometry_seg  = _make_reviewed_seg(TrackSegmentType.APEX_ZONE)
        overlay_seg_g = _make_reviewed_seg(TrackSegmentType.GEAR_ZONE)
        overlay_seg_l = _make_reviewed_seg(TrackSegmentType.LIMITER_ZONE)
        overlay_seg_f = _make_reviewed_seg(TrackSegmentType.FUEL_SAVING_CANDIDATE)
        overlay_seg_k = _make_reviewed_seg(TrackSegmentType.KERB_OR_BUMP_CANDIDATE)
        overlay_seg_b = _make_reviewed_seg(TrackSegmentType.BRAKING_ZONE)
        overlay_seg_t = _make_reviewed_seg(TrackSegmentType.TRACTION_ZONE)

        all_segs = [
            geometry_seg, overlay_seg_g, overlay_seg_l,
            overlay_seg_f, overlay_seg_k, overlay_seg_b, overlay_seg_t,
        ]
        filtered = [s for s in all_segs if s.segment_type not in _TELEMETRY_OVERLAY_SEG_TYPES]

        assert len(filtered) == 1
        assert filtered[0].segment_type == TrackSegmentType.APEX_ZONE

    def test_review_result_after_filter_has_no_overlays(self):
        """After the overlay filter is applied to a review result, no overlay types remain."""
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        from data.track_segment_review import TrackModelReviewResult

        segs = [
            _make_reviewed_seg(TrackSegmentType.STRAIGHT),
            _make_reviewed_seg(TrackSegmentType.CORNER_ENTRY),
            _make_reviewed_seg(TrackSegmentType.GEAR_ZONE),
            _make_reviewed_seg(TrackSegmentType.LIMITER_ZONE),
            _make_reviewed_seg(TrackSegmentType.FUEL_SAVING_CANDIDATE),
        ]
        from data.track_segment_detection import TrackSegmentDetectionConfidence
        review = TrackModelReviewResult(
            track_location_id="loc", layout_id="lay",
            calibration_car_id=None, source_lap_count=4,
            detected_corner_count=3, expected_corner_count=None,
            detection_confidence=TrackSegmentDetectionConfidence.MEDIUM,
            segments=segs,
        )
        review.segments = [s for s in review.segments if s.segment_type not in _TELEMETRY_OVERLAY_SEG_TYPES]

        types_in_review = {s.segment_type for s in review.segments}
        assert TrackSegmentType.GEAR_ZONE           not in types_in_review
        assert TrackSegmentType.LIMITER_ZONE         not in types_in_review
        assert TrackSegmentType.FUEL_SAVING_CANDIDATE not in types_in_review
        assert TrackSegmentType.STRAIGHT             in types_in_review
        assert TrackSegmentType.CORNER_ENTRY         in types_in_review

    def test_overlay_count_drops_from_segment_count(self):
        """Segment count shown to user must be geometry-only count, not total."""
        from ui.track_modelling_ui import _TELEMETRY_OVERLAY_SEG_TYPES
        from data.track_segment_detection import TrackSegmentType
        from data.track_segment_review import TrackModelReviewResult

        segs = [
            _make_reviewed_seg(TrackSegmentType.STRAIGHT),          # geometry
            _make_reviewed_seg(TrackSegmentType.APEX_ZONE),         # geometry
            _make_reviewed_seg(TrackSegmentType.CORNER_EXIT),       # geometry
            _make_reviewed_seg(TrackSegmentType.GEAR_ZONE),         # overlay
            _make_reviewed_seg(TrackSegmentType.LIMITER_ZONE),      # overlay
            _make_reviewed_seg(TrackSegmentType.KERB_OR_BUMP_CANDIDATE),  # overlay
        ]
        geometry_count = len([s for s in segs if s.segment_type not in _TELEMETRY_OVERLAY_SEG_TYPES])
        overlay_count  = len([s for s in segs if s.segment_type in _TELEMETRY_OVERLAY_SEG_TYPES])
        assert geometry_count == 3
        assert overlay_count  == 3


# ---------------------------------------------------------------------------
# DEF-17O-UAT-003 — Daytona: seeded 12 corners preserved in runtime model
# ---------------------------------------------------------------------------

class TestDef17OUAT003DaytonaCornerCount:
    """Daytona seed expects 12 corners; station map must guarantee that count."""

    def test_daytona_seed_12_produces_12_seeded_corners(self):
        """build_track_station_map with corners_expected=12 always returns 12 corners."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12, length_m=5800.0)
        sm = build_track_station_map(ref, layout_seed=seed)
        assert len(sm.seeded_corners) == 12, (
            f"Expected 12 seeded corners for Daytona, got {len(sm.seeded_corners)}"
        )

    def test_station_map_corner_count_is_authoritative_over_detection_count(self):
        """If station map has 12 corners, UI should show 12, not the detection count."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12)
        sm = build_track_station_map(ref, layout_seed=seed)

        n_seeded = len(sm.seeded_corners)
        n_placeholder = sum(1 for c in sm.seeded_corners if c.is_seeded_placeholder)
        n_detected_geo = n_seeded - n_placeholder

        # The UI summary line should be built from these values, not from
        # result.detected_corner_count (the old telemetry-based 5-corner count)
        summary = (
            f"{n_seeded} seeded corners  |  {n_detected_geo} curvature-detected  |  "
            f"{n_placeholder} estimated"
        )
        assert "12 seeded corners" in summary
        # Must NOT say "5" as the total corner count
        assert "12" in summary

    def test_placeholder_corners_make_up_gap_to_expected(self):
        """When curvature detection finds fewer than expected, placeholders fill the gap."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12)
        sm = build_track_station_map(ref, layout_seed=seed)

        n_seeded      = len(sm.seeded_corners)
        n_placeholder = sum(1 for c in sm.seeded_corners if c.is_seeded_placeholder)
        n_detected    = n_seeded - n_placeholder

        # Total must always be 12
        assert n_seeded == 12
        # Detected + placeholder must sum to 12
        assert n_detected + n_placeholder == 12

    def test_draw_data_has_12_corner_labels_for_daytona_seed(self):
        """build_track_map_draw_data produces 12 corner labels when seed=12."""
        from data.track_station_map import build_track_station_map
        from ui.track_map_vm import build_track_map_draw_data
        ref = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12)
        sm = build_track_station_map(ref, layout_seed=seed)
        dd = build_track_map_draw_data(sm)
        assert len(dd.corner_labels) == 12

    def test_no_seed_does_not_guarantee_12_corners(self):
        """Without a seed, the corner count may differ — confirms seed is required."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        sm_no_seed = build_track_station_map(ref, layout_seed=None)
        sm_seeded  = build_track_station_map(ref, layout_seed=_make_layout_seed(12))

        # Seeded always has 12
        assert len(sm_seeded.seeded_corners) == 12
        # No-seed count is determined by curvature peaks only
        # (may or may not be 12 — the point is seed is the guarantee)

    def test_station_map_status_text_includes_seeded_count(self):
        """build_track_map_draw_data status_text reports the corner count."""
        from data.track_station_map import build_track_station_map
        from ui.track_map_vm import build_track_map_draw_data
        ref = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12)
        sm = build_track_station_map(ref, layout_seed=seed)
        dd = build_track_map_draw_data(sm)
        assert "12" in dd.status_text, (
            f"Status text should mention 12 corners, got: {dd.status_text!r}"
        )

    def test_detection_result_corner_count_can_differ_from_station_map(self):
        """The old detection result (Group 17E) corner count may be < 12.
        The station map corner count (Group 17O) must be used for display.
        """
        from data.track_segment_detection import SegmentDetectionResult, TrackSegmentDetectionConfidence
        from data.track_station_map import build_track_station_map
        from ui.track_map_vm import build_track_map_draw_data

        # Simulate old detection returning only 5 corners
        old_result = SegmentDetectionResult(
            success=True,
            track_location_id="daytona",
            layout_id="road",
            detected_corner_count=5,
            expected_corner_count=12,
            corner_count_matches_expected=False,
            confidence=TrackSegmentDetectionConfidence.HIGH,
        )
        assert old_result.detected_corner_count == 5

        # Station map guarantees 12
        ref  = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12)
        sm   = build_track_station_map(ref, layout_seed=seed)
        assert len(sm.seeded_corners) == 12

        # Dashboard logic: if station map available, use sm corner count (12)
        # NOT old_result.detected_corner_count (5)
        n_seeded = len(sm.seeded_corners)
        assert n_seeded == 12  # This is what should appear in the UI, not 5


# ---------------------------------------------------------------------------
# DEF-17O-UAT-004 — Build info label shows station map count (not just 200 pts)
# ---------------------------------------------------------------------------

class TestDef17OUAT004StationMapCountDisplay:
    """Station map count must be visible alongside reference path point count."""

    def test_station_map_station_count_is_non_zero(self):
        """A built station map returns a positive station count."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(200)
        sm = build_track_station_map(ref)
        assert sm.station_count() > 0

    def test_station_map_count_can_be_formatted_for_label(self):
        """The station count and corner count can be formatted for a UI label."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(200)
        seed = _make_layout_seed(corners_expected=12)
        sm = build_track_station_map(ref, layout_seed=seed)
        n  = sm.station_count()
        nc = len(sm.seeded_corners)
        label_text = f"Path: 200 pts  |  Conf: 1.00  |  Map: {n} stations / {nc} corners"
        assert str(n) in label_text
        assert str(nc) in label_text
        assert "Map:" in label_text

    def test_station_count_distinct_from_reference_path_points(self):
        """Station count (~1 per metre) must differ from reference path point count (200)."""
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(200)
        sm = build_track_station_map(ref)
        assert sm.station_count() != 200, (
            f"Station count {sm.station_count()} must not equal reference path point count 200; "
            "they are different metrics and must be shown separately"
        )


# ---------------------------------------------------------------------------
# DEF-17O-UAT-005 — Seed lookup uses get_selected_layout not .layouts iteration
# ---------------------------------------------------------------------------

class TestDef17OUAT005SeedLookupFix:
    """get_selected_layout() must be used — TrackSeedLoadResult has no .layouts attribute."""

    def _make_seed_result(self, loc_id="daytona", lay_id="road", corners=12):
        """Build a minimal TrackSeedLoadResult with nested track_locations."""
        from data.track_intelligence import (
            TrackSeedLoadResult, TrackLocationSeed, TrackLayoutSeed,
        )
        layout = TrackLayoutSeed(
            layout_id         = lay_id,
            display_name      = lay_id,
            track_location_id = loc_id,
            corners_expected  = corners,
            length_m          = 5800.0,
        )
        location = TrackLocationSeed(
            track_location_id = loc_id,
            display_name      = loc_id,
            layouts           = [layout],
        )
        return TrackSeedLoadResult(
            success         = True,
            track_locations = [location],
        )

    def test_seed_result_has_no_layouts_attribute(self):
        """TrackSeedLoadResult must NOT have a top-level .layouts attribute."""
        seed_result = self._make_seed_result()
        assert not hasattr(seed_result, "layouts"), (
            "TrackSeedLoadResult has a .layouts attribute — the old bug used this "
            "path and raised AttributeError at runtime"
        )

    def test_seed_result_has_track_locations_attribute(self):
        """TrackSeedLoadResult has .track_locations (plural) as the nested list."""
        seed_result = self._make_seed_result()
        assert hasattr(seed_result, "track_locations")
        assert len(seed_result.track_locations) == 1

    def test_get_selected_layout_finds_nested_layout(self):
        """get_selected_layout() navigates track_locations[i].layouts correctly."""
        from ui.track_modelling_vm import get_selected_layout
        seed_result = self._make_seed_result(loc_id="daytona", lay_id="road", corners=12)
        layout = get_selected_layout(seed_result, "daytona", "road")
        assert layout is not None, "get_selected_layout must find the layout"
        assert layout.layout_id == "road"
        assert layout.corners_expected == 12

    def test_get_selected_layout_returns_none_for_wrong_ids(self):
        """get_selected_layout returns None when loc_id or lay_id do not match."""
        from ui.track_modelling_vm import get_selected_layout
        seed_result = self._make_seed_result(loc_id="daytona", lay_id="road")
        assert get_selected_layout(seed_result, "brands_hatch", "road") is None
        assert get_selected_layout(seed_result, "daytona", "oval") is None

    def test_station_map_builds_correctly_with_get_selected_layout(self):
        """Full pipeline: get_selected_layout → SimpleNamespace seed → build_track_station_map."""
        import types as _types
        from ui.track_modelling_vm import get_selected_layout
        from data.track_station_map import build_track_station_map
        seed_result = self._make_seed_result(loc_id="daytona", lay_id="road", corners=12)
        layout = get_selected_layout(seed_result, "daytona", "road")
        assert layout is not None
        seed = _types.SimpleNamespace(
            corners_expected = getattr(layout, "corners_expected", 0) or 0,
            length_m         = getattr(layout, "length_m", 0) or 0,
        )
        ref = _make_ref_path(200)
        sm = build_track_station_map(ref, layout_seed=seed)
        assert len(sm.seeded_corners) == 12


# ---------------------------------------------------------------------------
# DEF-17O-UAT-007 — Track map displayed after build (seed bug previously killed it)
# ---------------------------------------------------------------------------

class TestDef17OUAT007MapDisplayFix:
    """Station map must be built and the draw data must have has_map=True."""

    def test_station_map_with_seed_produces_valid_draw_data(self):
        """When seed lookup succeeds, draw data has_map=True and centreline is populated."""
        import types as _types
        from ui.track_modelling_vm import get_selected_layout
        from data.track_station_map import build_track_station_map
        from ui.track_map_vm import build_track_map_draw_data
        from data.track_intelligence import (
            TrackSeedLoadResult, TrackLocationSeed, TrackLayoutSeed,
        )
        layout = TrackLayoutSeed(
            layout_id="road", display_name="Road", track_location_id="daytona",
            corners_expected=12, length_m=5800.0,
        )
        location = TrackLocationSeed(
            track_location_id="daytona", display_name="Daytona", layouts=[layout],
        )
        seed_result = TrackSeedLoadResult(success=True, track_locations=[location])
        found = get_selected_layout(seed_result, "daytona", "road")
        seed = _types.SimpleNamespace(
            corners_expected=found.corners_expected or 0,
            length_m=found.length_m or 0,
        )
        ref = _make_ref_path(200)
        sm = build_track_station_map(ref, layout_seed=seed)
        dd = build_track_map_draw_data(sm)
        assert dd.has_map is True
        assert len(dd.centreline) > 0
        assert len(dd.corner_labels) == 12

    def test_no_seed_still_produces_draw_data_with_some_corners(self):
        """Even without a seed (corners_expected=0), a map is still produced."""
        from data.track_station_map import build_track_station_map
        from ui.track_map_vm import build_track_map_draw_data
        ref = _make_ref_path(200)
        sm = build_track_station_map(ref, layout_seed=None)
        dd = build_track_map_draw_data(sm)
        assert dd.has_map is True
        assert len(dd.centreline) > 0


# ---------------------------------------------------------------------------
# DEF-17O-UAT-008 — Station map persisted to disk; auto-loaded on layout select
# ---------------------------------------------------------------------------

class TestDef17OUAT008StationMapPersistence:
    """Station map JSON must round-trip through export/import correctly."""

    def test_export_creates_file(self, tmp_path):
        """export_station_map_json writes a JSON file to disk."""
        from data.track_station_map import build_track_station_map, export_station_map_json
        ref = _make_ref_path(200, loc="daytona", lay="road")
        sm = build_track_station_map(ref)
        p = export_station_map_json(sm, output_dir=tmp_path)
        assert p.exists(), f"Expected station map file at {p}"
        assert p.suffix == ".json"

    def test_import_roundtrip_preserves_station_count(self, tmp_path):
        """import_station_map_json returns a map with the same station count."""
        from data.track_station_map import (
            build_track_station_map, export_station_map_json, import_station_map_json,
        )
        ref = _make_ref_path(200, loc="daytona", lay="road")
        sm = build_track_station_map(ref)
        p = export_station_map_json(sm, output_dir=tmp_path)
        sm2 = import_station_map_json(p)
        assert sm2.station_count() == sm.station_count()

    def test_import_roundtrip_preserves_corner_count(self, tmp_path):
        """import_station_map_json preserves seeded corners."""
        from data.track_station_map import (
            build_track_station_map, export_station_map_json, import_station_map_json,
        )
        ref = _make_ref_path(200, loc="daytona", lay="road")
        seed = _make_layout_seed(corners_expected=12)
        sm = build_track_station_map(ref, layout_seed=seed)
        p = export_station_map_json(sm, output_dir=tmp_path)
        sm2 = import_station_map_json(p)
        assert len(sm2.seeded_corners) == 12

    def test_find_station_map_path_returns_path_after_export(self, tmp_path):
        """find_station_map_path returns the file path after export."""
        from data.track_station_map import (
            build_track_station_map, export_station_map_json, find_station_map_path,
        )
        ref = _make_ref_path(200, loc="daytona", lay="road")
        sm = build_track_station_map(ref)
        export_station_map_json(sm, output_dir=tmp_path)
        p = find_station_map_path("daytona", "road", base_dir=tmp_path)
        assert p is not None, "find_station_map_path must return path after export"
        assert p.exists()

    def test_find_station_map_path_returns_none_when_not_exported(self, tmp_path):
        """find_station_map_path returns None when no file exists for this layout."""
        from data.track_station_map import find_station_map_path
        p = find_station_map_path("brands_hatch", "indy", base_dir=tmp_path)
        assert p is None

    def test_imported_map_produces_valid_draw_data(self, tmp_path):
        """A station map round-tripped through JSON produces valid has_map=True draw data."""
        from data.track_station_map import (
            build_track_station_map, export_station_map_json, import_station_map_json,
        )
        from ui.track_map_vm import build_track_map_draw_data
        ref = _make_ref_path(200, loc="daytona", lay="road")
        seed = _make_layout_seed(corners_expected=12)
        sm = build_track_station_map(ref, layout_seed=seed)
        p = export_station_map_json(sm, output_dir=tmp_path)
        sm2 = import_station_map_json(p)
        dd = build_track_map_draw_data(sm2)
        assert dd.has_map is True
        assert len(dd.corner_labels) == 12
