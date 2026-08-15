"""What the engineer says, and when.

CLAUDE.md §5.5 is the spec, and it is unusually strict about form because the
driver hears this under a helmet at racing speed:

    "Box this lap or next. Fuel is the constraint - you're 1.2 laps short."

One thing at a time. The instruction first, the reason second and short. Not a
table, not three options. If the app is not confident it says so **inside the
call**, because "unconfirmed" is a word the driver can act on.

So this module returns **at most one call per lap** — the most urgent thing
true right now. A second call would arrive while he is still processing the
first, and two instructions at once is the same as none.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.strategy.model import FUEL_MAP_CONSUMPTION

# Confidence travels with every call so a guess never sounds like a reading.
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# Kinds, ordered by urgency. The first match wins the lap.
BOX_NOW = "box-now"
BOX_SOON = "box-soon"
FUEL_SHORT = "fuel-short"
FUEL_LONG = "fuel-long"
TYRE = "tyre"
STATUS = "status"
GREEN = "green"
CHEQUER = "chequer"

URGENCY = (BOX_NOW, FUEL_SHORT, BOX_SOON, TYRE, FUEL_LONG, GREEN, CHEQUER,
           STATUS)

# A status call every few laps, so silence means "nothing to report" rather
# than "the app has died".
STATUS_EVERY_LAPS = 5

# Fuel margin below which the plan no longer reaches the stop.
FUEL_SHORT_LAPS = 0.5
# Fuel surplus above which he is carrying a lap he does not need.
FUEL_LONG_LAPS = 1.5

# How much worse a thing has to get before it is worth saying twice, in the
# units of the call itself. The docstring on `next_call` has always promised
# re-issue "unless it has become more urgent" and nothing implemented it: a
# shortfall warned at 3.8 laps was met with silence at 4.9, 5.9 and 7.0. These
# are the stated thresholds that promise now rests on - large enough that a
# drifting number does not chatter, small enough that a lap of fuel going
# missing is always spoken.
WORSE_BY = {
    FUEL_SHORT: 0.5,     # half a lap further short
    FUEL_LONG: 1.0,      # another lap in hand
    TYRE: 0.10,          # ten more points of modelled life gone
    BOX_NOW: 1.0,        # another lap overdue at the stop
    BOX_SOON: 1.0,       # a lap closer to it
}


@dataclass(frozen=True)
class Call:
    """One thing said, with why and how sure."""
    kind: str
    lap: int
    call: str
    reason: str
    confidence: str = HIGH
    # What the call was made *at*, in its own units, with larger meaning
    # worse. Not exported and never spoken: it exists so the same call can be
    # made again when the thing it was about has deteriorated.
    severity: float | None = None

    def spoken(self) -> str:
        """Instruction, then reason. Confidence only when it is not high."""
        text = self.call
        if self.reason:
            text = f"{text} {self.reason}"
        if self.confidence == LOW:
            text = f"{text} Unconfirmed."
        return text

    def as_export(self) -> dict:
        return {
            "lap": self.lap,
            "call": self.call,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class RaceState:
    """What is true right now, as far as the app can tell."""
    lap: int = 0                       # laps completed
    laps_total: int | None = None
    # Set when the race runs to the clock rather than to a distance. The lap
    # count is then a **derived** figure - the distance the approved plan
    # expects to cover - and every remaining-laps number said out loud is an
    # estimate, so the calls say "about". `events.race_laps` holds the minutes
    # for a timed race, which is how a 45-minute Monza came to be raced as a
    # 45-lap one: "40 to go" with 19 left, and a fuel shortfall to match.
    race_minutes: float | None = None
    fuel_l: float | None = None
    fuel_per_lap_l: float | None = None
    # What the tank actually holds. Without it the engineer will ask for a
    # fuel figure the car cannot take - and it did: "Fuel to 510 litres."
    fuel_capacity_l: float | None = None
    position: int | None = None
    in_pit: bool = False
    finished: bool = False
    # Stint accounting against the approved plan.
    stint_index: int = 0
    stint_ends_on_lap: int | None = None
    next_compound: str | None = None
    # How long the stint *after* the next stop is. The fill at that stop is
    # for that stint and not for the rest of the race: fuelling to the flag at
    # stop 1 of a two-stop asks for a tankful nobody needs, and where the tank
    # cannot hold it the call became a shortfall that does not exist.
    next_stint_laps: int | None = None
    wear_per_lap: float | None = None
    laps_since_stop: int = 0
    # A stop was made and nothing said whether the tyres came off. The wear
    # model keeps counting through it - GT7 lets you take fuel without taking
    # tyres - and the call that rests on it says so out loud.
    tyre_change_unconfirmed: bool = False
    said: list[str] = field(default_factory=list)
    # What each kind was last said at, so a call can be made again when it has
    # got worse. Kept beside `said` rather than inside it because `said` is
    # read as a plain list of kinds in half a dozen places.
    said_at: dict[str, float] = field(default_factory=dict)

    def laps_remaining(self) -> int | None:
        if self.laps_total is None:
            return None
        return max(0, self.laps_total - self.lap)

    def laps_of_fuel(self) -> float | None:
        """How many more laps the fuel on board covers."""
        if self.fuel_l is None or not self.fuel_per_lap_l:
            return None
        return self.fuel_l / self.fuel_per_lap_l

    def laps_to_stop(self) -> int | None:
        """Laps still to run before the planned stop. **Never negative.**

        A stop cannot be fewer than no laps away, and the negative this used
        to return was read straight into the fuel gap as surplus: every lap
        run past the box lap *added* to the fuel reported in hand. "You can
        push. 2.9 laps of fuel in hand." was spoken at high confidence with
        0.88 laps aboard.
        """
        if self.stint_ends_on_lap is None:
            return None
        return max(0, self.stint_ends_on_lap - self.lap)

    @property
    def past_box_lap(self) -> bool:
        """The planned stop has come and it has not been taken."""
        return (self.stint_ends_on_lap is not None
                and self.lap >= self.stint_ends_on_lap)

    def record(self, call: Call) -> None:
        """Remember a call was made, and how bad it was when it was."""
        if call.kind not in self.said:
            self.said.append(call.kind)
        if call.severity is not None:
            self.said_at[call.kind] = call.severity


def _fuel_target(state: RaceState) -> float | None:
    """Laps that have to be covered on the fuel now aboard.

    The stop when there is one still to come, the flag when there is not.
    **Flooring `laps_to_stop` at zero is not enough on its own**: at a target
    of zero the gap becomes the whole tank and the "you can push" call fires
    harder than ever. Once the box lap has gone by, the honest target is the
    rest of the race - he is running on this fuel until he actually stops.
    """
    if state.past_box_lap:
        return state.laps_remaining()
    to_stop = state.laps_to_stop()
    return state.laps_remaining() if to_stop is None else to_stop


def _fuel_gap(state: RaceState) -> float | None:
    """Laps of fuel minus laps still to run before the stop.

    Negative means short. This is the number the driver acts on, so it is
    computed once and reused rather than re-derived per call.
    """
    onboard = state.laps_of_fuel()
    if onboard is None:
        return None
    target = _fuel_target(state)
    if target is None:
        return None
    return onboard - target


def next_call(state: RaceState) -> Call | None:
    """The single most urgent thing true this lap, or nothing.

    Silence is a valid answer and the common one. A call repeated every lap
    stops being information, so anything already said this stint is suppressed
    unless it has become more urgent.
    """
    candidates = [c for c in _candidates(state) if c is not None]
    if not candidates:
        return None
    candidates.sort(key=lambda c: URGENCY.index(c.kind))
    for call in candidates:
        if _worth_saying_again(state, call):
            return call
    return None


def _worth_saying_again(state: RaceState, call: Call) -> bool:
    """Whether a call already made this stint should be made again.

    Only on a **stated deterioration**, in the units of the call itself: a
    repeated call stops being information, but silence while a shortfall
    doubles is worse - the driver reads silence as "nothing has changed",
    which is exactly what `_status` promises it means.
    """
    if call.kind not in state.said:
        return True
    if call.kind == STATUS:
        # `STATUS_EVERY_LAPS` is already this call's rate limiter. Suppressing
        # it as well meant the reassuring call could only ever be made once,
        # on lap 5, and never again for the rest of the race.
        return True
    margin = WORSE_BY.get(call.kind)
    was = state.said_at.get(call.kind)
    if margin is None or call.severity is None or was is None:
        return False
    return call.severity >= was + margin


def _candidates(state: RaceState) -> list[Call | None]:
    return [
        _chequer(state),
        _green(state),
        _box_now(state),
        _box_soon(state),
        _fuel(state),
        _tyre(state),
        _status(state),
    ]


def _green(state: RaceState) -> Call | None:
    if state.lap != 0 or state.finished:
        return None
    laps = f"{state.laps_total} laps." if state.laps_total else ""
    return Call(GREEN, 0, "Green, green, green.", laps)


def _chequer(state: RaceState) -> Call | None:
    if not state.finished:
        return None
    where = f"P{state.position}." if state.position else ""
    return Call(CHEQUER, state.lap, "Chequered flag.", where)


def _box_now(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if to_stop > 0:
        return None

    fuel = _fuel_instruction(state)
    compound = f" {state.next_compound}." if state.next_compound else ""
    # `to_stop` is not None here, so neither is the lap it came from.
    overdue = state.lap - (state.stint_ends_on_lap or 0)
    return Call(
        BOX_NOW, state.lap,
        f"Box this lap.{compound}",
        fuel or "On the plan.",
        severity=float(overdue),
    )


def _box_soon(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if not 1 <= to_stop <= 2:
        return None
    return Call(
        BOX_SOON, state.lap,
        f"Box in {to_stop}." if to_stop > 1 else "Box next lap.",
        f"Stop {state.stint_index + 1}, on the plan.",
        severity=float(-to_stop),
    )


def _fuel_instruction(state: RaceState) -> str:
    """How much to take, in litres, to the diamond plus a lap.

    **For the next stint, not for the rest of the race.** In a multi-stop race
    the fill at stop 1 has another stop after it, so fuelling to the flag asks
    for a tankful nobody needs - and where the tank cannot hold it, the call
    turned into a shortfall that does not exist. The stint's own lap count is
    the target and the burn is the one this race is showing, not the planned
    litres: the coordinator installs the race's measured rate for a reason,
    and reading the plan's `fuel_l` back would throw it away.

    Clamped to the tank, because an instruction the car cannot execute is
    worse than no instruction: the driver acts on it, finds the fill stops
    short, and has to work out the shortfall himself at pit-exit speed. When
    the clamp binds, the shortfall is the call - "fill it and you are still
    two laps short" is something he can plan around; "fuel to 510 litres" is
    not.
    """
    if not state.fuel_per_lap_l or state.laps_remaining() is None:
        return ""
    if state.next_stint_laps is not None:
        after_stop = state.next_stint_laps
    elif state.stint_ends_on_lap is not None:
        # A stop is planned but how long the stint after it runs is unknown.
        # Fuelling to the flag is the safe direction to be wrong in, and the
        # clamp still reports what the tank cannot cover.
        after_stop = (state.laps_total or 0) - state.stint_ends_on_lap
    else:
        after_stop = state.laps_remaining()
    litres = (after_stop + 1) * state.fuel_per_lap_l

    capacity = state.fuel_capacity_l
    if capacity and litres > capacity:
        short = (litres - capacity) / state.fuel_per_lap_l
        return f"Fuel to full. Still {short:.1f} laps short."
    return f"Fuel to {litres:.0f} litres."


def fuel_map_for(onboard_laps: float, needed_laps: float) -> tuple[int, float]:
    """The richest map that still reaches the target, and what it leaves short.

    CLAUDE.md §5.3: **map 1 is the richest**, 6 the leanest, and step 6 is
    anomalous - about half the fuel for about 80% of the power - so the map is
    read from the measured table rather than extrapolated down a straight line.

    The map has to follow from the shortfall. A fixed "Map 3" is 0.85 on that
    table, so it answers a deficit of 15% of the remaining distance and
    nothing larger: told to run map 3 with two laps missing from a ten-lap
    stint, the driver saves for the rest of the stint and still runs dry.

    Returns the leanest map and the laps it still cannot cover when even map 6
    is not enough - which is a box call, not a fuel-saving one, and the caller
    says so.
    """
    if needed_laps <= 0:
        return min(FUEL_MAP_CONSUMPTION), 0.0
    required = onboard_laps / needed_laps
    for level in sorted(FUEL_MAP_CONSUMPTION):
        if FUEL_MAP_CONSUMPTION[level] <= required:
            return level, 0.0
    leanest = max(FUEL_MAP_CONSUMPTION)
    still = needed_laps - onboard_laps / FUEL_MAP_CONSUMPTION[leanest]
    return leanest, still


def _fuel(state: RaceState) -> Call | None:
    gap = _fuel_gap(state)
    if gap is None or state.in_pit or state.finished:
        return None

    confidence = MEDIUM if state.lap < 3 else HIGH
    if gap < -FUEL_SHORT_LAPS:
        onboard = state.laps_of_fuel() or 0.0
        level, still = fuel_map_for(onboard, _fuel_target(state) or 0.0)
        reason = f"You're {abs(gap):.1f} laps short on fuel."
        if still > 0.05:
            reason += f" Map {level} still leaves {still:.1f}."
        return Call(
            FUEL_SHORT, state.lap,
            f"Map {level} down the straights.",
            reason,
            confidence,
            severity=-gap)
    if gap > FUEL_LONG_LAPS and _past_half_stint(state):
        # Only worth saying once the stint is half run. At the start of a
        # stint there is always surplus - the tank was just filled - and
        # "you can push" on lap one is noise the driver learns to ignore.
        return Call(
            FUEL_LONG, state.lap,
            "You can push.",
            f"{gap:.1f} laps of fuel in hand.",
            confidence,
            severity=gap)
    return None


def _past_half_stint(state: RaceState) -> bool:
    to_stop = state.laps_to_stop()
    if to_stop is None:
        remaining = state.laps_remaining()
        if remaining is None or state.laps_total is None:
            return True
        return state.lap >= state.laps_total / 2
    return state.laps_since_stop >= to_stop


def _tyre(state: RaceState) -> Call | None:
    """Only ever a warning, never a lap time.

    Wear is modelled, never measured, so this call carries low confidence by
    construction - and says so out loud.
    """
    if state.wear_per_lap is None or state.in_pit or state.finished:
        return None
    consumed = state.laps_since_stop * state.wear_per_lap
    if consumed < 0.85:
        return None
    reason = f"Modelled at {consumed:.0%}."
    if state.tyre_change_unconfirmed:
        # The count ran through a stop that said nothing about the tyres, so
        # the set may be fresher than this. Said out loud rather than folded
        # into the number: "unconfirmed" is a word the driver can act on.
        reason += " Counting through a stop that may have changed them."
    return Call(
        TYRE, state.lap,
        "Tyres are at the end of their window.",
        reason,
        LOW,
        severity=consumed)


def _status(state: RaceState) -> Call | None:
    """Proactive reassurance, rarely. Silence should mean nothing to report."""
    if state.lap < 1 or state.finished or state.in_pit:
        return None
    if state.lap % STATUS_EVERY_LAPS != 0:
        return None
    remaining = state.laps_remaining()
    where = f"P{state.position}." if state.position else ""
    # A timed race has no lap count to count down: the distance follows from
    # the plan and the flag falls on the clock, so the figure is an estimate
    # and is spoken as one.
    about = "about " if state.race_minutes else ""
    left = f"{about}{remaining} to go." if remaining is not None else ""
    return Call(STATUS, state.lap, f"{where} {left}".strip(), "")


def clear_stint(state: RaceState, *, tyres_changed: bool | None = None) -> None:
    """A stop resets what has been said, so the next stint speaks freshly.

    **The tyre model is only reset when the tyres actually changed.** GT7 lets
    you take fuel without taking tyres, and `analysis/runs.py` forbids the
    same inference offline for the same reason: treating every stop as a fresh
    set halves every wear rate that spans one, and here it silenced the
    end-of-window call for a whole further stint - the driver reading silence
    as nothing to report.

    `None` is "the stop said nothing either way", which is not "no". The count
    carries on and the call that rests on it is marked unconfirmed.
    """
    state.said = [kind for kind in state.said if kind in (GREEN,)]
    state.said_at = {kind: value for kind, value in state.said_at.items()
                     if kind in (GREEN,)}
    if tyres_changed:
        state.laps_since_stop = 0
        state.tyre_change_unconfirmed = False
    elif tyres_changed is None:
        state.tyre_change_unconfirmed = True
