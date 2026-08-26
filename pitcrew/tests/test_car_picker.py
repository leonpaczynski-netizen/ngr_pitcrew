"""Finding a car in a catalogue of 608.

The flat picker put every car behind one dropdown with eight class headings,
369 of them under `Road Car`. These tests are about the two things the
narrowing must not cost: no car may become unreachable, and the value the
event saves must still be the car and nothing else.
"""
from __future__ import annotations

from pitcrew.store import catalogs
from pitcrew.ui.widgets import CascadingPicker, Picker

from .test_controller import qt_app  # noqa: F401

CATALOGUE = [
    ("Gr.3", {"Porsche": ("Porsche 911 RSR (991) '17",
                          "Porsche 911 GT3 R (992) '22"),
              "Lamborghini": ("Lamborghini Huracan GT3 '15",)}),
    ("Road Car", {"Honda": ("Honda Civic Type R '17",)}),
]


def picker() -> CascadingPicker:
    return CascadingPicker(CATALOGUE, placeholder="Pick a car")


def offered(combo) -> list[str]:
    return [combo.itemData(i) for i in range(combo.count())
            if combo.itemData(i) is not None]


# --------------------------------------------------------------- narrowing

def test_the_class_is_the_first_step(qt_app):  # noqa: F811
    assert offered(picker().category_combo) == ["Gr.3", "Road Car"]


def test_picking_a_class_offers_only_that_class_makers(qt_app):  # noqa: F811
    p = picker()
    p.category_combo.setCurrentIndex(p.category_combo.findData("Gr.3"))
    assert offered(p.maker_combo) == ["Lamborghini", "Porsche"]


def test_makers_and_cars_are_offered_in_the_alphabet(qt_app):  # noqa: F811
    """A list in dict-insertion order cannot be found by eye."""
    p = picker()
    p.category_combo.setCurrentIndex(p.category_combo.findData("Gr.3"))
    assert offered(p.maker_combo) == sorted(offered(p.maker_combo))


def test_picking_a_maker_offers_only_that_makers_cars(qt_app):  # noqa: F811
    p = picker()
    p.category_combo.setCurrentIndex(p.category_combo.findData("Gr.3"))
    p.maker_combo.setCurrentIndex(p.maker_combo.findData("Porsche"))
    assert offered(p.car_combo) == ["Porsche 911 GT3 R (992) '22",
                                    "Porsche 911 RSR (991) '17"]


def test_no_car_is_offered_before_a_maker_is_chosen(qt_app):  # noqa: F811
    """A car list that fills itself in is a car chosen by the app."""
    p = picker()
    p.category_combo.setCurrentIndex(p.category_combo.findData("Gr.3"))
    assert offered(p.car_combo) == []


# ------------------------------------------------------------------- value

def test_only_the_car_is_the_value(qt_app):  # noqa: F811
    """Class and maker are navigation. Neither may reach `currentText`."""
    p = picker()
    p.category_combo.setCurrentIndex(p.category_combo.findData("Gr.3"))
    p.maker_combo.setCurrentIndex(p.maker_combo.findData("Porsche"))
    assert p.currentText() == ""
    p.car_combo.setCurrentIndex(
        p.car_combo.findData("Porsche 911 RSR (991) '17"))
    assert p.currentText() == "Porsche 911 RSR (991) '17"


def test_a_stored_car_drives_the_two_steps_above_it(qt_app):  # noqa: F811
    """Loading a saved event must show where the car lives, not just its name."""
    p = picker()
    p.setCurrentText("Lamborghini Huracan GT3 '15")
    assert p.category_combo.currentData() == "Gr.3"
    assert p.maker_combo.currentData() == "Lamborghini"
    assert p.currentText() == "Lamborghini Huracan GT3 '15"


def test_changing_class_discards_the_car_and_says_so(qt_app):  # noqa: F811
    """Silently keeping a Gr.3 car under Road Car is how a wrong car saves."""
    p = picker()
    p.setCurrentText("Lamborghini Huracan GT3 '15")
    heard: list[str] = []
    p.changed.connect(heard.append)
    p.category_combo.setCurrentIndex(p.category_combo.findData("Road Car"))
    assert p.currentText() == ""
    assert heard == [""]


def test_clearing_resets_every_step(qt_app):  # noqa: F811
    p = picker()
    p.setCurrentText("Lamborghini Huracan GT3 '15")
    p.setCurrentText("")
    assert p.currentText() == ""
    assert p.category_combo.currentData() is None
    assert offered(p.car_combo) == []


# ------------------------------------------------------- what must not break

def test_every_car_in_the_catalogue_is_still_reachable(qt_app):  # noqa: F811
    """The narrowing is a route to the car, never a filter on which exist."""
    nested = list(catalogs.cars_by_category_and_maker().items())
    flat = {name for names in catalogs.cars_by_category().values()
            for name in names}
    assert set(CascadingPicker(nested).items()) == flat


def test_a_car_the_catalogue_no_longer_carries_is_still_shown(qt_app):  # noqa: F811
    """Blanking it would throw away what the event was actually raced on."""
    p = picker()
    p.setCurrentText("Ghost Car '99")
    assert p.currentText() == "Ghost Car '99"
    # ...but it is not smuggled into a real maker's list.
    assert "Ghost Car '99" not in p.items()


def test_a_refresh_keeps_a_selection_the_new_catalogue_still_carries(qt_app):  # noqa: F811
    p = picker()
    p.setCurrentText("Porsche 911 RSR (991) '17")
    p.set_groups(CATALOGUE + [("Added", {"Added": ("Custom Car '00",)})])
    assert p.currentText() == "Porsche 911 RSR (991) '17"


def test_a_refresh_drops_a_selection_the_new_catalogue_does_not(qt_app):  # noqa: F811
    """`Picker` documents why re-adding here leaks one list into another."""
    p = picker()
    p.setCurrentText("Porsche 911 RSR (991) '17")
    p.set_groups([("Road Car", {"Honda": ("Honda Civic Type R '17",)})])
    assert p.currentText() == ""


def test_it_answers_the_same_calls_the_event_screen_makes_of_a_picker(qt_app):  # noqa: F811
    """A drop-in, or the event screen has two shapes of car field to maintain."""
    for name in ("currentText", "setCurrentText", "set_groups", "items",
                 "setEnabledState"):
        assert hasattr(CascadingPicker, name), name
        assert hasattr(Picker, name), name


def test_a_flat_group_list_still_works(qt_app):  # noqa: F811
    """The custom-catalogue `Added` group has no maker to file under."""
    p = CascadingPicker([("Added", ["Custom Car '00"])])
    p.setCurrentText("Custom Car '00")
    assert p.currentText() == "Custom Car '00"
