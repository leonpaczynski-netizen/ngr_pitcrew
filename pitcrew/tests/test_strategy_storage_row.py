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


# ------------------------------------ critic 2 on the storage row

def _write(db, event_id, **extra):
    payload = {"stints": [{"laps": 10, "compound": "RS"},
                          {"laps": 10, "compound": "RS"}],
               "stops": 1, "playbook": [], **extra}
    return call("write_strategy", {"event_id": event_id,
                                   "plan": json.dumps(payload)}, db=db)


def test_write_strategy_does_not_approve_a_plan_for_another_race(seeded):
    """The context check went into one approving door. This one approved on
    `certified` alone, demoted the good plan, and the grid then refused the
    foreign one with nothing left to fall back on."""
    from pitcrew.store.db import Store

    db, event_id = seeded
    good = _write(db, event_id)
    assert good["approved"] is True, good
    foreign = _write(db, event_id, context={
        "car": "Porsche 911 RSR (991) '17", "track": "Suzuka Circuit",
        "layout": "Full", "race_laps": 20, "race_minutes": None})
    assert foreign["written"] is True and foreign["approved"] is False
    assert "built for Suzuka Circuit" in foreign["note"]
    assert "built for Suzuka Circuit" in foreign["builtForAnotherRace"]
    store = Store(db)
    try:
        assert store.get_approved_strategy(event_id)["id"] == good[
            "strategyId"], "the good plan was demoted"
    finally:
        store.close()


@pytest.mark.parametrize("first, words", [
    (2, "stint 1 starts on lap 2, so lap 1 belongs to no stint"),
    (3, "stint 1 starts on lap 3, so laps 1 and 2 belong to no stint"),
    (5, "stint 1 starts on lap 5, so laps 1 to 4 belong to no stint"),
])
def test_the_first_stint_starts_on_lap_one(first, words):
    """A first stint on lap 5 certified; the page said box lap 10 and George
    boxed on 14, on a load sized for 10."""
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = first
    proposed["stints"][1]["start_lap"] = first + 10
    assert words in certify(proposed, inputs()).refusals


@pytest.mark.parametrize("pit_laps, words", [
    ([12], "the plan's pit laps say lap 12 but its stints box on lap 10"),
    (["x"], "the plan's pit laps say lap 'x' but its stints box on lap 10"),
    ([], "the plan's pit laps say no lap but its stints box on lap 10"),
])
def test_the_pit_laps_are_the_laps_the_stints_box_on(pit_laps, words):
    """The Race page reads `pit_laps`; George boxes on the stints. One stop,
    two lap numbers a glance apart, is rule 13."""
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = 1
    proposed["stints"][1]["start_lap"] = 11
    proposed["pit_laps"] = pit_laps
    assert words in certify(proposed, inputs()).refusals


def test_pit_laps_that_agree_certify_including_as_floats():
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = 1
    proposed["stints"][1]["start_lap"] = 11
    for pit_laps in ([10], [10.0]):
        proposed["pit_laps"] = pit_laps
        assert certify(proposed, inputs()).certified, pit_laps


def test_a_bad_start_is_the_only_refusal_not_the_first_of_many():
    """What the other checks would say about a plan whose laps cannot be
    placed is not worth saying; the early return is pinned here."""
    proposed = plan(stint(10, fuel=510.0), stint(10, "RM"))
    proposed["stints"][0]["start_lap"] = 0
    assert certify(proposed, inputs()).refusals == [
        "stint 1 starts on lap 0; laps count from 1"]


def test_an_unrecorded_layout_is_not_called_the_none_layout():
    from pitcrew.race.coordinator import PlanContext

    old = PlanContext(car="RSR", track="Monza", layout=None, race_laps=20)
    here = PlanContext(car="RSR", track="Monza", layout="Full Course",
                       race_laps=20)
    fits, why = old.matches(here)
    assert not fits and "None" not in why
    assert why == ("plan does not record which layout it was built for; "
                   "this is Full Course")
    fits, why = here.matches(old)
    assert not fits and "None" not in why


def test_an_unreadable_approved_row_is_not_told_approval_fills_it_in(raced):
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    broken = dict(row["plan"])
    broken["stints"] = [broken["stints"][0], "x", *broken["stints"][2:]]
    store.update_strategy_plan(row["id"], broken)
    assert controller.start_race() is False
    said = screen.subtitle.text()
    assert said == ("Plan refused: Stint 2 of the plan cannot be read. "
                    "Approve another plan on the Strategy page.")
    assert "fills" not in said


