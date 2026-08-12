"""Evidence built from real practice laps, and the plan approved from it."""
from __future__ import annotations

import pytest

from pitcrew.controller import PitCrewController
from pitcrew.store.db import Store
from pitcrew.strategy.evidence import (
    DECLARED,
    MEASURED,
    MISSING,
    build_inputs,
)
from pitcrew.telemetry.session_state import Lap
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen
from pitcrew.ui.strategy_screen import StrategyScreen

from .test_controller import an_event, qt_app  # noqa: F401


@pytest.fixture()
def planned(qt_app, store: Store):  # noqa: F811
    event_screen = EventScreen()
    practice = PracticeScreen()
    strategy = StrategyScreen()
    controller = PitCrewController(store, event_screen, practice, strategy)
    controller._on_event_saved(an_event(race_laps=20))
    event_id = store.active_event_id()

    session_id = controller.open_practice_session()
    store.note_stream_facts(session_id, packet_format="C",
                            car_category="GR3", fuel_capacity_l=100.0)
    for lap_num in range(1, 7):
        lap = Lap(
            lap_num=lap_num, lap_time_ms=94_000 + lap_num * 50,
            best_lap_ms=94_050, delta_ms=0,
            fuel_start=92.0 - (lap_num - 1) * 3.4,
            fuel_end=92.0 - lap_num * 3.4, fuel_used=3.4, position=1,
            is_pit_lap=False, is_out_lap=lap_num == 1,
        )
        lap_id = store.add_lap(session_id, lap)
        store.set_lap_compound(lap_id, "RM")
    yield controller, strategy, store, event_id
    controller.shutdown()


def _lap_ids(store: Store, event_id: int):
    return [row["id"] for row in store.list_event_laps(event_id, "practice")]


# ------------------------------------------------------------------ evidence

def test_fuel_per_lap_is_measured_from_the_laps(planned):
    _, _, store, event_id = planned
    inputs, evidence = build_inputs(store, event_id)
    assert inputs.fuel_per_lap_l == pytest.approx(3.4, abs=0.01)
    fuel = next(e for e in evidence if e.label == "Fuel per lap")
    assert fuel.source == MEASURED


def test_the_out_lap_does_not_set_the_reference(planned):
    _, _, store, event_id = planned
    inputs, _ = build_inputs(store, event_id)
    assert inputs.lap_time_ms == 94_100    # lap 2, not the out-lap


def test_wear_is_missing_until_the_gauge_is_read(planned):
    _, _, store, event_id = planned
    inputs, evidence = build_inputs(store, event_id)
    assert inputs.wear_per_lap is None
    wear = next(e for e in evidence if e.label == "Tyre wear")
    assert wear.source == MISSING
    assert "gauge" in wear.note


def test_a_gauge_reading_makes_wear_declared(planned):
    _, _, store, event_id = planned
    store.set_lap_wear(_lap_ids(store, event_id)[-1], 0.30, 0.30, 0.24, 0.24)
    inputs, evidence = build_inputs(store, event_id)
    assert inputs.wear_per_lap == pytest.approx(0.05)
    assert next(e for e in evidence
                if e.label == "Tyre wear").source == DECLARED


def test_pit_loss_comes_from_the_event_as_declared(planned):
    _, _, store, event_id = planned
    _, evidence = build_inputs(store, event_id)
    pit = next(e for e in evidence if e.label == "Pit loss")
    assert pit.source == DECLARED
    assert "track constant" in pit.note


def test_fuel_weight_is_never_presented_as_measured(planned):
    _, _, store, event_id = planned
    _, evidence = build_inputs(store, event_id)
    weight = next(e for e in evidence if e.label == "Fuel weight")
    assert weight.source == "assumed"
    assert "derived, not measured" in weight.note


# --------------------------------------------------------------------- plans

def test_building_produces_ordered_plans(planned):
    controller, strategy, _, _ = planned
    plans = controller.build_strategy()
    assert plans
    assert plans[0].delta_s == 0.0
    assert strategy.approve_button.isEnabled()


def test_missing_inputs_are_warned_about_not_hidden(planned):
    controller, strategy, _, _ = planned
    controller.build_strategy()
    assert "tyre wear rate" in strategy.footer_note.text()


def test_every_input_measured_says_so(planned):
    controller, strategy, store, event_id = planned
    store.set_lap_wear(_lap_ids(store, event_id)[-1], 0.30, 0.30, 0.24, 0.24)
    controller.build_strategy()
    assert "Every input measured" in strategy.footer_note.text()


def test_a_plan_without_practice_refuses_rather_than_inventing(qt_app, store):  # noqa: F811
    event_screen = EventScreen()
    practice = PracticeScreen()
    strategy = StrategyScreen()
    controller = PitCrewController(store, event_screen, practice, strategy)
    controller._on_event_saved(an_event())

    assert controller.build_strategy() == []
    assert "practice lap" in strategy.subtitle.text()
    assert strategy.approve_button.isEnabled() is False
    controller.shutdown()


