"""Authoritative writes from outside the app, and what makes them survivable.

⚠ **The doctrine changed twice.** On 29 Aug 2026 `mcp/server.py` stopped
refusing to apply anything: the driver's decision was that the database is the
single source of truth for the app and for the race engineer both, because a
correction that lives in a conversation leaves 96 sessions of history wrong.

On 5 Sep 2026 the setup sheet left the app entirely - the tune builder holds
the car and the gearbox now, and the driver confirms what is in it against
GT7's own settings screen. **The audit trail did not leave with it.** What is
still written from outside is the race plan, the race briefing and the upshift
table, and every one of those reaches the driver under a helmet, so the record
of who wrote it and when is worth more than it was, not less.

`undo` went with the sheet. It only ever restored a `setup_sheet`, and it was
right to: a sheet describes something that already exists, so putting the
previous description back is always meaningful. A plan may be armed and partly
executed, and a shift table is replaced by issuing a better one.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer.shift_points import ShiftPoints
from pitcrew.store.db import Store


@pytest.fixture()
def store(tmp_path):
    one = Store(tmp_path / "t.db")
    try:
        yield one
    finally:
        one.close()


# --- the audit trail --------------------------------------------------------

def test_a_write_records_what_it_replaced(store):
    """Without it, a table written from outside is indistinguishable from one
    the driver set up himself - and this one is what he hears at the wheel."""
    before = ShiftPoints(car_name="Ford Shelby GT350R '16",
                         circuit_key="red-bull-ring-short-track",
                         performance={6: 8000.0})
    store.save_shift_points(before)

    store.note_engineer_write(
        "shift_points", summary="raised 6th to 8250",
        author="race engineer (MCP)",
        before=before.as_export(),
        after=ShiftPoints(car_name="Ford Shelby GT350R '16",
                          circuit_key="red-bull-ring-short-track",
                          performance={6: 8250.0}).as_export())

    rows = store.list_engineer_writes()
    assert len(rows) == 1
    assert rows[0]["author"] == "race engineer (MCP)"
    assert "8000" in rows[0]["before_json"]
    assert "8250" in rows[0]["after_json"]


def test_writes_come_back_newest_first(store):
    for n in range(3):
        store.note_engineer_write("shift_points", summary=f"write {n}")
    assert [row["summary"] for row in store.list_engineer_writes()] == [
        "write 2", "write 1", "write 0"]


def test_they_can_be_filtered_by_kind(store):
    store.note_engineer_write("shift_points", summary="a table")
    store.note_engineer_write("strategy", summary="a plan")
    assert [row["summary"] for row in
            store.list_engineer_writes(kind="strategy")] == ["a plan"]


def test_re_issuing_a_table_leaves_two_entries_in_the_ledger(store):
    """The table is replaced, the record of replacing it is not. One row per
    write is the only way to say who changed the beep and when."""
    for rpm in (8000.0, 8250.0):
        table = ShiftPoints(car_name="A", circuit_key="monza",
                            performance={6: rpm})
        store.save_shift_points(table)
        store.note_engineer_write("shift_points", summary=f"6th at {rpm:.0f}",
                                  after=table.as_export())

    assert len(store.list_shift_points("A")) == 1
    assert len(store.list_engineer_writes(kind="shift_points")) == 2
