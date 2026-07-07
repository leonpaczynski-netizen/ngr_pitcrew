"""Group 57 — live progress activation tests.

Proves a loaded approved reference path feeds the Group 56 resolver and Group 55
pit corroboration, that missing/malformed/mismatched paths degrade safely, and
that reference-path matching never creates a pit event.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import TrackProgressConfidence, resolve_live_track_progress  # noqa: E402
from data.reference_path_loader import (  # noqa: E402
    load_reference_path_file,
    load_reference_path_for_layout,
    reference_path_to_track_stations,
    validate_reference_path_identity,
)
from strategy.race_strategy_replan import RaceReplanState  # noqa: E402
from strategy.race_strategy_live_state import (  # noqa: E402
    LiveReplanStateResult,
    apply_pit_lane_evidence,
    attach_track_progress,
    resolve_live_progress_evidence,
)
from strategy.race_strategy_live_replan import fuji_pit_lane_mapping  # noqa: E402


FUJI_TRACK = "fuji_international_speedway"
FUJI_LAYOUT = "fuji_international_speedway__full_course"


@pytest.fixture(scope="module")
def fuji_asset():
    res = load_reference_path_for_layout(FUJI_TRACK, FUJI_LAYOUT)
    assert res.has_stations
    return res.asset


@pytest.fixture()
def fuji_stations(fuji_asset):
    return reference_path_to_track_stations(fuji_asset)


@pytest.fixture()
def pit_ctx():
    return fuji_pit_lane_mapping()


def _pos_at(asset, i):
    p = asset.stations[i]
    return (p["x"], p["y"], p["z"])


class TestActivation:
    def test_loaded_path_feeds_group56(self, fuji_asset, fuji_stations):
        pos = _pos_at(fuji_asset, 100)
        r = resolve_live_track_progress(pos, fuji_stations, track_id=FUJI_TRACK,
                                        lap_length_m=fuji_asset.lap_length_m)
        assert r.confidence in (TrackProgressConfidence.HIGH, TrackProgressConfidence.MEDIUM)
        assert r.has_progress

    def test_progress_matches_station_progress(self, fuji_asset, fuji_stations):
        target = fuji_asset.stations[130]
        r = resolve_live_track_progress((target["x"], target["y"], target["z"]),
                                        fuji_stations, lap_length_m=fuji_asset.lap_length_m)
        assert abs(r.progress - target["progress"]) < 0.02


class TestSafeFallback:
    def test_missing_path_preserves_group55(self, pit_ctx):
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(base, track_context=pit_ctx, live_progress=None)
        assert out.pit_corroboration == "position_unknown"
        assert out.pit_evidence_confidence == "MEDIUM"

    def test_malformed_path_unavailable(self, tmp_path):
        p = tmp_path / "x.reference_path.json"
        p.write_text("{bad", encoding="utf-8")
        res = load_reference_path_file(p)
        assert not res.has_stations
        assert reference_path_to_track_stations(res.asset) == []

    def test_identity_mismatch_caps_confidence(self, fuji_asset, fuji_stations):
        # A valid path but wrong track identity → progress must not read HIGH/MEDIUM.
        pos = _pos_at(fuji_asset, 100)
        r = resolve_live_track_progress(pos, fuji_stations, track_id="spa",
                                        lap_length_m=fuji_asset.lap_length_m,
                                        identity_ok=False)
        assert r.confidence == TrackProgressConfidence.LOW
        assert not r.usable_for_pit


class TestBridgeToPitLane:
    def test_medium_high_feeds_pit_lane(self, fuji_asset, fuji_stations, pit_ctx):
        # Fuji station near the pit-lane body (progress ~0.97) corroborates a refuel pit.
        idx = min(range(len(fuji_asset.stations)),
                  key=lambda i: abs(fuji_asset.stations[i]["progress"] - 0.97))
        pos = _pos_at(fuji_asset, idx)
        prog = resolve_live_progress_evidence(
            position=pos, reference_stations=fuji_stations,
            track_id=FUJI_TRACK, layout_id=FUJI_LAYOUT)
        assert prog.usable_for_pit
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(attach_track_progress(base, prog),
                                      track_context=pit_ctx, live_progress=None)
        assert out.pit_lane_zone == "PIT_LANE"
        assert out.pit_evidence_confidence == "HIGH"

    def test_low_progress_cannot_lift(self, fuji_asset, fuji_stations, pit_ctx):
        near = fuji_asset.stations[10]
        far = (near["x"] + 45.0, near["y"], near["z"])  # ~45 m off the path → LOW
        prog = resolve_live_progress_evidence(
            position=far, reference_stations=fuji_stations, track_id=FUJI_TRACK)
        assert prog.confidence == TrackProgressConfidence.LOW
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(attach_track_progress(base, prog),
                                      track_context=pit_ctx, live_progress=None)
        assert out.pit_corroboration == "position_unknown"
        assert out.pit_evidence_confidence == "MEDIUM"


class TestNeverCreatesPit:
    def test_progress_does_not_touch_pit_count(self, fuji_asset, fuji_stations, pit_ctx):
        idx = min(range(len(fuji_asset.stations)),
                  key=lambda i: abs(fuji_asset.stations[i]["progress"] - 0.97))
        prog = resolve_live_progress_evidence(
            position=_pos_at(fuji_asset, idx), reference_stations=fuji_stations)
        base = LiveReplanStateResult(
            state=RaceReplanState(pit_stops_completed=1, tyre_age_laps=2),
            pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(attach_track_progress(base, prog),
                                      track_context=pit_ctx, live_progress=None)
        assert out.state.pit_stops_completed == 1
        assert out.state.tyre_age_laps == 2

    def test_no_event_no_lift_even_in_pit_lane(self, fuji_asset, fuji_stations, pit_ctx):
        idx = min(range(len(fuji_asset.stations)),
                  key=lambda i: abs(fuji_asset.stations[i]["progress"] - 0.97))
        prog = resolve_live_progress_evidence(
            position=_pos_at(fuji_asset, idx), reference_stations=fuji_stations)
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="UNKNOWN")
        out = apply_pit_lane_evidence(attach_track_progress(base, prog),
                                      track_context=pit_ctx, live_progress=None)
        assert out.state.pit_stops_completed is None
        assert out.pit_evidence_confidence == "UNKNOWN"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
