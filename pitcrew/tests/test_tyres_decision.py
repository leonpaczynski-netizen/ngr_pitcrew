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


def test_a_set_on_with_no_compound_is_said_as_a_set_on():
    """Pass 2, BLOCKER: `tyres: true` with no compound - the box call said
    "Tyres on." and "what tyres?" answered "No tyre change planned."."""
    on = {"hasPlan": True, "nextCompound": None, "nextTyres": True,
          "lapsToStop": 3}
    assert answer(BOX_WHAT, on).text == "Tyres on."
    assert answer(PLAN, on).text == "Box in 3 laps, tyres on."
    # And the absence of a decision is still said as one.
    assert answer(BOX_WHAT, dict(on, nextTyres=None)).text \
        == "No tyre change planned."


def test_a_replan_that_adds_a_stop_takes_the_replanners_decisions():
    """Pass 2, MAJOR: carried by position, a lap-14 "No tyres." moved onto a
    new lap-8 stop and the added third stop had no decision at all."""
    plan = {"stints": [
        {"laps": 14, "compound": "RS", "fuel_l": 50.0, "start_lap": 1},
        {"laps": 6, "compound": "RS", "fuel_l": 20.0, "start_lap": 15,
         "tyres": False}]}
    race = _race(plan)
    race.adopt((8, 6, 6), compounds=("RS", "RS", "RS"),
               tyres=(None, True, True))
    assert [s["tyres"] for s in race._stints] == [None, True, True]
    assert race.state.next_tyres is True


def test_the_replanner_prices_every_stop_as_a_set():
    from pitcrew.race.replan import Replan

    offer = Replan("recommended", "why", stops=2, stint_laps=(8, 6, 6),
                   stint_compounds=("RS",) * 3, stint_tyres=(None, True, True))
    assert offer.as_plan()["stint_tyres"] == [None, True, True]


def test_the_offer_assess_makes_carries_a_decision_per_stint(monkeypatch):
    """The critic on row 2.6, pass 3 (M4): `assess` could stop putting
    `stint_tyres` on its offer and nothing went red, because the test above
    builds a `Replan` by hand. Driven through `assess` itself here, with
    `recommend` answering a faster two-stop against his one-stop - the only
    road to an offer with stints that needs no hand-tuned race."""
    from pitcrew.race import replan
    from pitcrew.race.replan import RECOMMENDED, assess

    from .test_ptt_and_replan import an_inputs

    two_stop = Plan(stints=[Stint(5, "RM", 20.0, 6), Stint(5, "RM", 20.0, 11),
                            Stint(5, "RM", 20.0, 16)],
                    total_time_s=1000.0, binding_constraint="fuel")
    one_stop = Plan(stints=[Stint(7, "RM", 30.0, 6), Stint(8, "RM", 30.0, 13)],
                    total_time_s=1100.0, binding_constraint="fuel")
    monkeypatch.setattr(replan, "recommend",
                        lambda *a, **k: [two_stop, one_stop])
    offer = assess(laps_done=5, laps_total=20, fuel_l=60.0,
                   planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.4,
                   lap_time_ms=94_000, planned_lap_time_ms=94_000,
                   current_stops=1, inputs=an_inputs())
    assert offer.verdict == RECOMMENDED, offer
    assert offer.stint_laps == (5, 5, 5)
    assert offer.stint_tyres == (None, True, True)


def test_the_brief_says_a_fuel_only_stop_before_the_green():
    """Pass 2, minor: "20 laps, 1 stop, on RS." on the grid, then "No
    tyres." at the box - the one was never said before the other."""
    from pitcrew.race.brief import Instruments, brief

    def said(stops, fuel_only):
        return brief(Instruments(has_plan=True, race_laps=20, stops=stops,
                                 compounds=("RS",), fuel_only_stops=fuel_only))

    assert "No tyres at the stop - fuel only." in said(1, 1)
    assert "No tyres at any stop - fuel only." in said(2, 2)
    assert "Not every stop takes tyres - I'll say which at the box." \
        in said(2, 1)
    assert not any("tyres at" in line or "takes tyres" in line
                   for line in said(1, 0))
    # And a timed race, whose shape line is a different branch (pass 3, M13).
    timed = brief(Instruments(has_plan=True, race_minutes=30.0, stops=1,
                              compounds=("RS",), fuel_only_stops=1,
                              laps_estimate=20))
    assert "No tyres at the stop - fuel only." in timed


