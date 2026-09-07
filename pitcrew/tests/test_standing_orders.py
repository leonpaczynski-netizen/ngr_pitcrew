"""The contract, on the page the driver is sitting on when the lights go out.

**It was a screen away.** The playbook, the certificate and what George cannot
see lived on the Strategy page's `LoadedCard` - and `refresh_plan`, which
rebuilds that card, is wired to the RACE screen's `shown` signal. So arriving
on the race page refreshed a contract rendered somewhere he was not looking,
on the one evening he has a helmet in his hands (row 1.7, finding S12).

The words moved to `strategy.handover.standing_orders` and the ink to
`ui.widgets.render_standing_orders`, so both screens say one thing rather than
two - `CLAUDE.md` §1a's rule applied to the sentence that says what the
engineer may do without asking.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from pitcrew.strategy.handover import (CANNOT_SEE, DECLARED, DERIVED, GAP,
                                       Handover, PlaybookEntry, TRIGGERS,
                                       standing_orders)
from pitcrew.ui.race_screen import RaceScreen
from pitcrew.ui.strategy_screen import LoadedCard, StrategyScreen
from pitcrew.ui.widgets import render_standing_orders
from .test_controller import qt_app  # noqa: F401


def a_plan(playbook=(), assumptions=(), certificate=None) -> dict:
    """A stored plan row's `plan_json`, the shape both screens are handed."""
    handover = Handover(
        # Two stints for one stop. `_stops_planned` reads `stints`, because
        # `len(stints) - 1` is `Plan.stops`' own definition and the thing the
        # coordinator arms from - and this fixture used to say one stop with
        # one stint, which is a no-stop plan wearing a `stops` key.
        plan={"stints": [{"laps": 15, "compound": "RM", "start_lap": 1},
                         {"laps": 5, "compound": "RM", "start_lap": 16}],
              "stops": 1, "pit_laps": [15], "binding_constraint": "fuel"},
        playbook=list(playbook),
        assumptions=list(assumptions))
    stored = handover.as_stored(handover.plan)
    if certificate is not None:
        stored["handover"]["certificate"] = certificate
    return stored


def lines(plan) -> str:
    return " | ".join(order.text for order in standing_orders(plan))


# --------------------------------------------------------------- the words


def test_no_plan_says_nothing_at_all():
    """**No plan and no handover are different, and this said the same about
    both.** With `{}`, `playbook_of` returns nothing, every trigger is
    unhandled, and the function happily built the whole contract - so a driver
    with no plan approved would have read "No rule from the desk on fuel
    short, fuel long, ..." as if a desk had considered his race and declined.
    """
    assert standing_orders({}) == []
    assert standing_orders(None) == []


def test_a_plan_with_no_handover_still_says_george_has_no_rules():
    """The other side of the same line. A plan IS approved, nobody wrote a
    playbook for it, and that is the most consequential thing on the grid -
    seven of the ten approved plans on file are in exactly this state."""
    orders = standing_orders({"stints": [{"laps": 10}]})
    text = " | ".join(o.text for o in orders)
    assert "No rule from the desk on" in text
    for trigger in TRIGGERS:
        if trigger not in CANNOT_SEE:
            assert trigger.replace("_", " ") in text, trigger


def test_a_rule_for_something_he_cannot_see_is_not_a_standing_order():
    """**Found rendering the real RBR Short plan (30 Aug).** It carries a
    `rain` entry, so `rain` counted as covered, so the "he cannot see rain"
    line was suppressed - and "rain - report only when the surface reads wet"
    appeared under *George may, on his own*. Backwards: the card went quiet
    exactly where a rule the driver believes is armed cannot fire.
    """
    plan = a_plan(playbook=[
        PlaybookEntry(trigger="rain", action="report_only",
                      when="the surface reads wet", until="he acknowledges")])
    text = lines(plan)

    assert "report only when the surface reads wet" not in text, text
    assert "he cannot see" in text.lower()
    assert "never fire" in text
    assert "Tell him." in text


def test_a_rule_for_a_retired_trigger_can_never_fire_either():
    """`safety_car` left `TRIGGERS` on 7 Sep 2026 and the plan on file
    predates it. `PlaybookEntry.validate` refuses an unknown trigger when a
    handover is AUTHORED; nothing revalidates a stored one on its way to a
    screen, so it rendered as an ordinary standing order."""
    plan = a_plan()
    plan["handover"]["playbook"].append(
        {"trigger": "safety_car", "action": "offer_stay_out",
         "when": "the field is neutralised", "until": "the restart"})
    text = lines(plan)

    assert "offer stay out when the field is neutralised" not in text, text
    assert "safety car" in text
    assert "never fire" in text


def test_a_dead_rule_does_not_fill_the_gap_it_names():
    """A rule that cannot fire must not stop the app saying there is no rule.
    It is the same defect as the one above, read from the other end."""
    plan = a_plan(playbook=[
        PlaybookEntry(trigger="fuel_short", action="short_shift",
                      when="0.5 laps short", until="it clears")])
    plan["handover"]["playbook"].append(
        {"trigger": "safety_car", "action": "offer_stay_out",
         "when": "neutralised", "until": "the restart"})

    text = lines(plan)
    assert "fuel short - short shift" in text
    assert "No rule from the desk on" in text
    assert "stop missed" in text


