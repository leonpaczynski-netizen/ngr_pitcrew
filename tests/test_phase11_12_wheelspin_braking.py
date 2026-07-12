"""Phase 11/12 — wheelspin-subtype gating of LSD accel + rear-lock disposition.

UAT: the engine proposed LSD accel 15->17 despite 'rear loose on throttle' and a
gear_too_short_spin subtype. Now an LSD-accel INCREASE is blocked when the rear is
loose or the cause is short gearing, uncertain subtypes defer, and untreated
feedback (deferred LSD, rear lock) gets an explicit disposition in the analysis.
"""
from __future__ import annotations

import json

from strategy.setup_rule_engine import run_rule_engine
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import build_driver_profile


def _diag(**over):
    d = {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 20.0, "wheelspin_band": "severe",
        "avg_snap": 0.0, "avg_lockups": 0.0,
        "driver_feel_flags": {"snap_oversteer_exit": False, "rear_loose_on_exit": False,
                              "braking_instability": False, "floaty_front": False,
                              "entry_understeer": False},
        "gearbox_flag": "preserve", "compliance_priority": False,
        "aero_front_near_min": False, "aero_rear_near_min": False, "aero_rear_healthy": False,
        "dominant_problem": "wheelspin", "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "both_rear_spin",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0, "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None, "tyre_wear_high": False,
        "driver_feel_traction_status": "unknown",
    }
    for k, v in over.items():
        if k == "flags":
            d["driver_feel_flags"].update(v)
        else:
            d[k] = v
    return d


def _lsd_increases(diag):
    plan = run_rule_engine(diag, {"lsd_accel": 15, "lsd_decel": 10, "final_drive": 4.25},
                           resolve_ranges(""), build_driver_profile())
    return [c.rule_id for c in plan.proposed if c.field == "lsd_accel" and c.delta > 0]


# ------------------------------------------------------------- rule gating

def test_traction_subtype_allows_lsd_increase():
    assert _lsd_increases(_diag(wheelspin_subtype="both_rear_spin")), "traction wheelspin should allow an LSD increase"


def test_gear_too_short_blocks_lsd_increase():
    assert _lsd_increases(_diag(wheelspin_subtype="gear_too_short_spin")) == []


def test_rear_loose_blocks_lsd_increase():
    assert _lsd_increases(_diag(flags={"rear_loose_on_exit": True})) == []


def test_snap_subtype_blocks_generic_lsd_increase():
    # The GENERIC LSD-accel rules (B6/C5) must not fire on snap. (P1 is a
    # deliberate Porsche-RR-specific exception with its own rationale — out of scope.)
    fired = _lsd_increases(_diag(wheelspin_subtype="snap_throttle_induced"))
    assert "B6" not in fired and "C5_exit_lsd_accel" not in fired


def test_insufficient_subtype_blocks_lsd_increase():
    assert _lsd_increases(_diag(wheelspin_subtype="insufficient_data")) == []


# ------------------------------------------------------------- dispositions

def _advisor(monkeypatch):
    import tests.test_group41_validation_gate as G
    laps = [G._make_lap(wheelspin_count=20, rev_limiter_by_gear={2: 5, 3: 3})]
    adv = G._make_full_advisor({}, laps)
    import strategy.driving_advisor as da
    monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
        "status": "APPROVED", "warnings": [], "contradictions": [],
        "missing_evidence": [], "explanation_notes": "ok"}))
    return adv


def test_disposition_gear_too_short_defers_lsd(monkeypatch):
    adv = _advisor(monkeypatch)
    setup = {"lsd_accel": 15, "final_drive": 4.25, "aero_front": 400, "aero_rear": 600}
    res = json.loads(adv.build_combined_setup_response(
        setup_dict=setup, car_name="", feeling="Exit Stability: Rear loose on throttle"))
    analysis = res.get("analysis", "")
    assert "LSD accel change DEFERRED" in analysis
    # No lsd_accel increase was applied.
    assert all(c.get("field") != "lsd_accel" or c.get("to", 0) <= 15
               for c in res.get("changes", []))


def test_disposition_rear_lock_noted(monkeypatch):
    adv = _advisor(monkeypatch)
    setup = {"brake_bias": 0, "aero_front": 400, "aero_rear": 600}
    res = json.loads(adv.build_combined_setup_response(
        setup_dict=setup, car_name="", feeling="Rear Under Braking: Locks up rear"))
    assert "Rear lock under braking NOTED" in res.get("analysis", "")
