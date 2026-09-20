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

**Two sources, not one.** The driver's questions come back through
`intents.answer()`, and the calls the engineer makes unprompted come from
`race.calls.next_call()`. The proactive half was missing for the pack's whole
existence - measured, 0 of 7 real race calls covered - which is the wrong way
round: a reply he asked for can be asked for again, and a call that arrives
mid-corner cannot.

Lines that cannot be rendered whole are assembled from parts:

* **`{x.x} laps of fuel.`** would be a thousand clips. It is assembled from
  number words instead, which is the approach a real pre-recorded pack uses.
* **A race call is an instruction and a short reason** (CLAUDE.md §5.5) with at
  most one number in it, so the same trick works: the words either side of the
  number, plus the number, reusing the fuel line's own words.
* **The plan summary** is combinatorial - a stop phrase, an optional compound
  and an optional laps-remaining, in one sentence. That is tens of thousands
  of sentences, so it is deliberately *not* covered and falls through to live
  synthesis. `uncovered_reason()` says so out loud rather than leaving it to be
  discovered as a mysterious pause.
"""
from __future__ import annotations

import re
from functools import lru_cache

from pitcrew.engineer import gate
from pitcrew.engineer.intents import (
    GAP,
    ACCEPT,
    BOX_FUEL,
    BOX_WHAT,
    BOX_WHEN,
    FUEL,
    KEEP,
    LAPS_LEFT,
    NO_LAP_COUNT,
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
MAX_STOPS = 6               # "Stop 7, on the plan." is not a GT7 league race

NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
TENS_WORDS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty",
              "seventy", "eighty", "ninety")

POINT = "point"
# The tail of `colour.py`'s running fuel line. Kept beside the fuel answer's
# own fragments because it shares its number words; see `fuel_fragments`.
COLOUR_FUEL_TAIL = "laps of fuel in hand to the flag."
# **The same tail against the other reference.** `calls._fuel`'s FUEL_LONG
# line used to end "to the box" as a constant; it now takes its reference
# from `calls.fuel_reference`, because a stop can be cancelled mid-race and
# a fixed word then names a box the driver is no longer driving to. Two
# references, two clips - and neither may fall through to live synthesis,
# which is a pause at the moment a call arrives mid-corner.
STOP_FUEL_TAIL = "laps of fuel in hand to the stop."

# `answer()` produces this shape for the fuel question. Parsed rather than
# re-formatted, so the fragments are derived from what the function actually
# returned; `test_every_fuel_line_decomposes` fails loudly if the shape moves.
#
# **The tail is no longer a constant, and that is rule 13 paying the pack**
# (row 1.10). The answer said "4.5 laps of fuel." - an absolute, in the noun
# phrase the volunteered call uses for a MARGIN - and now says the same words
# the engineer says: "1.9 laps of fuel in hand to the stop." So it decomposes
# into `STOP_FUEL_TAIL` and `COLOUR_FUEL_TAIL`, which the pack already holds
# for the volunteered line, and the only new clip is the one the answer falls
# back to when there is no reference to be a margin to.
_FUEL_LINE = re.compile(r"^(\d+)\.(\d) (laps of fuel[^.]*\.)$")
# What the answer says when no stop and no flag can frame the figure: the
# absolute, said as one so it cannot be heard as a margin.
TANK_FUEL_TAIL = "laps of fuel in the tank."

# `calls.position_line`'s two-number form. Given its own shape for the same
# reason the fuel line has one: `_split_on_number` peels a single number and
# refuses a sentence with two, so a family with a known fixed shape is
# decomposed by that shape rather than generically.
_POSITION_LINE = re.compile(r"^P(\d+) of (\d+)\.$")
# **The stop picture's two place sentences** (`race/news.py`, 14 Sep 2026):
# "P6 on the road." and "Effectively P8 after the stops.". `_NUMBER` rightly
# refuses the 6 in "P6", so without a shape each would be a whole clip per
# place - sixty clips for two sentences whose place is already in the pack.
_ROAD_LINE = re.compile(r"^P(\d+) on the road\.$")
_EFFECTIVE_LINE = re.compile(r"^Effectively P(\d+) after the stops\.$")

# The one number inside a race call, wherever it sits. Deliberately strict
# about its edges, because each edge is a line that decomposed wrongly once:
#
#   (?<![\w.])   "P3." is a position, not the number three - it is a clip in
#                its own right and is peeled off whole, never split.
#   (?:\.(\d))?  "1.2 laps short" is a tenth, and shares the fuel answer's
#                number words rather than getting its own.
#   (%)?         "Modelled at 90%." - a clip named "%." is not a word any
#                synthesiser can say, so the percent sign is spelled out.
#   (?![\w,])    "Stop 1, on the plan." is rendered whole. Splitting it would
#                leave a fragment beginning with a comma, which reads as a
#                pause in the middle of the instruction.
_NUMBER = re.compile(r"(?<![\w.])(\d+)(?:\.(\d))?(%)?(?![\w,])")
PERCENT = "percent"


def number_word(value: int) -> str:
    """English for a whole number. Only as far as the ranges above need."""
    # **A full tank is a hundred litres**, and a fill to 100 indexed past
    # `TENS_WORDS` here - so the one figure most likely at a long-stint stop
    # could never be played from the pack (11 Sep 2026).
    if value == 100:
        return "one hundred"
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


@lru_cache(maxsize=1)
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
        NO_LAP_COUNT,                          # timed race, no count yet
        _text(FUEL, {}),                                     # no fuel rate
        _text(BOX_WHEN, {}),                                 # no plan at all
        _text(BOX_WHEN, {"hasPlan": True}),                  # no stop planned
        _text(BOX_WHEN, {"lapsToStop": 0}),                  # box this lap
        _text(BOX_WHAT, {}),                                 # no plan at all
        _text(BOX_WHAT, {"hasPlan": True}),                  # no tyre change
        _text(BOX_FUEL, {}),                                 # no fuel target
        _text(GAP, {}),                                      # never answerable
        # **The wall is up and has nothing yet**, and the side he asked about
        # is the one not read. Each is said at the moment he has just failed
        # to get an answer - the exchange that has already gone wrong, and
        # the worst place in the race for a synthesis pause.
        _text(GAP, {"wallRunning": True}),
        _text(GAP, {"wallRunning": True, "gapAheadS": 1.0},
              heard="who's behind me"),
        _text(GAP, {"wallRunning": True, "gapBehindS": 1.0},
              heard="who am i behind"),
        *rejection_lines(),
    ]
    return tuple(dict.fromkeys(lines))


def rejection_lines() -> tuple[str, ...]:
    """What he hears when the button produced no question.

    Taken from `gate.SPOKEN` rather than listed, for the same reason as
    everything else here. These matter more than most: they are what the
    engineer says at the moment the driver has just failed to get an answer,
    and falling through to live synthesis there adds a pause to the one
    exchange that has already gone wrong.
    """
    return tuple(dict.fromkeys(
        gate.spoken_reason(reason) for reason in gate.ALL_REASONS))


# The largest grid GT7 fields. Positions are enumerated against it because a
# position and a field size are two numbers in one sentence and
# `_split_on_number` peels one - the same reason "N or M laps to go." is
# enumerated rather than decomposed.
MAX_FIELD = 24


@lru_cache(maxsize=1)
def position_lines() -> tuple[str, ...]:
    """`P8.` - a position with no field size, said whole.

    **One family serves the answer AND the engineer's own call**, because
    `calls.position_line` renders a position everywhere: the PTT answer to
    "where am i", and the unprompted call when he gains or loses one. Written
    as "Up to P8 of 12." that call would have needed its own enumeration of
    these same lines with a word bolted on the front; the direction is
    carried in the reason instead, and the reason is six clips
    (`place_change_lines`).
    """
    return tuple(_text(POSITION, {"position": n})
                 for n in range(1, MAX_POSITION + 1))


@lru_cache(maxsize=1)
def position_fragments() -> tuple[str, ...]:
    """The two halves `P8 of 12.` is played from.

    **Enumerating it whole is 329 clips and it broke the pack's budget on the
    first attempt** - a position and a field size are two numbers in one
    sentence, and even taking the triangle rather than the rectangle (a
    position cannot exceed the field it is in, so `P14 of 9` is not a sentence
    anybody can be handed) it is a third of the pack for one family.

    So it is played from two, the way `{x.x} laps of fuel.` is played from
    four: the position without its stop, and the field with one. Fifty-three
    clips instead of three hundred and twenty-nine, and one join - fewer than
    the fuel line already carries.
    """
    return (*(f"P{n}" for n in range(1, MAX_POSITION + 1)),
            *(f"of {n}." for n in range(2, MAX_FIELD + 1)))


@lru_cache(maxsize=1)
def place_change_lines() -> tuple[str, ...]:
    """Why the position moved: made or lost, one place or up to three.

    Taken from the function that says it, never copied - a wording change
    there fails the coverage test rather than going stale in the pack.
    """
    from pitcrew.race.calls import POSITION_MAX_STEP, _places_moved

    steps = range(-POSITION_MAX_STEP, POSITION_MAX_STEP + 1)
    return tuple(dict.fromkeys(
        said for said in (_places_moved(n) for n in steps) if said))


@lru_cache(maxsize=1)
def lane_place_lines() -> tuple[str, ...]:
    """Why the position moved when the pit lane moved it, and a stop's result.

    "P11 of 13. After your stop." and "P6 of 13. Not passes - 2 cars ahead
    boxed." (the rival fix, 14 Sep 2026) were declared nowhere, so every place
    call the lane explained was a live synthesis mid-lap. Whole lines, from
    `places_through_the_lane` over every step it will word: thirteen clips,
    and the ones with two numbers ("You've made 3 places, and 2 of them
    boxed.") cannot be split, so they are enumerated - three steps is the most
    the call ever counts.

    Played whole rather than as "Not passes -" + a number + a tail: the same
    count of clips, and no join in a sentence said at racing speed.
    """
    from pitcrew.race.calls import (AFTER_YOUR_STOP, POSITION_MAX_STEP,
                                    places_through_the_lane)

    lines = [AFTER_YOUR_STOP]
    for places in range(-POSITION_MAX_STEP, POSITION_MAX_STEP + 1):
        for lane in range(1, POSITION_MAX_STEP + 1):
            said = places_through_the_lane(places, lane)
            if said:
                lines.append(said)
    return tuple(dict.fromkeys(lines))


@lru_cache(maxsize=1)
def laps_remaining_lines() -> tuple[str, ...]:
    return tuple(_text(LAPS_LEFT, {"lapsRemaining": n})
                 for n in range(0, MAX_LAPS + 1))


@lru_cache(maxsize=1)
def box_when_lines() -> tuple[str, ...]:
    return tuple(_text(BOX_WHEN, {"lapsToStop": n})
                 for n in range(1, MAX_LAPS + 1))


@lru_cache(maxsize=1)
def box_fuel_lines() -> tuple[str, ...]:
    return tuple(_text(BOX_FUEL, {"stopFuelL": float(n)})
                 for n in range(0, MAX_FUEL_LITRES + 1))


@lru_cache(maxsize=1)
def compound_lines() -> tuple[str, ...]:
    """Both the two-letter code and the full name.

    The strategy plan stores the code (`model.py` exports `"compound": code`)
    and that is what reaches `nextCompound`, so the code is what the engineer
    actually says at almost every stop. Only the full names were rendered, so
    "RS." missed the pack every single time and every box call ended in a live
    synthesis the driver hears as a pause on the compound.
    """
    lines = [_text(BOX_WHAT, {"nextCompound": compound.name})
             for compound in ALL_COMPOUNDS]
    lines += [_text(BOX_WHAT, {"nextCompound": compound.code})
              for compound in ALL_COMPOUNDS]
    # And the decision forms the radio now gives (the critic on row
    # 2.6): "RS on." for a set going on, "No tyres." for fuel only.
    lines += [_text(BOX_WHAT, {"nextCompound": compound.code,
                               "nextTyres": True})
              for compound in ALL_COMPOUNDS]
    lines.append(_text(BOX_WHAT, {"nextCompound": "RS", "nextTyres": False}))
    return tuple(dict.fromkeys(lines))


@lru_cache(maxsize=1)
def tyre_word_lines() -> tuple[str, ...]:
    """The tyre half of a box call - the DECISION - as a clip of its own.

    **Every box call carrying a decision missed the pack** (11 Sep 2026, 15
    of 36 box-call shapes). `_tyre_word` says "RS on." or "No tyres." since
    the plan's tyre decision landed, and nothing here declared either: the
    peel stopped at "Box this lap.", asked for "RS on. On the plan." whole,
    and an overdue one carrying two numbers was filed by `uncovered_reason`
    as a DECLARED gap - a decision nobody made, on the call he most needs
    without a pause.

    Taken from `calls._tyre_word` itself, every code by every decision, so a
    reworded tyre word is a re-rendered clip and never a copy that drifts.
    Codes only: the plan stores the code, and the full names would be a
    dozen clips for a spelling no plan on file uses.
    """
    from pitcrew.race.calls import _tyre_word

    lines = []
    for code in [c.code for c in ALL_COMPOUNDS] + [None]:
        for tyres in (True, False, None):
            word = _tyre_word(_state(next_compound=code, next_tyres=tyres))
            if word.strip():
                lines.append(word.strip())
    return tuple(dict.fromkeys(lines))


def _box_fuel_states() -> list:
    """Box calls as a race with a measured burn makes them.

    **The coverage sweep never had one** (critic 3 on the voice batch, 11
    Sep 2026): every box state here carried no fuel data, so no swept call
    carried a fuel figure - and no race with a burn makes any other. Every
    reason branch, every tyre decision, all three fuel sentences, and each
    basis the fill names.
    """
    states = []
    reasons = (dict(mandatory_stops_left=1),
               dict(mandatory_stops_left=None),
               dict(mandatory_stops_left=0, plan_binding_constraint="fuel"),
               dict(mandatory_stops_left=0, plan_binding_constraint="tyre"))
    fuels = (dict(fuel_l=10.0, fuel_per_lap_l=3.0),            # fuel to N
             dict(fuel_l=60.0, fuel_per_lap_l=3.0),            # fuel is fine
             dict(fuel_l=2.0, fuel_per_lap_l=9.0))             # fuel to full
    bases = (dict(next_stint_laps=8, further_stop_planned=False),
             dict(next_stint_laps=8, further_stop_planned=False,
                  crossed_in_box=True),
             dict(next_stint_laps=9, further_stop_planned=True),
             dict(next_stint_laps=None, further_stop_planned=None))
    for reason in reasons:
        for fuel in fuels:
            for basis in bases:
                for tyres in (True, False, None):
                    states.append(_state(
                        lap=12, laps_total=20, stint_ends_on_lap=13,
                        fuel_capacity_l=100.0, next_compound="RS",
                        next_tyres=tyres, **reason, **fuel, **basis))
    # **One lap of fill, both frames** (critic 3, pass 2): "1 lap after the
    # box." and "1 lap to the flag." are the singular the fill sentence was
    # given in this batch, and no state above left a single lap - so a late
    # splash filed its whole box call as a declared gap.
    # Thirteen and fourteen laps, because the two frames count differently:
    # across the line the lap in progress is covered, before it the laps
    # after the box lap are - so one lap of each needs a different race.
    for crossed in (False, True):
        for total in (13, 14):
            for basis in (dict(), dict(next_stint_laps=1,
                                       further_stop_planned=False)):
                states.append(_state(
                    lap=12, laps_total=total, stint_ends_on_lap=13,
                    fuel_l=1.0, fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                    next_compound="RS", next_tyres=True,
                    crossed_in_box=crossed, **basis))
    return states


@lru_cache(maxsize=1)
def reason_lines() -> tuple[str, ...]:
    """Every whole sentence a call's reason says with no number in it.

    **Peelable, which they were not** (critic 3). "The regulations need a
    stop." was a clip and `_decompose` could not peel it, because nothing
    put the reasons in `_reusable_lines` - so the peel stopped at the
    reason and the fuel sentence behind it landed as one two-number clause,
    filed as a declared gap. Taken from the calls' own reasons, sentence by
    sentence, so a reworded reason is a re-rendered clip.
    """
    from pitcrew.race.calls import next_call

    lines = []
    for state in [*_call_states(), *_box_fuel_states()]:
        call = next_call(state)
        if call is None or not call.reason:
            continue
        for sentence in re.split(r"(?<=\.)\s+", call.reason):
            if sentence and not re.search(r"\d", sentence):
                lines.append(sentence)
    return tuple(dict.fromkeys(lines))


@lru_cache(maxsize=1)
def fuel_sentence_fragments() -> tuple[str, ...]:
    """The words around the numbers of the fuel sentence.

    The fill sentence carries two numbers - the litres and the laps they
    are for - and `_split_on_number` refuses two, so it was filed as
    combinatorial. It is not: the words between its numbers are a handful,
    and they are taken here from `_fuel_instruction` itself over every basis
    the fill can name, so `_split_on_numbers` can play the sentence from
    these and the number words.
    """
    from pitcrew.race.calls import _fuel_instruction

    fragments = []
    for state in _box_fuel_states():
        for sentence in re.split(r"(?<=\.)\s+", _fuel_instruction(state)):
            pieces = _text_between_numbers(sentence)
            if pieces is not None and len(pieces) > 1:
                fragments.extend(piece for piece in pieces if piece)
    return tuple(dict.fromkeys(fragments))


def _text_between_numbers(sentence: str) -> list[str] | None:
    """The text on either side of every number in `sentence`, stripped."""
    matches = list(_NUMBER.finditer(sentence))
    if not matches:
        return None
    pieces, cursor = [], 0
    for match in matches:
        pieces.append(sentence[cursor:match.start()].strip())
        cursor = match.end()
    tail = sentence[cursor:].strip()
    pieces.append("" if tail in {".", "!", "?"} else tail)
    return pieces


def _split_on_numbers(sentence: str) -> tuple[str, ...] | None:
    """A sentence of several numbers, as its words and number words.

    Only where every piece of text between the numbers is a declared
    fragment - the fuel sentence's - so a combinatorial line (the plan
    summary) is still refused rather than split into words the pack does
    not hold.
    """
    matches = list(_NUMBER.finditer(sentence))
    if len(matches) < 2:
        return None
    allowed = set(fuel_sentence_fragments())
    pieces = _text_between_numbers(sentence)
    if pieces is None or any(p and p not in allowed for p in pieces):
        return None
    # **At least one word.** A sentence of numbers alone - "3 7." - passed
    # the check above on its empty pieces and played as two number words
    # (critic 3, pass 2). Latent, and not a sentence any call says.
    if not any(pieces):
        return None
    out: list[str] = []
    for text, match in zip(pieces, matches):
        if text:
            out.append(text)
        whole = int(match.group(1))
        if whole > MAX_FUEL_LITRES or match.group(3):
            return None
        out.append(number_word(whole))
        if match.group(2) is not None:
            out += [POINT, number_word(int(match.group(2)))]
    if pieces[-1]:
        out.append(pieces[-1])
    return tuple(out)


@lru_cache(maxsize=1)
def number_fragments() -> tuple[str, ...]:
    """The number words, shared by every line assembled from parts.

    "4.5 laps of fuel.", "12 to go.", "20 laps." and "1.2 laps short on fuel."
    between them would be thousands of whole clips. One set of number words
    serves all of them, which is how a pre-recorded pack has always worked.
    """
    return tuple(number_word(n) for n in range(0, MAX_FUEL_LITRES + 1))


def fuel_fragments() -> tuple[str, ...]:
    """The pieces "4.5 laps of fuel." is assembled from, beyond the numbers.

    **Plus the colour line's tail**, which the `race_call_lines` decomposition
    cannot reach: it enumerates `calls.py`, and the running commentary in
    `colour.py` is a separate family that is not enumerated anywhere. Every
    colour line in the Fuji race logged a pack miss and was synthesised live;
    the fuel one is the most repeated of them, and it shares this family's
    number words, so one tail clip covers it.
    """
    return (POINT, _fuel_tail(), COLOUR_FUEL_TAIL, STOP_FUEL_TAIL,
            TANK_FUEL_TAIL)


@lru_cache(maxsize=1)
def _fuel_tail() -> str:
    """The invariant part of the fuel line, taken from the line itself."""
    sample = _text(FUEL, {"fuelInHand": 4.5, "fuelReference": "to the stop"})
    match = _FUEL_LINE.match(sample)
    if match is None:
        raise ValueError(
            f"the fuel answer no longer looks like "
            f"'<n>.<n> laps of fuel in hand <reference>.': {sample!r} - the "
            f"manifest cannot decompose it")
    return match.group(3)


@lru_cache(maxsize=1)
def plan_single_part_lines() -> tuple[str, ...]:
    """Plan summaries that came out as one clause, so are one clip.

    Asked with a plan but no stop and no lap count, "what's the plan" answers
    "Running to the flag." - a whole sentence with no comma in it, and one the
    pack would otherwise miss because it appears in no other family.
    """
    lines = [_text(PLAN, {"hasPlan": True}),
             _text(PLAN, {"hasPlan": True, "lapsToStop": 0})]
    lines += [_text(PLAN, {"hasPlan": True, "lapsToStop": n})
              for n in range(1, MAX_LAPS + 1)]
    return tuple(line for line in dict.fromkeys(lines) if "," not in line)


# ------------------------------------------------- what he says unprompted
#
# The other half of the pack, and the half that was missing entirely. These
# are driven through `next_call` for the same reason the answers are driven
# through `answer()`: a call reworded in `race/calls.py` is a re-rendered clip
# and a failing coverage test, not a pause in the driver's ear that nobody
# notices until it happens mid-corner.

@lru_cache(maxsize=1)
def call_openers() -> tuple[str, ...]:
    """The instruction half of a proactive call, with no number in it.

    CLAUDE.md §5.5 is what makes this possible: every call is an instruction
    first and a short reason second, so the instruction is a closed set and
    the reason is where the number lives. These are the clips a numbered call
    is peeled back to before its reason is decomposed.
    """
    lines = []
    for state in _opener_states():
        call = _next_call(state)
        if call is not None and call.call:
            lines.append(call.call)
    return tuple(dict.fromkeys(lines))


@lru_cache(maxsize=1)
def race_call_lines() -> tuple[str, ...]:
    """Every clip the proactive calls need, whole or in pieces.

    Built by decomposing the real calls rather than by listing them, so the
    families below stay a list of *states* - the thing that is genuinely
    enumerable - and the wording stays wherever it is written.
    """
    lines: list[str] = list(call_openers())
    for state in _call_states():
        call = _next_call(state)
        if call is None:
            continue
        spoken = call.spoken()
        if uncovered_reason(spoken):
            # A declared gap. Rendering it whole is the tens of thousands of
            # files the decomposition exists to avoid.
            continue
        segments = segments_for(spoken)
        if segments is not None:
            lines.extend(segments)
    return tuple(dict.fromkeys(lines))


def _next_call(state):
    from pitcrew.race.calls import next_call

    return next_call(state)


def _state(**fields):
    from pitcrew.race.calls import RaceState

    return RaceState(**fields)


def _opener_states() -> list:
    """One state per kind of call, chosen so the instruction carries no number.

    A call whose instruction still has a number in it - the status call is
    "P4. 12 to go." and nothing else - simply contributes no opener, and is
    assembled from clips the questions already rendered.
    """
    states = [
        _state(lap=0),                                        # green flag
        _state(lap=6, finished=True),                         # chequered flag
        _state(lap=6, stint_ends_on_lap=7),                   # box now
        # **A stop he was told was off, back on** - the call that reverses
        # `STOPS_OFF`, so it cannot be the one that pauses.
        _state(lap=8, laps_total=20, stint_ends_on_lap=11, fuel_l=20.0,
               fuel_per_lap_l=6.0, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0,
               drop_stop_granted=True, stop_back_due=True),
        _state(lap=6, stint_ends_on_lap=8),                   # box next lap
        _state(lap=6, stint_ends_on_lap=9),                   # box in 3
        _state(lap=18, laps_total=20, fuel_l=20.0,            # fuel long
               fuel_per_lap_l=1.0),
        _state(lap=6, laps_since_stop=6, wear_per_lap=0.15),  # tyres
    ]
    # One per fuel map: the call names the map it is asking for, and which map
    # that is follows from the size of the shortfall.
    states += [_state(lap=6, laps_total=16, fuel_l=onboard,
                      fuel_per_lap_l=1.0)
               for onboard in _fuel_short_onboard()]
    return states


def _fuel_short_onboard() -> list[float]:
    """Laps of fuel aboard that between them ask for every fuel map.

    Swept rather than reasoned about: `fuel_map_for` picks the leanest map
    that covers the deficit off a measured consumption table, and which
    fraction lands on which map is that table's business, not this module's.
    Paired with a ten-lap target, so the fractions run the whole way from
    almost nothing aboard to almost enough.
    """
    return [n / 10.0 for n in range(1, 95)]


def _call_states() -> list:
    """States that between them produce every *shape* of call.

    Only the shapes: the numbers inside them come from `number_fragments()`,
    so one example of each shape is enough to render the words around them.
    The small enumerations that genuinely are rendered whole - the stop number
    in a box-soon call, the compound in a box-now - are swept properly.
    """
    # **The status states carry a silence behind them.** `_status` became a
    # heartbeat on 22 Aug - it fires on laps since anything was said rather
    # than on `lap % 5` - so a freshly built state never reaches it, and the
    # moment it stopped being reachable the manifest stopped declaring its
    # clips. "10 to go." lost its "to go." fragment and would have fallen
    # through to live synthesis, silently.
    def _quiet(**fields):
        state = _state(**fields)
        state.last_said_lap = 0
        return state

    states = [
        # **The stop that stops being a stop.** `_stops_off` fires once, when
        # a fuel-bound plan's tank starts covering the flag, and it cancels a
        # box call - so it is the one call in the race whose absence from the
        # pack would be heard as the app having died rather than as the plan
        # having changed. Two shapes: with the spare litres and without.
        #
        # **Retired, as a race retires it** (`stop_needed_held=False`). Since
        # the latch (85522eb) an unjudged stop is the plan's and stands, so a
        # bare state here never reached `_stops_off` - and "You're fuelled to
        # the flag." and its litres dropped out of the pack with nothing red.
        _state(lap=8, laps_total=20, fuel_l=82.3, fuel_per_lap_l=6.0,
               position=11, stint_ends_on_lap=10, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0,
               stop_needed_held=False),
        _state(lap=19, laps_total=20, fuel_l=7.0, fuel_per_lap_l=6.0,
               position=11, stint_ends_on_lap=19, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0,
               stop_needed_held=False),
        _state(lap=0),                                        # bare green
        _state(lap=0, laps_total=20),                         # green + laps
        _state(lap=6, finished=True),                         # bare chequer
        _state(lap=6, finished=True, position=4),             # chequer + place
        _quiet(lap=5, laps_total=20, position=4),             # status, both
        _quiet(lap=5, position=4),                            # status, place
        _quiet(lap=5, laps_total=20),                         # status, laps
        _quiet(lap=5, laps_total=20, position=4,              # timed: "about"
               race_minutes=45.0),
        _quiet(lap=5, laps_total=20, race_minutes=45.0),
        # **Box now, once per branch of `_why_the_stop_stands`** (the
        # critic on row 1.10). The box call gained its reason from the
        # branch that kept the stop, and two of the three - "The regulations
        # need a stop." and "Fuel won't reach the flag." - were spoken at
        # racing speed with no clip behind them. `test_phrase_manifest`
        # checks that a declared opener still exists in its module and never
        # the reverse, so nothing caught it.
        _state(lap=6, laps_total=20, stint_ends_on_lap=7,
               mandatory_stops_left=1),
        _state(lap=6, laps_total=40, stint_ends_on_lap=7, fuel_l=40.0,
               fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0),
        # **The ungranted drop, which is the DEFAULT branch**: with no
        # playbook granting `fuel_long: drop_stop`, this is what a
        # fuel-covered race says at the box lap. `stops_off_said` is
        # required or `STOPS_OFF` outranks the box call and the state
        # renders nothing at all.
        # Retired by the fuel too, or the "not granted" clause is never
        # reached: it answers "You're fuelled to the flag.", which only a
        # retired stop says.
        _state(lap=10, laps_total=20, stint_ends_on_lap=11, fuel_l=60.0,
               fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0,
               drop_stop_granted=False, stops_off_said=True,
               stop_needed_held=False),
        _state(lap=8, laps_total=20, stint_ends_on_lap=10, fuel_l=60.0,
               fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0,
               drop_stop_granted=False, stops_off_said=True,
               stop_needed_held=False),
        # **And every stop number, because the ordinal renders whole.** The
        # plain box-soon is already swept over `range(MAX_STOPS)` for exactly
        # that reason; this branch was pinned at stop 1, so "Stop 2, on the
        # plan. Fuel would reach the flag - dropping the stop was not
        # granted." would have fallen through to live synthesis.
        *[_state(lap=8, laps_total=20, stint_ends_on_lap=10, fuel_l=60.0,
                 fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                 plan_binding_constraint="fuel", mandatory_stops_left=0,
                 drop_stop_granted=False, stops_off_said=True,
                 stop_needed_held=False, stint_index=index)
          for index in range(1, MAX_STOPS)],
        # Box soon carries the same reason two laps earlier.
        _state(lap=5, laps_total=20, stint_ends_on_lap=7,
               mandatory_stops_left=1),
        _state(lap=5, laps_total=40, stint_ends_on_lap=7, fuel_l=40.0,
               fuel_per_lap_l=3.0, plan_binding_constraint="fuel",
               mandatory_stops_left=0),
        # **Overdue, in every shape the reason takes.** None was declared, so
        # "N laps overdue." and both of its tails - the fuel that is fine
        # for the next stint, and FUEL_SHORT's "short of the flag on current
        # burn" - were synthesised live on a repeated box call (11 Sep 2026).
        _state(lap=7, laps_total=20, stint_ends_on_lap=7),
        _state(lap=9, laps_total=20, stint_ends_on_lap=6),
        _state(lap=8, laps_total=20, stint_ends_on_lap=6, fuel_l=60.0,
               fuel_per_lap_l=3.4, fuel_capacity_l=100.0),
        _state(lap=9, laps_total=20, stint_ends_on_lap=6, fuel_l=8.0,
               fuel_per_lap_l=1.0, fuel_capacity_l=100.0, next_compound="RS",
               next_tyres=True),
        # Box now: on the plan, to a fuel figure, and clamped to the tank.
        _state(lap=6, stint_ends_on_lap=7),
        _state(lap=6, laps_total=20, stint_ends_on_lap=7,
               fuel_per_lap_l=3.4, fuel_capacity_l=100.0),
        _state(lap=6, laps_total=99, stint_ends_on_lap=7,
               fuel_per_lap_l=9.0, fuel_capacity_l=100.0),
        # Fuel calls, and the modelled-wear warning - including the one made
        # through a stop that never said whether the tyres came off.
        _state(lap=18, laps_total=20, fuel_l=20.0, fuel_per_lap_l=1.0),
        _state(lap=6, laps_since_stop=6, wear_per_lap=0.15),
        _state(lap=6, laps_since_stop=6, wear_per_lap=0.15,
               tyre_change_unconfirmed=True),
    ]
    # **The beep changing column, which the tablet's middle button does.**
    # `_fuel_mode` only fires on a state carrying `fuel_mode_change`, and no
    # state here ever set one, so every sentence in that family - including
    # "Fuel-save beeps. Your call - held until you change it.", the answer to
    # a button he presses mid-race - was live-synthesised.
    states += _fuel_mode_states()
    states += [_state(lap=6, laps_total=16, fuel_l=onboard,
                      fuel_per_lap_l=1.0)
               for onboard in _fuel_short_onboard()]
    # The box call with its fuel figure, so its segments are rendered.
    states += _box_fuel_states()
    # Every compound the plan can call for, on a box-now.
    states += [_state(lap=6, stint_ends_on_lap=7, next_compound=code)
               for code in _compound_words()]
    # Every stop number a box-soon can announce, at both distances.
    for stint in range(0, MAX_STOPS):
        states += [_state(lap=6, stint_ends_on_lap=8, stint_index=stint),
                   _state(lap=6, stint_ends_on_lap=9, stint_index=stint)]
    return states


def _fuel_mode_states() -> list:
    """One state per shape the beep-column call takes, both columns.

    The `why` is not inferred from the state - it is carried on
    `fuel_mode_change`, exactly as the coordinator sets it - so each branch of
    `_fuel_mode` is reached directly. The two frames matter: the reason names
    the flag or the stop (rule 13), and they are different clips.
    """
    from pitcrew.race.calls import (
        FUEL_MODE_DRIVER,
        FUEL_MODE_FULL_REACHES,
        FUEL_MODE_FULL_SHORT,
        FUEL_MODE_PLANNED,
        TO_THE_FLAG,
        TO_THE_STOP,
    )

    def _change(change, **fields):
        state = _state(**fields)
        state.fuel_mode_change = change
        state.last_said_lap = 0
        return state

    # To the flag: no stop ahead. To the stop: one is, and the fuel is ample
    # so the shortfall calls do not outrank the one being rendered.
    flag = dict(lap=18, laps_total=20, fuel_l=40.0, fuel_per_lap_l=3.0,
                fuel_capacity_l=100.0)
    stop = dict(lap=6, laps_total=40, stint_ends_on_lap=14, fuel_l=60.0,
                fuel_per_lap_l=3.0, fuel_capacity_l=100.0)
    # The reference the litres are a gap TO, carried on the change as the
    # coordinator carries it - the two are different clips (rule 13).
    states = [
        # His own press, either way - the tablet button's answer. Neither
        # names a reference, so neither carries one.
        _change((6, True, FUEL_MODE_DRIVER, None, None), lap=6),
        _change((6, False, FUEL_MODE_DRIVER, None, None), lap=6),
        # The plan moving it, either way.
        _change((6, False, FUEL_MODE_PLANNED, None, None), lap=6),
        _change((6, True, FUEL_MODE_PLANNED, None, None), lap=6),
    ]
    for fields, frame in ((flag, TO_THE_FLAG), (stop, TO_THE_STOP)):
        states += [
            # Full revs reach, with the spare litres and without.
            _change((fields["lap"], False, FUEL_MODE_FULL_REACHES, 12.4,
                     frame), **fields),
            _change((fields["lap"], False, FUEL_MODE_FULL_REACHES, None,
                     frame), **fields),
            # And full revs falling short, which puts the beep back to saving.
            _change((fields["lap"], True, FUEL_MODE_FULL_SHORT, 6.2, frame),
                    **fields),
        ]
    return states


def lever_lines() -> tuple[str, ...]:
    """What the tablet's three buttons say back, from the code that says it.

    **Built by calling the real builders in `race.calls`**, like every other
    family here - the wording stays where it is written and an edit to it
    fails the coverage test rather than quietly falling through to synthesis.

    The pit button's confirmation is spoken *even with George off* (his call,
    17 Sep 2026), so it is the one sentence in the app that a silenced
    engineer still says. A pause in front of it is the worst place in the race
    for one: he is deciding whether he is in the lane this lap.
    """
    from pitcrew.race.calls import (
        BOX_CANCELLED,
        BOX_TOO_LATE,
        column_held_said,
        declared_box_said,
    )

    lines = [BOX_CANCELLED, BOX_TOO_LATE]
    for saving in (True, False):
        for why in _no_target_whys():
            lines.extend(segments_for(column_held_said(saving, why)) or ())
    # The fill is the box call's own sentence, already rendered by
    # `box_fuel_lines()`; what is new is the opener in front of it, so the
    # decomposition is asked for one whole example of each.
    for instruction in _box_instructions():
        lines.extend(segments_for(declared_box_said(instruction)) or ())
    return tuple(dict.fromkeys(lines))


def replan_lines() -> tuple[str, ...]:
    """The re-planner's INSTRUCTION half - "Recommend 2 stops from here."

    **The highest-consequence sentence the app says, and it was live.** The
    strategy engine changing its mind mid-race is job 4's own output, and
    none of `Replan.call()` was declared: the driver got a pause and a
    different voice in front of the stop count.

    Only the instruction is rendered. `spoken_reason()` is the first clause of
    an accumulated reason and is genuinely free-form, so it falls through -
    but the words he must act on arrive from the pack, and the explanation
    behind them can take the pause. §5.5: instruction first, reason second.

    NOTED verdicts return the reason itself as the call, which is the same
    free-form text, so they are not enumerated here either.
    """
    from pitcrew.race.replan import RECOMMENDED, REPLANNING_OFF, Replan

    from pitcrew.race.brief import (
        GAUGE_NOT_IN_FRAME,
        GAUGE_UNREADABLE,
        blind_note,
    )

    # The rig's own two sentences. Held until the flag, so the pause they
    # would take is cheap - but they are two clips, and unreachable is not a
    # state any speech in this app should be left in.
    from pitcrew.rig.supervisor import HAPTICS_BACK, HAPTICS_MUTED

    # **The "I cannot see it" message**, whose whole purpose is to stop
    # silence being read as "tyres are fine". Its sibling `lost_the_gauge()`
    # has been declared since the openers existed; this one never was.
    lines = [REPLANNING_OFF, HAPTICS_BACK, HAPTICS_MUTED,
             blind_note(GAUGE_NOT_IN_FRAME), blind_note(GAUGE_UNREADABLE)]
    for stops in (None, 0, *range(1, MAX_STOPS + 1)):
        said = Replan(verdict=RECOMMENDED, reason="", stops=stops).call()
        if said:
            lines.extend(segments_for(said) or ())
    return tuple(dict.fromkeys(lines))


def quali_lines() -> tuple[str, ...]:
    """The qualifying coach, which had not one line in the pack.

    **`phrase_manifest` imported nothing from `race/qualifying.py`**, so every
    sentence the coach says was live-synthesised - and the split calls fire at
    `EARLY_FRACTION` and `MID_FRACTION` of a FLYING LAP. A pause before the
    engineer speaks mid-flyer is a pause on the one lap of the weekend that
    cannot be taken again.

    The delta calls are obtained by calling `_delta_call` itself, over the
    tenths it can say, both directions, both halves of the lap and both sides
    of the "about" - which is earned by the integration noise, so it is not a
    wording choice but a state. Above a second the line splits on its number
    and costs prefixes only.

    The lap time in a line call is not here: `spoken_lap_time` is a minute, a
    second and a tenth, which is tens of thousands of clips, and it is said at
    the line rather than mid-corner.
    """
    from pitcrew.race.qualifying import LEVEL_BAND_S, QualifyingCoach

    # `_delta_call` reads one field and no packet, so the real method is
    # called on a bare instance rather than a rig full of stubs.
    coach = object.__new__(QualifyingCoach)
    lines: list[str] = []
    for noise in (None, 0.0):       # with the "about", and without it
        coach._noise_s = noise
        # A tenth either side of level, up to the abandon threshold; past
        # that the coach stops speaking and goes back to the out lap.
        steps = [LEVEL_BAND_S / 2] + [n / 10.0 for n in range(1, 31)]
        for step in steps:
            for delta in (step, -step):
                for early in (True, False):
                    said = coach._delta_call(delta, early=early)
                    lines.extend(segments_for(said) or ())
    # The temperature calls that carry ONE number. The pair that carries two
    # (fronts and rears in one clause) is a declared gap, not an omission -
    # `uncovered_reason` says so - and it is an out-lap call, not a flyer one.
    for axle in ("Fronts", "Rears"):
        lines += [f"{axle} coming -", f"{axle} still",
                  "cold - your call."]
    return tuple(dict.fromkeys(lines))


def _no_target_whys() -> list[str]:
    """Every reason a held column can have no lap target, from `for_lap`."""
    from pitcrew.strategy.targets import CompoundTarget, PlanTargets

    whys: list[str] = []
    for code in [c.code for c in ALL_COMPOUNDS]:
        # No entry at all, and an entry with no time in one column.
        tables = (
            PlanTargets({}, fuel_weight=0.0, burn_full_l=None,
                        burn_save_l=None),
            PlanTargets({code: CompoundTarget(
                lap_time_ms=None, save_lap_time_ms=None, wear_per_lap=None,
                reference_load_l=None, lap_source=None, save_source=None)},
                fuel_weight=0.0, burn_full_l=None, burn_save_l=None))
        for table in tables:
            for saving in (True, False):
                target = table.for_lap(compound=code, saving=saving,
                                       lap_on_set=1, fuel_at_start_l=None)
                if target.why_no_lap:
                    whys.append(target.why_no_lap)
        # The compound not yet read off the HUD, and the coordinator's own
        # fallback for a target that names no reason.
    table = PlanTargets({}, fuel_weight=0.0, burn_full_l=None,
                        burn_save_l=None)
    unknown = table.for_lap(compound=None, saving=True, lap_on_set=1,
                            fuel_at_start_l=None)
    if unknown.why_no_lap:
        whys.append(unknown.why_no_lap)
    whys.append("no target for that column")
    return list(dict.fromkeys(whys))


def _box_instructions() -> list[str]:
    """One box-now instruction of each shape, for the declared-stop opener."""
    from pitcrew.race.calls import _fuel_instruction

    shapes = [
        _state(lap=6, stint_ends_on_lap=7),                   # on the plan
        _state(lap=6, laps_total=20, stint_ends_on_lap=7,     # to a figure
               fuel_per_lap_l=3.4, fuel_capacity_l=100.0),
        _state(lap=6, laps_total=99, stint_ends_on_lap=7,     # to the brim
               fuel_per_lap_l=9.0, fuel_capacity_l=100.0),
    ]
    said = [_fuel_instruction(state) for state in shapes]
    return [line for line in dict.fromkeys(said) if line]


def _compound_words() -> list[str]:
    return [c.code for c in ALL_COMPOUNDS] + [c.name for c in ALL_COMPOUNDS]


def spoken_openers() -> tuple[str, ...]:
    """Whole lines the engineer says that no synthetic state produces.

    `race_call_lines()` decomposes whatever `next_call` returns for a list of
    enumerable states, which is the right way round - the wording stays where
    it is written. But three families never come out of it: the temperature
    calls, whose states are combinations of four per-wheel readings against a
    measured window; the run-in, which lives in `colour.py` and not in
    `next_call` at all; and the push-to-talk acknowledgement.

    **Measured before this list existed: fourteen of the sixteen lines the
    engineer can say were missing from the pack**, so nearly every race call
    was being live-synthesised. They are numberless, so each is one clip and
    the decomposition is not needed.

    Sourced by import where the module exposes them and quoted here where it
    does not; a line that drifts from its module is a clip that stops matching
    and falls back to synthesis, which is the failure this list exists to fix -
    so `test_phrase_manifest` checks these against the modules.
    """
    return (
        # race/calls.py - the temperature family
        "Tyres cold.",
        "Rears heating.",
        "Fronts heating.",
        "Tyres are up to temperature.",
        "Ease the traction out of the slow corners.",
        # race/calls.py - the run-in, sayable only with an accurate clock
        "Last lap.",
        "Two to go.",
        # ... and the run-in's hedged pair (Suzuka, 13 Sep 2026).
        "One or two to go.",
        "Too close to call on the clock.",
        # race/qualifying.py - the coach's whole lines. The splits fire on a
        # flying lap, so a pause in front of one costs the lap.
        "No reference lap from practice - temperatures and lap times only.",
        "Tyres in window. Push when you cross the line.",
        "Tyres still coming up.",
        "Splits off until your next best - that lap's trace had a gap.",
        "Tyres were ready - grip should hold for another run.",
        "Purple.",
        # race/calls.py - the beep's two columns, named. Openers rather than
        # whole lines because each is followed by a different reason: the
        # column is one clip and the reason another, not one clip per pair.
        "Fuel-save beeps.",
        "Full beeps.",
        # race/calls.py - the tablet's pit button, spoken even with George
        # off, so the fill behind it peels into the box call's own clips.
        "Boxing this lap.",
        # race/calls.py - the answer to a save that is no longer needed.
        "Fuel reaches the flag now.",
        "On current burn.",
        # "Save 1.5 litres a lap to make the flag.", split on its number.
        "Save",
        "litres a lap to make the flag.",
        # race/colour.py - the quiet-lap tier
        "That's the best lap of the race.",
        "That's the tidiest run of the race.",
        "Halfway.",
        # Row 1.10: the countdown said "Stop next lap." - the box call's own
        # words, from the commentary tier. It describes now.
        "One lap to the stop.",
        "Tyre gauge when you get a straight.",
        # engineer/intents.py - acknowledge, never analyse
        "Copy, noted with the temperatures.",
        # engineer/intents.py - the two intents the vocabulary was missing.
        # "How are my tyres" used to match BOX_WHAT and be answered with the
        # compound planned for the stop; "what's my best lap" matched
        # LAPS_LEFT and was answered "twelve to go".
        "No tyre gauge - read it to me.",
        "No pace reference yet.",
        "Pace is inside the noise - nothing to call.",
        # controller.start_race - said late where the wall was going to watch
        # and then failed to start, after the brief dropped its own line.
        "The pit wall did not start.",
        # race/brief.py - the arming brief. Spoken on the grid rather than at
        # racing speed, so latency matters less here than anywhere - but these
        # are the lines that define what every later silence means, and a
        # stutter before "I can't see them, not that they're fine" would
        # undercut the one sentence that has to land.
        "I have the tyre gauge this race.",
        "No tyre gauge this race - read it to me when you can.",
        "If I'm quiet about tyres it means I can't see them, "
        "not that they're fine.",
        "No measured temperature window on this car, so I'll call the trend "
        "and not a number.",
        "I can't see kerbs or offs on this stream.",
        "I can't see other cars - position only.",
        # The fuel-only stops (the critic on row 2.6, pass 2).
        "No tyres at the stop - fuel only.",
        "No tyres at any stop - fuel only.",
        "Not every stop takes tyres - I'll say which at the box.",
        # The register suffixes - "You can push ... Suggestion." and a
        # LOW-confidence call's "Unconfirmed."
        "Suggestion.",
        "Unconfirmed.",
        # A timed race's green - "About 20 laps on the clock." - is split on
        # its one number by `_split_on_number`, so only the two fragments
        # either side of it are rendered, not one clip per lap count.
        "About",
        "laps on the clock.",
        "No plan loaded - I'll call fuel and nothing else.",
        "I won't give you a lap count until I can stand behind one.",
        "I've lost the tyre gauge. Read it to me when you get a straight.",
    )


# ------------------------------------- the families said away from next_call
#
# **Six families the pack never swept** (Bathurst, 14 Sep 2026: 32 of 46 race
# lines missed the pack and were synthesised live). None of them comes out of
# `next_call`, so none was reached by `race_call_lines`: the straight's data
# line and the colour countdown live in `colour.py`, the word on the way back
# from an off in the coordinator, the incident call behind a crossing's
# ranking, and the fill and the release in the pit box. Each is driven through
# the function that says it - never retyped - and kept as the numberless
# sentences (which `_decompose` peels) plus the words either side of its one
# number (which the number words already in the pack complete).
#
# **Not the rival's stop.** "TommyTbone boxed, 7 litres." carries a name
# no clip can hold, and the engine plays a line from the pack only whole - a
# pack clip spliced to a live-synthesised name would be two voices in one
# sentence. It stays live, and says so in the miss log.

WEAR_CORNERS = ("fl", "fr", "rl", "rr")


def _pieces(*lines: str) -> tuple[str, ...]:
    """Each line's numberless sentences, and the words around each number."""
    out: list[str] = []
    for line in lines:
        for sentence in re.split(r"(?<=\.)\s+", line.strip()):
            if not sentence:
                continue
            if not _NUMBER.search(sentence):
                out.append(sentence)
                continue
            split = _split_on_number(sentence)
            if split is None:
                continue
            numbers = set(number_fragments()) | {POINT}
            out.extend(piece for piece in split if piece not in numbers)
    return tuple(dict.fromkeys(out))


