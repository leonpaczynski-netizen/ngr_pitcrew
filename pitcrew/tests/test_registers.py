"""The three registers, asserted against rendered pixels.

DESIGN.md's thesis is that measured, declared and derived never look alike.
It was false for the whole life of the app and every test passed, because no
test looked at a pixel: `QWidget { color: STENCIL }` in the stylesheet matched
every editor subclass and beat `QPalette.Text = CRAYON`, so a range the driver
typed rendered in the ink that means "came off the telemetry stream".

A style rule cannot be checked by reading the style rule - Qt's cascade
decides, and the cascade is the thing that was wrong. So these tests paint the
widget and read the colour back out.
"""
from __future__ import annotations

import collections

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt                                    # noqa: E402
from PyQt6.QtGui import QImage                                 # noqa: E402
from PyQt6.QtWidgets import (                                  # noqa: E402
    QApplication,
    QLayout,
    QLineEdit,
)

from pitcrew.ui import theme                                   # noqa: E402
from pitcrew.ui.widgets import (                               # noqa: E402
    Declared,
    Derived,
    Measured,
    SpecLine,
)


@pytest.fixture(scope="module")
def qt_app():
    """The real platform, not offscreen.

    Offscreen Qt has none of Bahnschrift, Bahnschrift Condensed, Cascadia Mono
    or Consolas, so text metrics inflate and layout assertions go false. It
    renders ink correctly, but the app is only ever measured natively and these
    tests should match.
    """
    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


# The four inks a value can legitimately be painted in. Rendered text lands a
# channel or two off the authored value - antialiasing and gamma - so a test
# that demanded an exact hex would fail on a hue it got right. The question
# these tests ask is "which register is this", so the answer is snapped to the
# nearest one, and a colour that is near none of them fails loudly.
REGISTERS = {
    "measured": theme.STENCIL,
    "declared": theme.CRAYON,
    "derived": theme.DERIVED,
    "struck": theme.STRUCK,
}
# Comfortably tighter than the gap between any two registers - the closest
# pair is ~90 units apart in this metric.
INK_TOLERANCE = 12


def nearest_register(rendered: str) -> str:
    """Which register a painted colour belongs to."""
    if rendered == "none":
        return "none"
    got = [int(rendered[i:i + 2], 16) for i in (1, 3, 5)]
    best, distance = None, None
    for name, value in REGISTERS.items():
        want = [int(value[i:i + 2], 16) for i in (1, 3, 5)]
        apart = sum(abs(a - b) for a, b in zip(got, want))
        if distance is None or apart < distance:
            best, distance = name, apart
    return best if distance <= INK_TOLERANCE else f"unknown ({rendered})"


def _fonts_are_real() -> bool:
    """Whether this Qt platform actually has the faces the app is drawn in.

    Offscreen has none of them, so text metrics inflate and any assertion
    about position or size is measuring the platform rather than the app.
    """
    from PyQt6.QtGui import QFont

    return all(QFont(family).exactMatch() for family in
               (theme.STENCIL_FAMILY, theme.STENCIL_CONDENSED,
                theme.DATA_FAMILY))


def ink_of(widget) -> str:
    """The strongest text colour the widget actually paints, as #RRGGBB."""
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    QApplication.processEvents()
    pixmap = widget.grab()
    image: QImage = pixmap.toImage()

    every: collections.Counter = collections.Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            every[(colour.red(), colour.green(), colour.blue())] += 1
    ground = every.most_common(1)[0][0]

    counts = collections.Counter(
        {rgb: n for rgb, n in every.items()
         if sum(rgb) > 250 and rgb != ground})
    if not counts:
        return "none"

    # **The pixels vote for a register; the fringes abstain.**
    #
    # ClearType renders each glyph across the three subpixels, so a stroke is
    # a core of the authored colour with coloured fringes either side - and
    # the fringes are numerous. Measured on the Race Engineer's `worst` combo,
    # a 611 px widget: the authored `#807870` appears 114 times and the fringe
    # `#4C6870` 116. The plain mode lost by two pixels, and which one wins is
    # a function of how long the string happens to be - the six shorter combos
    # beside it passed. Taking the colour furthest from the ground fails the
    # other way: subpixel rendering OVERSHOOTS as well, and `#EBEBD8` beat the
    # stencil `#E8E4DC` it was a fringe of.
    #
    # So the estimator asks the question the test asks. A fringe is a blend
    # and lands near none of the four registers; a glyph's core lands on one.
    # Counting only the pixels that are within tolerance of a register makes
    # the answer the register the widget actually painted, and leaves a colour
    # near none of them - the real failure this file is for - to fall through
    # and be reported with its value.
    def near_a_register(rgb: tuple[int, int, int]) -> bool:
        return any(sum(abs(a - int(value[i:i + 2], 16))
                       for a, i in zip(rgb, (1, 3, 5))) <= INK_TOLERANCE
                   for value in REGISTERS.values())

    voting = collections.Counter({rgb: n for rgb, n in counts.items()
                                  if near_a_register(rgb)})
    red, green, blue = (voting or counts).most_common(1)[0][0]
    return f"#{red:02X}{green:02X}{blue:02X}"