def test_the_race_page_does_not_fall_over_on_an_unreadable_plan(qt_app):  # noqa: F811
    """Found by the test above: every line of `set_plan` called `.get` on a
    stint, so an unreadable row raised on the Race page - from the refresh
    and from `_poll_plan` every tick. It says what is wrong instead, and
    draws none of the stints rather than the ones that survive."""
    from pitcrew.ui.race_screen import RaceScreen

    screen = RaceScreen()
    screen.set_plan({"label": "old", "plan": {
        "stints": [{"laps": 10, "compound": "RS"}, "x"]}})
    assert screen.plan_line.text() == (
        "The approved plan will not arm: stint 2 of the plan cannot be read.")
    assert not screen.orders.isVisibleTo(screen)

    # A figure that is not a number is not known, not a crash.
    screen.set_plan({"label": "typo", "plan": {
        "stints": [{"laps": 10, "compound": "RS", "fuel_l": "sixty"},
                   {"laps": 10, "compound": "RS", "fuel_l": 60.0}]}})
    assert "? L + 60 L" in screen.plan_line.text()


def test_the_race_page_says_in_the_week_that_the_plan_will_not_arm(raced):
    """Strategies 3 and 9 showed as the approved plan with no sign they would
    be refused on the grid."""
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    store.update_strategy_plan(row["id"], _unstamped(row["plan"]))
    controller._refresh_race_options(store.get_event(event_id))
    said = screen.subtitle.text()
    assert said.startswith("The approved plan will not arm: It was approved "
                           "without what it was built for")
    # The same words the grid gives, from the same expression (rule 13).
    assert controller.start_race() is False
    assert screen.subtitle.text() == said.replace(
        "The approved plan will not arm: ", "Plan refused: ")


def test_a_refused_rearm_takes_the_last_races_result_off_the_board(
        raced, monkeypatch):
    """Critic pass 3 on row 1.8: only `stop_race` and `shutdown` closed the
    board, so a re-arm refused before `self.race` was replaced left the last
    race's FLAG and position on the new grid under "Not armed"."""
    controller, _screen, _store, _event_id = raced
    assert controller.start_race() is True
    controller.race.state.finished = True

    class Board:
        hidden = False

        def geometry_text(self):
            return ""

        def hide(self):
            self.hidden = True

    board = Board()
    controller.driver_board = board
    monkeypatch.setattr(controller, "gauge_preflight_ok", lambda _what: False)
    assert controller.start_race() is False
    assert board.hidden is True


def test_approval_records_what_it_stamped_and_its_own_certificate(raced):
    controller, _screen, store, event_id = raced
    reference = store.get_approved_strategy(event_id)["plan"]
    candidate = store.save_strategy(event_id, _unstamped(reference),
                                    label="old", evidence={"certified": False,
                                                           "refusals": ["x"]})
    assert controller.approve_stored_strategy(candidate) is True
    row = next(r for r in store.list_strategies(event_id)
               if r["id"] == candidate)
    evidence = row["evidence"]
    assert evidence["refusals"] == ["x"], "what it was written with is kept"
    stamped = evidence["at_approval"]["stamped"]
    assert len(stamped) == 3, stamped
    assert evidence["at_approval"]["refusals"] == []


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




# ------------------------------------ critic 2, pass 3 on the storage row

@pytest.mark.parametrize("context", [
    {"car": "RSR", "track": "Monza", "layout": "Full", "race_laps": "twenty",
     "race_minutes": None},
    {"car": "RSR", "track": "Monza", "layout": "Full", "race_laps": 0,
     "race_minutes": "50"},
    {"car": "RSR", "track": "Monza", "layout": "Full", "race_laps": 20.5,
     "race_minutes": None},
    {"car": "RSR", "track": "Monza", "layout": "Full", "race_laps": None,
     "race_minutes": None},
])
def test_a_context_that_cannot_be_read_is_refused_by_name(store, event_id,
                                                          context):
    """**The BLOCKER.** `stamp` checked the context's keys and not their
    values, so `"race_laps": "twenty"` stored clean and then `int()` raised
    inside `built_for_another_race` on the Approve button - uncaught, and
    PyQt aborts the process. A null distance read as "built for 0 laps"
    (rule 3). One shape check, `_is_context`, for every door and the grid."""
    from pitcrew.strategy.execution import built_for_another_race

    with pytest.raises(ValueError) as refused:
        stamp(store, event_id, {**A_PLAN_FOR_CONTEXT, "context": context})
    assert "int()" not in str(refused.value)
    assert "race_laps" in str(refused.value) or "race_minutes" in str(
        refused.value)
    # And a row that somehow carries one is a contract gap, never a raise.
    plan = {**A_PLAN_FOR_CONTEXT, "context": context}
    assert contract_gaps(plan)
    assert built_for_another_race(plan, store.get_event(event_id)) is None