@lru_cache(maxsize=1)
def colour_data_lines() -> tuple[str, ...]:
    """The straight's data line and the crossing's stop countdown.

    "RR 19 percent.", "Worst tyre 19 percent.", "6 laps to the stop.", and the
    gap to his best in both of `say.spoken_gap`'s forms - off
    `ColourCalls._data` and `_countdown` themselves.
    """
    from pitcrew.race.colour import CHATTY, ColourCalls

    lines = []
    for corner in (*WEAR_CORNERS, None):
        call = ColourCalls(level=CHATTY)._data(
            None, "", 0.19, corner, None, None, 1)
        lines.append(call.spoken())
    for to_box in (1, 6):
        call = ColourCalls(level=CHATTY)._data(
            None, "", None, None, None, 1 + to_box, 1)
        lines.append(call.spoken())
        countdown = ColourCalls()._countdown(1, 1 + to_box)
        if countdown is not None:
            lines.append(countdown.spoken())
    for off_ms in (*range(100, 1000, 100), 1300):
        colour = ColourCalls(level=CHATTY)
        colour._best_ms = 90_000
        call = colour._data(None, "", None, None, 90_000 + off_ms, None, 1)
        lines.append(call.spoken())
    return _pieces(*lines)


@lru_cache(maxsize=1)
def off_road_lines() -> tuple[str, ...]:
    """The incident call, and the word on the way back from an off.

    "Lap 1 is out. You stopped on it.", "Lap 16 is out. That cost you 32
    seconds against your pace." and "You're back on it. About 9 seconds off
    the road." - all three said at Bathurst, none in the pack.
    """
    from types import SimpleNamespace

    from pitcrew.race.calls import RaceState, _incident
    from pitcrew.race.coordinator import RaceCoordinator

    lines = []
    for cost_ms in (None, 32_000):
        state = RaceState(lap=2)
        state.incident_lap = 1
        state.incident_cost_ms = cost_ms
        call = _incident(state)
        if call is not None:
            lines.append(call.spoken())
    stub = SimpleNamespace(
        composure=SimpleNamespace(owed=lambda: 9.0),
        state=SimpleNamespace(lap=1))
    call = RaceCoordinator._compose(stub, None)
    if call is not None:
        lines.append(call.spoken())
    return _pieces(*lines)