def test_a_retired_stop_takes_its_tyres_decision_with_it():
    """Pass 3, MAJOR 1: after "You're fuelled to the flag. No more stops on
    fuel." the radio still answered "Tyres on." and the plan summary
    "Running to the flag, tyres on" - the stop's decision outliving it."""
    from pitcrew.race.calls import STOP_FLIP_LAPS

    # With and without a compound named: unnamed, `nextCompound` is None
    # whether the guard is there or not (pass 4, mutant N1).
    for compound in (None, "RS"):
        plan = {"stints": [
            {"laps": 10, "compound": "RS", "fuel_l": 60.0, "start_lap": 1},
            {"laps": 10, "compound": compound, "fuel_l": 30.0,
             "start_lap": 11, "tyres": True}],
            "binding_constraint": "fuel"}
        race = _race(plan)
        race.state.lap, race.state.laps_total = 8, 20
        race.state.fuel_l, race.state.fuel_per_lap_l = 60.0, 3.0
        race.state.drop_stop_granted = True
        for _ in range(STOP_FLIP_LAPS):
            race.state.note_stop_need()
        snap = race.snapshot()
        assert snap["lapsToStop"] is None
        assert (snap["nextTyres"], snap["nextCompound"]) == (None, None)
        assert answer(BOX_WHAT, snap).text == "No tyre change planned."
        summary = answer(PLAN, snap).text
        assert "tyres on" not in summary and "onto" not in summary, summary
        # While the stop stands, the decision is said.
        standing = _race(plan).snapshot()
        assert standing["nextTyres"] is True
        assert standing["nextCompound"] == compound


def test_a_replan_keeping_the_stop_count_keeps_the_desks_decision():
    """The merge of passes 2 and 3: the same number of stops keeps the desk's
    fuel-only; a changed number takes the re-planner's priced fresh set."""
    race = _race(_plan(False))
    race.adopt((5, 10), tyres=(None, True))
    assert race._stints[1]["tyres"] is False
    race = _race(_plan(False))
    race.adopt((5, 5, 5), tyres=(None, True, True))
    assert [s["tyres"] for s in race._stints[1:]] == [True, True]
    # And a plan that never decided takes the priced answer either way.
    race = _race(_plan(None))
    race.adopt((5, 10), tyres=(None, True))
    assert race._stints[1]["tyres"] is True


def test_the_driver_refusal_and_the_desk_refusal_refuse_the_same_plans():
    """Pass 3, minor: one remedy was appended to every problem, in the desk's
    words. `tyres_refusal` speaks to the driver; it must refuse exactly what
    `stint_tyre_problems` refuses."""
    from pitcrew.strategy.handover import tyres_refusal

    changed = _plan(False)
    changed["stints"][1]["compound"] = "RS"
    first = _plan(True)
    first["stints"][0]["tyres"] = "yes"
    plans = [_plan(None), changed, _plan("false"), first, _plan(True, False),
             _plan(0), _plan(1), _plan(), {"stints": []}, {}]
    for plan in plans:
        assert (tyres_refusal(plan) is None) == (stint_tyre_problems(plan) == []), plan
    assert "fits a set there or keeps RM" in tyres_refusal(changed)
    assert "neither tyres on nor fuel only" in tyres_refusal(first)
    assert all(tyres_refusal(p).endswith("on the Strategy page.")
               for p in plans if tyres_refusal(p))


def test_the_optimisers_plan_says_a_set_goes_on():
    """Bathurst's strategy 30 came from here with no decision at all."""
    plan = Plan(stints=[Stint(10, "RM", 60.0, 1), Stint(10, "RM", 60.0, 11)],
                total_time_s=1800.0, binding_constraint="fuel")
    stints = plan.as_dict()["stints"]
    assert "tyres" not in stints[0] and stints[1]["tyres"] is True
