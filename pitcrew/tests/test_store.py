"""Store round-trips."""
from __future__ import annotations

import pytest

from pitcrew.store.db import Store
from pitcrew.telemetry.recorder import LapRecorder
from pitcrew.telemetry.session_state import Lap

from .conftest import make_packet, rolling_wheel_rps


def a_lap(lap_num: int = 1, **overrides) -> Lap:
    fields = dict(
        lap_num=lap_num, lap_time_ms=92_000, best_lap_ms=91_000, delta_ms=1_000,
        fuel_start=60.0, fuel_end=57.5, fuel_used=2.5, position=3,
        is_pit_lap=False, is_out_lap=False,
    )
    fields.update(overrides)
    return Lap(**fields)


# --------------------------------------------------------------------- events

def test_event_round_trip(store: Store, event_id: int):
    event = store.get_event(event_id)
    assert event["name"] == "Test Event"
    assert event["race_laps"] == 20
    assert event["available_compounds"] == ["RH", "RM", "RS"]
    assert event["pit_loss_secs"] == 20.0


def test_event_names_are_unique(store: Store, event_id: int):
    with pytest.raises(Exception):
        store.create_event(name="Test Event", track="Spa")


def test_update_event(store: Store, event_id: int):
    store.update_event(event_id, race_laps=30, required_compounds=["RS"])
    event = store.get_event(event_id)
    assert event["race_laps"] == 30
    assert event["required_compounds"] == ["RS"]


def test_list_events_newest_first(store: Store, event_id: int):
    second = store.create_event(name="Second", track="Spa")
    assert [e["id"] for e in store.list_events()][0] == second


