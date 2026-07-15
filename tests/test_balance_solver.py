"""Multi-complaint balance solver tests (strategy/setup_balance_solver).

Prove the Setup Brain AUTHORS a coherent setup from conflicting complaints instead
of deferring to evidence_required — while respecting every safety invariant.
"""
from __future__ import annotations

import json

from strategy.setup_balance_solver import (
    solve_balance, confirmed_handling_complaints, BalanceSolution,
)
from strategy.setup_ranges import resolve_ranges

_CAR = "Porsche 911 RSR (991) '17"


def _ranges():
    return resolve_ranges(_CAR)


def _setup(**over):
    s = {"arb_front": 6, "arb_rear": 5, "aero_front": 400, "aero_rear": 600,
         "toe_front": 0.0, "toe_rear": 0.05, "brake_bias": 0, "lsd_accel": 15,
         "lsd_decel": 10}
    s.update(over)
    return s


def _diag(**flags):
    ws = flags.pop("wheelspin_band", "low")
    return {"driver_feel_flags": dict(flags), "wheelspin_band": ws}


# ------------------------------------------------------------------ gating

def test_single_complaint_does_not_trigger_solver():
    sol = solve_balance(_diag(mid_corner_understeer=True), _setup(), _ranges())
    assert sol.solved is False


def test_two_complaints_solve():
    sol = solve_balance(
        _diag(mid_corner_understeer=True, rear_loose_on_exit=True), _setup(), _ranges())
    assert sol.solved is True
    assert len(sol.moves) >= 3


# ------------------------------------------------------------------ coherent balance

def test_uat_four_complaints_authors_coordinated_set():
    diag = _diag(entry_understeer=True, mid_corner_understeer=True,
                 rear_loose_on_exit=True, rear_loose_under_braking=True,
                 braking_instability=True, wheelspin_band="severe")
    sol = solve_balance(diag, _setup(), _ranges())
    assert sol.solved is True
    by_field = {m.field: m for m in sol.moves}
    # Free the front:
    assert by_field["arb_front"].direction < 0        # soften front
    assert by_field["toe_front"].direction < 0        # front toe-out
    # Plant the rear:
    assert by_field["aero_rear"].direction > 0        # more rear downforce
    assert by_field["toe_rear"].direction > 0         # rear toe-in
    assert by_field["arb_rear"].direction < 0         # soften rear for grip
    # Stable braking:
    assert by_field["brake_bias"].direction < 0       # forward
    # The engineer's trade-off is explained.
    assert sol.tradeoffs and "freed at the FRONT" in sol.tradeoffs[0]
    assert sol.test_protocol


# ------------------------------------------------------------------ safety invariants

def test_never_adds_accel_lock_when_rear_loose():
    diag = _diag(mid_corner_understeer=True, rear_loose_on_exit=True,
                 wheelspin_band="severe")
    sol = solve_balance(diag, _setup(), _ranges())
    assert "lsd_accel" not in {m.field for m in sol.moves}
    # And it says so as a test, not a silent omission.
    assert any("do NOT add lock" in t or "Acceleration" in t for t in sol.targeted_tests)


def test_brake_bias_only_moves_forward_under_instability():
    diag = _diag(mid_corner_understeer=True, braking_instability=True)
    sol = solve_balance(diag, _setup(brake_bias=0), _ranges())
    bb = {m.field: m for m in sol.moves}.get("brake_bias")
    assert bb is not None and bb.direction < 0        # forward (never rearward)
    assert bb.to_value < 0


def test_lsd_braking_left_to_targeted_test():
    diag = _diag(mid_corner_understeer=True, rear_loose_under_braking=True)
    sol = solve_balance(diag, _setup(), _ranges())
    assert "lsd_decel" not in {m.field for m in sol.moves}
    assert any("LSD Braking" in t for t in sol.targeted_tests)


