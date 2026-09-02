"""The rival dataset: what survives from one race into the next.

The point of the book is that tonight's stop joins up with the same driver's
stop last month. Everything here is about that join holding, and about what the
book refuses to claim when it cannot.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.race import rival_book
from pitcrew.race.pit_wall import Seen
from pitcrew.race.rivals import Stop
from pitcrew.store.db import Store


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "book.db")


@pytest.fixture()
def races(store):
    """Two real sessions to file stops against.

    Real ones, because `rival_stops.session_id` is a foreign key with a cascade
    - a stop belongs to the race it was watched in, and deleting that race
    should take its observations with it rather than leaving them orphaned
    against an id that means nothing.
    """
    event_id = store.create_event(name="Spa R5", track="Spa", car_name="992")
    return [store.start_session(event_id, "race") for _ in range(2)]


def a_stop(driver="Rocky", lap=11, fuel_in=8.0, fuel_out=93.0,
           reads=14, partial=False):
    return Seen(driver=driver, driver_id=0,
                stop=Stop(lap=lap, fuel_in_l=fuel_in, fuel_out_l=fuel_out),
                reads=reads, watched_s=120.0, partial=partial)


# --- identity across races --------------------------------------------------

def test_an_exemplar_round_trips_bit_for_bit(store):
    """It is the only reason a driver is the same driver next month."""
    bits = np.zeros((16, 64), dtype=bool)
    bits[3:9, 5:41] = True
    store.save_driver("Rocky", bits)
    assert (store.driver_exemplars()["Rocky"] == bits).all()


def test_a_driver_with_no_bitmap_cannot_recognise_anybody(store):
    """A name alone would seed a cluster that swallows the first row it sees."""
    store.save_driver("Rocky")
    assert store.driver_exemplars() == {}


def test_re_saving_updates_the_bitmap_because_an_exemplar_improves(store):
    first = np.zeros((16, 64), dtype=bool)
    first[3:9, 5:20] = True
    second = first.copy()
    second[3:9, 20:30] = True
    store.save_driver("Rocky", first)
    store.save_driver("Rocky", second)
    assert (store.driver_exemplars()["Rocky"] == second).all()


def test_the_teammate_is_a_flag_on_a_driver(store):
    store.save_driver("Rocky", np.ones((16, 64), dtype=bool), is_teammate=True)
    store.save_driver("PUNISHED", np.zeros((16, 64), dtype=bool))
    assert rival_book.teammate_of(store) == "Rocky"


def test_saving_a_driver_again_does_not_clear_the_teammate_flag(store):
    store.save_driver("Rocky", np.ones((16, 64), dtype=bool), is_teammate=True)
    store.save_driver("Rocky", np.ones((16, 64), dtype=bool))
    assert store.teammate_name() == "Rocky"


# --- filing what was watched ------------------------------------------------

def test_a_watched_stop_is_filed_with_its_evidence(store):
    rival_book.record(store, None, a_stop(), laps_total=20)
    rows = store.rival_stops("Rocky")
    assert len(rows) == 1
    assert rows[0]["fuel_in_l"] == 8.0 and rows[0]["fuel_out_l"] == 93.0
    assert rows[0]["reads"] == 14 and rows[0]["partial"] == 0


def test_a_stop_with_no_name_is_not_filed(store):
    """A row keyed on an anonymous cluster id joins up with nothing: the ids
    are per-session, which is the one thing the book exists to survive."""
    assert rival_book.record(store, None, a_stop(driver=None)) is None
    assert store.rival_stops() == []


def test_an_unread_tank_is_stored_as_missing_and_never_as_zero(store):
    """CLAUDE.md rule 3, at the storage layer."""
    rival_book.record(store, None, a_stop(fuel_in=None), laps_total=20)
    assert store.rival_stops("Rocky")[0]["fuel_in_l"] is None


def test_a_partial_sighting_is_kept_but_marked(store):
    rival_book.record(store, None, a_stop(partial=True), laps_total=20)
    assert store.rival_stops("Rocky")[0]["partial"] == 1
    assert store.rival_stops("Rocky", include_partial=False) == []


# --- reading it back --------------------------------------------------------

def test_a_profile_is_assembled_from_every_race_on_file(store, races):
    rival_book.record(store, races[0], a_stop(lap=11), laps_total=20)
    rival_book.record(store, races[1], a_stop(lap=10, fuel_in=20.0),
                      laps_total=20)
    profile = rival_book.profile_of(store, "Rocky")
    assert profile.stops_seen == 2 and profile.races_seen == 2
    burn, count = profile.burn_per_lap_l()
    assert count == 2 and burn is not None


def test_a_partial_sighting_does_not_set_a_burn_rate(store, races):
    """Its entry figure is an upper bound, so the litres taken are a floor -
    and nothing in the number itself says so."""
    rival_book.record(store, races[0], a_stop(partial=True), laps_total=20)
    assert rival_book.profile_of(store, "Rocky").stops_seen == 0
    assert rival_book.profile_of(store, "Rocky",
                                 include_partial=True).stops_seen == 1


def test_a_driver_nobody_watched_has_an_empty_page_not_a_habit(store):
    """The board is truncated to eight, and pitting drops a car below the cut,
    so an empty page means never seen stopping."""
    assert rival_book.profile_of(store, "K.Graebs").stops_seen == 0
    assert rival_book.briefing(store) == []


def test_the_briefing_reads_the_whole_field(store, races):
    for driver, entry in (("Rocky", 8.0), ("Boxhead", 1.0)):
        for lap in (9, 10, 11):
            rival_book.record(store, races[lap % 2],
                              a_stop(driver=driver, lap=lap, fuel_in=entry),
                              laps_total=20)
    said = " ".join(rival_book.briefing(store, ours_burn_l=8.0))
    assert "Rocky" in said and "Boxhead" in said
    assert "L a lap" in said


def test_the_briefing_can_be_narrowed_to_the_drivers_actually_racing(
        store, races):
    rival_book.record(store, races[0], a_stop(driver="Rocky"), laps_total=20)
    rival_book.record(store, races[0], a_stop(driver="Gone"), laps_total=20)
    said = " ".join(rival_book.briefing(store, drivers=["Rocky"]))
    assert "Rocky" in said and "Gone" not in said


def test_races_seen_counts_up_per_race_not_per_stop(store):
    store.save_driver("Rocky", np.ones((16, 64), dtype=bool))
    store.note_races_seen(["Rocky"])
    store.note_races_seen(["Rocky"])
    rows = store._query("SELECT races_seen FROM drivers WHERE name = 'Rocky'")
    assert rows[0]["races_seen"] == 2


# --- naming, which is the only thing that lets a stop be filed at all -------

def test_a_provisional_handle_is_issued_rather_than_dropping_a_stop(store):
    """A stop with no name is a stop thrown away, and there is no second
    chance at one: the columns are gone the moment the car leaves."""
    first = store.provisional_driver_name()
    assert first == "Car #1"
    store.save_driver(first, np.ones((16, 64), dtype=bool))
    assert store.provisional_driver_name() == "Car #2"


def test_renaming_carries_every_stop_already_on_file(store, races):
    """Retroactive on purpose: `rival_stops.driver` is the name, so renaming
    the driver and renaming his stops are the same act."""
    store.save_driver("Car #1", np.ones((16, 64), dtype=bool))
    for lap in (9, 11):
        rival_book.record(store, races[0], a_stop(driver="Car #1", lap=lap),
                          laps_total=20)
    assert store.rename_driver("Car #1", "Rocky") == 2
    assert store.rival_stops("Car #1") == []
    assert len(store.rival_stops("Rocky")) == 2
    assert [d["name"] for d in store.unnamed_drivers()] == []


def test_two_handles_that_are_one_person_merge(store, races):
    """The expected reason to rename at all: a driver who came back as two
    clusters in different races."""
    for handle in ("Car #1", "Car #2"):
        store.save_driver(handle, np.ones((16, 64), dtype=bool))
        rival_book.record(store, races[0], a_stop(driver=handle), laps_total=20)
    store.rename_driver("Car #1", "Rocky")
    store.rename_driver("Car #2", "Rocky")
    assert len(store.rival_stops("Rocky")) == 2
    assert store.unnamed_drivers() == []


def test_renaming_to_the_same_name_or_to_nothing_does_nothing(store):
    store.save_driver("Rocky", np.ones((16, 64), dtype=bool))
    assert store.rename_driver("Rocky", "Rocky") == 0
    assert store.rename_driver("Rocky", "") == 0
    assert store.driver_exemplars().get("Rocky") is not None


def test_only_provisional_handles_are_listed_as_needing_a_name(store):
    store.save_driver("Car #1", np.ones((16, 64), dtype=bool))
    store.save_driver("Rocky", np.ones((16, 64), dtype=bool))
    assert [d["name"] for d in store.unnamed_drivers()] == ["Car #1"]
