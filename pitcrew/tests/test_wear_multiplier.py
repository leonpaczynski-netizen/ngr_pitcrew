"""A briefed wear rate is read only at the multiplier it was measured at.

CLAUDE.md §5.2: multiplier linearity is assumed, never proven; never silently
convert. Sardegna on 16 Sep 2026 runs tyre x8; every rate on file was fitted at
x2. A rate that names its multiplier is refused for another; one that names
none - the rows written before the field existed - is used and logged as
assumed, because refusing them all would silence every briefed rate at once.
"""
from __future__ import annotations

from pitcrew.race.coordinator import PlanContext, RaceCoordinator, context_from_event
from pitcrew.race.knowledge import Knowledge, _multiplier


def _knowledge(**entry):
    record = {"perLap": 0.057, "samples": 9}
    record.update(entry)
    return Knowledge(circuit_key="sardegna", wear_rates={"RS": record})


def test_the_multiplier_is_read_in_every_shape_the_row_may_hold():
    assert _multiplier("2x") == 2.0
    assert _multiplier("2") == 2.0
    assert _multiplier(2) == 2.0
    assert _multiplier(8.0) == 8.0
    assert _multiplier(None) is None
    assert _multiplier("normal") is None


def test_a_rate_at_the_same_multiplier_is_used():
    assert _knowledge(multiplier="2x").wear_per_lap("RS", multiplier="2x") == (0.057, 9)


def test_a_rate_at_another_multiplier_is_refused_not_converted():
    assert _knowledge(multiplier="2x").wear_per_lap("RS", multiplier="8x") == (None, 0)


def test_a_rate_with_no_multiplier_is_used_as_assumed():
    assert _knowledge().wear_per_lap("RS", multiplier="8x") == (0.057, 9)


def test_a_race_with_no_declared_multiplier_takes_the_rate():
    assert _knowledge(multiplier="2x").wear_per_lap("RS") == (0.057, 9)


def test_the_event_multiplier_reaches_the_race_and_gates_the_briefing():
    event = {"car_name": "Porsche 911 RSR (991) '17", "track": "Sardegna",
             "layout": "Road Track", "race_type": "laps", "race_laps": 30,
             "tyre_wear_mult": "8x"}
    context = context_from_event(event)
    assert context.tyre_wear_mult == "8x"
    plan = {"stops": 1, "stints": [
        {"laps": 15, "compound": "RS", "fuel_l": 100.0, "start_lap": 1},
        {"laps": 15, "compound": "RS", "fuel_l": 100.0, "start_lap": 16}]}
    race = RaceCoordinator(plan, knowledge=_knowledge(multiplier="2x"))
    assert race.arm(context, context) is True
    assert race.state.tyre_wear_mult == "8x"
    assert race.state.briefed_wear_per_lap is None, "a x2 rate for a x8 race"

    same = RaceCoordinator(plan, knowledge=_knowledge(multiplier="8x"))
    assert same.arm(context, context) is True
    assert same.state.briefed_wear_per_lap == 0.057


def test_the_multiplier_does_not_refuse_a_plan():
    a = PlanContext(car="c", track="t", layout=None, race_laps=20,
                    tyre_wear_mult="2x")
    b = PlanContext(car="c", track="t", layout=None, race_laps=20,
                    tyre_wear_mult="8x")
    assert a.matches(b)[0] is True
