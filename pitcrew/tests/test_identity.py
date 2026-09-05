"""Canonical identity for cars and circuits: the v7 tables and the evidence gate.

Every one of these covers a defect that was live in the archive on 17 Aug 2026,
not a hypothetical. The one that matters most is
`test_a_mismatched_session_leaves_the_evidence_set`: session 11 streamed a Gr.3
class on an event whose car is a road car, and its lap 4 burn of
7.563377380371094 L became `assumptions.fuelPerLapL = 7.563` in the **approved**
race plan.
"""
from __future__ import annotations

import pytest

from pitcrew.store import catalogs
from pitcrew.store.db import Store
from pitcrew.store.identity import (
    IDENTITY_MISMATCH,
    IDENTITY_NO_READING,
    IDENTITY_OK,
    IDENTITY_QUARANTINED,
    IDENTITY_UNKNOWN_CAR,
    STATUS_QUARANTINED,
    expected_stream_token,
    reconcile_car_id,
    slugify,
)
from pitcrew.telemetry.session_state import Lap

# Two real cars off the shipped catalogue, in GT7's own spelling. Named rather
# than invented: a fixture that invents a car or a track name is how the tyre
# scope bug passed its tests for a whole race.
SHELBY = "Ford Shelby GT350R '16"          # Road Car -> GT7 streams GRN
PORSCHE = "Porsche 911 RSR (991) '17"      # Gr.3     -> GT7 streams GR3
HURACAN = "Lamborghini Huracán GT3 '15"

SHELBY_PACKET_ID = 3391                    # measured off the live stream
PORSCHE_PACKET_ID = 4102                   # not measured; any other id will do


def _event(store: Store, *, car: str = SHELBY,
           track: str = "Yas Marina Circuit",
           layout: str | None = "Full Course", name: str = "R3") -> int:
    return store.create_event(
        name=name, track=track, layout=layout, car_name=car,
        race_type="laps", race_laps=15,
        available_compounds=["RS"], required_compounds=[])


def _lap(num: int, *, fuel_used: float = 7.0) -> Lap:
    return Lap(lap_num=num, lap_time_ms=119_000, best_lap_ms=118_000,
               delta_ms=0, fuel_start=80.0, fuel_end=80.0 - fuel_used,
               fuel_used=fuel_used, position=1, is_pit_lap=False,
               is_out_lap=False, compound="RS")


# ------------------------------------------------------------------- stage 1


def test_the_catalogue_seeds_and_every_row_carries_a_slug(store: Store):
    tracks = store._query("SELECT * FROM tracks")
    layouts = store.list_track_layouts()
    cars = store.list_cars()

    assert len(tracks) == len(catalogs.track_layouts()) == 41
    # 84 catalogue layouts plus the 37 reverse configurations GT7 offers.
    assert len(layouts) == sum(len(v) for v in catalogs.track_layouts().values())
    assert len(layouts) == 121
    assert len(cars) == len(catalogs.car_specs()) == 608

    assert all(row["slug"] for row in tracks)
    assert all(row["slug"] for row in layouts)
    assert all(row["slug"] for row in cars)


def test_no_car_imports_an_id_from_the_catalogue_file(store: Store):
    """`car_id_map.json` looks like the game's id space and is not.

    The Shelby streams 3391; that file maps it to 473 and stops at 712. An id
    that measured false must never reach `cars.gt7_car_id`, so every seeded
    row starts NULL - unmeasured, which is the truth - and the id is learned
    off the wire instead.
    """
    assert all(row["gt7_car_id"] is None for row in store.list_cars())
    assert catalogs.cars_by_id()[473] == SHELBY      # what the file claims
    assert 3391 not in catalogs.cars_by_id()         # what the stream measured


def test_the_layout_slug_is_the_key_already_on_disk(store: Store):
    """Stage 3 resolves 1,459 stored keys against this column by equality.

    `slugify(track + ' ' + layout)` is what `corner_models.circuit_key`,
    `track_clock.circuit_key`, `grip_observations` and `tyre_models` all hold
    today. Changing the composition would orphan every one of them.
    """
    rows = {r["slug"] for r in store.list_track_layouts()}
    assert "yas-marina-circuit-full-course" in rows
    assert "autodromo-nazionale-monza-full-course" in rows
    assert "watkins-glen-international-long-course" in rows


