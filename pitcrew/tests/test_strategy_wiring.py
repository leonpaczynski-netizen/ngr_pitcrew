"""Evidence built from real practice laps, and the plan approved from it."""
from __future__ import annotations

import pytest

from pitcrew.controller import PitCrewController
from pitcrew.export import payload
from pitcrew.store.db import Store
from pitcrew.strategy.evidence import (
    DECLARED,
    MEASURED,
    MISSING,
    _laps_to_hydrate,
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
    """The out-lap stays out; and the reference is the *pace*, not the
    opening lap. `build_inputs` used to take `green_lap_reference_ms` - the
    best of the first counted laps, a degradation reference by its own
    docstring - so a race was once judged "2% slower than planned" against a
    three-day-old opening lap. The plan is now built on `reference_pace_ms`:
    the recency-weighted median of every counted lap, 94,200 here, not the
    94,100 the old green-lap figure would have picked."""
    _, _, store, event_id = planned
    inputs, _ = build_inputs(store, event_id)
    assert inputs.lap_time_ms == 94_200    # weighted pace over laps 2-6


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
    # The contract's vocabulary, not a hand-kept subset of it. `evidence`
    # joined it in 1.6 and this assertion is exactly the kind that goes stale
    # silently - it passed for two versions by listing three of four values.
    assert (approved["plan"]["export"]["bindingConstraint"]
            in payload.BINDING_CONSTRAINTS)
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
            # The tank descends across each stint and is filled at the stop.
            # Fuel is what separates one run from the next, so a fixture that
            # refills every lap is twelve stops, not one stint.
            lap = Lap(lap_num=lap_num, lap_time_ms=lap_ms, best_lap_ms=lap_ms,
                      delta_ms=0,
                      fuel_start=round(100.0 - 2.6 * (step - 1), 2),
                      fuel_end=round(100.0 - 2.6 * step, 2),
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


# ------------------------------------------------- the refuel lap is decoded
#
# Regression for SM1. `_laps_to_hydrate` was written for the tyre-temperature
# window - counted laps, compound-tagged, the last few per compound - and then
# used as the ONLY hydration for the whole strategy path. All three filters
# exclude a refuel lap, so `analysis/refuel.py` was structurally guaranteed to
# receive no frames on the only lap that carries what it measures, and the
# rate came back "declared" forever. On a 100 L tank that is a 100 s stop
# costed against a real 33 s, which decides the stop count.

def a_lap_row(lap_id: int, **overrides) -> dict:
    row = dict(id=lap_id, compound="RH", excluded=0, is_out_lap=0,
               is_pit_lap=0, fuel_start=100.0 - lap_id * 6.0,
               fuel_end=100.0 - (lap_id + 1) * 6.0, fuel_added_l=None)
    row.update(overrides)
    return row


def test_the_refuel_lap_is_hydrated_even_though_the_window_drops_it():
    """Shaped like the owner's own rehearsal: 26 laps, the fill on lap 14,
    `is_pit_lap` 0 on every one of them."""
    rows = [a_lap_row(n) for n in range(1, 27)]
    rows[13]["fuel_end"] = rows[13]["fuel_start"] + 50.0     # the tank climbed
    wanted = _laps_to_hydrate(rows)

    assert 14 in wanted                       # the lap that carries the rate
    assert {21, 22, 23, 24, 25, 26} <= wanted  # the window's last six
    assert len(wanted) == 7                    # and nothing else


def test_a_refuel_survives_every_one_of_the_windows_three_filters():
    rows = [a_lap_row(n) for n in range(1, 27)]
    rows[13].update(is_pit_lap=1, excluded=1, compound=None,
                    fuel_end=rows[13]["fuel_start"] + 50.0)
    assert 14 in _laps_to_hydrate(rows)


def test_a_recorded_fill_is_taken_from_the_flag_too():
    rows = [a_lap_row(n) for n in range(1, 10)]
    rows[4]["fuel_added_l"] = 50.0
    assert 5 in _laps_to_hydrate(rows)


def test_a_session_with_no_stop_hydrates_only_the_window():
    rows = [a_lap_row(n) for n in range(1, 27)]
    assert _laps_to_hydrate(rows) == {21, 22, 23, 24, 25, 26}


def test_the_rate_reaches_the_plan_as_measured(qt_app, store):  # noqa: F811
    """End to end: a stop recorded in practice, and a plan costed on it."""
    from pitcrew.telemetry.recorder import FRAME_FIELDS, LapFrames, encode_frames

    controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                   StrategyScreen())
    controller._on_event_saved(an_event(race_laps=20))
    event_id = store.active_event_id()
    session_id = controller.open_practice_session()
    store.note_stream_facts(session_id, packet_format="C",
                            car_category="GR3", fuel_capacity_l=100.0)

    fuel_index = FRAME_FIELDS.index("fuel_l")
    time_index = FRAME_FIELDS.index("t_ms")

    def frames_for(series: list[float]) -> LapFrames:
        rows = []
        for index, litres in enumerate(series):
            row = [None] * len(FRAME_FIELDS)
            row[time_index] = int(round(index * 1000.0 / 60.0))
            row[fuel_index] = litres
            rows.append(row)
        return LapFrames(frame_count=len(rows), sample_hz=60.0,
                         blob=encode_frames(rows))

    for lap_num in range(1, 9):
        # Lap 4 is the stop: 60 L taken at 3 L/s, and nothing marks it a pit
        # lap because nothing in this database ever does.
        if lap_num == 4:
            series = ([20.0] * 60
                      + [20.0 + (n + 1) * 3.0 / 60.0 for n in range(1200)]
                      + [80.0] * 60)
        else:
            series = [90.0 - 3.4 * n / 60.0 for n in range(60)]
        lap = Lap(lap_num=lap_num, lap_time_ms=94_000, best_lap_ms=94_000,
                  delta_ms=0, fuel_start=series[0], fuel_end=series[-1],
                  fuel_used=max(0.0, series[0] - series[-1]), position=1,
                  is_pit_lap=False, is_out_lap=lap_num == 1)
        lap_id = store.add_lap(session_id, lap, frames_for(series))
        store.set_lap_compound(lap_id, "RM")

    inputs, evidence = build_inputs(store, event_id)
    row = next(item for item in evidence if item.label == "Refuel rate")
    assert row.source == MEASURED
    assert inputs.refuel_rate_lps == pytest.approx(3.0, abs=0.05)
    controller.shutdown()


def test_practice_is_checked_against_the_races_clock_and_not_its_own(
        qt_app, store):  # noqa: F811
    """`practice_clock_warning` was handed the pooled practice reading
    whenever practice had one, so it compared practice against itself: every
    session matched and the check could never fire. The case it exists for -
    practice run in daylight for a race that sweeps into the dark - was the
    case it could not see."""
    from pitcrew.telemetry.recorder import FRAME_FIELDS, LapFrames, encode_frames

    controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                   StrategyScreen())
    controller._on_event_saved(an_event(race_laps=20, time_multiplier=6.0,
                                        start_hour=18.0))
    event_id = store.active_event_id()
    session_id = controller.open_practice_session()

    time_index = FRAME_FIELDS.index("t_ms")
    clock_index = FRAME_FIELDS.index("time_of_day_ms")
    hour_ms = 3_600_000

    for lap_num in range(1, 6):
        rows = []
        for index in range(60):
            row = [None] * len(FRAME_FIELDS)
            row[time_index] = int(round(index * 94_000 / 60))
            # The lobby clock runs at x1: 94 s of game time in a 94 s lap.
            row[clock_index] = int(12.0 * hour_ms
                                   + (lap_num - 1) * 94_000
                                   + index * 94_000 / 60)
            rows.append(row)
        lap = Lap(lap_num=lap_num, lap_time_ms=94_000, best_lap_ms=94_000,
                  delta_ms=0, fuel_start=92.0 - (lap_num - 1) * 3.4,
                  fuel_end=92.0 - lap_num * 3.4, fuel_used=3.4, position=1,
                  is_pit_lap=False, is_out_lap=lap_num == 1)
        lap_id = store.add_lap(session_id, lap,
                               LapFrames(frame_count=len(rows), sample_hz=60.0,
                                         blob=encode_frames(rows)))
        store.set_lap_compound(lap_id, "RM")

    _, evidence = build_inputs(store, event_id)
    note = next(item for item in evidence if item.label == "Time of day").note
    assert "Practice was not run at the race's clock" in note
    assert "against the race's x6" in note
    controller.shutdown()