def test_a_value_the_driver_typed_renders_in_crayon(qt_app):
    """The failure this file exists for. An editor must not paint stencil."""
    editor = QLineEdit()
    editor.setText("Round 4 - Fuji")
    editor.resize(280, 34)
    assert nearest_register(ink_of(editor)) == "declared"


def test_an_empty_editor_renders_its_placeholder_struck(qt_app):
    """And the fix must not have cost the placeholder rule.

    A placeholder in crayon reads as a value the driver declared, which is the
    mirror image of the bug being fixed here.
    """
    editor = QLineEdit()
    editor.setPlaceholderText("Round 4 - Fuji")
    editor.resize(280, 34)
    assert nearest_register(ink_of(editor)) == "struck"


def test_the_three_registers_are_three_different_inks(qt_app):
    assert nearest_register(ink_of(Measured("1:33.912"))) == "measured"
    assert nearest_register(ink_of(Declared("1:33.912"))) == "declared"
    assert nearest_register(ink_of(Derived("1:33.912"))) == "derived"


def test_the_same_number_reads_differently_by_provenance(qt_app):
    """The whole point: identical text, three claims, three inks."""
    registers = {nearest_register(ink_of(cls("11")))
                 for cls in (Measured, Declared, Derived)}
    assert registers == {"measured", "declared", "derived"}


def test_a_spec_line_carries_provenance_per_entry(qt_app):
    """SpecLine is where a measured, a declared and a derived figure sit on
    one line - so it is where a collapsed register would be least visible."""
    line = SpecLine()
    line.add("Best", "1:33.912")                    # off the stream
    line.add("Wear", "55%", declared=True)          # off the in-game gauge
    line.add("Box in", "3", derived=True)           # the model's call
    line.finish()

    kinds = [type(reading).__name__ for _label, reading in line._entries]
    assert kinds == ["Measured", "Declared", "Derived"]
    assert {w.styleSheet().split("color:")[1].split(";")[0].strip()
            for _l, w in line._entries} == {theme.STENCIL, theme.CRAYON,
                                            theme.DERIVED}


def test_an_event_with_no_stop_costs_entered_paints_them_struck(qt_app):
    """Refuel rate and pit loss shipped holding 2.5 and 20.0 in crayon, so the
    evidence column swore he had entered two app defaults. Pit loss sets what
    a stop costs and refuel rate sets the stop count."""
    from pitcrew.ui.event_screen import EventScreen

    screen = EventScreen()
    for box in (screen.refuel_rate, screen.pit_loss):
        assert nearest_register(ink_of(box.lineEdit())) == "struck"
    assert screen.values()["refuel_rate_lps"] is None
    assert screen.values()["pit_loss_secs"] is None

    screen.pit_loss.setValue(18.5)
    assert nearest_register(ink_of(screen.pit_loss.lineEdit())) == "declared"
    assert screen.values()["pit_loss_secs"] == 18.5


def test_laps_of_fuel_is_not_painted_as_a_measurement(qt_app):
    """`fuel_l / fuel_per_lap_l`, where the rate is the *planned* burn until
    three laps are in. The pit board carries a model output and a stream
    reading side by side, at 56px, on the surface read at racing speed - so
    which is which cannot be left to the reader."""
    from pitcrew.ui import theme
    from pitcrew.ui.race_screen import RaceScreen

    screen = RaceScreen()
    screen.show_snapshot({"lap": 12, "lapsTotal": 30, "lapsOfFuel": 8.3,
                          "lapsToStop": 3, "nextCompound": "RM"})
    for reading in (screen.fuel_left, screen.box_in):
        assert theme.DERIVED in reading.value.styleSheet(),             f"{reading.name.text()} claims to be measured"
    for reading in (screen.lap_now, screen.position):
        assert theme.DERIVED not in reading.value.styleSheet()


