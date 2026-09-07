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
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen
    from pitcrew.ui.race_screen import RaceScreen
    from pitcrew.ui.reference_screen import ReferenceScreen
    from pitcrew.ui.settings_screen import SettingsScreen
    from pitcrew.ui.strategy_screen import StrategyScreen

    settings = SettingsScreen()
    settings.load(Settings())
    for screen in (EventScreen(), CarScreen(), PracticeScreen(),
                   StrategyScreen(), RaceScreen(),
                   ReferenceScreen(), settings):
        # **With the sheet the app runs.** Bare, a screen reports up to 22 px
        # less than it will actually take, so this guard had that much slack
        # on the one display that cannot afford any.
        #
        # Measured natively, bare -> styled: Car 247 -> 265, Settings
        # 243 -> 265, Event 249 -> 267, Strategy 257 -> 279, Reference
        # 267 -> 285, Practice 305 -> 324, **Race 497 -> 499** against a 501
        # cap - so the six that are not the Race page sit between 265 and
        # 324 styled. The cost is not a font size: deleting `font-size: 15px`
        # from the sheet changes nothing on either platform, and what moves
        # the Race page is
        # `QScrollBar::handle:vertical { min-height: 40px }`.
        screen.setStyleSheet(theme.STYLESHEET)
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


# ------------------------------------------------- state you can actually see

def test_recording_looks_different_from_not_recording(qt_app):
    """The design argues this for a row of mode buttons - "a selection nobody
    can see is no selection" - and then left the app's one genuinely stateful
    control carrying its state in a verb."""
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    screen.set_recording(False)
    idle = screen.record_button.styleSheet()
    screen.set_recording(True)
    assert screen.record_button.styleSheet() != idle


def test_a_lap_landing_does_not_destroy_the_row_being_marked_up(qt_app):
    """A rebuild closes any open dropdown, takes the focus and deletes a tyre
    gauge mid-drag. `restructured` was split from `changed` for exactly that
    reason and `add_lap` did the unguarded thing anyway."""
    from pitcrew.ui.practice_screen import LapRow, PracticeScreen, RackRow

    def lap(n):
        return LapRow(lap_id=n, lap_num=n, lap_time_ms=109_000, fuel_used=6.0,
                      fuel_start=100 - 6 * (n - 1), fuel_end=100 - 6 * n,
                      compound="RH", session_id=1)

    screen = PracticeScreen()
    screen.set_laps([lap(n) for n in range(1, 6)])
    watched = screen.findChildren(RackRow)[1]
    combo = watched.compound_picker
    screen.add_lap(lap(6))

    # Still the same widget, not a rebuilt copy of it - which is the whole
    # point: a rebuilt row has a fresh combo box, so the one he had open is
    # gone and so is anything he was dragging.
    assert watched in screen._row_widgets
    assert combo is watched.compound_picker
    # The screen's own list, not Qt's child list: `deleteLater` is deferred,
    # so rows retired by an earlier rebuild are still children for a while.
    assert len(screen._row_widgets) == 6


def test_a_replan_offer_can_be_answered_without_the_microphone(qt_app):
    """With push-to-talk off, the key misbound, or no keyboard hook on the
    machine, the offer sat on screen as an unanswerable sentence."""
    from pitcrew.ui.race_screen import RaceScreen

    class _Verdict:
        reason = "Fuel is the constraint"

        def call(self):
            return "Box this lap or next"

    screen = RaceScreen()
    assert screen.offer_row.isVisibleTo(screen) is False
    screen.show_offer(_Verdict())
    assert screen.offer_row.isVisibleTo(screen) is True
    screen.hide_offer()
    assert screen.offer_row.isVisibleTo(screen) is False


# ------------------------------------------------------ finding things again

def test_the_reference_can_be_filtered(qt_app):
    """Its stated use is looking something up at the rig with the headset
    pushed up, and the only tool was the scroll wheel."""
    from pitcrew.ui.reference_screen import ReferenceScreen

    screen = ReferenceScreen()
    total = len(screen._plates)
    assert total, "the reference should have sections to filter"
    screen._apply_filter("zzzznomatch")
    assert not [p for p, _ in screen._plates if p.isVisibleTo(screen)]
    screen._apply_filter("")
    assert len([p for p, _ in screen._plates if p.isVisibleTo(screen)]) == total


# -------------------------------------------------------- labels and controls

def test_every_labelled_control_is_named_for_assistive_tech(qt_app):
    """A grep of the package found no `setBuddy` and two `setAccessibleName`,
    so ~80 form controls were anonymous and carried no Alt-mnemonic."""
    from PyQt6.QtWidgets import QLineEdit
    from pitcrew.ui.widgets import Field

    editor = QLineEdit()
    field = Field("Refuel rate", editor, hint="Litres a second")
    assert field is not None       # keeps the parent alive for the assertions
    assert editor.accessibleName() == "Refuel rate"
    assert editor.accessibleDescription() == "Litres a second"


def test_changing_the_track_does_not_leak_its_layout_into_the_next_one(qt_app):
    """`Picker.set_groups` restored the previous selection with
    `setCurrentText`, which ADDS when `findData` misses - so Le Mans / Full
    Course, switched to Alsace, left the layout reading Full Course and put
    Full Course in Alsace's dropdown. 31 circuits have more than one layout,
    and layout is what the track model and the rain list key on."""
    from pitcrew.ui.event_screen import EventScreen

    screen = EventScreen()
    screen.track_edit.setCurrentText("24 Heures du Mans Racing Circuit")
    screen.layout_edit.setCurrentText("No Chicane")
    assert screen.layout_edit.currentText() == "No Chicane"

    screen.track_edit.setCurrentText("Alsace")
    assert "No Chicane" not in screen.layout_edit.items()
    assert screen.values()["layout"] is None


