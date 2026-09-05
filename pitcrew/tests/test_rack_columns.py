"""Column heads fit their columns, and a label is drawn at the size it asks for.

The driver reported one word losing a letter: "WEAR AT EN". The head needs
73px at the 10px it asks for and had 92, so the column was never too narrow —
**it was not being drawn at 10px.** `theme.apply` sets
`QWidget { font-size: 15px }`, a style-sheet rule beats `setFont`, and nothing
in `StencilLabel` restated it, so every stencilled label in the app rendered
at 15px whatever it asked for. Measured before the fix: `StencilLabel` at
size 10, 15 and 20 all painted 111px wide and 15px tall.

That is the third instance of this cascade and they are all one shape — a
style-sheet rule silently beating a per-widget setting. `QWidget { color }`
beat `QPalette.Text` and made every declared value render as a measured one.
`QWidget { font-size }` beat `setFont` here and in `Measured`.

**The first test below needs no fonts and is the one that matters**; it fails
on the bug itself rather than on its symptom. The width checks need the real
faces, and skip where they are absent rather than measuring a fallback and
reporting the answer as though it were about Bahnschrift.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFontDatabase, QFontMetrics          # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

from pitcrew.ui import practice_screen as ps                 # noqa: E402
from pitcrew.ui import theme                                 # noqa: E402
from pitcrew.ui.widgets import Measured, StencilLabel        # noqa: E402


@pytest.fixture(scope="module")
def app():
    made = QApplication.instance() or QApplication([])
    theme.apply(made)
    return made


def _needs(family: str):
    if family not in QFontDatabase.families():
        pytest.skip(
            f"{family} is not installed here. A width measured against a "
            f"fallback face is a measurement of the wrong typeface, and "
            f"padding a column to satisfy it would be the wrong fix.")


# The head text against the width constant the rows use for the same column.
# Data rather than read off the widget, so a column added to the rows and
# forgotten in the heads still fails here.
COLUMNS = (
    ("LAP", "W_LAP"), ("TIME", "W_TIME"), ("DELTA", "W_DELTA"),
    ("S1", "W_SECTOR"), ("S2", "W_SECTOR"), ("S3", "W_SECTOR"),
    ("USED", "W_FUEL"), ("ON BOARD", "W_TANK"),
    ("COMPOUND", "W_COMPOUND"), ("FRESH SET", "W_SET_ON"),
    ("WEAR AT END", "W_WEAR"),
)


# ------------------------------------------------- the cause, font-independent

def test_a_stencil_label_is_drawn_at_the_size_it_asks_for(app):
    """**The bug itself.** Needs no particular font: whatever face is in use,
    three different sizes must not paint as one."""
    heights = {size: StencilLabel("WEAR AT END", size=size,
                                  tracking=14.0).sizeHint().height()
               for size in (10, 15, 20)}
    assert len(set(heights.values())) == 3, (
        f"the size argument is being ignored - heights {heights}. A "
        f"style-sheet font-size beats setFont; restate it in the rule that "
        f"wins.")
    assert heights[10] < heights[15] < heights[20]


def test_a_measured_label_is_drawn_at_the_size_it_asks_for(app):
    """The same cascade, and the one that surfaced it: a 78px pit-board
    reading rendered at 15px."""
    heights = {size: Measured("3", size=size).sizeHint().height()
               for size in (15, 23, 60)}
    assert len(set(heights.values())) == 3, f"sizes collapsed: {heights}"


def test_re_inking_a_label_does_not_drop_its_size(app):
    """The rack re-inks whole rows. A raw `setStyleSheet` that restated only
    the colour is what dropped the size in the first place."""
    label = StencilLabel("WEAR AT END", size=10, tracking=14.0)
    before = label.sizeHint().height()
    label.set_ink(theme.WARNING)
    assert label.sizeHint().height() == before


# ------------------------------------------------ the symptom, needs the fonts

def test_no_column_head_is_clipped(app):
    _needs(theme.STENCIL_FAMILY)
    metrics = QFontMetrics(theme.stencil_font(10, tracking=14.0))
    short = [f"{text!r} needs {metrics.horizontalAdvance(text)}px, "
             f"{const} is {getattr(ps, const)}px"
             for text, const in COLUMNS
             if metrics.horizontalAdvance(text) > getattr(ps, const)]
    assert not short, "column heads clip: " + "; ".join(short)


def test_the_heads_on_screen_are_the_ones_measured(app):
    """The table above is only worth having if it is the real set."""
    screen = ps.PracticeScreen()
    on_screen = {w.text() for w in screen.head_view.widget()
                 .findChildren(StencilLabel) if w.text()}
    assert {text for text, _ in COLUMNS} <= on_screen, (
        "a head was renamed on the screen and not in this test's table")


def test_the_wear_cell_fits_a_fully_worn_corner(app):
    """100% is the cliff - the reading on this column that decides whether a
    stint can be finished - so it is the one that must not lose a character."""
    _needs(theme.DATA_FAMILY)
    widest = QFontMetrics(theme.data_font(13)).horizontalAdvance("RR 100%")
    assert widest + 16 <= ps.W_WEAR, (
        f"a fully worn corner needs {widest + 16}px including the button's "
        f"border, the column is {ps.W_WEAR}px")


def test_a_full_tank_fits_its_column(app):
    _needs(theme.DATA_FAMILY)
    metrics = QFontMetrics(theme.data_font(theme.DATA_PX))
    assert metrics.horizontalAdvance("100.0 L") <= ps.W_TANK
