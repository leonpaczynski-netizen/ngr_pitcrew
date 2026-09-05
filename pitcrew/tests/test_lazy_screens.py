"""The three screens that are built on first visit rather than at launch.

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


LATE = (5, 6)             # Reference, Settings
SIGNALS = {
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
    for _ in range(10):
        qt_app.processEvents()

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
    def boom():
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
