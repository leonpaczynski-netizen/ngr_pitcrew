"""A change without its reason is a log, not a learning loop.

Three defects, all found on 3 Sep 2026 after the Huracan's build drifted from
restrictor 99 / ECU 94 to 93 / 100 with no row anywhere recording it:

1. **`setup_changes` could not hold a performance or gearing key at all.**
   `SetupChange.validate` checked the 23 export-contract sliders, and
   `note_sheet_change` only iterated `sheet.values` - so a sheet's
   `performance` and `gears` were invisible to the ledger by construction.
2. **There was nowhere to record WHY.** `dc_r 30 -> 26` scores differently
   depending on whether it was made for exit traction or braking stability;
   the same outcome confirms one and refutes the other.
3. **`data_health.py` printed the same words for AGREED and NOT COMPARED.**
   All four Daytona sessions carry no sheet, so the gearbox check examined
   nothing, found no mismatch, and reported that every session ran the sheet
   it was tagged with.
"""
from __future__ import annotations

import pytest

from pitcrew.setup.sheet import SetupChange, SetupError, SetupSheet
from pitcrew.store.db import Store


def a_sheet(name: str, circuit: str | None = "fuji-international-speedway",
            gears: list[float] | None = None,
            performance: dict | None = None, **values) -> SetupSheet:
    base = {"arb_f": 6.0, "arb_r": 4.0, "rh_f": 63.0, "rh_r": 72.0}
    base.update(values)
    return SetupSheet(car_name="Test Car", sheet_name=name, purpose="race",
                      values=base, circuit_key=circuit,
                      gears=gears or [3.02, 2.45, 1.97, 1.60, 1.29, 1.087],
                      performance=performance or {
                          "powerRestrictor": 99.0, "ecuOutput": 94.0,
                          "ballastKg": 55.0, "ballastPosition": -24.0})


def an_event(store: Store, car: str = "Test Car") -> int:
    return store.create_event(name="R", track="Fuji", car_name=car,
                              race_type="laps", race_laps=20)


# --------------------------------------------------------------- the vocabulary

def test_a_performance_key_is_recordable():
    """The restrictor drift had no home in the ledger. Now it has."""
    SetupChange(from_lap=1, key="powerRestrictor",
                from_value=99.0, to_value=93.0).validate()


def test_a_gear_is_recordable():
    SetupChange(from_lap=1, key="gear6", from_value=1.087,
                to_value=1.030).validate()


def test_the_export_still_refuses_a_non_contract_key():
    """The ledger is wider than the payload, and the payload must not widen.

    `EXPORT-CONTRACT.md` section 3 keys `driverChanges` on the 23 sliders; a
    key the tune builder does not know is silently dropped at the far end.
    """
    change = SetupChange(from_lap=1, key="ecuOutput", from_value=94.0,
                         to_value=100.0)
    assert change.exportable is False
    with pytest.raises(SetupError, match="ledger key, not a contract key"):
        change.as_export()
    assert SetupChange(from_lap=1, key="dc_r", from_value=30.0,
                       to_value=26.0).exportable is True


def test_an_invented_key_is_still_refused():
    """Widening the vocabulary must not make it a free-for-all."""
    with pytest.raises(SetupError, match="not in the shared setup vocabulary"):
        SetupChange(from_lap=1, key="tyre_pressure", from_value=1.0,
                    to_value=2.0).validate()


def test_an_unknown_source_is_refused():
    with pytest.raises(SetupError, match="not a known source"):
        SetupChange(from_lap=1, key="dc_r", from_value=1.0, to_value=2.0,
                    source="probably").validate()


# ------------------------------------------------------------------- the reason

def test_a_reason_survives_the_round_trip(store: Store):
    event_id = an_event(store)
    sheet = store.save_setup_sheet(a_sheet("v1"))
    session = store.start_session(event_id, "practice", setup_sheet_id=sheet)
    store.add_setup_change(session, SetupChange(
        from_lap=4, key="dc_r", from_value=30.0, to_value=26.0,
        reason="rear mechanical grip off the apex; zone 4 exit",
        source="issued"))
    change, = store.list_setup_changes(session)
    assert change.reason == "rear mechanical grip off the apex; zone 4 exit"
    assert change.source == "issued"