def test_blindness_is_named_even_with_no_rule_for_it():
    plan = a_plan(playbook=[
        PlaybookEntry(trigger="fuel_short", action="short_shift",
                      when="0.5 laps short", until="it clears")])
    text = lines(plan)
    assert "cannot see rain at all" in text
    assert "never fire" not in text, "there is no rule for it to be about"


def test_the_assumptions_are_rendered_at_all():
    """Six of them are stored against the Daytona plan and no screen has ever
    shown one, so a plan whose stint length rests on a wear rate nobody
    measured looked exactly like one that did not."""
    plan = a_plan(assumptions=["RS wear read off the HUD via OBS",
                               "pit loss 20.0 s, declared, never measured"])
    orders = standing_orders(plan)
    text = " | ".join(o.text for o in orders)
    assert "Resting on" in text
    assert "RS wear read off the HUD via OBS" in text
    assert "pit loss 20.0 s, declared, never measured" in text
    # A human wrote them, so they are set as a human's word.
    resting = [o for o in orders if o.text.startswith("RS wear")]
    assert resting and resting[0].register == DECLARED


def test_an_unchecked_certificate_gap_is_named_not_dropped():
    plan = a_plan(certificate={"warnings": ["the stint exceeds the longest run"],
                               "unchecked": ["the lap count"]})
    orders = standing_orders(plan)
    by_text = {o.text: o for o in orders}
    assert by_text["the stint exceeds the longest run"].register == DERIVED
    assert by_text["Not checked: the lap count"].register == GAP


# --------------------------------------------------------------- the screens


def test_the_race_page_shows_the_orders_when_a_plan_is_approved(qt_app):
    screen = RaceScreen()
    screen.set_plan({"label": "Ludo - one stop",
                     "plan": a_plan(assumptions=["wear off the HUD"])})

    text = " | ".join(
        screen.orders_layout.itemAt(i).widget().text()
        for i in range(screen.orders_layout.count()))
    assert screen.orders.isVisibleTo(screen)
    assert "Standing orders" in text
    assert "wear off the HUD" in text
    assert "No rule from the desk on" in text


def test_the_race_page_hides_the_block_with_no_plan(qt_app):
    """A heading over nothing reads as the app having lost something."""
    screen = RaceScreen()
    screen.set_plan({"label": "Ludo", "plan": a_plan()})
    assert screen.orders_layout.count()

    screen.set_plan(None)
    assert screen.orders_layout.count() == 0
    assert not screen.orders.isVisibleTo(screen)


def test_the_orders_cost_the_race_page_no_height(qt_app):
    """The page has eight pixels of headroom against the 501 the smallest
    display gives, which is why the block lives INSIDE the log's scroll area
    rather than beside it.

    **The height assertion alone has no teeth** - inside a scroller it cannot
    fail, whatever the content - so the structural fact is asserted too. A
    later hand moving the block out of the scroller is the failure this is
    for, and only the second assertion would catch it.
    """
    from PyQt6.QtWidgets import QScrollArea

    screen = RaceScreen()
    bare = screen.minimumSizeHint().height()
    screen.set_plan({"label": "Ludo", "plan": a_plan(
        assumptions=["a long line " * 12] * 40)})
    assert screen.orders_layout.count() > 40
    assert screen.minimumSizeHint().height() == bare
    assert screen.minimumSizeHint().height() <= 501

    parent = screen.orders.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    assert parent is not None, (
        "the orders must sit inside the log's scroll area; outside it they "
        "take the page over the 501 the smallest display gives")


def test_both_screens_say_the_same_words(qt_app, store, event_id):
    """One contract, one source. Two renderings are two contracts, and this
    is the sentence where that matters most."""
    from .test_loaded_plan_screen import loaded_row

    row = loaded_row(store, event_id)

    strategy = StrategyScreen()
    strategy.show_loaded([row])
    card = strategy.findChildren(LoadedCard)[0]
    on_card = [w.text() for w in card.findChildren(QWidget)
               if hasattr(w, "text")]

    race = RaceScreen()
    race.set_plan(row)
    on_race = [race.orders_layout.itemAt(i).widget().text()
               for i in range(race.orders_layout.count())]

    # The race page adds the author heading; the card carries it in its own
    # header beside the label, so that one line is the only difference.
    assert on_race[0].startswith("Standing orders")
    for line in on_race[1:]:
        assert line in on_card, line


def test_the_race_page_names_the_author(qt_app):
    screen = RaceScreen()
    screen.set_plan({"label": "x", "plan": a_plan()})
    assert screen.orders_layout.itemAt(0).widget().text() == \
        "Standing orders - LUDO"


def test_render_is_a_no_op_with_nothing_to_say(qt_app):
    holder = QWidget()
    layout = QVBoxLayout(holder)
    assert render_standing_orders(layout, None) == 0
    assert layout.count() == 0


# ------------------------------------------------------------------ the rail


