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
                "values": {"rh_f": 60, "rh_r": 65, "cam_f": 3.2},
                "gears": [3.10, 2.28, 1.79],
                "why": {"cam_f": "front-limited entry on the long corners"},
            },
            {
                "purpose": "qualifying",
                "sheetName": "Monza quali v3",
                "values": {"rh_f": 55, "rh_r": 60, "cam_f": 3.6},
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
    assert reply.race.values["cam_f"] == 3.2
    assert reply.qualifying.values["cam_f"] == 3.6


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
    reply = parse_reply("Ride Height (Front): 60\nToe Front: -0.05")
    assert reply.race.values["rh_f"] == 60.0
    # Toe is one of the three settings GT7 does let go negative, so this also
    # covers the line reader keeping a sign it should keep.
    assert reply.race.values["toe_f"] == -0.05


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


# ------------------------------------------- what actually arrives in the box
#
# He copies the whole reply. That is what copying a reply means: two readable
# setup sheets, a diagnosis, a delta table, and the JSON block somewhere near
# the end. Reading the text only when it *starts* with a brace found the JSON
# in none of them - it fell through to the line reader, took what it could out
# of the markdown table, and lost the second sheet in silence.

WHOLE_REPLY = """Here is the revised setup for Monza.

## Race sheet

| Parameter | Value | Clicks from min | % of range |
|---|---|---|---|
| Ride height front | 62 mm | 7 | 28% |
| Camber front | 3.2 | 16 | 53% |

The front ride height comes up to settle the entry understeer.

## Qualifying sheet

Same as race with a softer rear bar.

```json
{
  "contract": "gt7-pitcrew-reply/1.0",
  "sheets": [
    {"purpose": "race", "sheetName": "Monza race v4",
     "values": {"rh_f": 62, "cam_f": 3.2}, "gears": [3.10, 2.28]},
    {"purpose": "qualifying", "sheetName": "Monza quali v4",
     "values": {"rh_f": 58, "cam_f": 3.5}}
  ],
  "clamped": [],
  "testFirst": ["rear ARB one softer if it is still loose on exit"]
}
```

Let me know how it feels."""


def test_the_whole_reply_pasted_finds_both_sheets():
    reply = parse_reply(WHOLE_REPLY)
    assert set(reply.sheets) == {RACE, QUALIFYING}
    assert reply.race.values == {"rh_f": 62.0, "cam_f": 3.2}
    assert reply.qualifying.values == {"rh_f": 58.0, "cam_f": 3.5}
    assert reply.race.gears == [3.10, 2.28]
    assert reply.test_first


def test_the_json_wins_over_the_markdown_table_beside_it():
    """Both are in the paste and they are the same sheet twice. The JSON is
    the one that was written to be read."""
    reply = parse_reply(WHOLE_REPLY)
    assert reply.source == "json"
    assert reply.unmatched == [], "the prose is not junk to be reported"


def test_a_block_fenced_without_a_language_tag_still_reads():
    """A reply that fences it bare is trying to do the right thing."""
    text = "Here you go.\n\n```\n" + json.dumps(
        {"sheets": [{"purpose": "race", "values": {"rh_f": 60}}]}) + "\n```\n"
    assert parse_reply(text).race.values == {"rh_f": 60.0}


def test_the_last_block_is_the_one_that_counts():
    """The contract puts it at the end, so where a reply carries more than one
    the last is the one that was meant - a revision after a first attempt, or
    the prompt's own example quoted back."""
    first = json.dumps({"sheets": [{"purpose": "race", "values": {"rh_f": 99}}]})
    last = json.dumps({"sheets": [{"purpose": "race", "values": {"rh_f": 60}}]})
    text = f"First thought:\n```json\n{first}\n```\nOn reflection:\n```json\n{last}\n```"
    assert parse_reply(text).race.values == {"rh_f": 60.0}


def test_prose_with_no_block_at_all_still_falls_back_to_reading_it():
    """A reply that ignored the contract is still a reply. Refusing on a
    formatting technicality helps nobody."""
    reply = parse_reply(
        "## Race sheet\n\nRide Height (Front): 62\nCamber Front: 3.2\n")
    assert reply.race.values == {"rh_f": 62.0, "cam_f": 3.2}


def test_the_shape_the_prompt_prints_is_the_shape_the_parser_reads():
    """The round trip that matters: the example in the prompt, fed to the app.

    If these two drift, every reply is malformed and nothing says so.
    """
    from pitcrew.prompts.templates import templates

    shape = "\n".join(templates()["shared"]["returnShape"])
    reply = parse_reply(shape)
    assert reply.race is not None, "the prompt's own example must parse"
    assert reply.race.values, "and must carry values"
    assert reply.clamped and reply.test_first
