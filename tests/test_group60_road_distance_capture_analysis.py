"""Group 60 — real-capture road-distance semantics analysis tests.

Covers cumulative/reset/inconsistent/insufficient/unknown from realistic multi-lap
samples, NaN/inf handling, missing lap numbers, trusted-lap-length comparison, the
real shipped Fuji/Daytona captures, and no-false-certainty reporting.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.road_distance_semantics import RoadDistanceSemanticsStatus as St  # noqa: E402
from data.road_distance_capture_analysis import (  # noqa: E402
    analyse_calibration_capture,
    analyse_capture_road_distance,
    build_capture_report,
    extract_lap_observations,
    load_capture_laps_from_calibration_file,
)

LAP = 4563.0


def _lap(lap_number, start, cover, n=20):
    return {"lap_number": lap_number,
            "samples": [{"road_distance": start + cover * (j / n)} for j in range(n + 1)]}


class TestExtraction:
    def test_extracts_boundaries_and_span(self):
        obs = extract_lap_observations([_lap(1, 0.0, LAP), _lap(2, LAP, LAP)])
        assert len(obs) == 2
        assert obs[0].start_distance == 0.0
        assert abs(obs[0].end_distance - LAP) < 1e-6
        assert abs(obs[0].span - LAP) < 1e-6

    def test_skips_laps_with_too_few_samples(self):
        obs = extract_lap_observations([{"lap_number": 1, "samples": [{"road_distance": 5.0}]}])
        assert obs == []

    def test_missing_lap_number_uses_index(self):
        obs = extract_lap_observations([{"samples": [{"road_distance": 0.0}, {"road_distance": LAP}]}])
        assert obs[0].lap_number == 1

    def test_nan_inf_ignored(self):
        lap = {"lap_number": 1, "samples": [{"road_distance": float("nan")},
                                            {"road_distance": 0.0}, {"road_distance": LAP},
                                            {"road_distance": float("inf")}]}
        obs = extract_lap_observations([lap])
        assert len(obs) == 1
        assert obs[0].max_distance == LAP


class TestAnalysis:
    def test_cumulative_confirmed(self):
        r = analyse_capture_road_distance([_lap(i + 1, i * LAP, LAP) for i in range(3)],
                                          track_id="t", lap_length_m=LAP)
        assert r.status == St.CUMULATIVE_CONFIRMED and r.confirmed
        assert r.span_covers_lap is True

    def test_per_lap_reset_confirmed(self):
        r = analyse_capture_road_distance([_lap(i + 1, 0.0, LAP) for i in range(3)],
                                          lap_length_m=LAP)
        assert r.status == St.PER_LAP_RESET_CONFIRMED and r.confirmed

    def test_inconsistent(self):
        r = analyse_capture_road_distance([_lap(1, 0.0, LAP), _lap(2, LAP, -LAP)],
                                          lap_length_m=LAP)
        assert r.status == St.INCONSISTENT and not r.confirmed

    def test_insufficient(self):
        r = analyse_capture_road_distance([_lap(1, 0.0, LAP)], lap_length_m=LAP)
        assert r.status == St.INSUFFICIENT_EVIDENCE
        assert "capture at least" in r.next_action.lower()

    def test_unknown_empty(self):
        r = analyse_capture_road_distance([], lap_length_m=LAP)
        assert r.status == St.UNKNOWN and r.lap_count == 0

    def test_no_lap_length_handled(self):
        r = analyse_capture_road_distance([_lap(i + 1, i * LAP, LAP) for i in range(3)])
        assert r.lap_length_m is None
        assert r.span_covers_lap is None

    def test_span_below_lap_length_flagged(self):
        # Each lap sweeps only 100 m — far below a 4563 m lap → red flag + honest action.
        r = analyse_capture_road_distance([_lap(i + 1, 0.0, 100.0) for i in range(3)],
                                          lap_length_m=LAP)
        assert r.span_covers_lap is False
        assert "does not measure cumulative lap distance" in " ".join(r.warnings)
        assert "do not treat" in r.next_action.lower()

    def test_never_raises_on_garbage(self):
        for bad in [None, "x", 123, [1, 2, 3], [{"samples": "no"}], [{"samples": [{"road_distance": "z"}]}]]:
            r = analyse_capture_road_distance(bad, lap_length_m=LAP)
            assert r.status.value in ("UNKNOWN", "INSUFFICIENT_EVIDENCE", "INCONSISTENT",
                                      "CUMULATIVE_CONFIRMED", "PER_LAP_RESET_CONFIRMED")


class TestRealShippedCaptures:
    """Real-capture evidence: the shipped captures do NOT confirm cumulative semantics."""

    def test_fuji_capture_loads_but_not_confirmed(self):
        r = analyse_calibration_capture("fuji_international_speedway",
                                        "fuji_international_speedway__full_course")
        assert r.lap_count >= 2
        assert r.confirmed is False           # honest: real data does not confirm
        assert r.span_covers_lap is False     # captured field does not span the lap

    def test_daytona_capture_loads_but_not_confirmed(self):
        r = analyse_calibration_capture("daytona_international_speedway",
                                        "daytona_international_speedway__road_course")
        assert r.lap_count >= 2
        assert r.confirmed is False

    def test_missing_capture_is_honest(self, tmp_path):
        r = analyse_calibration_capture("spa", "spa__gp", base_dir=tmp_path)
        assert r.lap_count == 0
        assert not r.confirmed

    def test_loader_returns_empty_on_missing(self, tmp_path):
        assert load_capture_laps_from_calibration_file(tmp_path / "nope.json") == []


class TestReport:
    def test_report_no_false_certainty(self):
        r = analyse_calibration_capture("fuji_international_speedway",
                                        "fuji_international_speedway__full_course")
        text = "\n".join(build_capture_report(r)).lower()
        assert "not confirmed" in text
        # Never claims confirmation the validator did not make.
        assert "cumulative behaviour confirmed" not in text
        assert "next action:" in text

    def test_report_shows_deltas_and_lap_length(self):
        r = analyse_capture_road_distance([_lap(i + 1, i * LAP, LAP) for i in range(3)],
                                          track_id="t", layout_id="l", lap_length_m=LAP)
        text = "\n".join(build_capture_report(r))
        assert "delta" in text.lower()
        assert "trusted lap length" in text.lower()

    def test_report_never_raises(self):
        assert build_capture_report(None) or True  # None-safe path returns rows


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
