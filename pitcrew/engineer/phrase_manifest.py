"""Every line the engineer can say, enumerated from the code that says it.

Synthesising a line takes long enough to be heard as a pause before the
engineer speaks. Almost everything he says comes from a closed template over a
small set of numbers, so almost everything can be rendered once, ahead of time,
and played back as a wav. This module is the list of what to render.

**Nothing here copies a string out of `intents.py`.** Every line is obtained by
calling the real `answer()` with a snapshot that drives it down the branch in
question. A format string that changes there changes here, and the coverage
test fails rather than the pack silently going stale — which would show up as
the engineer sounding different on one sentence in fifty.

Two families cannot be rendered whole:

* **`{x.x} laps of fuel.`** would be a thousand clips. It is assembled from
  number words instead, which is the approach a real pre-recorded pack uses.
* **The plan summary** is combinatorial - a stop phrase, an optional compound
  and an optional laps-remaining, in one sentence. That is tens of thousands
  of sentences, so it is deliberately *not* covered and falls through to live
  synthesis. `uncovered_reason()` says so out loud rather than leaving it to be
  discovered as a mysterious pause.
"""
from __future__ import annotations

import re

from pitcrew.engineer.intents import (
    ACCEPT,
    BOX_FUEL,
    BOX_WHAT,
    BOX_WHEN,
    FUEL,
    KEEP,
    LAPS_LEFT,
    PLAN,
    POSITION,
    REPEAT,
    UNKNOWN,
    answer,
)
from pitcrew.store.tyres import ALL_COMPOUNDS

# Ranges. Chosen to cover what a GT7 league race can actually produce, not to
# be generous: every extra value is a clip to render and a file to ship.
MAX_POSITION = 30           # GT7 grids do not exceed 24; 30 is headroom
MAX_LAPS = 99               # a 100-lap race is not a format he runs
MAX_FUEL_LITRES = 100       # tank capacity, and the diamond marker's ceiling
MAX_FUEL_LAPS = 60          # a full tank at the leanest plausible burn

NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
TENS_WORDS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty",
              "seventy", "eighty", "ninety")

POINT = "point"

# `answer()` produces this shape for the fuel question. Parsed rather than
# re-formatted, so the fragments are derived from what the function actually
# returned; `test_every_fuel_line_decomposes` fails loudly if the shape moves.
_FUEL_LINE = re.compile(r"^(\d+)\.(\d) laps of fuel\.$")


def number_word(value: int) -> str:
    """English for a whole number. Only as far as the ranges above need."""
    if value < 20:
        return NUMBER_WORDS[value]
    tens, units = divmod(value, 10)
    word = TENS_WORDS[tens]
    return word if units == 0 else f"{word}-{NUMBER_WORDS[units]}"


# ------------------------------------------------------- walking answer()
#
# Each helper drives the real function down one branch. The snapshots are the
# minimum that reaches the branch, so a new required key in `answer()` breaks
# these rather than silently changing what gets rendered.

def _text(intent: str, snapshot: dict, **kwargs) -> str:
    return answer(intent, snapshot, **kwargs).text


def fixed_lines() -> tuple[str, ...]:
    """Every line with no number in it: refusals, confirmations, absences."""
    lines = [
        _text(UNKNOWN, {}),
        _text(REPEAT, {}),                                   # nothing to repeat
        _text(ACCEPT, {}),                                   # nothing to accept
        _text(ACCEPT, {}, pending_replan="x"),
        _text(KEEP, {}, pending_replan="x"),
        _text(POSITION, {}),                                 # no position
        _text(LAPS_LEFT, {}),                                # no race length
        _text(FUEL, {}),                                     # no fuel rate
        _text(BOX_WHEN, {}),                                 # no stop planned
        _text(BOX_WHEN, {"lapsToStop": 0}),                  # box this lap
        _text(BOX_WHAT, {}),                                 # no tyre change
        _text(BOX_FUEL, {}),                                 # no fuel target
    ]
    return tuple(dict.fromkeys(lines))


def position_lines() -> tuple[str, ...]:
    return tuple(_text(POSITION, {"position": n})
                 for n in range(1, MAX_POSITION + 1))


def laps_remaining_lines() -> tuple[str, ...]:
    return tuple(_text(LAPS_LEFT, {"lapsRemaining": n})
                 for n in range(0, MAX_LAPS + 1))


