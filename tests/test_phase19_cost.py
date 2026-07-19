"""Phase 19 — cost-of-knowledge + budget-planner domain tests.

Engineering VALUE is reused verbatim from Phase 17 (never recomputed). Cost constants are all
visible. The budget planner is a deterministic greedy fit in the given rank order - NOT an
optimiser or scheduler; it selects/executes/mutates nothing.
"""
import inspect

import pytest

from strategy.engineering_cost_model import (
    estimate_experiment_cost, plan_budget, ExperimentCostEstimate, EngineeringBudget,
    COST_CONSTANTS, ENGINEERING_COST_VERSION, MIN_CLEAN_LAPS, WARMUP_LAPS, AB_A_REVERT_LAPS,
    TYRE_LAPS_PER_SET,
)


def _exp(cid="c1", field="arb_front", value=0.8, role="primary_discriminator",
         outcome="not_tested", coupled=False, rank=0):
    return {"candidate_id": cid, "field": field, "engineering_value": value,
            "campaign_role": role, "outcome_state": outcome, "phase17_rank": rank,
            "attribution_scope": "coupled_pair" if coupled else "single_field"}


def test_single_field_lap_budget():
    e = estimate_experiment_cost(_exp())
    assert e.laps == WARMUP_LAPS + MIN_CLEAN_LAPS + MIN_CLEAN_LAPS + AB_A_REVERT_LAPS
    assert e.warmup_laps == WARMUP_LAPS and e.baseline_laps == MIN_CLEAN_LAPS
    assert e.revert_laps == AB_A_REVERT_LAPS
    assert e.ab_structure == "A/B/A"
    assert e.testable is True


def test_coupled_pair_costs_more_test_laps():
    single = estimate_experiment_cost(_exp(coupled=False))
    coupled = estimate_experiment_cost(_exp(coupled=True))
    assert coupled.test_laps == single.test_laps + MIN_CLEAN_LAPS
    assert coupled.laps > single.laps


def test_value_reused_not_recomputed():
    e = estimate_experiment_cost(_exp(value=0.73))
    assert e.engineering_value == 0.73
    # value/lap and info-gain/tyre-set are pure divisions of the reused value
    assert e.value_per_lap == round(0.73 / e.laps, 6)
    assert e.info_gain_per_tyre_set == round(0.73 / e.tyre_sets, 6)


def test_confidence_share_by_role():
    disc = estimate_experiment_cost(_exp(role="primary_discriminator", value=1.0))
    other = estimate_experiment_cost(_exp(role="validation", value=1.0))
    assert disc.estimated_confidence_gain > other.estimated_confidence_gain


def test_tyre_and_fuel_derived_from_laps():
    e = estimate_experiment_cost(_exp())
    assert e.tyre_sets == round(e.laps / TYRE_LAPS_PER_SET, 3)
    assert e.fuel_laps == round(e.laps * 1.0, 2)


def test_retired_and_tested_not_testable():
    assert estimate_experiment_cost(_exp(role="retired")).testable is False
    assert estimate_experiment_cost(
        _exp(outcome="confirmed_improvement")).testable is False


def test_cost_constants_visible_on_estimate():
    e = estimate_experiment_cost(_exp())
    assert e.cost_constants == COST_CONSTANTS
    assert set(COST_CONSTANTS) >= {"min_clean_laps", "warmup_laps", "ab_a_revert_laps",
                                   "tyre_laps_per_set"}


def test_minutes_override():
    fast = estimate_experiment_cost(_exp(), minutes_per_lap=1.0)
    slow = estimate_experiment_cost(_exp(), minutes_per_lap=3.0)
    assert slow.time_minutes > fast.time_minutes


def test_never_raises_on_garbage():
    for junk in (None, {}, {"engineering_value": "x"}, {"campaign_role": None}):
        e = estimate_experiment_cost(junk)
        assert isinstance(e, ExperimentCostEstimate)


# ---- budget planner -------------------------------------------------------- #
def _est(cid, value, rank, laps_ok=True):
    return estimate_experiment_cost(_exp(cid=cid, value=value, rank=rank))


def test_budget_unknown_defers_all():
    ests = [_est("a", 0.9, 0), _est("b", 0.5, 1)]
    b = plan_budget(ests, session_budget={})
    assert b.budget_known is False
    assert len(b.recommended) == 0 and len(b.deferred) == 2


def test_budget_greedy_fit_in_rank_order():
    ests = [_est("a", 0.9, 0), _est("b", 0.5, 1), _est("c", 0.3, 2)]
    # each costs 13 laps; allow ~2 experiments of time
    b = plan_budget(ests, session_budget={"session_minutes_remaining": 13 * 2 * 2.0})
    assert b.budget_known is True
    rec_ids = [r["candidate_id"] for r in b.recommended]
    assert rec_ids == ["a", "b"]                 # top-2 by given rank order
    assert "c" in [d["candidate_id"] for d in b.deferred]


def test_budget_tyre_constraint():
    ests = [_est("a", 0.9, 0), _est("b", 0.5, 1)]
    # one experiment ~1.08 tyre sets; allow only 1.5 sets -> only one fits
    b = plan_budget(ests, session_budget={"tyre_sets_available": 1.5})
    assert len(b.recommended) == 1
    assert b.tyre_utilisation is not None


def test_budget_does_not_execute_or_mutate():
    ests = [_est("a", 0.9, 0)]
    b = plan_budget(ests, session_budget={"session_minutes_remaining": 999})
    d = b.to_dict()
    # advisory-only structure: fits/deferred + utilisation, no execution handles
    assert set(d) >= {"recommended", "deferred", "budget_known", "estimated_confidence_increase"}
    assert "optimis" not in d["rationale"].lower() or "no optimis" in d["rationale"].lower()


def test_budget_deterministic():
    ests = [_est("a", 0.9, 0), _est("b", 0.5, 1)]
    sb = {"session_minutes_remaining": 40, "tyre_sets_available": 3}
    assert plan_budget(ests, session_budget=sb).to_dict() == \
        plan_budget(ests, session_budget=sb).to_dict()


def test_only_testable_are_planned():
    ests = [estimate_experiment_cost(_exp(cid="a", role="retired")),
            estimate_experiment_cost(_exp(cid="b", value=0.5, role="primary_discriminator"))]
    b = plan_budget(ests, session_budget={"session_minutes_remaining": 999})
    ids = [r["candidate_id"] for r in b.recommended] + [d["candidate_id"] for d in b.deferred]
    assert "a" not in ids                          # retired experiment never planned


def test_no_forbidden_imports():
    src = inspect.getsource(__import__("strategy.engineering_cost_model", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "time.time", "from data.session_db"):
        assert banned not in src
    assert ENGINEERING_COST_VERSION == "engineering_cost_v1"
