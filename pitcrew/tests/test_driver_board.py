"""The glance-up board above the game, in its two states.

`DriverView` was written on 2 Sep 2026, tested, and referenced by nothing but
its own test file — so the instrument existed and had never once been on a
screen. These tests cover what was added on 4 Sep: the box state, the window
that hosts it, and the refusals that keep the box honest.

The box is where this display can do the most damage. He is stationary, he is
holding the trigger, and he is reading one number off it. Every figure there
either rests on something measured or shows a dash — there is no third option,
and most of these tests are about the dash.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pitcrew.ui.driver_view import (  # noqa: E402
    DriverState,
    DriverView,
    DriverWindow,
    format_release,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------- the countdown

@pytest.mark.parametrize("seconds,expected", [
    (None, "--"),       # no measured fill rate here - never a guess
    (0.0, "GO"),
    (-2.0, "GO"),       # already covered before the fill got going
    (1.0, "1"),
    (12.4, "13"),       # rounded UP, like the litres it counts down
    (42.9, "43"),
])
def test_the_countdown_reads_in_whole_seconds(seconds, expected):
    """Rounded up, for the reason `refuel._ceil_l` rounds the litres up: being
    late costs about a litre, being early costs fuel he cannot get back."""
    assert format_release(seconds) == expected


def test_the_countdown_never_shows_a_clock_face():
    """A `0:47` is a lap time everywhere else on this rig."""
    assert ":" not in format_release(47.0)


# ------------------------------------------------------------ state switching

def test_the_screen_switches_wholly_when_he_stops(app):
    view = DriverView()
    view.update_state(DriverState(laps_to_box=3.0))
    assert view.states.currentWidget() is view.running
    view.update_state(DriverState(in_box=True))
    assert view.states.currentWidget() is view.box
    view.update_state(DriverState(laps_to_box=11.0))
    assert view.states.currentWidget() is view.running


def test_in_box_switches_the_screen_even_with_nothing_to_put_on_it(app):
    """A stop with no plan behind it still has to show something, and five
    dashes is the honest something. `in_box` is what switches the screen, not
    any of the figures being set."""
    view = DriverView()
    view.update_state(DriverState(in_box=True))
    assert view.states.currentWidget() is view.box
    assert view.box.fuel_stat.value.text() == "--"
    assert view.box.release_stat.value.text() == "--"
    assert view.box.out_stat.value.text() == "--"


# ------------------------------------------------------------- what it claims

def test_the_box_shows_the_fill_target_and_what_is_aboard(app):
    view = DriverView()
    view.update_state(DriverState(
        in_box=True, fuel_target_l=74.0, fuel_l=31.0, release_in_s=43.0))
    assert view.box.fuel_stat.value.text() == "74"
    assert "31" in view.box.fuel_stat.sub.text()
    assert view.box.release_stat.value.text() == "43"


def test_an_unsized_stop_says_so_rather_than_showing_a_number(app):
    """The same refusal `RefuelWatch.note` makes: he is holding the trigger on
    this figure and one the app invented is worse than none."""
    view = DriverView()
    view.update_state(DriverState(in_box=True, fuel_l=31.0))
    assert view.box.fuel_stat.value.text() == "--"
    assert "nothing sized" in view.box.fuel_stat.sub.text()


def test_the_compound_in_the_box_is_captioned_as_the_plan(app):
    """It is a decision about what to fit, not a reading off the car - and
    nothing here knows how worn the set coming off is, because no packet
    format carries wear at all."""
    view = DriverView()
    view.update_state(DriverState(in_box=True, compound="RH"))
    assert view.box.tyre_stat.value.text() == "RH"
    assert view.box.tyre_stat.sub.text() == "plan"


def test_an_unread_gap_shows_a_dash_and_says_why(app):
    """The gap boxes this rests on have never returned a number in a real
    race, so a dash is the expected state rather than a fault - and an empty
    box he cannot explain is one he would stop trusting the screen over."""
    view = DriverView()
    view.update_state(DriverState(in_box=True))
    assert view.box.out_stat.value.text() == "--"
    assert "no gap read" in view.box.out_stat.sub.text()


def test_a_read_gap_names_the_car_it_puts_him_behind(app):
    view = DriverView()
    view.update_state(DriverState(in_box=True, out_position=7,
                                  out_behind="Rocky"))
    assert view.box.out_stat.value.text() == "P7"
    assert "Rocky" in view.box.out_stat.sub.text()


def test_the_last_stint_and_a_counted_one_name_their_reference_in_words(app):
    """CLAUDE.md rule 13. "Laps in hand" was spoken twice in two minutes
    meaning laps-to-the-stop and laps-to-the-flag, ten laps apart, neither
    naming its reference. On a screen it can be written out, so it is."""
    view = DriverView()
    view.update_state(DriverState(in_box=True, runs_to_flag=True))
    assert view.box.next_stat.value.text() == "FLAG"
    assert "to the end" in view.box.next_stat.sub.text()

    view.update_state(DriverState(in_box=True, next_stint_laps=12))
    assert view.box.next_stat.value.text() == "12"
    assert "then box again" in view.box.next_stat.sub.text()


def test_no_plan_is_not_the_same_claim_as_running_to_the_flag(app):
    """Both reach the board as "no next stint", and only one of them means
    the race ends on this set."""
    view = DriverView()
    view.update_state(DriverState(in_box=True))
    assert view.box.next_stat.value.text() == "--"
    assert view.box.next_stat.sub.text() == "no plan"


# ------------------------------------------------------------------ the window

def test_the_window_never_takes_focus_from_the_game(app):
    """He is driving. A window that activates itself can steal a keypress from
    the PS5, and a stolen keypress in a race is worse than any display is
    good."""
    from PyQt6.QtCore import Qt

    window = DriverWindow()
    assert window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint


def test_geometry_round_trips(app):
    window = DriverWindow()
    window.setGeometry(40, 60, 900, 400)
    assert window.geometry_text() == "40,60,900,400"


@pytest.mark.parametrize("text", ["", None, "nonsense", "1,2,3", "1,2,10,10"])
def test_unusable_geometry_is_refused_rather_than_applied(app, text):
    """A board restored onto a display that has gone, or at ten pixels square,
    is one he can neither see nor find to drag back."""
    window = DriverWindow()
    assert window.restore_geometry(text) is False


def test_geometry_on_a_screen_that_is_not_here_is_refused(app):
    """This rig has three monitors and the one he can see is not the one
    Windows calls first. Qt will happily place a window entirely off every
    screen, and that board is gone."""
    window = DriverWindow()
    assert window.restore_geometry("99999,99999,800,400") is False


def test_geometry_on_a_screen_that_is_here_is_restored(app):
    available = QApplication.instance().primaryScreen().geometry()
    wanted = f"{available.x() + 10},{available.y() + 10},640,320"
    window = DriverWindow()
    assert window.restore_geometry(wanted) is True
    assert window.geometry_text() == wanted
