"""The standing orders, capped where the desk's prose runs long (11 Sep 2026).

Carried from row 1.7: strategy 15 rendered 3,432 characters of standing
orders with one 432-character line, uncapped, on the page he reads on the
grid. Measured read-only off the live DB: every line over 200 characters is a
*Resting on* assumption - the desk's prose - and the eight of them are 2,262
of the 3,432.

**What is capped and what is not.** Only the assumptions. A playbook rule or
a line about what George cannot do is the contract, and a rule cut short is a
rule the driver cannot read in full - so those are never touched. The cap is
in the ONE renderer both screens use, so the Strategy card and the Race page
still say the same words (`test_both_screens_say_the_same_words`), and the
full text is on the line's tooltip on both.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from pitcrew.strategy.handover import standing_orders
from pitcrew.ui.widgets import RESTING_CAP, render_standing_orders

from .test_controller import qt_app  # noqa: F401
from .test_standing_orders import a_plan

LONG = ("OVERRIDE, stated: the app's optimiser caps a stint at 13 laps because "
        "that is the longest run on file, and this plan runs 21 - the run at "
        "session 98 went 12 laps on RS at x2 and the gauge read 31% worn, so "
        "21 laps is 54% on the linear rate and inside the 85% ceiling with a "
        "lap of margin, which is the whole case for overriding the cap here.")


# The holders, kept for the module: a `QWidget` collected when `_texts`
# returns takes its child labels with it, and every `text()` then raises.
_HOLDERS: list = []


def _texts(plan):
    holder = QWidget()
    _HOLDERS.append(holder)
    layout = QVBoxLayout(holder)
    render_standing_orders(layout, plan)
    return [layout.itemAt(i).widget() for i in range(layout.count())]


def test_a_long_assumption_is_cut_at_a_word_and_kept_whole_in_the_tooltip(
        qt_app):  # noqa: F811
    assert len(LONG) > RESTING_CAP
    widgets = _texts(a_plan(assumptions=[LONG]))
    cut = next(w for w in widgets if w.text().startswith("OVERRIDE"))
    assert len(cut.text()) <= RESTING_CAP
    assert cut.text().endswith("…")
    # At a word, not mid-word.
    assert LONG.startswith(cut.text()[:-1].rstrip())
    assert LONG[len(cut.text()[:-1].rstrip())] == " "
    assert cut.toolTip() == LONG


def test_a_short_assumption_is_untouched_and_carries_no_tooltip(qt_app):  # noqa: F811
    widgets = _texts(a_plan(assumptions=["wear off the HUD"]))
    line = next(w for w in widgets if w.text() == "wear off the HUD")
    assert line.toolTip() == ""


def test_a_rule_is_never_cut_however_long(qt_app):  # noqa: F811
    """A playbook rule cut short is one he cannot read in full."""
    plan = a_plan()
    orders = standing_orders(plan)
    rules = [o.text for o in orders if not o.resting and not o.heading]
    shown = [w.text() for w in _texts(plan)]
    for rule in rules:
        assert rule in shown, rule


def test_both_screens_cut_the_same_line_the_same_way(qt_app, store,  # noqa: F811
                                                     event_id):
    """`test_both_screens_say_the_same_words` runs on a 35-character
    assumption, so it never reaches the cap. This one does: the card and the
    Race page show the same cut and carry the same whole line underneath."""
    from pitcrew.strategy.handover import accept
    from pitcrew.ui.race_screen import RaceScreen
    from pitcrew.ui.strategy_screen import LoadedCard, StrategyScreen

    from .test_loaded_plan_screen import a_handover

    handover = a_handover()
    handover.assumptions = [LONG]
    strategy_id, problems = accept(store, event_id, handover, label="long")
    assert strategy_id is not None, problems
    row = next(r for r in store.list_strategies(event_id)
               if r["id"] == strategy_id)

    strategy = StrategyScreen()
    strategy.show_loaded([row])
    card = strategy.findChildren(LoadedCard)[0]
    on_card = [w for w in card.findChildren(QWidget)
               if hasattr(w, "text") and w.text().startswith("OVERRIDE")]
    race = RaceScreen()
    race.set_plan(row)
    on_race = [race.orders_layout.itemAt(i).widget()
               for i in range(race.orders_layout.count())]
    on_race = [w for w in on_race if w.text().startswith("OVERRIDE")]

    assert len(on_card) == len(on_race) == 1
    assert on_card[0].text() == on_race[0].text()
    assert on_card[0].toolTip() == on_race[0].toolTip() == LONG


def test_only_the_assumptions_are_marked_resting():
    orders = standing_orders(a_plan(assumptions=[LONG, "short"]))
    resting = [o.text for o in orders if o.resting]
    assert resting == [LONG, "short"]