def test_a_missing_board_figure_is_struck_and_never_a_zero(qt_app):
    """A `0` box-in reads as *box now*, which is the most expensive
    misreading available on this screen. Absent is absent."""
    from pitcrew.ui import theme
    from pitcrew.ui.race_screen import RaceScreen

    screen = RaceScreen()
    screen.show_snapshot({"lap": 4})
    assert screen.box_in.value.text() == "—"
    assert theme.STRUCK in screen.box_in.value.styleSheet()
    assert screen.fuel_left.value.text() == "—"


def test_an_overdue_stop_says_overdue_rather_than_zero(qt_app):
    """CLAUDE.md rule 9 on the highest-consequence number the app emits: it
    was `max(0, to_stop)`, so a plan he was two laps past reported as `0` -
    'box now', which is a different instruction from 'you are two laps
    late'."""
    from pitcrew.ui.race_screen import RaceScreen

    screen = RaceScreen()
    screen.show_snapshot({"lap": 15, "lapsToStop": -2})
    assert "2" in screen.box_in.value.text()
    assert screen.box_in.value.text() != "0"
    assert "OVERDUE" in screen.box_in.name.text().upper()


def test_the_fresh_set_picker_fits_its_longest_state(qt_app):
    """`W_SET_ON` was 118 with a 74px edit field against an 84px "Carried
    over", so the picker rendered "Carried o..." - the truncation its own
    comment claimed it prevented, on the control that decides whether the wear
    rate is measured or assumed."""
    from PyQt6.QtWidgets import QStyle, QStyleOptionComboBox

    from pitcrew.ui.practice_screen import SET_CARRIED, LapRow, RackRow

    if not _fonts_are_real():
        pytest.skip("this platform resolves none of the app's faces, so every "
                    "text metric taken off it is measuring the platform")

    row = RackRow(LapRow(1, 1, 94_000, 3.4, compound="RM"), 94_000,
                  run_start=True)
    combo = row.set_picker
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    field = combo.style().subControlRect(
        QStyle.ComplexControl.CC_ComboBox, option,
        QStyle.SubControl.SC_ComboBoxEditField, combo)
    assert combo.fontMetrics().elidedText(
        SET_CARRIED, Qt.TextElideMode.ElideRight, field.width()) == SET_CARRIED


def test_derived_is_not_struck(qt_app):
    """It used to be. Struck means "removed from the count", so a modelled
    stint length wore the ink for something that does not count."""
    assert theme.DERIVED != theme.STRUCK
    assert nearest_register(ink_of(Derived("11"))) == "derived"


def test_the_stylesheet_sets_no_colour_on_qwidget():
    """Guards the mechanism, not just the symptom.

    A `color` on the QWidget rule matches every subclass and beats the
    palette, which is exactly how declared and measured collapsed into one
    ink. The rendering tests above catch it too, but this names the cause.
    """
    block = theme.STYLESHEET.split("QWidget {", 1)[1].split("}", 1)[0]
    assert "color:" not in block, (
        "a colour on the QWidget rule paints every editor, so a value the "
        "driver typed renders as one that came off the stream")


def test_every_register_ink_is_legible_on_every_ground():
    """Provenance carried in colour is worth nothing if the colour cannot be
    read from the driving position with a headset just pushed up."""
    def luminance(value: str) -> float:
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                    for c in channels]
        return (0.2126 * channels[0] + 0.7152 * channels[1]
                + 0.0722 * channels[2])

    def contrast(one: str, two: str) -> float:
        first, second = luminance(one), luminance(two)
        high, low = max(first, second), min(first, second)
        return (high + 0.05) / (low + 0.05)

    grounds = (theme.RUBBER, theme.RUBBER_DEEP, theme.SHOULDER)
    for ink in (theme.STENCIL, theme.CRAYON, theme.DERIVED):
        for ground in grounds:
            ratio = contrast(ink, ground)
            assert ratio >= 4.5, (
                f"{ink} on {ground} is {ratio:.2f}:1, below the 4.5:1 floor "
                f"for the size this app sets values at")


