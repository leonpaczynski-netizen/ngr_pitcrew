"""The screens that are built after the window appears rather than before it.

**Nothing in this repository built a `PitCrewWindow` before this file.** It is
constructed in exactly one place, `app.main`, and 145 test files went around
it. That is why this exists: the whole risk of deferring a screen is that its
wiring is done in a second place, and a `connect` left out of that second
place fails silently - no exception, no log, just a button that does nothing
for the life of the process.

So the shape of the test is a comparison, not an assertion about one window:
an eager window and a lazy one, built against the same store, must end up
indistinguishable. Anything the attach forgets shows up as a difference.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.app import SCREENS  # noqa: E402

from pitcrew.store.db import Store                      # noqa: E402


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


LATE = (1, 5, 6)          # Car, Reference, Settings
SIGNALS = {
    # Car joined these on 19 Sep 2026, when the window stopped waiting for
    # the speech models and its 300 ms stopped hiding inside that wait.
    1: ("saved", "car_changed"),
    6: ("saved", "test_beep_requested", "test_voice_requested",
        "test_haptics_requested", "test_feed_requested",
        "test_gauge_requested", "capture_toggled", "listen_toggled"),
}


def test_the_stack_is_full_width_before_anything_is_built(window):
    """`NavRail` disables an item past `stack.count()` and calls it "Not built
    yet". A screen waiting to be built is not that, and must not read as
    that - the rail would be telling the driver the app is unfinished."""
    assert window.stack.count() == len(SCREENS)
    assert all(label.isEnabled() for label in window.rail._labels)


def test_the_deferred_screens_start_absent(window):
    for index in LATE:
        name = window.LATE_SCREENS[index][0]
        assert getattr(window, name) is None


@pytest.mark.parametrize("index", LATE)
def test_navigating_builds_the_screen_and_shows_it(window, index):
    window.rail.select(index)
    name, factory, _attach = window.LATE_SCREENS[index]
    screen = getattr(window, name)
    assert isinstance(screen, factory)
    assert window.stack.widget(index) is screen
    assert window.stack.currentWidget() is screen
    assert window.stack.count() == len(SCREENS)


@pytest.mark.parametrize("index", LATE)
def test_the_controller_sees_the_screen_it_was_given(window, index):
    """The controller keeps `settings_screen`; a screen the window has but the
    controller does not is a screen whose buttons are wired to nothing."""
    window.rail.select(index)
    screen = window.stack.widget(index)
    if index == 6:
        assert window.controller.settings_screen is screen
    elif index == 1:
        assert window.controller.car_screen is screen
    else:
        # Reference is never passed to the controller at all, by design.
        assert window.reference_screen is screen


def test_the_rig_and_the_bench_see_the_settings_screen(window):
    """The one that would be silent. `test_feed`, `test_gauge`, `test_beep`,
    `test_voice`, `probe_button` and the transducer test all return at their
    own `is None` guard - so a settings screen the bench cannot see is five
    dead pre-race checks and a driver who verified nothing."""
    assert window.controller.rig.settings_screen is None
    assert window.controller.bench.settings_screen is None

    window.rail.select(6)
    screen = window.settings_screen
    assert window.controller.rig.settings_screen is screen
    assert window.controller.bench.settings_screen is screen


def pump_until(qt_app, done, timeout: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while not done() and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.002)
    qt_app.processEvents()


def wired(screen, name: str) -> int:
    """How many slots are on one of a screen's signals.

    `receivers` is on the QObject, not on the bound signal.
    """
    return screen.receivers(getattr(screen, name))


def test_a_second_visit_does_not_rebuild_or_rewire(window):
    """A doubled `connect` is permanent, fires everything twice, and is
    invisible until a Save writes two records."""
    for index in LATE:
        window.rail.select(index)
        first = window.stack.widget(index)
        counts = {name: wired(first, name) for name in SIGNALS.get(index, ())}

        window.rail.select(0)
        window.rail.select(index)

        assert window.stack.widget(index) is first, "rebuilt"
        for name, before in counts.items():
            assert wired(first, name) == before, f"{name} was connected twice"


def test_every_deferred_signal_is_connected_exactly_once(window):
    for index, names in SIGNALS.items():
        window.rail.select(index)
        screen = window.stack.widget(index)
        for name in names:
            assert wired(screen, name) == 1, (
                f"{name} on screen {index} has {wired(screen, name)} "
                f"receivers, not 1")


def test_warming_builds_them_all_without_navigating(window, qt_app):
    """The background chain: the first visit to a screen should not be the
    first time it is made."""
    window.warm_screens()
    # Car is built a slice per turn now, so the chain is a dozen turns, not
    # three. Pumped until it is done, with a bound.
    pump_until(qt_app, lambda: all(
        getattr(window, window.LATE_SCREENS[i][0]) is not None for i in LATE))

    for index in LATE:
        assert getattr(window, window.LATE_SCREENS[index][0]) is not None
    assert window.stack.count() == len(SCREENS)
    # It warmed them; it did not navigate to one.
    assert window.stack.currentIndex() == 0


def test_a_screen_that_will_not_build_does_not_spin_the_chain(window, qt_app,
                                                              monkeypatch,
                                                              caplog):
    """**The worst failure in the set if it were missed.** A chain that
    re-armed on the index it just failed would peg a core for the rest of the
    race, with nothing in the log to say why."""
    def boom(**_kwargs):
        raise RuntimeError("this screen will not build")

    monkeypatch.setitem(window.LATE_SCREENS, 5,
                        ("reference_screen", boom, None))
    with caplog.at_level("ERROR"):
        window.warm_screens()
        for _ in range(40):
            qt_app.processEvents()

    assert window.reference_screen is None
    assert any("could not warm" in record.getMessage()
               for record in caplog.records)
    # The chain stopped rather than retrying, and the rail can still try.
    assert window.stack.count() == len(SCREENS)


def test_the_lazy_window_ends_up_like_an_eager_one(qt_app, store: Store):
    """The comparison that catches an attach which forgot a connect."""
    from pitcrew.app import PitCrewWindow

    lazy = PitCrewWindow(store)
    for index in LATE:
        lazy.rail.select(index)

    eager = PitCrewWindow(store)
    for index in LATE:
        eager._ensure_screen(index)

    try:
        for index, names in SIGNALS.items():
            for name in names:
                assert (wired(lazy.stack.widget(index), name)
                        == wired(eager.stack.widget(index), name)), (
                    f"{name} on screen {index} is wired differently")
        assert lazy.stack.count() == eager.stack.count() == len(SCREENS)
    finally:
        lazy.controller.shutdown()
        eager.controller.shutdown()


# ------------------------------------- an attach that fails after wiring
#
# Critic, round 3: the wiring was a flag for the process, set before the
# attach finished. An attach that raised after it (`load_car` for Car,
# `screen.load` for Settings) left the flag on, `warm_screens` dropped the
# screen, and the replacement the rail built next was never connected - its
# Save wrote nothing, with nothing in the log. Wiring now follows the screen.

def _fail_once(real):
    calls = {"n": 0}

    def once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the first attach fails after wiring")
        return real(*args, **kwargs)

    return once


def test_a_car_screen_rebuilt_after_a_failed_attach_still_saves(
        window, qt_app, store, event_id, monkeypatch, caplog):
    controller = window.controller
    # A real active event with a car, so the attach reaches `load_car`.
    store.set_state("active_event_id", str(event_id))
    saves: list = []
    loads: list = []
    # Instance attributes, patched BEFORE the first attach, because the
    # attach connects whatever `self.save_ranges` / `self.load_car` are.
    monkeypatch.setattr(controller, "save_ranges",
                        lambda *args: saves.append(args))
    monkeypatch.setattr(controller, "load_car",
                        _fail_once(lambda car: loads.append(car)))

    with caplog.at_level("ERROR"):
        window.warm_screens()            # Car is first; its attach raises
        for _ in range(20):
            qt_app.processEvents()
    assert any("could not warm the car_screen" in r.getMessage()
               for r in caplog.records)
    assert window.car_screen is None
    assert controller.car_screen is None    # forgotten on both sides

    window.rail.select(1)                # the driver goes to Car
    screen = window.car_screen
    assert screen is not None and window.stack.widget(1) is screen
    assert controller.car_screen is screen
    assert loads == ["Porsche 911 RSR"]         # the retry got the active car
    assert wired(screen, "saved") == 1
    assert wired(screen, "car_changed") == 1

    screen.saved.emit("Porsche 911 RSR", {}, False)
    assert len(saves) == 1, "Save on the rebuilt Car screen went nowhere"

    # A second visit neither rebuilds nor rewires.
    window.rail.select(0)
    window.rail.select(1)
    assert window.car_screen is screen
    assert wired(screen, "saved") == 1


def test_a_settings_screen_rebuilt_after_a_failed_attach_still_saves(
        window, qt_app, monkeypatch):
    from pitcrew.ui.settings_screen import SettingsScreen

    controller = window.controller
    saves: list = []
    monkeypatch.setattr(controller, "save_settings", saves.append)
    monkeypatch.setattr(SettingsScreen, "load",
                        _fail_once(SettingsScreen.load))

    with pytest.raises(RuntimeError):
        window._ensure_screen(6)         # the rail's path, first visit
    assert window.settings_screen is None
    assert controller.settings_screen is None
    for _ in range(5):
        qt_app.processEvents()           # the failed screen is deleted

    screen = window._ensure_screen(6)    # the next visit
    assert window.stack.widget(6) is screen
    assert controller.settings_screen is screen
    for name in SIGNALS[6]:
        assert wired(screen, name) == 1, f"{name} is not wired once"
    screen.saved.emit(controller.settings)
    assert len(saves) == 1, "Save on the rebuilt Settings screen went nowhere"


def test_a_replaced_screen_is_disconnected_from_the_controller(window,
                                                               monkeypatch):
    """A discarded screen must not keep writing into the controller."""
    from pitcrew.ui.car_screen import CarScreen

    controller = window.controller
    saves: list = []
    monkeypatch.setattr(controller, "save_ranges",
                        lambda *args: saves.append(args))
    first = CarScreen(parent=window.stack)
    controller.attach_car_screen(first)
    assert wired(first, "saved") == 1
    second = CarScreen(parent=window.stack)
    controller.attach_car_screen(second)
    assert wired(first, "saved") == 0 and wired(second, "saved") == 1
    first.saved.emit("Old", {}, False)
    second.saved.emit("New", {}, False)
    assert [args[0] for args in saves] == ["New"]
    # And attaching the same screen again is a no-op, not a second connect.
    controller.attach_car_screen(second)
    assert wired(second, "saved") == 1
