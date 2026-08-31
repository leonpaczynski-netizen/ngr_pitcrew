"""Whether anybody has checked what is in the car.

Rank zero of the diagnosis hierarchy. The setup record was wrong in five
consecutive sessions and the app caught none of them - every one was found by
the driver mentioning it in passing.

These test the two detectors and the one place they act: **the export refuses;
the capture never does.** A session not recorded cannot be re-driven. A sheet
can be corrected afterwards and the session re-bound.
"""
from __future__ import annotations

import pytest

from pitcrew.setup import doubt as setup_doubt
from pitcrew.setup.doubt import GEARBOX, UNFILED, Doubt


# --- the gearbox, which is the only setup value the feed can check ----------

def test_a_gearbox_that_disagrees_with_the_sheet_is_doubt():
    found = setup_doubt.gearbox_doubt(
        {"matchesSheet": False, "matchesSheetCovers": "the ratios"})
    assert found
    assert found.reasons == (GEARBOX,)


def test_a_gearbox_that_agrees_is_not_doubt():
    assert not setup_doubt.gearbox_doubt({"matchesSheet": True})


def test_an_unknown_gearbox_is_not_doubt():
    """`None` means the box was never fitted or the sheet has no gears.

    Reading an unknown as a disagreement would raise an alarm on every
    session that never reached top gear - which is most short-circuit
    practice - and an alarm that fires on everything is one nobody reads.
    """
    assert not setup_doubt.gearbox_doubt({"matchesSheet": None})
    assert not setup_doubt.gearbox_doubt({})
    assert not setup_doubt.gearbox_doubt(None)


# --- a revision issued and never filed --------------------------------------

class FakeStore:
    def __init__(self, sheet, filed):
        self._sheet, self._filed = sheet, filed

    def sheet_for(self, car, purpose, circuit_key=None):
        return self._sheet

    def sheet_filed_on(self, sheet_id):
        return self._filed


class FakeSheet:
    id = 1


@pytest.fixture()
def setups(tmp_path, monkeypatch):
    folder = tmp_path / "brain" / "_inbox" / "setups"
    folder.mkdir(parents=True)
    monkeypatch.setattr(setup_doubt, "PROJECT_ROOT", tmp_path)
    return folder


def test_a_document_newer_than_the_sheet_is_doubt(setups):
    (setups / "2026-08-26-shelby-red-bull-ring-short.md").write_text("x")
    store = FakeStore(FakeSheet(), "2026-08-20")

    found = setup_doubt.unfiled_revisions(
        store, "Ford Shelby GT350R '16", "red-bull-ring-short-track")

    assert found.reasons == (UNFILED,)
    assert "2026-08-26-shelby-red-bull-ring-short.md" in found.describe()


def test_a_document_older_than_the_sheet_was_filed(setups):
    """The real state of the archive on the day this was written: every sheet
    on file postdates its newest document, so the detector is silent and that
    silence is a true result rather than a dead one."""
    (setups / "2026-08-26-shelby-red-bull-ring-short.md").write_text("x")
    store = FakeStore(FakeSheet(), "2026-08-27")

    assert not setup_doubt.unfiled_revisions(
        store, "Ford Shelby GT350R '16", "red-bull-ring-short-track")


def test_another_car_at_another_track_is_not_this_session_s_revision(setups):
    """Both the car AND the circuit have to appear, or every document in the
    folder is newer than some sheet somewhere and it cries wolf every time."""
    (setups / "2026-08-26-huracan-fuji.md").write_text("x")
    store = FakeStore(FakeSheet(), "2026-08-20")

    assert not setup_doubt.unfiled_revisions(
        store, "Ford Shelby GT350R '16", "red-bull-ring-short-track")


def test_the_right_car_at_the_wrong_track_is_not_it_either(setups):
    (setups / "2026-08-26-shelby-yas-marina.md").write_text("x")
    store = FakeStore(FakeSheet(), "2026-08-20")

    assert not setup_doubt.unfiled_revisions(
        store, "Ford Shelby GT350R '16", "red-bull-ring-short-track")