def test_a_reason_can_be_attached_after_the_fact(store: Store):
    """The ledger is written at session open; the why arrives at the debrief."""
    event_id = an_event(store)
    first = store.save_setup_sheet(a_sheet("v1"))
    s1 = store.start_session(event_id, "practice", setup_sheet_id=first)
    store.note_sheet_change(s1)
    second = store.save_setup_sheet(a_sheet("v2", arb_f=7.0))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=second)
    store.note_sheet_change(s2)

    row, = store._query(                                    # noqa: SLF001
        "SELECT id FROM setup_changes WHERE session_id = ?", (s2,))
    assert store.set_setup_change_reason(row["id"], "chasing mid-corner roll")
    change, = store.list_setup_changes(s2)
    assert change.reason == "chasing mid-corner roll"
    # The automatic source is not silently unset by recording a reason.
    assert change.source == "sheet-diff"


def test_a_missing_reason_is_null_never_invented(store: Store):
    """A sheet diff has no access to intent, and must not fabricate one."""
    event_id = an_event(store)
    first = store.save_setup_sheet(a_sheet("v1"))
    store.note_sheet_change(
        store.start_session(event_id, "practice", setup_sheet_id=first))
    second = store.save_setup_sheet(a_sheet("v2", rh_f=58.0))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=second)
    store.note_sheet_change(s2)
    change, = store.list_setup_changes(s2)
    assert change.reason is None
    assert change.source == "sheet-diff"


def test_setting_a_reason_on_a_missing_row_says_so(store: Store):
    assert store.set_setup_change_reason(999_999, "nope") is False


# --------------------------------------------------------- what the diff sees

def test_a_restrictor_change_is_filed(store: Store):
    """The exact drift that went unrecorded for eight days."""
    event_id = an_event(store)
    first = store.save_setup_sheet(a_sheet("v1"))
    store.note_sheet_change(
        store.start_session(event_id, "practice", setup_sheet_id=first))
    second = store.save_setup_sheet(a_sheet(
        "v2", performance={"powerRestrictor": 93.0, "ecuOutput": 100.0,
                           "ballastKg": 55.0, "ballastPosition": -24.0}))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=second)
    store.note_sheet_change(s2)

    changes = {c.key: (c.from_value, c.to_value)
               for c in store.list_setup_changes(s2)}
    assert changes["powerRestrictor"] == (99.0, 93.0)
    assert changes["ecuOutput"] == (94.0, 100.0)
    assert "ballastKg" not in changes, "unchanged values are not experiments"


def test_a_gearbox_change_is_filed_per_ratio(store: Store):
    event_id = an_event(store)
    first = store.save_setup_sheet(a_sheet("v1"))
    store.note_sheet_change(
        store.start_session(event_id, "practice", setup_sheet_id=first))
    second = store.save_setup_sheet(a_sheet(
        "v2", gears=[3.02, 2.45, 1.97, 1.60, 1.29, 1.030]))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=second)
    store.note_sheet_change(s2)

    changes = {c.key: (c.from_value, c.to_value)
               for c in store.list_setup_changes(s2)}
    assert changes == {"gear6": (1.087, 1.030)}, \
        "only 6th moved, so only 6th is an experiment"


def test_a_gearbox_that_loses_a_ratio_shows_the_loss(store: Store):
    """A shorter list is a change to None, not a silently shorter loop."""
    event_id = an_event(store)
    first = store.save_setup_sheet(a_sheet("v1"))
    store.note_sheet_change(
        store.start_session(event_id, "practice", setup_sheet_id=first))
    second = store.save_setup_sheet(a_sheet(
        "v2", gears=[3.02, 2.45, 1.97, 1.60, 1.29]))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=second)
    store.note_sheet_change(s2)
    changes = {c.key: (c.from_value, c.to_value)
               for c in store.list_setup_changes(s2)}
    assert changes == {"gear6": (1.087, None)}


def test_the_export_carries_only_contract_keys(store: Store):
    """A mixed ledger must still produce a contract-valid payload."""
    event_id = an_event(store)
    sheet = store.save_setup_sheet(a_sheet("v1"))
    session = store.start_session(event_id, "practice", setup_sheet_id=sheet)
    for change in (
        SetupChange(1, "dc_r", 30.0, 26.0, reason="exit traction"),
        SetupChange(1, "ecuOutput", 94.0, 100.0, reason="power cap"),
        SetupChange(1, "gear6", 1.087, 1.030, reason="terminal speed"),
    ):
        store.add_setup_change(session, change)
    ledger = store.list_setup_changes(session)
    assert len(ledger) == 3, "the ledger keeps all three"
    exported = [c.as_export() for c in ledger if c.exportable]
    assert exported == [{"fromLap": 1, "key": "dc_r", "from": 30.0, "to": 26.0}]
