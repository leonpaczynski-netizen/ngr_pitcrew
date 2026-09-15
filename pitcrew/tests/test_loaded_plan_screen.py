"""A plan written at the desk, on the screen where the driver chooses.

**It was visible to nobody.** The Strategy screen rendered `recommend()`'s
output and nothing else, and `approve_strategy` took an INDEX into that list -
so a plan the app had not thought of could be stored, certified, and never
chosen. Fuji is the cost: Ludo's one-stop plan with a fifteen-lap opening
stint certified clean, the optimiser would not offer a fifteen-lap stint
against an evidence cap of six, and there was no other way in. He raced three
stops.

The card is deliberately not the optimiser's. It carries no `+N s` delta,
because a loaded plan was never costed against the others and a delta would be
a fabricated comparison. What it carries instead is what only it has: an
author, the certificate the app wrote about it, and the playbook - the bounds
George may move inside, which the driver has to know before the green.
"""
from __future__ import annotations

from pitcrew.strategy.handover import Handover, PlaybookEntry, accept
from ._desk import with_desk_figures
from .test_controller import qt_app  # noqa: F401
from pitcrew.ui.strategy_screen import LoadedCard, PlanCard, StrategyScreen


def a_handover() -> Handover:
    return Handover(
        plan=with_desk_figures(
            {"stints": [{"laps": 15, "compound": "RM", "fuel_l": 92.0,
                         "start_lap": 1},
                        {"laps": 5, "compound": "RM", "fuel_l": 32.0,
                         "start_lap": 16, "tyres": True}],
             "stops": 1, "pit_laps": [15], "binding_constraint": "fuel"}),
        playbook=[PlaybookEntry(trigger="fuel_short", action="short_shift",
                                when="more than 0.5 laps short to the flag",
                                until="the deficit clears")],
        assumptions=["RS wear read off the HUD via OBS"])


def loaded_row(store, event_id) -> dict:
    strategy_id, _ = accept(store, event_id, a_handover(),
                            label="Ludo - one stop")
    assert strategy_id is not None
    return next(r for r in store.list_strategies(event_id)
                if r["id"] == strategy_id)


def test_a_loaded_plan_appears_on_the_screen(qt_app, store, event_id):
    screen = StrategyScreen()
    screen.show_loaded([loaded_row(store, event_id)])

    cards = screen.findChildren(LoadedCard)
    assert len(cards) == 1
    assert "Ludo" in cards[0].accessibleName()


def test_it_carries_no_delta_because_it_was_never_ranked(qt_app, store,
                                                         event_id):
    """`+1.4 s` means "against the fastest plan the optimiser found". A plan
    it never costed has no place in that comparison, and printing one would be
    a number the app made up."""
    screen = StrategyScreen()
    screen.show_loaded([loaded_row(store, event_id)])

    text = " ".join(w.text() for w in
                    screen.findChildren(LoadedCard)[0].findChildren(
                        type(screen.footer_note)))
    assert "+" not in text, text


def test_it_separates_what_he_cannot_see_from_what_he_has_no_rule_for(
        qt_app, store, event_id):
    """**Two different things, and the card said the wrong one about both.**

    It read "He will report and decide nothing on: fuel long, rain, safety
    car." Half of that is false in the direction that matters:
    `stop_still_needed` and `stay_out_call` decide fuel and a missed stop with
    or without a playbook, so a driver told George would stay out of it was
    told the opposite of the truth on the screen where he reads the contract.

    The other half is true and stronger than it was put: GT7 broadcasts no
    weather and no flag state in any packet format, so rain and the safety car
    are not "unhandled", they are invisible - and the only thing that can fix
    that is the driver saying so.
    """
    screen = StrategyScreen()
    screen.show_loaded([loaded_row(store, event_id)])

    card = screen.findChildren(LoadedCard)[0]
    text = " ".join(w.text() for w in card.findChildren(type(screen.footer_note)))
    assert "cannot see rain at all" in text, text
    assert "safety car" not in text, "retired from TRIGGERS on 7 Sep 2026"
    assert "tell him" in text
    assert "No rule from the desk" in text
    assert "falls back to his own" in text
    assert "decide nothing" not in text, "the claim that was false"


def test_choosing_a_loaded_plan_clears_the_app_s_own(qt_app, store, event_id):
    """Two lists on one plate, one plan approved. Two cards reading as chosen
    is a button acting on whichever branch happens to win."""
    from pitcrew.strategy.model import Plan, Stint

    screen = StrategyScreen()
    plan = Plan(stints=[Stint(10, "RM", 60.0, 1), Stint(10, "RM", 60.0, 11)],
                total_time_s=1800.0, binding_constraint="fuel")
    screen.show_plans([plan], [])
    screen.show_loaded([loaded_row(store, event_id)])

    own = screen.findChildren(PlanCard)[0]
    loaded = screen.findChildren(LoadedCard)[0]
    assert own._chosen is True and loaded._chosen is False

    loaded.selected.emit(loaded.strategy_id)
    assert loaded._chosen is True, "the loaded card is not shown as chosen"
    assert own._chosen is False, "both cards read as chosen"