A_PLAN_FOR_CONTEXT = {
    "stints": [{"laps": 10, "compound": "RM", "start_lap": 1},
               {"laps": 10, "compound": "RM", "start_lap": 11}],
    "stops": 1}


def test_a_context_typo_never_reaches_the_approve_button_as_a_raise(raced):
    controller, _screen, store, event_id = raced
    plan = dict(store.get_approved_strategy(event_id)["plan"])
    plan["context"] = {**plan["context"], "race_laps": "twenty"}
    candidate = store.save_strategy(event_id, plan, label="typo")
    assert controller.approve_stored_strategy(candidate) is False
    assert "race_laps" in controller.strategy.subtitle.text()


def test_the_mcp_door_refuses_a_context_typo_in_words(seeded):
    db, event_id = seeded
    got = _write(db, event_id, context={
        "car": "Porsche 911 RSR (991) '17",
        "track": "Autodromo Nazionale Monza", "layout": "Full",
        "race_laps": "twenty", "race_minutes": None})
    assert got["written"] is False
    assert "int()" not in got["error"] and "race_laps" in got["error"]


def test_the_in_week_warning_is_taken_down_when_it_stops_being_true(raced):
    """**MAJOR.** It was set when true and never cleared, so after he
    re-approved the plan the page still told him it would not arm."""
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    store.update_strategy_plan(row["id"], _unstamped(row["plan"]))
    controller._refresh_race_options(store.get_event(event_id))
    assert "will not arm" in screen.subtitle.text()
    assert controller.approve_stored_strategy(row["id"]) is True
    assert "will not arm" not in screen.subtitle.text()


def test_the_in_week_warning_names_a_plan_for_another_race(raced):
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    plan = dict(row["plan"])
    plan["context"] = {**plan["context"], "track": "Suzuka Circuit"}
    store.update_strategy_plan(row["id"], plan)
    controller._refresh_race_options(store.get_event(event_id))
    said = screen.subtitle.text()
    assert "built for Suzuka Circuit" in said
    # With what to do about it, as the other two warnings have (pass 5).
    assert said.endswith("Approve a plan built for this race on the "
                         "Strategy page, or correct the event.")


def test_a_foreign_plan_is_certified_and_not_approved_without_contradiction(
        seeded):
    """Minor 6: `certified: True`, "Driveable", and a refusal, in one reply.
    It IS driveable - it is simply for another race - so the refusals stay
    the certificate's and the mismatch is said under its own key."""
    db, event_id = seeded
    _write(db, event_id)
    foreign = _write(db, event_id, context={
        "car": "Porsche 911 RSR (991) '17", "track": "Suzuka Circuit",
        "layout": "Full", "race_laps": 20, "race_minutes": None})
    assert foreign["approved"] is False and foreign["certified"] is True
    assert foreign["refusals"] == []
    assert "Suzuka Circuit" in foreign["builtForAnotherRace"]


def test_the_grids_own_refusal_is_taken_down_after_he_fixes_it(raced):
    """Critic 2, pass 4 (MAJOR): after a failed Start the page carried the
    grid's "Plan refused: It was approved without...", which the take-down
    never matched - pass 3's stale message, reached the likelier way."""
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    store.update_strategy_plan(row["id"], _unstamped(row["plan"]))
    assert controller.start_race() is False
    assert screen.subtitle.text().startswith("Plan refused: It was approved")
    assert controller.approve_stored_strategy(row["id"]) is True
    assert not screen.subtitle.text().startswith("Plan refused")


def test_the_refresh_leaves_somebody_elses_status_alone(raced):
    """The mutant that survived pass 4: a refresh that cleared ANY status."""
    controller, screen, store, event_id = raced
    other = "Not armed - set the OBS projector up and arm again."
    screen.set_status(other, warn=True)
    controller._refresh_race_options(store.get_event(event_id))
    assert screen.subtitle.text() == other