def test_strategy_is_not_a_race_day_screen():
    """The Race page carries the contract now, so the rail must stop offering
    a page to go and read at the moment he should be on the one he starts
    from."""
    from pitcrew.app import NAV_GROUPS, SCREENS

    race_day = next(names for heading, names in NAV_GROUPS
                    if heading == "Race day")
    assert race_day == ("Race",)
    assert any(heading == "Plan" and names == ("Strategy",)
               for heading, names in NAV_GROUPS)
    # **The flattened order is the stack's order and `LATE_SCREENS`' keys.**
    # Splitting the group rather than moving the name is what keeps it.
    assert SCREENS == ("Event", "Car", "Practice", "Strategy", "Race",
                       "Reference", "Settings")


# ------------------------------------------------- what the critic found


def test_arming_the_race_does_not_delete_the_contract(qt_app):
    """**`clear_log` deleted the standing orders, and then the app aborted.**

    It takes every widget out of `log_layout` and `deleteLater`s anything
    that is not `log_empty`; the orders live in that layout now, and
    `controller.start_race` calls it. Between the arm and the deferred delete
    the block was out of the layout but still a child of the log holding its
    last geometry, so it drew under the incoming calls - and once the loop
    ran the delete, every later `set_plan` raised `RuntimeError: wrapped
    C/C++ object of type QVBoxLayout has been deleted`, which PyQt turns into
    an abort. Reachable by returning to the Race page after the race, by
    `_poll_plan`, and by approving a plan mid-race.

    They also *should* survive the arm: the contract is what he reads on the
    grid, and the green flag is not the moment to take it away.
    """
    screen = RaceScreen()
    screen.set_plan({"label": "Ludo", "plan": a_plan(
        assumptions=["wear off the HUD"])})
    assert screen.orders_layout.count()

    screen.clear_log()
    # `processEvents` does NOT run a DeferredDelete; measured, the crash only
    # appears once this does, which is why an ordinary test would have seen
    # the block vanish and the app survive.
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication

    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert screen.log_layout.indexOf(screen.orders) >= 0, (
        "out of the layout but still a child: it draws under the calls")
    assert screen.orders.isVisibleTo(screen)
    # The one that aborted the process.
    screen.set_plan({"label": "Ludo", "plan": a_plan()})
    assert screen.orders_layout.count()


def test_the_tyre_short_sentence_is_true_of_the_stint_it_is_about():
    """**The gate has a condition and the sentence stated it flat.**

    `add_stop` is set on the wear cliff only when `stint_ends_on_lap is
    None` - the last stint. With a stop ahead the same reading brings it
    forward, which is timing, and timing is free. So the driver hears "Box
    this lap." on lap 8 of stint 1 at Daytona, the instruction the contract
    had just told him he would not get. Asserted against the CALL, not
    against the words, because the words were the thing that was wrong.
    """
    from pitcrew.race.calls import _wear
    from .test_playbook_bounds import _at_the_cliff, a_plan as a_race_plan

    with_a_stop = _at_the_cliff(a_race_plan(), stop_planned=True)
    assert _wear(with_a_stop.state).structural_action is None
    assert with_a_stop._within_the_playbook(
        _wear(with_a_stop.state)).call == "Box this lap."

    last_stint = _at_the_cliff(a_race_plan(), stop_planned=False)
    withheld = last_stint._within_the_playbook(_wear(last_stint.state))
    assert withheld.call == "Tyres past the stint limit."

    said = lines(a_plan())
    assert "may bring a planned stop forward" in said, said
    assert "not add one after the last" in said
    # The contract quotes the call, so the two cannot drift apart.
    assert withheld.call in said

    # **And the condition is evaluated, not narrated.** A plan with no stop
    # has none to bring forward, and the gate bites from the green.
    no_stop = lines(a_plan())
    assert "bring a planned stop forward" in no_stop
    none_planned = lines({"stints": [{"laps": 20}], "stops": 0,
                          "handover": {"playbook": []}})
    assert "No stop is planned, so he cannot bring one forward" in none_planned
    assert "bring a planned stop forward" not in none_planned, none_planned
    # And no line about dropping a stop that does not exist.
    assert "cannot drop a stop" not in none_planned


def test_he_is_told_what_he_cannot_do_without_a_rule(qt_app):
    """**"George falls back to his own" was false for the two gated pairs.**

    `RaceCoordinator._may` refuses a STRUCTURAL action with no playbook entry
    - "the one place absence now means no rather than yes". Two pairs reach
    it: `tyre_short -> add_stop` (the wear cliff with no stop planned) and
    `fuel_long -> drop_stop`. `tyre_short` joined TRIGGERS on 7 Sep, so no
    plan on file grants it, and the approved plan told the driver George
    would use his judgement on the one decision he is barred from.
    """
    text = lines(a_plan())
    assert "not add one after the last" in text, text
    assert "On fuel long he cannot drop a stop without a rule from the desk" \
        in text
    # And never both sentences about one trigger.
    assert "No rule from the desk on tyre short" not in text
    assert "tyre short - George falls back" not in text


