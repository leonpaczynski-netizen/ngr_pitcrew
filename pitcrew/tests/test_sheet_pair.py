"""One paste, two sheets, both labelled.

*"I want to load both race and quali car setups into the app and have them
appear in different sections of the app."*

The data model and the practice split were built first and had nothing to
point at: sheets were saved untagged, so `sheet_for(car, "qualifying")` could
never return anything. This is the half that was missing — a way to say which
sheet is which, and a paste that keeps both.
"""
from __future__ import annotations

import json

from pitcrew.analysis.runs import FOR_QUALIFYING, FOR_RACE
from pitcrew.setup.parse import parse_reply
from pitcrew.store.db import Store
from pitcrew.ui.event_screen import EventScreen

from .test_controller import qt_app  # noqa: F401


BOTH_SHEETS = json.dumps({
    "contract": "gt7-pitcrew-reply/1.0",
    "sheets": [
        {"purpose": "race", "sheetName": "Monza race v3",
         "values": {"rh_f": 60, "cam_f": 3.2}, "gears": [3.10, 2.28]},
        {"purpose": "qualifying", "sheetName": "Monza quali v3",
         "values": {"rh_f": 55, "cam_f": 3.6}},
    ],
})


def test_a_paste_with_both_sheets_loads_the_race_one_and_holds_the_other(qt_app):
    screen = EventScreen()
    screen.paste_box.setPlainText(BOTH_SHEETS)
    screen._on_read_sheet()

    assert screen.sheet_name.text() == "Monza race v3"
    assert screen.values()["setup_values"]["rh_f"] == 60
    held = screen.values()["other_sheets"]
    assert set(held) == {FOR_QUALIFYING}
    assert held[FOR_QUALIFYING].values["rh_f"] == 55


def test_switching_the_picker_shows_the_other_sheet(qt_app):
    screen = EventScreen()
    screen.paste_box.setPlainText(BOTH_SHEETS)
    screen._on_read_sheet()

    index = screen.sheet_purpose.findData(FOR_QUALIFYING)
    screen.sheet_purpose.setCurrentIndex(index)
    assert screen.sheet_name.text() == "Monza quali v3"
    assert screen.values()["setup_values"]["rh_f"] == 55
    assert set(screen.values()["other_sheets"]) == {FOR_RACE}


def test_changing_the_picker_with_nothing_pasted_does_not_wipe_his_typing(qt_app):
    """He is saying what the sheet he is entering is for. Overwriting the
    form to answer that would be a strange way to take the answer."""
    screen = EventScreen()
    screen.sheet_name.setText("hand-typed quali")
    screen.sheet_purpose.setCurrentIndex(
        screen.sheet_purpose.findData(FOR_QUALIFYING))
    assert screen.sheet_name.text() == "hand-typed quali"


def test_loading_a_sheet_sets_the_picker_from_the_sheet(qt_app):
    """Otherwise the label lies and one save makes it true.

    `_reset` leaves the picker on Race and `values()` reads the picker, so a
    qualifying sheet displayed under a Race label was written back as the race
    sheet - and the qualifying one stopped existing.
    """
    from pitcrew.setup.sheet import SetupSheet

    screen = EventScreen()
    screen.load({"id": 1, "name": "Round 8"},
                SetupSheet(car_name="Porsche 911 RSR (991) '17",
                           sheet_name="Monza quali v3",
                           values={"rh_f": 55.0},
                           purpose=FOR_QUALIFYING))
    assert screen.sheet_purpose.currentData() == FOR_QUALIFYING
    assert screen.values()["sheet_purpose"] == FOR_QUALIFYING


def test_a_sheet_that_never_answered_the_question_loads_as_race(qt_app):
    """`purpose` is None where the sheet predates the question. Falling back
    to index 0 there is the only place a fallback is honest."""
    from pitcrew.setup.sheet import SetupSheet

    screen = EventScreen()
    screen.load({"id": 1}, SetupSheet(car_name="X", sheet_name="old",
                                      values={"rh_f": 55.0}))
    assert screen.sheet_purpose.currentData() == FOR_RACE


def test_a_reply_with_one_sheet_still_loads(qt_app):
    screen = EventScreen()
    screen.paste_box.setPlainText(json.dumps({
        "sheets": [{"purpose": "race", "sheetName": "v1",
                    "values": {"rh_f": 60}}]}))
    screen._on_read_sheet()
    assert screen.sheet_name.text() == "v1"
    assert screen.values()["other_sheets"] == {}


# ---------------------------------------------------------------- the saving

def a_form(**overrides) -> dict:
    reply = parse_reply(BOTH_SHEETS)
    data = {
        "car_name": "Porsche 911 RSR (991) '17",
        "name": "Round 8",
        "sheet_name": "Monza race v3",
        "sheet_purpose": FOR_RACE,
        "setup_values": {"rh_f": 60.0},
        "gear_text": "3.10 2.28",
        "other_sheets": {FOR_QUALIFYING: reply.qualifying},
    }
    data.update(overrides)
    return data


def test_saving_keeps_both_and_tags_them(store: Store, event_id, qt_app):
    """Asking for two sheets and quietly storing one is worse than not
    asking."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.practice_screen import PracticeScreen

    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    try:
        sheet_id = controller._save_sheet(a_form())
    finally:
        controller.shutdown()

    car = "Porsche 911 RSR (991) '17"
    race = store.sheet_for(car, FOR_RACE)
    quali = store.sheet_for(car, FOR_QUALIFYING)
    assert race is not None and quali is not None
    assert race.id == sheet_id, "the form's sheet is the one the event is on"
    assert race.values["rh_f"] == 60.0
    assert quali.values["rh_f"] == 55.0
    assert quali.sheet_name == "Monza quali v3"


def test_two_sheets_from_one_paste_never_collide(store: Store, qt_app):
    """`setup_sheets` is unique on (car, name). Two sheets saved under one
    name would make the second silently overwrite the first."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.practice_screen import PracticeScreen

    reply = parse_reply(json.dumps({"sheets": [
        {"purpose": "race", "values": {"rh_f": 60}},
        {"purpose": "qualifying", "values": {"rh_f": 55}},
    ]}))
    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    try:
        controller._save_sheet(a_form(
            sheet_name="unnamed",
            other_sheets={FOR_QUALIFYING: reply.qualifying}))
    finally:
        controller.shutdown()

    car = "Porsche 911 RSR (991) '17"
    sheets = store.list_setup_sheets(car)
    assert len({sheet.sheet_name for sheet in sheets}) == len(sheets) == 2
    assert store.sheet_for(car, FOR_QUALIFYING).values["rh_f"] == 55.0
