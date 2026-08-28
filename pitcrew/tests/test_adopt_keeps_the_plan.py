"""What survives an adaptation, and what a stop does to the rubber on record.

A re-plan changes the **shape** of the race - how many laps each stint runs.
It says nothing about what goes on the car. `adopt` wrote `None` over both the
compound and the fuel of every remaining stint anyway, so the first adaptation
of any race threw away the two answers the plan existed to give:

* `state.next_compound` went `None`, and `_box_now` names the compound only
  when there is one - so a plan that said RM produced **"Box this lap."** with
  no tyre in it, in a race that may require a specific one.
* `stints[i]["fuel_l"]` went `None`, and the push-to-talk snapshot reads
  `stopFuelL` straight off it - so *"how much fuel do I take"* lost its answer.

And the half that is worse, because it is silent: `state.tyre_compound` is
only ever **written**, never cleared. With the adopted stint naming no
compound, `_apply_stint` left the previous stint's rubber in place, and
`_tag_lap_compound` then wrote it onto every lap of the new set. Its own
docstring says what that costs: a wear rate attributed to the wrong tyre is
not a gap in the model, it is a corruption of it.
"""
from __future__ import annotations

from pitcrew.race.coordinator import RaceCoordinator


def a_plan() -> dict:
    return {"stints": [
        {"laps": 10, "compound": "RM", "fuel_l": 37.4, "start_lap": 1},
        {"laps": 10, "compound": "RS", "fuel_l": 48.0, "start_lap": 11},
    ]}


def running(plan=None, lap: int = 6) -> RaceCoordinator:
    race = RaceCoordinator(plan or a_plan())
    race.state.lap = lap
    race.state.laps_total = 20
    return race


def test_a_reshaped_race_keeps_the_rubber_the_plan_chose():
    """The re-planner moved the stop. It did not change the tyres."""
    race = running()
    race.adopt((6, 8))
    assert [s["compound"] for s in race._stints[race.state.stint_index:]] \
        == ["RM", "RS"]
    assert race.state.next_compound == "RS", \
        "'Box this lap' would name no tyre on a plan that named RS"


def test_the_replanner_s_own_compounds_win_where_it_supplied_them():
    race = running()
    race.adopt((6, 8), compounds=("RM", "RH"))
    assert [s["compound"] for s in race._stints[race.state.stint_index:]] \
        == ["RM", "RH"]


def test_a_stint_the_plan_never_had_carries_nothing_rather_than_guessing():
    """Three stints out of a two-stint plan: the third has no answer on file,
    and `None` there is the truth rather than a discard."""
    race = running()
    race.adopt((4, 5, 5))
    assert [s["compound"] for s in race._stints[race.state.stint_index:]] \
        == ["RM", "RS", None]


def test_fuel_is_not_carried_because_the_stint_length_changed():
    """**Deliberately not carried.** A fill is sized for the stint it feeds,
    and the whole point of an adaptation is that the stint is now a different
    length. Carrying 48 litres onto a stint that is four laps shorter is a
    measured-looking number that is simply wrong; `None` sends the fill back
    to `refuel`, which sizes it from the laps actually remaining."""
    race = running()
    race.adopt((6, 8))
    assert all(s["fuel_l"] is None
               for s in race._stints[race.state.stint_index:])


def test_a_stop_onto_an_unnamed_compound_clears_the_rubber_on_record():
    """**The silent one.** Fresh tyres went on and the adopted plan cannot say
    which - so the honest reading is "unknown", not the set that just came off
    the car. CLAUDE.md §4.3: missing is null, never a stale real value."""
    race = running()
    race.state.tyre_compound = "RM"
    race.adopt((4, 6))
    race._stints[race.state.stint_index + 1]["compound"] = None
    race._apply_stint(race.state.stint_index + 1, over_a_stop=True)
    assert race.state.tyre_compound is None, \
        "every lap of the new set would be tagged with the old set's rubber"


def test_an_adaptation_that_crosses_no_stop_leaves_the_rubber_alone():
    """The counterpart, and why this is not just "clear it always": adopting a
    new shape does not change the tyres that are on the car right now."""
    race = running()
    race.state.tyre_compound = "RM"
    race.adopt((6, 8))
    assert race.state.tyre_compound == "RM"
