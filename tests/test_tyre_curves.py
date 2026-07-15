"""Sprint 7 — RS/RM/RH performance curves + crossover laps.

The mandatory deterministic acceptance fixture (from the spec):
  RS  laps 1-3  @ 1:38.000, lap 4+  @ 1:40.000
  RM  laps 1-6  @ 1:39.000, lap 7+  @ 1:41.500
  RH  laps 1-12 @ 1:40.000, lap 13+ @ 1:41.800
Expected crossovers:  RS -> RM after lap 3,  RM -> RH after lap 6.
"""
from __future__ import annotations

from strategy.tyre_curves import (
    build_compound_curves, compute_crossovers, usable_stint_window,
    build_compound_curve, TyreCurveConfig,
)

_RS = [98000, 98000, 98000] + [100000] * 5           # 8 laps
_RM = [99000] * 6 + [101500] * 6                       # 12 laps
_RH = [100000] * 12 + [101800] * 2                      # 14 laps


def _crossover(crossovers, softer, harder):
    for c in crossovers:
        if c.softer == softer and c.harder == harder:
            return c
    return None


def test_mandatory_fixture_crossovers():
    curves = build_compound_curves({"RS": _RS, "RM": _RM, "RH": _RH})
    crossovers = compute_crossovers(curves)

    rs_rm = _crossover(crossovers, "RS", "RM")
    rm_rh = _crossover(crossovers, "RM", "RH")
    assert rs_rm is not None and rm_rh is not None
    assert rs_rm.crossover_after_lap == 3, f"RS->RM after lap {rs_rm.crossover_after_lap}"
    assert rm_rh.crossover_after_lap == 6, f"RM->RH after lap {rm_rh.crossover_after_lap}"


def test_fresh_ranking_rs_fastest():
    curves = build_compound_curves({"RS": _RS, "RM": _RM, "RH": _RH})
    assert curves["RS"].pace_at_age(1) < curves["RM"].pace_at_age(1) < curves["RH"].pace_at_age(1)


def test_rm_supersedes_rs_after_lap_3():
    curves = build_compound_curves({"RS": _RS, "RM": _RM, "RH": _RH})
    rs, rm = curves["RS"], curves["RM"]
    assert rs.pace_at_age(3) < rm.pace_at_age(3)   # RS still best at lap 3
    assert rs.pace_at_age(4) > rm.pace_at_age(4)   # RM better from lap 4


def test_rh_supersedes_rm_after_lap_6():
    curves = build_compound_curves({"RS": _RS, "RM": _RM, "RH": _RH})
    rm, rh = curves["RM"], curves["RH"]
    assert rm.pace_at_age(6) < rh.pace_at_age(6)   # RM still best at lap 6
    assert rm.pace_at_age(7) > rh.pace_at_age(7)   # RH better from lap 7


def test_usable_windows_reflect_measured_life():
    curves = build_compound_curves({"RS": _RS, "RM": _RM, "RH": _RH})
    # RS degrades after lap 3 -> usable ~3; RM after lap 6 -> ~6.
    assert usable_stint_window(curves["RS"]).max_usable_laps <= 3
    assert usable_stint_window(curves["RM"]).max_usable_laps <= 6


def test_untested_compound_flagged_and_excluded_from_crossovers():
    curves = build_compound_curves({"RS": _RS, "RM": _RM, "RH": []})
    assert curves["RH"].tested is False
    assert curves["RH"].evidence.confidence == "none"
    crossovers = compute_crossovers(curves)
    # RH has no data → no RM->RH crossover.
    assert _crossover(crossovers, "RM", "RH") is None


def test_evidence_quality_scales_with_sample():
    short = build_compound_curve("RS", [98000, 98000])            # < min_laps
    med = build_compound_curve("RS", [98000] * 5)
    lng = build_compound_curve("RS", [98000] * 10)
    assert short.evidence.confidence == "low"
    assert med.evidence.confidence == "medium"
    assert lng.evidence.confidence == "high"


def test_deterministic_repeatable():
    a = compute_crossovers(build_compound_curves({"RS": _RS, "RM": _RM, "RH": _RH}))
    b = compute_crossovers(build_compound_curves({"RS": _RS, "RM": _RM, "RH": _RH}))
    assert a == b


def test_no_data_returns_no_crossovers():
    assert compute_crossovers(build_compound_curves({})) == []


def test_single_compound_no_crossover():
    assert compute_crossovers(build_compound_curves({"RM": _RM})) == []