def test_a_granted_structural_action_is_not_reported_as_withheld():
    """Both halves in one run, so the assertion is a difference rather than
    the absence of a string."""
    granted = a_plan(playbook=[
        PlaybookEntry(trigger="tyre_short", action="add_stop",
                      when="the gauge passes the cliff", until="the stop"),
        PlaybookEntry(trigger="fuel_long", action="drop_stop",
                      when="1.5 laps in hand", until="the flag")])
    said = lines(granted)
    assert "not add one after the last" not in said, said
    assert "cannot drop a stop" not in said
    assert "tyre short - add stop" in said
    # The same two sentences DO appear with nothing granted.
    bare = lines(a_plan())
    assert "not add one after the last" in bare
    assert "cannot drop a stop" in bare


def test_a_rule_that_is_not_the_gated_action_does_not_grant_it():
    """The Daytona plan's `fuel_long: recost_to_flag` is an entry, so the
    trigger is covered - but `grants` says he may not drop the stop, and the
    screen has to say the second, not infer the first."""
    plan = a_plan(playbook=[
        PlaybookEntry(trigger="fuel_long", action="recost_to_flag",
                      when="1.5 laps in hand", until="the flag")])
    text = lines(plan)
    assert "fuel long - recost to flag" in text
    assert "On fuel long he cannot drop a stop" in text


def test_the_screen_and_the_race_ask_the_same_gate():
    """One expression, asked of the SAME stored plan by both sides.

    Comparing `_may` with `grants` is `x == x` now that one calls the other;
    what has been wrong twice is the plan the SCREEN reads against the book
    the RACE builds from the same row.
    """
    from pitcrew.race.coordinator import RaceCoordinator
    from pitcrew.strategy.handover import GATED, grants, playbook_of

    books = (
        [],
        [PlaybookEntry(trigger="tyre_short", action="add_stop",
                       when="the cliff", until="the stop")],
        [PlaybookEntry(trigger="fuel_long", action="report_only",
                       when="1.5 in hand", until="the flag")],
        [PlaybookEntry(trigger="fuel_long", action="drop_stop",
                       when="1.5 in hand", until="the flag"),
         PlaybookEntry(trigger="fuel_long", action="report_only",
                       when="1.5 in hand", until="the flag")],
    )
    from pitcrew.strategy.handover import _withheld_sentence

    for book in books:
        plan = a_plan(playbook=book)
        stored = playbook_of(plan)
        # **The real coordinator, so its own comprehension is under test.**
        # Hand-writing `{e.trigger: e for e in stored}` here re-implemented
        # the line it was meant to compare against, so a change of direction
        # in `coordinator.py` would have left this green.
        coordinator = RaceCoordinator(plan)
        said = lines(plan)
        for trigger, action in GATED:
            withheld = not coordinator._may(trigger, action)
            assert grants(stored, trigger, action) is not withheld, \
                (book, trigger)
            sentence = _withheld_sentence(trigger, plan)
            assert (sentence is not None and sentence in said) is withheld, \
                (book, trigger, said)


def test_a_retirement_is_not_reported_as_blindness():
    """`dead` is anything not in TRIGGERS - a retirement for ANY reason - and
    one sentence asserted the cause was a missing channel (rules 5 and 12).
    `safety_car` happens to be both; a future retirement would not be."""
    plan = a_plan()
    plan["handover"]["playbook"].append(
        {"trigger": "tyre_pressure", "action": "report_only",
         "when": "they drop", "until": "the stop"})
    text = lines(plan)
    assert "tyre pressure, which George no longer acts on" in text, text
    assert "tyre pressure, which he cannot see" not in text


def test_a_duplicated_trigger_reads_the_way_the_race_reads_it():
    """**The screen and the race answered one stored plan differently.**

    `grants`' list branch took the FIRST entry for a trigger; the
    coordinator's dict comprehension keeps the LAST. So a playbook holding
    `fuel_long: drop_stop` then `fuel_long: report_only` had the screen say
    George may drop the stop while the race refused it - the exact inversion
    the single expression exists to remove.

    `Handover.validate` rejects a duplicated trigger, but
    `mcp.propose_strategy` stores a payload without validating and `certify`
    never reads the playbook, which is the premise of this whole module.
    """
    from pitcrew.strategy.handover import grants

    drop = PlaybookEntry(trigger="fuel_long", action="drop_stop",
                         when="1.5 laps in hand", until="the flag")
    report = PlaybookEntry(trigger="fuel_long", action="report_only",
                           when="1.5 laps in hand", until="the flag")
    for order in ([drop, report], [report, drop]):
        as_the_race_reads_it = grants({e.trigger: e for e in order},
                                      "fuel_long", "drop_stop")
        assert grants(order, "fuel_long", "drop_stop") == as_the_race_reads_it
        said = "On fuel long he cannot drop a stop" in lines(
            a_plan(playbook=order))
        assert said is not as_the_race_reads_it, order


def test_an_entry_with_no_trigger_is_named_as_unreadable():
    """`playbook_of` defaults every field to `""`, and this function exists
    because stored rows escape validation - so the blank case rendered as
    "The desk left a rule for , which ...", a sentence naming nothing."""
    plan = a_plan()
    plan["handover"]["playbook"].append(
        {"trigger": "", "action": "", "when": "", "until": ""})
    text = lines(plan)
    assert "rule for ," not in text, text
    assert " -  when " not in text
    assert "1 playbook entry names no trigger and cannot be read" in text