def test_a_certify_refusal_on_the_grid_stays_up_after_a_refresh(
        raced, monkeypatch):
    """Critic 2, pass 5: the surviving mutant widened the take-down to
    anything starting "Plan refused: ". A tank refusal is still true after a
    refresh - the refresh's own check cannot see it - so it must stay."""
    import pitcrew.controller as controller_module

    class Refused:
        certified = False
        warnings = ()

        @staticmethod
        def describe():
            return "Stint 1 needs more fuel than the tank holds."

    controller, screen, store, event_id = raced
    monkeypatch.setattr(controller_module, "build_inputs",
                        lambda *_a, **_k: (object(), None))
    monkeypatch.setattr(controller_module, "certify",
                        lambda *_a, **_k: Refused())
    assert controller.start_race() is False
    said = screen.subtitle.text()
    assert said == "Plan refused: Stint 1 needs more fuel than the tank holds."
    controller._refresh_race_options(store.get_event(event_id))
    assert screen.subtitle.text() == said


def test_no_warning_about_a_plan_he_has_set_aside(raced):
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    store.update_strategy_plan(row["id"], _unstamped(row["plan"]))
    controller._refresh_race_options(store.get_event(event_id))
    assert "will not arm" in screen.subtitle.text()
    # He chooses "No plan": the screen's own slot, then the controller's.
    index = screen.plan_picker.findData(False)
    screen.plan_picker.setCurrentIndex(index)
    screen.plan_picker.activated.emit(index)
    assert screen.use_plan() is False
    assert "will not arm" not in screen.subtitle.text()


@pytest.mark.parametrize("over, words", [
    ({"race_minutes": True}, "race_minutes"),
    ({"race_minutes": float("inf")}, "race_minutes"),
    ({"race_minutes": 0}, "race_minutes"),
    ({"car": None}, "names no car"),
    ({"track": "  "}, "names no track"),
])
def test_a_context_value_that_is_not_one_is_refused(store, event_id, over,
                                                    words):
    context = {"car": "RSR", "track": "Monza", "layout": "Full",
               "race_laps": 20, "race_minutes": None, **over}
    with pytest.raises(ValueError) as refused:
        stamp(store, event_id, {**A_PLAN_FOR_CONTEXT, "context": context})
    assert words in str(refused.value)


def test_an_event_with_no_distance_is_refused_at_approval(store):
    """Critic 2, pass 4: approval stamped a context from an event with no
    distance, the week said "approval fills those in", and the next approval
    refused its own stamp."""
    no_distance = store.create_event(
        name="No distance", track="Monza", layout="Full", car_id=1,
        car_name="RSR", race_type="laps", race_laps=0)
    with pytest.raises(ValueError) as refused:
        stamp(store, no_distance, A_PLAN_FOR_CONTEXT)
    assert "the event has no race length" in str(refused.value)


def test_the_optimisers_approve_refuses_in_words_rather_than_raising(raced):
    """Critic 2, pass 5: `approve_strategy` called `stamp` outside any try,
    and `stamp` now refuses an event it cannot build a context from - from a
    Qt slot, an uncaught ValueError aborts the app."""
    controller, _screen, store, event_id = raced
    store.update_event(event_id, car_name="")
    assert controller.approve_strategy(0) is None
    assert "has no car" in controller.strategy.subtitle.text()


def test_the_week_warning_does_not_overwrite_an_armed_race(raced):
    """Critic 2, pass 5: armed on "No plan", flipping the picker ran the
    refresh and replaced "Armed: no plan - fuel calls only" with a warning
    about the plan that race is not using."""
    controller, screen, store, event_id = raced
    row = store.get_approved_strategy(event_id)
    store.update_strategy_plan(row["id"], _unstamped(row["plan"]))
    no_plan = screen.plan_picker.findData(False)
    screen.plan_picker.setCurrentIndex(no_plan)
    screen.plan_picker.activated.emit(no_plan)
    assert controller.start_race() is True
    armed = screen.subtitle.text()
    with_plan = screen.plan_picker.findData(True)
    screen.plan_picker.setCurrentIndex(with_plan)
    screen.plan_picker.activated.emit(with_plan)
    assert screen.subtitle.text() == armed
    assert "will not arm" not in screen.subtitle.text()


def test_pit_laps_on_a_plan_with_no_start_laps_is_not_a_crash():
    """Minor 5's surviving mutant: the `all(s is not None ...)` guard. A raw
    plan carrying `pit_laps` and no start laps would raise TypeError."""
    proposed = plan(stint(10), stint(10, "RM"))
    proposed["pit_laps"] = [10]
    assert certify(proposed, inputs()).certified