@lru_cache(maxsize=1)
def refuel_lines() -> tuple[str, ...]:
    """What is said in the box: the fill, the release, and leaving short.

    Driven frame by frame through `RefuelWatch.note`, over every basis
    `calls.fuel_target_basis` names for the box states the manifest already
    sweeps, so a reworded basis is a re-rendered clip - and over each burn
    the sentence can name: this race's (every `FUEL_BASIS_*`), practice's
    (None), and none where the caller did not say.

    **And over the lap counts the evidence sentence can carry.** "Measured
    over N laps." is its own numberless-but-for-one sentence precisely so the
    pack can hold it; `_pieces` renders the words around the number, so one
    sweep of a singular and a plural covers every count a race can reach.
    """
    from pitcrew.race.calls import fuel_target_basis
    from pitcrew.race.expectations import (FUEL_BASIS_HIGHER_RACE,
                                           FUEL_BASIS_HIGHER_STINT,
                                           FUEL_BASIS_RACE,
                                           FUEL_BASIS_STINT)
    from pitcrew.race.refuel import (BURN_UNSTATED, UNSIZED_RISE_L,
                                     RefuelWatch)

    bases = [None]
    for state in _box_fuel_states():
        basis = fuel_target_basis(state)
        if basis:
            bases.append(basis)
    burns = (None, FUEL_BASIS_STINT, FUEL_BASIS_RACE,
             FUEL_BASIS_HIGHER_RACE, FUEL_BASIS_HIGHER_STINT, BURN_UNSTATED)
    lines = []
    for basis in dict.fromkeys(bases):
        for burn_basis in burns:
            for burn_laps in (None, 1, 19):
                for start_l, to_flag_l in ((5.0, None), (5.0, 40.0),
                                           (19.9, None), (19.9, 40.0)):
                    watch = RefuelWatch()
                    watch.note(start_l, speed_kph=100.0, target_l=None)
                    fuel = start_l
                    while fuel < 30.0:
                        fuel += 0.5
                        call = watch.note(
                            fuel, speed_kph=0.0, target_l=20.0,
                            fuel_per_lap_l=2.5, to_flag_l=to_flag_l,
                            basis=basis, burn_basis=burn_basis,
                            burn_laps=burn_laps)
                        if call is not None:
                            lines.append(call.spoken())
    watch = RefuelWatch()
    watch.note(5.0, speed_kph=100.0, target_l=None)
    for fuel in (5.5, 6.0, 6.5, 7.0):
        watch.note(fuel, speed_kph=0.0, target_l=20.0)
    short = watch.left_early(10.0)
    if short is not None:
        lines.append(short.spoken())
    # **And the stop nothing could size.** It carries no number at all, so it
    # is one clip and a cheap one - and it is exactly the line that must not
    # arrive late, because it is said to a driver holding the refuelling
    # trigger with no figure of his own to work to.
    unsized = RefuelWatch()
    unsized.note(5.0, speed_kph=100.0, target_l=None)
    fuel = 5.0
    while fuel < 5.0 + UNSIZED_RISE_L + 2.0:
        fuel += 0.5
        call = unsized.note(fuel, speed_kph=0.0, target_l=None)
        if call is not None:
            lines.append(call.spoken())
    return _pieces(*lines)