def test_no_author_is_not_the_desk(qt_app):
    """"Standing orders - THE DESK" over a block whose whole content is that
    no desk wrote anything asserts the opposite of what it says. Seven of the
    ten approved plans on file are in that state."""
    screen = RaceScreen()
    screen.set_plan({"label": "app plan", "plan": {"stints": [{"laps": 10}]}})
    assert screen.orders_layout.itemAt(0).widget().text() == "Standing orders"


def test_the_card_carries_no_second_heading(qt_app, store, event_id):
    """`Declared(author)` is already in the card's header; a second
    attribution three rows below it is the same fact twice."""
    from .test_loaded_plan_screen import loaded_row

    screen = StrategyScreen()
    screen.show_loaded([loaded_row(store, event_id)])
    card = screen.findChildren(LoadedCard)[0]
    texts = [w.text() for w in card.findChildren(QWidget)
             if hasattr(w, "text")]
    assert not any(t.startswith("Standing orders") for t in texts), texts


def test_the_rail_fits_the_smallest_display_he_owns(qt_app):
    """**Never measured, and it did not fit.** 384 px bare and 510 px with
    all seven state notes, against 501 - before row 1.7, which took it to
    425/551. Nothing clipped because the layout spent the 20 px bottom
    margin first; `test_every_screen_fits_the_smallest_display_he_owns`
    iterates SCREENS and has never covered the rail."""
    from PyQt6.QtWidgets import QStackedWidget

    from pitcrew.app import NAV_GROUPS, NavRail, SCREENS

    stack = QStackedWidget()
    for _ in SCREENS:
        stack.addWidget(QWidget())
    rail = NavRail(stack, NAV_GROUPS)
    for index in range(len(SCREENS)):
        rail.set_note(index, "12 LAPS")
    height = rail.minimumSizeHint().height()
    assert height <= 501, (
        f"the rail demands {height}px; the smallest display gives 501 and "
        f"Settings is the last item on it")

    # **And the height alone has no teeth once it scrolls** - it is 68 px
    # whatever the rail holds. What can still go wrong is moving focus or
    # selection to an item below the fold: `QScrollArea` follows
    # `focusNextPrevChild`, NOT a direct `setFocus`, so End and Ctrl+7 put
    # the crayon focus bar 71 px off-screen with nothing to say where he is.
    rail.resize(178, 441)
    rail.show()
    qt_app.processEvents()
    last = rail._labels[len(SCREENS) - 1]
    assert last.geometry().bottom() > 441, "not below the fold; test is void"
    rail.focus_item(len(SCREENS) - 1)
    qt_app.processEvents()
    assert not last.visibleRegion().isEmpty(), "focused off-screen"
    rail._scroller.verticalScrollBar().setValue(0)
    qt_app.processEvents()
    rail.select(len(SCREENS) - 1)
    qt_app.processEvents()
    assert not last.visibleRegion().isEmpty(), "selected off-screen"

    # **The note elides in PIXELS, against the room the widget HAS.**
    # Asserting it against `NOTE_PX` was the elider checked against its own
    # argument - green at 134, at 300 and at 1000. The room is the viewport
    # less the column margins, which is what actually changes when the
    # scrollbar appears, and a constant for the narrow case cut every note
    # short in the wide one.
    # **Against what the LAYOUT hands the label, not what `set_note` was
    # given.** Comparing with `viewport().width() - NOTE_MARGINS` was the
    # elider checked against its own expression, bit for bit: the suite was
    # green with `NOTE_MARGINS = 0`, while notes rendered 41 px past the
    # viewport with the horizontal bar off - unreachable and un-ellipsised.
    # **A note must never be what widens the rail.** Horizontal scrolling is
    # `AlwaysOff`, so anything past 178 px is unreachable and un-ellipsised.
    #
    # Asserted as a DIFFERENCE, not against 178: the absolute width is a text
    # measurement, and the suite runs offscreen where Qt has no font database
    # - there "Reference" alone wants 154 px of the rail's 178 (it wants 96
    # on the real font). Measuring that would be the third instrument error
    # on this row. What no font can change is that eliding a long note must
    # not make the rail want more room than a short one does.
    inner = rail._scroller.widget()
    rail.set_note(0, "12 LAPS")
    qt_app.processEvents()
    baseline = inner.minimumSizeHint().width()
    for note in ("Ludo 1-stop, RBR Short, 30 Aug", "3 x RM, 2 stops",
                 "ludo plan - Daytona GR3 Rd6, 11+9 with playbook (rev 2)"):
        rail.set_note(0, note)
        qt_app.processEvents()
        assert inner.minimumSizeHint().width() <= baseline, (
            note, inner.minimumSizeHint().width(), baseline)

    # **And the room follows the scrollbar.** A note elided while the bar was
    # hidden used to keep its old text and have the last 12 px clipped, with
    # the horizontal bar off, until something happened to set it again -
    # reachable by dragging the window toward its own 560 px minimum.
    rail.resize(178, 900)
    qt_app.processEvents()
    long_note = "ludo plan - Daytona GR3 Rd6, 11+9 with playbook"
    rail.set_note(0, long_note)
    rail.resize(178, 200)
    qt_app.processEvents()
    # The raw text is kept so the resize can redo the elision - asserting the
    # elided STRING changed would need real font metrics, because offscreen
    # 146 px and 132 px of fallback advance round to the same cut.
    assert rail._note_text[0] == long_note
    assert inner.minimumSizeHint().width() <= baseline
    # **This half needs a real font, and saying so IS the finding.**
    # Offscreen Qt has no font database: `QFontInfo(...).pixelSize()` is -1,
    # every glyph gets the same fallback advance, and no string over twelve
    # characters fits 134 px - so under the CI font "3 x RM, 2 stops" is
    # genuinely too wide and there is no string that can tell a pixel elision
    # from a character count. A test that asserted it anyway would be
    # asserting the artefact that caused the defect.
    from PyQt6.QtGui import QFontInfo

    if QFontInfo(rail._notes[0].font()).pixelSize() > 0:
        rail.set_note(0, "3 x RM, 2 stops")
        assert rail._notes[0].text() == "3 x RM, 2 stops", (
            "a note that fits must not be cut: it was truncated to "
            "'3 x RM, 2 s…' on the strength of an offscreen measurement")


