"""Three independent choices about how a race runs.

*"In race simulation I want to be able to choose engineer on or off with race
Strat loaded or not."*

They are separate questions and the screen carried one checkbox, so it could
only ever say one of them. Running without the plan is how you find out what
the plan is worth; running silent is how you find out whether you reach the
same decisions it does.

**Silent is not off.** Every call is still computed, still shown on the Race
screen and still written into the outcome export — it is simply not spoken,
and push-to-talk is not armed. A silent run still says what it would have told
him, which is exactly what makes the post-mortem worth reading.
"""
from __future__ import annotations

import pytest

from .test_controller import qt_app  # noqa: F401
from .test_race_wiring import green, raced, voice  # noqa: F401


def choose(screen, *, rehearsal=False, speaks=True, plan=True) -> None:
    screen.mode_picker.setCurrentIndex(screen.mode_picker.findData(rehearsal))
    screen.engineer_picker.setCurrentIndex(
        screen.engineer_picker.findData(speaks))
    screen.plan_picker.setCurrentIndex(screen.plan_picker.findData(plan))


# ------------------------------------------------------------ the four corners

def test_the_league_race_to_the_plan_with_the_engineer_speaking(raced, voice):
    controller, screen, store, _ = raced
    choose(screen, rehearsal=False, speaks=True, plan=True)
    assert controller.start_race() is True
    green(controller)
    assert voice.spoken, "the engineer should have spoken at green"
    assert store.get_session(controller.session_id)["rehearsal"] == 0


def test_a_rehearsal_to_the_plan_is_filed_as_a_rehearsal(raced, voice):
    controller, screen, store, _ = raced
    choose(screen, rehearsal=True, speaks=True, plan=True)
    assert controller.start_race() is True
    assert store.get_session(controller.session_id)["rehearsal"] == 1
    assert "Rehearsal armed" in screen.subtitle.text()


def test_silent_says_nothing_and_still_logs_everything(raced, voice):
    """The whole point of silent rather than off."""
    controller, screen, store, _ = raced
    choose(screen, rehearsal=True, speaks=False, plan=True)
    assert controller.start_race() is True
    green(controller)

    assert voice.spoken == [], "the engineer spoke on a silent run"
    assert controller.race_screen.log_layout.count() > 0, (
        "a silent run still shows the calls it would have made")
    assert store.list_revisions(controller.race_run_id), (
        "a silent run still records the calls for the post-mortem")


def test_without_the_plan_it_races_on_fuel_alone(raced, voice):
    controller, screen, store, _ = raced
    choose(screen, rehearsal=True, speaks=True, plan=False)
    assert controller.start_race() is True
    # The coordinator normalises an absent plan to an empty mapping.
    assert not controller.race.plan
    assert "fuel calls only" in screen.subtitle.text()


# ------------------------------------------------------ the choices are honest

def test_the_plan_choice_is_disabled_when_there_is_no_plan(raced):
    controller, screen, store, event_id = raced
    for strategy in store.list_strategies(event_id):
        with store._write() as conn:
            conn.execute("UPDATE strategies SET status='candidate' WHERE id=?",
                         (strategy["id"],))
    controller._refresh_race_options(store.get_event(event_id))

    assert screen.use_plan() is False, (
        "offering a plan that does not exist is a control that cannot do what "
        "it says")
    index = screen.plan_picker.findData(True)
    assert screen.plan_picker.model().item(index).isEnabled() is False


def test_approving_a_plan_offers_it_without_being_asked(raced):
    """Approve, then go straight to Race: the choice has to have heard."""
    controller, screen, _store, _event_id = raced
    assert screen.use_plan() is True


def test_a_deliberate_no_plan_is_not_overwritten(raced):
    """Following availability is a default, not a rule. If he said no plan,
    approving one later must not quietly turn it back on."""
    controller, screen, store, event_id = raced
    screen.plan_picker.setCurrentIndex(screen.plan_picker.findData(False))
    screen.plan_picker.activated.emit(screen.plan_picker.currentIndex())

    controller._refresh_race_options(store.get_event(event_id))
    assert screen.use_plan() is False


def test_the_engineer_speaks_again_after_a_silent_race(raced, voice):
    """The flag belongs to the race in progress, not to the app."""
    controller, screen, _store, _event_id = raced
    choose(screen, speaks=False, plan=True)
    controller.start_race()
    controller.stop_race()

    choose(screen, speaks=True, plan=True)
    controller.start_race()
    green(controller)
    assert voice.spoken
