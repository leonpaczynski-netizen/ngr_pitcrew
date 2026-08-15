"""The controller defects the pre-UAT review found, and their fixes.

Each of these failed before the fix and would not have been caught by the
suite as it stood: they live in the joins between the hook thread and Qt, one
event and the next, and the two units `events.race_laps` carries.
"""
from __future__ import annotations

import threading

import pytest

from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.setup.sheet import SetupSheet
from pitcrew.store.db import Store

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_push_to_talk_answer_crosses_from_the_hook_thread(qt_app):
    """The reply arrives on pynput's thread, which has no event loop.

    `QTimer.singleShot(0, fn)` builds its dispatch object on the *calling*
    thread, so posted from there it never ran at all - the driver said
    "accept", heard "Copy, changing the plan", and nothing changed.
    """
    from PyQt6.QtCore import QTimer

    from pitcrew.controller import TelemetryBridge

    bridge = TelemetryBridge()
    delivered: list[tuple[str, str, str]] = []
    bridge.ptt_answered.connect(
        lambda heard, said: delivered.append(
            (heard, said, threading.current_thread().name)))

    def on_hook_thread() -> None:
        bridge.ptt_answered.emit("how much fuel", "Eight laps.")

    worker = threading.Thread(target=on_hook_thread, daemon=True)
    worker.start()
    worker.join()
    QTimer.singleShot(50, qt_app.quit)
    qt_app.exec()

    assert delivered == [("how much fuel", "Eight laps.", "MainThread")]


def test_a_timed_race_does_not_count_its_minutes_as_laps():
    """`events.race_laps` holds minutes when the format is timed.

    Read as a distance, a 45-minute race counted down 45 laps: "40 to go" with
    19 left, and a fuel call short by the difference.
    """
    timed = RaceCoordinator()
    timed.arm(None, PlanContext(car="RSR", track="Monza", layout=None,
                                race_laps=0, race_minutes=45.0))
    assert timed.state.race_minutes == 45.0
    # No plan, so no distance to count down - and 45 is certainly not it.
    assert timed.state.laps_total is None

    counted = RaceCoordinator()
    counted.arm(None, PlanContext(car="RSR", track="Monza", layout=None,
                                  race_laps=24))
    assert counted.state.laps_total == 24


def test_the_event_screen_is_given_the_race_sheet_not_the_last_saved(store: Store):
    """A pasted pair is written inside one second, so `updated_at` ties.

    `list_setup_sheets` breaks the tie on `id DESC`, which put the qualifying
    sheet on top; the screen showed it under the Race label and one Save
    rewrote it as the race sheet.
    """
    store.save_setup_sheet(SetupSheet(
        car_name="RSR", sheet_name="race v3", purpose="race",
        values={"rh_f": 60.0}))
    store.save_setup_sheet(SetupSheet(
        car_name="RSR", sheet_name="quali v3", purpose="qualifying",
        values={"rh_f": 55.0}))

    newest_first = store.list_setup_sheets("RSR")[0]
    assert newest_first.purpose == "qualifying", "fixture no longer reproduces the tie"

    assert store.sheet_for("RSR", "race").values["rh_f"] == 60.0
    assert store.sheet_for("RSR", "qualifying").values["rh_f"] == 55.0


def test_an_untouched_pit_loss_is_not_recorded_as_declared(store: Store):
    """`pit_loss_secs` is NOT NULL with the app's own 20.0 in it.

    The column cannot say "he never entered one", which is how the export came
    to label a default `measured-this-track`.  The provenance says it instead.
    """
    untouched = store.create_event(name="A", track="Monza", car_name="RSR",
                                   pit_loss_secs=None, refuel_rate_lps=None)
    row = store.get_event(untouched)
    assert row["pit_loss_source"] is None
    assert row["refuel_rate_source"] is None

    typed = store.create_event(name="B", track="Monza", car_name="RSR",
                               pit_loss_secs=18.5, refuel_rate_lps=1.0)
    row = store.get_event(typed)
    assert row["pit_loss_secs"] == 18.5
    assert row["pit_loss_source"] == "declared"
    assert row["refuel_rate_source"] == "declared"


def test_a_measured_clock_stops_overwriting_the_hour_he_typed(store: Store):
    event_id = store.create_event(name="C", track="Monza", car_name="RSR")
    assert store.record_measured_clock(event_id, 15.933, 6.0) is True

    store.update_event(event_id, start_hour=18.0)
    assert store.get_event(event_id)["clock_source"] == "typed"

    # The next session must not put its own reading back over his correction.
    assert store.record_measured_clock(event_id, 15.933, 6.0) is False
    assert store.get_event(event_id)["start_hour"] == 18.0


def test_re_saving_a_measured_clock_unchanged_keeps_the_measurement(store: Store):
    event_id = store.create_event(name="D", track="Monza", car_name="RSR")
    store.record_measured_clock(event_id, 15.933, 6.0)
    store.update_event(event_id, start_hour=15.933, time_multiplier=6.0)
    assert store.get_event(event_id)["clock_source"] == "measured"


def test_the_voice_self_test_can_fail():
    """It reported success off the back of a queue put, keyed on `enabled` -
    which only means an engine object exists."""
    from pitcrew.engineer.voice import Voice

    class Mute:
        name = "voice-pack"

        def warm(self) -> None:
            pass

        def speak(self, text: str) -> None:
            raise RuntimeError("Error opening OutputStream: Invalid device")

    voice = Voice(engine=Mute())
    assert voice.enabled is True
    spoke, why = voice.say_now("Radio check.")
    assert spoke is False
    assert "Invalid device" in why


def test_reference_data_is_found_from_any_working_directory(tmp_path, monkeypatch):
    """The shortcut runs pythonw with no "Start in", so `data/` read relative
    to the cwd gave a fully-working app with no tracks, no cars and a fresh
    empty database - silently, because a missing catalogue file is an absent
    section by design."""
    from pitcrew.store import catalogs

    monkeypatch.chdir(tmp_path)
    assert len(catalogs.track_names()) > 100
    assert len(catalogs.car_names()) > 100
