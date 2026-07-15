"""Evidence-scaled driver-fit tests (strategy/driver_fit).

Prove the driver profile now tailors the car IN PROPORTION to how far it sits from
the driver's window (not a fixed nudge), leaves a well-fitting car alone, is
range-aware, net-resolves opposing preferences, and reaches the telemetry path.
"""
from __future__ import annotations

import json

from strategy.driver_fit import derive_driver_fit, driver_fit_bias, driver_fit_reasoning
from strategy.setup_driver_profile import build_driver_profile, DriverProfile
from strategy.setup_ranges import resolve_ranges

_CAR = "Porsche 911 RSR (991) '17"


def _ranges():
    return resolve_ranges(_CAR)


def _profile(**over):
    base = dict(profile_version="t", style_tags=[], hard_constraints=[],
                prefers_rear_stability=False, dislikes_snap_exit=False,
                trail_braker=False, rotation_without_snap=False,
                prefers_front_bite=False, dislikes_floaty_front=False,
                protects_downforce=False, race_values_consistency=False)
    base.update(over)
    base["style_tags"] = [k for k, v in base.items() if v is True]
    return DriverProfile(**base)


def _far_setup():
    # stiff front, min aero, rearward brake, high accel lock — actively against a
    # front-bite / stable-rear / no-snap / trail-braking driver.
    return {"arb_front": 9, "arb_rear": 4, "aero_front": 360, "aero_rear": 510,
            "toe_front": 0.2, "toe_rear": -0.5, "brake_bias": 3, "lsd_accel": 40,
            "lsd_decel": 30}


# ------------------------------------------------------------------ evidence-scaling

def test_far_from_preference_produces_corrective_moves():
    prof = _profile(prefers_front_bite=True, prefers_rear_stability=True,
                    trail_braker=True, dislikes_snap_exit=True)
    moves = {m.field: m for m in derive_driver_fit(prof, _far_setup(), _ranges())}
    # front freed, rear planted, brake forward, accel lock reduced — all correct.
    assert moves["arb_front"].delta < 0
    assert moves["toe_front"].delta < 0              # toe-out
    assert moves["toe_rear"].delta > 0               # toe-in
    assert moves["brake_bias"].delta < 0             # forward
    assert moves["lsd_accel"].delta < 0              # less lock


def test_already_fitting_car_is_left_alone():
    prof = _profile(prefers_front_bite=True)
    # arb_front already soft (front-bite side) -> no arb_front move.
    fit = _far_setup(); fit["arb_front"] = 3
    fields = {m.field for m in derive_driver_fit(prof, fit, _ranges())}
    assert "arb_front" not in fields


def test_move_scales_with_distance_from_window():
    prof = _profile(prefers_front_bite=True)   # wants arb_front lower
    r = _ranges()
    # Slightly-too-stiff vs very-stiff front → the very-stiff car moves at least as far.
    near = {m.field: m for m in derive_driver_fit(prof, {**_far_setup(), "arb_front": 6}, r)}
    far = {m.field: m for m in derive_driver_fit(prof, {**_far_setup(), "arb_front": 10}, r)}
    assert abs(far["arb_front"].delta) >= abs(near.get("arb_front").delta if near.get("arb_front") else 0)


def test_range_aware_same_fraction_different_range():
    # A 0-100 vs a 0-10 field at the same fractional violation → delta scales with range.
    prof = _profile(prefers_front_bite=True)
    wide = {"aero_front": (0, 100)}
    narrow = {"aero_front": (0, 10)}
    mw = derive_driver_fit(prof, {"aero_front": 10}, wide)   # frac 0.10, wants >=0.45
    mn = derive_driver_fit(prof, {"aero_front": 1}, narrow)  # frac 0.10, wants >=0.45
    dw = {m.field: m for m in mw}["aero_front"].delta
    dn = {m.field: m for m in mn}["aero_front"].delta
    assert abs(dw) > abs(dn)                          # same fraction, bigger range → bigger delta


# ------------------------------------------------------------------ trade-off band

def test_opposing_prefs_form_a_band():
    prof = _profile(rotation_without_snap=True, race_values_consistency=True)
    r = _ranges()

    def move(v):
        m = [x for x in derive_driver_fit(prof, {"lsd_decel": v}, r) if x.field == "lsd_decel"]
        return m[0].delta if m else 0

    # lsd_decel range (5,60): band ~[0.45,0.55] → [~30, ~35].
    assert move(10) > 0        # below band → pulled up (consistency)
    assert move(55) < 0        # above band → freed (rotation)
    assert move(32) == 0       # inside band → left alone


# ------------------------------------------------------------------ honesty

def test_neutral_profile_no_moves():
    assert derive_driver_fit(_profile(), _far_setup(), _ranges()) == []
    assert derive_driver_fit(None, _far_setup(), _ranges()) == []


def test_reasoning_surface_shape():
    prof = _profile(prefers_front_bite=True)
    intents = derive_driver_fit(prof, _far_setup(), _ranges())
    r = driver_fit_reasoning(prof, intents)
    assert "intents" in r and "note" in r
    for i in r["intents"]:
        assert i["field"] and "confidence" in i and i["drivers"]


# ------------------------------------------------------------------ integration

def test_real_profile_tailors_baseline():
    from strategy.driving_advisor import DrivingAdvisor
    from types import SimpleNamespace
    adv = DrivingAdvisor(SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None,
                                         best_lap=lambda: None), SimpleNamespace(), {})
    r = json.loads(adv.build_baseline_setup_response(
        _CAR, _ranges(), "RR", 6, None, False, session_type="Race",
        duration_mins=45.0, track_name="T", layout_id="full", historical_setups=[]))
    dfr = r.get("driver_fit_reasoning") or {}
    # The real (Leon) profile tailors at least one field from the neutral base.
    assert dfr.get("intents")


def test_driver_fit_reaches_telemetry_path_but_respects_deferrals():
    from tests.test_group63_setup_brain_uat2 import (
        _uat_advisor, _uat_history, _UAT_FEELING, _CAR as UCAR,
    )
    adv = _uat_advisor()
    setup = {"final_drive": 4.25, "transmission_max_speed_kmh": 0, "num_gears": 6,
             "aero_front": 450, "aero_rear": 590, "lsd_initial": 10, "lsd_accel": 40,
             "lsd_decel": 10, "camber_front": 1.0, "camber_rear": 1.5, "arb_front": 6,
             "arb_rear": 5, "toe_front": 0.0, "toe_rear": 0.05, "brake_bias": 0}
    r = json.loads(adv.build_combined_setup_response(
        setup_dict=setup, car_name=UCAR, feeling=_UAT_FEELING, purpose="Race",
        drivetrain="RR", historical_setups=_uat_history(), track_name="NGR",
        fuel_multiplier=3.0, refuel_rate_lps=1.0))
    # Driver-fit reasoning is surfaced on the telemetry path (was zero before).
    assert r.get("driver_fit_reasoning")
    # The balance solver's DEFERRED lsd fields are NOT authored by driver-fit.
    authored = {c["field"] for c in r.get("changes", [])}
    assert "lsd_accel" not in authored and "lsd_decel" not in authored
