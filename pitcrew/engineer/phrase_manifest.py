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
        _text(FUEL, {}),                                     # no fuel rate
        _text(BOX_WHEN, {}),                                 # no plan at all
        _text(BOX_WHEN, {"hasPlan": True}),                  # no stop planned
        _text(BOX_WHEN, {"lapsToStop": 0}),                  # box this lap
        _text(BOX_WHAT, {}),                                 # no plan at all
        _text(BOX_WHAT, {"hasPlan": True}),                  # no tyre change
        _text(BOX_FUEL, {}),                                 # no fuel target
        _text(GAP, {}),                                      # never answerable
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
    return tuple(dict.fromkeys(lines))


@lru_cache(maxsize=1)
def number_fragments() -> tuple[str, ...]:
    """The number words, shared by every line assembled from parts.

    "4.5 laps of fuel.", "12 to go.", "20 laps." and "1.2 laps short on fuel."
    between them would be thousands of whole clips. One set of number words
    serves all of them, which is how a pre-recorded pack has always worked.
    """
    return tuple(number_word(n) for n in range(0, MAX_LAPS + 1))


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
        _state(lap=6, stint_ends_on_lap=6),                   # box now
        _state(lap=6, stint_ends_on_lap=7),                   # box next lap
        _state(lap=6, stint_ends_on_lap=8),                   # box in 2
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
        _state(lap=8, laps_total=20, fuel_l=82.3, fuel_per_lap_l=6.0,
               position=11, stint_ends_on_lap=10, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0),
        _state(lap=19, laps_total=20, fuel_l=7.0, fuel_per_lap_l=6.0,
               position=11, stint_ends_on_lap=19, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0),
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
        _state(lap=6, laps_total=20, stint_ends_on_lap=6,
               mandatory_stops_left=1),
        _state(lap=6, laps_total=40, stint_ends_on_lap=6, fuel_l=40.0,
               fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0),
        # **The ungranted drop, which is the DEFAULT branch**: with no
        # playbook granting `fuel_long: drop_stop`, this is what a
        # fuel-covered race says at the box lap. `stops_off_said` is
        # required or `STOPS_OFF` outranks the box call and the state
        # renders nothing at all.
        _state(lap=10, laps_total=20, stint_ends_on_lap=10, fuel_l=60.0,
               fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0,
               drop_stop_granted=False, stops_off_said=True),
        _state(lap=8, laps_total=20, stint_ends_on_lap=10, fuel_l=60.0,
               fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
               plan_binding_constraint="fuel", mandatory_stops_left=0,
               drop_stop_granted=False, stops_off_said=True),
        # **And every stop number, because the ordinal renders whole.** The
        # plain box-soon is already swept over `range(MAX_STOPS)` for exactly
        # that reason; this branch was pinned at stop 1, so "Stop 2, on the
        # plan. Fuel would reach the flag - dropping the stop was not
        # granted." would have fallen through to live synthesis.
        *[_state(lap=8, laps_total=20, stint_ends_on_lap=10, fuel_l=60.0,
                 fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                 plan_binding_constraint="fuel", mandatory_stops_left=0,
                 drop_stop_granted=False, stops_off_said=True,
                 stint_index=index)
          for index in range(1, MAX_STOPS)],
        # Box soon carries the same reason two laps earlier.
        _state(lap=5, laps_total=20, stint_ends_on_lap=6,
               mandatory_stops_left=1),
        _state(lap=5, laps_total=40, stint_ends_on_lap=6, fuel_l=40.0,
               fuel_per_lap_l=3.0, plan_binding_constraint="fuel",
               mandatory_stops_left=0),
        # Box now: on the plan, to a fuel figure, and clamped to the tank.
        _state(lap=6, stint_ends_on_lap=6),
        _state(lap=6, laps_total=20, stint_ends_on_lap=6,
               fuel_per_lap_l=3.4, fuel_capacity_l=100.0),
        _state(lap=6, laps_total=99, stint_ends_on_lap=6,
               fuel_per_lap_l=9.0, fuel_capacity_l=100.0),
        # Fuel calls, and the modelled-wear warning - including the one made
        # through a stop that never said whether the tyres came off.
        _state(lap=18, laps_total=20, fuel_l=20.0, fuel_per_lap_l=1.0),
        _state(lap=6, laps_since_stop=6, wear_per_lap=0.15),
        _state(lap=6, laps_since_stop=6, wear_per_lap=0.15,
               tyre_change_unconfirmed=True),
    ]
    states += [_state(lap=6, laps_total=16, fuel_l=onboard,
                      fuel_per_lap_l=1.0)
               for onboard in _fuel_short_onboard()]
    # Every compound the plan can call for, on a box-now.
    states += [_state(lap=6, stint_ends_on_lap=6, next_compound=code)
               for code in _compound_words()]
    # Every stop number a box-soon can announce, at both distances.
    for stint in range(0, MAX_STOPS):
        states += [_state(lap=6, stint_ends_on_lap=7, stint_index=stint),
                   _state(lap=6, stint_ends_on_lap=8, stint_index=stint)]
    return states


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
        *laps_remaining_lines(),
        *box_when_lines(),
        *box_fuel_lines(),
        *compound_lines(),
        *plan_single_part_lines(),
        *number_fragments(),
        *fuel_fragments(),
        *orientation_lines(),
        *race_call_lines(),
        *spoken_openers(),
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
    match = _FUEL_LINE.match(text)
    if match is not None:
        whole, tenth = int(match.group(1)), int(match.group(2))
        if whole > MAX_FUEL_LAPS:
            return None
        return (number_word(whole), POINT, number_word(tenth), _fuel_tail())
    match = _POSITION_LINE.match(text)
    if match is not None:
        position, field = int(match.group(1)), int(match.group(2))
        if not 1 <= position <= MAX_POSITION or not 2 <= field <= MAX_FIELD:
            return None
        return (f"P{position}", f"of {field}.")
    return _decompose(text)


