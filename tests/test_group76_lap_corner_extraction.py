"""Holistic brain — Phase 1: per-corner reference-point extraction."""
from __future__ import annotations

from strategy.lap_corner_extraction import (
    extract_lap_corner_metrics, build_segment_corner_map, CornerReferencePoints,
)


def _f(rd, spd, thr, brk, gear, seg):
    return {"road_distance": rd, "speed_kmh": spd, "throttle": thr,
            "brake": brk, "gear": gear, "_seg": seg}


def _resolver(frame):
    return frame.get("_seg", ""), ""


# A Turn 1 built from braking -> apex -> exit phase-segments, all turn 1.
CORNER_MAP = {
    "t1_brake": (1, "Turn 1"),
    "t1_apex": (1, "Turn 1"),
    "t1_exit": (1, "Turn 1"),
    "t2_apex": (2, "Turn 2"),
}


def test_extract_reference_points():
    frames = [
        # Approach + braking (brake ramps up), gear 5
        _f(100, 250, 1.0, 0.0, 5, "t1_brake"),
        _f(110, 240, 0.0, 0.4, 5, "t1_brake"),   # first braking @110
        _f(120, 200, 0.0, 0.9, 4, "t1_brake"),
        # Apex — slowest, gear 3
        _f(140, 120, 0.0, 0.2, 3, "t1_apex"),    # min speed 120 @ apex
        _f(150, 125, 0.3, 0.0, 3, "t1_apex"),
        # Exit — back on throttle, gear up
        _f(170, 150, 0.8, 0.0, 4, "t1_exit"),    # throttle-on @170
        _f(190, 190, 1.0, 0.0, 5, "t1_exit"),
    ]
    metrics = extract_lap_corner_metrics(frames, _resolver, CORNER_MAP)
    assert len(metrics) == 1
    m = metrics[0]
    assert m.turn_number == 1 and m.corner_name == "Turn 1"
    assert set(m.segment_ids) == {"t1_brake", "t1_apex", "t1_exit"}
    assert m.braking_point_m == 110       # first brake >= 0.2
    assert m.min_speed_kmh == 120.0       # apex speed
    assert m.entry_gear == 5 and m.exit_gear == 5 and m.apex_gear == 3
    assert m.throttle_on_m == 170         # first throttle >= 0.5 at/after apex
    assert m.entry_speed_kmh == 250.0 and m.exit_speed_kmh == 190.0


def test_multiple_corners_in_order():
    frames = [
        _f(100, 200, 0.0, 0.5, 4, "t1_brake"),
        _f(120, 120, 0.0, 0.1, 3, "t1_apex"),
        _f(140, 160, 0.9, 0.0, 4, "t1_exit"),
        _f(400, 180, 0.0, 0.6, 4, "t2_apex"),
        _f(420, 110, 0.0, 0.0, 2, "t2_apex"),
    ]
    metrics = extract_lap_corner_metrics(frames, _resolver, CORNER_MAP)
    assert [m.turn_number for m in metrics] == [1, 2]
    assert metrics[1].min_speed_kmh == 110.0


def test_unresolved_and_unmapped_frames_skipped():
    frames = [
        _f(10, 250, 1.0, 0.0, 6, ""),          # unresolved -> skipped
        _f(20, 250, 1.0, 0.0, 6, "unknown"),   # not in corner map -> skipped
        _f(100, 200, 0.0, 0.5, 4, "t1_brake"),
        _f(120, 120, 0.0, 0.1, 3, "t1_apex"),
    ]
    metrics = extract_lap_corner_metrics(frames, _resolver, CORNER_MAP)
    assert len(metrics) == 1 and metrics[0].turn_number == 1


def test_no_braking_no_throttle_on():
    # A flat-out kink: no braking, throttle stays high -> braking None, apex=min.
    frames = [
        _f(100, 250, 1.0, 0.0, 6, "t2_apex"),
        _f(110, 245, 1.0, 0.0, 6, "t2_apex"),
    ]
    metrics = extract_lap_corner_metrics(frames, _resolver, CORNER_MAP)
    m = metrics[0]
    assert m.braking_point_m is None
    # Apex is the slower frame (245 @ rd110); throttle already high there.
    assert m.throttle_on_m == 110
    assert m.min_speed_kmh == 245.0


def test_coaching_line():
    frames = [
        _f(110, 240, 0.0, 0.6, 5, "t1_brake"),
        _f(140, 120, 0.0, 0.1, 3, "t1_apex"),
        _f(170, 160, 0.8, 0.0, 4, "t1_exit"),
    ]
    m = extract_lap_corner_metrics(frames, _resolver, CORNER_MAP)[0]
    line = m.coaching_line()
    assert "Turn 1" in line and "brake" in line and "gear" in line and "apex" in line


def test_build_segment_corner_map():
    import types
    segs = [
        types.SimpleNamespace(segment_id="a", turn_number=1, display_name="Turn 1"),
        types.SimpleNamespace(segment_id="b", turn_number=1, display_name="Turn 1"),
        types.SimpleNamespace(segment_id="c", turn_number=None, display_name="Esses"),
    ]
    m = build_segment_corner_map(segs)
    assert m["a"] == (1, "Turn 1") and m["b"] == (1, "Turn 1")
    assert m["c"] == (None, "Esses")
