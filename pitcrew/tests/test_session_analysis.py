"""Per-lap and run-level aggregation, and corner-model persistence."""
from __future__ import annotations

import pytest

from pitcrew.analysis.corner_model import detect_corners
from pitcrew.analysis.resolve import circuit_key, resolve_corner_model
from pitcrew.analysis.session import (
    LapInput,
    counted_laps,
    exclusion_note,
    green_lap_reference_ms,
    lap_export,
    laps_per_stint,
    session_export,
)
from pitcrew.store.db import Store

from .test_corners import frame, synthetic_lap


def a_lap(lap_num: int = 1, **overrides) -> LapInput:
    fields = dict(lap_num=lap_num, lap_time_ms=94_000,
                  fuel_start=92.0, fuel_end=88.6)
    fields.update(overrides)
    return LapInput(**fields)


def temp_frames(**temps) -> list[dict]:
    base = {"temp_fl": 84.0, "temp_fr": 79.0, "temp_rl": 81.0, "temp_rr": 82.0}
    base.update(temps)
    return [frame(i * 2.0, 200.0, i, **base) for i in range(20)]


# ------------------------------------------------------------------ counting

def test_out_laps_and_in_laps_do_not_count():
    laps = [a_lap(1, is_out_lap=True), a_lap(2), a_lap(3, is_pit_lap=True)]
    assert [lap.lap_num for lap in counted_laps(laps)] == [2]


def test_driver_exclusions_do_not_count():
    laps = [a_lap(1), a_lap(2, excluded=True, exclusion_reason="traffic")]
    assert [lap.lap_num for lap in counted_laps(laps)] == [1]


def test_exclusion_reasons_default_to_the_structural_cause():
    assert a_lap(1, is_out_lap=True).reason_not_counted() == "out-lap"
    assert a_lap(1, is_pit_lap=True).reason_not_counted() == "in-lap"
    assert a_lap(1).reason_not_counted() is None


def test_a_stated_reason_wins_over_the_structural_one():
    lap = a_lap(1, is_out_lap=True, excluded=True, exclusion_reason="spun at T4")
    assert lap.reason_not_counted() == "spun at T4"


def test_exclusion_note_names_laps_and_reasons():
    laps = [a_lap(1, is_out_lap=True),
            a_lap(2),
            a_lap(3, excluded=True, exclusion_reason="traffic")]
    note = exclusion_note(laps)
    assert "lap 1 out-lap" in note
    assert "lap 3 traffic" in note
    assert "lap 2" not in note


def test_no_exclusions_gives_an_empty_note():
    assert exclusion_note([a_lap(1), a_lap(2)]) == ""


# ---------------------------------------------------------------------- laps

def test_lap_export_shape():
    payload = lap_export(a_lap(3, frames=temp_frames()))
    assert payload["lap"] == 3
    assert payload["timeMs"] == 94_000
    assert payload["valid"] is True
    assert payload["fuelStartL"] == 92.0
    assert payload["tyreTempMeanC"]["fl"] == 84.0
    assert payload["tyreTempMaxC"]["fl"] == 84.0


def test_tyre_temperature_reports_mean_and_max_separately():
    """The mean gives the working range; the max shows what is being abused."""
    frames = temp_frames()
    frames[10]["temp_fl"] = 120.0
    payload = lap_export(a_lap(1, frames=frames))
    assert payload["tyreTempMaxC"]["fl"] == 120.0
    assert payload["tyreTempMeanC"]["fl"] < 120.0


def test_lap_without_frames_reports_null_temperatures():
    payload = lap_export(a_lap(1))
    assert payload["tyreTempMeanC"] is None
    assert payload["offTrackCount"] is None


def test_fuel_map_is_null_unless_the_driver_says():
    """GT7 does not broadcast it, so it is never inferred."""
    assert lap_export(a_lap(1))["fuelMap"] is None
    assert lap_export(a_lap(1, fuel_map=3))["fuelMap"] == 3


def test_off_track_counts_excursions_not_frames():
    frames = temp_frames()
    for f in frames[5:12]:
        f["surf_rl"] = "G"
    assert lap_export(a_lap(1, frames=frames))["offTrackCount"] == 1