@lru_cache(maxsize=1)
def race_news_lines() -> tuple[str, ...]:
    """The race around him (D7, 14 Sep 2026): the parts that hold no name.

    Driven through `race/news.py`'s own wording functions, never retyped:
    the gap line and the pace line about an UNNAMED car ("The car ahead,
    2.1.", "Catching the car ahead, 0.9 seconds a lap."), the count it rests
    on, and the stop picture ("P6 on the road. Effectively P8 after the
    stops. If they stop once."). Kept as the words either side of each number
    (`_pieces`), and the two place sentences as the fixed halves `_shaped`
    plays them from - "P6" is already a clip.

    **Not a named line.** "PUNISHED ahead, 2.1." and "Magical daddy P4, 3
    ahead." carry a name no clip can hold, and a pack clip spliced to a
    live-synthesised name is two voices in one sentence - they stay live, as
    the rival's stop does.
    """
    from pitcrew.race.news import (catch_reason, gap_sentence, pace_reason,
                                   pace_sentence, picture_words)
    from pitcrew.race.rival_tyres import tyres_words

    lines: list[str] = []
    for side in ("ahead", "behind"):
        for gap_s in (2.1, 12.0, 0.04):
            lines.append(gap_sentence(side, None, gap_s))
        for rate in (0.9, -0.9):
            lines.append(pace_sentence(side, None, rate))
    lines.append(pace_reason(5))
    # When a closing car gets there (17 Sep 2026): the lap split on its number,
    # and the flag answer whole, each side.
    for side in ("ahead", "behind"):
        lines.append(catch_reason(side, 25, True))
        lines.append(catch_reason(side, 25, False))
        # **A neighbour's set going off** (19 Sep 2026) - its own call,
        # unnamed so the pack can hold it. Every shape: seen and assumed, so
        # "Keep fighting." is declared as well as the fact.
        for seen in (True, False):
            call, reason, _firm = tyres_words(side, 28, seen)
            lines.append(f"{call} {reason}".strip())
    for line, required in ((("still", 2), 1), (("effective", 8), 1),
                           (("effective", 8), 2), (("effective", 8), 3)):
        call, reason = picture_words(6, line, required)
        lines.append(f"{call} {reason}")
        # The hedge when a rival's own fuel moved the count - declared with
        # the one it replaces, or it would be the only sentence in the stop
        # picture played live.
        call, reason = picture_words(6, line, required, on_fuel=True)
        lines.append(f"{call} {reason}")
    out: list[str] = []
    for line in lines:
        for sentence in re.split(r"(?<=\.)\s+", line.strip()):
            shaped = _shaped(sentence)
            if shaped:
                out.extend(piece for piece in shaped
                           if not re.fullmatch(r"P\d+", piece))
            else:
                out.extend(_pieces(sentence))
    return tuple(dict.fromkeys(out))


