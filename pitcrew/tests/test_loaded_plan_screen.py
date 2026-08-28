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
from .test_controller import qt_app  # noqa: F401
from pitcrew.ui.strategy_screen import LoadedCard, PlanCard, StrategyScreen


def a_handover() -> Handover:
    return Handover(
        plan={"stints": [{"laps": 15, "compound": "RM", "fuel_l": 92.0,
                          "start_lap": 1},
                         {"laps": 5, "compound": "RM", "fuel_l": 32.0,
                          "start_lap": 16}],
              "stops": 1, "pit_laps": [15], "binding_constraint": "fuel"},
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


def test_it_names_what_george_will_not_decide(qt_app, store, event_id):
    """Anything outside the playbook is George reporting rather than deciding,
    and a driver who has not been told reads the silence as it being handled."""
    screen = StrategyScreen()
    screen.show_loaded([loaded_row(store, event_id)])

    card = screen.findChildren(LoadedCard)[0]
    text = " ".join(w.text() for w in card.findChildren(type(screen.footer_note)))
    assert "report and decide nothing" in text
    assert "rain" in text and "safety car" in text


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

    assert len(screen.findChildren(LoadedCard)) == 1, "the loaded plan vanished"