def test_the_huracan_has_one_slug_and_it_is_folded(store: Store):
    """Bug 3: `str.isalnum()` is True for an accent, so one car got two keys.

    `lamborghini-huracán-gt3-15` was written to 300 grip observations
    while a regex-based rule composed `lamborghini-hurac-n-gt3-15` to look
    them up, and the two could never meet. There is one rule now, it folds,
    and the slug is a stored column rather than something a caller rebuilds.
    """
    row = store.car_by_name(HURACAN)
    assert row["slug"] == "lamborghini-huracan-gt3-15"
    assert row["slug"] == slugify(HURACAN)


def test_the_migration_never_touches_laps(tmp_path):
    """`lap_frames` cascades off `laps`; rebuilding it would take every blob."""
    path = tmp_path / "pitcrew.db"
    store = Store(path)
    before = store._query(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='laps'"
    )[0]["sql"]
    store.close()

    store = Store(path)                     # re-open, re-run the upgrade pass
    after = store._query(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='laps'"
    )[0]["sql"]
    store.close()
    assert before == after


def test_the_migration_is_idempotent_and_loses_nothing(tmp_path):
    path = tmp_path / "pitcrew.db"
    store = Store(path)
    event_id = _event(store)
    session_id = store.start_session(event_id, "practice")
    store.add_lap(session_id, _lap(1))
    counts = {t: store._query(f"SELECT COUNT(*) c FROM {t}")[0]["c"]
              for t in ("events", "sessions", "laps", "cars", "tracks",
                        "track_layouts")}
    store.close()

    for _ in range(2):
        store = Store(path)
        again = {t: store._query(f"SELECT COUNT(*) c FROM {t}")[0]["c"]
                 for t in counts}
        store.close()
        assert again == counts


def test_an_event_is_keyed_to_canonical_rows_on_save(store: Store):
    event_id = _event(store)
    event = store.get_event(event_id)
    assert event["identity_status"] == IDENTITY_OK
    assert store.get_car(event["car_ref"])["name"] == SHELBY
    layout = store.get_track_layout(event["layout_id"])
    assert (layout["track_name"], layout["layout"]) == ("Yas Marina Circuit",
                                                        "Full Course")


def test_an_event_with_no_layout_is_quarantined_and_keeps_its_data(store: Store):
    """Event 1 carried `layout IS NULL` for weeks with 763 observations on it.

    The migration must not pick a layout for him. The corner model measures
    the lap at 5746.9 m, the catalogue says Full Course 5793 and No Chicane
    5748, and the stored track-model file is named *full course* - those
    sources disagree, and per CLAUDE.md 4.1 the disagreement is the finding.
    """
    event_id = _event(store, track="Autodromo Nazionale Monza", layout=None,
                      car=PORSCHE, name="R8")
    session_id = store.start_session(event_id, "practice")
    store.add_lap(session_id, _lap(1))

    event = store.get_event(event_id)
    assert event["identity_status"] == IDENTITY_QUARANTINED
    assert event["layout_id"] is None
    assert event["car_ref"] is not None            # the car half still resolved
    assert len(store.list_laps(session_id)) == 1   # nothing was dropped
    assert any(row["scope"] == "event" and row["id"] == event_id
               for row in store.list_unresolved_identities())


def test_re_keying_follows_an_edited_declaration(store: Store):
    event_id = _event(store)
    first = store.get_event(event_id)["layout_id"]
    store.update_event(event_id, track="Suzuka Circuit", layout="Full Course")
    second = store.get_event(event_id)["layout_id"]
    assert second != first
    assert store.get_track_layout(second)["track_name"] == "Suzuka Circuit"


# ------------------------------------------------- stage 2: reconciliation


