"""Regressions found by the design critique and the technical audit.

Each of these was a real defect on a screen the driver uses. They are grouped
by what went wrong rather than by file, because the same mistake appeared in
several places and the shape is what matters.
"""
from __future__ import annotations

import pytest

from pitcrew.ui import theme

from .test_controller import qt_app  # noqa: F401


def contrast(a: str, b: str) -> float:
    def lum(h):
        c = [int(h.lstrip('#')[i:i+2], 16) / 255 for i in (0, 2, 4)]
        c = [(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
             for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    high, low = max(lum(a), lum(b)), min(lum(a), lum(b))
    return (high + 0.05) / (low + 0.05)


# ------------------------------------------------------------------ contrast

def test_the_declared_ink_is_the_most_legible_register():
    """He reads it more than any other — every value he entered, on every
    screen. It used to be the third most legible of the four."""
    on_ground = contrast(theme.CRAYON, theme.RUBBER)
    assert on_ground > 10.0
    for other in (theme.DERIVED, theme.CHALK):
        assert on_ground > contrast(other, theme.RUBBER)


def test_the_declared_ink_is_far_from_the_warning_and_the_medium_band():
    """It sits beside both on the same row. The logo's own lime is 27-30
    degrees away, which is why this one was not sampled off it."""
    import colorsys

    def hue(h):
        r, g, b = [int(h.lstrip('#')[i:i+2], 16) / 255 for i in (0, 2, 4)]
        return colorsys.rgb_to_hsv(r, g, b)[0] * 360

    def gap(a, b):
        d = abs(hue(a) - hue(b))
        return min(d, 360 - d)

    assert gap(theme.CRAYON, theme.WARNING) > 35
    assert gap(theme.CRAYON, theme.COMPOUND_BANDS["RM"]) > 35


def test_struck_clears_the_body_floor():
    """It is every placeholder in the app and the dash of an unset field.
    Those are live state — "nothing entered" is a reading — not disabled
    controls, which is what WCAG exempts."""
    assert contrast(theme.STRUCK, theme.RUBBER_DEEP) >= 4.5


def test_the_rail_does_not_paint_words_in_a_border_token(qt_app):
    """TREAD_LIGHT on RUBBER_DEEP is 2.04:1 — worse than the STRUCK the
    design rejected for exactly this reason, on the surface used every visit.
    It escaped both existing guards: one checks six named inks and this was
    not among them, the other greps `pitcrew/ui/*.py` and the rail is in
    `app.py`."""
    import io
    from pathlib import Path

    source = Path("pitcrew/app.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        if "TREAD_LIGHT" in line and "StencilLabel" in line:
            pytest.fail(f"rail paints text in a border token: {line.strip()}")
    assert contrast(theme.TREAD_LIGHT, theme.RUBBER_DEEP) < 3.0, (
        "if this ever clears 3:1 the rule above can be relaxed")


# ------------------------------------------------------------- the registers

def test_a_ticked_checkbox_is_declared_not_measured():
    """A checkbox in this app is only ever the driver's own mark. Ticking one
    painted it STENCIL — the ink for something that came off the stream —
    while the indicator beside it correctly filled with crayon."""
    sheet = theme.STYLESHEET
    checked = [line for line in sheet.splitlines()
               if line.strip().startswith("QCheckBox:checked")]
    assert checked, "the rule should still exist"
    assert theme.CRAYON in checked[0]


def test_mono_is_not_the_default_face_for_every_editor():
    """The ban list closes on "monospace anywhere it is not measurement", and
    the theme put Cascadia on every editor — the event name, the notes, and
    the driver's own words, which its own label calls the most valuable field
    on the screen."""
    sheet = theme.STYLESHEET
    block = sheet.split("QLineEdit, QPlainTextEdit, QComboBox")[1].split("}")[0]
    assert theme.DATA_FAMILY not in block
    assert theme.STENCIL_FAMILY in block


def test_a_field_holding_a_number_still_gets_the_mono_face(qt_app):
    from PyQt6.QtWidgets import QDoubleSpinBox, QLineEdit
    from pitcrew.ui.widgets import Field

    Field("Ride height", QDoubleSpinBox())
    assert Field("Ride height", QDoubleSpinBox()).findChild(
        QDoubleSpinBox).property("data") == "true"
    assert Field("Event name", QLineEdit()).findChild(
        QLineEdit).property("data") == "false"


# ------------------------------------------------------------- the sentinels

def test_no_event_field_renders_the_empty_sentinel_as_a_number(qt_app):
    """`EMPTY` is -9999. Three spin boxes never called setSpecialValueText,
    so they read "-9999" on the screen whose whole claim is that a setting
    nobody entered never reads as a number."""
    from pitcrew.ui.event_screen import EventScreen

    screen = EventScreen()
    for name in ("extra_time", "start_hour", "time_multiplier", "pp_cap"):
        assert "9999" not in getattr(screen, name).text(), name


# --------------------------------------------------------------- the layout

def test_every_screen_fits_the_smallest_display_he_owns(qt_app):
    """1280x800 at 150% reports 853x501 logical, less the 178px rail."""
    from pitcrew.settings import Settings
    from pitcrew.ui.car_screen import CarScreen
    from pitcrew.ui.engineer_screen import EngineerScreen
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen
    from pitcrew.ui.race_screen import RaceScreen
    from pitcrew.ui.reference_screen import ReferenceScreen
    from pitcrew.ui.settings_screen import SettingsScreen
    from pitcrew.ui.strategy_screen import StrategyScreen

    settings = SettingsScreen()
    settings.load(Settings())
    for screen in (EventScreen(), CarScreen(), PracticeScreen(),
                   StrategyScreen(), RaceScreen(), EngineerScreen(),
                   ReferenceScreen(), settings):
        height = screen.minimumSizeHint().height()
        assert height <= 501, (
            f"{type(screen).__name__} demands {height}px of height; the "
            f"smallest display gives 501 and its own controls go off the "
            f"bottom with no bar to reach them")


def test_the_window_never_opens_bigger_than_the_screen():
    from pitcrew.app import fit_to_screen

    class _Rect:
        def __init__(self, w, h):
            self._w, self._h = w, h

        def width(self):
            return self._w

        def height(self):
            return self._h

    class _Screen:
        def __init__(self, w, h):
            self._r = _Rect(w, h)

        def availableGeometry(self):    # noqa: N802 - Qt naming
            return self._r

    class _Widget:
        def __init__(self, s):
            self._s = s

        def screen(self):
            return self._s

    for w, h in ((853, 501), (1280, 752), (2560, 1392)):
        fw, fh = fit_to_screen(_Widget(_Screen(w, h)), 1600, 1000)
        assert fw <= w and fh <= h, f"{fw}x{fh} does not fit {w}x{h}"
