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
from PyQt6.QtWidgets import QApplication, QLineEdit            # noqa: E402

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


def ink_of(widget) -> str:
    """The strongest text colour the widget actually paints, as #RRGGBB."""
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    QApplication.processEvents()
    pixmap = widget.grab()
    image: QImage = pixmap.toImage()

    counts: collections.Counter = collections.Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            # Text pixels are the ones brighter than the panel they sit on;
            # antialiasing fills the gap, so the mode of the bright end is the
            # authored colour.
            if colour.red() + colour.green() + colour.blue() > 250:
                counts[(colour.red(), colour.green(), colour.blue())] += 1
    if not counts:
        return "none"
    red, green, blue = counts.most_common(1)[0][0]
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