def test_the_expected_stream_token_is_absent_rather_than_guessed():
    assert expected_stream_token("Gr.3") == "GR3"
    assert expected_stream_token("Road Car") == "GRN"
    # VGT streams under more than one token and nothing here has measured
    # which, so there is no expectation and therefore no accusation.
    assert expected_stream_token("VGT") is None
    assert expected_stream_token(None) is None


def test_an_id_of_zero_is_not_a_car():
    """0 is GT7's 'the car has not loaded' sentinel, measured on session 42."""
    outcome = reconcile_car_id(0, event_car=None, car_by_gt7_id=None)
    assert outcome.status == IDENTITY_NO_READING
    assert outcome.car_ref_observed is None
    assert reconcile_car_id(None, event_car=None,
                            car_by_gt7_id=None).status == IDENTITY_NO_READING


def test_the_events_car_learns_its_id_from_the_stream(store: Store):
    event_id = _event(store)
    session_id = store.start_session(event_id, "practice")

    status = store.note_stream_facts(session_id, packet_format="C",
                                     car_category="GRN", fuel_capacity_l=100.0,
                                     car_id=SHELBY_PACKET_ID,
                                     game_version="GT7 1.70")
    assert status == IDENTITY_OK

    car = store.car_by_name(SHELBY)
    assert car["gt7_car_id"] == SHELBY_PACKET_ID
    assert car["gt7_id_source"] == "observed-on-stream"
    assert car["gt7_id_game_version"] == "GT7 1.70"
    assert store.get_session(session_id)["car_id_observed"] == SHELBY_PACKET_ID
    assert any(r["table_name"] == "cars" and r["field"] == "gt7_car_id"
               for r in store.list_identity_repairs())


def test_a_no_reading_run_learns_nothing_and_accuses_nobody(store: Store):
    event_id = _event(store)
    session_id = store.start_session(event_id, "practice")
    status = store.note_stream_facts(session_id, packet_format="C", car_id=0)

    assert status == IDENTITY_OK              # unchanged, not demoted
    assert store.car_by_name(SHELBY)["gt7_car_id"] is None
    assert store.get_session(session_id)["car_id_observed"] is None


def test_a_second_car_on_the_same_event_is_a_mismatch(store: Store):
    """Bug 1, live. The session records in full and leaves the evidence set."""
    porsche_event = _event(store, car=PORSCHE,
                           track="Autodromo Nazionale Monza",
                           layout="Full Course", name="R8")
    teach = store.start_session(porsche_event, "practice")
    store.note_stream_facts(teach, car_id=PORSCHE_PACKET_ID)

    shelby_event = _event(store)
    session_id = store.start_session(shelby_event, "practice")
    store.add_lap(session_id, _lap(1, fuel_used=7.563377380371094))
    status = store.note_stream_facts(session_id, packet_format="C",
                                     car_category="GR3",
                                     car_id=PORSCHE_PACKET_ID)

    assert status == IDENTITY_MISMATCH
    session = store.get_session(session_id)
    assert session["car_id_observed"] == PORSCHE_PACKET_ID
    assert store.get_car(session["car_ref_observed"])["name"] == PORSCHE
    # Recorded in full. Excluded is not lost.
    assert len(store.list_laps(session_id)) == 1
    assert store.list_evidence_laps(shelby_event) == []
    assert [r["id"] for r in store.excluded_evidence_sessions(shelby_event)] \
        == [session_id]


def _force_status(store: Store, session_id: int, status: str) -> None:
    """Stamp a status the archive has but a fresh fixture cannot produce."""
    store._conn.execute(
        "UPDATE sessions SET identity_status = ? WHERE id = ?",
        (status, session_id))
    store._conn.commit()