def test_the_contract_quotes_the_calls_it_is_about():
    """Both `report_form`s, not one. The `tyre_short` half is pinned by the
    test above; nothing held `"You're fuelled to the flag."` against
    `calls.py`, so the contract could have drifted from the call it quotes on
    the half that has been right all along."""
    from pitcrew.race.calls import RaceState, _stops_off

    state = RaceState()
    state.lap, state.laps_total = 8, 20
    state.stint_ends_on_lap = 10
    state.fuel_l, state.fuel_per_lap_l = 60.0, 3.0
    # The stop must have stopped being needed on fuel, or the call is silent:
    # no regulation owes one, fuel is what the plan was capped by, and the
    # tank covers the twelve laps left.
    state.mandatory_stops_left = 0
    state.plan_binding_constraint = "fuel"
    call = _stops_off(state)
    assert call is not None and call.structural_action == "drop_stop"
    assert call.report_form in lines(a_plan()), call.report_form


def test_gated_names_every_structural_call_site():
    """**`GATED` is hand-maintained against `calls.py`.**

    `change_compound` and `abandon_plan` are in `STRUCTURAL_ACTIONS` with no
    call site today. If either gains one, the standing orders go silent about
    a decision George has been barred from - which is the defect class this
    whole row is about, and nothing would have said so.

    Read off the source rather than trusted: every `Call(...)` carrying a
    `structural_action` must have its (trigger, action) pair named in
    `GATED`, and every pair in `GATED` must have a call.
    """
    import pathlib

    import pitcrew.race.calls as calls_module
    from pitcrew.strategy.handover import GATED

    source = pathlib.Path(calls_module.__file__).read_text(encoding="utf-8")
    found, unread, balanced = _structural_sites(source)
    assert balanced, (
        "the uses of structural_action in calls.py do not match the "
        "containers this walker read - it is written in a shape the walker "
        "cannot see, so it is not guarding anything")
    assert not unread, (
        f"the walker saw {len(unread)} structural_action site(s) it could "
        f"not read, so their (trigger, action) pair was dropped in silence: "
        f"{unread}")
    assert found == set(GATED), (
        f"calls.py gates {found}; GATED names {set(GATED)} - a pair in one "
        f"and not the other is a decision the standing orders are silent "
        f"about")


def _structural_sites(source: str):
    """Every `(trigger, action)` pair `calls.py` gates, off its own AST.

    **Lifted out of its test so the break-test is a test.** Four shapes used
    to pass while blind: a dict literal splatted as `**rail`, an action named
    through a module constant, a missing `trigger` key, and plain keyword
    arguments. Returns `(pairs, unreadable, balanced)`.

    `balanced` is False when some occurrence of the identifier fits none of
    the forms below - which is how this says it has gone blind rather than
    going quiet. It is a CLASSIFICATION, not a count: the arithmetic version
    assumed exactly one benign mention and then failed on a bare local read
    and on `replace(call, structural_action=None)`, both of which
    `coordinator.py` already contains.

    **One shape it still cannot see, stated rather than claimed away**: a
    `Call(...)` built with the field passed POSITIONALLY mentions the name
    nowhere, so nothing is there to classify. The field sits eleventh in
    `Call`, so nobody writes it that way - but "cannot go blind" would be the
    overstatement this row keeps finding, and this is the honest bound.
    """
    import ast
    import io
    import tokenize

    NAME = "structural_action"
    tree = ast.parse(source)

    def constant(node):
        # `structural_action="add_stop" if unplanned else None` - the action
        # is the branch that is not None; the CONDITION is what
        # `_withheld_sentence` has to evaluate.
        if isinstance(node, ast.IfExp):
            node = node.body
        return node.value if isinstance(node, ast.Constant) else None

    # An `AnnAssign`'s target is an `ast.Name`, and `ast.walk` visits both -
    # so the declaration counted twice and nothing balanced. Claim it once.
    claimed = {id(node.target) for node in ast.walk(tree)
               if isinstance(node, ast.AnnAssign)
               and isinstance(node.target, ast.Name) and node.target.id == NAME}

    found, unread, classified = set(), [], 0
    for node in ast.walk(tree):
        # --- the two shapes a gate is written in ---------------------------
        if isinstance(node, ast.Dict):
            pairs = {k.value: v for k, v in zip(node.keys, node.values)
                     if isinstance(k, ast.Constant)}
        else:
            pairs = {k.arg: k.value
                     for k in getattr(node, "keywords", None) or ()
                     if k.arg}
        if NAME in pairs:
            classified += 1
            action = pairs[NAME]
            # A literal None is a deliberate STRIP, not a gate:
            # `_within_the_playbook` writes exactly that to withhold one.
            if isinstance(action, ast.Constant) and action.value is None:
                continue
            trigger = constant(pairs.get("trigger"))
            action = constant(action)
            if trigger is None or action is None:
                # **Counted but not read is the same as not seen.** This used
                # to fall through, keeping the tally balanced and dropping
                # the pair in silence.
                unread.append(ast.dump(node)[:120])
                continue
            found.add((trigger, action))
            continue
        # --- and the forms that are not a gate at all ----------------------
        if isinstance(node, ast.AnnAssign) and \
                isinstance(node.target, ast.Name) and node.target.id == NAME:
            classified += 1        # the dataclass field's own declaration
        elif isinstance(node, ast.Attribute) and node.attr == NAME:
            classified += 1        # reading it back off a Call
        elif isinstance(node, ast.arg) and node.arg == NAME:
            classified += 1        # a parameter named after it
        elif isinstance(node, ast.Name) and node.id == NAME and \
                id(node) not in claimed:
            classified += 1        # a local of that name, read or written

    # Tokenised, not `str.count`: the raw substring appears in comments and
    # in prose, so counting text failed on a docstring and passed on a
    # rename.
    uses = 0
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NAME and token.string == NAME:
            uses += 1
        elif token.type == tokenize.STRING and \
                token.string.strip("bBrRuUfF") in (f'"{NAME}"', f"'{NAME}'"):
            uses += 1
    return found, unread, classified == uses


