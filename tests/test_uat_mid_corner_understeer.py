"""UAT: 'Pushes wide' (mid-corner understeer) must drive a correct-direction fix.

Before: "Pushes wide" matched the 'push' keyword in floaty_front, firing B2
(increase front ARB) — which WORSENS mid-corner understeer. Now it routes to
mid_corner_understeer → B2b (soften front ARB, add front grip), and B2 is
suppressed when the driver is happy with entry balance / reports mid understeer.
"""
from __future__ import annotations

from strategy.setup_diagnosis import _parse_driver_feel, build_setup_diagnosis
from strategy.setup_rule_engine import run_rule_engine
from strategy.setup_driver_profile import build_driver_profile
from strategy.setup_ranges import resolve_ranges

CAR = "Porsche 911 RSR (991) '17"


def _plan(feeling, setup=None):
    setup = setup or {"arb_front": 6, "arb_rear": 4, "aero_front": 425,
                      "aero_rear": 600, "lsd_accel": 14, "lsd_decel": 10, "brake_bias": 0}
    diag = build_setup_diagnosis(laps=[], setup=setup, car_name=CAR, event_ctx={},
                                 feeling=feeling, location_confidence="low")
    return run_rule_engine(diag, setup, resolve_ranges(CAR), build_driver_profile())


# ---------------------------------------------------------------- feel parsing

def test_pushes_wide_is_mid_corner_understeer_not_floaty():
    flags = _parse_driver_feel("Mid-Corner: Pushes wide")
    assert flags["mid_corner_understeer"] is True
    assert flags["floaty_front"] is False


def test_good_balance_sets_entry_balance_good():
    assert _parse_driver_feel("Corner Entry: Good balance")["entry_balance_good"] is True


def test_genuine_floaty_front_still_detected():
    flags = _parse_driver_feel("front feels floaty and lazy turn-in")
    assert flags["floaty_front"] is True
    assert flags["mid_corner_understeer"] is False


# ---------------------------------------------------------------- rule direction

def test_pushes_wide_softens_front_arb_not_stiffens():
    ids = {(c.rule_id, c.field, c.delta) for c in _plan("Mid-Corner: Pushes wide").proposed}
    # B2b: soften front ARB (correct direction — adds front grip).
    assert ("B2b", "arb_front", -1.0) in ids
    # B2 (increase front ARB) must NOT fire — it would worsen the push.
    assert not any(rid == "B2" for (rid, _f, _d) in ids)


def test_full_uat_feedback_gives_correct_front_change():
    feeling = ("Corner Entry: Good balance\nMid-Corner: Pushes wide\n"
               "Exit Stability: Good traction\nRear Under Braking: Locks up rear\n"
               "Tyre Condition: Fine\nFuel Use: Higher than expected")
    proposed = _plan(feeling).proposed
    front = [(c.rule_id, c.delta) for c in proposed if c.field == "arb_front"]
    # The only front-ARB move is a SOFTENING (never a stiffening).
    assert front, "expected a front-ARB change for mid-corner understeer"
    assert all(d < 0 for (_rid, d) in front), f"front ARB must soften, got {front}"
    assert not any(c.rule_id == "B2" for c in proposed)


def test_genuine_floaty_front_still_stiffens_front_arb():
    # A real vague-turn-in complaint (not mid-corner push, aero not at min) still
    # stiffens the front via B2 — the fix is preserved for its correct case.
    ids = {(c.rule_id, c.field, c.delta) for c in _plan("front feels floaty, lazy turn-in").proposed}
    assert ("B2", "arb_front", 1.0) in ids
    assert not any(rid == "B2b" for (rid, _f, _d) in ids)


def test_good_entry_balance_suppresses_turn_in_change():
    # Contradictory input (floaty + happy entry): the turn-in stiffening is
    # suppressed because the driver is happy with entry balance.
    ids = {c.rule_id for c in _plan("front feels floaty but good balance on entry").proposed}
    assert "B2" not in ids


def test_high_fuel_use_flagged_for_acknowledgement():
    flags = _parse_driver_feel("Fuel Use: Higher than expected")
    assert flags["fuel_use_high"] is True
    diag = build_setup_diagnosis(laps=[], setup={"arb_front": 6}, car_name=CAR,
                                 event_ctx={}, feeling="Fuel Use: Higher than expected",
                                 location_confidence="low")
    assert diag.get("driver_feel_flags", {}).get("fuel_use_high") is True
