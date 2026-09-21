"""Which monitor our windows open on.

**21 Sep 2026: "I want the app to open on the wide screen not the main screen
and same with the board so it doesn't cover OBS."** Two monitors: a 1920x1080
primary at the origin with OBS on it, and a 2560x1080 ultrawide beside it at
x=1920. Qt opens a window on the primary, and the board's remembered spot was
`0,0,2480,1050` - beginning on the primary and running 560 px onto the
ultrawide, so it lay across the stream.

The rig that has the defect cannot run the suite: the offscreen platform has
exactly one 800x600 screen. So the rule is a pure function over screen
rectangles and these are the two real monitors, written down.
"""
from __future__ import annotations

import pytest

from pitcrew.ui.displays import Display, choose, holds


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])

# The rig as it is, measured 21 Sep 2026.
OBS = Display("PHL 271V8", 0, 0, 1920, 1080, primary=True)
WIDE = Display("LG ULTRAWIDE", 1920, 0, 2560, 1080)
RIG = (OBS, WIDE)

# The board's saved spot, which is the defect.
SAVED = (0, 0, 2480, 1050)


def test_nothing_chosen_opens_on_the_widest_not_the_primary():
    """The default has to be right with nothing typed in: he asked for this
    from the seat, not from the settings screen."""
    assert choose(RIG) == WIDE


def test_the_display_he_named_wins_even_where_it_is_the_narrower():
    """OBS may move. The setting is the answer, not a rule about primaries."""
    assert choose(RIG, "PHL 271V8") == OBS


def test_a_display_that_is_not_attached_falls_back_to_the_widest():
    """Not to the primary. A monitor unplugged since the setting was written
    must not quietly put the board back over the stream - which is the whole
    defect, arriving by a second route."""
    assert choose(RIG, "DELL U2415 - sold in August") == WIDE


def test_the_widest_is_chosen_over_an_equally_wide_primary():
    twin = Display("second 1920", 1920, 0, 1920, 1080)
    assert choose((OBS, twin)) == twin


def test_no_screens_at_all_is_none_rather_than_a_guess():
    assert choose(()) is None


def test_the_saved_spot_is_not_on_the_ultrawide():
    """`0,0,2480,1050`: 1920 of its 2480 columns are on the primary. It is a
    board on OBS that happens to touch the ultrawide."""
    assert holds(WIDE, SAVED) is False
    assert holds(OBS, SAVED) is True


def test_a_board_dragged_part_way_off_an_edge_is_still_on_that_screen():
    """He drags it deliberately past the bottom edge to reach the app behind
    it - his saved spot was y=237 with 212 px off-screen. A rule that wanted
    the whole rectangle would throw that spot away every race."""
    assert holds(WIDE, (1920 + 40, 237, 2480, 1050)) is True


def test_a_board_wholly_on_another_screen_is_refused():
    assert holds(WIDE, (10, 10, 800, 400)) is False


@pytest.mark.parametrize("rect", [(0, 0, 0, 400), (0, 0, 800, -1)])
def test_an_empty_rectangle_is_on_no_screen(rect):
    assert holds(WIDE, rect) is False


# ----------------------------------------------------- and through the app


def test_the_chosen_display_round_trips_through_the_store(store):
    from pitcrew import settings as settings_module

    saved = settings_module.Settings(preferred_display="LG ULTRAWIDE")
    settings_module.save(store, saved)
    assert settings_module.load(store).preferred_display == "LG ULTRAWIDE"


def test_the_default_is_empty_so_the_widest_rule_applies(store):
    from pitcrew import settings as settings_module

    assert settings_module.Settings().preferred_display == ""


def test_a_saved_spot_on_the_wrong_display_is_refused(app):
    """The board's own half of the fix. Mostly-off is refused even though it
    overlaps - the old rule asked only whether it touched any screen at all,
    and `0,0,2480,1050` touches both."""
    from PyQt6.QtWidgets import QApplication
    from pitcrew.ui.driver_view import DriverWindow

    primary = QApplication.instance().primaryScreen()
    area = primary.geometry()
    window = DriverWindow()
    # 100 px of 400 on the screen, 300 off it: it overlaps and is refused.
    mostly_off = f"{area.x() + area.width() - 100},{area.y() + 10},400,300"
    assert window.restore_geometry(mostly_off, display=primary.name()) is False


def test_a_saved_spot_on_the_chosen_display_is_kept(app):
    from PyQt6.QtWidgets import QApplication
    from pitcrew.ui.driver_view import DriverWindow

    primary = QApplication.instance().primaryScreen()
    area = primary.geometry()
    wanted = f"{area.x() + 10},{area.y() + 10},640,320"
    window = DriverWindow()
    assert window.restore_geometry(wanted, display=primary.name()) is True
    assert window.geometry_text() == wanted


def test_the_board_opens_on_the_chosen_display(app):
    """With no remembered spot at all, which is every first race on a rig."""
    from PyQt6.QtWidgets import QApplication
    from pitcrew.ui.driver_view import DriverWindow

    primary = QApplication.instance().primaryScreen()
    window = DriverWindow()
    window.resize(400, 300)
    window.move(-5000, -5000)
    window.open_on_display(primary.name())
    area = primary.availableGeometry()
    assert area.x() <= window.x() < area.x() + area.width()
    assert area.y() <= window.y() < area.y() + area.height()