def box_when_lines() -> tuple[str, ...]:
    return tuple(_text(BOX_WHEN, {"lapsToStop": n})
                 for n in range(1, MAX_LAPS + 1))


def box_fuel_lines() -> tuple[str, ...]:
    return tuple(_text(BOX_FUEL, {"stopFuelL": float(n)})
                 for n in range(0, MAX_FUEL_LITRES + 1))


def compound_lines() -> tuple[str, ...]:
    return tuple(_text(BOX_WHAT, {"nextCompound": compound.name})
                 for compound in ALL_COMPOUNDS)


def fuel_fragments() -> tuple[str, ...]:
    """The pieces "4.5 laps of fuel." is assembled from.

    Rendering every tenth as its own clip would be a thousand files for one
    question. Number words plus a tail is sixty-odd, and it is how a real
    pre-recorded pack has always done it.
    """
    tail = _fuel_tail()
    words = [number_word(n) for n in range(0, MAX_FUEL_LAPS + 1)]
    return tuple(dict.fromkeys([*words, POINT, tail]))


def _fuel_tail() -> str:
    """The invariant part of the fuel line, taken from the line itself."""
    sample = _text(FUEL, {"lapsOfFuel": 4.5})
    match = _FUEL_LINE.match(sample)
    if match is None:
        raise ValueError(
            f"the fuel answer no longer looks like '<n>.<n> laps of fuel.': "
            f"{sample!r} - the manifest cannot decompose it")
    return sample[match.end(2):].lstrip()


def plan_single_part_lines() -> tuple[str, ...]:
    """Plan summaries that came out as one clause, so are one clip.

    Asked with no stop and no lap count, "what's the plan" answers "Running to
    the flag." - a whole sentence with no comma in it, and one the pack would
    otherwise miss because it appears in no other family.
    """
    lines = [_text(PLAN, {}), _text(PLAN, {"lapsToStop": 0})]
    lines += [_text(PLAN, {"lapsToStop": n})
              for n in range(1, MAX_LAPS + 1)]
    return tuple(line for line in dict.fromkeys(lines) if "," not in line)


def clips() -> tuple[str, ...]:
    """Everything the render tool should produce, de-duplicated."""
    everything = [
        *fixed_lines(),
        *position_lines(),
        *laps_remaining_lines(),
        *box_when_lines(),
        *box_fuel_lines(),
        *compound_lines(),
        *plan_single_part_lines(),
        *fuel_fragments(),
    ]
    return tuple(dict.fromkeys(everything))


# ------------------------------------------------------------- playing back

def segments_for(text: str) -> tuple[str, ...] | None:
    """How to play `text` from the pack, or None if it cannot be.

    Returns the clips to play in order. Almost every line is one clip; the
    fuel answer is four.
    """
    if not text:
        return None
    match = _FUEL_LINE.match(text)
    if match is not None:
        whole, tenth = int(match.group(1)), int(match.group(2))
        if whole > MAX_FUEL_LAPS:
            return None
        return (number_word(whole), POINT, number_word(tenth), _fuel_tail())
    return (text,)


def uncovered_reason(text: str) -> str | None:
    """Why a line is not in the pack, when it is a known gap rather than a bug.

    The plan summary is the only one: it is a sentence assembled from three
    optional parts, which is tens of thousands of sentences. It is asked on a
    straight rather than mid-corner, so live synthesis is an acceptable cost -
    but it is stated here so it never reads as an oversight.
    """
    if _looks_like_plan_summary(text):
        return ("the plan summary is combinatorial - stop phrase, optional "
                "compound, optional laps remaining - so it is synthesised live")
    return None


def _looks_like_plan_summary(text: str) -> bool:
    """A plan summary is the only line `answer()` builds with commas."""
    return "," in text and text not in fixed_lines()


def plan_summary_examples() -> tuple[str, ...]:
    """A representative sweep of plan summaries, for the coverage test."""
    snapshots = [
        {},
        {"lapsToStop": 0},
        {"lapsToStop": 1},
        {"lapsToStop": 4},
        {"lapsToStop": 4, "nextCompound": "Racing Medium"},
        {"lapsToStop": 4, "lapsRemaining": 1},
        {"lapsToStop": 4, "nextCompound": "Racing Soft", "lapsRemaining": 12},
        {"nextCompound": "Racing Hard", "lapsRemaining": 20},
        {"lapsRemaining": 0},
    ]
    return tuple(_text(PLAN, snapshot) for snapshot in snapshots)