def test_two_separate_offs_count_twice():
    frames = temp_frames()
    frames[3]["surf_rl"] = "G"
    frames[15]["surf_rl"] = "G"
    assert lap_export(a_lap(1, frames=frames))["offTrackCount"] == 2


def test_kerbs_are_not_off_track():
    frames = temp_frames()
    for f in frames[5:10]:
        f["surf_rl"] = "C"
    assert lap_export(a_lap(1, frames=frames))["offTrackCount"] == 0


def test_off_track_is_null_without_a_surface_channel():
    frames = [frame(i * 2.0, 200.0, i, surf_fl=None, surf_fr=None,
                    surf_rl=None, surf_rr=None) for i in range(20)]
    assert lap_export(a_lap(1, frames=frames))["offTrackCount"] is None


# ------------------------------------------------------------------- session

def test_session_totals():
    laps = [a_lap(1, is_out_lap=True),
            a_lap(2, lap_time_ms=94_000),
            a_lap(3, lap_time_ms=93_000),
            a_lap(4, lap_time_ms=95_000)]
    payload = session_export(laps, fuel_capacity_l=100.0)
    assert payload["lapsRun"] == 4
    assert payload["lapsCounted"] == 3
    assert payload["lapsExcluded"] == [1]
    assert payload["bestLapMs"] == 93_000
    assert payload["medianLapMs"] == 94_000
    assert payload["fuelCapacityL"] == 100.0


def test_median_not_mean_so_one_bad_lap_does_not_move_it():
    laps = [a_lap(1, lap_time_ms=93_000), a_lap(2, lap_time_ms=93_500),
            a_lap(3, lap_time_ms=94_000), a_lap(4, lap_time_ms=200_000)]
    payload = session_export(laps)
    assert payload["medianLapMs"] == 93_750
    assert payload["medianLapMs"] < 95_000


def test_fuel_per_lap_ignores_refuelling_laps():
    laps = [a_lap(1, fuel_start=92.0, fuel_end=88.6),
            a_lap(2, fuel_start=88.6, fuel_end=85.2),
            a_lap(3, fuel_start=85.2, fuel_end=100.0)]   # refuelled
    assert session_export(laps)["fuelUsedPerLapL"] == 3.4


def test_zero_fuel_capacity_is_a_real_value():
    """Electric cars. Not missing - the divide has to be guarded, not the field."""
    assert session_export([a_lap(1)], fuel_capacity_l=0.0)["fuelCapacityL"] == 0.0


def test_a_session_with_no_counted_laps_reports_nulls_not_zeros():
    payload = session_export([a_lap(1, is_out_lap=True)])
    assert payload["lapsCounted"] == 0
    assert payload["bestLapMs"] is None
    assert payload["medianLapMs"] is None
    assert payload["fuelUsedPerLapL"] is None


def test_std_dev_needs_more_than_one_lap():
    assert session_export([a_lap(1)])["lapTimeStdDevMs"] is None
    assert session_export([a_lap(1, lap_time_ms=93_000),
                           a_lap(2, lap_time_ms=95_000)])["lapTimeStdDevMs"] == 1000


# ------------------------------------------------------------- green lap ref

def test_green_lap_comes_from_the_early_laps_not_the_session_best():
    """Tyres are freshest at the start; a late flyer is not a fresh-tyre lap."""
    laps = [a_lap(1, lap_time_ms=94_000), a_lap(2, lap_time_ms=93_800),
            a_lap(3, lap_time_ms=94_100), a_lap(4, lap_time_ms=92_000)]
    assert green_lap_reference_ms(laps) == 93_800
    assert session_export(laps)["bestLapMs"] == 92_000


def test_green_lap_skips_the_out_lap():
    laps = [a_lap(1, lap_time_ms=140_000, is_out_lap=True),
            a_lap(2, lap_time_ms=94_000)]
    assert green_lap_reference_ms(laps) == 94_000


def test_green_lap_is_none_without_counted_laps():
    assert green_lap_reference_ms([a_lap(1, is_out_lap=True)]) is None


# -------------------------------------------------------------------- stints

def test_stints_split_at_each_pit_lap():
    laps = [a_lap(1), a_lap(2), a_lap(3, is_pit_lap=True), a_lap(4), a_lap(5)]
    stints = laps_per_stint(laps)
    assert [[lap.lap_num for lap in stint] for stint in stints] == [[1, 2, 3], [4, 5]]


