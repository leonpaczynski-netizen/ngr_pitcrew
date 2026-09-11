"""The strategy-storage row, carried out of row 1.7 (plan §9a, 11 Sep 2026).

Row 1.7's passes 15-19 produced seventeen findings and not one was in its
deliverable: they were all in the layer between a plan arriving and a plan
being armed. This file holds that layer to what was carried out of the row:

* **a stored row is stamped at the door it walks through to the grid**, and a
  row approved before that is refused on the grid rather than armed blind -
  strategy 9 (Spa, approved) carried neither `context` nor `expects`, so
  `arm(None, actual)` returned True at any circuit;
* **a stint that cannot be read keeps its place** and is refused by position,
  where `_with_start_laps` dropped it and re-numbered the laps after it;
* **the MCP door stores a plan with an unreadable count** and `certify` says
  what is wrong with it, where it used to return `int()`'s own message;
* **each start-lap refusal names the constraint it broke** (rule 12), where
  one sentence covered three;
* and `Handover.validate` answers a reserved key by whoever owns it.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.strategy.certify import certify
from pitcrew.strategy.execution import _with_start_laps, contract_gaps, stamp
from pitcrew.strategy.handover import Handover, from_dict

from .test_certify import inputs, plan, stint
from .test_controller import qt_app  # noqa: F401
from .test_mcp_server import call, seeded  # noqa: F401
from .test_race_wiring import raced, voice  # noqa: F401


def _unstamped(stored: dict) -> dict:
    """A stored plan as it was written before either door stamped."""
    bare = {k: v for k, v in stored.items() if k not in ("context", "expects")}
    bare["stints"] = [{k: v for k, v in s.items() if k != "start_lap"}
                      for s in stored["stints"]]
    return bare


# -------------------------------------------------- the door to the grid

def test_a_candidate_without_its_contract_is_stamped_when_approved(raced):
    controller, screen, store, event_id = raced
    reference = store.get_approved_strategy(event_id)["plan"]
    candidate = store.save_strategy(event_id, _unstamped(reference),
                                    label="written before stamping")

    assert controller.approve_stored_strategy(candidate) is True
    row = store.get_approved_strategy(event_id)
    assert row["id"] == candidate
    # **The row that reaches the grid is the row that was certified.**
    assert contract_gaps(row["plan"]) == []
    assert ([s["start_lap"] for s in row["plan"]["stints"]]
            == [s["start_lap"] for s in reference["stints"]])
    assert row["plan"]["context"]["track"] == reference["context"]["track"]
    assert controller.start_race() is True


def test_a_row_approved_before_stamping_is_refused_on_the_grid(raced):
    """Strategy 9's shape. Not stamped at the grid: a context taken off the
    event there is the event checked against itself."""
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    bare = {k: v for k, v in row["plan"].items()
            if k not in ("context", "expects")}
    store.update_strategy_plan(row["id"], bare)

    assert controller.start_race() is False
    assert controller.race is None
    said = screen.subtitle.text()
    # **Both gaps named, not the first** (rule 12): they are two different
    # things to have been told.
    assert "what it was built for, so it would arm at any circuit" in said
    assert "what it expects to execute" in said
    assert "start" not in said, "its start laps were there; only two gaps"
    assert "Approve a plan on the Strategy page" in said


def test_approving_again_is_the_way_back_to_the_grid(raced):
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    store.update_strategy_plan(row["id"], _unstamped(row["plan"]))
    assert controller.start_race() is False

    assert controller.approve_stored_strategy(row["id"]) is True
    assert contract_gaps(store.get_approved_strategy(event_id)["plan"]) == []
    assert controller.start_race() is True


def test_a_candidate_built_for_another_race_is_not_approved(raced):
    """`arm` would refuse it anyway - but only on the grid, after the Race
    screen had spent the week saying "approved" over it."""
    controller, _screen, store, event_id = raced
    before = store.get_approved_strategy(event_id)["id"]
    elsewhere = dict(store.get_approved_strategy(event_id)["plan"])
    elsewhere["context"] = {**elsewhere["context"], "track": "Suzuka Circuit"}
    candidate = store.save_strategy(event_id, elsewhere, label="for Suzuka")

    assert controller.approve_stored_strategy(candidate) is False
    assert "built for Suzuka Circuit" in controller.strategy.subtitle.text()
    assert store.get_approved_strategy(event_id)["id"] == before


def test_a_contract_that_cannot_be_read_is_not_approved(raced):
    controller, _screen, store, event_id = raced
    before = store.get_approved_strategy(event_id)["id"]
    broken = dict(store.get_approved_strategy(event_id)["plan"])
    broken["context"] = {"circuit": "Monza"}
    candidate = store.save_strategy(event_id, broken, label="typo")

    assert controller.approve_stored_strategy(candidate) is False
    assert "does not name car, track, race_laps" in (
        controller.strategy.subtitle.text())
    assert store.get_approved_strategy(event_id)["id"] == before


def test_a_stored_row_that_is_not_a_plan_is_refused_in_words(raced):
    """`stamp` does `dict(plan)`, and on a list that raises a ValueError whose
    text is about "dictionary update sequence" - which is what the Strategy
    page would have said."""
    controller, _screen, store, event_id = raced
    before = store.get_approved_strategy(event_id)["id"]
    candidate = store.save_strategy(event_id, ["not", "a", "plan"],
                                    label="corrupt")
    assert controller.approve_stored_strategy(candidate) is False
    said = controller.strategy.subtitle.text()
    assert said == "Not approved. The stored plan cannot be read."
    assert store.get_approved_strategy(event_id)["id"] == before


def test_every_gap_in_the_contract_is_named():
    bare = {"stints": [{"laps": 10}, {"laps": 10}]}
    gaps = contract_gaps(bare)
    assert len(gaps) == 3, gaps
    assert contract_gaps("not a plan") == ["a plan the app can read"]


def test_a_stamped_plan_has_no_gaps(store, event_id):
    assert contract_gaps(stamp(store, event_id, plan(stint(10), stint(10)))) \
        == []


# ------------------------------------------- stints that cannot be read

def test_a_stint_that_cannot_be_read_keeps_its_place():
    """It used to vanish, and the laps after it were re-numbered as though
    the plan had one stint fewer."""
    got = _with_start_laps([{"laps": 10}, "garbage", {"laps": 10}])
    assert got[0]["start_lap"] == 1
    assert got[1] == "garbage"
    assert "start_lap" not in got[2], "past it the running lap is not known"

    refused = certify({"stints": got}, inputs())
    assert refused.refusals == ["stint 2 is 'garbage', not a stint"]


def test_an_unreadable_length_stops_the_count_without_raising():
    got = _with_start_laps([{"laps": "ten"}, {"laps": 10}])
    assert got[0] == {"laps": "ten", "start_lap": 1}
    assert "start_lap" not in got[1]
    assert certify({"stints": got}, inputs()).refusals == [
        "every stint needs a positive whole number of laps"]


def test_a_start_of_zero_is_left_for_the_gate_to_refuse():
    """`if row.get("start_lap")` rewrote a falsy start to the running lap, so
    `certify`'s `minimum=1` was nearly dead."""
    got = _with_start_laps([{"laps": 10, "start_lap": 0}, {"laps": 10}])
    assert got[0]["start_lap"] == 0
    assert "start_lap" not in got[1]


