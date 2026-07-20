"""Holistic brain — Phase 1+2 pipeline (laps+frames -> coaching report)."""
from __future__ import annotations

import types

from strategy.perfect_lap_pipeline import coach_from_laps


def _f(rd, spd, thr, brk, gear, seg):
    return {"road_distance": rd, "speed_kmh": spd, "throttle": thr,
            "brake": brk, "gear": gear, "_seg": seg}


def _resolver(frame):
    return frame.get("_seg", ""), ""


SEGS = [
    types.SimpleNamespace(segment_id="t1_brake", turn_number=1, display_name="Turn 1"),
    types.SimpleNamespace(segment_id="t1_apex", turn_number=1, display_name="Turn 1"),
    types.SimpleNamespace(segment_id="t1_exit", turn_number=1, display_name="Turn 1"),
]


def _lap(lap_ms, brake_rd, apex_spd, throttle_rd, pit=False):
    return {
        "lap_time_ms": lap_ms, "is_pit_lap": pit,
        "frames": [
            _f(brake_rd, 240, 0.0, 0.6, 5, "t1_brake"),
            _f(brake_rd + 30, apex_spd, 0.0, 0.1, 3, "t1_apex"),
            _f(throttle_rd, 160, 0.8, 0.0, 4, "t1_exit"),
        ],
    }


def test_pipeline_builds_report_and_excludes_outliers():
    laps = [
        _lap(90000, brake_rd=110, apex_spd=118, throttle_rd=175),
        _lap(89500, brake_rd=128, apex_spd=126, throttle_rd=158),   # best exec
        _lap(120000, brake_rd=90, apex_spd=100, throttle_rd=200),   # slow outlier
        _lap(0, brake_rd=0, apex_spd=0, throttle_rd=0, pit=True),   # pit lap
    ]
    report = coach_from_laps(laps, _resolver, SEGS)
    assert report.ideal_corners, "should extract Turn 1"
    ic = report.ideal_corners[0]
    assert ic.turn_number == 1
    # Outlier + pit lap excluded from clean set -> ideal from laps 0 & 1.
    assert ic.target_braking_m == 128
    assert ic.target_min_speed_kmh == 126
    assert report.clean_laps == 2
    assert report.coaching


def test_pipeline_empty_laps():
    report = coach_from_laps([], _resolver, SEGS)
    assert report.ideal_corners == ()
    assert "Not enough" in report.session_consistency
