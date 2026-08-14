"""The end-to-end join: a recorded session out of the store, into a payload."""
from __future__ import annotations

import json

import pytest

from pitcrew.export.build import (
    build_event_export,
    build_session_export,
    multiplier_factor,
)
from pitcrew.export.payload import to_json, validate
from pitcrew.setup.sheet import RangeRecord, SetupChange, SetupSheet
from pitcrew.store.db import Store
from pitcrew.telemetry.recorder import (
    FRAME_FIELDS,
    clock_span,
    encode_frames,
    standing_start_ms,
)
from pitcrew.telemetry.session_state import Lap

from .test_corners import synthetic_lap


class StoredFrames:
    """Stand-in for LapFrames, so these tests need no packet plumbing.

    It derives the clock span the same way the recorder does rather than
    stubbing it, so a lap stored through here is indistinguishable from one
    that came off the wire.
    """

    def __init__(self, frames: list[dict]) -> None:
        rows = [[f[name] for name in FRAME_FIELDS] for f in frames]
        self.frame_count = len(frames)
        self.sample_hz = 60.0
        self.blob = encode_frames(rows)
        self.tod_start_ms, self.tod_end_ms = clock_span(rows)
        self.standing_start_ms = standing_start_ms(rows, self.sample_hz)


def _frames_as_rows(frames: list[dict]) -> StoredFrames:
    return StoredFrames(frames)


def a_stored_lap(lap_num: int, **overrides) -> Lap:
    """One lap of a run, the tank where it would be that far in.

    Fuel is what tells one run from the next, so a fixture whose tank refills
    itself every lap describes a session of consecutive pit stops - and gets
    read as one.
    """
    fields = dict(
        lap_num=lap_num, lap_time_ms=94_000, best_lap_ms=93_000, delta_ms=1_000,
        fuel_start=round(100.0 - 3.4 * (lap_num - 1), 2),
        fuel_end=round(100.0 - 3.4 * lap_num, 2), fuel_used=3.4, position=3,
        is_pit_lap=False, is_out_lap=False,
    )
    fields.update(overrides)
    return Lap(**fields)


@pytest.fixture()
def recorded(store: Store):
    """An event with a practice session of four laps, three of them counted."""
    event_id = store.create_event(
        name="Fuji round", track="Fuji Speedway", layout="Full",
        car_id=123, car_name="Porsche 911 RSR (991) '17",
        race_type="laps", race_laps=20,
        tyre_wear_mult="4x", fuel_mult="2x",
        game_version="1.70", abs_setting="Weak", tcs=1, countersteer=0,
        available_compounds=["RH", "RM", "RS"])

    sheet_id = store.save_setup_sheet(SetupSheet(
        car_name="Porsche 911 RSR (991) '17", sheet_name="Fuji race v2",
        values={"rh_f": 62, "arb_r": 4}, gears=[3.10, 2.28, 1.79]))
    store.save_range_record(RangeRecord(
        car_name="Porsche 911 RSR (991) '17", measured_date="2026-08-11",
        ranges={"rh_f": [55, 80], "arb_r": [1, 10]}, verified=True))

    session_id = store.start_session(event_id, "practice", setup_sheet_id=sheet_id)
    store.note_stream_facts(session_id, packet_format="C", car_category="GR3",
                            fuel_capacity_l=100.0)
    store.add_setup_change(session_id, SetupChange(3, "arb_r", 4, 3))

    frames = synthetic_lap(apex_positions=(300.0, 900.0, 1500.0))
    for lap_num, kwargs in enumerate([
        {"is_out_lap": True, "lap_time_ms": 140_000},
        {"lap_time_ms": 94_000},
        {"lap_time_ms": 93_500},
        {"lap_time_ms": 94_200},
    ], start=1):
        lap_id = store.add_lap(session_id, a_stored_lap(lap_num, **kwargs),
                               frames=_frames_as_rows(frames))
        if lap_num > 1:
            store.set_lap_compound(lap_id, "RM")
    return {"event_id": event_id, "session_id": session_id}


def test_payload_validates_end_to_end(store: Store, recorded):
    payload = build_session_export(store, recorded["session_id"])
    assert validate(payload) == []
    assert json.loads(to_json(payload)) == payload


def test_meta_comes_from_event_and_stream(store: Store, recorded):
    meta = build_session_export(store, recorded["session_id"])["meta"]
    assert meta["car"] == "Porsche 911 RSR (991) '17"
    assert meta["circuit"] == "Fuji Speedway (Full)"
    assert meta["sessionType"] == "practice"
    assert meta["packet"] == "C"
    assert meta["carCategory"] == "GR3"
    assert meta["multipliers"]["tyreWear"] == "4x"
    assert meta["assists"]["abs"] == "Weak"