def test_an_authors_own_start_is_kept_and_the_rest_follow_it():
    got = _with_start_laps([{"laps": 10, "start_lap": 3}, {"laps": 10}])
    assert [s["start_lap"] for s in got] == [3, 13]


def test_a_plan_that_is_not_a_list_of_stints_is_left_for_the_gate():
    assert _with_start_laps(None) is None
    assert _with_start_laps({"laps": 10}) == {"laps": 10}


def test_the_mcp_door_stores_an_unreadable_count_and_says_why(seeded):
    db, event_id = seeded
    got = call("propose_strategy",
               {"event_id": event_id,
                "plan": json.dumps({"stints": [
                    {"laps": "ten", "compound": "RS"},
                    {"laps": 10, "compound": "RS"}]})},
               db=db)
    assert got["saved"] is True, got
    assert "int()" not in json.dumps(got)
    assert got["certified"] is False
    assert got["refusals"] == [
        "every stint needs a positive whole number of laps"]


def test_the_mcp_door_keeps_a_garbage_stint_where_it_was(seeded):
    from pitcrew.store.db import Store

    db, event_id = seeded
    got = call("propose_strategy",
               {"event_id": event_id,
                "plan": json.dumps({"stints": [
                    {"laps": 10, "compound": "RS"}, "x",
                    {"laps": 10, "compound": "RS"}]})},
               db=db)
    assert got["saved"] is True and got["certified"] is False, got
    assert got["refusals"] == ["stint 2 is 'x', not a stint"]
    store = Store(db)
    try:
        row = next(r for r in store.list_strategies(event_id)
                   if r["id"] == got["strategyId"])
    finally:
        store.close()
    assert row["plan"]["stints"][1] == "x"
    assert len(row["plan"]["stints"]) == 3