def hud_alert_lines() -> tuple[str, ...]:
    """Contact and water, appearing and going (`race/hud_alerts.py`).

    **Whole clips, and every one is said mid-corner.** An onset lands the
    moment the icon lights or the bar fills, which is exactly when a pause for
    live synthesis would be heard. Eight fixed sentences, no numbers, imported
    from the module that says them.
    """
    from pitcrew.race.hud_alerts import fixed_lines as alert_lines

    return tuple(alert_lines())


@lru_cache(maxsize=1)
def target_lines() -> tuple[str, ...]:
    """The lap against the plan's target, inside the heartbeat (16 Sep 2026).

    Driven through `race/targets.py`'s own sentence functions over every gap
    they can say: each tenth from the on-target band to a second in both
    directions, the seconds form past it, and the burn either way - so a
    reworded clause is a re-rendered clip.

    **And over both burn references**, which is why the reference is its own
    numberless sentence: "Against the plan." and "Against this race's burn."
    are one clip each and cover every burn verdict of every race.
    """
    from pitcrew.race.targets import (ON_TARGET_L, ON_TARGET_S, burn_sentence,
                                      pace_sentence)
    from pitcrew.strategy.targets import BURN_BASIS_PLAN, BURN_BASIS_RACE

    lines = []
    tenths = [tenth / 10.0 for tenth in range(int(ON_TARGET_S * 10), 10)]
    for gap in (*tenths, 1.0, 1.4, 0.0):
        for sign in (1.0, -1.0):
            lines.append(pace_sentence(sign * gap))
    for litres in (ON_TARGET_L, 0.3, 0.0):
        for sign in (1.0, -1.0):
            for against in (None, BURN_BASIS_PLAN, BURN_BASIS_RACE):
                lines.append(burn_sentence(sign * litres, against))
    return _pieces(*lines)


