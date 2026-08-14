"""The prompts have to be true, and they have to agree with themselves.

Two failures this guards, both found by generating the real prompts against
the real database and reading them.

**The prose disagreed with its own payload.** The refinement's headline read
"best lap 1:44.912 over 79 counted laps" while the `gt7-pitcrew` block
attached underneath it read 1:46.828 over 73. The prose section was computing
its totals on unclassified laps — no out-laps struck, no incidents, and no
fuel-implausible test — so a lap that burned 0.16 L against a 6.4 L median was
the headline. That is a lap boundary landing inside a pit transition, not a
lap of the circuit, and the knowledge base would have read it as the car's
potential and built a sheet to reach it.

**The refinement went out with no telemetry at all.** The payload is refused
without a game version, and the version moved to app settings without the
prompt path being told. Every refinement for an event created without the old
field was arriving as prose only.
"""
from __future__ import annotations

import json
import re

import pytest

from pitcrew.prompts.build import build_prompt
from pitcrew.prompts.context import gather
from pitcrew.prompts.report import DriverReport
from pitcrew.prompts.templates import templates
from pitcrew.setup.vocabulary import SETUP_KEY_NAMES

from pitcrew.prompts.build import BRIEF, OUTCOME, REFINEMENT

from .test_prompts import practice_event  # noqa: F401


def a_prompt(store, event_id, kind, **overrides):
    context = gather(store, event_id=event_id, kind=kind,
                     game_version=overrides.pop("game_version", "1.70"))
    return build_prompt(context, DriverReport(), kind=kind)


# ------------------------------------------------------ the prose is the data

def test_the_headline_pace_matches_the_attached_payload(store, practice_event):
    """One prompt, one set of numbers. Two would be worse than none: the
    reader cannot tell which is the measurement."""
    prompt = a_prompt(store, practice_event, REFINEMENT)
    block = re.search(r"```json\n(\{.*?\n\})\n```", prompt.text, re.S)
    assert block, "the refinement carries its telemetry payload"
    payload = json.loads(block.group(1))

    counted = payload["session"]["lapsCounted"]
    assert f"over {counted} counted laps" in prompt.text

    best = payload["session"]["bestLapMs"]
    minutes, remainder = divmod(best, 60_000)
    seconds, millis = divmod(remainder, 1000)
    assert f"{minutes}:{seconds:02d}.{millis:03d}" in prompt.text


def test_the_payload_is_attached_when_the_app_knows_the_version(store,
                                                               practice_event):
    """It is refused without one, and a refused payload is a refinement sent
    with no telemetry in it - the failure it exists to avoid."""
    prompt = a_prompt(store, practice_event, REFINEMENT)
    assert prompt.warnings == []
    assert "gt7-pitcrew/" in prompt.text


def test_no_version_anywhere_says_so_rather_than_going_out_silently(store,
                                                                    practice_event):
    """The state every one of his events was in: nothing on the event, and
    nothing being passed from settings either."""
    store.update_event(practice_event, game_version=None)
    prompt = a_prompt(store, practice_event, REFINEMENT, game_version=None)
    assert any("gameVersion" in warning for warning in prompt.warnings)
    assert "gt7-pitcrew/" not in prompt.text


def test_the_event_keeps_its_own_version_over_the_app_setting(store,
                                                              practice_event):
    """A measurement taken under a version no longer installed keeps the
    version it was taken under."""
    store.update_event(practice_event, game_version="1.55")
    prompt = a_prompt(store, practice_event, REFINEMENT)
    assert '"gameVersion": "1.55"' in prompt.text


# --------------------------------------------------- the contract is coherent

def test_a_first_sheet_is_asked_for_in_full(store, practice_event):
    """There is nothing to leave unchanged on a sheet that does not exist yet,
    and a key left out of one is a value the app has nothing to enter."""
    text = a_prompt(store, practice_event, BRIEF).text
    assert "Every setting on the sheet, every time" in text
    assert "Omit a setting you are not changing" not in text


@pytest.mark.parametrize("kind", [REFINEMENT, OUTCOME])
def test_a_revision_may_omit_what_it_did_not_change(store, practice_event, kind):
    """Pit Crew holds the sheet as run, so an omission is safe here in a way
    it is not on a first sheet."""
    text = a_prompt(store, practice_event, kind).text
    assert "Omit a setting you are not changing" in text
    assert "Every setting on the sheet, every time" not in text


def test_nothing_is_asked_for_that_nothing_reads():
    """`clicksFromMin` and `percentOfRange` were in the JSON shape and dropped
    by the parser - and already required in the readable sheet, where he reads
    them. A contract that asks for things nothing reads stops being believed.
    """
    shape = "\n".join(templates()["shared"]["returnShape"])
    assert "clicksFromMin" not in shape
    assert "percentOfRange" not in shape
    for field in ("values", "gears", "why", "purpose", "sheetName"):
        assert field in shape


def test_every_key_the_contract_names_is_one_the_app_stores():
    """An invented key is dropped on the way back in, so the example must not
    invent one."""
    shape = "\n".join(templates()["shared"]["returnShape"])
    for key in re.findall(r'"([a-z]{2,4}_[a-z]{1,2})"', shape):
        assert key in SETUP_KEY_NAMES, f"{key} is not a setup key"


# ------------------------------------------------------ conditions travel too

@pytest.mark.parametrize("kind", [BRIEF, REFINEMENT, OUTCOME])
def test_the_measured_clock_reaches_every_prompt(store, practice_event, kind):
    """"Afternoon" is a name, not an hour, and it means a different hour at
    every circuit. A race that sweeps into the evening cools the track and can
    leave a harder compound below its working range - a setup problem before
    it is a strategy one."""
    from pitcrew.analysis.resolve import circuit_key

    event = store.get_event(practice_event)
    store.save_track_clock(
        circuit_key(event["track"], event["layout"]),
        event["time_of_day"] or "",
        _reading(multiplier=6.0, start_hour=15.933, stopped_at_hour=18.833))
    text = a_prompt(store, practice_event, kind).text
    assert "measured off GT7's own clock" in text


def _reading(**fields):
    from pitcrew.analysis.gameclock import ClockReading
    base = dict(multiplier=None, start_hour=None, end_hour=None,
                stopped_at_hour=None, laps_sampled=40, note="")
    base.update(fields)
    return ClockReading(**base)


# ------------------------------------------------- a prompt that cannot answer

def test_a_post_mortem_with_no_race_says_so_loudly(store, practice_event):
    """This is the one prompt whose entire job is to explain what happened.
    Asking that of an empty session is asking for a plausible answer rather
    than a true one."""
    prompt = a_prompt(store, practice_event, OUTCOME)
    assert any("nothing to write a post-mortem from" in warning
               for warning in prompt.warnings)
    assert "No race was recorded for this event" in prompt.text
    assert "Do not reconstruct what probably happened" in prompt.text