# ------------------------------------------------- the start-lap refusals

@pytest.mark.parametrize("value, words", [
    (1.5, "stint 1 starts on lap 1.5, which is not a whole lap"),
    (float("nan"), "stint 1 starts on lap nan, which is not a whole lap"),
    (0, "stint 1 starts on lap 0; laps count from 1"),
    (-3, "stint 1 starts on lap -3; laps count from 1"),
    (200_000, "stint 1 starts on lap 200000, past any race distance"),
    ("one", "stint 1's start lap is 'one', which is not a lap number"),
    (True, "stint 1's start lap is True, which is not a lap number"),
])
def test_each_start_lap_refusal_names_the_constraint_it_broke(value, words):
    """Rule 12. "Needs a whole one" told an author fixing a `0` to make it
    whole."""
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = value
    assert certify(proposed, inputs()).refusals == [words]


def test_every_bad_start_is_named_not_the_first():
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = 0
    proposed["stints"][1]["start_lap"] = 10.5
    assert len(certify(proposed, inputs()).refusals) == 2


@pytest.mark.parametrize("second, words", [
    (8, "stint 2 starts on lap 8, inside stint 1, which runs to lap 10"),
    (10, "stint 2 starts on lap 10, inside stint 1, which runs to lap 10"),
    (12, "stint 2 starts on lap 12 but stint 1 ends on lap 10, so lap 11 "
         "belongs to no stint"),
    (13, "stint 2 starts on lap 13 but stint 1 ends on lap 10, so laps 11 "
         "and 12 belong to no stint"),
    (15, "stint 2 starts on lap 15 but stint 1 ends on lap 10, so laps 11 "
         "to 14 belong to no stint"),
])
def test_starts_that_do_not_chain_are_refused(second, words):
    """Two stints that overlap share a box lap - the nine-box-calls defect -
    and two with a gap leave laps that belong to no stint."""
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = 1
    proposed["stints"][1]["start_lap"] = second
    assert words in certify(proposed, inputs()).refusals


def test_starts_that_chain_certify():
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = 1
    proposed["stints"][1]["start_lap"] = 11
    assert certify(proposed, inputs()).certified


def test_a_plan_that_is_not_a_dict_is_refused_not_raised():
    got = certify(["a", "list"], inputs())
    assert got.refusals == ["the plan is ['a', 'list'], not a plan"]


# --------------------------------------- reserved keys, answered by owner

@pytest.mark.parametrize("key, words", [
    ("export", "the app builds that section itself"),
    ("unhandled", "the app works that out itself"),
    ("certificate", "the app works that out itself"),
    ("playbook", "it is the handover's - put it beside the plan"),
    ("author", "it is the handover's - put it beside the plan"),
    ("handover", "it is the handover's - put it beside the plan"),
])
def test_a_reserved_key_inside_the_plan_is_answered_by_its_owner(key, words):
    """"Rename it" was the answer for all five, and renaming a `playbook`
    strips George's bounds without a word."""
    problems = Handover(plan={"stints": [{"laps": 10}], key: {}}).validate()
    mine = [p for p in problems if repr(key) in p]
    assert len(mine) == 1 and words in mine[0], problems
    assert not any("rename" in p for p in problems)


def test_the_desks_own_export_is_refused_by_name_on_the_flat_shape():
    """The branch `from_dict` keeps `export` on the plan for: nothing reads
    it back, so it would otherwise vanish with no message."""
    handover = from_dict({"stints": [{"laps": 10}], "export": {"stops": 1}})
    assert any("'export'" in p and "the app builds that section itself" in p
               for p in handover.validate())
