"""The notice that has to be readable through a headset.

He reads this monitor through PSVR2 passthrough from a metre away, in a
headset, sitting in a rig. The lap rack is unreadable like that and it is
exactly when he needs to know whether the app is recording.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt

from pitcrew.ui import theme
from pitcrew.ui.banner import HEADLINE_FRACTION, Banner

from .test_controller import qt_app  # noqa: F401


def test_the_headline_is_sized_off_the_screen_not_off_a_constant(qt_app):
    """A regression with a number on it.

    The first version set the font with `setFont`, which a Qt style sheet
    beats — and the app sets one on every QLabel. It rendered a screen-filling
    sign at fifteen pixels.
    """
    banner = Banner()
    banner.announce("Recording")
    height = banner.screen().geometry().height()
    rendered = banner.headline.fontMetrics().height()
    assert rendered > height * HEADLINE_FRACTION * 0.8
    assert rendered > 100, "a notice this small cannot be read in a headset"


def test_it_never_takes_focus(qt_app):
    """He may be driving, and a window that activates itself can take a
    keypress from the game."""
    banner = Banner()
    assert banner.testAttribute(
        Qt.WidgetAttribute.WA_ShowWithoutActivating) is True
    assert banner.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_it_goes_away_on_its_own(qt_app):
    """There is no mouse in the rig, so it cannot wait for a click."""
    banner = Banner()
    banner.announce("Recording", seconds=0.05)
    assert banner.isVisible() is True
    assert banner._timer.isActive() is True


def test_a_click_dismisses_it_early(qt_app):
    banner = Banner()
    banner.announce("Recording", seconds=30)
    banner.mousePressEvent(None)
    assert banner.isVisible() is False
    assert banner._timer.isActive() is False


def test_a_warning_reads_in_the_warning_ink(qt_app):
    banner = Banner()
    banner.announce("Stopped", "No laps recorded.", warn=True)
    assert theme.WARNING in banner.headline.styleSheet()
    banner.announce("Recording")
    assert theme.STENCIL in banner.headline.styleSheet()


def test_a_second_notice_replaces_the_first_with_its_own_full_time(qt_app):
    """Stacked, the second would inherit whatever was left of the first."""
    banner = Banner()
    banner.announce("Recording", seconds=10)
    banner.announce("Stopped", seconds=10)
    assert banner.headline.text() == "STOPPED"
    assert banner._timer.remainingTime() > 9000


def test_announcing_with_no_banner_is_a_no_op(qt_app, store, event_id):
    """The recording path has to stay drivable where there is no widget to
    anchor a banner to — every controller test runs that way, and so does
    replaying a stored capture."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    try:
        controller._banner = None
        controller.announce("Recording")      # must not raise
    finally:
        controller.shutdown()


def test_the_toggle_turns_it_off(qt_app, store, event_id):
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    try:
        assert controller._banner is not None
        controller.settings.banner_enabled = False
        controller.announce("Recording")
        assert controller._banner.isVisible() is False
    finally:
        controller.shutdown()
