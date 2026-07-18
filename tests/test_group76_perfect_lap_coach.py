"""Holistic brain — Phase 2: perfect-lap coach."""
from __future__ import annotations

from strategy.lap_corner_extraction import CornerReferencePoints
from strategy.perfect_lap_coach import (
    build_ideal_lap, coach_against_ideal, perfect_lap_report,
)


def _corner(turn, name, brake, apex, throttle, eg=3, xg=4):
    return CornerReferencePoints(
        turn_number=turn, corner_name=name, segment_ids=(name,), frame_count=5,
        braking_point_m=brake, min_speed_kmh=apex, entry_speed_kmh=apex + 100,
        exit_speed_kmh=apex + 60, entry_gear=eg, exit_gear=xg, apex_gear=eg,
        throttle_on_m=throttle, max_brake=0.9, max_throttle=1.0)


def test_ideal_is_best_per_corner():
    # 3 clean laps; Turn 1 executed differently each lap.
    per_lap = [
        [_corner(1, "Turn 1", brake=110, apex=118, throttle=175)],
        [_corner(1, "Turn 1", brake=125, apex=124, throttle=160)],  # best-ish
        [_corner(1, "Turn 1", brake=118, apex=121, throttle=168)],
    ]
    ideal = build_ideal_lap(per_lap)
    assert len(ideal) == 1
    ic = ideal[0]
    assert ic.target_braking_m == 125       # latest braking
    assert ic.target_min_speed_kmh == 124   # highest apex speed
    assert ic.target_throttle_on_m == 160   # earliest throttle
    assert ic.clean_laps == 3
    assert ic.braking_spread_m == 15.0      # 125 - 110


def test_coaching_gap():
    per_lap = [
        [_corner(1, "Turn 1", brake=110, apex=118, throttle=175)],
        [_corner(1, "Turn 1", brake=112, apex=119, throttle=178)],
        [_corner(1, "Turn 1", brake=130, apex=126, throttle=158)],  # the good one
    ]
    ideal = build_ideal_lap(per_lap)
    coaching = coach_against_ideal(per_lap, ideal)
    assert len(coaching) == 1
    c = coaching[0]
    # Median brake ~112, ideal 130 -> brake ~18 m later.
    assert c.braking_delta_m is not None and c.braking_delta_m >= 6
    assert any("brake" in a and "later" in a for a in c.advice)
    assert any("apex" in a for a in c.advice)
    assert any("throttle" in a and "earlier" in a for a in c.advice)


def test_consistent_corner_praised():
    per_lap = [
        [_corner(6, "Turn 6", brake=200, apex=150, throttle=220)],
        [_corner(6, "Turn 6", brake=201, apex=151, throttle=219)],
        [_corner(6, "Turn 6", brake=199, apex=150, throttle=221)],
    ]
    report = perfect_lap_report(per_lap)
    c = report.coaching[0]
    assert c.consistent
    assert any("hold it" in a or "consistent" in a for a in c.advice)


def test_inconsistent_flagged():
    per_lap = [
        [_corner(4, "Turn 4", brake=180, apex=120, throttle=210)],
        [_corner(4, "Turn 4", brake=210, apex=132, throttle=190)],  # huge spread
    ]
    report = perfect_lap_report(per_lap)
    c = report.coaching[0]
    assert not c.consistent
    assert any("inconsistent" in a for a in c.advice)
    assert "inconsistent" in report.session_consistency.lower()


def test_clean_lap_filtering():
    # Lap index 1 is dirty and should be excluded from the ideal.
    per_lap = [
        [_corner(1, "Turn 1", brake=120, apex=122, throttle=165)],
        [_corner(1, "Turn 1", brake=200, apex=140, throttle=100)],  # dirty outlier
        [_corner(1, "Turn 1", brake=122, apex=123, throttle=163)],
    ]
    ideal = build_ideal_lap(per_lap, clean_lap_indices=[0, 2])
    assert ideal[0].target_braking_m == 122     # dirty lap's 200 excluded
    assert ideal[0].target_min_speed_kmh == 123


def test_report_summary_and_ideal_lines():
    per_lap = [
        [_corner(1, "Turn 1", brake=120, apex=122, throttle=165),
         _corner(2, "Turn 2", brake=300, apex=90, throttle=330)],
        [_corner(1, "Turn 1", brake=121, apex=123, throttle=164),
         _corner(2, "Turn 2", brake=301, apex=91, throttle=331)],
    ]
    report = perfect_lap_report(per_lap)
    assert len(report.ideal_corners) == 2
    lines = report.ideal_lap_lines
    assert any("Turn 1" in l and "apex" in l for l in lines)
    assert report.clean_laps == 2