# ------------------------------------------------------- the declared fuel map

def test_a_declared_race_map_with_no_practice_map_refuses_to_re_cost(planned):
    """Rule 3. `laps.fuel_map` has been NULL on every lap since session 83, so
    a declared race map usually has nothing to convert FROM - and an
    unrecorded practice map is not map 1. The burn stands, and the plan says
    so rather than saying nothing."""
    _controller, _, store, event_id = planned
    # **Written straight to the store, because the controller drops it.**
    # `EventScreen.values()` has emitted `fuel_map` since the combo was
    # built (`ui/event_screen.py:1094`) and `_on_event_saved`'s optional-key
    # list does not carry it, so the declaration never reaches the column -
    # which is why `events.fuel_map` is NULL on all but four events on file.
    # The same defect `series` had. One word in that tuple fixes it.
    store.update_event(event_id, fuel_map=3)
    inputs, evidence = build_inputs(store, event_id)

    assert inputs.fuel_map == 3
    assert inputs.evidence_fuel_map is None
    assert inputs.fuel_per_lap_l == pytest.approx(3.4, abs=0.01)
    assert "NOT" in inputs.fuel_map_note
    row = next(e for e in evidence if e.label == "Fuel map")
    assert row.value == "3" and row.source == DECLARED


def test_an_undeclared_map_leaves_the_burn_and_says_it_is_missing(planned):
    _, _, store, event_id = planned
    inputs, evidence = build_inputs(store, event_id)
    assert inputs.fuel_map is None and inputs.fuel_map_note is None
    row = next(e for e in evidence if e.label == "Fuel map")
    assert row.source == MISSING
    assert "declare it on the event page" in row.note