def test_a_spin_box_shows_entered_and_unentered_in_different_inks(qt_app):
    """The sentinel dash must read as absent, not as declared.

    Caught only by sampling a fully built window: the spin box's palette said
    crayon while its internal line edit kept a resolved copy at struck, so
    every entered setup value rendered as if nobody had entered it. Setting
    the parent palette is not enough, and neither is testing the parent.
    """
    from PyQt6.QtWidgets import QDoubleSpinBox

    from pitcrew.ui.widgets import struck_when_empty

    def spin(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-9999.0, 9999.0)
        box.setSpecialValueText("—")
        box.setValue(-9999.0)
        struck_when_empty(box)
        box.setValue(value)
        box.resize(160, 34)
        return box

    assert nearest_register(ink_of(spin(62.0))) == "declared"
    assert nearest_register(ink_of(spin(-9999.0))) == "struck"


def test_the_line_edit_inside_a_spin_box_carries_the_ink(qt_app):
    """Names the mechanism, so a future refactor cannot quietly undo it."""
    from PyQt6.QtWidgets import QDoubleSpinBox

    from pitcrew.ui.widgets import struck_when_empty

    box = QDoubleSpinBox()
    box.setRange(-9999.0, 9999.0)
    box.setSpecialValueText("—")
    box.setValue(-9999.0)
    struck_when_empty(box)
    box.setValue(62.0)

    role = box.palette().ColorRole
    assert box.lineEdit().palette().color(role.Text).name().upper() == \
        theme.CRAYON.upper()


# --------------------------------------------------------------- contrast
#
# This app is read on an upper monitor at the rig with a VR headset just
# pushed up, and PRODUCT.md commits to high contrast for that reason. The
# numbers below are the floor, not an aspiration.

def _contrast(one: str, two: str) -> float:
    from PyQt6.QtGui import QColor

    return theme.contrast_ratio(QColor(one), QColor(two))


GROUNDS = ("RUBBER", "RUBBER_DEEP", "SHOULDER")


def test_every_ink_that_carries_words_clears_the_body_floor():
    """4.5:1 for text this size. `STRUCK` used to carry every hint, unit and
    column header at 2.93:1 - the ink whose own meaning is "removed from the
    count", doing duty as the app's instructional colour."""
    for name in ("STENCIL", "STENCIL_DIM", "CRAYON", "DERIVED", "CHALK",
                 "WARNING"):
        ink = getattr(theme, name)
        for ground in GROUNDS:
            ratio = _contrast(ink, getattr(theme, ground))
            assert ratio >= 4.5, f"{name} on {ground} is {ratio:.2f}:1"


def test_struck_is_only_used_where_low_contrast_is_the_point():
    """It stays low on purpose - placeholders, disabled controls, the empty
    sentinel, the strike line. Those are inactive or absent, which is exactly
    what WCAG exempts and what the ink means. So this asserts the boundary
    rather than the ratio: no screen may paint prose with it."""
    import pathlib

    offenders = []
    for path in pathlib.Path("pitcrew/ui").glob("*.py"):
        if path.name in ("theme.py", "widgets.py", "preview.py"):
            continue
        text = path.read_text(encoding="utf-8")
        if "theme.STRUCK" in text:
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} paint with STRUCK. It means 'removed from the count'; "
        f"instructional prose belongs in STENCIL_DIM")


def test_every_compound_code_is_legible_on_its_own_band():
    """Colour is never the only channel - so the code carrying the
    classification has to be readable, or the band is colour-only after all."""
    from PyQt6.QtGui import QColor

    for code, value in theme.COMPOUND_BANDS.items():
        ratio = theme.contrast_ratio(theme.band_ink(code), QColor(value))
        # The code is set as large text (19px DemiBold), where the floor is
        # 3:1. Four of the racing colours cannot reach 4.5:1 against either
        # ink without repainting colours that are the sport's, not ours.
        assert ratio >= 3.0, f"{code} code is {ratio:.2f}:1 on its own band"


def test_band_ink_picks_the_better_of_the_two_inks():
    """Measured, not thresholded. The NTSC-brightness version put warm white
    on Intermediate green at 2.53:1."""
    from PyQt6.QtGui import QColor

    for code, value in theme.COMPOUND_BANDS.items():
        band = QColor(value)
        chosen = theme.band_ink(code)
        other = (QColor(theme.STENCIL) if chosen.name().upper()
                 == theme.RUBBER.upper() else QColor(theme.RUBBER))
        assert theme.contrast_ratio(chosen, band) >= \
            theme.contrast_ratio(other, band), f"{code} picked the worse ink"


