"""Discipline intelligence tests (Engineering-Brain Phase 4).

Base / Qualifying / Race are independent engineering products: soft-tyre qualifying
enforcement, objective-specific RPM/shift intent, and distinct scoring priorities.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from strategy.discipline_objectives import (
    softest_dry_compound, qualifying_tyre_plan, objective_rpm_target,
    objective_priorities, discipline_objective_summary,
)
from strategy.setup_ranges import resolve_ranges

_CAR = "Porsche 911 RSR (991) '17"


# ------------------------------------------------------------------ soft-tyre quali

def test_softest_dry_compound():
    assert softest_dry_compound(["RM", "RS", "RH"]) == "RS"
    assert softest_dry_compound(["RH", "RM"]) == "RM"
    assert softest_dry_compound(["SM", "SH"]) == "SM"
    assert softest_dry_compound(["RI", "RW"]) is None       # wet only → no dry pick
    assert softest_dry_compound([]) is None


def test_qualifying_tyre_plan_picks_softest():
    tp = qualifying_tyre_plan(["RM", "RS", "RH"])
    assert tp.compound == "RS" and "Racing Soft" in tp.name
    assert "one flying lap" in tp.reason


def test_qualifying_tyre_plan_respects_required():
    # If only RM/RH are legal (required), pick the softest of those.
    tp = qualifying_tyre_plan(["RS", "RM", "RH"], required=["RM", "RH"])
    assert tp.compound == "RM"


def test_qualifying_tyre_plan_no_dry_is_honest():
    tp = qualifying_tyre_plan(["RI", "RW"])
    assert tp.compound == "" and "cannot enforce" in tp.reason


# ------------------------------------------------------------------ RPM / shift intent

def test_objective_rpm_targets_differ():
    assert objective_rpm_target("qualifying").shift_style == "rev_out"
    assert objective_rpm_target("race").shift_style == "short_shift"
    assert objective_rpm_target("base").shift_style == "balanced"
    assert "short-shift" in objective_rpm_target("race").note


# ------------------------------------------------------------------ scoring priorities

def test_objective_priorities_are_distinct():
    q = objective_priorities("qualifying")
    r = objective_priorities("race")
    # Qualifying prizes one-lap pace and de-emphasises tyre life; race is the opposite.
    assert q["one_lap_pace"] > 1.0 and q["tyre_life"] < 0.5
    assert r["tyre_degradation"] > 1.0 and r["lap_time_variance"] > 1.0
    assert r.get("peak_grip", 1.0) < q["peak_grip"]


# ------------------------------------------------------------------ summary

def test_discipline_summary_qualifying_enforces_tyre():
    s = discipline_objective_summary("qualifying", available_tyres=["RM", "RS", "RH"])
    assert s["tyre"]["enforced"] and s["tyre"]["compound"] == "RS"
    assert s["rpm"]["shift_style"] == "rev_out"
    assert s["priorities"]["one_lap_pace"] > 1.0


def test_discipline_summary_race_has_no_tyre_enforcement():
    s = discipline_objective_summary("race")
    assert "tyre" not in s                                  # only qualifying enforces
    assert s["rpm"]["shift_style"] == "short_shift"


# ------------------------------------------------------------------ integration

def test_discipline_objective_surfaced_in_baseline_response():
    from strategy.driving_advisor import DrivingAdvisor
    adv = DrivingAdvisor(SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None,
                                         best_lap=lambda: None), SimpleNamespace(), {})
    r = json.loads(adv.build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False, session_type="Qualifying",
        duration_mins=0.0, track_name="Fuji", layout_id="full", historical_setups=[]))
    do = r.get("discipline_objective") or {}
    assert do.get("objective") == "qualifying"
    assert do["rpm"]["shift_style"] == "rev_out"
    assert do["priorities"]["one_lap_pace"] > 1.0
