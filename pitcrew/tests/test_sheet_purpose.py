"""A race sheet and a qualifying sheet are two sheets, not one.

The driver's report, verbatim: *"trying to load both a race setup and quali
setup into app it only accepts the last setup you add even though you can
select race or quali."*

Measured before the fix: `setup_sheets` was `UNIQUE(car_name, sheet_name)` with
`purpose` outside the key, while `save_setup_sheet` upserted on that key and
assigned `purpose=excluded.purpose`. Saving a qualifying sheet after a race
sheet of the same name did not add a row - it overwrote the race sheet and
relabelled it, and `sheet_for(car, 'race')` then returned nothing at all. All
seven archived sheets also carried `purpose IS NULL`, so nothing on the save
path had ever tagged one.
"""
from __future__ import annotations

import sqlite3

from pitcrew.setup.parse import parse_reply
from pitcrew.setup.sheet import SetupSheet
from pitcrew.store.db import Store

from .test_controller import qt_app  # noqa: F401

CAR = "Ford Shelby GT350R '16"
NAME = "Yas Marina v3"

# One reply carrying both sheets, in the envelope shape the prompts ask for -
# and deliberately with the SAME `sheetName` on both, because that is the case
# the old key could not represent and the one the driver hit.
REPLY = """
Here is the pair you asked for.

```json
{"sheets": [
  {"purpose": "race",
   "setup": {"sheetName": "Yas Marina v3",
             "values": {"rh_f": 60, "rh_r": 70, "arb_f": 4}}},
  {"purpose": "qualifying",
   "setup": {"sheetName": "Yas Marina v3",
             "values": {"rh_f": 55, "rh_r": 65, "arb_f": 6}}}
]}
```
"""


def _save(store: Store, purpose: str, rh_f: float, name: str = NAME) -> int:
    return store.save_setup_sheet(SetupSheet(
        car_name=CAR, sheet_name=name, values={"rh_f": rh_f},
        purpose=purpose))


# ------------------------------------------------------------------ the key


def test_two_purposes_of_one_name_are_two_rows(store: Store):
    race = _save(store, "race", 60.0)
    quali = _save(store, "qualifying", 55.0)

    assert race != quali
    sheets = {s.purpose: s for s in store.list_setup_sheets(CAR)}
    assert set(sheets) == {"race", "qualifying"}
    assert sheets["race"].values["rh_f"] == 60.0
    assert sheets["qualifying"].values["rh_f"] == 55.0


def test_saving_again_updates_in_place_and_does_not_duplicate(store: Store):
    first = _save(store, "race", 60.0)
    again = _save(store, "race", 62.0)

    assert first == again
    sheets = store.list_setup_sheets(CAR)
    assert len(sheets) == 1
    assert sheets[0].values["rh_f"] == 62.0


def test_an_untagged_sheet_does_not_breed_a_row_per_save(store: Store):
    """Sqlite counts two NULLs as distinct in a UNIQUE index.

    So a nullable `purpose` inside the key would stop the upsert matching its
    own row - the same bug in the opposite direction. The column is NOT NULL
    with a default and the store normalises before it writes.
    """
    ids = {store.save_setup_sheet(SetupSheet(
        car_name=CAR, sheet_name=NAME, values={"rh_f": 60.0}, purpose=None))
        for _ in range(3)}

    assert len(ids) == 1
    stored = store.list_setup_sheets(CAR)
    assert len(stored) == 1
    assert stored[0].purpose == "race"


def test_a_missing_purpose_reads_as_missing(store: Store):
    """None means none. Substituting the race sheet would file a qualifying
    run's symptoms against a setup that was not on the car."""
    _save(store, "race", 60.0)

    assert store.sheet_for(CAR, "race") is not None
    assert store.sheet_for(CAR, "qualifying") is None


# ---------------------------------------------------------- the parse path


def test_a_reply_with_both_sheets_stores_both(store: Store, event_id: int):
    """The tag has to travel from `parse_reply` all the way to the row.

    `parse_reply` already returned both sheets; nothing on the save path was
    tagging them, so the last one written won.
    """
    parsed = parse_reply(REPLY)
    assert set(parsed.sheets) == {"race", "qualifying"}

    fitted = store.save_setup_sheet(SetupSheet(
        car_name=CAR, sheet_name=NAME,
        values=dict(parsed.race.values), purpose="race"))
    store.save_setup_sheet(SetupSheet(
        car_name=CAR, sheet_name=parsed.qualifying.sheet_name or NAME,
        values=dict(parsed.qualifying.values), purpose="qualifying"))

    sheets = {s.purpose: s for s in store.list_setup_sheets(CAR)}
    assert set(sheets) == {"race", "qualifying"}
    assert sheets["race"].id == fitted
    assert sheets["race"].values["rh_f"] == 60
    assert sheets["qualifying"].values["rh_f"] == 55
    # Both sheets carry the same name and coexist on it.
    assert sheets["race"].sheet_name == sheets["qualifying"].sheet_name


def test_re_pasting_the_same_reply_updates_both_rather_than_duplicating(
        store: Store):
    parsed = parse_reply(REPLY)
    for _ in range(2):
        for purpose, sheet in parsed.sheets.items():
            store.save_setup_sheet(SetupSheet(
                car_name=CAR, sheet_name=sheet.sheet_name or NAME,
                values=dict(sheet.values), purpose=purpose))

    assert len(store.list_setup_sheets(CAR)) == 2


