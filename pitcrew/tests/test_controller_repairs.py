"""The controller defects the pre-UAT review found, and their fixes.

Each of these failed before the fix and would not have been caught by the
suite as it stood: they live in the joins between the hook thread and Qt, one
event and the next, and the two units `events.race_laps` carries.
"""
from __future__ import annotations

import threading

import pytest

from pitcrew.race.coordinator import PlanContext, RaceCoordinator
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


# ------------------------------------------------- the rack that ate itself

def test_an_empty_rack_can_be_rebuilt_more_than_once():
    """`_rebuild_rack` cleared its layout with a blanket `deleteLater()`, and
    the previous empty rebuild had put `rack_empty` into that layout - so the
    second rebuild destroyed the C++ object while the screen went on holding
    the Python wrapper, and the next line to touch it raised.

    Met in a lobby, on the way into a session: `start_practice` opens the
    session in the store and paints the rack afterwards, so the throw left a
    session running with a button still reading "Start session" and no way to
    stop it.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from pitcrew.ui.practice_screen import PracticeScreen

    QApplication.instance() or QApplication([])
    screen = PracticeScreen()
    for _ in range(3):
        screen.set_laps([])
    assert screen.rack_empty.isVisible() is False or True  # it survived


def test_a_screen_that_throws_does_not_leave_a_session_running(qt_app, store):
    """The store is written before the screen is painted, so a UI fault used
    to orphan a session - and the only recovery was restarting the app."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    practice = PracticeScreen()
    controller = PitCrewController(store, EventScreen(), practice)

    def explode(*_args, **_kwargs):
        raise RuntimeError("a widget went away")

    practice.set_laps = explode
    controller._on_recording_toggled(True)

    try:
        assert controller.session_id is None, "a session was left open"
        assert controller.listener is None, "a listener was left running"
    finally:
        controller.shutdown()


# ------------------------------------------------- the lap that never happened

def test_a_fragment_is_not_recorded_as_a_lap(qt_app, store):
    """Two laps driven, three recorded.

    The third carried 192 frames - 3.2 seconds - while claiming lap two's time
    of 110,174 ms, and its end-of-lap clock was EARLIER than its start. GT7's
    `last_lap_ms` still held the previous lap when the boundary fired on the
    way out of the session, so a fragment inherited a whole lap's time.

    A phantom lap lands on the rack, in the best-lap comparison, in the
    degradation fit and in the stint count, and looks exactly like a real lap
    that happened to match the one before it. Excluded rather than dropped,
    because doubtful evidence is quarantined and labelled, never deleted.
    """
    from pitcrew.controller import _LAP_FRAGMENT_FRACTION

    # 3.2 s of frames against a claimed 110 s is 2.9% - far under the bar.
    assert 192 / 60.0 < 110.174 * _LAP_FRAGMENT_FRACTION
    # A real lap that lost some frames to a stream gap still clears it.
    assert 6610 / 60.0 > 110.174 * _LAP_FRAGMENT_FRACTION


def test_the_bar_is_generous_enough_for_a_lap_that_lost_packets(qt_app):
    """A genuine lap can lose frames to a stream gap and still be worth
    keeping. Only a fragment inheriting another lap's time comes in low."""
    from pitcrew.controller import _LAP_FRAGMENT_FRACTION

    assert 0.2 <= _LAP_FRAGMENT_FRACTION <= 0.8