def test_a_painted_band_actually_draws_its_code(qt_app):
    """The gap that shipped a P1.

    Both tests above call `theme.band_ink` directly, and nothing in the suite
    ever painted a band - so when `paintEvent` was changed to call a function
    nobody had written, every test still passed while the two-letter code was
    silently absent from every band and chip in the app. A raising paintEvent
    is not a crash under the app's own excepthook; it is a blank band and a
    CRITICAL traceback per repaint. Only a pixel catches it.
    """
    from PyQt6.QtGui import QColor

    from pitcrew.ui.widgets import CompoundBand, _desaturate

    for code, value in theme.COMPOUND_BANDS.items():
        for struck in (False, True):
            band = CompoundBand(code, animate=False)
            band.setStruck(struck)
            band.resize(CompoundBand.WIDTH, 34)
            band.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            band.show()
            QApplication.processEvents()
            image: QImage = band.grab().toImage()

            painted = _desaturate(QColor(value)) if struck else QColor(value)
            ink = theme.band_ink_for(painted)
            on_ink = sum(
                1
                for y in range(image.height())
                for x in range(image.width())
                if theme.contrast_ratio(image.pixelColor(x, y), painted) >= 3.0
                and theme.contrast_ratio(image.pixelColor(x, y), ink) < 1.4)
            assert on_ink > 20, (
                f"{code} band ({'struck' if struck else 'plain'}) painted no "
                f"legible code - colour is the only channel left")


# ------------------------------------------------------- keyboard and empties