def test_no_sheet_at_all_is_a_louder_fault_and_not_reported_here(setups):
    """The export already refuses a payload with no setup block. Reporting
    "there is a document you have not filed" on top of that names the smaller
    of the two problems."""
    (setups / "2026-08-26-shelby-red-bull-ring-short.md").write_text("x")

    assert not setup_doubt.unfiled_revisions(
        FakeStore(None, None), "Ford Shelby GT350R '16",
        "red-bull-ring-short-track")


def test_a_sheet_with_no_filing_date_cannot_be_compared(setups):
    """**The bug the first draft shipped.** It read `sheet.updated_at`, which
    `SetupSheet` does not have, so `getattr` returned None on every sheet and
    the detector was silent on all eight events while looking correct."""
    (setups / "2026-08-26-shelby-red-bull-ring-short.md").write_text("x")

    assert not setup_doubt.unfiled_revisions(
        FakeStore(FakeSheet(), None), "Ford Shelby GT350R '16",
        "red-bull-ring-short-track")


def test_the_filing_date_comes_off_the_store_and_not_the_dataclass():
    """A regression guard on the same bug: if `_sheet_date` stops asking the
    store, this fails rather than going quietly silent."""
    asked = []

    class Watching(FakeStore):
        def sheet_filed_on(self, sheet_id):
            asked.append(sheet_id)
            return "2026-08-20"

    setup_doubt._sheet_date(Watching(FakeSheet(), None), FakeSheet())
    assert asked == [1]


# --- an empty answer is not a clean bill of health --------------------------

def test_empty_means_nothing_flagged_and_not_verified():
    """Two of the five failures on record would have been caught by neither
    detector. An empty result that read as verified would be the same
    confident wrong answer in a new place."""
    assert not Doubt()
    assert Doubt().describe() == ""


def test_both_detectors_report_together():
    found = Doubt((GEARBOX, UNFILED), ("one.", "two."))
    assert found
    assert found.describe() == "one. two."


# --- the export refuses; the capture never does -----------------------------

def _an_export(monkeypatch, found, **kwargs):
    """Drive the real `_build` with a controlled doubt verdict."""
    from pitcrew.export import build as export_build

    monkeypatch.setattr(export_build.setup_doubt, "for_event",
                        lambda *a, **k: found)
    from pitcrew.store.db import Store

    store = Store()
    try:
        return export_build.build_event_export(store, 4, kind="practice",
                                               **kwargs)
    finally:
        store.close()


def test_a_doubtful_setup_record_refuses_the_export(monkeypatch):
    """An export is read by a knowledge base, which reasons from it and issues
    a revision. That is where a wrong premise stops being a local error."""
    from pitcrew.export.payload import ExportRefused

    with pytest.raises(ExportRefused) as raised:
        _an_export(monkeypatch, Doubt((GEARBOX,), ("the box disagrees.",)))
    assert "the box disagrees." in str(raised.value)
    assert "photograph" in str(raised.value).lower(), \
        "the refusal has to say what would settle it"


def test_a_clean_record_exports(monkeypatch):
    payload = _an_export(monkeypatch, Doubt())
    assert payload["format"]


def test_an_acknowledged_doubt_travels_with_the_payload(monkeypatch):
    """**Acknowledged, never suppressed.** A refusal with no way forward makes
    every historical event permanently unexportable - three of the eight on
    file fail this today - but a payload that quietly drops the warning is
    worse than the refusal it replaced.
    """
    payload = _an_export(monkeypatch,
                         Doubt((GEARBOX,), ("the box disagrees.",)),
                         acknowledge_setup_doubt=True)
    assert "SETUP RECORD UNVERIFIED" in payload["notes"]
    assert "the box disagrees." in payload["notes"]


# --- an event that spans a gearbox revision ---------------------------------
#
# **The mistake that refused three real exports on the day this shipped.**
# `matchesSheet` takes the most recent lap's box and compares it against
# whichever single sheet the merged session carries, so a driver who revised
# his gearbox mid-event - the ordinary way of testing one - read as a wrong
# setup record. Measured on the archive: Yas Marina ran two boxes on two
# sheets and Watkins Glen ran two on two, and all four matched their own
# sheets exactly. Nothing was wrong with any of them.

FAILED_FLAT = {"matchesSheet": False, "matchesSheetCovers": "the ratios"}