def test_deleting_an_event_takes_its_sessions(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    store.delete_event(event_id)
    assert store.get_session(session_id) is None


# ----------------------------------------------------------------------- laps

def test_lap_round_trip(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session_id, a_lap())
    laps = store.list_laps(session_id)
    assert len(laps) == 1
    assert laps[0]["id"] == lap_id
    assert laps[0]["lap_time_ms"] == 92_000
    assert laps[0]["compound"] is None
    assert laps[0]["is_pit_lap"] == 0


def test_compound_tagging(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session_id, a_lap())
    store.set_lap_compound(lap_id, "RM")
    assert store.list_laps(session_id)[0]["compound"] == "RM"


def test_laps_are_ordered(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    for n in (3, 1, 2):
        store.add_lap(session_id, a_lap(n))
    assert [lap["lap_num"] for lap in store.list_laps(session_id)] == [1, 2, 3]


def test_event_laps_span_sessions(store: Store, event_id: int):
    first = store.start_session(event_id, "practice")
    store.add_lap(first, a_lap(1))
    second = store.start_session(event_id, "practice")
    store.add_lap(second, a_lap(1))
    race = store.start_session(event_id, "race")
    store.add_lap(race, a_lap(1))

    assert len(store.list_event_laps(event_id, "practice")) == 2
    assert len(store.list_event_laps(event_id, "race")) == 1


def test_frames_are_stored_with_the_lap(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    rec = LapRecorder()
    rps = rolling_wheel_rps(50.0)
    for i in range(120):
        rec.record_frame(make_packet(
            speed_ms=50.0, time_of_day_ms=i * 16,
            wheel_rps_fl=rps, wheel_rps_fr=rps,
            wheel_rps_rl=rps, wheel_rps_rr=rps))
    lap_id = store.add_lap(session_id, a_lap(), frames=rec.take_lap())

    stored = store.get_lap_frames(lap_id)
    assert store.has_frames(lap_id)
    assert stored["frame_count"] == 120
    assert len(stored["frames"]) == 120
    assert stored["frames"][5]["speed_kph"] == 180.0


def test_lap_without_frames_reports_none(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session_id, a_lap())
    assert store.get_lap_frames(lap_id) is None
    assert store.has_frames(lap_id) is False


def test_deleting_a_session_takes_laps_and_frames(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    rec = LapRecorder()
    rec.record_frame(make_packet())
    lap_id = store.add_lap(session_id, a_lap(), frames=rec.take_lap())
    store.delete_session(session_id)
    assert store.list_laps(session_id) == []
    assert store.get_lap_frames(lap_id) is None


# ----------------------------------------------------------------- strategies

def test_approving_a_strategy_demotes_the_previous_one(store: Store, event_id: int):
    first = store.save_strategy(event_id, {"stints": [10, 10]}, label="two stop")
    second = store.save_strategy(event_id, {"stints": [20]}, label="no stop")
    store.approve_strategy(first)
    store.approve_strategy(second)

    approved = store.get_approved_strategy(event_id)
    assert approved["id"] == second
    assert approved["plan"] == {"stints": [20]}
    statuses = {s["id"]: s["status"] for s in store.list_strategies(event_id)}
    assert statuses[first] == "candidate"


def test_no_approved_strategy_initially(store: Store, event_id: int):
    store.save_strategy(event_id, {"stints": [20]})
    assert store.get_approved_strategy(event_id) is None


def test_approving_a_missing_strategy_raises(store: Store):
    with pytest.raises(ValueError):
        store.approve_strategy(999)


def test_strategy_evidence_round_trips(store: Store, event_id: int):
    sid = store.save_strategy(event_id, {"stints": [20]}, evidence={"fuel_per_lap": 2.4})
    assert store.list_strategies(event_id)[0]["evidence"]["fuel_per_lap"] == 2.4
    assert store.list_strategies(event_id)[0]["id"] == sid


# ------------------------------------------------------------------ race runs

def test_revisions_form_a_chain(store: Store, event_id: int):
    strategy_id = store.save_strategy(event_id, {"stints": [20]})
    run_id = store.start_race_run(event_id, strategy_id, None)

    first = store.append_revision(run_id, 5, "fuel high", {"stints": [12, 8]})
    second = store.append_revision(run_id, 9, "accepted", {"stints": [12, 8]},
                                   accepted=True)

    revisions = store.list_revisions(run_id)
    assert [r["id"] for r in revisions] == [first, second]
    assert revisions[0]["parent_id"] is None
    assert revisions[1]["parent_id"] == first
    assert revisions[1]["accepted"] is True
    assert revisions[1]["plan"] == {"stints": [12, 8]}


def test_finishing_a_race_run_stamps_it(store: Store, event_id: int):
    run_id = store.start_race_run(event_id, None, None)
    store.finish_race_run(run_id)
    rows = store._query("SELECT finished_at FROM race_runs WHERE id = ?", (run_id,))
    assert rows[0]["finished_at"] is not None


# ------------------------------------------------------------------- schema

def test_reopening_an_existing_database_is_fine(tmp_path):
    path = tmp_path / "pitcrew.db"
    first = Store(path)
    event_id = first.create_event(name="E", track="Spa")
    first.close()

    second = Store(path)
    assert second.get_event(event_id)["track"] == "Spa"
    second.close()


def test_a_v1_database_upgrades_in_place_without_losing_anything(tmp_path):
    """v1 -> v2 adds the prompt log and five declared event columns.

    The upgrade runs on the driver's real file, so this checks the rows and
    the settings in them survive it - a migration that quietly empties an
    event is worse than one that refuses to run.
    """
    import sqlite3

    path = tmp_path / "v1.db"
    first = Store(path)
    event_id = first.create_event(name="E", track="Spa", car_name="Car",
                                  refuel_rate_lps=1.0, pit_loss_secs=19.5)
    first.close()

    # Rewind to v1 and strip what v2 added, the way a real old file looks.
    conn = sqlite3.connect(str(path))
    conn.execute("DROP TABLE prompt_issues")
    for column in ("start_type", "time_of_day", "priority", "pp_cap"):
        conn.execute(f"ALTER TABLE events DROP COLUMN {column}")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    upgraded = Store(path)
    event = upgraded.get_event(event_id)
    assert event["track"] == "Spa"
    assert event["refuel_rate_lps"] == 1.0
    # The new columns read null, which is what "nobody has said" means.
    assert event["start_type"] is None
    assert event["pp_cap"] is None
    issue_id = upgraded.log_prompt(kind="brief", body="x",
                                   prompt_version="v", app_version="a",
                                   event_id=event_id)
    assert upgraded.get_prompt(issue_id)["body"] == "x"
    upgraded.close()


def test_a_v3_file_that_predates_gear_ratios_gains_the_column(tmp_path):
    """The regression behind five practice laps that were never stored.

    `gear_ratios` was added to the `laps` DDL without a matching
    `ADDED_COLUMNS` entry. `CREATE TABLE IF NOT EXISTS` does nothing to a
    table that is already there, so a fresh file had the column and the
    driver's real file did not - and the version number was v3 either way,
    so nothing looked wrong until a lap was completed and the insert threw.

    A column added to a table that already ships must be reachable from an
    existing file, not only from one built this morning.
    """
    import json
    import sqlite3

    path = tmp_path / "v3-old.db"
    first = Store(path)
    session_id = first.start_session(first.create_event(name="E", track="Spa"),
                                     kind="practice")
    first.close()

    # Rewind to the shape the file had before the column was declared. The
    # version stays at 3: that is what made this invisible.
    conn = sqlite3.connect(str(path))
    conn.execute("ALTER TABLE laps DROP COLUMN gear_ratios")
    conn.commit()
    conn.close()

    upgraded = Store(path)
    lap_id = upgraded.add_lap(
        session_id, a_lap(gear_ratios=[3.1, 2.2, 1.7, 1.3, 1.0, 0.8]))
    stored = upgraded.list_laps(session_id)
    assert len(stored) == 1
    assert json.loads(stored[0]["gear_ratios"]) == [3.1, 2.2, 1.7, 1.3, 1.0, 0.8]
    assert lap_id is not None
    upgraded.close()


def test_a_foreign_schema_version_is_refused(tmp_path):
    import sqlite3
    path = tmp_path / "other.db"
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA user_version = 43")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="schema v43"):
        Store(path)
