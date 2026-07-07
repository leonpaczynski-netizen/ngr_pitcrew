"""Group 56 — pit-lane ↔ track-progress bridge tests.

Focuses on the confidence-gating contract between the Group 56 resolver and the
Group 55 pit-lane corroboration: LOW/UNKNOWN progress never lifts pit confidence,
MEDIUM/HIGH may, and pit-lane mapping still never CREATES a pit event.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import TrackProgressConfidence  # noqa: E402
from strategy.race_strategy_replan import RaceReplanState  # noqa: E402
from strategy.race_strategy_live_state import (  # noqa: E402
    LiveReplanStateResult,
    apply_pit_lane_evidence,
    attach_track_progress,
    resolve_live_progress_evidence,
)
from strategy.race_strategy_live_replan import (  # noqa: E402
    fuji_pit_lane_mapping,
    fuji_position_at_progress,
    fuji_reference_path,
)


@pytest.fixture()
def ctx():
    c = dict(fuji_pit_lane_mapping())
    c["reference_path"] = fuji_reference_path()["reference_path"]
    return c


def _result(conf, progress_result=None, *, in_pit=False):
    r = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence=conf,
                              pit_evidence_confidence=conf, pit_in_progress=in_pit)
    if progress_result is not None:
        r = attach_track_progress(r, progress_result)
    return r


class TestConfidenceGating:
    def test_low_progress_does_not_lift(self, ctx):
        far = (fuji_position_at_progress(0.97)[0] + 45.0, 0.0,
               fuji_position_at_progress(0.97)[2])
        prog = resolve_live_progress_evidence(position=far, track_context=ctx)
        assert prog.confidence == TrackProgressConfidence.LOW
        out = apply_pit_lane_evidence(_result("LOW", prog), track_context=ctx)
        # Speed-only pit + unusable progress → no lift, stays LOW.
        assert out.pit_evidence_confidence == "LOW"
        assert out.pit_corroboration == "position_unknown"

    def test_unknown_progress_does_not_lift(self, ctx):
        prog = resolve_live_progress_evidence(position=None, track_context=ctx)
        assert prog.confidence == TrackProgressConfidence.UNKNOWN
        out = apply_pit_lane_evidence(_result("MEDIUM", prog), track_context=ctx)
        assert out.pit_evidence_confidence == "MEDIUM"
        assert out.pit_corroboration == "position_unknown"

    def test_medium_progress_may_lift(self, ctx):
        pos = fuji_position_at_progress(0.97)
        prog = resolve_live_progress_evidence(position=pos, track_context=ctx)
        assert prog.usable_for_pit
        out = apply_pit_lane_evidence(_result("MEDIUM", prog), track_context=ctx)
        assert out.pit_evidence_confidence == "HIGH"

    def test_speed_only_pit_capped_medium_even_with_high_progress(self, ctx):
        pos = fuji_position_at_progress(0.97)
        prog = resolve_live_progress_evidence(position=pos, track_context=ctx)
        assert prog.confidence == TrackProgressConfidence.HIGH
        out = apply_pit_lane_evidence(_result("LOW", prog), track_context=ctx)
        assert out.pit_evidence_confidence == "MEDIUM"  # never HIGH from a speed-only pit


class TestNeverCreatesPit:
    def test_progress_in_pit_lane_without_event_creates_nothing(self, ctx):
        # HIGH progress inside the pit lane but NO pit event (UNKNOWN tracker conf).
        pos = fuji_position_at_progress(0.97)
        prog = resolve_live_progress_evidence(position=pos, track_context=ctx)
        out = apply_pit_lane_evidence(_result("UNKNOWN", prog), track_context=ctx)
        assert out.state.pit_stops_completed is None   # not fabricated
        assert out.state.tyre_age_laps is None
        assert out.pit_evidence_confidence == "UNKNOWN"  # no event → no lift
        assert out.pit_lane_zone == "PIT_LANE"           # position still reported

    def test_progress_never_touches_pit_count(self, ctx):
        pos = fuji_position_at_progress(0.97)
        prog = resolve_live_progress_evidence(position=pos, track_context=ctx)
        base = LiveReplanStateResult(
            state=RaceReplanState(pit_stops_completed=1, tyre_age_laps=2),
            pit_state_confidence="MEDIUM")
        base = attach_track_progress(base, prog)
        out = apply_pit_lane_evidence(base, track_context=ctx)
        assert out.state.pit_stops_completed == 1
        assert out.state.tyre_age_laps == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