def test_locked_field_is_not_moved():
    diag = _diag(entry_understeer=True, rear_loose_on_exit=True)
    sol = solve_balance(diag, _setup(), _ranges(), locked_fields={"aero_rear", "arb_front"})
    fields = {m.field for m in sol.moves}
    assert "aero_rear" not in fields and "arb_front" not in fields
    assert any("locked" in t for t in sol.targeted_tests)


def test_field_at_range_limit_is_noted_not_moved():
    # aero_front already at its max (450) — solver can't add more, and says so.
    diag = _diag(entry_understeer=True, mid_corner_understeer=True, rear_loose_on_exit=True)
    sol = solve_balance(diag, _setup(aero_front=450), _ranges())
    front_aero = [m for m in sol.moves if m.field == "aero_front"]
    assert not front_aero
    assert any("limit" in t for t in sol.targeted_tests)


def test_all_moves_stay_in_range():
    diag = _diag(entry_understeer=True, rear_loose_on_exit=True, braking_instability=True)
    sol = solve_balance(diag, _setup(), _ranges())
    r = _ranges()
    for m in sol.moves:
        if m.field in r and m.to_value is not None:
            lo, hi = r[m.field]
            assert lo <= m.to_value <= hi


# ------------------------------------------------------------------ helpers / shape

def test_confirmed_complaints_excludes_fuel_and_good_balance():
    diag = _diag(mid_corner_understeer=True, fuel_use_high=True, entry_balance_good=True)
    c = confirmed_handling_complaints(diag)
    assert "mid_corner_understeer" in c
    assert "fuel_use_high" not in c and "entry_balance_good" not in c


def test_severe_wheelspin_counts_as_rear_grip_complaint():
    c = confirmed_handling_complaints(_diag(mid_corner_understeer=True, wheelspin_band="severe"))
    assert "wheelspin" in c


def test_change_dicts_have_apply_shape():
    diag = _diag(entry_understeer=True, rear_loose_on_exit=True)
    sol = solve_balance(diag, _setup(), _ranges())
    for ch in sol.as_change_dicts():
        assert ch["field"] and "to_clamped" in ch and ch["rule_id"] == "balance_solver"
    assert sol.setup_fields()  # non-empty applyable field map


# ------------------------------------------------------------------ end-to-end integration

def test_integration_authors_instead_of_evidence_required():
    """The exact UAT scenario now returns a balance_recommendation with real changes,
    not evidence_required with none."""
    from tests.test_group63_setup_brain_uat2 import (
        _uat_advisor, _uat_history, _UAT_FEELING, _CAR as UCAR,
    )
    adv = _uat_advisor()
    setup = {"final_drive": 4.25, "transmission_max_speed_kmh": 0, "num_gears": 6,
             "aero_front": 450, "aero_rear": 590, "lsd_initial": 10, "lsd_accel": 15,
             "lsd_decel": 10, "camber_front": 1.0, "camber_rear": 1.5,
             "arb_front": 6, "arb_rear": 5, "toe_front": 0.0, "toe_rear": 0.05,
             "brake_bias": 0}
    r = json.loads(adv.build_combined_setup_response(
        setup_dict=setup, car_name=UCAR, feeling=_UAT_FEELING, purpose="Race",
        drivetrain="RR", historical_setups=_uat_history(), track_name="NGR",
        fuel_multiplier=3.0, refuel_rate_lps=1.0))
    assert r.get("recommendation_status") == "balance_recommendation"
    assert r.get("changes"), "must author a real setup, not defer"
    assert r.get("setup_fields")
    bs = r.get("balance_solution") or {}
    assert bs.get("solved") is True
    # Apply-eligible: status is in the approved family.
    from strategy._setup_constants import APPROVED_STATUSES
    assert r["recommendation_status"] in APPROVED_STATUSES
    # Safety preserved: no accel-lock increase authored; brake bias not rearward.
    changes = {c["field"]: c for c in r["changes"]}
    assert "lsd_accel" not in changes
    if "brake_bias" in changes:
        assert float(changes["brake_bias"]["to_clamped"]) <= 0