def volunteered_lines() -> tuple[str, ...]:
    """Every clip the families above need."""
    return tuple(dict.fromkeys((*colour_data_lines(), *off_road_lines(),
                                *refuel_lines(), *race_news_lines(),
                                *hud_alert_lines(), *target_lines())))


# The two references the fuel clause is measured against, mirrored from
# `calls.TO_THE_STOP` / `TO_THE_FLAG`. Imported lazily there would be a cycle;
# a test asserts the two stay in step.
# The uncertain form is only ever said from halfway through a timed race - his
# rule, 28 Aug 2026 - so the count it carries is at most half a race. Forty is
# generous against every format on file; beyond it the line falls to live
# synthesis, which early in a race it can afford to.
UNCERTAIN_LAPS = range(1, 41)


def _no_clock_line() -> str:
    from pitcrew.race.calls import NO_CLOCK

    return NO_CLOCK


def _no_notes_line() -> str:
    """What George says at the green when nobody wrote a briefing.

    It rides on the green call, which is the one sentence of the race that is
    true exactly once - so a fall to live synthesis here is a pause on the
    lights, and there is no second chance to say it.

    Imported, never retyped, like every other line in this file.
    """
    from pitcrew.race.knowledge import NO_NOTES

    return NO_NOTES


def _stop_pending_line() -> str:
    """`orientation`'s wording while a stop is still on the plan.

    It lands at every crossing of the second half of any race with a stop
    still to come, so a miss here is a live synthesis on every one of them.
    """
    from pitcrew.race.calls import RaceState, orientation

    state = RaceState(lap=13, laps_total=22, race_minutes=30.0,
                      stop_pending=True, stop_costs_laps=1)
    state.race_remaining_s = 660.0
    # The final sentence only: `_tails_of` splits ONE sentence on its ONE
    # number, and the whole line carries three.
    return orientation(state).rsplit(". ", 1)[-1]


