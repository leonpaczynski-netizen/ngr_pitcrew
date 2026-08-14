"""The window has to fit the screen it opens on.

The app asked for 1600x1000 unconditionally. One of this driver's three
displays is a 1280x800 desktop at 150% scaling, whose work area is 1280x752
once the taskbar is out — so the window opened 320 px wider and 248 px taller
than the screen could show, and everything past the edge was gone. The
practice rack made it unrecoverable by refusing a horizontal scrollbar, on the
stated grounds that its fixed columns "set the window's own minimum, so it can
never be given less than it needs anyway".
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.app import MIN_WINDOW, WINDOW, fit_to_screen


@dataclass
class _Rect:
    _w: int
    _h: int

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h


class _Screen:
    def __init__(self, w: int, h: int) -> None:
        self._rect = _Rect(w, h)

    def availableGeometry(self) -> _Rect:      # noqa: N802 - Qt naming
        return self._rect


class _Widget:
    def __init__(self, screen) -> None:
        self._screen = screen

    def screen(self):
        return self._screen


def test_a_big_desktop_gets_the_size_the_app_asked_for():
    fitted = fit_to_screen(_Widget(_Screen(2560, 1392)), *WINDOW)
    assert fitted == WINDOW


def test_the_small_panel_gets_a_window_that_fits_on_it():
    """1280x752 is the measured work area of the display this went wrong on."""
    width, height = fit_to_screen(_Widget(_Screen(1280, 752)), *WINDOW)
    assert width <= 1280
    assert height <= 752
    assert (width, height) < WINDOW


def test_a_screen_smaller_than_the_minimum_still_gets_the_minimum():
    """Better to overflow a screen nothing can fit on than to open unusably
    small — and the rack scrolls sideways now, so the overflow is reachable."""
    assert fit_to_screen(_Widget(_Screen(640, 400)), *WINDOW) == MIN_WINDOW


def test_no_screen_at_all_is_not_an_error():
    """Offscreen platforms and early construction both report None."""
    assert fit_to_screen(_Widget(None), *WINDOW) == WINDOW
