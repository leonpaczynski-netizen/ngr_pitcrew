"""Engineering-reasoning layer tests (strategy/setup_engineering).

Prove the Setup Brain reasons like a race engineer, not a validator:
  * a vehicle model is built from real specs and drives authoring;
  * rich track characteristics differentiate setups beyond aero (gearing, springs,
    ARB, ride height) — Fuji (straight-heavy) != a twisty circuit;
  * the RR Porsche gets front-bite + rear-stability + brake-forward engineering;
  * the objective genuinely shapes intents (race protects the rear tyre, quali sharpens);
  * intents carry coupling links (systems reasoning);
  * everything degrades honestly with no track / no specs and stays in range.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from strategy.setup_engineering import (
    build_vehicle_model, derive_engineering_intents, coupling_report,
    resolve_car_specs, VehicleModel,
    BAL_ENTRY_US_POWER_OS, BAL_STRONG_US, OBJ_BASE, OBJ_QUALI, OBJ_RACE,
)
from strategy.setup_ranges import resolve_ranges
from strategy.driving_advisor import DrivingAdvisor

_CAR = "Porsche 911 RSR (991) '17"
_SPECS = {"category": "Gr.3", "power_hp": 509, "weight_kg": 1243, "aspiration": "NA"}


def _fuji():
    return SimpleNamespace(trustworthy=True, straight_fraction=0.32,
                           corner_density_per_km=3.5, elevation_change_m=40,
                           aero_bias="trim", summary=lambda: "Fuji")


def _twisty():
    return SimpleNamespace(trustworthy=True, straight_fraction=0.10,
                           corner_density_per_km=8.0, elevation_change_m=8,
                           aero_bias="add", summary=lambda: "Twisty")


# ------------------------------------------------------------------ vehicle model

def test_vehicle_model_from_real_specs():
    vm = build_vehicle_model(_CAR, "rr", 6, _SPECS)
    assert vm.engine_location == "rear"
    assert vm.balance_tendency == BAL_ENTRY_US_POWER_OS
    assert vm.power_to_weight == round(509 / 1.243, 1)   # ~410 hp/t
    assert vm.high_power_to_weight is True
    assert vm.rear_traction_priority is True


def test_vehicle_model_front_drive_tendency():
    vm = build_vehicle_model("Some FF Hatch", "ff", 6, {"power_hp": 200, "weight_kg": 1200})
    assert vm.balance_tendency == BAL_STRONG_US
    assert vm.rear_traction_priority is False


def test_vehicle_model_missing_specs_is_honest():
    vm = build_vehicle_model(_CAR, "rr", 6, {})
    assert vm.power_to_weight is None
    assert vm.high_power_to_weight is False
    assert isinstance(vm, VehicleModel)


def test_resolve_car_specs_reads_real_file():
    specs = resolve_car_specs(_CAR)
    assert specs.get("power_hp") == 509 and specs.get("weight_kg") == 1243
    assert resolve_car_specs("No Such Car") == {}


# ------------------------------------------------------------------ RR engineering

def test_rr_gets_front_bite_rear_stability_brake_forward():
    vm = build_vehicle_model(_CAR, "rr", 6, _SPECS)
    plan = derive_engineering_intents(vm, _fuji(), OBJ_RACE, None)
    bias = plan.bias()
    assert bias.get("arb_front", 0) < 0        # soften front = free entry understeer
    assert bias.get("toe_rear", 0) > 0         # rear toe-in = stability under power
    assert bias.get("brake_bias", 0) < 0       # bias forward = front-limited braking
    # And it explains WHY (engineer reasoning, not a bare number).
    reasons = " ".join(i.reason for i in plan.intents).lower()
    assert "rear-engined" in reasons and "brak" in reasons


# ------------------------------------------------------------------ track differentiation

def test_track_differentiates_beyond_aero():
    vm = build_vehicle_model(_CAR, "rr", 6, _SPECS)
    fuji = derive_engineering_intents(vm, _fuji(), OBJ_RACE, None)
    twisty = derive_engineering_intents(vm, _twisty(), OBJ_RACE, None)
    # Gearing: Fuji gears LONGER (negative lean), twisty SHORTER (positive lean).
    assert fuji.final_drive_lean < 0 < twisty.final_drive_lean
    fb, tb = fuji.bias(), twisty.bias()
    # Twisty softens the front spring for mechanical grip; Fuji does not.
    assert tb.get("springs_front", 0) < 0
    assert fb.get("springs_front", 0) == 0
    # Fuji carries ride-height margin for its 40 m elevation; twisty (8 m) does not.
    assert fb.get("ride_height_front", 0) > 0
    assert tb.get("ride_height_front", 0) == 0


def test_elevation_is_actually_used():
    vm = build_vehicle_model(_CAR, "rr", 6, _SPECS)
    flat = SimpleNamespace(trustworthy=True, straight_fraction=0.15,
                           corner_density_per_km=4.0, elevation_change_m=5)
    hilly = SimpleNamespace(trustworthy=True, straight_fraction=0.15,
                            corner_density_per_km=4.0, elevation_change_m=45)
    assert derive_engineering_intents(vm, flat, OBJ_RACE, None).bias().get("ride_height_front", 0) == 0
    assert derive_engineering_intents(vm, hilly, OBJ_RACE, None).bias().get("ride_height_front", 0) > 0


# ------------------------------------------------------------------ objective shaping

def test_race_protects_rear_tyre_more_than_quali():
    vm = build_vehicle_model(_CAR, "rr", 6, _SPECS)
    race = derive_engineering_intents(vm, _fuji(), OBJ_RACE, None).bias()
    quali = derive_engineering_intents(vm, _fuji(), OBJ_QUALI, None).bias()
    # Race adds rear downforce to protect the rear tyre over the stint; quali does not.
    assert race.get("aero_rear", 0) > quali.get("aero_rear", 0)
    # Quali sharpens the front for one lap (firmer front bar relative to race).
    assert quali.get("arb_front", 0) > race.get("arb_front", 0)


# ------------------------------------------------------------------ coupling

def test_intents_carry_coupling():
    vm = build_vehicle_model(_CAR, "rr", 6, _SPECS)
    plan = derive_engineering_intents(vm, _fuji(), OBJ_RACE, None)
    report = coupling_report(plan)
    assert report, "engineering intents must expose systems-coupling notes"
    # rear toe intent couples to lsd/arb/aero (systems reasoning, not isolated slider).
    joined = " ".join(report)
    assert "toe rear" in joined and ("lsd" in joined or "aero" in joined)


# ------------------------------------------------------------------ honesty / safety

def test_no_track_still_reasons_from_vehicle_only():
    vm = build_vehicle_model(_CAR, "rr", 6, _SPECS)
    plan = derive_engineering_intents(vm, None, OBJ_RACE, None)
    bias = plan.bias()
    assert plan.final_drive_lean == 0.0        # no track → neutral gearing, nothing invented
    assert bias.get("arb_front", 0) < 0        # vehicle reasoning still applies
    assert any("no trustworthy track" in n.lower() for n in plan.notes)


def _advisor():
    rec = SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None, best_lap=lambda: None)
    return DrivingAdvisor(rec, SimpleNamespace(), {})


def test_end_to_end_authored_values_stay_in_range_and_differ_by_track():
    adv = _advisor()
    ranges = resolve_ranges(_CAR)

    def run(trk):
        r = json.loads(adv.build_baseline_setup_response(
            _CAR, ranges, "RR", 6, None, False, session_type="Race",
            duration_mins=45.0, track_name="T", layout_id="full",
            historical_setups=[], track_profile=trk))
        return {c["field"]: c.get("to_clamped") for c in r.get("changes", [])}, r

    fuji, rfuji = run(_fuji())
    twisty, _ = run(_twisty())
    # Genuinely track-specific: gearing differs.
    assert fuji["final_drive"] != twisty["final_drive"]
    assert fuji["final_drive"] < twisty["final_drive"]   # Fuji longer
    # All authored values remain within the car's legal range.
    for f, v in fuji.items():
        if f in ranges and isinstance(v, (int, float)):
            lo, hi = ranges[f]
            assert lo <= v <= hi, f"{f}={v} out of range"
    # The engineering reasoning is surfaced with a vehicle model + coupling.
    er = rfuji.get("engineering_reasoning") or {}
    assert "rear-engined" in er.get("vehicle", "")
    assert er.get("coupling")


def test_end_to_end_default_build_baseline_unchanged_without_engineering():
    # build_baseline_setup with no engineering_bias is byte-for-byte unchanged (safety:
    # existing callers/tests are unaffected).
    from strategy.setup_baseline import build_baseline_setup
    from strategy.setup_driver_profile import build_driver_profile
    a = build_baseline_setup(_CAR, resolve_ranges(_CAR), "RR", 6,
                             build_driver_profile(), None, False, session_type="Race")
    b = build_baseline_setup(_CAR, resolve_ranges(_CAR), "RR", 6,
                             build_driver_profile(), None, False, session_type="Race",
                             engineering_bias=None, final_drive_lean=0.0)
    assert a["setup_fields"] == b["setup_fields"]