def _laps_to_go_line(n: int) -> str:
    from pitcrew.race.calls import laps_to_go

    return laps_to_go(n)


def _minutes_line(seconds: float = 600.0) -> str:
    from pitcrew.race.calls import RaceState, minutes_left

    state = RaceState(lap=1)
    state.race_remaining_s = seconds
    return minutes_left(state)


def _seconds_line() -> str:
    from pitcrew.race.calls import RaceState, minutes_left

    state = RaceState(lap=1)
    state.race_remaining_s = 45.0
    return minutes_left(state)


def _colour_milestone(laps: int) -> str:   # laps REMAINING, not lap number
    """`colour.ColourCalls._milestone`'s wording, from the source.

    **It is not enumerated anywhere and it does not produce its own tail.**
    The tail came into the pack as a side effect of `_status` once saying
    "about N to go.", and when that wording changed on 28 Aug 2026 the
    milestone lines lost their clip with nothing failing except the one test
    that names them. Taken from the source now, so the two cannot drift again.
    """
    from pitcrew.race.colour import ColourCalls

    call = ColourCalls()._milestone(laps + 5, laps, laps + 5)
    if call is None:
        raise RuntimeError(
            "the milestone wording could not be read from its source - the "
            "pack must not fall back to a copy of it")
    return call.call


def _tails_of(*lines: str) -> tuple[str, ...]:
    """What is left of each line once its one number is peeled off.

    The number words are already in the pack and shared with four other
    sentences, so a family of a hundred costs one clip.
    """
    tails = []
    for line in lines:
        split = _split_on_number(line)
        if split:
            tails.append(split[-1])
    return tuple(dict.fromkeys(tails))


TO_THE_STOP_REF = "to the stop"
TO_THE_FLAG_REF = "to the flag"


def orientation_lines() -> tuple[str, ...]:
    """The heartbeat's own sentences, as families of one number each.

    **He turned GT7's race HUD off on 28 Aug 2026**, so the lap, the clock and
    the laps remaining reach him only here - and they reach him at every
    crossing. A family that falls through to live synthesis is a pause on
    every lap of the race, which is the one place the pack cannot afford one.

    `"Lap N or M."` is deliberately absent: it is said only when a crossing
    went missing, it carries two numbers, and it is a fault report rather than
    a figure to plan on. It misses, and it is rare enough to.

    `"N or M laps to go."` is NOT absent, though it has two numbers for the
    same reason. It is not rare: it is what every crossing says while the
    `ceil` sits near a boundary, which is a stretch of laps rather than an
    instant, and it is the figure he plans the end of the race on.
    """
    laps = range(1, MAX_LAPS + 1)
    return (
        # Tails, not enumerations: `_split_on_number` peels the figure and the
        # number words are already in the pack, shared with four other
        # sentences. Only "N or M laps to go." is enumerated, because two
        # numbers cannot be split - and it is not rare, it is what every
        # crossing says while the `ceil` sits near a boundary.
        "Lap",
        *(f"{n} or {n + 1} laps to go." for n in UNCERTAIN_LAPS),
        # `minutes_left` says "left" every time, so the bare form is not a
        # family the app can produce - and 120 clips nothing will ever play
        # is 120 clips of render time for nothing.
        # **Derived by asking the source, never retyped.** Two copies of a
        # spoken line drift, and the copy in the pack drifting is a silent
        # fall to live synthesis - which is a pause on every crossing of the
        # race at the cadence he asked for.
        *_tails_of(_laps_to_go_line(2), _laps_to_go_line(1),
                   # 110 s is the singular: "1 minute left." has its own
                   # tail and would otherwise miss in the last two minutes.
                   _minutes_line(), _minutes_line(110.0),
                   _seconds_line(), _colour_milestone(10),
                   _stop_pending_line()),
        # Where the fuel stands, which is the clause that ends every
        # heartbeat. Both references, because `fuel_frame` produces both and
        # a stop that gets cancelled mid-race swaps one for the other.
        *(f"Fuel good {ref}." for ref in (TO_THE_STOP_REF, TO_THE_FLAG_REF)),
        *(f"spare {ref}." for ref in (TO_THE_STOP_REF, TO_THE_FLAG_REF)),
        *(f"short {ref} on current burn."
          for ref in (TO_THE_STOP_REF, TO_THE_FLAG_REF)),
        "No burn figure yet.",
        # Imported, never retyped: two copies of a spoken line drift, and the
        # one in the pack drifting is a silent fall to live synthesis.
        _no_clock_line(),
        _no_notes_line(),
    )


def clips() -> tuple[str, ...]:
    """Everything the render tool should produce, de-duplicated."""
    everything = [
        *fixed_lines(),
        *position_lines(),
        *position_fragments(),
        *place_change_lines(),
        *lane_place_lines(),
        *laps_remaining_lines(),
        *box_when_lines(),
        *box_fuel_lines(),
        *compound_lines(),
        *tyre_word_lines(),
        *reason_lines(),
        *fuel_sentence_fragments(),
        *plan_single_part_lines(),
        *number_fragments(),
        *fuel_fragments(),
        *orientation_lines(),
        *race_call_lines(),
        *spoken_openers(),
        *volunteered_lines(),
        *lever_lines(),
        *replan_lines(),
        *quali_lines(),
    ]
    return tuple(dict.fromkeys(everything))


# ------------------------------------------------------------- playing back

def segments_for(text: str) -> tuple[str, ...] | None:
    """How to play `text` from the pack, or None if it cannot be.

    Returns the clips to play in order. Almost every answer is one clip; the
    fuel answer is four; a race call is its instruction, whatever whole lines
    it reuses, and the words either side of its one number.
    """
    if not text:
        return None
    shaped = _shaped(text)
    if shaped is not None:
        return shaped or None
    return _decompose(text)


def _shaped(sentence: str) -> tuple[str, ...] | None:
    """`sentence` played by one of the two fixed shapes, or None if neither.

    Returns an EMPTY tuple for a sentence that has the shape but a figure out
    of range - a shape that matched is never handed on to the generic split,
    which would cut it in the wrong place.

    **Applied per sentence, not only to the whole line** (Bathurst, 14 Sep
    2026). The shapes were anchored to the whole string and tried only in
    `segments_for`, so "P11 of 13. You've lost a place." reached `_decompose`,
    where "P11 of 13." went to `_split_on_number` - whose `(?<![\\w.])` edge
    rightly refuses the 11 in "P11", so it split on the 13 and asked for a
    clip called "P11 of" that nothing renders. Eleven position calls missed
    the pack that night, every one of them made of pieces the pack held.
    """
    match = _FUEL_LINE.match(sentence)
    if match is not None:
        whole, tenth = int(match.group(1)), int(match.group(2))
        if whole > MAX_FUEL_LAPS:
            return ()
        if match.group(3) not in fuel_fragments():
            return None
        # **The tail the sentence said, not the answer's sampled one.** This
        # returned `_fuel_tail()` - sampled with the reference "to the stop" -
        # whatever the line said, so the straight's "4.5 laps of fuel in hand
        # to the flag." and the answer's "4.5 laps of fuel in the tank." were
        # both PLAYED as "... in hand to the stop": the right number with the
        # other journey's words, the rule-13 defect produced by the pack
        # itself. A tail the pack does not hold is not this shape.
        return (number_word(whole), POINT, number_word(tenth), match.group(3))
    match = _POSITION_LINE.match(sentence)
    if match is not None:
        position, field = int(match.group(1)), int(match.group(2))
        if not 1 <= position <= MAX_POSITION or not 2 <= field <= MAX_FIELD:
            return ()
        return (f"P{position}", f"of {field}.")
    match = _ROAD_LINE.match(sentence)
    if match is not None:
        position = int(match.group(1))
        if not 1 <= position <= MAX_POSITION:
            return ()
        return (f"P{position}", "on the road.")
    match = _EFFECTIVE_LINE.match(sentence)
    if match is not None:
        position = int(match.group(1))
        if not 1 <= position <= MAX_POSITION:
            return ()
        return ("Effectively", f"P{position}", "after the stops.")
    return None