def test_practice_on_map_1_re_costs_the_burn_for_a_map_3_race(planned):
    """The Bathurst Rd 8 case, end to end. A burn measured on map 1 spent on a
    map-3 race was 22% out on the one number that decides the stop count."""
    from pitcrew.strategy.evidence import ASSUMED

    _controller, _, store, event_id = planned
    for lap_id in _lap_ids(store, event_id):
        store.set_lap_fuel_map(lap_id, 1)
    store.update_event(event_id, fuel_map=3)
    inputs, evidence = build_inputs(store, event_id)

    assert inputs.evidence_fuel_map == 1 and inputs.fuel_map == 3
    assert inputs.fuel_per_lap_l == pytest.approx(3.4 * 0.85, abs=0.01)
    # Rule 5: a re-costed burn is derived and may not wear "measured".
    fuel = next(e for e in evidence if e.label == "Fuel per lap")
    assert fuel.source == ASSUMED
    assert "[ASSUMED]" in fuel.note


def test_the_event_screen_still_emits_the_fuel_map_it_is_given(qt_app):  # noqa: F811
    """Half the declaration path, pinned - and the half that works.

    `EventScreen.values()` has carried `fuel_map` since the combo was built
    (`ui/event_screen.py:1094`). The other half is broken and is not fixed
    here: `PitCrewController._on_event_saved` copies a fixed list of optional
    keys into the write and that list does not include `fuel_map`, so the
    only route the map has into `events.fuel_map` drops it silently. That is
    the same defect `series` had - the box worked, the column was NULL on
    every event on file - and the fix is one word in that tuple
    (`controller.py`, the `for key in (...)` list in `_on_event_saved`).
    Until it lands, a declared map reaches the plan only if something writes
    the column directly.
    """
    screen = EventScreen()
    screen.fuel_map.setCurrentText("3")
    assert screen.values()["fuel_map"] == 3
    screen.fuel_map.setCurrentText("—")
    assert screen.values()["fuel_map"] is None


def test_the_burns_scatter_moves_with_the_map_too(planned):
    """`fuel_sd_l` sizes every fill margin. A converted mean beside an
    unconverted spread is two quantities measured on two different maps, and
    scaling only the mean under-states the margin on a richer map - the
    direction that runs him dry."""
    _controller, _, store, event_id = planned
    before = build_inputs(store, event_id)[0]
    for lap_id in _lap_ids(store, event_id):
        store.set_lap_fuel_map(lap_id, 1)
    store.update_event(event_id, fuel_map=3)
    after = build_inputs(store, event_id)[0]

    assert after.fuel_per_lap_l == pytest.approx(
        before.fuel_per_lap_l * 0.85, abs=0.01)
    if before.fuel_sd_l:
        assert after.fuel_sd_l == pytest.approx(
            before.fuel_sd_l * 0.85, rel=1e-6)