def test_the_switch_guard_releases_on_an_event_id_above_the_int_cache(qt_app):
    """`itemData` round-trips through a QVariant and returns a fresh int, so
    an `is not` comparison held only while CPython's small-int cache made two
    900s the same object. Above 256 the guard never released and an event with
    unsaved edits on screen could never be reached."""
    from pitcrew.ui.event_screen import EventScreen

    screen = EventScreen()
    screen.set_events([{"id": 900, "name": "Round 9"},
                       {"id": 901, "name": "Round 10"}])
    screen.load({"id": 900, "name": "Round 9"})
    screen.name_edit.setText("Round 9 - edited")
    assert screen.is_dirty()

    targets = []
    screen.switched.connect(targets.append)
    index = screen.event_picker.findData(901)
    screen._on_picker_activated(index)
    assert targets == [], "the first click must arm, not switch"
    screen._on_picker_activated(index)
    assert targets == [901], "the second click must switch"


def test_a_refused_rebuild_takes_the_old_plan_off_the_spec_line(qt_app):
    """The controller catches `StrategyImpossible`, calls `show_plans([], ...)`
    and returns before it reaches `note()` - and every `spec.add` sat inside
    `if plans:`. The two largest pieces of text on the screen went on
    describing a plan the app had just refused to make."""
    from pitcrew.strategy.model import Plan, Stint
    from pitcrew.ui.strategy_screen import StrategyScreen

    plan = Plan(stints=[Stint(15, "RM", 45.0, 1), Stint(15, "RM", 45.0, 16)],
                total_time_s=2892.0, binding_constraint="tyres",
                notes=["measured"])

    screen = StrategyScreen()
    screen.show_plans([plan], [])
    screen.note("Every input measured.")
    assert screen.spec._entries

    screen.show_plans([], [])
    assert screen.spec._entries == []
    assert screen.footer_note.text() == ""


def test_a_range_whose_max_is_below_its_min_is_refused(qt_app):
    """This screen exists to copy 22 pairs of numbers off the car's own
    settings screen by hand, and what it writes is a hard slider limit.
    `fraction_of_range` guards only `high == low`, so 200/50 makes every
    percentage quoted against that key negative (CLAUDE.md 4.6)."""
    from pitcrew.ui.car_screen import CarScreen

    screen = CarScreen()
    screen._min_editors["rh_f"].setValue(200.0)
    screen._max_editors["rh_f"].setValue(50.0)
    screen._min_editors["rh_r"].setValue(50.0)
    screen._max_editors["rh_r"].setValue(200.0)

    assert "rh_f" not in screen.read_ranges()
    assert screen.read_ranges()["rh_r"] == [50.0, 200.0]
    assert screen.inverted_ranges()

    saved = []
    screen.saved.connect(lambda *a: saved.append(a))
    screen.car_edit.setCurrentText(screen.car_edit.items()[0])
    screen._on_save()
    assert saved == [], "an inverted pair reached the store as a slider limit"
    assert "below min" in screen.footer_note.text()


def test_a_picker_takes_focus_when_it_is_told_to(qt_app):
    """`Picker` is a plain QWidget wrapping the combo, so its focus policy is
    NoFocus and the save message's "and go there" did nothing for Track and
    Car - the two fields it names most often."""
    from PyQt6.QtCore import Qt
    from pitcrew.ui.event_screen import EventScreen

    screen = EventScreen()
    screen.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    screen.show()
    screen.name_edit.setText("Round 8")
    screen._on_save()
    assert screen.focusWidget() is screen.track_edit.combo


def test_an_incident_lap_is_out_of_the_rack_count_too(qt_app):
    """`LapRow.counted` omitted `incident`, which `LapInput.counted` includes -
    so a 122 s spin stayed in the rack's count and its best. On a stored
    ten-lap event the rack read "Counted 9/10, Best 92.100" against the
    export's `lapsCounted 7, bestLapMs 94000`."""
    from pitcrew.ui.practice_screen import LapRow, RackRow

    spun = LapRow(9, 9, 122_000, 3.4, compound="RM", incident=True,
                  incident_note="spin")
    clean = LapRow(2, 2, 94_000, 3.4, compound="RM")
    assert clean.counted
    assert not spun.counted, "an incident lap is not a pace sample"

    widget = RackRow(spun, 94_000)
    assert widget.band._struck, "neither dimmed nor strikeable"
    assert not widget.exclude_button.isVisibleTo(widget)


def test_the_screenshot_harness_starts(qt_app):
    """It is the harness that would have caught a paintEvent calling a
    function nobody wrote. `NavRail.select` read `self.stack`; `__init__`
    assigns `self._stack`, so it died on construction in both modes."""
    from PyQt6.QtWidgets import QStackedWidget, QWidget

    from pitcrew.ui.preview import NavRail

    stack = QStackedWidget()
    for _ in range(2):
        stack.addWidget(QWidget())
    rail = NavRail(stack, ["Event", "Practice", "Strategy", "Race"])
    rail.select(1)
    assert stack.currentIndex() == 1
    rail.select(3)                      # past the end of a two-screen stack
    assert stack.currentIndex() == 1

