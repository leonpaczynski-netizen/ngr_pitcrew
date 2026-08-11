"""The wiring: screens, telemetry and store, driven end to end.

These run against real widgets under an offscreen Qt platform, and feed the
controller real packet bytes rather than mocks - the whole point is to catch
the joins, and a mocked join is not joined.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.controller import PitCrewController, TelemetryBridge
from pitcrew.store.db import Store
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen

from .conftest import make_packet

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def wired(qt_app, store: Store):
    event_screen = EventScreen()
    practice = PracticeScreen()
    controller = PitCrewController(store, event_screen, practice)
    yield controller, event_screen, practice, store
    controller.shutdown()


def an_event(**overrides) -> dict:
    data = {
        "name": "Round 4 - Fuji", "track": "Fuji Speedway", "layout": "Full",
        "car_name": "Porsche 911 RSR (991) '17", "race_type": "laps",
        "race_laps": 20, "weather": "dry", "tyre_wear_mult": "4x",
        "fuel_mult": "2x", "refuel_rate_lps": 2.5, "pit_loss_secs": 20.0,
        "mandatory_stops": 0, "abs_setting": "Weak", "tcs": 1,
        "available_compounds": ["RH", "RM", "RS"],
        "sheet_name": "Fuji race v2",
        "setup_values": {"rh_f": 62.0, "arb_r": 4.0},
        "gear_text": "3.10 2.28 1.79",
    }
    data.update(overrides)
    return data


def raw(**overrides) -> bytes:
    """A packet as bytes, the way the listener would hand it over."""
    packet = make_packet(**overrides)
    from .conftest import raw_packet
    import struct
    data = bytearray(raw_packet(extended=True))
    struct.pack_into("<H", data, 142, packet.flags_raw)
    struct.pack_into("<f", data, 76, packet.speed_ms)
    struct.pack_into("<f", data, 68, packet.fuel_level)
    struct.pack_into("<i", data, 124, packet.last_lap_ms)
    struct.pack_into("<I", data, 128, packet.time_of_day_ms)
    for offset in (180, 184, 188, 192):
        struct.pack_into("<f", data, offset, 0.35)
    data[344:348] = b"TTTT"
    data[364:368] = b"GR3\x00"
    return bytes(data)


# ------------------------------------------------------------------- events

def test_saving_creates_the_event_and_makes_it_active(wired):
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event())

    events = store.list_events()
    assert len(events) == 1
    assert events[0]["name"] == "Round 4 - Fuji"
    assert events[0]["tyre_wear_mult"] == "4x"
    assert store.active_event_id() == events[0]["id"]


def test_saving_the_same_name_updates_rather_than_duplicates(wired):
    controller, _, _, store = wired
    controller._on_event_saved(an_event())
    controller._on_event_saved(an_event(race_laps=30))

    assert len(store.list_events()) == 1
    assert store.list_events()[0]["race_laps"] == 30


def test_the_sheet_is_saved_with_the_event(wired):
    controller, _, _, store = wired
    controller._on_event_saved(an_event())

    sheets = store.list_setup_sheets("Porsche 911 RSR (991) '17")
    assert len(sheets) == 1
    assert sheets[0].sheet_name == "Fuji race v2"
    assert sheets[0].values["rh_f"] == 62.0
    assert sheets[0].gears == [3.10, 2.28, 1.79]


def test_a_refused_sheet_does_not_lose_the_event(wired):
    """Gears out of order are refused - but the event still saves."""
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event(gear_text="1.00 2.00 3.00"))

    assert len(store.list_events()) == 1
    assert store.list_setup_sheets() == []
    assert "refused" in event_screen.footer_note.text()


def test_an_event_round_trips_into_the_form(wired):
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event())

    fresh = EventScreen()
    fresh.load(store.get_event(store.active_event_id()),
               store.list_setup_sheets()[0])
    assert fresh.name_edit.text() == "Round 4 - Fuji"
    assert fresh.pit_loss.value() == 20.0
    assert fresh.tyre_mult.currentText() == "4x"
    assert fresh._compound_chips["RM"].isSelected()
    assert fresh._compound_chips["IM"].isSelected() is False


# ----------------------------------------------------------------- practice

def test_recording_needs_an_event(wired):
    controller, _, practice, store = wired
    controller.start_practice()
    assert controller.session_id is None
    assert store.list_events() == []
    assert "Create an event" in practice.subtitle.text()


def test_a_lap_off_the_stream_reaches_the_store_and_the_rack(wired):
    controller, _, practice, store = wired
    controller._on_event_saved(an_event())
    session_id = controller.open_practice_session()

    bridge = controller.bridge
    bridge.on_packet(raw(speed_ms=50.0, fuel_level=92.0, time_of_day_ms=0))
    bridge.on_packet(raw(speed_ms=50.0, fuel_level=88.6,
                         last_lap_ms=93_912, time_of_day_ms=16))

    stored = store.list_laps(session_id)
    assert len(stored) == 1
    assert stored[0]["lap_time_ms"] == 93_912
    assert round(stored[0]["fuel_used"], 2) == 3.40
    assert store.has_frames(stored[0]["id"])

    assert len(practice.rows()) == 1
    assert practice.rows()[0].lap_time_ms == 93_912


def test_stream_facts_are_recorded_from_the_first_packet(wired):
    controller, _, _, store = wired
    controller._on_event_saved(an_event())
    controller.open_practice_session()

    controller.bridge.on_packet(raw(speed_ms=50.0))
    session = store.get_session(controller.session_id)
    assert session["packet_format"] == "C"
    assert session["car_category"] == "GR3"


def test_frames_are_attributed_to_the_lap_they_belong_to(wired):
    """The rows must detach at the boundary, not after the next frames land."""
    controller, _, _, store = wired
    controller._on_event_saved(an_event())
    controller.open_practice_session()

    bridge = controller.bridge
    for tick in range(5):
        bridge.on_packet(raw(speed_ms=50.0, time_of_day_ms=tick * 16))
    bridge.on_packet(raw(speed_ms=50.0, last_lap_ms=93_912,
                         time_of_day_ms=96))
    for tick in range(3):
        bridge.on_packet(raw(speed_ms=50.0, time_of_day_ms=200 + tick * 16))

    first = store.list_laps(controller.session_id)[0]
    assert store.get_lap_frames(first["id"])["frame_count"] == 6
    assert bridge.recorder.frame_count == 3


def test_a_malformed_packet_is_counted_not_swallowed(wired):
    controller, _, _, _ = wired
    controller.bridge.on_packet(b"nonsense")
    assert controller._parse_errors == 1


# --------------------------------------------------------------- persistence

def test_marks_persist_the_moment_they_are_made(wired):
    controller, _, practice, store = wired
    controller._on_event_saved(an_event())
    session_id = controller.open_practice_session()
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=92.0))
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=88.6,
                                    last_lap_ms=93_912))

    row = practice.rows()[0]
    row.compound = "RM"
    row.excluded = True
    row.wear_front, row.wear_rear = 0.42, 0.35
    controller._on_lap_changed(row.lap_id)

    stored = store.list_laps(session_id)[0]
    assert stored["compound"] == "RM"
    assert stored["excluded"] == 1
    assert stored["exclusion_reason"] == "struck by hand"
    assert stored["wear_front"] == 0.42


def test_reopening_reloads_the_last_session_onto_the_rack(wired):
    controller, _, practice, store = wired
    controller._on_event_saved(an_event())
    session_id = controller.open_practice_session()
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=92.0))
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=88.6,
                                    last_lap_ms=93_912))
    controller._on_lap_changed(practice.rows()[0].lap_id)

    controller.load_active_event()
    assert len(practice.rows()) == 1
    assert practice.rows()[0].lap_time_ms == 93_912


# -------------------------------------------------------------------- export

def test_export_produces_a_validated_payload(wired, tmp_path, monkeypatch):
    import pitcrew.controller as controller_module
    monkeypatch.setattr(controller_module, "EXPORT_DIR", tmp_path / "exports")

    controller, _, practice, store = wired
    controller._on_event_saved(an_event())
    session_id = controller.open_practice_session()
    store.note_stream_facts(session_id, packet_format="C", car_category="GR3")
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=92.0))
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=88.6,
                                    last_lap_ms=93_912))

    text = controller._on_export()
    assert text is not None
    payload = json.loads(text)
    assert payload["format"] == "gt7-pitcrew/1.1"
    assert payload["meta"]["packet"] == "C"
    assert payload["session"]["lapsRun"] == 1
    assert payload["setup"]["values"]["rh_f"] == 62.0

    written = list((tmp_path / "exports").glob("pitcrew-*.json"))
    assert len(written) == 1
    assert json.loads(written[0].read_text(encoding="utf-8")) == payload


def test_export_without_a_session_says_so(wired):
    controller, _, practice, _ = wired
    assert controller._on_export() is None
    assert "Nothing recorded" in practice.footer_note.text()


# -------------------------------------------------------------------- bridge

def test_bridge_reset_clears_state_between_sessions():
    bridge = TelemetryBridge()
    bridge.on_packet(raw(speed_ms=50.0))
    bridge.on_packet(raw(speed_ms=50.0, last_lap_ms=93_912))
    assert bridge.state.lap_count == 1

    bridge.reset()
    assert bridge.state.lap_count == 0
    assert bridge.recorder.frame_count == 0
