"""The Car and Race Engineer screens, wired to the store through the controller.

Real widgets under an offscreen Qt platform, like the rest of the wiring
tests: the point is the join, and a mocked join is not joined.
"""
from __future__ import annotations

import pytest

from pitcrew.controller import PitCrewController
from pitcrew.prompts.build import BRIEF, OUTCOME, REFINEMENT
from pitcrew.prompts.templates import PROMPT_VERSION
from pitcrew.store import catalogs
from pitcrew.store.db import Store
from pitcrew.ui.car_screen import CarScreen
from pitcrew.ui.engineer_screen import EngineerScreen
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen

pytest.importorskip("PyQt6.QtWidgets")

CAR = "Porsche 911 RSR (991) '17"


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def wired(qt_app, store: Store):
    event_screen = EventScreen()
    practice = PracticeScreen()
    car = CarScreen()
    engineer = EngineerScreen()
    controller = PitCrewController(store, event_screen, practice,
                                   car_screen=car, engineer_screen=engineer)
    yield controller, car, engineer, event_screen, store
    controller.shutdown()


def an_event(store) -> int:
    event_id = store.create_event(
        name="Round 4 - Fuji", track="Fuji International Speedway",
        car_name=CAR, race_type="laps", race_laps=20, weather="dry",
        tyre_wear_mult="4x", fuel_mult="2x", refuel_rate_lps=1.0,
        pit_loss_secs=19.5, mandatory_stops=1,
        available_compounds=["RH", "RM", "RS"], abs_setting="Weak", tcs=1)
    store.set_state("active_event_id", event_id)
    return event_id


# ---------------------------------------------------------------- car screen

def test_the_seed_ranges_land_once_when_the_controller_starts(wired):
    _controller, _car, _engineer, _event, store = wired
    assert store.get_range_record(CAR) is not None
    assert store.get_range_record(CAR).verified is True


def test_measuring_a_car_once_reaches_every_prompt(wired):
    controller, car, engineer, _event_screen, store = wired
    an_event(store)

    car.set_car(CAR)
    car.write_ranges({"rh_f": [50, 75], "nf_f": [3, 5]})
    car.verified.setChecked(True)
    car._on_save()

    record = store.get_range_record(CAR)
    assert record.ranges["rh_f"] == [50, 75]
    assert record.verified is True

    for kind in (BRIEF, REFINEMENT, OUTCOME):
        engineer.set_kind(kind)
        text = controller.generate_prompt(kind)
        assert "| Ride height — front | 50 mm | 75 mm |" in text


def test_a_half_entered_range_is_not_saved_as_a_range(wired):
    _controller, car, _engineer, _event_screen, store = wired
    car.set_car(CAR)
    car.clear_ranges()
    car._min_editors["rh_f"].setValue(55.0)     # no maximum
    assert car.read_ranges() == {}
    car._on_save()
    assert "Nothing to save" in car.footer_note.text()


def test_a_preset_is_never_saved_as_measured(wired):
    _controller, car, _engineer, _event_screen, store = wired
    car.set_car("Ferrari 296 GT3 '23")
    car.load_preset("race")
    assert car.verified.isChecked() is False
    car._on_save()
    assert store.get_range_record("Ferrari 296 GT3 '23").verified is False


def test_showing_a_car_with_nothing_on_file_says_so(wired):
    controller, car, _engineer, _event_screen, _store = wired
    controller.load_car("Ferrari 296 GT3 '23")
    assert "Nothing on file" in car.state_note.text()
    assert car.verified.isChecked() is False


# ----------------------------------------------------------- engineer screen

def test_generating_a_prompt_logs_it_with_its_template(wired):
    controller, _car, engineer, _event_screen, store = wired
    event_id = an_event(store)

    engineer.set_kind(BRIEF)
    text = controller.generate_prompt(BRIEF)
    assert text and text in engineer.prompt_text()

    logged = store.list_prompts(event_id)
    assert len(logged) == 1
    assert logged[0]["kind"] == BRIEF
    assert logged[0]["prompt_version"] == PROMPT_VERSION
    assert logged[0]["car_name"] == CAR
    assert logged[0]["body"] == text


