"""Group 60 — real-capture UAT helper tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.road_distance_semantics import RoadDistanceSemanticsStatus as St  # noqa: E402
from data.road_distance_capture_analysis import build_capture_report  # noqa: E402
from ui.race_strategy_uat import run_real_capture_road_distance_uat as run  # noqa: E402


class TestSyntheticFixtures:
    def test_cumulative(self):
        assert run("cumulative").status == St.CUMULATIVE_CONFIRMED

    def test_reset(self):
        assert run("reset").status == St.PER_LAP_RESET_CONFIRMED

    def test_inconsistent(self):
        assert run("inconsistent").status == St.INCONSISTENT

    def test_insufficient(self):
        assert run("insufficient").status == St.INSUFFICIENT_EVIDENCE

    def test_unknown(self):
        assert run("unknown").status == St.UNKNOWN

    def test_empty_no_crash(self):
        r = run("empty")
        assert r.status == St.UNKNOWN and r.lap_count == 0


class TestRealCaptures:
    def test_fuji_real_capture(self):
        r = run("fuji")
        assert r.lap_count >= 2
        assert r.confirmed is False   # honest

    def test_daytona_real_capture(self):
        r = run("daytona")
        assert r.lap_count >= 2
        assert r.confirmed is False


class TestNextAction:
    def test_clear_next_action_present(self):
        for kind in ("fuji", "daytona", "cumulative", "reset", "inconsistent",
                     "insufficient", "unknown", "empty"):
            assert run(kind).next_action.strip()

    def test_report_renders(self):
        rows = build_capture_report(run("fuji"))
        assert any("Next action:" in r for r in rows)
        assert any("Semantics status:" in r for r in rows)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
