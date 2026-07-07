"""Group 58 — pure road-distance fallback resolver tests.

Covers confidence rules (never HIGH), NaN/inf/negative rejection, missing/invalid
lap length, wrapping, identity mismatch, and honest labelling.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import TrackProgressConfidence  # noqa: E402
from data.live_track_progress_fallback import (  # noqa: E402
    FALLBACK_SOURCE,
    format_road_distance_fallback_evidence,
    is_fallback_result,
    resolve_progress_from_road_distance,
)

LAP = 4563.0


class TestConfidence:
    def test_accurate_lap_distance_is_medium(self):
        r = resolve_progress_from_road_distance(lap_distance_m=LAP / 2, lap_length_m=LAP)
        assert r.confidence == TrackProgressConfidence.MEDIUM
        assert abs(r.progress - 0.5) < 1e-6
        assert r.source == FALLBACK_SOURCE

    def test_cumulative_only_is_low(self):
        r = resolve_progress_from_road_distance(road_distance=LAP * 3 + LAP / 4, lap_length_m=LAP)
        assert r.confidence == TrackProgressConfidence.LOW
        assert abs(r.progress - 0.25) < 1e-6

    def test_wrapped_lap_distance_is_low(self):
        r = resolve_progress_from_road_distance(lap_distance_m=LAP + 500.0, lap_length_m=LAP)
        assert r.confidence == TrackProgressConfidence.LOW
        assert any("wrapped" in w for w in r.warnings)

    def test_never_high(self):
        for kwargs in ({"lap_distance_m": 100.0}, {"road_distance": 100.0},
                       {"lap_distance_m": LAP + 1}, {"lap_distance_m": 0.0}):
            r = resolve_progress_from_road_distance(lap_length_m=LAP, **kwargs)
            assert r.confidence != TrackProgressConfidence.HIGH


class TestUnknown:
    def test_identity_mismatch_unknown(self):
        r = resolve_progress_from_road_distance(lap_distance_m=100.0, lap_length_m=LAP,
                                                identity_ok=False)
        assert r.confidence == TrackProgressConfidence.UNKNOWN
        assert r.progress is None
        assert any("mismatch" in w for w in r.warnings)

    def test_missing_lap_length(self):
        r = resolve_progress_from_road_distance(lap_distance_m=100.0, lap_length_m=None)
        assert r.confidence == TrackProgressConfidence.UNKNOWN
        assert any("lap length unavailable" in w for w in r.warnings)

    def test_zero_negative_lap_length(self):
        for lap in (0.0, -100.0):
            r = resolve_progress_from_road_distance(lap_distance_m=100.0, lap_length_m=lap)
            assert r.confidence == TrackProgressConfidence.UNKNOWN

    def test_missing_road_distance(self):
        r = resolve_progress_from_road_distance(lap_length_m=LAP)
        assert r.confidence == TrackProgressConfidence.UNKNOWN
        assert any("road-distance signal unavailable" in w for w in r.warnings)


class TestGarbageNeverCrashes:
    def test_nan_inf_negative(self):
        bad = [float("nan"), float("inf"), float("-inf"), -5.0, "x", None, [1]]
        for d in bad:
            for lap in bad + [LAP]:
                r = resolve_progress_from_road_distance(
                    lap_distance_m=d, road_distance=d, lap_length_m=lap)
                assert r.confidence.value in ("UNKNOWN", "LOW", "MEDIUM")
                assert r.confidence != TrackProgressConfidence.HIGH

    def test_negative_falls_through_to_unknown(self):
        r = resolve_progress_from_road_distance(lap_distance_m=-1.0, road_distance=-1.0,
                                                lap_length_m=LAP)
        assert r.confidence == TrackProgressConfidence.UNKNOWN


class TestNormalisation:
    def test_progress_in_unit_interval(self):
        for d in (0.0, LAP / 3, LAP - 1, LAP * 5 + 10):
            r = resolve_progress_from_road_distance(road_distance=d, lap_length_m=LAP)
            if r.progress is not None:
                assert 0.0 <= r.progress < 1.0


class TestLabelling:
    def test_source_and_evidence_labelled(self):
        r = resolve_progress_from_road_distance(lap_distance_m=LAP / 2, lap_length_m=LAP)
        assert is_fallback_result(r)
        ev = format_road_distance_fallback_evidence(r)
        joined = " ".join(ev["found"]).lower()
        assert "road-distance fallback" in joined
        assert "lower confidence" in joined
        assert any("approved reference path unavailable" in f for f in ev["found"])

    def test_unknown_evidence_is_missing(self):
        r = resolve_progress_from_road_distance(lap_length_m=None)
        ev = format_road_distance_fallback_evidence(r)
        assert ev["found"] == []
        assert ev["missing"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
