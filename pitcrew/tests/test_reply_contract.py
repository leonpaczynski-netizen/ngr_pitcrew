"""A reply the app can read, not just one the driver can.

*"Also refine prompts to AI they aren't including the direction for the return
Json file and aren't as clear as they need to be."*

Correct, and the reader was already there: `setup/parse.py` has always
accepted the export contract's own JSON. The prompts simply never asked for
it, so every reply came back as prose and every value was retyped by hand —
which is where transcription errors come from.

The outcome prompt was the exception and shows the shape of the mistake: it
asked for a paste block per sheet, in a second format described in a second
place. Two shapes is worse than one, so there is one envelope now and all
three prompts point at it.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.setup.parse import (
    QUALIFYING,
    RACE,
    parse_reply,
    parse_sheet,
)


def a_reply(**overrides) -> str:
    payload = {
        "contract": "gt7-pitcrew-reply/1.0",
        "car": "Porsche 911 RSR (991) '17",
        "circuit": "Autodromo Nazionale Monza",
        "sheets": [
            {
                "purpose": "race",
                "sheetName": "Monza race v3",
                "values": {"rh_f": 60, "rh_r": 65, "cam_f": -3.2},
                "gears": [3.10, 2.28, 1.79],
                "why": {"cam_f": "front-limited entry on the long corners"},
            },
            {
                "purpose": "qualifying",
                "sheetName": "Monza quali v3",
                "values": {"rh_f": 55, "rh_r": 60, "cam_f": -3.6},
            },
        ],
        "clamped": ["arb_r: hit the maximum, the car wants more than GT7 gives"],
        "testFirst": ["one click of rear ARB off if it is still loose"],
    }
    payload.update(overrides)
    return json.dumps(payload)


# ------------------------------------------------------------- the round trip

def test_both_sheets_come_back_separately():
    reply = parse_reply(a_reply())
    assert reply.race.sheet_name == "Monza race v3"
    assert reply.qualifying.sheet_name == "Monza quali v3"
    assert reply.race.values["cam_f"] == -3.2
    assert reply.qualifying.values["cam_f"] == -3.6


def test_the_gearbox_survives():
    assert parse_reply(a_reply()).race.gears == [3.10, 2.28, 1.79]


def test_the_reasons_are_kept_with_the_sheet_they_belong_to():
    """A sheet with no reasons is a sheet nobody can argue with a month
    later."""
    reply = parse_reply(a_reply())
    assert "front-limited" in reply.why[RACE]["cam_f"]


def test_what_had_to_be_clamped_is_carried():
    reply = parse_reply(a_reply())
    assert reply.clamped and "arb_r" in reply.clamped[0]
    assert reply.test_first


# ------------------------------------------------------------- what it refuses

def test_an_invented_key_is_surfaced_and_never_silently_dropped():
    """The rule that matters: a value quietly missed is a setup change the
    driver thinks he made and did not."""
    reply = parse_reply(a_reply(sheets=[{
        "purpose": "race", "values": {"rh_f": 60, "front_wing": 7}}]))
    assert reply.race.values == {"rh_f": 60.0}
    assert any("front_wing" in line for line in reply.unmatched)


def test_a_null_stays_a_null_and_never_becomes_zero():
    """Zero is a real value on camber, toe and ballast. A null read as zero
    is a setup change nobody asked for."""
    reply = parse_reply(a_reply(sheets=[{
        "purpose": "race", "values": {"rh_f": 60, "cam_r": None}}]))
    assert "cam_r" not in reply.race.values


def test_an_untagged_sheet_is_filed_as_the_race_sheet():
    """The prompts ask for the tag. A reply that omitted it has still sent
    the sheet that matters most, so it is filed rather than dropped."""
    reply = parse_reply(a_reply(sheets=[{
        "sheetName": "v3", "values": {"rh_f": 60}}]))
    assert reply.race is not None
    assert reply.qualifying is None


# ------------------------------------------------- it still reads the old ways

def test_a_reply_that_ignored_the_contract_is_still_read():
    """A driver pasting something is a driver trying to record a setup, and
    refusing on a formatting technicality helps nobody."""
    reply = parse_reply("Ride Height (Front): 60\nCamber Front: -3.2")
    assert reply.race.values["rh_f"] == 60.0
    assert reply.race.values["cam_f"] == -3.2


def test_a_bare_setup_block_still_parses_as_it_always_did():
    block = json.dumps({"setup": {"sheetName": "v1", "values": {"rh_f": 60}}})
    assert parse_sheet(block).values == {"rh_f": 60.0}


def test_the_envelope_reduces_to_its_race_sheet_for_old_callers():
    """`parse_sheet` keeps its single-sheet meaning, so nothing that already
    reads a pasted block has to know the contract changed."""
    assert parse_sheet(a_reply()).sheet_name == "Monza race v3"


def test_nothing_readable_is_not_an_exception():
    reply = parse_reply("thanks, that all looks good to me")
    assert reply.sheets == {}
    assert reply.summary() == "no sheet found"


def test_the_summary_names_both_sheets():
    summary = parse_reply(a_reply()).summary()
    assert RACE in summary and QUALIFYING in summary
    assert "clamped" in summary