@lru_cache(maxsize=1)
def _reusable_lines() -> frozenset[str]:
    """Whole lines the pack already carries, which a race call can reuse.

    A box call is "Box this lap." plus a compound plus a fuel figure, and all
    three are already rendered for the questions the driver asks - so the
    proactive call costs the pack nothing but the words that join them.
    """
    return frozenset((*fixed_lines(), *position_lines(), *compound_lines(),
                      # The engineer's position call is a position line and a
                      # place-change line, both whole and both already here -
                      # so the call itself costs the pack nothing.
                      *place_change_lines(),
                      *orientation_lines(),
                      *spoken_openers(),
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
    if whole > MAX_LAPS:
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
        split = _split_on_number(sentence)
        if split is None:
            break
        parts.extend(split)
        rest = tail
    if not rest:
        return tuple(parts)

    # **One implementation of the split.** This was a second copy of
    # `_split_on_number`, and the two drifted the moment one of them learned
    # that a tail of bare punctuation is not a clip: `segments_for("Lap 5.")`
    # went on asking for a wav containing a full stop while the per-sentence
    # path had stopped. A line that asks for a clip the manifest no longer
    # declares is a silent miss and a live synthesis.
    split = _split_on_number(rest)
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
    r"^(?:Running to the flag|Box this lap|Box in \d+ laps?)"
    r"(, onto .+?)?(, \d+ laps? to go)?\.$")


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
        {"lapsToStop": 4},
        {"lapsToStop": 4, "nextCompound": "Racing Medium"},
        {"lapsToStop": 4, "lapsRemaining": 1},
        {"lapsToStop": 4, "nextCompound": "Racing Soft", "lapsRemaining": 12},
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
    states += [_state(lap=0, laps_total=n) for n in range(1, MAX_LAPS + 1)]
    states += [_state(lap=6, finished=True, position=n)
               for n in range(1, MAX_POSITION + 1)]
    states += [_state(lap=5, laps_total=n + 5, position=3)
               for n in range(0, MAX_LAPS - 5)]
    states += [_state(lap=6, laps_total=20, stint_ends_on_lap=6,
                      fuel_per_lap_l=litres / 15.0, fuel_capacity_l=100.0)
               for litres in range(15, MAX_FUEL_LITRES + 1, 5)]
    lines = []
    for state in states:
        call = _next_call(state)
        if call is not None and call.spoken():
            lines.append(call.spoken())
    return tuple(dict.fromkeys(lines))
