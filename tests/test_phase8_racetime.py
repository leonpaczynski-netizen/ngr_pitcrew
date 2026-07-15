"""Phase 8 — setup ↔ race-time (aero/fuel) reasoning.

On a fuel-heavy, drag-sensitive circuit with high front aero, high fuel use gets a
controlled A/B comparison-run recommendation + refuel arithmetic — never a
fabricated saving. Elsewhere fuel is routed to strategy honestly.
"""
from __future__ import annotations

from types import SimpleNamespace

from strategy.race_time_reasoning import (
    refuel_time_seconds, assess_aero_fuel_tradeoff, FUEL_SENSITIVE_MULTIPLIER,
)
from strategy.track_tune_profile import build_track_tune_profile


def _straight_track():   # Fuji-like -> aero_bias "trim", trustworthy
    return build_track_tune_profile("fuji", "full",
                                    seed_layout=SimpleNamespace(length_m=4563, corners_expected=16,
                                                                longest_straight_m=1475,
                                                                elevation_change_m=40))


def _twisty_track():
    return build_track_tune_profile("tw", "l",
                                    seed_layout=SimpleNamespace(length_m=2000, corners_expected=16,
                                                                longest_straight_m=200,
                                                                elevation_change_m=10))


# ------------------------------------------------- refuel arithmetic

def test_refuel_time_one_litre_per_second():
    assert refuel_time_seconds(5, 1.0) == 5.0        # 1 L = 1 s at 1 L/s
    assert refuel_time_seconds(10, 2.0) == 5.0
    assert refuel_time_seconds(3, 1.0) == 3.0


def test_refuel_time_none_when_rate_unknown():
    assert refuel_time_seconds(5, 0.0) is None
    assert refuel_time_seconds(5, -1) is None


# ------------------------------------------------- tradeoff assessment

def _assess(**over):
    base = dict(fuel_multiplier=3.0, refuel_rate_lps=1.0, track_profile=_straight_track(),
                aero_front_value=440, aero_front_lo=350, aero_front_hi=450, fuel_use_high=True)
    base.update(over)
    return assess_aero_fuel_tradeoff(**base)


def test_fuel_relevant_on_straight_track_high_fuel_high_aero():
    a = _assess()
    assert a.fuel_relevant_to_setup is True
    assert a.recommend_comparison_run is True
    assert "Run A" in a.comparison_run and "Run B" in a.comparison_run
    assert "L/s" in a.refuel_note
    assert "race time" in a.reason


def test_low_fuel_multiplier_not_relevant():
    assert _assess(fuel_multiplier=1.0).fuel_relevant_to_setup is False


def test_non_drag_sensitive_track_not_relevant():
    assert _assess(track_profile=_twisty_track()).fuel_relevant_to_setup is False


def test_low_front_aero_not_relevant():
    assert _assess(aero_front_value=360).fuel_relevant_to_setup is False


def test_no_fuel_flag_not_relevant():
    assert _assess(fuel_use_high=False).fuel_relevant_to_setup is False


def test_note_empty_when_not_relevant():
    assert _assess(fuel_multiplier=1.0).as_note() == ""


# ------------------------------------------------- integration

def test_fuel_note_recommends_comparison_run_on_drag_track():
    import json
    import tests.test_group41_validation_gate as G
    laps = [G._make_lap()]
    adv = G._make_full_advisor({}, laps)
    setup = {"aero_front": 440, "aero_rear": 690}
    res = json.loads(adv.build_combined_setup_response(
        setup_dict=setup, car_name="Porsche 911 RSR (991) '17",
        feeling="Fuel Use: Higher than expected",
        fuel_multiplier=3.0, refuel_rate_lps=1.0, track_profile=_straight_track()))
    assert "Comparison run" in res["analysis"]


def test_fuel_note_routes_to_strategy_when_not_drag_sensitive():
    import json
    import tests.test_group41_validation_gate as G
    adv = G._make_full_advisor({}, [G._make_lap()])
    res = json.loads(adv.build_combined_setup_response(
        setup_dict={"aero_front": 400}, car_name="Porsche 911 RSR (991) '17",
        feeling="Fuel Use: Higher than expected",
        fuel_multiplier=1.0, refuel_rate_lps=1.0, track_profile=_twisty_track()))
    assert "Comparison run" not in res["analysis"]
    assert "Strategy tab" in res["analysis"]