def test_a_session_without_a_stop_is_one_stint():
    assert len(laps_per_stint([a_lap(1), a_lap(2)])) == 1


# ----------------------------------------------------- corner model persistence

def test_a_detected_model_is_saved_and_reused(store: Store):
    frames = synthetic_lap()
    first = resolve_corner_model(store, "Fuji Speedway", "Full", frames)
    assert first is not None
    assert store.list_corner_models() == ["fuji-speedway-full"]

    # A different line on a later session must not renumber the corners.
    second = resolve_corner_model(store, "Fuji Speedway", "Full",
                                  synthetic_lap(apex_positions=(310.0, 890.0, 1510.0)))
    assert second.version == first.version
    assert [c.apex_m for c in second.corners] == [c.apex_m for c in first.corners]


def test_a_stored_model_is_returned_without_reference_frames(store: Store):
    resolve_corner_model(store, "Fuji Speedway", "Full", synthetic_lap())
    assert resolve_corner_model(store, "Fuji Speedway", "Full", None) is not None


def test_a_different_layout_supersedes_the_stored_model(store: Store):
    first = resolve_corner_model(store, "Fuji Speedway", "Full", synthetic_lap())
    longer = synthetic_lap(apex_positions=(300.0, 900.0, 1500.0, 2400.0),
                           lap_length_m=3000.0)
    second = resolve_corner_model(store, "Fuji Speedway", "Full", longer)
    assert second.version == first.version + 1
    assert len(second.corners) > len(first.corners)


def test_an_unsegmentable_lap_yields_no_model(store: Store):
    flat = [frame(d * 2.0, 240.0, d) for d in range(400)]
    assert resolve_corner_model(store, "Nowhere", None, flat) is None
    assert store.list_corner_models() == []


def test_circuit_key_includes_the_layout():
    assert circuit_key("Fuji Speedway", "Full") == "fuji-speedway-full"
    assert circuit_key("Fuji Speedway") == "fuji-speedway"


def test_corner_model_round_trips_through_the_store(store: Store):
    model = detect_corners(synthetic_lap(), "test-track")
    store.save_corner_model("test-track", model)
    assert store.get_corner_model("test-track") == model


def test_missing_corner_model_is_none(store: Store):
    assert store.get_corner_model("never-driven") is None


# ------------------------------------------------------------- driver inputs

def test_wear_gauge_round_trips(store: Store, event_id: int):
    from .test_store import a_lap as a_stored_lap
    session_id = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session_id, a_stored_lap())
    store.set_lap_wear(lap_id, 0.55, 0.51, 0.42, 0.40)
    row = store.list_laps(session_id)[0]
    assert row["wear_fl"] == 0.55
    assert row["wear_fr"] == 0.51
    assert row["wear_rl"] == 0.42
    assert row["wear_rr"] == 0.40


def test_an_unread_corner_stores_as_null_not_zero(store: Store, event_id: int):
    """A zero would read as a fresh tyre. Missing is null, never 0."""
    from .test_store import a_lap as a_stored_lap
    session_id = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session_id, a_stored_lap())
    store.set_lap_wear(lap_id, 0.55, None, None, None)
    row = store.list_laps(session_id)[0]
    assert row["wear_fl"] == 0.55
    assert row["wear_fr"] is None


def test_wear_outside_zero_to_one_is_refused(store: Store, event_id: int):
    from .test_store import a_lap as a_stored_lap
    session_id = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session_id, a_stored_lap())
    with pytest.raises(ValueError, match="fraction consumed"):
        store.set_lap_wear(lap_id, 55.0, 55.0, 0.42, 0.42)


def test_lap_exclusion_round_trips(store: Store, event_id: int):
    from .test_store import a_lap as a_stored_lap
    session_id = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session_id, a_stored_lap())
    store.exclude_lap(lap_id, "traffic")
    row = store.list_laps(session_id)[0]
    assert row["excluded"] == 1
    assert row["exclusion_reason"] == "traffic"

    store.exclude_lap(lap_id, None)
    assert store.list_laps(session_id)[0]["excluded"] == 0
