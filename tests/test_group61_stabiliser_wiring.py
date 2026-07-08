"""Group 61 — stateful stabiliser wiring tests.

Proves the stateful holder + live-replan wiring preserve every invariant: global
nearest wins, implausible jumps downgrade (display-only), the reported progress
value never changes, confidence never inflates, state resets across identities,
and pit corroboration is untouched by stabilisation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.live_track_progress import (  # noqa: E402
    LiveTrackProgressResult, TrackProgressConfidence as C,
    build_track_path_stations, nearest_station,
)
from data.live_progress_stabiliser import (  # noqa: E402
    LiveProgressStabiliserState, nearest_station_stabilised,
)
from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from strategy.race_strategy_live_replan import (  # noqa: E402
    build_live_replan_snapshot, render_live_replan_text,
    fuji_pit_lane_mapping, fuji_reference_path, fuji_position_at_progress,
    fuji_live_state_pre_pit_healthy,
)


def _crossing():
    pts = []
    for i in range(11):
        pts.append({"x": i * 10.0, "y": 0.0, "z": 0.0,
                    "distance_along_lap_m": i * 10.0, "lap_progress": i / 20.0})
    for i in range(1, 11):
        pts.append({"x": (10 - i) * 10.0, "y": 0.0, "z": 3.0,
                    "distance_along_lap_m": (10 + i) * 10.0, "lap_progress": (10 + i) / 20.0})
    return build_track_path_stations({"reference_path": {"points": pts}})


class TestNearestStabilised:
    def test_global_wins_over_bad_hint(self):
        st = _crossing()
        pos = (20.0, 0.0, 0.0)
        g = nearest_station(pos, st)
        out = nearest_station_stabilised(pos, st, hint_index=15, window=4)
        assert out[0] == g[0] and out[1] == g[1]


class TestStateHolder:
    def test_small_step_keeps_confidence(self):
        st = LiveProgressStabiliserState()
        a = LiveTrackProgressResult(progress=0.30, confidence=C.HIGH)
        b = LiveTrackProgressResult(progress=0.33, confidence=C.HIGH)
        st.update(a, identity_key="k")
        sp = st.update(b, identity_key="k")
        assert sp.jumped is False and sp.stabilised_confidence == C.HIGH

    def test_implausible_jump_downgrades(self):
        st = LiveProgressStabiliserState()
        st.update(LiveTrackProgressResult(progress=0.30, confidence=C.HIGH), identity_key="k")
        sp = st.update(LiveTrackProgressResult(progress=0.80, confidence=C.HIGH), identity_key="k")
        assert sp.jumped is True and sp.stabilised_confidence == C.LOW
        assert sp.progress == 0.80          # value unchanged

    def test_value_never_changed(self):
        st = LiveProgressStabiliserState()
        cur = LiveTrackProgressResult(progress=0.42, confidence=C.MEDIUM)
        assert st.update(cur, identity_key="k").progress == 0.42

    def test_never_inflates(self):
        st = LiveProgressStabiliserState()
        lo = LiveTrackProgressResult(progress=0.5, confidence=C.LOW)
        st.update(lo, identity_key="k")
        assert st.update(lo, identity_key="k").stabilised_confidence == C.LOW

    def test_state_resets_on_identity_change(self):
        st = LiveProgressStabiliserState()
        st.update(LiveTrackProgressResult(progress=0.30, confidence=C.HIGH), identity_key="trackA")
        # New identity → previous dropped → the "jump" is not flagged (fresh start).
        sp = st.update(LiveTrackProgressResult(progress=0.80, confidence=C.HIGH), identity_key="trackB")
        assert sp.jumped is False
        assert st.identity_key == "trackB"

    def test_lap_wrap_not_a_jump(self):
        st = LiveProgressStabiliserState()
        st.update(LiveTrackProgressResult(progress=0.97, confidence=C.HIGH), identity_key="k")
        assert st.update(LiveTrackProgressResult(progress=0.02, confidence=C.HIGH),
                         identity_key="k").jumped is False


class TestLiveReplanWiring:
    def _ctx(self):
        c = dict(fuji_pit_lane_mapping())
        c["reference_path"] = fuji_reference_path()["reference_path"]
        return c

    def test_no_stabiliser_state_is_identical(self):
        pre = run_fuji_uat()
        r = build_live_replan_snapshot(
            pre_race_result=pre, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=self._ctx(), live_position=fuji_position_at_progress(0.4),
            reference_stations=build_track_path_stations(fuji_reference_path()))
        assert r.stabilised_confidence == "" and r.stabiliser_notes == ()

    def test_jump_downgrades_display_but_not_pit(self):
        pre = run_fuji_uat()
        ctx = self._ctx()
        stations = build_track_path_stations(fuji_reference_path())
        state = LiveProgressStabiliserState()
        r1 = build_live_replan_snapshot(
            pre_race_result=pre, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx, live_position=fuji_position_at_progress(0.4),
            reference_stations=stations, stabiliser_state=state)
        r2 = build_live_replan_snapshot(
            pre_race_result=pre, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx, live_position=fuji_position_at_progress(0.9),
            reference_stations=stations, stabiliser_state=state)
        # Raw track progress + pit corroboration unaffected; only the display confidence drops.
        assert r2.track_progress.confidence == C.HIGH
        assert r2.stabilised_confidence == "LOW"
        assert r2.stabiliser_jumped is True
        assert r1.pit_corroboration == r2.pit_corroboration   # pit path unchanged
        assert "jitter guard" in render_live_replan_text(r2).lower()

    def test_state_resets_between_tracks_via_identity(self):
        pre = run_fuji_uat()
        ctx = self._ctx()
        stations = build_track_path_stations(fuji_reference_path())
        state = LiveProgressStabiliserState()
        build_live_replan_snapshot(
            pre_race_result=pre, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx, live_position=fuji_position_at_progress(0.4),
            reference_stations=stations, stabiliser_state=state)
        # Different track identity → the big move is a fresh start, not a jump.
        ctx2 = dict(ctx); ctx2["track_id"] = "different_track"
        r = build_live_replan_snapshot(
            pre_race_result=pre, live_state=fuji_live_state_pre_pit_healthy(),
            track_context=ctx2, live_position=fuji_position_at_progress(0.9),
            reference_stations=stations, stabiliser_state=state)
        assert r.stabiliser_jumped is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
