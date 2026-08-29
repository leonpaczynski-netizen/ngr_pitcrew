"""Authoritative writes from outside the app, and what makes them survivable.

⚠ **The doctrine changed on 29 Aug 2026.** `mcp/server.py` used to state that
reads are open and writes only propose, and its reason was good: the app had
been wrong about which sheet was in the car three sessions out of three, so a
tool that wrote one directly would make that unrecoverable.

The driver's decision is that the database is the single source of truth for the
app and for the race engineer both - a correction that lives in a conversation
leaves 96 sessions of history wrong. So `unrecoverable` is the word that had to
stop being true, and these are the tests for the thing that made it stop.
"""
from __future__ import annotations

import pytest

from pitcrew.setup.sheet import SetupSheet
from pitcrew.store.db import Store


@pytest.fixture()
def store(tmp_path):
    one = Store(tmp_path / "t.db")
    try:
        yield one
    finally:
        one.close()


def a_sheet(name: str, **values) -> SetupSheet:
    return SetupSheet(car_name="Ford Shelby GT350R '16", sheet_name=name,
                      values=values or {"rh_f": 62}, gears=[],
                      purpose="race", circuit_key="red-bull-ring-short-track")


# --- the audit trail --------------------------------------------------------

def test_a_write_records_what_it_replaced(store):
    """Without it a sheet written from outside is indistinguishable from one
    the driver typed himself."""
    before = a_sheet("race v1", rh_f=62)
    store.save_setup_sheet(before)

    store.note_engineer_write(
        "setup_sheet", summary="wrote Rev B", author="race engineer (MCP)",
        before={"sheet_name": "race v1"}, after={"sheet_name": "Rev B"})

    rows = store.list_engineer_writes()
    assert len(rows) == 1
    assert rows[0]["author"] == "race engineer (MCP)"
    assert "race v1" in rows[0]["before_json"]


def test_writes_come_back_newest_first(store):
    for n in range(3):
        store.note_engineer_write("setup_sheet", summary=f"write {n}")
    assert [row["summary"] for row in store.list_engineer_writes()] == [
        "write 2", "write 1", "write 0"]


def test_they_can_be_filtered_by_kind(store):
    store.note_engineer_write("setup_sheet", summary="a sheet")
    store.note_engineer_write("strategy", summary="a plan")
    assert [row["summary"] for row in
            store.list_engineer_writes(kind="strategy")] == ["a plan"]


# --- the undo ---------------------------------------------------------------

def test_undo_puts_the_previous_sheet_back(store):
    from dataclasses import asdict

    before = a_sheet("race v1", rh_f=62)
    store.save_setup_sheet(before)
    write_id = store.note_engineer_write(
        "setup_sheet", summary="wrote Rev B", before=asdict(before))
    store.save_setup_sheet(a_sheet("race v1", rh_f=70))

    store.undo_engineer_write(write_id)

    back = store.sheet_for("Ford Shelby GT350R '16", "race",
                           "red-bull-ring-short-track")
    assert back.values["rh_f"] == 62


def test_undoing_twice_says_so_rather_than_doing_it_again(store):
    from dataclasses import asdict

    before = a_sheet("race v1")
    store.save_setup_sheet(before)
    write_id = store.note_engineer_write("setup_sheet", summary="x",
                                         before=asdict(before))
    store.undo_engineer_write(write_id)

    assert "already undone" in store.undo_engineer_write(write_id)


def test_a_write_that_created_a_sheet_has_nothing_to_put_back(store):
    """Said rather than silently doing nothing."""
    write_id = store.note_engineer_write("setup_sheet", summary="new sheet")
    assert "nothing to put back" in store.undo_engineer_write(write_id)


def test_a_plan_is_never_undone(store):
    """**It may already be armed and partly executed.** Rewinding one mid-race
    would leave the coordinator running against a document nobody approved. A
    plan is replaced by writing a better one."""
    write_id = store.note_engineer_write("strategy", summary="a plan",
                                         before={"anything": 1})
    with pytest.raises(ValueError) as raised:
        store.undo_engineer_write(write_id)
    assert "setup_sheet" in str(raised.value)


def test_undoing_a_write_that_does_not_exist_raises(store):
    with pytest.raises(ValueError):
        store.undo_engineer_write(9999)


# --- the confirm-not-recall wiring ------------------------------------------

def test_the_question_registry_is_reachable_from_the_app():
    """**Five hundred lines, a registry, a gate and working resolvers, with no
    caller anywhere in the app** until 29 Aug - reachable only from its own
    test file, while the thirteen-field form its docstring is a rebuttal of
    was what the driver actually saw.

    This asserts the seam exists, which is the thing that was missing. The
    fourth built-and-never-wired defect found this week.
    """
    import inspect

    from pitcrew.controller import PitCrewController

    source = inspect.getsource(PitCrewController._ask_only_what_is_left)
    assert "from pitcrew.prompts.questions import resolve" in source
    assert "set_questions" in source


def test_the_screen_can_receive_a_resolution():
    from pitcrew.prompts.questions import Answer, Resolution

    class FakeLabel:
        def setText(self, text): self.text = text
        def set_ink(self, ink): self.ink = ink

    from pitcrew.ui.engineer_screen import EngineerScreen

    screen = EngineerScreen.__new__(EngineerScreen)
    screen.questions_note = FakeLabel()
    screen.set_questions(Resolution(
        answered={"tyre_state_at_end": Answer(
            "40 percent", "hud gauge", "read off 12 crossings", 12)},
        asked=[], suppressed=("tyre_state_at_end",)))

    assert "tyre_state_at_end" in screen.questions_note.text


def test_a_resolver_that_broke_is_named_rather_than_swallowed():
    """A question that quietly came back is one only he would notice."""
    from pitcrew.prompts.questions import Resolution

    class FakeLabel:
        def setText(self, text): self.text = text
        def set_ink(self, ink): self.ink = ink

    from pitcrew.ui.engineer_screen import EngineerScreen

    screen = EngineerScreen.__new__(EngineerScreen)
    screen.questions_note = FakeLabel()
    screen.set_questions(Resolution(failed=("rear_wheelspin_pattern",)))

    assert "could not check" in screen.questions_note.text
    assert "rear_wheelspin_pattern" in screen.questions_note.text
