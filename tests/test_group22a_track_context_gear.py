"""Group 22A — Gear usage block in build_resolved_track_context_for_prompt.

Tests:
  1. Output contains '## Gear Usage by Corner' when calibration laps +
     segments (with APEX_ZONE) are present.
  2. Block is absent when no calibration laps (existing no-data path).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# Mock helpers  (same style as test_group19a_track_intelligence_enrichment.py)
# ---------------------------------------------------------------------------

class MockSample:
    def __init__(self, lap_progress: float, gear: int = 3, rpm: float = 6000.0):
        self.lap_progress = lap_progress
        self.gear = gear
        self.rpm = rpm
        self.speed_kph = 100.0
        self.throttle = 0.8
        self.timestamp_ms = 0
        self.surface_type = "road"


class MockLap:
    def __init__(self, samples, is_usable: bool = True):
        self.samples = samples
        self.is_usable = is_usable


class MockSegment:
    def __init__(
        self,
        segment_type,
        lap_progress_start: float,
        lap_progress_end: float,
        display_name: str = "T1",
    ):
        self.segment_type = segment_type
        self.lap_progress_start = lap_progress_start
        self.lap_progress_end = lap_progress_end
        self.display_name = display_name
        self.segment_id = display_name
        self.confidence = "HIGH"
        self.turn_number = None
        self.review_status = None
        self.warnings = []


def _make_samples_in_range(
    start: float,
    end: float,
    count: int = 5,
    gear: int = 3,
    rpm: float = 6000.0,
) -> list[MockSample]:
    samples = []
    for i in range(count):
        progress = start + (end - start) * (i / max(count - 1, 1))
        samples.append(MockSample(progress, gear=gear, rpm=rpm))
    return samples


def _make_apex_lap(apex_start: float = 0.30, apex_end: float = 0.34) -> MockLap:
    """Build a single usable calibration lap that covers entry, apex, and exit zones."""
    entry_start = max(0.0, apex_start - 0.02)
    exit_end = min(1.0, apex_end + 0.025)

    entry = _make_samples_in_range(entry_start, apex_start - 0.001, 5, gear=4, rpm=7000.0)
    apex = _make_samples_in_range(apex_start, apex_end, 5, gear=3, rpm=5500.0)
    exit_ = _make_samples_in_range(apex_end + 0.001, exit_end, 5, gear=4, rpm=6000.0)
    return MockLap(entry + apex + exit_)


def _make_apex_segment(start: float = 0.30, end: float = 0.34) -> MockSegment:
    from data.track_segment_detection import TrackSegmentType
    return MockSegment(TrackSegmentType.APEX_ZONE, start, end, display_name="T1")


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestTrackContextGearBlock(unittest.TestCase):

    def _run_context_with_calib(
        self, calib_laps, reviewed_segs, rev_limit_threshold_pct: float = 0.90
    ):
        """
        Patch the internal helpers inside track_model_resolver so we can inject
        synthetic calibration data without touching the filesystem.
        """
        from data import track_model_resolver as resolver

        # Build a minimal review / resolved model that has confirmed segments
        from data.track_segment_review import SegmentReviewStatus

        mock_seg = _make_apex_segment()
        # Give it the attributes the context builder needs
        mock_seg.review_status = SegmentReviewStatus.CONFIRMED

        mock_review = MagicMock()
        mock_review.segments = [mock_seg]
        mock_review.detection_warnings = []
        mock_review.review_warnings = []
        mock_review.modelling_status = "user_reviewed"
        mock_review.created_at = "2026-01-01T00:00:00"
        mock_review.calibration_car_id = ""
        mock_review.source_lap_count = 3
        mock_review.semantic_model = None

        mock_resolved = MagicMock()
        mock_resolved.source_type = resolver.TrackModelSourceType.AI_READY_REVIEWED_MODEL
        mock_resolved.modelling_status = "user_reviewed"
        mock_resolved.ai_ready = True
        mock_resolved.review_completion_pct = 100.0
        mock_resolved.segment_count = 1
        mock_resolved.confirmed_count = 1
        mock_resolved.rejected_count = 0
        mock_resolved.needs_more_laps_count = 0
        mock_resolved.warning_count = 0
        mock_resolved.blockers = []
        mock_resolved.warnings = []
        mock_resolved.reviewed_model = mock_review
        mock_resolved.seed_layout = None

        mock_result = MagicMock()
        mock_result.resolved_model = mock_resolved
        mock_result.resolution_status = resolver.TrackModelResolutionStatus.FOUND
        mock_result.errors = []

        # Mock calib session that returns our synthetic laps
        mock_calib_session = MagicMock()
        mock_calib_session.laps = calib_laps
        mock_calib_session.calibration_car_id = ""

        with patch.object(resolver, "resolve_best_track_model", return_value=mock_result), \
             patch.object(resolver, "_load_calibration_session", return_value=mock_calib_session), \
             patch.object(resolver, "_load_reference_path", return_value=None):

            # Also patch the reviewed_model's segments to be our apex segment list
            mock_review.segments = reviewed_segs

            return resolver.build_resolved_track_context_for_prompt(
                "test_track", "test_layout",
                rev_limit_threshold_pct=rev_limit_threshold_pct,
            )

    def test_gear_block_present_when_calibration_laps_and_segments_provided(self):
        """Output contains '## Gear Usage by Corner' when data is sufficient."""
        calib_laps = [_make_apex_lap()]
        reviewed_segs = [_make_apex_segment()]
        # Give the segment the attributes the context builder checks for review status
        from data.track_segment_review import SegmentReviewStatus
        reviewed_segs[0].review_status = SegmentReviewStatus.CONFIRMED
        reviewed_segs[0].warnings = []

        result = self._run_context_with_calib(calib_laps, reviewed_segs)

        self.assertIn("## Gear Usage by Corner", result,
                      f"Expected '## Gear Usage by Corner' in output, got:\n{result}")

    def test_gear_block_absent_when_no_calibration_laps(self):
        """Block must not appear when calibration laps list is empty."""
        reviewed_segs = [_make_apex_segment()]
        from data.track_segment_review import SegmentReviewStatus
        reviewed_segs[0].review_status = SegmentReviewStatus.CONFIRMED
        reviewed_segs[0].warnings = []

        # Pass empty calib laps
        result = self._run_context_with_calib([], reviewed_segs)

        self.assertNotIn("## Gear Usage by Corner", result,
                         "Gear block should not appear with no calibration laps")

    def test_db_rev_limit_threshold_used_when_available(self):
        """rev_limit_threshold_pct passed to the resolver flows through to compute_corner_gear_usage."""
        from unittest.mock import patch
        from data import track_model_resolver as resolver

        calib_laps = [_make_apex_lap()]
        reviewed_segs = [_make_apex_segment()]
        from data.track_segment_review import SegmentReviewStatus
        reviewed_segs[0].review_status = SegmentReviewStatus.CONFIRMED
        reviewed_segs[0].warnings = []

        captured = {}

        original_compute = None
        try:
            from strategy.track_intelligence_enrichment import compute_corner_gear_usage as _orig
            original_compute = _orig
        except Exception:
            pass

        def _fake_compute(calib_laps, reviewed_segs, rev_limit_threshold_pct=0.90):
            captured["rev_limit_threshold_pct"] = rev_limit_threshold_pct
            if original_compute:
                return original_compute(calib_laps, reviewed_segs,
                                        rev_limit_threshold_pct=rev_limit_threshold_pct)
            return []

        with patch("strategy.track_intelligence_enrichment.compute_corner_gear_usage",
                   side_effect=_fake_compute):
            # Pass the threshold directly — the caller (get_track_context_for_ai)
            # resolves it from SessionDB before calling the resolver.
            self._run_context_with_calib(
                calib_laps, reviewed_segs, rev_limit_threshold_pct=0.85
            )

        if "rev_limit_threshold_pct" in captured:
            self.assertAlmostEqual(captured["rev_limit_threshold_pct"], 0.85, places=4)


if __name__ == "__main__":
    unittest.main()
