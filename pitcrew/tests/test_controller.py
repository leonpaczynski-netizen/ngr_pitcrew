"""The wiring: screens, telemetry and store, driven end to end.

These run against real widgets under an offscreen Qt platform, and feed the
controller real packet bytes rather than mocks - the whole point is to catch
the joins, and a mocked join is not joined.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.controller import PitCrewController, TelemetryBridge
from pitcrew.export.payload import FORMAT
from pitcrew.store.db import Store
from pitcrew.ui.event_screen import EMPTY, EventScreen
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
        "game_version": "1.70",
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
    struct.pack_into("<H", data, 136, packet.rpm_alert_min)
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


def test_saving_an_event_that_was_loaded_updates_it(wired):
    """The id decides what is written, so a rename edits rather than forks."""
    controller, _, _, store = wired
    controller._on_event_saved(an_event())
    event_id = store.active_event_id()

    controller._on_event_saved(an_event(id=event_id, race_laps=30,
                                        name="Round 4 - Fuji (wet)"))

    assert len(store.list_events()) == 1
    assert store.list_events()[0]["id"] == event_id
    assert store.list_events()[0]["race_laps"] == 30
    assert store.list_events()[0]["name"] == "Round 4 - Fuji (wet)"


def test_a_new_event_cannot_take_a_name_already_in_use(wired):
    """The old screen overwrote the stored event instead, in silence."""
    controller, event_screen, _, store = wired
    controller._on_event_saved(an_event())
    first = store.get_event(store.active_event_id())

    # No id: a form filled in for a different round, on the same name.
    controller._on_event_saved(an_event(track="Bathurst", race_laps=30))

    assert len(store.list_events()) == 1
    assert store.get_event(first["id"])["track"] == "Fuji Speedway"
    assert store.get_event(first["id"])["race_laps"] == 20
    assert "already called" in event_screen.footer_note.text()


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
    row.set_wear({"fl": 0.42, "fr": 0.38, "rl": 0.35, "rr": 0.35})
    controller._on_lap_changed(row.lap_id)

    stored = store.list_laps(session_id)[0]
    assert stored["compound"] == "RM"
    assert stored["excluded"] == 1
    assert stored["exclusion_reason"] == "struck by hand"
    assert stored["wear_fl"] == 0.42
    assert stored["wear_fr"] == 0.38
    assert stored["wear_rr"] == 0.35


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

def test_a_fresh_set_declared_on_the_rack_reaches_the_export(wired):
    """The whole point of the control: the rack is the only place this fact
    can enter the app, and it has to survive all the way to `runs[]`."""
    from pitcrew.export.build import build_event_export

    controller, _, practice, store = wired
    controller._on_event_saved(an_event())
    session_id = controller.open_practice_session()
    store.note_stream_facts(session_id, packet_format="C",
                            fuel_capacity_l=100.0)
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=100.0))
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=93.5,
                                    last_lap_ms=93_912))

    row = practice.rows()[0]
    assert row.lap_id is not None
    row.tyres_fresh = True
    controller._on_lap_changed(row.lap_id)

    assert store.list_laps(session_id)[0]["tyres_fresh"] == 1
    runs = build_event_export(store, store.active_event_id())["runs"]
    assert runs[0]["tyresFresh"] is True
    assert runs[0]["tyresFreshSource"] == "driver-declared at the run's first lap"


def test_an_undeclared_set_stays_null_all_the_way_out(wired):
    """Never false. "He has not said" and "the set carried over" are
    different claims and the export must not conflate them."""
    from pitcrew.export.build import build_event_export

    controller, _, practice, store = wired
    controller._on_event_saved(an_event())
    session_id = controller.open_practice_session()
    store.note_stream_facts(session_id, packet_format="C",
                            fuel_capacity_l=100.0)
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=100.0))
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=93.5,
                                    last_lap_ms=93_912))

    runs = build_event_export(store, store.active_event_id())["runs"]
    assert runs[0]["tyresFresh"] is None


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
    assert payload["format"] == FORMAT
    assert payload["meta"]["packet"] == "C"
    assert payload["session"]["lapsRun"] == 1
    assert payload["setup"]["values"]["rh_f"] == 62.0

    written = list((tmp_path / "exports").glob("pitcrew-*.json"))
    assert len(written) == 1
    assert json.loads(written[0].read_text(encoding="utf-8")) == payload


def test_export_without_an_event_says_so(wired):
    controller, _, practice, _ = wired
    assert controller._on_export() is None
    assert "Create an event" in practice.footer_note.text()


def test_export_with_an_event_but_no_laps_says_so(wired):
    controller, _, practice, _ = wired
    controller._on_event_saved(an_event())
    assert controller._on_export() is None
    assert "nothing recorded" in practice.footer_note.text().lower()


# -------------------------------------------------------------------- bridge

def test_bridge_reset_clears_state_between_sessions():
    bridge = TelemetryBridge()
    bridge.on_packet(raw(speed_ms=50.0))
    bridge.on_packet(raw(speed_ms=50.0, last_lap_ms=93_912))
    assert bridge.state.lap_count == 1

    bridge.reset()
    assert bridge.state.lap_count == 0
    assert bridge.recorder.frame_count == 0


# ---------------------------------------------------------------- switching

def two_events(controller, store):
    """Two saved events, the way a driver preparing for two rounds has them."""
    controller._on_event_saved(an_event())
    porsche = store.active_event_id()
    controller._on_event_saved(an_event(
        name="V8s - Bathurst", track="Bathurst", layout=None,
        car_name="Ford Falcon Gr.3", race_laps=32, tyre_wear_mult="6x",
        pit_loss_secs=27.5, sheet_name="Bathurst race v1",
        setup_values={"rh_f": 80.0}, gear_text=""))
    v8 = store.active_event_id()
    return porsche, v8


def test_saving_a_second_event_leaves_the_first_alone(wired):
    controller, _, _, store = wired
    porsche, v8 = two_events(controller, store)

    assert porsche != v8
    assert len(store.list_events()) == 2
    kept = store.get_event(porsche)
    assert kept["track"] == "Fuji Speedway"
    assert kept["race_laps"] == 20
    assert kept["tyre_wear_mult"] == "4x"


def test_the_picker_lists_every_event_and_a_way_to_start_another(wired):
    from pitcrew.ui.event_screen import NEW_EVENT

    controller, event_screen, _, store = wired
    porsche, v8 = two_events(controller, store)

    picker = event_screen.event_picker
    ids = [picker.itemData(i) for i in range(picker.count())]
    assert sorted(i for i in ids if i is not None) == sorted([porsche, v8])
    assert picker.itemText(picker.count() - 1) == NEW_EVENT
    # The one being worked on is the one showing.
    assert picker.currentData() == v8


def test_switching_back_reloads_the_event_it_was_saved_as(wired):
    controller, event_screen, _, store = wired
    porsche, v8 = two_events(controller, store)

    controller.switch_event(porsche)

    assert store.active_event_id() == porsche
    assert event_screen.name_edit.text() == "Round 4 - Fuji"
    assert event_screen.track_edit.currentText() == "Fuji Speedway"
    assert event_screen.race_length.value() == 20
    assert event_screen.tyre_mult.currentText() == "4x"
    assert event_screen.pit_loss.value() == 20.0
    assert event_screen.values()["id"] == porsche


def test_switching_writes_nothing_to_either_event(wired):
    """A switch is a read. Both rows come back byte for byte."""
    controller, _, _, store = wired
    porsche, v8 = two_events(controller, store)
    before = store.get_event(porsche), store.get_event(v8)

    controller.switch_event(porsche)
    controller.switch_event(v8)
    controller.switch_event(porsche)

    assert (store.get_event(porsche), store.get_event(v8)) == before


def test_a_sheet_does_not_follow_the_driver_to_an_event_without_one(wired):
    """The bug this feature would otherwise have shipped with.

    A round with no sheet yet is the ordinary state of the next race on the
    calendar. Loading it used to leave the previous car's springs, dampers
    and gears on the form - and the next save would file them against it.
    """
    controller, event_screen, _, store = wired
    porsche, _ = two_events(controller, store)
    controller._on_event_saved(an_event(
        name="Gr.3 - Monza", track="Monza", layout=None,
        car_name="Nissan GT-R Gr.3", race_laps=18,
        sheet_name="", setup_values={}, gear_text="",
        priority="", start_type="", time_of_day=""))
    monza = store.active_event_id()

    controller.switch_event(porsche)
    assert event_screen._setup_editors["arb_r"].value() == 4.0
    assert event_screen.gear_edit.text() != ""

    controller.switch_event(monza)

    assert event_screen._setup_editors["arb_r"].value() == EMPTY
    assert event_screen._setup_editors["rh_f"].value() == EMPTY
    assert event_screen.sheet_name.text() == ""
    assert event_screen.gear_edit.text() == ""
    assert event_screen.values()["setup_values"] == {}


def test_a_sheet_does_not_follow_the_driver_to_another_car(wired):
    controller, event_screen, _, store = wired
    porsche, v8 = two_events(controller, store)
    controller.switch_event(porsche)
    assert event_screen._setup_editors["arb_r"].value() == 4.0

    controller.switch_event(v8)

    assert event_screen._setup_editors["arb_r"].value() == EMPTY
    assert event_screen._setup_editors["rh_f"].value() == 80.0


def test_practice_laps_stay_with_the_event_they_were_run_at(wired):
    controller, _, practice, store = wired
    porsche, v8 = two_events(controller, store)

    controller.switch_event(porsche)
    session = controller.open_practice_session()
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=92.0,
                                    time_of_day_ms=0))
    controller.bridge.on_packet(raw(speed_ms=50.0, fuel_level=88.6,
                                    last_lap_ms=93_912, time_of_day_ms=16))
    assert len(store.list_laps(session)) == 1

    controller.stop_practice()
    controller.switch_event(v8)
    assert practice.rows() == []
    assert store.list_event_laps(v8) == []

    controller.switch_event(porsche)
    assert len(practice.rows()) == 1
    assert practice.rows()[0].lap_time_ms == 93_912


def test_switching_with_unsaved_edits_asks_before_discarding_them(wired):
    controller, event_screen, _, store = wired
    porsche, v8 = two_events(controller, store)
    picker = event_screen.event_picker
    index = picker.findData(porsche)

    event_screen.pit_loss.setValue(31.0)
    assert event_screen.is_dirty()

    event_screen._on_picker_activated(index)
    assert store.active_event_id() == v8            # nothing happened
    assert picker.currentData() == v8               # and the picker says so
    assert event_screen.pit_loss.value() == 31.0    # the edit survives
    assert "Unsaved changes" in event_screen.footer_note.text()

    event_screen._on_picker_activated(index)
    assert store.active_event_id() == porsche
    assert event_screen.pit_loss.value() == 20.0


def test_a_clean_form_switches_on_the_first_pick(wired):
    controller, event_screen, _, store = wired
    porsche, _ = two_events(controller, store)

    event_screen._on_picker_activated(
        event_screen.event_picker.findData(porsche))

    assert store.active_event_id() == porsche


def test_new_event_blanks_the_form_and_stops_recording_against_the_old_one(wired):
    """Otherwise a session started here files laps under the event on screen
    a moment ago, which is the failure this whole feature is for."""
    controller, event_screen, practice, store = wired
    porsche, v8 = two_events(controller, store)

    controller.switch_event(None)

    assert store.active_event_id() is None
    assert event_screen.name_edit.text() == ""
    assert event_screen.values()["id"] is None
    assert event_screen._setup_editors["rh_f"].value() == EMPTY
    # Nothing was deleted to get here.
    assert len(store.list_events()) == 2
    assert store.get_event(porsche)["track"] == "Fuji Speedway"

    controller.start_practice()
    assert controller.session_id is None


def test_an_event_deleted_elsewhere_is_refused_not_crashed_into(wired):
    controller, event_screen, _, store = wired
    porsche, v8 = two_events(controller, store)
    store.delete_event(porsche)

    controller.switch_event(porsche)

    assert store.active_event_id() == v8
    assert "no longer in the store" in event_screen.footer_note.text()


def test_a_lap_that_never_crossed_the_line_is_not_counted_as_one(wired):
    """Reported from the seat twice, and the second time with numbers.

    Two and a third laps driven, three recorded, laps two and three carrying
    the SAME time. GT7's `last_lap_ms` is a reliable crossing signal while the
    stream is continuous, but leaving the session drops it and brings it back -
    and a value that has changed away and back looks exactly like a new lap
    time. The fragment then inherits a whole lap's time: 1,306 frames of
    telemetry claiming 110.9 seconds.

    The claimed time is what does the damage. A lap time on the record is a
    number something will eventually average, rank or fit a degradation curve
    through, and this one was never set. So it is cleared, the lap is excluded,
    and it never reaches the rack - he sees the laps he drove. The frames stay
    on disk, because doubtful evidence is quarantined here and never deleted.

    Driven through `_on_lap_completed` directly rather than by monkeypatching
    the recorder: replacing a method on a Qt-owned object keeps the closure
    alive past teardown and segfaults the interpreter on Windows/Py3.14, which
    costs the whole run its output and looks nothing like a test failure.
    """
    from pitcrew.telemetry.recorder import FRAME_FIELDS
    from pitcrew.telemetry.session_state import Lap

    controller, _, practice, store = wired
    controller._on_event_saved(an_event())
    session_id = controller.open_practice_session()

    # 1,306 frames is 21.8 s at 60 Hz - the real number off the real session.
    row = [None] * len(FRAME_FIELDS)
    row[FRAME_FIELDS.index("t_ms")] = 0
    row[FRAME_FIELDS.index("speed_kph")] = 180.0
    rows = [list(row) for _ in range(1306)]
    for index, one in enumerate(rows):
        one[FRAME_FIELDS.index("t_ms")] = int(index * 1000 / 60)

    lap = Lap(lap_num=3, lap_time_ms=110_921, best_lap_ms=110_921,
              delta_ms=0, fuel_start=88.0, fuel_end=85.0, fuel_used=3.0,
              position=1, is_pit_lap=False, is_out_lap=False)
    controller._on_lap_completed(lap, rows)

    stored = store.list_laps(session_id)
    assert len(stored) == 1, "the frames should still be on disk"
    assert stored[0]["lap_time_ms"] == 0, (
        "it kept a lap time it never set - something will average that")
    assert stored[0]["excluded"] == 1
    assert stored[0]["exclusion_reason"] == "fragment"
    assert practice.rows() == [], "a lap he did not complete reached the rack"
