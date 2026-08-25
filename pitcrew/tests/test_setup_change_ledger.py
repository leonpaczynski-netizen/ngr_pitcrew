"""Every change is an experiment, and the ledger held zero rows for 88 sessions.

`setup_changes` had both ends built — `Store.add_setup_change`,
`Store.list_setup_changes`, a consumer in `export/build.py` and another in
`prompts/context.py` — and **no production caller anywhere**. The charter calls
it the single biggest gap in the system, because everything downstream is
blocked on it: a change is not an experiment until it is recorded, a regression
cannot be recognised without knowing what moved, and setup history is not
knowledge until a change is tied to the run that tested it.

The caller was missing because the obvious one is impossible. The table is
written as *mid-session* changes, and of the 23 setup values the only one the
feed can see change mid-session is the gearbox — the other 22 have no channel.
So that case needs a human to type it and has no interface.

**The between-session case needs neither, and it is the one that carries the
experiment.** A session opens against a sheet; the last session on this car and
circuit opened against another; the difference is what this run tests.
"""
from __future__ import annotations

import pytest

from pitcrew.setup.sheet import SetupSheet
from pitcrew.store.db import Store


def a_sheet(name: str, circuit: str | None = "fuji-international-speedway",
            **values) -> SetupSheet:
    base = {"arb_f": 6.0, "arb_r": 4.0, "rh_f": 63.0, "rh_r": 72.0,
            "cam_f": 2.4, "df_f": 395.0}
    base.update(values)
    return SetupSheet(car_name="Test Car", sheet_name=name, purpose="race",
                      values=base, circuit_key=circuit)


def an_event(store: Store, car: str = "Test Car") -> int:
    return store.create_event(name="R", track="Fuji", car_name=car,
                              race_type="laps", race_laps=20)


def test_a_changed_sheet_is_filed_as_this_run_s_experiment(store: Store):
    event_id = an_event(store)
    first = store.save_setup_sheet(a_sheet("v1"))
    s1 = store.start_session(event_id, "practice", setup_sheet_id=first)
    store.note_sheet_change(s1)

    second = store.save_setup_sheet(a_sheet("v2", arb_f=7.0, rh_f=65.0))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=second)
    written = store.note_sheet_change(s2)

    assert written == 2, "two values moved, so two experiments"
    changes = {c.key: (c.from_value, c.to_value)
               for c in store.list_setup_changes(s2)}
    assert changes["arb_f"] == (6.0, 7.0)
    assert changes["rh_f"] == (63.0, 65.0)
    assert all(c.from_lap == 1 for c in store.list_setup_changes(s2))


def test_the_first_session_on_a_car_is_not_a_change(store: Store):
    event_id = an_event(store)
    sheet = store.save_setup_sheet(a_sheet("v1"))
    session = store.start_session(event_id, "practice", setup_sheet_id=sheet)

    assert store.note_sheet_change(session) == 0
    assert store.list_setup_changes(session) == []


def test_an_unchanged_sheet_files_nothing(store: Store):
    event_id = an_event(store)
    sheet = store.save_setup_sheet(a_sheet("v1"))
    s1 = store.start_session(event_id, "practice", setup_sheet_id=sheet)
    store.note_sheet_change(s1)
    s2 = store.start_session(event_id, "practice", setup_sheet_id=sheet)

    assert store.note_sheet_change(s2) == 0


def test_it_is_idempotent(store: Store):
    """Opening the same session twice must not double the ledger."""
    event_id = an_event(store)
    store.start_session(event_id, "practice",
                        setup_sheet_id=store.save_setup_sheet(a_sheet("v1")))
    second = store.save_setup_sheet(a_sheet("v2", arb_f=7.0))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=second)

    assert store.note_sheet_change(s2) == 1
    assert store.note_sheet_change(s2) == 0
    assert len(store.list_setup_changes(s2)) == 1


def test_another_circuit_is_not_an_experiment(store: Store):
    """A sheet built for another track differs in every value that responds to
    the track. Calling that an experiment fills the ledger with noise — the
    same error `tools/check_setup_sheets.py` was making one level up."""
    event_id = an_event(store)
    watkins = store.save_setup_sheet(
        a_sheet("Watkins", circuit="watkins-glen-international", arb_f=9.0))
    s1 = store.start_session(event_id, "practice", setup_sheet_id=watkins)
    store.note_sheet_change(s1)

    fuji = store.save_setup_sheet(a_sheet("Fuji v1"))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=fuji)

    assert store.note_sheet_change(s2) == 0, (
        "a different circuit's sheet is not a change to this one")


def test_a_value_appearing_or_disappearing_is_recorded(store: Store):
    """Null is not zero — a value that was not set and now is, is a change."""
    event_id = an_event(store)
    store.start_session(event_id, "practice",
                        setup_sheet_id=store.save_setup_sheet(a_sheet("v1")))
    with_toe = store.save_setup_sheet(a_sheet("v2", toe_r=0.20))
    s2 = store.start_session(event_id, "practice", setup_sheet_id=with_toe)

    store.note_sheet_change(s2)
    changes = {c.key: (c.from_value, c.to_value)
               for c in store.list_setup_changes(s2)}
    assert changes["toe_r"] == (None, 0.20)


def test_a_session_with_no_sheet_files_nothing(store: Store):
    event_id = an_event(store)
    session = store.start_session(event_id, "practice", setup_sheet_id=None)

    assert store.note_sheet_change(session) == 0


def test_the_controller_calls_it_on_both_session_kinds():
    """The gap was never the writer — it was that nothing called it. Practice
    and race both open against a sheet and both are experiments."""
    import inspect

    from pitcrew import controller

    source = inspect.getsource(controller)
    assert source.count("self._note_sheet_change()") >= 2


def test_the_ledger_reaches_the_export(store: Store):
    """`export/build.py` and `prompts/context.py` have consumed this table all
    along. They were reading an empty one."""
    event_id = an_event(store)
    store.start_session(event_id, "practice",
                        setup_sheet_id=store.save_setup_sheet(a_sheet("v1")))
    s2 = store.start_session(
        event_id, "practice",
        setup_sheet_id=store.save_setup_sheet(a_sheet("v2", cam_f=3.0)))
    store.note_sheet_change(s2)

    exported = [c.as_export() for c in store.list_setup_changes(s2)]

    assert exported == [{"fromLap": 1, "key": "cam_f",
                         "from": 2.4, "to": 3.0}]