def test_approving_a_loaded_plan_sends_its_id_not_an_index(qt_app, store,
                                                           event_id):
    """**Two different kinds of number on one wire is how a plan gets approved
    by ordinal against a list it was never in.** `approve_requested` carries
    an index into the optimiser's output; this carries a stored row's id."""
    screen = StrategyScreen()
    row = loaded_row(store, event_id)
    screen.show_loaded([row])
    sent: list[int] = []
    screen.approve_loaded_requested.connect(sent.append)

    screen.findChildren(LoadedCard)[0].selected.emit(row["id"])
    screen.approve_button.click()

    assert sent == [row["id"]]


def test_rebuilding_the_app_s_plans_does_not_drop_the_loaded_one(qt_app,
                                                                store,
                                                                event_id):
    """`_clear` takes every item out of the plan layout, and the loaded cards
    live in a sub-layout of it. Dropping that leaves them parented to nothing
    and they vanish on the next build - which is every time he presses Build."""
    from pitcrew.strategy.model import Plan, Stint

    screen = StrategyScreen()
    screen.show_loaded([loaded_row(store, event_id)])
    plan = Plan(stints=[Stint(20, "RM", 100.0, 1)],
                total_time_s=1800.0, binding_constraint="fuel")

    screen.show_plans([plan], [])

    # **Layout membership, not widget parentage.** `findChildren` walks the
    # WIDGET tree, and an orphaned layout leaves its cards parented to the
    # holder - so the card is still "found" while it has vanished from the
    # layout and off the screen. The critic built that mutant and this
    # assertion was the one that could not fail.
    held = [screen.plan_layout.itemAt(i).layout()
            for i in range(screen.plan_layout.count())]
    assert screen.loaded_layout in held, (
        "the loaded sub-layout was taken out of the plan layout and not put "
        "back - its cards are orphaned and off the screen, while "
        "findChildren still finds them parented to the holder")
    assert len(screen.findChildren(LoadedCard)) == 1, "the loaded plan vanished"


def test_clearing_the_loaded_list_disarms_the_selection(qt_app, store,
                                                        event_id):
    """It survived the cards: layout empty, nothing rendering as chosen,
    Approve still enabled, and pressing it emitting the id of a card no longer
    on screen. Invisible and live at once is the worst of both."""
    screen = StrategyScreen()
    row = loaded_row(store, event_id)
    screen.show_loaded([row])
    screen.findChildren(LoadedCard)[0].selected.emit(row["id"])
    assert screen._chosen_loaded == row["id"]

    screen.show_loaded([])

    assert screen._chosen_loaded is None
    assert not screen.findChildren(LoadedCard)
    sent: list[int] = []
    screen.approve_loaded_requested.connect(sent.append)
    screen._on_approve()
    assert sent == [], "approved a plan that is not on the screen"


def test_picking_an_app_plan_after_a_loaded_one_moves_the_selection(
        qt_app, store, event_id):
    """The direction nothing covered. Clicking Ludo's card then an
    optimiser's left Ludo's lit and Approve still approving Ludo's."""
    from pitcrew.strategy.model import Plan, Stint

    screen = StrategyScreen()
    plan = Plan(stints=[Stint(20, "RM", 100.0, 1)], total_time_s=1800.0,
                binding_constraint="fuel")
    screen.show_plans([plan], [])
    row = loaded_row(store, event_id)
    screen.show_loaded([row])

    loaded = screen.findChildren(LoadedCard)[0]
    loaded.selected.emit(row["id"])
    own = screen.findChildren(PlanCard)[0]
    own.selected.emit(own.index)

    assert own._chosen is True and loaded._chosen is False
    sent: list[int] = []
    screen.approve_requested.connect(sent.append)
    screen._on_approve()
    assert sent == [own.index]


def test_a_loaded_plan_still_exports_its_strategy_section(store, event_id):
    """**The post-race audit vanished without a word.** `_strategy_section`
    reads an `export` block that only `Plan.as_export` produces, and a
    handover never goes through it - so a race run to a loaded plan exported
    with no plan, no assumptions, no `callsMade` and no outcome, and
    `validate` returned no problems. CLAUDE.md 5.5 requires the calls and the
    assumptions behind them."""
    from pitcrew.export.build import _strategy_section

    strategy_id, _ = accept(store, event_id, a_handover(),
                            label="Ludo - one stop")
    store.approve_strategy(strategy_id)

    section = _strategy_section(store, event_id)

    assert section is not None, "the whole strategy section vanished"
    assert section["plan"]["stintLaps"] == [15, 5]
    assert section["plan"]["compounds"] == ["RM", "RM"]
    assert section["plan"]["pitLap"] == 15
    assert section["bindingConstraint"] == "fuel"
