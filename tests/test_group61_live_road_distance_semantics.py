"""Group 61 — live road-distance semantics (raw-capture) tests.

Covers cumulative / reset / inconsistent / insufficient / non-distance-like, the
trusted lap-length comparison, and clear next-action output through the raw-live
UAT helper (same analysis flow as Group 60).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.road_distance_semantics import RoadDistanceSemanticsStatus as St  # noqa: E402
from data.road_distance_capture_analysis import build_capture_report  # noqa: E402
from ui.race_strategy_uat import run_raw_live_capture_uat as run  # noqa: E402


class TestStatuses:
    def test_cumulative_confirmed(self):
        r = run("cumulative")
        assert r.capture_status == St.CUMULATIVE_CONFIRMED and r.confirmed

    def test_per_lap_reset_confirmed(self):
        assert run("reset").capture_status == St.PER_LAP_RESET_CONFIRMED

    def test_inconsistent(self):
        assert run("inconsistent").capture_status == St.INCONSISTENT

    def test_insufficient(self):
        assert run("insufficient").capture_status == St.INSUFFICIENT_EVIDENCE

    def test_non_distance_like_matches_group60_lesson(self):
        # Tiny per-lap span vs lap length → the Fuji/Daytona lesson → NON_DISTANCE_LIKE.
        r = run("non_distance")
        assert r.capture_status == St.NON_DISTANCE_LIKE
        assert r.confirmed is False
        assert r.span_covers_lap is False


class TestReport:
    def test_trusted_lap_length_and_deltas_shown(self):
        rows = build_capture_report(run("cumulative"))
        text = "\n".join(rows).lower()
        assert "trusted lap length" in text
        assert "delta" in text
        assert "next action:" in text

    def test_non_distance_report_is_honest(self):
        rows = build_capture_report(run("non_distance"))
        text = "\n".join(rows).lower()
        assert "non_distance_like" in text
        assert "not a lap-distance measure" in text or "does not measure cumulative" in text
        assert "not changed" in text            # production behaviour statement

    def test_confirmed_report_no_over_claim(self):
        # Even a confirmed synthetic fixture keeps the capped-confidence framing.
        rows = build_capture_report(run("cumulative"))
        text = "\n".join(rows)
        assert "Capture verdict: CUMULATIVE_CONFIRMED" in text


class TestNextActionClarity:
    def test_next_action_present_for_all(self):
        for kind in ("cumulative", "reset", "inconsistent", "insufficient", "non_distance"):
            assert run(kind).next_action.strip()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