@lru_cache(maxsize=1)
def _reusable_lines() -> frozenset[str]:
    """Whole lines the pack already carries, which a race call can reuse.

    A box call is "Box this lap." plus a compound plus a fuel figure, and all
    three are already rendered for the questions the driver asks - so the
    proactive call costs the pack nothing but the words that join them.
    """
    return frozenset((*fixed_lines(), *position_lines(), *compound_lines(),
                      # The decision in a box call, peelable on its own so
                      # "Box this lap. RS on. 3 laps overdue." is three
                      # clips and a number rather than one miss.
                      *tyre_word_lines(),
                      # And the reasons, so the peel reaches the fuel
                      # sentence behind them (critic 3).
                      *reason_lines(),
                      # The engineer's position call is a position line and a
                      # place-change line, both whole and both already here -
                      # so the call itself costs the pack nothing.
                      *place_change_lines(),
                      # And its lane-made reasons, whole (`lane_place_lines`).
                      *lane_place_lines(),
                      *orientation_lines(),
                      *spoken_openers(),
                      # "You're back on it." and "Go." open a line whose
                      # second sentence carries the number - peelable, or
                      # the whole line is one clip nothing renders.
                      *(line for line in volunteered_lines()
                        if line.endswith(".") and line[0].isupper()),
                      *box_when_lines(), *box_fuel_lines(),
                      *laps_remaining_lines(), *plan_single_part_lines(),
                      *call_openers()))


def _split_on_number(sentence: str) -> tuple[str, ...] | None:
    """One sentence as (words before, the number, words after), or None.

    None where it has no number or more than one - several means the wording
    is combinatorial and splitting it would invent an ordering the pack cannot
    honour.
    """
    found = _NUMBER.findall(sentence)
    if len(found) != 1:
        return None
    match = _NUMBER.search(sentence)
    whole = int(match.group(1))
    if whole > MAX_FUEL_LITRES:
        return None
    number = [number_word(whole)]
    if match.group(2) is not None:
        number += [POINT, number_word(int(match.group(2)))]
    head = sentence[:match.start()].strip()
    tail = sentence[match.end():]
    if match.group(3):
        tail = PERCENT + tail
    tail = tail.strip()
    # **A tail of nothing but punctuation is not a clip.** "Lap 5." ends on
    # its number, so the tail is "." - and rendering that is a wav whose
    # entire content is a full stop, looked up and concatenated into every
    # heartbeat of the race. The sentence boundary is the join, not a sound.
    if tail in {".", "!", "?", ",", ".."}:
        tail = ""
    return tuple(part for part in (head, *number, tail) if part)


def _decompose(text: str) -> tuple[str, ...]:
    """A line as the clips that make it up.

    Two steps, in this order. **Peel** leading sentences that are already
    clips, longest-known-prefix first, so "Box this lap. RS. Fuel to 37
    litres." is three clips the pack already had. Then **split** what is left
    on its single number, if it has exactly one, so "12 to go." is a number
    word and a tail.

    Anything else is one clip. That is not a failure - it is how every fixed
    line has always been played - and a line whose clip has not been rendered
    simply misses and is synthesised live.
    """
    parts: list[str] = []
    rest = text
    while rest:
        if rest in _reusable_lines():
            return (*parts, rest)
        head, separator, tail = rest.partition(". ")
        if not separator:
            break
        sentence = f"{head}."
        if sentence in _reusable_lines():
            parts.append(sentence)
            rest = tail
            continue
        # **A sentence that is not a clip is split on its own number, and the
        # walk goes on.** It used to stop here and hand back everything that
        # followed as one clip, which was fine while at most one sentence in a
        # call carried a number. The heartbeat carries up to four - the lap,
        # the clock, the laps remaining and the fuel - so stopping at the
        # first would have made every crossing of the race a pack miss, and
        # rendering the combinations whole is tens of thousands of files.
        shaped = _shaped(sentence)
        if shaped == ():
            # The shape, with a figure the pack has no clip for: a miss, and
            # said whole rather than cut somewhere arbitrary.
            return (*parts, rest)
        split = (shaped or _split_on_number(sentence)
                 or _split_on_numbers(sentence))
        if split is None:
            break
        parts.extend(split)
        rest = tail
    if not rest:
        return tuple(parts)
    shaped = _shaped(rest)
    if shaped:
        return (*parts, *shaped)

    # **One implementation of the split.** This was a second copy of
    # `_split_on_number`, and the two drifted the moment one of them learned
    # that a tail of bare punctuation is not a clip: `segments_for("Lap 5.")`
    # went on asking for a wav containing a full stop while the per-sentence
    # path had stopped. A line that asks for a clip the manifest no longer
    # declares is a silent miss and a live synthesis.
    split = _split_on_number(rest) or _split_on_numbers(rest)
    if split is None:
        # No number, or several: several means the line is combinatorial - the
        # plan summary is the one that reaches here - and splitting it would
        # invent an ordering the pack cannot honour.
        return (*parts, rest)
    return (*parts, *split)


# The exact shape `_plan_summary` builds: a stop clause, an optional compound
# and an optional laps-remaining, comma-joined into one sentence. Every clause
# after the first is what makes it combinatorial, so the single-clause form -
# which `plan_single_part_lines` renders whole - deliberately does not count.
_PLAN_SUMMARY = re.compile(
    # "Box next lap" since the box ladder's rung 2 (e9c7657): without it a
    # summary on that lap logged as "not in the manifest", a bug, instead of
    # the known combinatorial gap it is.
    r"^(?:Running to the flag|Box this lap|Box next lap|Box in \d+ laps?)"
    r"(, onto .+?|, no tyres|, tyres on)?(, \d+ laps? to go)?\.$")


def uncovered_reason(text: str) -> str | None:
    """Why a line is not in the pack, when it is a known gap rather than a bug.

    Two families, each recognised by its own shape rather than by a comma:

    * **The plan summary** - a stop phrase, an optional compound and an
      optional laps-remaining, comma-joined. Ninety-nine stop counts times
      twenty-two compounds times a hundred lap counts.
    * **A call with two numbers left in one clause** after everything the pack
      already carries has been peeled off it. The fuel-short call that names
      both the shortfall and what the leanest map still leaves is the one
      today; the rule is written structurally so the next one is covered
      without anybody remembering to come back here.

    Both are said on a straight rather than mid-corner, so live synthesis is
    an acceptable cost - but it is stated here so it never reads as an
    oversight.

    This used to be `"," in text and text not in fixed_lines()`, which is a
    test for a comma and not for anything else: it attached this confident
    explanation to every other line with a comma in it, starting with the
    green-flag call.
    """
    match = _PLAN_SUMMARY.match(text)
    if match is not None and any(match.groups()):
        return ("the plan summary is combinatorial - stop phrase, optional "
                "compound, optional laps remaining - so it is synthesised live")
    for segment in segments_for(text) or ():
        numbers = len(_NUMBER.findall(segment))
        if numbers > 1:
            return (f"{numbers} numbers left in one clause, so a clip per "
                    f"combination is tens of thousands of files - it is "
                    f"synthesised live")
    return None


def plan_summary_examples() -> tuple[str, ...]:
    """A representative sweep of plan summaries, for the coverage test."""
    snapshots = [
        {},
        {"lapsToStop": 0},
        {"lapsToStop": 1},
        {"lapsToStop": 2, "nextCompound": "Racing Medium"},
        {"lapsToStop": 4},
        {"lapsToStop": 4, "nextCompound": "Racing Medium"},
        {"lapsToStop": 4, "lapsRemaining": 1},
        {"lapsToStop": 4, "nextCompound": "Racing Soft", "lapsRemaining": 12},
        {"lapsToStop": 4, "nextCompound": "RS", "nextTyres": False,
         "lapsRemaining": 12},
        {"lapsToStop": 4, "nextTyres": True, "lapsRemaining": 12},
        {"nextCompound": "Racing Hard", "lapsRemaining": 20},
        {"lapsRemaining": 0},
    ]
    return tuple(_text(PLAN, {"hasPlan": True, **snapshot})
                 for snapshot in snapshots)


def race_call_examples() -> tuple[str, ...]:
    """A representative sweep of proactive calls, for the coverage test.

    Wider than `_call_states()`: that one only has to reach every shape once,
    where this sweeps the numbers inside them, which is where a missing number
    word would hide.
    """
    states = list(_call_states())
    # The box call a real race makes, with its fuel figure (critic 3).
    states += _box_fuel_states()
    states += [_state(lap=0, laps_total=n) for n in range(1, MAX_LAPS + 1)]
    states += [_state(lap=6, finished=True, position=n)
               for n in range(1, MAX_POSITION + 1)]
    states += [_state(lap=5, laps_total=n + 5, position=3)
               for n in range(0, MAX_LAPS - 5)]
    states += [_state(lap=6, laps_total=20, stint_ends_on_lap=7,
                      fuel_per_lap_l=litres / 15.0, fuel_capacity_l=100.0)
               for litres in range(15, MAX_FUEL_LITRES + 1, 5)]
    lines = []
    for state in states:
        call = _next_call(state)
        if call is not None and call.spoken():
            lines.append(call.spoken())
    return tuple(dict.fromkeys(lines))
