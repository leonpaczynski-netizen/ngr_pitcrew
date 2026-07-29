"""Data-maturity → cold-start aggression: bolder corrective moves while data is thin,
decaying to the normal single-step behaviour once 3 qualifying runs (>=5 clean laps
each) exist and telemetry becomes the dominant driver.
"""
from __future__ import annotations

from types import SimpleNamespace

from strategy.setup_maturity import (
    count_qualifying_runs, data_maturity, cold_start_aggression, aggression_for_runs,
)


# ---------------------------------------------------------------------------
# Maturity math
# ---------------------------------------------------------------------------

def test_a_too_short_run_does_not_count():
    # 5 clean laps qualifies; a 2-lap bail (setup was so bad the driver came in) doesn't.
    assert count_qualifying_runs([6, 2, 7]) == 2
    assert count_qualifying_runs([4, 4, 4]) == 0
    assert count_qualifying_runs([5]) == 1


def test_aggression_curve_3x_to_1x_over_three_runs():
    assert aggression_for_runs([]) == 3.0                 # blank → max aggression
    assert round(aggression_for_runs([6]), 2) == 2.33
    assert round(aggression_for_runs([6, 7]), 2) == 1.67
    assert aggression_for_runs([6, 7, 8]) == 1.0          # 3 qualifying runs → normal
    assert aggression_for_runs([6, 7, 8, 9, 10]) == 1.0   # never below 1.0


def test_aggression_is_clamped():
    assert cold_start_aggression(0.0) == 3.0
    assert cold_start_aggression(1.0) == 1.0
    assert cold_start_aggression(-5) == 3.0    # maturity clamps to [0,1]
    assert cold_start_aggression(9) == 1.0
    assert data_maturity(-2) == 0.0 and data_maturity(99) == 1.0


# ---------------------------------------------------------------------------
# DB counter — only runs with >= min_laps timed laps count
# ---------------------------------------------------------------------------

def test_db_counts_only_runs_with_enough_laps():
    from data.session_db import SessionDB
    db = SessionDB(":memory:")

    def run(nlaps):
        sid = db.open_session(car_id=1, track="Monza", session_type="Race", event_id=1)
        for i in range(1, nlaps + 1):
            db.write_lap(sid, i, 90_000, 2.0, None)
        return sid

    run(6); run(7); run(2)   # two qualifying runs + one 2-lap bail-out
    assert db.count_qualifying_runs(1, "Monza") == 2
    assert db.count_qualifying_runs(1, "Monza", min_laps=7) == 1
    assert db.count_qualifying_runs(1, "Silverstone") == 0
    db.close()


# ---------------------------------------------------------------------------
# Rule-engine effect — cold-start aggression enlarges corrective moves
# ---------------------------------------------------------------------------

def _lap(**kw):
    d = dict(bottoming_count=0, wheelspin_count=0, snap_throttle_count=0, lock_up_count=0,
             rev_limiter_by_gear={}, max_speed_kmh=200.0, brake_consistency_m=5.0,
             oversteer_count=0, oversteer_throttle_on_count=0, kerb_count=0, max_lat_g=1.5,
             lock_up_positions=[], wheelspin_positions=[], oversteer_positions=[],
             snap_throttle_positions=[], over_braking_positions=[], bottoming_positions=[],
             over_braking_count=0, abrupt_release_count=0, off_track_count=0, rev_limiter_count=0)
    d.update(kw)
    return SimpleNamespace(**d)


def test_cold_start_aggression_enlarges_corrective_moves():
    from strategy.setup_diagnosis import build_setup_diagnosis
    from strategy.setup_rule_engine import run_rule_engine
    from strategy.setup_driver_profile import build_driver_profile
    from strategy.setup_ranges import resolve_ranges

    setup = {"arb_rear": 5, "arb_front": 5, "lsd_decel": 20, "aero_front": 400, "aero_rear": 600}
    diag = build_setup_diagnosis(laps=[_lap()], setup=setup, car_name="", event_ctx={},
                                 feeling="mid-corner understeer, entry understeer",
                                 location_confidence="low")
    ranges = resolve_ranges("")
    profile = build_driver_profile()

    def moves(agg):
        plan = run_rule_engine(diag, setup, ranges, profile, cold_start_aggression=agg)
        return {i.field: abs(i.to_value - i.from_value) for i in plan.proposed
                if i.to_value is not None and i.from_value is not None}

    m1, m3 = moves(1.0), moves(3.0)
    assert m1, "diagnosis should fire at least one corrective change"
    for f, v in m1.items():                       # a bold move is never smaller
        assert m3.get(f, 0.0) + 1e-9 >= v
    assert sum(m3.values()) > sum(m1.values()) + 1e-9   # at least one field moves more


def test_default_aggression_is_a_no_op():
    """Default cold_start_aggression=1.0 must leave the plan byte-identical (existing
    callers/behaviour unaffected)."""
    from strategy.setup_diagnosis import build_setup_diagnosis
    from strategy.setup_rule_engine import run_rule_engine
    from strategy.setup_driver_profile import build_driver_profile
    from strategy.setup_ranges import resolve_ranges

    setup = {"arb_rear": 5, "lsd_decel": 20}
    diag = build_setup_diagnosis(laps=[_lap()], setup=setup, car_name="", event_ctx={},
                                 feeling="mid-corner understeer", location_confidence="low")
    ranges = resolve_ranges("")
    profile = build_driver_profile()
    default = run_rule_engine(diag, setup, ranges, profile)
    explicit = run_rule_engine(diag, setup, ranges, profile, cold_start_aggression=1.0)
    assert [(i.field, i.delta) for i in default.proposed] == \
           [(i.field, i.delta) for i in explicit.proposed]