def test_the_nav_rail_is_reachable_without_a_mouse(qt_app):
    """It was eight labels with mousePressEvent reassigned onto them: zero
    focusable, no key handled, while all 355 controls inside the screens were
    focusable. The gap was the one thing used on every visit."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QStackedWidget, QWidget

    from pitcrew.app import NAV_GROUPS, SCREENS, NavRail

    stack = QStackedWidget()
    for _ in range(len(SCREENS)):
        stack.addWidget(QWidget())
    rail = NavRail(stack, NAV_GROUPS)

    assert len(rail._labels) == len(SCREENS)
    for item in rail._labels:
        assert item.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert item.accessibleName()


def test_enter_on_a_focused_rail_item_selects_its_screen(qt_app):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QStackedWidget, QWidget

    from pitcrew.app import NAV_GROUPS, SCREENS, NavRail

    stack = QStackedWidget()
    for _ in range(len(SCREENS)):
        stack.addWidget(QWidget())
    rail = NavRail(stack, NAV_GROUPS)

    rail._labels[4].keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return.value,
                  Qt.KeyboardModifier.NoModifier))
    assert stack.currentIndex() == 4


def test_the_rail_wraps_at_both_ends(qt_app):
    """Qt only grants focus inside a shown widget, so the rail is realised
    off-screen rather than the assertion weakened."""
    from PyQt6.QtWidgets import QStackedWidget, QWidget

    from pitcrew.app import NAV_GROUPS, SCREENS, NavRail

    stack = QStackedWidget()
    for _ in range(len(SCREENS)):
        stack.addWidget(QWidget())
    rail = NavRail(stack, NAV_GROUPS)
    rail.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    rail.show()
    QApplication.processEvents()

    rail.focus_item(-1)
    assert rail.focusWidget() is rail._labels[len(SCREENS) - 1]
    rail.focus_item(len(SCREENS))
    assert rail.focusWidget() is rail._labels[0]
    rail.focus_item(3)
    assert rail.focusWidget() is rail._labels[3]


def test_checkboxes_have_a_visible_focus_style():
    """The stylesheet restyles the indicator, which suppresses Qt's own focus
    rect. The Engineer screen has 28 focusable checkboxes and nothing showed
    which one had focus."""
    assert "QCheckBox::indicator:focus" in theme.STYLESHEET


def test_a_plate_with_nothing_in_it_says_what_would_fill_it(qt_app):
    """Strategy and Race rested as about a million pixels of bordered nothing
    with the only explanation outside the plate."""
    from pitcrew.ui.race_screen import RaceScreen
    from pitcrew.ui.strategy_screen import StrategyScreen

    strategy = StrategyScreen()
    assert strategy.plan_empty.isVisibleTo(strategy)
    assert strategy.evidence_empty.isVisibleTo(strategy)

    race = RaceScreen()
    assert race.log_empty.isVisibleTo(race)


def test_the_empty_state_returns_when_a_rebuild_finds_nothing(qt_app):
    """A second build that produces no plans must say so again, not leave a
    blank plate - so it is detached on clear, never destroyed."""
    from pitcrew.ui.strategy_screen import StrategyScreen

    screen = StrategyScreen()
    screen.show_plans([], [])
    assert screen.plan_empty.isVisibleTo(screen)
    assert screen.approve_button.isEnabled() is False


# --------------------------------------------------- layout and dead controls

def test_discard_is_connected_to_something(qt_app):
    """It was constructed, laid out, and wired to nothing for the life of the
    screen - the one control in the app that did not do what it said.

    It is guarded now, the same way switching events away from unsaved work
    is: the first press arms and names what it is about to throw away, the
    second does it. The less deliberate gesture was protected and this, which
    loses the same 23-key sheet, was not.
    """
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.widgets import MarkButton

    screen = EventScreen()
    fired = []
    screen.discarded.connect(lambda: fired.append(1))
    discard = next(b for b in screen.findChildren(MarkButton)
                   if b.text().startswith("DISCARD"))

    # Nothing typed: nothing to throw away, and it says so rather than firing.
    discard.click()
    assert fired == []

    screen.name_edit.setText("Round 9 — Bathurst")
    discard.click()
    assert fired == [], "the first press on a dirty form asks"
    assert "sure" in discard.text().lower()
    discard.click()
    assert fired == [1]


def test_no_pane_hides_content_it_cannot_scroll_to(qt_app):
    """Hiding the bar did not stop the overflow, it stopped it being
    reachable: Event lost 96px at 1280x800 with no way to get at it."""
    from PyQt6.QtWidgets import QScrollArea

    from pitcrew.ui.car_screen import CarScreen
    from pitcrew.ui.event_screen import EventScreen

    for cls in (EventScreen, CarScreen):
        screen = cls()
        screen.resize(1170 - 178, 745)
        screen.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        screen.show()
        QApplication.processEvents()
        for area in screen.findChildren(QScrollArea):
            inner = area.widget()
            if inner is None:
                continue
            over = inner.minimumSizeHint().width() - area.viewport().width()
            if over <= 0:
                continue
            assert area.horizontalScrollBarPolicy() !=                 Qt.ScrollBarPolicy.ScrollBarAlwaysOff, (
                    f"{cls.__name__} hides {over}px nothing can reach")


def test_the_car_screen_reads_as_one_table_not_four(qt_app):
    """Each plate used to size its own name column, so Min and Max stepped
    about 8px further right down the screen."""
    from pitcrew.ui.car_screen import CarScreen

    from PyQt6.QtWidgets import QGridLayout

    screen = CarScreen()
    screen.resize(1600 - 178, 1000)
    screen.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    screen.show()
    for _ in range(3):
        for layout in screen.findChildren(QLayout):
            layout.activate()
        QApplication.processEvents()

    # The mechanism, which holds on any platform: every range grid pins its
    # name column to the same measured width and gives it no stretch, so none
    # of them can size it to its own longest label.
    grids = [g for g in screen.findChildren(QGridLayout)
             if g.columnMinimumWidth(0) > 0]
    assert len(grids) >= 4, "expected a pinned grid per range plate"
    assert len({g.columnMinimumWidth(0) for g in grids}) == 1
    assert {g.columnStretch(0) for g in grids} == {0}

    # And the result, where the platform can be trusted to measure it. Under
    # QT_QPA_PLATFORM=offscreen none of Bahnschrift, Bahnschrift Condensed,
    # Cascadia Mono or Consolas exist, so every text metric inflates and
    # positions are meaningless - the same trap that made a geometry sweep of
    # this app report clipping that was not there.
    if _fonts_are_real():
        columns = {box.mapTo(screen, box.rect().topLeft()).x()
                   for box in screen._min_editors.values()}
        assert len(columns) == 1, f"Min column starts at {sorted(columns)}"


def test_a_plate_title_outranks_the_captions_inside_it(qt_app):
    """The container was quieter than its contents: 12px STENCIL_DIM title
    over 11px STENCIL_DIM captions, which left a 23-key form with its only
    chunking device as the least legible text on it."""
    assert theme.PLATE_TITLE_PX > 11
    body = theme.STYLESHEET  # touched so a missing token fails loudly here
    assert body

    from pitcrew.ui.widgets import Plate

    plate = Plate("Regulations")
    # The title is painted, not a child widget, so the font is the assertion.
    assert plate._label_font.pixelSize() == theme.PLATE_TITLE_PX
