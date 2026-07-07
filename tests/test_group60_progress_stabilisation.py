"""Group 60 — correctness-preserving live-progress stabilisation tests.

Proves the global nearest is always the returned match (safe on crossings/parallel
sections), continuity reduces jitter without lying, implausible jumps downgrade
confidence (never inflate), lap wrap is handled, and fallback / pit invariants hold.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import (  # noqa: E402
    LiveTrackProgressResult, TrackProgressConfidence as C,
    build_track_path_stations, nearest_station, resolve_live_track_progress,
)
from data.live_track_progress_fallback import resolve_progress_from_road_distance  # noqa: E402
from data.live_progress_stabiliser import (  # noqa: E402
    nearest_station_stabilised, stabilise_progress,
)

LAP = 4563.0


def _straight(n=21, spacing=10.0):
    pts = [{"x": i * spacing, "y": 0.0, "z": 0.0, "distance_along_lap_m": i * spacing,
            "lap_progress": i / (n - 1)} for i in range(n)]
    return build_track_path_stations({"reference_path": {"points": pts}})


def _crossing():
    """A path that returns near an earlier point (a crossing/parallel section)."""
    pts = []
    for i in range(11):          # go out along +x
        pts.append({"x": i * 10.0, "y": 0.0, "z": 0.0,
                    "distance_along_lap_m": i * 10.0, "lap_progress": i / 20.0})
    for i in range(1, 11):       # come back parallel, 3 m away in z
        pts.append({"x": (10 - i) * 10.0, "y": 0.0, "z": 3.0,
                    "distance_along_lap_m": (10 + i) * 10.0, "lap_progress": (10 + i) / 20.0})
    return build_track_path_stations({"reference_path": {"points": pts}})


class TestGlobalNearestWins:
    def test_global_wins_over_bad_hint(self):
        st = _straight()
        # Car at station 3 (x=30) but hint points to station 18 → global (3) must win.
        out = nearest_station_stabilised((30.0, 0.0, 1.0), st, hint_index=18, window=3)
        assert out is not None
        idx, dist, continuity = out
        assert idx == nearest_station((30.0, 0.0, 1.0), st)[0] == 3
        assert continuity is False

    def test_continuity_true_when_hint_correct(self):
        st = _straight()
        out = nearest_station_stabilised((30.0, 0.0, 1.0), st, hint_index=3, window=3)
        assert out[0] == 3 and out[2] is True

    def test_crossing_section_returns_global_not_local(self):
        st = _crossing()
        # Point on the OUTbound leg near station 2 (x=20, z=0). A hint stuck on the
        # inbound parallel leg must NOT drag the match there — global wins.
        pos = (20.0, 0.0, 0.0)
        g = nearest_station((20.0, 0.0, 0.0), st)
        out = nearest_station_stabilised(pos, st, hint_index=15, window=4)
        assert out[0] == g[0]         # exactly the global nearest
        assert out[1] == g[1]

    def test_none_position_safe(self):
        assert nearest_station_stabilised(None, _straight(), hint_index=3) is None


class TestJumpDowngrade:
    def test_implausible_backward_jump_downgrades(self):
        st = _straight()
        prev = resolve_live_track_progress((100.0, 0, 0), st)   # progress 0.5
        cur = resolve_live_track_progress((30.0, 0, 0), st)     # progress 0.15
        s = stabilise_progress(cur, prev)
        assert s.jumped is True
        assert s.stabilised_confidence == C.LOW
        assert s.progress == cur.progress                       # value never changed

    def test_small_forward_step_no_downgrade(self):
        st = _straight()
        a = resolve_live_track_progress((30.0, 0, 0), st)
        b = resolve_live_track_progress((40.0, 0, 0), st)
        s = stabilise_progress(b, a, continuity_ok=True)
        assert s.jumped is False
        assert s.stabilised_confidence == b.confidence           # unchanged (HIGH)

    def test_lap_wrap_is_plausible(self):
        prev = LiveTrackProgressResult(progress=0.97, confidence=C.HIGH)
        cur = LiveTrackProgressResult(progress=0.02, confidence=C.HIGH)
        assert stabilise_progress(cur, prev).jumped is False


class TestNeverInflate:
    def test_never_raises_confidence(self):
        lo = LiveTrackProgressResult(progress=0.5, confidence=C.LOW)
        s = stabilise_progress(lo, lo, continuity_ok=True)
        assert s.stabilised_confidence == C.LOW

    def test_unknown_stays_unknown(self):
        u = LiveTrackProgressResult(progress=None, confidence=C.UNKNOWN)
        assert stabilise_progress(u).stabilised_confidence == C.UNKNOWN

    def test_none_current_safe(self):
        assert stabilise_progress(None).stabilised_confidence == C.UNKNOWN


class TestFallbackAndPitInvariants:
    def test_fallback_never_becomes_high(self):
        fb = resolve_progress_from_road_distance(lap_distance_m=LAP / 2, lap_length_m=LAP)
        # Even with a big jump, fallback is downgraded, never HIGH.
        prev = LiveTrackProgressResult(progress=0.1, confidence=fb.confidence,
                                       source=fb.source)
        s = stabilise_progress(fb, prev)
        assert s.stabilised_confidence != C.HIGH

    def test_stabiliser_touches_no_pit_fields(self):
        # The stabilised result carries no pit attributes and never corroborates a pit.
        st = _straight()
        cur = resolve_live_track_progress((30.0, 0, 0), st)
        s = stabilise_progress(cur)
        for banned in ("pit_stops_completed", "pit_corroboration", "pit_evidence_confidence"):
            assert not hasattr(s, banned)
        assert not hasattr(s, "apply")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
