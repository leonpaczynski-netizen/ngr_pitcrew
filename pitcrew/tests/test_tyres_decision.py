"""Row 2.6, pass 2 (the critic on aad9ae3): the tyres decision reaches the
radio, the snapshot, the re-plan, the certifier and every door - not only the
box call."""
from __future__ import annotations

from pitcrew.engineer.intents import BOX_WHAT, PLAN, answer
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.strategy.certify import certify
from pitcrew.strategy.handover import stint_tyre_problems
from pitcrew.strategy.model import Plan, Stint, tyre_limited_laps

from .test_certify import inputs


def _plan(*decisions):
    stints = [{"laps": 7, "compound": "RM", "fuel_l": 50.0, "start_lap": 1}]
    start = 8
    for tyres in decisions:
        stints.append({"laps": 7, "compound": "RM", "fuel_l": 50.0,
                       "start_lap": start, "tyres": tyres})
        start += 7
    return {"stints": stints, "binding_constraint": "fuel"}


def _race(plan):
    return RaceCoordinator(plan, fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=3.0,
                           planned_lap_time_ms=90_000, mandatory_stops=0)


def test_the_radio_says_the_box_calls_decision():
    """BLOCKER: the box call said "No tyres." and "what tyres?" answered
    "RS." - which under a helmet is "fit RS" (rule 13)."""
    no = {"hasPlan": True, "nextCompound": "RM", "nextTyres": False,
          "lapsToStop": 10}
    assert answer(BOX_WHAT, no).text == "No tyres."
    assert answer(PLAN, no).text.startswith("Box in 10 laps, no tyres")
    assert answer(BOX_WHAT, dict(no, nextTyres=True)).text == "RM on."
    assert answer(BOX_WHAT, dict(no, nextTyres=None)).text == "RM."
    assert "onto RM" in answer(PLAN, dict(no, nextTyres=True)).text


def test_the_snapshot_carries_the_decision():
    assert _race(_plan(False)).snapshot()["nextTyres"] is False
    assert _race(_plan(True)).snapshot()["nextTyres"] is True


def test_a_replan_keeps_the_decision():
    """`adopt` rebuilt the stints without `tyres`, so "No tyres." became a
    bare "RS." after the driver accepted a re-plan."""
    race = _race(_plan(False, False))
    assert race.state.next_tyres is False
    race.adopt((5, 10))
    assert race.state.next_tyres is False


def test_a_replan_that_changes_the_compound_puts_a_set_on():
    race = _race(_plan(False))
    race.adopt((5, 10), compounds=("RM", "RS"))
    assert race.state.next_tyres is True


def test_laps_on_one_set_are_summed_across_a_fuel_only_stop():
    """`certify` priced a `tyres: false` stop as a fresh set, so a stated
    fuel-only plan certified straight past the wear cliff."""
    limit = tyre_limited_laps(inputs().wear_per_lap)
    half = limit // 2 + 1
    stints = [{"laps": half, "compound": "RH", "fuel_l": 60.0},
              {"laps": half, "compound": "RH", "fuel_l": 60.0, "tyres": False}]
    got = certify({"stints": stints}, inputs(race_laps=2 * half))
    assert any("stints 1-2 (no tyres at the stop)" in r for r in got.refusals), \
        got.refusals
    stints[1]["tyres"] = True
    got = certify({"stints": stints}, inputs(race_laps=2 * half))
    assert not any("no tyres at the stop" in r for r in got.refusals)


def test_one_rule_for_every_door():
    assert any("stint 2 carries no tyres decision" in p
               for p in stint_tyre_problems(_plan(None)))
    changed = _plan(False)
    changed["stints"][1]["compound"] = "RS"
    assert any("changes compound" in p for p in stint_tyre_problems(changed))
    quoted = stint_tyre_problems(_plan("false"))
    assert any("must be true or false" in p for p in quoted)
    assert not any("absent" in p for p in quoted)
    assert stint_tyre_problems(_plan(True, False)) == []


def test_the_optimisers_plan_says_a_set_goes_on():
    """Bathurst's strategy 30 came from here with no decision at all."""
    plan = Plan(stints=[Stint(10, "RM", 60.0, 1), Stint(10, "RM", 60.0, 11)],
                total_time_s=1800.0, binding_constraint="fuel")
    stints = plan.as_dict()["stints"]
    assert "tyres" not in stints[0] and stints[1]["tyres"] is True