def test_compound_is_reported_by_full_name(store: Store, recorded):
    meta = build_session_export(store, recorded["session_id"])["meta"]
    assert meta["compound"]["front"] == "Racing Medium"
    assert meta["compound"]["rear"] == "Racing Medium"


def test_setup_and_range_record_ride_along(store: Store, recorded):
    payload = build_session_export(store, recorded["session_id"])
    assert payload["setup"]["sheetName"] == "Fuji race v2"
    assert payload["setup"]["driverChanges"][0]["key"] == "arb_r"
    assert payload["rangeRecord"]["verified"] is True
    assert payload["rangeRecord"]["r"]["rh_f"] == [55, 80]


def test_out_lap_is_excluded_and_explained(store: Store, recorded):
    payload = build_session_export(store, recorded["session_id"])
    assert payload["session"]["lapsRun"] == 4
    assert payload["session"]["lapsCounted"] == 3
    assert payload["session"]["lapsExcluded"] == [1]
    detail = payload["session"]["lapsExcludedDetail"]
    assert detail == [{"lap": 1, "reason": "out-lap", "source": "auto"}]


def test_extra_notes_are_appended(store: Store, recorded):
    payload = build_session_export(store, recorded["session_id"],
                                   notes="Rear ARB changed lap 3.")
    assert "Rear ARB changed lap 3." in payload["notes"]


def test_notes_no_longer_repeat_what_the_structure_already_says(
        store: Store, recorded):
    """Eight repetitions of "struck by hand" qualified nothing.

    The reason and its source live in `lapsExcludedDetail`; prose is for what
    the structure cannot hold.
    """
    payload = build_session_export(store, recorded["session_id"])
    assert "out-lap" not in payload.get("notes", "")


def test_the_driver_own_words_survive_the_classification(store: Store, recorded):
    lap_id = store.list_laps(recorded["session_id"])[2]["id"]
    store.exclude_lap(lap_id, "spun at T4")
    payload = build_session_export(store, recorded["session_id"])
    entry = [e for e in payload["session"]["lapsExcludedDetail"]
             if e["lap"] == 3][0]
    assert entry["reason"] == "manual"
    assert entry["source"] == "driver"
    assert entry["note"] == "spun at T4"
    assert "spun at T4" in payload["notes"]


def test_corners_are_built_and_declared(store: Store, recorded):
    payload = build_session_export(store, recorded["session_id"])
    assert payload["meta"]["cornerModel"]["source"] == "auto-segment"
    assert payload["meta"]["cornerModel"]["id"] == "fuji-speedway-full"
    assert len(payload["corners"]) == 3
    for corner in payload["corners"]:
        assert corner["samples"] == 3


def test_derived_carries_thresholds_and_bottoming_reference(store: Store, recorded):
    derived = build_session_export(store, recorded["session_id"])["derived"]
    assert derived["thresholds"]["lockupPct"] == 15
    assert derived["steerSource"] == "wheelRotation"
    assert derived["bottomingRefMm"]["fl"] == 60.0


def test_wear_says_the_channel_does_not_exist(store: Store, recorded):
    wear = build_session_export(store, recorded["session_id"])["wear"]
    assert wear["channelAvailable"] is False
    assert wear["modelledStintLaps"] is None
    assert wear["modelConfidence"] == "assumed"


def test_a_gauge_reading_promotes_the_model_to_measured(store: Store, recorded):
    lap_id = store.list_laps(recorded["session_id"])[-1]["id"]
    store.set_lap_wear(lap_id, 0.4, 0.4, 0.3, 0.3)
    first_lap_id = store.list_laps(recorded["session_id"])[0]["id"]
    store.set_lap_tyres_fresh(first_lap_id, True)
    wear = build_session_export(store, recorded["session_id"])["wear"]
    assert wear["modelConfidence"] == "measured"
    assert wear["byDriverGauge"][0]["fl"] == 0.4
    assert wear["byDriverGauge"][0]["rr"] == 0.3
    assert wear["modelledStintLaps"] == 8


def test_strategy_section_is_absent_until_it_exists(store: Store, recorded):
    assert "strategy" not in build_session_export(store, recorded["session_id"])