def test_a_no_reading_session_is_not_a_mismatch(store: Store):
    """Five archived sessions read no class at all. That is a different state.

    Sessions 4 and 21 have no packet format - GT7 never streamed. 13, 36 and
    42 read a 0 L tank, the shape of a packet that landed before the car
    loaded. None of them is evidence that the wrong car was driven, and none
    of them is filed as one.
    """
    event_id = _event(store)
    quiet = store.start_session(event_id, "practice")
    _force_status(store, quiet, IDENTITY_NO_READING)
    wrong = store.start_session(event_id, "practice")
    _force_status(store, wrong, IDENTITY_MISMATCH)

    unresolved = {r["id"]: r["identity_status"]
                  for r in store.list_unresolved_identities()
                  if r["scope"] == "session"}
    # A mismatch is a question for the driver. A missing reading is not: there
    # is nothing he can tell the app that it did not already know.
    assert unresolved == {wrong: IDENTITY_MISMATCH}


def test_a_contradiction_disqualifies_a_session_and_an_absence_does_not(
        store: Store):
    """The evidence gate's whole policy, both halves, on one event.

    Modelled on event 2 as it actually stands: session 11 streamed a class
    that contradicts the event's car and leaves; session 42 streamed no class
    at all and stays. Excluding session 42 was measured to move the burn from
    7.178 to 7.638 L against a race that burned 6.57-7.00 - so an absent
    packet field was making the answer worse, which is CLAUDE.md rule 3's
    failure mode exactly: missing treated as a value.
    """
    event_id = _event(store)

    ok = store.start_session(event_id, "practice")
    store.add_lap(ok, _lap(1))

    quiet = store.start_session(event_id, "practice")
    store.add_lap(quiet, _lap(1))
    _force_status(store, quiet, IDENTITY_NO_READING)

    wrong = store.start_session(event_id, "practice")
    store.add_lap(wrong, _lap(1))
    _force_status(store, wrong, IDENTITY_MISMATCH)

    unknown = store.start_session(event_id, "practice")
    store.add_lap(unknown, _lap(1))
    _force_status(store, unknown, IDENTITY_UNKNOWN_CAR)

    admitted = {row["session_id"] for row in store.list_evidence_laps(event_id)}
    assert admitted == {ok, quiet}
    assert {r["id"] for r in store.excluded_evidence_sessions(event_id)} == {
        wrong, unknown}


def test_an_unknown_car_records_the_session_and_is_not_selectable(store: Store):
    """The whole answer to 'a car the catalogue has never heard of'.

    Selection is closed and observation is open. The session captures in full
    against a distinct id from the first packet; the id just belongs to a
    quarantined row, which no picker offers and no fit pools.
    """
    event_id = _event(store)
    store.note_stream_facts(store.start_session(event_id, "practice"),
                            car_id=SHELBY_PACKET_ID)      # teach the real id

    session_id = store.start_session(event_id, "practice")
    store.add_lap(session_id, _lap(1))
    store.add_lap(session_id, _lap(2))
    status = store.note_stream_facts(session_id, car_id=99_999,
                                     game_version="GT7 1.71")

    assert status == IDENTITY_UNKNOWN_CAR
    session = store.get_session(session_id)
    created = store.get_car(session["car_ref_observed"])
    assert created["gt7_car_id"] == 99_999
    assert created["name"] == "Unknown car #99999"
    assert created["status"] == STATUS_QUARANTINED

    # Recorded in full.
    assert len(store.list_laps(session_id)) == 2
    # Not selectable.
    assert created["name"] not in {c["name"] for c in store.list_cars()}
    assert created["name"] in {
        c["name"] for c in store.list_cars(include_quarantined=True)}
    # Not pooled.
    assert session_id not in {r["session_id"]
                              for r in store.list_evidence_laps(event_id)}


def test_an_unknown_car_never_collapses_into_losing_the_session(store: Store):
    """The two failure modes this path exists between, asserted as absences."""
    event_id = _event(store)
    store.note_stream_facts(store.start_session(event_id, "practice"),
                            car_id=SHELBY_PACKET_ID)
    session_id = store.start_session(event_id, "practice")
    store.add_lap(session_id, _lap(1))
    store.note_stream_facts(session_id, car_id=12_345)

    # Not "lose the session":
    assert store.get_session(session_id) is not None
    assert store.list_laps(session_id)
    # Not "silently accept it as evidence":
    assert store.list_evidence_laps(event_id) == []