# --------------------------------------------------------- opening a session


def _start_qualifying_practice(store: Store, event_id: int):
    """Open a practice session set to qualifying, through the real controller."""
    from pitcrew.analysis.runs import FOR_QUALIFYING
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    store.set_state("active_event_id", event_id)
    practice = PracticeScreen()
    practice.set_practice_intent(FOR_QUALIFYING)
    controller = PitCrewController(store, EventScreen(), practice)
    try:
        session_id = controller.open_practice_session()
    finally:
        controller.shutdown()
    return store.get_session(session_id)


def test_one_sheet_on_file_is_the_sheet_that_is_fitted(store: Store, event_id,
                                                       qt_app):
    """A car with a single sheet is unambiguous whatever it is labelled.

    Refusing to record it over the label would be bureaucracy, and the driver
    is not helped by an app that knows what he ran and declines to say.
    """
    car = store.get_event(event_id)["car_name"]
    only = store.save_setup_sheet(SetupSheet(
        car_name=car, sheet_name="v1", values={"rh_f": 60.0}, purpose="race"))

    assert _start_qualifying_practice(store, event_id)["setup_sheet_id"] == only


def test_a_session_records_no_sheet_rather_than_the_wrong_one(store: Store,
                                                              event_id,
                                                              qt_app):
    """Missing is null, never a substitute.

    Two race sheets and no qualifying sheet: the app cannot say which was
    fitted for a qualifying run. It used to take `sheets[0]` - the most recent
    sheet of any purpose - and record that. A `setup_sheet_id` naming a sheet
    he was not running is worse than none, because the export presents it as
    the setup as run and the tune builder reads it as the thing that produced
    the symptoms.
    """
    car = store.get_event(event_id)["car_name"]
    for name in ("v1", "v2"):
        store.save_setup_sheet(SetupSheet(
            car_name=car, sheet_name=name, values={"rh_f": 60.0},
            purpose="race"))

    assert _start_qualifying_practice(store, event_id)["setup_sheet_id"] is None


# ------------------------------------------------------------- the migration


def _v7_sheets_file(path) -> None:
    """A file in the pre-v8 shape, with the archive's seven untagged sheets."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE setup_sheets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            car_name     TEXT    NOT NULL,
            sheet_name   TEXT    NOT NULL,
            values_json  TEXT    NOT NULL DEFAULT '{}',
            gears_json   TEXT,
            performance_json TEXT,
            build_json   TEXT,
            notes        TEXT,
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL,
            purpose      TEXT,
            UNIQUE(car_name, sheet_name)
        );
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            kind TEXT NOT NULL,
            setup_sheet_id INTEGER REFERENCES setup_sheets(id),
            started_at TEXT NOT NULL
        );
    """)
    # The real ids, gaps and all: 2, 7, 8, 10 and 11 were used and deleted.
    for sheet_id, car, name in (
            (1, "Porsche 911 RSR (991) '17", "Monza race v1"),
            (3, "Porsche 911 RSR (991) '17", "Monza race v2"),
            (4, CAR, "Round 3 Supercars sheet"),
            (5, CAR, "Yas Marina race v1"),
            (6, "Lamborghini Huracán GT3 '15", "Round 3 GR3 sheet"),
            (9, "Lamborghini Huracán GT3 '15", "Watkins Glen Long race v1"),
            (12, CAR, "Yas Marina race v2")):
        conn.execute(
            "INSERT INTO setup_sheets (id, car_name, sheet_name, created_at, "
            "updated_at) VALUES (?,?,?,'x','x')", (sheet_id, car, name))
    conn.execute("UPDATE sqlite_sequence SET seq = 15 WHERE name='setup_sheets'")
    for session_id, sheet_id in ((41, 12), (42, 12), (43, 12), (20, 3), (14, 9)):
        conn.execute(
            "INSERT INTO sessions (id, event_id, kind, setup_sheet_id, "
            "started_at) VALUES (?,1,'practice',?,'x')", (session_id, sheet_id))
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()


def test_the_seven_archived_sheets_keep_their_ids_and_become_race(tmp_path):
    path = tmp_path / "pitcrew.db"
    _v7_sheets_file(path)

    store = Store(path)
    rows = store._query("SELECT id, purpose FROM setup_sheets ORDER BY id")
    assert [r["id"] for r in rows] == [1, 3, 4, 5, 6, 9, 12]
    assert {r["purpose"] for r in rows} == {"race"}

    # Every session still resolves to the sheet it actually ran.
    dangling = store._query(
        "SELECT COUNT(*) c FROM sessions WHERE setup_sheet_id IS NOT NULL "
        "AND setup_sheet_id NOT IN (SELECT id FROM setup_sheets)")[0]["c"]
    assert dangling == 0
    assert store._query("PRAGMA foreign_key_check") == []
    # And an issued id is never issued twice: 13, 14 and 15 stay spent.
    assert store._query(
        "SELECT seq FROM sqlite_sequence WHERE name='setup_sheets'"
    )[0]["seq"] == 15
    store.close()


def test_the_rebuild_is_idempotent(tmp_path):
    path = tmp_path / "pitcrew.db"
    _v7_sheets_file(path)
    for _ in range(3):
        store = Store(path)
        rows = store._query("SELECT id FROM setup_sheets ORDER BY id")
        assert [r["id"] for r in rows] == [1, 3, 4, 5, 6, 9, 12]
        store.close()
