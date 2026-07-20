"""Phase 61 — Practice/Qualifying/Race discipline workflow (task items 11-13, 16-18)."""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.ngr_live_pit_wall import LivePitWallMode as PM
from strategy.strategy_maturity import StrategyMaturity as M
from strategy.discipline_workflow import assess_discipline_workflow


def test_practice_mode_no_extra_preconditions():
    g = assess_discipline_workflow(T.SETUP_EXPERIMENT, expected_discipline="race")
    assert g.mode == PM.PRACTICE and g.preconditions_ok is True


def test_qualifying_requires_qualifying_discipline():
    ok = assess_discipline_workflow(T.QUALIFYING, expected_discipline="qualifying")
    assert ok.mode == PM.QUALIFYING and ok.preconditions_ok is True
    bad = assess_discipline_workflow(T.QUALIFYING, expected_discipline="race")
    assert bad.preconditions_ok is False and bad.warnings


def test_race_requires_race_discipline_and_finalised_strategy():
    # not finalised, not accepted -> warning
    g = assess_discipline_workflow(T.RACE, expected_discipline="race",
                                   strategy_maturity=M.DEVELOPING.value, strategy_finalised=False)
    assert g.mode == PM.RACE and g.preconditions_ok is False
    assert any("strategy" in w for w in g.warnings)
    # finalised -> ok
    ok = assess_discipline_workflow(T.RACE, expected_discipline="race", strategy_finalised=True)
    assert ok.preconditions_ok is True


def test_race_low_confidence_accepted_is_ok():
    g = assess_discipline_workflow(T.RACE, expected_discipline="race", low_confidence_accepted=True)
    assert g.preconditions_ok is True


def test_race_simulation_is_race_mode():
    assert assess_discipline_workflow(T.LONG_RACE_RUN, strategy_finalised=True).mode == PM.RACE


def test_qualifying_simulation_is_qualifying_mode():
    assert assess_discipline_workflow(T.QUALIFYING_SIMULATION, expected_discipline="qualifying").mode == PM.QUALIFYING


def test_discipline_gate_deterministic():
    a = assess_discipline_workflow(T.RACE, expected_discipline="race", strategy_finalised=True)
    b = assess_discipline_workflow(T.RACE, expected_discipline="race", strategy_finalised=True)
    assert a.fingerprint == b.fingerprint