# ------------------------------------------------------- stage 2: the gate


def test_a_mismatched_session_leaves_the_evidence_set(store: Store):
    """Bug 1 end to end: the fuel figure stops coming off the wrong car.

    Session 11's lap 4 burned 7.563377380371094 L and the approved plan's
    `fuelPerLapL` was 7.563. With the gate the median is taken over the
    event's own car only.
    """
    from pitcrew.strategy.evidence import build_inputs

    porsche_event = _event(store, car=PORSCHE,
                           track="Autodromo Nazionale Monza",
                           layout="Full Course", name="R8")
    store.note_stream_facts(store.start_session(porsche_event, "practice"),
                            car_id=PORSCHE_PACKET_ID)

    event_id = _event(store)
    right = store.start_session(event_id, "practice")
    for num in range(1, 5):
        store.add_lap(right, _lap(num, fuel_used=6.8))
    store.note_stream_facts(right, packet_format="C", car_category="GRN",
                            fuel_capacity_l=100.0, car_id=SHELBY_PACKET_ID)

    wrong = store.start_session(event_id, "practice")
    for num in range(1, 5):
        store.add_lap(wrong, _lap(num, fuel_used=7.563377380371094))
    store.note_stream_facts(wrong, packet_format="C", car_category="GR3",
                            fuel_capacity_l=100.0, car_id=PORSCHE_PACKET_ID)

    inputs, _evidence = build_inputs(store, event_id)
    assert inputs.fuel_per_lap_l == pytest.approx(6.8, abs=0.001)
    assert inputs.fuel_per_lap_l != pytest.approx(7.563, abs=0.001)


def test_the_export_stops_asserting_the_wrong_class(store: Store):
    """`meta.carCategory` took the first non-null in start order.

    On event 2 that was session 11, so the payload declared `Gr.3` for a road
    car - for the whole event, in the file the knowledge base reads.
    """
    from pitcrew.export.build import _merged_session

    sessions = [
        {"id": 11, "started_at": "2026-08-13T16:00:37", "car_category": "GR3",
         "identity_status": IDENTITY_MISMATCH, "packet_format": "C",
         "setup_sheet_id": 5, "practice_intent": None, "practice_mode": None,
         "fuel_capacity_l": 100.0},
        {"id": 12, "started_at": "2026-08-13T16:46:00", "car_category": "GRN",
         "identity_status": IDENTITY_OK, "packet_format": "C",
         "setup_sheet_id": 12, "practice_intent": None, "practice_mode": None,
         "fuel_capacity_l": 100.0},
    ]
    assert _merged_session(sessions)["car_category"] == "GRN"


def test_a_session_that_never_answered_is_not_accused(store: Store):
    """A row older than the column makes no claim; null is not a mismatch."""
    from pitcrew.export.build import _merged_session

    event_id = _event(store)
    session_id = store.start_session(event_id, "practice")
    store.add_lap(session_id, _lap(1))
    store._conn.execute(
        "UPDATE sessions SET identity_status = NULL WHERE id = ?", (session_id,))
    store._conn.commit()

    assert len(store.list_evidence_laps(event_id)) == 1
    merged = _merged_session([{
        "id": 1, "started_at": "2026-08-13T16:00:37", "car_category": "GRN",
        "packet_format": "C", "setup_sheet_id": None, "practice_intent": None,
        "practice_mode": None, "fuel_capacity_l": 100.0}])
    assert merged["car_category"] == "GRN"


def test_the_export_contract_exposes_no_ids(store: Store):
    """`gt7-pitcrew/1.8` stands: ids are a storage concern, not a contract one.

    The consumer is a knowledge base reading prose, and `3391` means nothing
    to it. The validator refuses an undefined key at any depth, so adding one
    would be a breaking change for no benefit.
    """
    from pitcrew.export import build, payload

    source = (build.__file__, payload.__file__)
    for path in source:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        assert '"carId"' not in text
        assert '"layoutId"' not in text
        assert '"carRef"' not in text
    assert payload.FORMAT == "gt7-pitcrew/1.8"
