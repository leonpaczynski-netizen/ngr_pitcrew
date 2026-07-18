"""UAT Finding 2 completion — live per-lap capture wiring into Practice Analysis."""
from __future__ import annotations

import types

from strategy.practice_capture import (
    resolve_clean_lap, build_progress_segment_resolver,
    segments_to_corner_names, segments_to_track_corners,
)
from data.track_segment_detection import TrackSegmentType


def _seg(seg_id, stype, lo, hi, name="", status="unreviewed", turn=None):
    return types.SimpleNamespace(
        segment_id=seg_id, segment_type=stype, display_name=name or seg_id,
        original_display_name=name or seg_id, lap_progress_start=lo,
        lap_progress_end=hi, review_status=status, turn_number=turn)


# --------------------------------------------------------------------------- #
# Clean-lap rule
# --------------------------------------------------------------------------- #

def test_clean_lap_rule():
    assert resolve_clean_lap(90000, 89000) is True           # within 7%
    assert resolve_clean_lap(100000, 89000) is False          # outlier
    assert resolve_clean_lap(90000, 0) is True                # no best yet
    assert resolve_clean_lap(0, 89000) is False               # no time
    assert resolve_clean_lap(90000, 89000, valid=False) is False  # invalid lap


# --------------------------------------------------------------------------- #
# Progress -> segment resolver
# --------------------------------------------------------------------------- #

def test_progress_resolver_maps_and_excludes_rejected():
    segs = [
        _seg("t1", TrackSegmentType.BRAKING_ZONE, 0.10, 0.15, "Turn 1"),
        _seg("t1apex", TrackSegmentType.APEX_ZONE, 0.15, 0.20, "Turn 1"),
        _seg("t4", TrackSegmentType.CORNER_EXIT, 0.50, 0.55, "Turn 4"),
        _seg("t9", TrackSegmentType.APEX_ZONE, 0.80, 0.85, "Turn 9", status="rejected"),
    ]
    resolver = build_progress_segment_resolver(segs, lap_length_m=4000.0)
    # road_distance 0.12 of the lap (480 m) -> braking zone t1
    sid, phase = resolver(0.12 * 4000.0, 120.0, 0.0, 0.9)
    assert sid == "t1" and phase == "braking"
    # 0.52 -> corner exit t4
    sid, phase = resolver(0.52 * 4000.0, 100.0, 0.9, 0.0)
    assert sid == "t4" and phase == "exit"
    # 0.82 -> would be t9 but it's rejected -> unresolved
    sid, phase = resolver(0.82 * 4000.0, 90.0, 0.9, 0.0)
    assert sid == ""
    # Unknown lap length -> unresolved (honest fallback)
    r2 = build_progress_segment_resolver(segs, lap_length_m=0.0)
    assert r2(1000.0, 100.0, 0.5, 0.5) == ("", "")


def test_corner_name_helpers():
    segs = [
        _seg("t1apex", TrackSegmentType.APEX_ZONE, 0.15, 0.20, "Turn 1"),
        _seg("str1", TrackSegmentType.STRAIGHT, 0.20, 0.45, "Back straight"),
        _seg("t9", TrackSegmentType.APEX_ZONE, 0.80, 0.85, "Turn 9", status="rejected"),
    ]
    names = segments_to_corner_names(segs)
    assert names["t1apex"] == "Turn 1"
    corners = segments_to_track_corners(segs)
    ids = {c[0] for c in corners}
    assert "t1apex" in ids           # apex is a corner
    assert "str1" not in ids          # straight is not a corner phase
    assert "t9" not in ids            # rejected excluded


# --------------------------------------------------------------------------- #
# compute_lap_capture (pure orchestration) + end-to-end through the engine
# --------------------------------------------------------------------------- #

def test_compute_lap_capture(monkeypatch):
    from strategy import practice_capture as pc
    ep = types.SimpleNamespace(
        kind="lockup", axle="front", corner_phase="braking", segment_id="t1",
        exclusion_reason="", throttle=0.0, brake=0.95, duration_s=0.4,
        max_slip=0.3, yaw_rate=0.1)
    monkeypatch.setattr("telemetry.slip_events.extract_slip_episodes",
                        lambda *a, **k: [ep])
    episodes, is_clean = pc.compute_lap_capture(
        [object()], "FR", None, lap_time_ms=90000, best_ms=89000, valid=True)
    assert episodes == [ep]
    assert is_clean is True

    # No frames -> no episodes; invalid lap -> not clean.
    episodes, is_clean = pc.compute_lap_capture(
        [], "FR", None, lap_time_ms=90000, best_ms=0, valid=False)
    assert episodes == []
    assert is_clean is False


def test_capture_flows_into_engine(monkeypatch):
    """Captured episodes across 4 clean laps -> a recurring T1 finding."""
    from strategy import practice_capture as pc
    from strategy.practice_observation_builder import build_observations
    from strategy.practice_pattern_analysis import analyze_practice

    ep = types.SimpleNamespace(
        kind="lockup", axle="front", corner_phase="braking", segment_id="t1",
        exclusion_reason="", throttle=0.0, brake=0.95, duration_s=0.4,
        max_slip=0.3, yaw_rate=0.1)
    monkeypatch.setattr("telemetry.slip_events.extract_slip_episodes",
                        lambda *a, **k: [ep])

    lap_episodes = {}
    clean = set()
    for lap in (1, 2, 3, 4, 5):
        episodes, is_clean = pc.compute_lap_capture(
            [object()], "FR", None, lap_time_ms=90000, best_ms=89000, valid=True)
        lap_episodes[lap] = episodes
        if is_clean:
            clean.add(lap)

    obs = build_observations(lap_episodes, clean_lap_numbers=sorted(clean),
                             corner_names={"t1": "Turn 1"})
    report = analyze_practice(obs, clean_lap_numbers=sorted(clean),
                              total_lap_numbers=sorted(lap_episodes))
    t1 = next(f for f in report.findings if f.segment_id == "t1")
    assert t1.issue_type == "front_lock"
    assert t1.corner_name == "Turn 1"
    assert t1.laps_affected == 5
    assert t1.setup_authoring_eligible