def test_a_gearbox_revision_is_not_a_wrong_record():
    """Every sheet matched the laps driven on it. The event ran more than one
    gearbox, which the export already declares in `gearboxChangedMidSession` -
    a change is a known state, not a wrong record."""
    assert not setup_doubt.gearbox_doubt(FAILED_FLAT, disagreeing_sheets=[])


def test_a_sheet_that_disagrees_with_its_own_laps_is_still_doubt():
    found = setup_doubt.gearbox_doubt(FAILED_FLAT, disagreeing_sheets=[45])
    assert found.reasons == (GEARBOX,)
    assert "45" in found.describe()


def test_the_flat_boolean_still_answers_a_caller_that_cannot_group_laps():
    """`None` is not an empty list: one means "nobody grouped them", the other
    means "grouped, and they all agreed"."""
    assert setup_doubt.gearbox_doubt(FAILED_FLAT, disagreeing_sheets=None)


def test_sheets_disagree_names_only_the_sheet_that_is_wrong():
    from dataclasses import dataclass, field

    from pitcrew.analysis.gearing import sheets_disagree

    @dataclass
    class Lap:
        setup_sheet_id: int
        gear_ratios: list = field(default_factory=list)

    A = [3.832, 2.645, 1.96, 1.52, 1.235, 1.05]
    B = [3.4, 2.41, 1.76, 1.5, 1.32, 1.165]
    laps = [Lap(1, A), Lap(1, A), Lap(2, B), Lap(2, B)]

    # Both sheets name the box their own laps ran: nothing is wrong.
    assert sheets_disagree(laps, {1: A, 2: B}.get) == []
    # Sheet 2 names sheet 1's box: that one, and only that one.
    assert sheets_disagree(laps, {1: A, 2: A}.get) == [2]


def test_a_sheet_with_no_gears_is_not_a_disagreement():
    """An unknown is not a disagreement - the same rule as `matchesSheet`."""
    from dataclasses import dataclass, field

    from pitcrew.analysis.gearing import sheets_disagree

    @dataclass
    class Lap:
        setup_sheet_id: int
        gear_ratios: list = field(default_factory=list)

    assert sheets_disagree([Lap(1, [3.8, 2.6])], lambda _: None) == []


def test_the_archive_stopped_refusing_the_events_that_were_correct():
    """Yas Marina and Watkins Glen: two boxes, two sheets, all four matching.

    They refused for a day because the comparison was against the wrong sheet,
    and this is the regression guard on that.
    """
    from pitcrew.export.build import build_event_export
    from pitcrew.store.db import Store

    store = Store()
    try:
        for event_id in (2, 3):
            assert build_event_export(store, event_id, kind="practice")["format"]
    finally:
        store.close()


def test_a_change_made_in_a_later_run_reaches_the_payload():
    """**Red Bull Ring is the case.** `de_r` was 32 in session 93 and 38 in
    94, and `setup_changes` is per session - so an export reading only the
    merged session's id came out naming the v1 sheet, a gearbox that sheet
    does not hold, and no statement that anything had moved. The reader would
    have diagnosed a car on de_r 32.
    """
    from pitcrew.export.build import build_event_export
    from pitcrew.store.db import Store

    store = Store()
    try:
        setup = build_event_export(store, 8, kind="practice")["setup"]
    finally:
        store.close()

    changes = {one["key"]: one for one in (setup.get("driverChanges") or ())}
    assert "de_r" in changes, \
        "the change made in the second run never reached the payload"
    assert (changes["de_r"]["from"], changes["de_r"]["to"]) == (32.0, 38.0)


def test_the_merged_session_carries_every_session_id():
    """The merge keeps every session id, not just the first.

    **Containment, not equality, because this reads the live database.** It
    asserted `== [93, 94]` and went red on 30 Aug 2026 the moment three more
    practice sessions were driven at Red Bull Ring - the test broke because the
    driver drove, which is not a defect in the code under test and is not
    something a green suite should depend on him not doing.

    What the test is actually for is that the merge does not drop ids on the
    floor, so that is what it checks: the two known sessions are present, the
    list is sorted, and it carries no duplicates.
    """
    from pitcrew.export.build import _merged_session
    from pitcrew.store.db import Store

    store = Store()
    try:
        merged = _merged_session(store.list_sessions(8, "practice"))
    finally:
        store.close()
    ids = merged["session_ids"]
    assert {93, 94} <= set(ids)
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