def test_the_loader_prints_the_checks_that_could_not_run(store, event_id,
                                                         capsys, tmp_path):
    """**The CLI re-rendered what it was SENT, not what it stored.**

    `accept` attaches the certificate after `as_stored` and returns only the
    warnings, so every "Not checked:" line was dropped at the one moment the
    author could still act on it. Silence is never a pass.
    """
    import json

    from pitcrew.strategy import handover as module

    payload = {
        "plan": {"stints": [{"laps": 15, "compound": "RM", "fuel_l": 92.0,
                             "start_lap": 1},
                            {"laps": 5, "compound": "RM", "fuel_l": 32.0,
                             "start_lap": 16}],
                 "stops": 1, "pit_laps": [15], "binding_constraint": "fuel"},
        "playbook": [], "author": "ludo", "assumptions": []}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    stored_rows = []

    class _Store:
        def close(self):
            pass

        def list_strategies(self, _event):
            return stored_rows

    def _accept(store, event, handover, *, label=None):
        stored = handover.as_stored(handover.plan)
        stored["handover"]["certificate"] = {
            "warnings": [], "unchecked": ["the lap count"]}
        stored_rows.append({"id": 7, "plan": stored})
        return 7, []

    # `main` imports Store from `store.db` inside itself, so the patch goes
    # there rather than onto this module.
    from pitcrew.store import db

    real_store, real_accept = db.Store, module.accept
    db.Store, module.accept = _Store, _accept
    try:
        assert module.main(["--event", str(event_id), "--file", str(path)]) == 0
    finally:
        db.Store, module.accept = real_store, real_accept

    printed = capsys.readouterr().out
    assert "Not checked: the lap count" in printed, printed
    assert "Standing orders" not in printed, "the CLI prints no heading"


def test_the_walker_sees_what_it_claims_to_see():
    """The break-test, as a test. **Both directions.**

    Five shapes used to leave `found` equal to `GATED` and the guard green
    about a call site it had never read. And the fix for that - a
    `containers == uses - 1` balance - then failed on four shapes of ordinary
    code, two of which `coordinator.py` already contains, saying the guard
    "is not guarding anything" about a file nobody had touched.
    """
    control = ('rail = dict(structural_action="add_stop" if u else None,\n'
               '            trigger="tyre_short")\n'
               'structural_action: str | None = None\n')
    good = {("tyre_short", "add_stop")}

    def reads_cleanly(source):
        found, unread, balanced = _structural_sites(source)
        return found == good and not unread and balanced

    assert reads_cleanly(control)

    # --- must NOT fail: none of these is a gate ---------------------------
    for name, extra in {
        "an attribute read": "_x = bool(call.structural_action)\n",
        "a keyword-only parameter":
            "def _mk(*, structural_action=None):\n"
            "    return structural_action\n",
        "a second annotated field":
            "class _Other:\n    structural_action: str | None = None\n",
        "the deliberate strip": "_y = replace(c, structural_action=None)\n",
        "a mention in a comment": '# structural_action="abandon_plan"\n',
        "a local of that name": 'structural_action = "x"\n',
    }.items():
        assert reads_cleanly(extra + control), name

    # --- must fail: each is a gate the standing orders would not mention --
    for name, extra in {
        "a dict literal":
            '{"structural_action": "abandon_plan", "trigger": "incident"}\n',
        "an action named through a constant":
            '_A = "abandon_plan"\n'
            'r = dict(structural_action=_A, trigger="incident")\n',
        "no trigger key": 'r = dict(structural_action="abandon_plan")\n',
        "plain keywords":
            'c = Call(structural_action="abandon_plan", trigger="incident")\n',
        "a subscript assignment":
            'r = {}\nr["structural_action"] = "abandon_plan"\n',
    }.items():
        assert not reads_cleanly(extra + control), f"{name} passed while blind"


