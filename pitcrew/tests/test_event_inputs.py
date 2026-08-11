"""Input behaviour on the Event screen: no typos, no skipped steps, no
value changed by scrolling past it."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox

from pitcrew.controller import PitCrewController
from pitcrew.store.db import Store
from pitcrew.ui.event_screen import MULTIPLIERS, EventScreen
from pitcrew.ui.practice_screen import PracticeScreen
from pitcrew.ui.widgets import Picker, block_wheel

from .test_controller import an_event, qt_app  # noqa: F401


def scroll(widget) -> None:
    """One notch of wheel over a widget, as the mouse passing over it."""
    event = QWheelEvent(
        QPointF(5.0, 5.0), QPointF(5.0, 5.0), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


# ------------------------------------------------------------- wheel guard

def test_scrolling_over_an_unfocused_combo_changes_nothing(qt_app):  # noqa: F811
    """Scrolling the form must not quietly rewrite the car."""
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    block_wheel(combo)
    scroll(combo)
    assert combo.currentIndex() == 0


def test_scrolling_over_an_unfocused_spin_box_changes_nothing(qt_app):  # noqa: F811
    box = QDoubleSpinBox()
    box.setRange(0.0, 10.0)
    box.setValue(5.0)
    block_wheel(box)
    scroll(box)
    assert box.value() == 5.0


def test_a_focused_widget_still_takes_the_wheel(qt_app):  # noqa: F811
    """Deliberate is fine; incidental is not."""
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    block_wheel(combo)
    combo.setFocus()
    if combo.hasFocus():
        scroll(combo)
        assert combo.currentIndex() == 1


def test_every_setup_editor_is_guarded(qt_app):  # noqa: F811
    screen = EventScreen(tracks=["Fuji Speedway"],
                         car_groups=[("Gr.3", ["Some Car"])])
    for editor in screen._setup_editors.values():
        before = editor.value()
        scroll(editor)
        assert editor.value() == before


def test_the_regulation_boxes_are_guarded(qt_app):  # noqa: F811
    screen = EventScreen(tracks=["Fuji Speedway"],
                         car_groups=[("Gr.3", ["Some Car"])])
    for widget in (screen.tyre_mult, screen.fuel_mult, screen.race_length,
                   screen.refuel_rate, screen.pit_loss, screen.tcs,
                   screen.weather, screen.abs_setting):
        before = (widget.currentIndex() if isinstance(widget, QComboBox)
                  else widget.value())
        scroll(widget)
        after = (widget.currentIndex() if isinstance(widget, QComboBox)
                 else widget.value())
        assert after == before


def test_the_rack_pickers_are_guarded(qt_app):  # noqa: F811
    from pitcrew.ui.practice_screen import LapRow, RackRow
    row = RackRow(LapRow(1, 1, 94_000, 3.4), 94_000)
    scroll(row.compound_picker)
    scroll(row.wear_front)
    assert row.row.compound is None
    assert row.row.wear_front is None


# ------------------------------------------------------------------ pickers

def test_a_picker_is_empty_until_something_is_chosen(qt_app):  # noqa: F811
    picker = Picker(["Fuji Speedway", "Suzuka"], placeholder="Pick a track")
    assert picker.currentText() == ""


def test_a_picker_round_trips_a_choice(qt_app):  # noqa: F811
    picker = Picker(["Fuji Speedway", "Suzuka"])
    picker.setCurrentText("Suzuka")
    assert picker.currentText() == "Suzuka"


def test_a_stored_name_outside_the_list_is_still_loadable(qt_app):  # noqa: F811
    """An event saved before the name was added must still open."""
    picker = Picker(["Fuji Speedway"])
    picker.setCurrentText("Somewhere Else")
    assert picker.currentText() == "Somewhere Else"


def test_group_headings_cannot_be_chosen(qt_app):  # noqa: F811
    """A heading is a signpost, not a car."""
    picker = Picker(groups=[("Gr.3", ["A", "B"]), ("Road Car", ["C"])])
    assert picker.items() == ["A", "B", "C"]
    model = picker.combo.model()
    heading = next(i for i in range(picker.combo.count())
                   if picker.combo.itemText(i).startswith("—") and i > 0)
    assert model.item(heading).isEnabled() is False


def test_groups_keep_their_order(qt_app):  # noqa: F811
    picker = Picker(groups=[("Gr.1", ["one"]), ("Road Car", ["two"])])
    texts = [picker.combo.itemText(i) for i in range(picker.combo.count())]
    assert texts.index("— Gr.1 —") < texts.index("— Road Car —")


def test_setting_items_keeps_the_current_choice(qt_app):  # noqa: F811
    picker = Picker(["Fuji Speedway"])
    picker.setCurrentText("Fuji Speedway")
    picker.set_items(["Fuji Speedway", "Suzuka"])
    assert picker.currentText() == "Fuji Speedway"


# -------------------------------------------------------------- multipliers

def test_multipliers_do_not_skip_a_step():
    """GT7 offers every step; a list that skips 7x and 9x cannot describe it."""
    steps = [m for m in MULTIPLIERS if m != "Off"]
    assert steps == [f"{n}x" for n in range(1, 11)]


def test_off_is_available_as_a_multiplier():
    assert MULTIPLIERS[0] == "Off"


# ---------------------------------------------------------- custom catalogs

def test_adding_the_same_name_twice_stores_it_once(store: Store):
    store.add_to_catalog("car", "Some Car")
    store.add_to_catalog("car", "Some Car")
    assert store.custom_catalog("car") == ["Some Car"]


def test_an_unknown_catalog_kind_is_empty(store: Store):
    assert store.custom_catalog("banana") == []


def test_tracks_are_listed_once_with_layouts_split_off(qt_app, store: Store):  # noqa: F811
    """86 catalogue entries repeat 27 base names; the layout has its own box."""
    screen = EventScreen()
    controller = PitCrewController(store, screen, PracticeScreen())
    items = screen.track_edit.items()
    assert "Autodrome Lago Maggiore" in items
    assert not any("–" in name for name in items)
    assert len([n for n in items if n.startswith("Autodrome Lago")]) == 1
    controller.shutdown()


def test_choosing_a_track_offers_only_its_layouts(qt_app, store: Store):  # noqa: F811
    screen = EventScreen()
    controller = PitCrewController(store, screen, PracticeScreen())
    screen.track_edit.setCurrentText("Autodrome Lago Maggiore")
    layouts = screen.layout_edit.items()
    assert "Centre" in layouts
    assert "East" in layouts
    assert all("Lago" not in layout for layout in layouts)
    controller.shutdown()


def test_a_track_with_one_layout_disables_the_layout_box(qt_app, store: Store):  # noqa: F811
    screen = EventScreen(tracks=["Somewhere"],
                         car_groups=[("Gr.3", ["Some Car"])])
    controller = PitCrewController(store, screen, PracticeScreen())
    screen.track_edit.setCurrentText("Somewhere")
    assert screen.layout_edit.items() == []
    assert screen.layout_edit.combo.isEnabled() is False
    controller.shutdown()


def test_cars_are_grouped_by_class(qt_app, store: Store):  # noqa: F811
    screen = EventScreen()
    controller = PitCrewController(store, screen, PracticeScreen())
    texts = [screen.car_edit.combo.itemText(i)
             for i in range(screen.car_edit.combo.count())]
    assert "— Gr.3 —" in texts
    assert "— Road Car —" in texts
    assert texts.index("— Gr.3 —") < texts.index("— Road Car —")
    controller.shutdown()


# ------------------------------------------------------------------ round trip

def test_a_saved_event_reopens_with_its_track_and_car(qt_app, store: Store):  # noqa: F811
    screen = EventScreen()
    controller = PitCrewController(store, screen, PracticeScreen())
    data = an_event(track="Fuji Speedway",
                    car_name="Porsche 911 RSR (991) '17")
    controller._on_event_saved(data)

    reopened = EventScreen()
    PitCrewController(store, reopened, PracticeScreen())
    assert reopened.track_edit.currentText() == "Fuji Speedway"
    assert reopened.car_edit.currentText() == "Porsche 911 RSR (991) '17"
    controller.shutdown()


def test_the_popup_is_wide_enough_for_the_longest_name(qt_app):  # noqa: F811
    """Elided to "24 Heures du...cing Circuit", two circuits look identical."""
    longest = "24 Heures du Mans Racing Circuit No Chicane Extended"
    picker = Picker(["Short", longest])
    view = picker.combo.view()
    assert view.minimumWidth() >= view.fontMetrics().horizontalAdvance(longest)
    assert view.textElideMode() == Qt.TextElideMode.ElideNone


def test_the_popup_widens_for_grouped_names(qt_app):  # noqa: F811
    longest = "Porsche 911 GT3 RS (997) Something Very Long Indeed '11"
    picker = Picker(groups=[("Gr.3", ["A"]), ("Road Car", [longest])])
    view = picker.combo.view()
    assert view.minimumWidth() >= view.fontMetrics().horizontalAdvance(longest)