def test_a_session_with_no_setup_sheet_omits_the_section(store: Store, recorded):
    event_id = recorded["event_id"]
    bare = store.start_session(event_id, "practice")
    store.note_stream_facts(bare, packet_format="C")
    store.add_lap(bare, a_stored_lap(1))
    payload = build_session_export(store, bare)
    assert "setup" not in payload
    assert "corners" not in payload
    assert validate(payload) == []


def test_unknown_session_is_refused(store: Store):
    with pytest.raises(ValueError, match="no session"):
        build_session_export(store, 999)


def test_packet_format_defaults_to_the_base_set(store: Store, recorded):
    """Never null: the contract requires it, and 'A' is the honest floor."""
    bare = store.start_session(recorded["event_id"], "practice")
    store.add_lap(bare, a_stored_lap(1))
    assert build_session_export(store, bare)["meta"]["packet"] == "A"


# ------------------------------------------------------------- multipliers

def test_multiplier_off_is_a_factor_of_zero():
    """Off means the thing does not happen at all, not that it happens once."""
    assert multiplier_factor("Off") == 0.0


def test_multiplier_parses_the_x_suffix():
    assert multiplier_factor("4x") == 4.0
    assert multiplier_factor("1x") == 1.0


def test_unset_multiplier_is_none():
    assert multiplier_factor(None) is None
    assert multiplier_factor("") is None


def test_nonsense_multiplier_is_none_not_a_guess():
    assert multiplier_factor("fast") is None


# ------------------------------------------------------- accumulating runs

def test_a_second_run_adds_to_the_event_rather_than_replacing_it(store, recorded):
    """Going out again is more evidence about one car, not a fresh start."""
    from pitcrew.export.build import build_event_export

    event_id = recorded["event_id"]
    second = store.start_session(event_id, "practice")
    store.add_lap(second, a_stored_lap(1, lap_time_ms=93_300))
    store.add_lap(second, a_stored_lap(2, lap_time_ms=93_100))

    payload = build_event_export(store, event_id)
    assert payload["session"]["lapsRun"] == 6      # 4 from the first run + 2
    # The later run's flyer is in the aggregate, which is the whole point.
    assert payload["session"]["bestLapMs"] == 93_100


def test_laps_are_renumbered_continuously_across_runs(store, recorded):
    """Two laps both called "lap 1" in one export would be unreadable."""
    from pitcrew.export.build import build_event_export

    event_id = recorded["event_id"]
    second = store.start_session(event_id, "practice")
    store.add_lap(second, a_stored_lap(1))
    store.add_lap(second, a_stored_lap(2))

    numbers = [lap["lap"] for lap in build_event_export(store, event_id)["laps"]]
    assert numbers == [1, 2, 3, 4, 5, 6]


def test_stream_facts_survive_a_later_run_that_saw_none(store, recorded):
    """A run started before GT7 was streaming must not erase what was measured."""
    from pitcrew.export.build import build_event_export

    event_id = recorded["event_id"]
    later = store.start_session(event_id, "practice")
    store.add_lap(later, a_stored_lap(1))

    payload = build_event_export(store, event_id)
    assert payload["meta"]["packet"] == "C"
    assert payload["meta"]["carCategory"] == "GR3"
    assert payload["session"]["fuelCapacityL"] == 100.0


def test_an_event_with_nothing_recorded_refuses(store):
    from pitcrew.export.build import build_event_export
    event_id = store.create_event(name="Empty", track="Spa")
    with pytest.raises(ValueError, match="nothing recorded"):
        build_event_export(store, event_id)


# --------------------------------------------------------- the version gate

def test_an_event_with_no_version_exports_on_the_app_setting(store: Store, recorded):
    """The refusal he was hitting, and where the answer now comes from.

    `meta.gameVersion` is required — a measurement that does not say which
    update it was taken under cannot be compared with the next one, and GT7
    has rewritten its physics twice in two updates. It was asked for per
    event, so an event created without it produced an export refused outright
    with nothing on screen connecting the empty box to the failure.
    """
    store.update_event(recorded["event_id"], game_version=None)
    payload = build_event_export(store, recorded["event_id"],
                                 game_version="1.70")
    assert payload["meta"]["gameVersion"] == "1.70"


def test_a_version_on_the_event_still_wins(store: Store, recorded):
    """A measurement taken under a version that is no longer installed keeps
    the version it was taken under."""
    store.update_event(recorded["event_id"], game_version="1.55")
    payload = build_event_export(store, recorded["event_id"],
                                 game_version="1.70")
    assert payload["meta"]["gameVersion"] == "1.55"