def test_a_plan_with_only_stints_is_read_for_its_stops():
    """**`Handover.validate` requires `stints` and neither `stops` nor
    `pit_laps`**, so a plan carrying only the first certifies and stores -
    and `_stops_planned` returned None for it, which rendered as "he may
    bring a planned stop forward" about a plan with no stop in it."""
    from pitcrew.strategy.handover import Handover, _stops_planned

    bare = {"stints": [{"laps": 20, "compound": "RM", "start_lap": 1}]}
    assert Handover(plan=bare).validate() == []
    assert _stops_planned(bare) == 0

    said = lines({**bare, "handover": {"playbook": []}})
    assert "No stop is planned, so he cannot bring one forward" in said, said
    assert "may bring a planned stop forward" not in said
    assert "the stops stay in the plan" not in said

    # And `len(stints) - 1` agrees with a real plan's own `stops`.
    assert _stops_planned(a_plan()) == a_plan()["stops"]


def test_a_granted_rule_the_plan_cannot_fire_is_named():
    """The mirror of the withheld sentence, and the same failure as a rule
    for a trigger he cannot see: `_stops_off` returns None while
    `stint_ends_on_lap` is None, so `fuel_long: drop_stop` on a plan with no
    stop is a rule the driver believes is armed."""
    plan = {"stints": [{"laps": 20, "compound": "RM", "start_lap": 1}],
            "handover": {"playbook": [
                {"trigger": "fuel_long", "action": "drop_stop",
                 "when": "1.5 laps in hand", "until": "the flag"}]}}
    said = lines(plan)
    assert "cannot fire on this plan - there is no stop to drop" in said, said

    # With a stop in the plan the same rule is an ordinary standing order.
    with_a_stop = lines(a_plan(playbook=[
        PlaybookEntry(trigger="fuel_long", action="drop_stop",
                      when="1.5 laps in hand", until="the flag")]))
    assert "cannot fire on this plan" not in with_a_stop
    assert "fuel long - drop stop" in with_a_stop


def test_the_two_withheld_sentences_say_it_the_same_way():
    """Rule 13. They drifted: the tyre line dropped "without a rule from the
    desk" while the fuel line kept it, so the driver could not tell that the
    tyre gate is a permission the desk could grant."""
    from pitcrew.strategy.handover import GATED, _withheld_sentence

    plan = a_plan()
    for trigger, _action in GATED:
        sentence = _withheld_sentence(trigger, plan)
        assert sentence is not None
        assert "without a rule from the desk" in sentence, (trigger, sentence)
        assert sentence in lines(plan)


def test_fields_that_disagree_about_stops_are_not_answered_with_a_number():
    """**Three fields say how many stops a plan holds and nothing makes them
    agree.** `certify` refuses `stops != len(stints) - 1` but never checks
    `pit_laps` against either, and `validate` requires only `stints` - so a
    plan listing one box lap and one stint validates, certifies and stores.
    Reading `stints` first and returning it answered `0`, and the Race page
    printed "box lap 10" two inches above "No stop is planned".
    """
    from pitcrew.strategy.handover import _stops_planned

    plan = {"stints": [{"laps": 20, "compound": "RM", "start_lap": 1}],
            "pit_laps": [10], "binding_constraint": "fuel",
            "handover": {"playbook": []}}
    assert _stops_planned(plan) is None, "0 is a claim, and nothing made it"

    said = lines(plan)
    assert "they disagree, so how many stops it holds is not known" in said, \
        said
    # Neither of the two sentences that assume a count.
    assert "No stop is planned" not in said
    assert "may bring a planned stop forward" not in said
    # And the half that is true either way is still said.
    assert "cannot add a stop without a rule from the desk" in said

    # Agreeing fields still answer.
    assert _stops_planned(a_plan()) == 1
    assert "they disagree" not in lines(a_plan())


def test_a_rule_is_described_once_and_in_one_state():
    """An entry is readable and able to fire, readable and unable, or not
    readable - never two of those. Dropping the unfireable ones into `dead`
    got a rule a retirement notice, an unfireable notice AND a no-rule
    notice, all disagreeing."""
    plan = {"stints": [{"laps": 20, "compound": "RM", "start_lap": 1}],
            "handover": {"playbook": [
                {"trigger": "fuel_long", "action": "drop_stop",
                 "when": "1.5 laps in hand", "until": "the flag"}]}}
    said = lines(plan)

    assert said.count("fuel long") == 1, said
    assert "cannot fire on this plan - there is no stop to drop" in said
    # Not under "George may", not retired, and not reported as unruled.
    assert "fuel long - drop stop" not in said
    assert "George no longer acts on" not in said
    assert "No rule from the desk on fuel short, stop missed, incident" in said
