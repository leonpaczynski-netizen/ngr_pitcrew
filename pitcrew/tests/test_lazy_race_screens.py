"""Practice, Strategy and Race are built after the first frame - and nothing
can find one missing.

Critic, round 4 (19 Sep 2026): none of the three is visible at launch, and
together they were 57-95 ms of building, plus their share of `show()` and the
Practice fill's compound-pace read, all before the first frame. They were
kept eager because they are "wanted on race day". That reason is now kept by
a guarantee instead: the controller builds any of them the moment anything
reads it (`PitCrewController._lazy_screen`), and a session or a race is only
ever armed through code that reads one.

What each test pins:

* the launch - the window, the controller and its first fill - builds none
  of the three;
* reading one through the controller builds it, puts it in the stack where
  the rail looks, and wires every signal exactly once, however often it is
  read and by whichever route (controller, rail, warm chain);
* the warm chain builds these three before Car, Reference and Settings;
* a screen built after the first fill shows exactly what an eager one does -
  the status line, the laps, the plan picker - for an event and for none;
* arming a race with the Race screen not yet built builds it first, and the
  refusal lands on it;
* a notice said before the Practice screen exists builds its anchor.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.store.db import Store  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def window(qt_app, store: Store):
    from pitcrew.app import PitCrewWindow

    made = PitCrewWindow(store)
    yield made
    made.controller.shutdown()


# index in the stack -> (window attribute, controller attribute, signals the
# controller must be listening to)
OWNED = {
    2: ("practice_screen", "practice",
        ("recording_toggled", "lap_changed", "export_requested",
         "practice_mode_changed", "practice_intent_changed",
         "coach_speaks_changed", "debrief_requested")),
    3: ("strategy_screen", "strategy",
        ("build_requested", "qualifying_requested", "approve_requested",
         "approve_loaded_requested")),
    4: ("race_screen", "race_screen",
        ("start_requested", "shown", "replan_accepted", "replan_declined",
         "stop_requested")),
}


def wired(screen, name: str) -> int:
    return screen.receivers(getattr(screen, name))


def test_the_launch_builds_none_of_the_three(window, store, event_id):
    """The window, the controller, and the first fill - which is what runs
    before the first frame - touch none of them."""
    store.set_state("active_event_id", event_id)
    window.controller._first_paint_work()
    for index, (attr, _name, _signals) in OWNED.items():
        assert getattr(window, attr) is None, attr
        assert getattr(window.controller, f"_{_name.lstrip('_')}") is None
        placeholder = window.stack.widget(index)
        assert type(placeholder).__name__ == "QWidget", attr


@pytest.mark.parametrize("index", sorted(OWNED))
def test_reading_it_builds_it_where_the_rail_looks_and_wires_it_once(
        window, index):
    attr, name, signals = OWNED[index]
    screen = getattr(window.controller, name)
    assert screen is not None
    assert getattr(window, attr) is screen
    assert window.stack.widget(index) is screen
    # Every route returns the same screen, and none of them wires it again.
    assert getattr(window.controller, name) is screen
    assert window._ensure_screen(index) is screen
    window.warm_screens()
    assert getattr(window, attr) is screen
    for signal in signals:
        assert wired(screen, signal) == 1, (attr, signal)


def test_the_race_screen_picker_is_wired_once(window):
    screen = window.controller.race_screen
    window._ensure_screen(4)
    picker = screen.plan_picker
    # The screen's own slot, and the controller's.
    assert picker.receivers(picker.activated) == 2


def test_warming_builds_the_race_day_three_first(window):
    built = []
    for _ in range(6):
        before = {i for i, (attr, *_r) in
                  {**window.LATE_SCREENS, **window.CONTROLLER_SCREENS}.items()
                  if getattr(window, attr) is not None}
        window.warm_screens()
        after = {i for i, (attr, *_r) in
                 {**window.LATE_SCREENS, **window.CONTROLLER_SCREENS}.items()
                 if getattr(window, attr) is not None}
        built.extend(sorted(after - before))
    assert built == [2, 3, 4, 1, 5, 6]


def _shown(practice, race) -> dict:
    """What the driver can see on the two screens the first fill writes."""
    picker = race.plan_picker
    approved = picker.findData(True)
    return {
        "practice status": practice.subtitle.text(),
        "practice status ink": practice.subtitle.styleSheet(),
        "practice laps": len(practice._rows),
        "race status": race.subtitle.text(),
        "race picker": picker.currentIndex(),
        "race plan offered": picker.model().item(approved).isEnabled(),
    }


def _eager(store):
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen
    from pitcrew.ui.race_screen import RaceScreen
    from pitcrew.ui.strategy_screen import StrategyScreen

    practice, race = PracticeScreen(), RaceScreen()
    controller = PitCrewController(store, EventScreen(), practice,
                                   StrategyScreen(), race, defer_strip=True)
    controller._first_paint_work()
    return controller, practice, race


@pytest.mark.parametrize("case", ["event", "no event", "unarmable plan"])
def test_built_after_the_first_fill_it_shows_what_an_eager_one_does(
        qt_app, store, event_id, case):
    from pitcrew.app import PitCrewWindow

    with_event = case != "no event"
    store.set_state("active_event_id", event_id if with_event else None)
    if case == "unarmable plan":
        # Approved, and missing what it needs to arm: the Race screen says so
        # in the week - the one line `_refresh_race_options` writes.
        store.approve_strategy(store.save_strategy(event_id, {"stints": []}))
    eager, practice, race = _eager(store)
    lazy = PitCrewWindow(store)
    try:
        lazy.controller._first_paint_work()
        assert lazy.practice_screen is None and lazy.race_screen is None
        for _ in range(3):
            lazy.warm_screens()
        want = _shown(practice, race)
        got = _shown(lazy.practice_screen, lazy.race_screen)
        assert got == want
        if with_event:
            assert "Start practice when you are ready" in got[
                "practice status"]
        else:
            assert got["practice status"].startswith("No event yet")
        if case == "unarmable plan":
            assert got["race status"].startswith(
                "The approved plan will not arm")
            assert got["race plan offered"] is True
    finally:
        eager.shutdown()
        lazy.controller.shutdown()


def test_arming_a_race_builds_the_race_screen_first(window):
    """The guarantee, on the path that arms a race: `start_race` reads the
    screen, so it cannot run against one that does not exist. With no event
    it refuses - and the refusal is on the screen it built and wired."""
    assert window.race_screen is None
    assert window.controller.start_race() is False
    screen = window.race_screen
    assert screen is not None and window.stack.widget(4) is screen
    assert "Create an event before racing" in screen.subtitle.text()
    assert wired(screen, "start_requested") == 1


def test_a_notice_before_the_practice_screen_exists_builds_its_anchor(
        window):
    window.controller.settings.banner_enabled = True
    assert window.practice_screen is None
    window.controller.announce("Box this lap.")
    assert window.practice_screen is not None
    assert window.controller._banner is not None


def test_the_bench_writes_to_the_practice_screen_it_builds(window):
    assert window.practice_screen is None
    assert window.controller.bench.practice is window.controller.practice
    assert window.practice_screen is not None