def test_building_without_an_event_says_so(qt_app, store):  # noqa: F811
    strategy = StrategyScreen()
    controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                   strategy)
    assert controller.build_strategy() == []
    assert "Create an event" in strategy.subtitle.text()
    controller.shutdown()


# ------------------------------------------------------------------ approval

def test_approving_stores_the_plan_and_its_assumptions(planned):
    controller, _, store, event_id = planned
    plans = controller.build_strategy()
    controller.approve_strategy(0)

    approved = store.get_approved_strategy(event_id)
    assert approved is not None
    assert approved["plan"]["stints"][0]["laps"] == plans[0].stints[0].laps
    assert approved["plan"]["export"]["bindingConstraint"] in (
        "tyre", "fuel", "unknown")
    assert "tyre wear rate" in approved["evidence"]["missing"]


def test_approving_a_second_plan_demotes_the_first(planned):
    controller, _, store, event_id = planned
    controller.build_strategy()
    controller.approve_strategy(0)
    controller.approve_strategy(1)

    approved = store.get_approved_strategy(event_id)
    assert approved["label"] == controller._plans[1].label()
    assert len([s for s in store.list_strategies(event_id)
                if s["status"] == "approved"]) == 1


def test_rebuilding_preselects_the_approved_plan(planned):
    controller, strategy, _, _ = planned
    controller.build_strategy()
    controller.approve_strategy(1)
    controller.build_strategy()
    assert strategy._chosen == 1


def test_approving_nothing_is_harmless(planned):
    controller, _, _, _ = planned
    assert controller.approve_strategy(0) is None


# --------------------------------------------- the compound call, end to end

@pytest.fixture()
def two_compounds(qt_app, store: Store):  # noqa: F811
    """A practice day with a stint on each compound, both gauges read.

    Twelve laps on the soft to 66% worn, then twelve on the hard to 36%, the
    hard six tenths a lap slower. That is the evidence the crossover question
    needs, and none of it exists until both stints have been run and read.
    """
    event_screen = EventScreen()
    strategy = StrategyScreen()
    controller = PitCrewController(store, event_screen, PracticeScreen(),
                                   strategy)
    controller._on_event_saved(an_event(race_laps=24))
    event_id = store.active_event_id()
    store.update_event(event_id, available_compounds=["RS", "RH"])

    session_id = controller.open_practice_session()
    store.note_stream_facts(session_id, packet_format="C",
                            car_category="GR3", fuel_capacity_l=100.0)

    lap_num = 0
    for compound, lap_ms, final_wear in (("RS", 93_000, 0.66),
                                         ("RH", 93_600, 0.36)):
        for step in range(1, 13):
            lap_num += 1
            last = step == 12
            lap = Lap(lap_num=lap_num, lap_time_ms=lap_ms, best_lap_ms=lap_ms,
                      delta_ms=0, fuel_start=92.0, fuel_end=89.4,
                      fuel_used=2.6, position=1,
                      is_pit_lap=last, is_out_lap=False)
            lap_id = store.add_lap(session_id, lap)
            store.set_lap_compound(lap_id, compound)
            if last:
                store.set_lap_wear(lap_id, final_wear, final_wear,
                                   final_wear - 0.04, final_wear - 0.04)
    yield controller, strategy, store, event_id
    controller.shutdown()


def test_both_compounds_are_measured_from_the_stints_that_ran(two_compounds):
    _, _, store, event_id = two_compounds
    inputs, _ = build_inputs(store, event_id)

    assert set(inputs.compound_profiles) == {"RS", "RH"}
    assert inputs.compound_profiles["RS"].is_measured
    assert inputs.compound_profiles["RH"].is_measured
    # 66% over the twelve laps the set ran, not over its lap number.
    assert inputs.compound_profiles["RS"].wear_per_lap == pytest.approx(0.055)
    assert inputs.compound_profiles["RH"].wear_per_lap == pytest.approx(0.03)
    assert inputs.compound_profiles["RH"].pace_delta_s == pytest.approx(0.6)


def test_the_evidence_column_says_the_comparison_is_now_possible(two_compounds):
    _, _, store, event_id = two_compounds
    _, evidence = build_inputs(store, event_id)
    row = next(e for e in evidence if e.label == "Compounds compared")
    assert row.source == MEASURED
    assert "RH" in row.value and "RS" in row.value
    assert "rests on evidence" in row.note


def test_the_compound_call_reaches_the_screen(two_compounds):
    controller, strategy, _, _ = two_compounds
    plans = controller.build_strategy()

    assert plans
    assert plans[0].crossover is not None
    assert strategy.crossover_band.isVisibleTo(strategy)
    assert strategy.crossover_band.verdict.text() == plans[0].crossover["verdict"]


def test_one_measured_compound_hides_nothing_but_claims_nothing(planned):
    """The `planned` fixture ran RM only, so there is no comparison to show."""
    controller, strategy, store, event_id = planned
    store.set_lap_wear(_lap_ids(store, event_id)[-1], 0.30, 0.30, 0.24, 0.24)
    controller.build_strategy()

    band = strategy.crossover_band
    if band.isVisibleTo(strategy):
        # Shown only to say the comparison has not been earned yet.
        assert "not a comparison yet" in band.verdict.text()
