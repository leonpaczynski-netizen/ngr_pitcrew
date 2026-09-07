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


# ------------------------------------------- every dash carries its reason

def test_no_fill_rate_says_so_rather_than_showing_a_bare_dash(app):
    """The one figure he is holding the trigger on was the only one on the
    panel with an empty caption under its dash."""
    view = DriverView()
    view.update_state(DriverState(in_box=True, fuel_target_l=74.0))
    assert view.box.release_stat.value.text() == "--"
    assert "no fill rate" in view.box.release_stat.sub.text()


def test_the_fill_rate_source_is_printed_beside_the_target(app):
    """A rate measured at this pump and one typed on the event page are not
    the same claim, and the countdown is only as good as whichever it used."""
    view = DriverView()
    view.update_state(DriverState(in_box=True, fuel_target_l=74.0, fuel_l=31.0,
                                  release_in_s=43.0,
                                  fill_rate_note="declared rate"))
    assert "declared" in view.box.fuel_stat.sub.text()


def test_a_plan_that_names_no_compound_is_not_no_plan_at_all(app):
    """`next_compound` is None after a mid-race replan that names none, which
    is an honest state - and the board used to report it as having no plan."""
    view = DriverView()
    view.update_state(DriverState(in_box=True, has_plan=True))
    assert "no compound" in view.box.tyre_stat.sub.text()
    view.update_state(DriverState(in_box=True, has_plan=False))
    assert view.box.tyre_stat.sub.text() == "no plan"


def test_running_off_the_end_of_the_plan_is_not_no_plan_and_not_the_flag(app):
    view = DriverView()
    view.update_state(DriverState(in_box=True, has_plan=True,
                                  past_the_plan=True))
    assert view.box.next_stat.value.text() == "--"
    assert "past the plan" in view.box.next_stat.sub.text()


def test_a_planned_stint_with_no_stated_length_is_not_past_the_plan(app):
    """Three outcomes, not two: no plan, a plan that does not reach this
    stint, and a plan that reaches it but states no length. They shared one
    caption, so a stint squarely inside the plan read as being past its end."""
    view = DriverView()
    view.update_state(DriverState(in_box=True, has_plan=True))
    assert "plan: no length" in view.box.next_stat.sub.text()


def test_the_rejoin_caption_does_not_read_as_a_duration(app):
    """`out in P7` collides a duration caption with a position value, and
    "release in" directly above it genuinely is a duration."""
    view = DriverView()
    assert "in" not in view.box.out_stat.caption.text().lower().split()


# ------------------------------------------------------- overdue on track

def test_being_past_the_box_lap_says_so_instead_of_counting_zero(app):
    """`laps_to_stop()` clamps at zero, so three laps late read "0 laps to
    box, box on lap 15" - the current lap, every lap, with nothing saying he
    was overdue."""
    view = DriverView()
    view.update_state(DriverState(laps_to_box=0.0, box_on_lap=15,
                                  laps_past_box=3))
    assert view.box_stat.value.text() == "NOW"
    assert "3 past the box lap" in view.box_stat.sub.text()


def test_the_box_lap_itself_is_due_rather_than_late(app):
    """`past_box_lap` is true from `lap >= stint_ends_on_lap`, so it fires on
    the box lap itself - where the stop is due, not missed. `NOW` is right
    either way; the reason underneath it is not."""
    view = DriverView()
    view.update_state(DriverState(laps_to_box=0.0, box_on_lap=15,
                                  laps_past_box=0))
    assert view.box_stat.value.text() == "NOW"
    assert view.box_stat.sub.text() == "box this lap"


def test_after_the_flag_it_does_not_say_there_is_no_plan(app):
    """`laps_to_box` is None once the race is over, which it also is when no
    plan exists - and "no plan" is the wrong thing to tell a man who has just
    finished."""
    view = DriverView()
    view.update_state(DriverState(finished=True))
    assert view.box_stat.value.text() == "FLAG"
    assert "over" in view.box_stat.sub.text()


def test_a_stop_still_ahead_counts_down_normally(app):
    view = DriverView()
    view.update_state(DriverState(laps_to_box=3.0, box_on_lap=15))
    assert view.box_stat.value.text() == "3"


# ------------------------------------------------------------- getting rid of it

def test_escape_closes_the_board_without_stopping_the_race(app):
    """A frameless window has no close button, and the only other way off the
    screen was to stop the race - which is not a thing to do because a display
    is in the way."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent

    window = DriverWindow()
    window.show()
    window.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                  Qt.KeyboardModifier.NoModifier))
    assert not window.isVisible()


# ------------------------------------------------- the two neighbours

def test_the_gap_is_the_big_number_and_the_trend_is_the_caption(app):
    """The gap is what he can act on now - a car 1.2 s up is reachable and one
    12 s up is not - and the trend says whether acting is worth it."""
    from pitcrew.ui.driver_view import GapView

    view = DriverView()
    view.update_state(DriverState(
        ahead=GapView(1.8, "catching 0.4 s a lap - Rocky")))
    assert view.ahead_stat.value.text() == "1.8"
    assert "catching" in view.ahead_stat.sub.text()


def test_an_unread_gap_says_why_rather_than_sitting_blank(app):
    """The expected state: these come off the game's own gap boxes, which have
    never once returned a number in a real race."""
    view = DriverView()
    view.update_state(DriverState())
    assert view.ahead_stat.value.text() == "--"
    assert "no gap read" in view.ahead_stat.sub.text()
    assert view.behind_stat.value.text() == "--"


def test_the_two_sides_are_never_given_the_same_words(app):
    """**The rule-13 trap `race/gaps.py` names.** One signed rate means
    opposite things on the two sides - ahead it is us catching him, behind it
    is him catching us - and they demand opposite driving. No signed number
    reaches this screen; each side gets a sentence only true of that side."""
    from pitcrew.ui.driver_view import GapView

    view = DriverView()
    view.update_state(DriverState(
        ahead=GapView(1.8, "catching 0.4 s a lap"),
        behind=GapView(1.8, "he is catching 0.4 s a lap", urgent=True)))
    assert view.ahead_stat.sub.text() != view.behind_stat.sub.text()
