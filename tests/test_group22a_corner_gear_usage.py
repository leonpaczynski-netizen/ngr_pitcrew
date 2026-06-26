"""Group 22A — compute_corner_gear_usage and format_corner_gear_usage.

Tests:
  1. Returns correct apex_gear, gear ranges, apex_rpm from synthetic data.
  2. Corner with < 3 samples in any zone is omitted.
  3. limiter_approached=True when exit RPM exceeds threshold.
  4. Configurable threshold: test at 0.85 and 0.95.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from strategy.track_intelligence_enrichment import (
    compute_corner_gear_usage,
    format_corner_gear_usage,
)


# ---------------------------------------------------------------------------
# Mock helpers (same pattern as test_group19a_track_intelligence_enrichment.py)
# ---------------------------------------------------------------------------

class MockSample:
    def __init__(self, lap_progress: float, gear: int = 3, rpm: float = 6000.0):
        self.lap_progress = lap_progress
        self.gear = gear
        self.rpm = rpm
        # Other attributes expected by different enrichment functions
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
        segment_type: str,
        lap_progress_start: float,
        lap_progress_end: float,
        display_name: str = "",
    ):
        self.segment_type = segment_type
        self.lap_progress_start = lap_progress_start
        self.lap_progress_end = lap_progress_end
        self.display_name = display_name or f"Corner@{lap_progress_start:.2f}"
        self.segment_id = self.display_name
        self.confidence = "HIGH"


def _make_apex_seg(start: float, end: float, name: str = "T1") -> MockSegment:
    return MockSegment("APEX_ZONE", start, end, display_name=name)


def _make_samples_in_range(
    start: float,
    end: float,
    count: int,
    gear: int = 3,
    rpm: float = 6000.0,
) -> list[MockSample]:
    """Evenly-spaced samples within [start, end]."""
    samples = []
    for i in range(count):
        progress = start + (end - start) * (i / max(count - 1, 1))
        samples.append(MockSample(progress, gear=gear, rpm=rpm))
    return samples


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComputeCornerGearUsage(unittest.TestCase):

    def _make_standard_lap(
        self,
        apex_start: float = 0.30,
        apex_end: float = 0.34,
        entry_gear: int = 4,
        apex_gear: int = 3,
        exit_gear: int = 4,
        entry_rpm: float = 7000.0,
        apex_rpm: float = 5500.0,
        exit_rpm: float = 6000.0,
        count: int = 5,
    ) -> MockLap:
        """Create a lap with samples in entry, apex, and exit zones."""
        entry_start = max(0.0, apex_start - 0.02)
        exit_end = min(1.0, apex_end + 0.025)

        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, count, entry_gear, entry_rpm)
        apex_samples = _make_samples_in_range(apex_start, apex_end, count, apex_gear, apex_rpm)
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, count, exit_gear, exit_rpm)

        return MockLap(entry_samples + apex_samples + exit_samples)

    def test_correct_apex_gear_gear_ranges_and_rpm(self):
        """Returns correct apex_gear, entry/exit gear ranges, and apex_rpm."""
        apex_start, apex_end = 0.30, 0.34
        lap = self._make_standard_lap(
            apex_start=apex_start, apex_end=apex_end,
            entry_gear=4, apex_gear=3, exit_gear=5,
            apex_rpm=5500.0,
        )
        seg = _make_apex_seg(apex_start, apex_end, "T1")

        result = compute_corner_gear_usage([lap], [seg])

        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c["corner_id"], "T1")
        self.assertEqual(c["apex_gear"], 3)
        self.assertEqual(c["entry_gear_min"], 4)
        self.assertEqual(c["entry_gear_max"], 4)
        self.assertEqual(c["exit_gear_min"], 5)
        self.assertEqual(c["exit_gear_max"], 5)
        self.assertAlmostEqual(c["apex_rpm_avg"], 5500.0, places=0)

    def test_entry_gear_range_spans_multiple_values(self):
        """entry_gear_min and entry_gear_max reflect the actual range seen."""
        apex_start, apex_end = 0.50, 0.54
        entry_start = max(0.0, apex_start - 0.02)

        # Mix gear 4 and 5 in entry zone
        entry_samples = []
        progs = [entry_start + i * 0.004 for i in range(5)]
        for i, p in enumerate(progs):
            g = 4 if i < 3 else 5
            entry_samples.append(MockSample(p, gear=g, rpm=6000.0))

        apex_samples = _make_samples_in_range(apex_start, apex_end, 5, gear=3, rpm=5000.0)
        exit_end = min(1.0, apex_end + 0.025)
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, 5, gear=4, rpm=6000.0)

        lap = MockLap(entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T4")

        result = compute_corner_gear_usage([lap], [seg])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entry_gear_min"], 4)
        self.assertEqual(result[0]["entry_gear_max"], 5)

    def test_corner_with_fewer_than_3_entry_samples_omitted(self):
        """Corner with < 3 entry samples is omitted from output."""
        apex_start, apex_end = 0.20, 0.24
        entry_start = max(0.0, apex_start - 0.02)

        # Only 2 entry samples
        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, 2, gear=4)
        apex_samples = _make_samples_in_range(apex_start, apex_end, 5, gear=3)
        exit_end = min(1.0, apex_end + 0.025)
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, 5, gear=4)

        lap = MockLap(entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T2")

        result = compute_corner_gear_usage([lap], [seg])
        self.assertEqual(result, [])

    def test_corner_with_fewer_than_3_apex_samples_omitted(self):
        """Corner with < 3 apex samples is omitted."""
        apex_start, apex_end = 0.40, 0.44
        entry_start = max(0.0, apex_start - 0.02)

        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, 5, gear=4)
        # Only 2 apex samples
        apex_samples = _make_samples_in_range(apex_start, apex_end, 2, gear=3)
        exit_end = min(1.0, apex_end + 0.025)
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, 5, gear=4)

        lap = MockLap(entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T3")

        result = compute_corner_gear_usage([lap], [seg])
        self.assertEqual(result, [])

    def test_corner_with_fewer_than_3_exit_samples_omitted(self):
        """Corner with < 3 exit samples is omitted."""
        apex_start, apex_end = 0.60, 0.64
        entry_start = max(0.0, apex_start - 0.02)

        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, 5, gear=4)
        apex_samples = _make_samples_in_range(apex_start, apex_end, 5, gear=3)
        exit_end = min(1.0, apex_end + 0.025)
        # Only 2 exit samples
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, 2, gear=4)

        lap = MockLap(entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T5")

        result = compute_corner_gear_usage([lap], [seg])
        self.assertEqual(result, [])

    def test_limiter_approached_true_above_threshold(self):
        """limiter_approached=True when mean(exit_rpms) > threshold * global_gear_max.

        The global max for the exit gear is set by samples elsewhere in the lap
        (here at 10000 RPM). Exit samples at 9500 RPM mean 9500 > 0.90 * 10000 = 9000.
        """
        apex_start, apex_end = 0.70, 0.74
        entry_start = max(0.0, apex_start - 0.02)
        exit_end = min(1.0, apex_end + 0.025)

        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, 5, gear=4, rpm=7000.0)
        apex_samples = _make_samples_in_range(apex_start, apex_end, 5, gear=3, rpm=5500.0)
        # Exit gear 4 at 9500 RPM
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, 5, gear=4, rpm=9500.0)

        # Add a sample earlier in the lap at gear 4, 10000 RPM to set the global ceiling
        global_ceiling_sample = MockSample(0.05, gear=4, rpm=10000.0)

        lap = MockLap([global_ceiling_sample] + entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T6")

        result = compute_corner_gear_usage([lap], [seg], rev_limit_threshold_pct=0.90)

        self.assertEqual(len(result), 1)
        c = result[0]
        # Global ceiling for gear 4 = 10000; mean exit = 9500 > 0.90 * 10000 = 9000
        self.assertAlmostEqual(c["observed_ceiling_rpm"], 10000.0, places=0)
        self.assertTrue(c["limiter_approached"])

    def test_limiter_approached_false_below_threshold(self):
        """limiter_approached=False when mean(exit_rpms) <= threshold * global_gear_max.

        Global ceiling for exit gear 4 is 10000 RPM (set by a sample elsewhere).
        Exit RPMs at 5000 RPM → mean=5000, 5000 < 0.85 * 10000 = 8500 → False.
        """
        apex_start, apex_end = 0.80, 0.84
        entry_start = max(0.0, apex_start - 0.02)
        exit_end = min(1.0, apex_end + 0.025)

        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, 5, gear=4, rpm=7000.0)
        apex_samples = _make_samples_in_range(apex_start, apex_end, 5, gear=3, rpm=5500.0)
        # Exit gear 4 at low RPM (5000), well below global ceiling
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, 5, gear=4, rpm=5000.0)

        # Global ceiling sample for gear 4 at 10000 RPM
        global_ceiling_sample = MockSample(0.05, gear=4, rpm=10000.0)

        lap = MockLap([global_ceiling_sample] + entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T7")

        result_85 = compute_corner_gear_usage([lap], [seg], rev_limit_threshold_pct=0.85)
        result_95 = compute_corner_gear_usage([lap], [seg], rev_limit_threshold_pct=0.95)

        self.assertEqual(len(result_85), 1)
        self.assertFalse(result_85[0]["limiter_approached"])
        self.assertEqual(len(result_95), 1)
        self.assertFalse(result_95[0]["limiter_approached"])

    def test_threshold_85_vs_95_gives_different_results(self):
        """Threshold 0.85 may trip where 0.95 does not — confirms it is configurable.

        Global ceiling for exit gear 4 = 10000 RPM.
        Mean exit RPM = 8800.
        8800 / 10000 = 0.88 → True at 0.85, False at 0.95.
        """
        apex_start, apex_end = 0.15, 0.19
        entry_start = max(0.0, apex_start - 0.02)
        exit_end = min(1.0, apex_end + 0.025)

        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, 5, gear=5, rpm=7000.0)
        apex_samples = _make_samples_in_range(apex_start, apex_end, 5, gear=3, rpm=5000.0)
        exit_progs = [apex_end + 0.001 + i * 0.003 for i in range(5)]
        # mean = (8500*4 + 8800) / 5 = 8960 — use uniform 8800 for clarity
        # mean = 8800; global ceiling gear 4 = 10000 → ratio 0.88
        exit_rpms_vals = [8800.0, 8800.0, 8800.0, 8800.0, 8800.0]
        exit_samples = [MockSample(p, gear=4, rpm=r) for p, r in zip(exit_progs, exit_rpms_vals)]

        # Global ceiling for gear 4 at 10000 RPM set by sample at start of lap
        global_ceiling_sample = MockSample(0.05, gear=4, rpm=10000.0)

        lap = MockLap([global_ceiling_sample] + entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T8")

        result_85 = compute_corner_gear_usage([lap], [seg], rev_limit_threshold_pct=0.85)
        result_95 = compute_corner_gear_usage([lap], [seg], rev_limit_threshold_pct=0.95)

        self.assertEqual(len(result_85), 1)
        self.assertEqual(len(result_95), 1)
        # 8800 > 0.85 * 10000 = 8500 → True
        self.assertTrue(result_85[0]["limiter_approached"])
        # 8800 < 0.95 * 10000 = 9500 → False
        self.assertFalse(result_95[0]["limiter_approached"])

    def test_limiter_approached_uses_global_max_not_local_max(self):
        """Tightly clustered exit RPMs (mean ≈ local max) below global ceiling must NOT fire.

        Exit zone: all samples at 7000 RPM (mean = local max = 7000).
        Global ceiling for exit gear 4 = 10000 RPM (set by a separate sample).
        Under the old formula: mean(7000) > 0.90 * max(7000) = 6300 → incorrectly True.
        Under the new formula: 7000 > 0.90 * 10000 = 9000 → correctly False.
        """
        apex_start, apex_end = 0.45, 0.49
        entry_start = max(0.0, apex_start - 0.02)
        exit_end = min(1.0, apex_end + 0.025)

        entry_samples = _make_samples_in_range(entry_start, apex_start - 0.001, 5, gear=5, rpm=8000.0)
        apex_samples = _make_samples_in_range(apex_start, apex_end, 5, gear=3, rpm=5000.0)
        # Tightly clustered exit RPMs at 7000 — mean ≈ local max = 7000
        exit_samples = _make_samples_in_range(apex_end + 0.001, exit_end, 5, gear=4, rpm=7000.0)

        # Global ceiling sample for gear 4 at 10000 RPM
        global_ceiling_sample = MockSample(0.05, gear=4, rpm=10000.0)

        lap = MockLap([global_ceiling_sample] + entry_samples + apex_samples + exit_samples)
        seg = _make_apex_seg(apex_start, apex_end, "T_GlobalMax")

        result = compute_corner_gear_usage([lap], [seg], rev_limit_threshold_pct=0.90)

        self.assertEqual(len(result), 1)
        c = result[0]
        # Verify the ceiling used is the global max (10000), not the local exit max (7000)
        self.assertAlmostEqual(c["observed_ceiling_rpm"], 10000.0, places=0)
        # 7000 is NOT > 0.90 * 10000 = 9000
        self.assertFalse(c["limiter_approached"])

    def test_empty_when_no_apex_segments(self):
        """Returns [] when no APEX_ZONE segments are provided."""
        lap = self._make_standard_lap()
        seg = MockSegment("STRAIGHT", 0.10, 0.20, "S1")
        result = compute_corner_gear_usage([lap], [seg])
        self.assertEqual(result, [])

    def test_empty_when_no_calibration_laps(self):
        """Returns [] when calibration_laps is empty."""
        seg = _make_apex_seg(0.30, 0.34)
        result = compute_corner_gear_usage([], [seg])
        self.assertEqual(result, [])

    def test_unusable_lap_skipped(self):
        """Samples from is_usable=False laps are not counted."""
        apex_start, apex_end = 0.30, 0.34

        good_lap = self._make_standard_lap(apex_start=apex_start, apex_end=apex_end)
        bad_lap = self._make_standard_lap(apex_start=apex_start, apex_end=apex_end)
        bad_lap.is_usable = False

        seg = _make_apex_seg(apex_start, apex_end, "T9")

        # With only bad lap → all samples from good_lap pass
        result = compute_corner_gear_usage([good_lap, bad_lap], [seg])
        self.assertEqual(len(result), 1)

        # With only bad lap → no samples
        result_bad_only = compute_corner_gear_usage([bad_lap], [seg])
        self.assertEqual(result_bad_only, [])


class TestFormatCornerGearUsage(unittest.TestCase):

    def test_format_includes_corner_id_and_gears(self):
        gear_data = [
            {
                "corner_id": "T1",
                "entry_gear_min": 4,
                "entry_gear_max": 5,
                "apex_gear": 3,
                "exit_gear_min": 4,
                "exit_gear_max": 5,
                "apex_rpm_avg": 5500.0,
                "limiter_approached": False,
            }
        ]
        result = format_corner_gear_usage(gear_data)
        self.assertIn("T1", result)
        self.assertIn("entry 4–5", result)
        self.assertIn("apex 3", result)
        self.assertIn("exit 4–5", result)
        self.assertIn("5500", result)
        self.assertNotIn("limiter", result)

    def test_format_includes_limiter_note_when_true(self):
        gear_data = [
            {
                "corner_id": "T2",
                "entry_gear_min": 3,
                "entry_gear_max": 4,
                "apex_gear": 2,
                "exit_gear_min": 3,
                "exit_gear_max": 4,
                "apex_rpm_avg": 6000.0,
                "limiter_approached": True,
            }
        ]
        result = format_corner_gear_usage(gear_data)
        self.assertIn("limiter approached", result)

    def test_format_empty_list_returns_empty_string(self):
        self.assertEqual(format_corner_gear_usage([]), "")


if __name__ == "__main__":
    unittest.main()
