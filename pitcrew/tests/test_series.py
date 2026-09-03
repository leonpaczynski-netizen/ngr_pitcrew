"""Putting events into leagues, and what depends on their being there.

He races more than one league at a time with a different team mate in each.
Every event on file predates the column, so the backlog is unlabelled - which
is not broken, but it pools them into one unnamed league until it is fixed.
"""
from __future__ import annotations

import pytest

from pitcrew.race import rival_book
from pitcrew.store.db import Store
from tools.series import main as series_main


@pytest.fixture()
def store(tmp_path):
    archive = Store(tmp_path / "series.db")
    for name, track, car in (("R1 - Spa", "Spa", "992"),
                             ("R2 - Fuji", "Fuji", "992"),
                             ("Enduro - Spa 4h", "Spa", "GR86")):
        archive.create_event(name=name, track=track, car_name=car)
    return archive


# --- the backlog -----------------------------------------------------------

def test_the_unlabelled_are_listed_so_they_can_be_found(store):
    assert len(store.events_without_a_series()) == 3
    assert store.known_series() == []


def test_labelling_one_event_removes_it_from_the_backlog(store):
    first = store.events_without_a_series()[0]
    store.set_event_series(first["id"], "GT3 League")
    assert len(store.events_without_a_series()) == 2
    assert store.known_series() == ["GT3 League"]


def test_an_empty_league_name_is_stored_as_no_league(store):
    """"" is not a league called nothing - it is the absence of one."""
    first = store.events_without_a_series()[0]
    store.set_event_series(first["id"], "")
    assert len(store.events_without_a_series()) == 3


# --- the bulk tool ---------------------------------------------------------

def test_matching_by_car_labels_only_that_car(store, tmp_path):
    series_main(["--car", "GR86", "Endurance", "--yes",
                 "--db", str(tmp_path / "series.db")])
    labelled = [e for e in store._query(
        "SELECT name, series FROM events WHERE series IS NOT NULL")]
    assert len(labelled) == 1
    assert labelled[0]["name"] == "Enduro - Spa 4h"


def test_a_substring_is_a_blunt_instrument_which_is_why_it_previews(store,
                                                                    tmp_path):
    """"R" catches "Enduro" as readily as "R1". The tool shows what it would
    do and asks first, because an event labelled into the wrong league takes
    its rival evidence with it."""
    series_main(["--like", "R", "GT3 League", "--yes",
                 "--db", str(tmp_path / "series.db")])
    rows = store._query("SELECT COUNT(*) AS n FROM events WHERE series = ?",
                        ("GT3 League",))
    assert rows[0]["n"] == 3          # including the endurance round


def test_the_tool_needs_a_league_name(store, tmp_path):
    with pytest.raises(SystemExit):
        series_main(["--like", "R", "--db", str(tmp_path / "series.db")])


def test_nothing_matching_changes_nothing(store, tmp_path):
    series_main(["--like", "zzz", "GT3 League", "--yes",
                 "--db", str(tmp_path / "series.db")])
    assert len(store.events_without_a_series()) == 3


# --- what the labels are for -----------------------------------------------

def test_a_teammate_per_league_needs_the_leagues_to_exist(store):
    store.set_teammate("GT3 League", "Rocky")
    store.set_teammate("Endurance", "K.Graebs")
    assert rival_book.teammate_of(store, "GT3 League") == "Rocky"
    assert rival_book.teammate_of(store, "Endurance") == "K.Graebs"


def test_stops_carry_the_series_and_car_of_the_race_they_were_watched_in(store):
    events = store._query("SELECT id, name, car_name FROM events ORDER BY id")
    store.set_event_series(events[0]["id"], "GT3 League")
    session = store.start_session(events[0]["id"], "race")
    store.record_rival_stop(session, "Rocky", lap=11, fuel_in_l=12.0,
                            fuel_out_l=80.0)
    row = store.rival_stops("Rocky")[0]
    assert row["series"] == "GT3 League" and row["car_name"] == "992"


def test_a_profile_can_be_narrowed_to_one_league(store):
    events = store._query("SELECT id FROM events ORDER BY id")
    store.set_event_series(events[0]["id"], "GT3 League")
    store.set_event_series(events[2]["id"], "Endurance")
    for event, lap in ((events[0]["id"], 11), (events[2]["id"], 30)):
        session = store.start_session(event, "race")
        store.record_rival_stop(session, "Rocky", lap=lap, laps_total=60,
                                fuel_in_l=12.0, fuel_out_l=80.0)
    assert rival_book.profile_of(store, "Rocky").stops_seen == 2
    only = rival_book.profile_of(store, "Rocky", series="Endurance")
    assert only.stops_seen == 1


def test_burn_is_per_car_while_the_stop_habit_pools(store):
    """Litres a lap is the CAR's number; when he stops is the DRIVER's."""
    events = store._query("SELECT id, car_name FROM events ORDER BY id")
    for event in events:
        session = store.start_session(event["id"], "race")
        store.record_rival_stop(session, "Rocky", lap=11, laps_total=20,
                                fuel_in_l=12.0, fuel_out_l=80.0)
    profile = rival_book.profile_of(store, "Rocky")
    assert profile.burn_per_lap_l("992")[1] == 2
    assert profile.burn_per_lap_l("GR86")[1] == 1
    assert profile.stop_fraction()[1] == 3
