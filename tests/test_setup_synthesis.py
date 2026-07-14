"""Complete setup synthesis tests (Engineering-Brain Phase 3).

Proves the engine defines a TARGET handling model, generates COMPLETE candidate setups
within the Phase-2 working windows, scores them for the objective via the parameter
interaction graph, and selects the best — reasoning in coupled systems, not sliders.
"""
from __future__ import annotations

from types import SimpleNamespace

from strategy.setup_engineering_context import build_setup_engineering_context
from strategy.setup_synthesis import (
    build_target_handling_model, generate_candidates, score_candidate,
    synthesize_setup, PARAMETER_INTERACTIONS, HANDLING_AXES, SetupCandidate,
)
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import build_driver_profile

_CAR = "Porsche 911 RSR (991) '17"


def _prior():
    return {"lsd_initial": {"value": 22, "tier": 1, "source": "W"},
            "lsd_decel": {"value": 33, "tier": 1, "source": "W"},
            "camber_front": {"value": 2.5, "tier": 1, "source": "W"}}


def _ctx(objective, *, diag=None, prior=None, track=True):
    tp = SimpleNamespace(trustworthy=True, straight_fraction=0.32,
                         corner_density_per_km=3.5, summary=lambda: "Fuji") if track else None
    return build_setup_engineering_context(
        car=_CAR, objective=objective, ranges=resolve_ranges(_CAR), drivetrain="RR",
        profile=build_driver_profile(), track_profile=tp, history_prior=prior or {},
        diagnosis=diag or {})


# ------------------------------------------------------------------ target model

def test_target_model_differs_by_objective():
    race = build_target_handling_model(_ctx("race")).targets
    quali = build_target_handling_model(_ctx("qualifying")).targets
    # Race protects the tyre and values consistency; qualifying does the opposite.
    assert race["tyre_preservation"] > quali["tyre_preservation"]
    assert race["consistency"] > quali["consistency"]
    # Qualifying pushes rotation harder for one lap.
    assert quali["entry_rotation"] >= race["entry_rotation"]


def test_rr_and_feedback_shape_target():
    t = build_target_handling_model(
        _ctx("race", diag={"driver_feel_flags": {"mid_corner_understeer": True,
                                                 "rear_loose_on_exit": True}})).targets
    # RR + understeer → front support; RR + rear-loose → power-oversteer resistance.
    assert t["apex_front_support"] > 0.3
    assert t["power_oversteer_resistance"] > 0.3


# ------------------------------------------------------------------ interaction graph

def test_interaction_graph_sane_signs():
    # Stiffer front bar reduces front grip → less apex support / less rotation.
    assert PARAMETER_INTERACTIONS["arb_front"]["apex_front_support"] < 0
    # More rear aero → more exit traction + oversteer resistance.
    assert PARAMETER_INTERACTIONS["aero_rear"]["exit_traction"] > 0
    assert PARAMETER_INTERACTIONS["aero_rear"]["power_oversteer_resistance"] > 0
    # More accel lock → traction up but oversteer resistance down (RR).
    assert PARAMETER_INTERACTIONS["lsd_accel"]["power_oversteer_resistance"] < 0


# ------------------------------------------------------------------ candidates

def test_candidates_are_full_field_and_in_window():
    ctx = _ctx("race", prior=_prior())
    target = build_target_handling_model(ctx)
    cands = generate_candidates(ctx, target)
    assert len(cands) >= 3
    for c in cands:
        assert len(c.values) == len(ctx.working_windows)     # every field authored
        for f, v in c.values.items():
            w = ctx.working_windows[f]
            assert w.low - 1e-6 <= v <= w.high + 1e-6         # within the legal window


def test_score_rewards_target_match():
    ctx = _ctx("race", diag={"driver_feel_flags": {"mid_corner_understeer": True}},
               prior=_prior())
    target = build_target_handling_model(ctx)
    # A candidate that softens the front (more apex support) should beat one that stiffens
    # it, given a front-support target.
    soft = dict(ctx.working_windows)
    vals_soft = {f: (w.low if f == "arb_front" else
                     (w.preferred if w.preferred is not None else (w.low + w.high) / 2))
                 for f, w in ctx.working_windows.items()}
    vals_stiff = dict(vals_soft); vals_stiff["arb_front"] = ctx.working_windows["arb_front"].high
    s_soft = score_candidate(SetupCandidate("soft", vals_soft, {}), target, ctx).score
    s_stiff = score_candidate(SetupCandidate("stiff", vals_stiff, {}), target, ctx).score
    assert s_soft > s_stiff


# ------------------------------------------------------------------ synthesis

def test_synthesis_selects_best_and_differs_by_objective():
    race = synthesize_setup(_ctx("race", prior=_prior(),
                                 diag={"driver_feel_flags": {"rear_loose_on_exit": True}}))
    quali = synthesize_setup(_ctx("qualifying", prior=_prior()))
    assert race.best is not None and quali.best is not None
    # The winner is the top-scored candidate.
    assert race.best.score == max(c.score for c in race.candidates)
    # Complete + materially objective-specific.
    diff = [f for f in race.best.values if race.best.values[f] != quali.best.values.get(f)]
    assert len(diff) >= 4


def test_synthesis_uses_proven_values():
    r = synthesize_setup(_ctx("race", prior=_prior()))
    # The proven LSD decel / camber sit inside the chosen setup's neighbourhood.
    assert r.best.values["lsd_decel"] == 33 or abs(r.best.values["lsd_decel"] - 33) <= 8
    j = r.as_json()
    assert j["target_handling"] and j["best"] and j["candidates"]


def test_synthesis_honest_confidence_without_evidence():
    r = synthesize_setup(_ctx("base", prior={}, track=False))
    assert r.confidence == "low"
    assert r.best is not None       # still authors a complete setup, honestly low-conf
