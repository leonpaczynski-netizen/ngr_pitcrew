"""Group 59 — road-distance semantics validator tests.

Covers cumulative/reset detection, inconsistent/insufficient/unknown statuses,
NaN/inf/negative handling, missing lap numbers, and conservative lap-length
delta comparison.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.road_distance_semantics import (  # noqa: E402
    RoadDistanceSample as S,
    RoadDistanceSemanticsStatus as St,
    analyse_road_distance_semantics as analyse,
    build_lap_evidence,
    format_road_distance_semantics,
)

LAP = 4563.0


def _cumulative(n=3):
    return [S(i + 1, i * LAP, (i + 1) * LAP) for i in range(n)]


def _reset(n=3):
    return [S(i + 1, 0.0, LAP) for i in range(n)]


class TestDetection:
    def test_cumulative_confirmed(self):
        r = analyse(_cumulative(), LAP)
        assert r.status == St.CUMULATIVE_CONFIRMED
        assert r.appears_cumulative is True
        assert abs(r.mean_delta - LAP) < 1.0

    def test_per_lap_reset_confirmed(self):
        r = analyse(_reset(), LAP)
        assert r.status == St.PER_LAP_RESET_CONFIRMED
        assert r.appears_cumulative is False

    def test_inconsistent_on_negative_delta(self):
        r = analyse([S(1, 0.0, LAP), S(2, LAP, LAP * 0.4)], LAP)
        assert r.status == St.INCONSISTENT
        assert any("negative" in w for w in r.warnings)

    def test_inconsistent_on_wild_variation_without_lap_length(self):
        # Deltas 4563 then 9000 (not near-zero starts, not continuous) → not confirmed.
        r = analyse([S(1, 0.0, 4563.0), S(2, 100.0, 9100.0)], None)
        assert r.status in (St.INCONSISTENT, St.INSUFFICIENT_EVIDENCE)

    def test_insufficient_one_lap(self):
        r = analyse([S(1, 0.0, LAP)], LAP)
        assert r.status == St.INSUFFICIENT_EVIDENCE
        assert "second completed lap" in " ".join(r.missing)

    def test_unknown_empty(self):
        assert analyse([], LAP).status == St.UNKNOWN

    def test_unknown_all_invalid(self):
        r = analyse([S(1, float("nan"), LAP), S(2, float("inf"), LAP)], LAP)
        assert r.status == St.UNKNOWN


class TestLapEvidence:
    def test_delta_and_lap_length_match(self):
        ev = build_lap_evidence(_cumulative(), lap_length_m=LAP)
        assert len(ev) == 3
        assert all(e.matches_lap_length for e in ev)
        assert all(abs(e.delta - LAP) < 1.0 for e in ev)

    def test_no_lap_length_matches_none(self):
        ev = build_lap_evidence(_cumulative(), lap_length_m=None)
        assert all(e.matches_lap_length is None for e in ev)

    def test_missing_lap_number_uses_index(self):
        ev = build_lap_evidence([S(None, 0.0, LAP), S(None, LAP, 2 * LAP)], lap_length_m=LAP)
        assert [e.lap_number for e in ev] == [1, 2]

    def test_dict_samples_supported(self):
        ev = build_lap_evidence([{"lap_number": 1, "start_distance": 0.0, "end_distance": LAP}],
                                lap_length_m=LAP)
        assert len(ev) == 1 and ev[0].lap_number == 1

    def test_bad_values_skipped(self):
        ev = build_lap_evidence([S(1, "x", LAP), S(2, 0.0, LAP)], lap_length_m=LAP)
        assert len(ev) == 1


class TestGarbageNeverCrashes:
    @pytest.mark.parametrize("bad", [None, "x", 123, [1, 2, 3], [{"lap_number": "a"}],
                                     [S(1, float("nan"), float("inf"))]])
    def test_never_raises(self, bad):
        r = analyse(bad, LAP)
        assert r.status.value in ("UNKNOWN", "INSUFFICIENT_EVIDENCE", "INCONSISTENT",
                                  "CUMULATIVE_CONFIRMED", "PER_LAP_RESET_CONFIRMED")

    def test_negative_lap_length_ignored(self):
        r = analyse(_cumulative(), -100.0)
        # Negative lap length treated as unavailable (not a crash).
        assert r.status in (St.CUMULATIVE_CONFIRMED, St.INSUFFICIENT_EVIDENCE,
                            St.INCONSISTENT)


class TestConservativeComparison:
    def test_delta_off_lap_length_flags_warning(self):
        # Continuous + increasing but deltas far from lap length → not confirmed cumulative.
        bad = [S(1, 0.0, 3000.0), S(2, 3000.0, 6000.0), S(3, 6000.0, 9000.0)]
        r = analyse(bad, LAP)  # deltas 3000 vs lap 4563 → implausible
        assert r.status != St.CUMULATIVE_CONFIRMED
        assert any("not close to lap length" in w for w in r.warnings)


class TestRender:
    def test_format_lines(self):
        out = format_road_distance_semantics(analyse(_cumulative(), LAP))
        joined = " ".join(out["found"]).lower()
        assert "semantics" in joined
        assert "lap length" in joined

    def test_format_none_safe(self):
        out = format_road_distance_semantics(None)
        assert out["missing"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