def test_a_reply_is_filed_against_the_prompt_that_asked_for_it(wired):
    controller, _car, engineer, _event_screen, store = wired
    event_id = an_event(store)
    controller.generate_prompt(BRIEF)
    issue_id = controller.prompt_issue_id

    controller.file_prompt_reply("Race sheet: rh_f 60 ...")
    assert store.get_prompt(issue_id)["reply"].startswith("Race sheet")
    assert "Filed against prompt" in engineer.reply_note.text()

    assert store.list_prompts(event_id)[0]["id"] == issue_id


def test_a_reply_with_no_prompt_is_refused_rather_than_orphaned(wired):
    controller, _car, engineer, _event_screen, store = wired
    an_event(store)
    controller.file_prompt_reply("something")
    assert "Generate a prompt first" in engineer.reply_note.text()


def test_the_driver_report_reaches_the_prompt(wired):
    controller, _car, engineer, _event_screen, store = wired
    an_event(store)

    engineer.set_kind(REFINEMENT)
    for box in engineer._symptom_boxes:
        if box.text() == "Rear locking":
            box.setChecked(True)
    engineer._refresh_worst()
    engineer.worst.setCurrentIndex(1)
    engineer.notes.setPlainText("Rear steps out under braking into T1.")

    text = controller.generate_prompt(REFINEMENT)
    assert "- Rear locking" in text
    assert "**Biggest single limitation: Rear locking**" in text
    assert "Rear steps out under braking into T1." in text


def test_with_no_event_the_screen_says_so_rather_than_generating(wired):
    controller, _car, engineer, _event_screen, _store = wired
    controller.refresh_engineer()
    assert "No event yet" in engineer.knows_note.text()
    assert controller.generate_prompt(BRIEF) is None
    assert "Refused" in engineer.footer_note.text()


def test_the_screen_reports_what_it_is_filling_in(wired):
    controller, _car, engineer, _event_screen, store = wired
    an_event(store)
    controller.refresh_engineer()
    note = engineer.knows_note.text()
    assert CAR in note
    assert "Fuji International Speedway" in note
    assert "measured slider ranges" in note


def test_the_brief_hides_the_session_questions_it_cannot_be_about(wired):
    _controller, _car, engineer, _event_screen, _store = wired
    engineer.set_kind(BRIEF)
    assert engineer.symptoms_plate.isVisibleTo(engineer) is False
    engineer.set_kind(REFINEMENT)
    assert engineer.symptoms_plate.isVisibleTo(engineer) is True
    assert engineer.race_plate.isVisibleTo(engineer) is False
    engineer.set_kind(OUTCOME)
    assert engineer.race_plate.isVisibleTo(engineer) is True


# ------------------------------------------------------------- event screen

def test_the_event_screen_saves_the_facts_the_prompts_need(wired):
    controller, _car, engineer, event_screen, store = wired
    values = event_screen.values()
    values.update({
        "name": "Round 4 - Fuji", "track": "Fuji International Speedway",
        "car_name": CAR, "start_type": "Standing",
        "time_of_day": "Fixed night", "priority": "Race pace and tyre life",
        "pp_cap": 730.0, "countersteer": 1, "notes": "League bans ballast.",
        "build": {"bhp": 525, "weightKg": 1300},
    })
    controller._on_event_saved(values)

    event = controller.active_event()
    assert event["start_type"] == "Standing"
    assert event["time_of_day"] == "Fixed night"
    assert event["pp_cap"] == 730.0
    assert event["notes"] == "League bans ballast."

    text = controller.generate_prompt(BRIEF)
    assert "Start: Standing" in text
    assert "Fixed night" in text
    assert "PP cap 730" in text
    assert "As raced: **525 bhp · 1300 kg**" in text
    assert "Countersteer assist On" in text
    assert "League bans ballast." in text


def test_a_blank_pp_cap_stays_blank_rather_than_becoming_zero(wired):
    _controller, _car, _engineer, event_screen, _store = wired
    assert event_screen.values()["pp_cap"] is None
    assert event_screen.values()["build"] == {}
